"""Keep each (employee, day)'s Employee Checkins and its Attendance row
consistent no matter how punches arrive:

  - device batch pushes (bridge sends the whole day at once)
  - device streaming (ADMS pushes every punch within minutes)
  - late pushes after HRMS already marked the day's attendance
  - manual desk/API entries, edits and deletions

Two primitives, plus the Employee Checkin doc-event handlers that apply them:

  relabel_day_checkins — within one calendar day, checkins alternate
      IN, OUT, IN, ... in chronological order, with the day's last punch
      forced to OUT once there are two or more punches. This is the same
      policy the device pipeline (biometric/utils.py) applies on every sync;
      running it on manual entry/edit/delete keeps the day consistent for
      every source. Shifts here are day shifts — grouping is by calendar date.

  sync_day — link the day's orphan punches to an existing Present / Half Day
      Attendance and refresh the row's computed values (working hours, in/out
      times, late/early flags, shift-deviation fields) from the full punch set.

sync_day never changes status. A hand change to a PAST day's punches (form,
API) goes further and re-marks the whole day through hr/punch_correction —
status included — because a person editing a punch is making exactly the
decision Attendance Fix exists for; the punch is stamped and the Attendance
gets a comment, so the trail stays auditable. Device pushes never do: they
keep to sync_day and the self-heal.
"""

from collections import Counter
from datetime import datetime, time, timedelta

import frappe
from frappe.utils import cint, flt, get_datetime, getdate, today
from frappe.model.meta import get_field_precision

from hrms.hr.doctype.employee_checkin.employee_checkin import (
    update_attendance_in_checkins,
)

CHECKIN_FIELDS = [
    "name",
    "employee",
    "log_type",
    "time",
    "shift",
    "shift_start",
    "shift_end",
    "shift_actual_start",
    "shift_actual_end",
    "device_id",
    "attendance",
    "skip_auto_attendance",
]


def desired_log_type(idx, total):
    """Alternation policy: IN, OUT, IN, OUT, ... by order, nothing forced.

    An odd punch count (a forgotten punch) therefore ends on IN, which is the
    point: the day shows at a glance that a punch is missing (user,
    2026-10-15: "we do in out in"). Until then the last punch was forced to
    OUT, because a shift in "Strictly based on Log Type" mode reads the labels
    and would lose its out-time. Every Shift Type now uses "Alternating
    entries as IN and OUT", where HRMS takes the first punch as in and the
    last as out whatever the labels say (employee_checkin
    calculate_working_hours), so the labels are only what people read.
    `total` is kept for the callers."""
    return "IN" if idx % 2 == 0 else "OUT"


def get_day_checkins(employee, punch_date):
    """All of the employee's checkins for one calendar day, chronological."""
    day_start = datetime.combine(punch_date, time.min)
    day_end = datetime.combine(punch_date, time.max)
    return frappe.get_all(
        "Employee Checkin",
        filters={"employee": employee, "time": ("between", [day_start, day_end])},
        fields=CHECKIN_FIELDS,
        order_by="time asc, name asc",
    )


def relabel_day_checkins(employee, punch_date):
    """Re-apply the IN/OUT alternation to every checkin of the day. Returns
    the number of rows whose log_type changed.

    Manual log_type choices are deliberately overridden — the device pipeline
    already relabels the whole day on every sync, so alternation is the single
    policy for all sources."""
    rows = get_day_checkins(employee, punch_date)
    changed = 0
    for idx, row in enumerate(rows):
        desired = desired_log_type(idx, len(rows))
        if row.log_type != desired:
            frappe.db.set_value(
                "Employee Checkin", row.name, "log_type", desired,
                update_modified=False,
            )
            row.log_type = desired
            changed += 1
    return changed


def prepare_checkins_for_shift(checkins, shift_doc, include_skipped=False):
    """Make sure each checkin has shift fields populated. We call stock
    Employee Checkin.fetch_shift() if shift is missing, mirroring what the
    scheduled auto-attendance does. Re-fetching also repairs checkins stored
    before the employee had a shift assignment."""
    prepared = []
    for c in checkins:
        if c.skip_auto_attendance and not include_skipped:
            continue
        if not c.shift or not c.shift_actual_end:
            ck_doc = frappe.get_doc("Employee Checkin", c.name)
            ck_doc.fetch_shift()
            ck_doc.db_update()
            c.shift = ck_doc.shift
            c.shift_start = ck_doc.shift_start
            c.shift_end = ck_doc.shift_end
            c.shift_actual_start = ck_doc.shift_actual_start
            c.shift_actual_end = ck_doc.shift_actual_end

        if c.shift != shift_doc.name:
            continue
        prepared.append(c)
    return prepared


def _round_to_minute(seconds):
    """Round seconds to the nearest whole minute.
    >= 30 seconds → round up   (e.g. 30m 40s → 31m = 1860s)
    <  30 seconds → round down (e.g. 30m 20s → 30m = 1800s)
    """
    return int((int(seconds) + 30) / 60) * 60


def compute_shift_deviations(shift_doc, attendance_date, in_time, out_time):
    """The four custom deviation fields on Attendance (seconds, rounded to the
    nearest minute) for the given actual in/out against the shift's scheduled
    start/end. Only one of each pair is non-zero at a time."""
    values = {
        "custom_late_entry": 0,
        "custom_early_entry": 0,
        "custom_early_exit": 0,
        "custom_late_exit": 0,
    }
    attendance_date = getdate(attendance_date)
    shift_start_dt = datetime.combine(attendance_date, time.min) + shift_doc.start_time
    shift_end_dt = datetime.combine(attendance_date, time.min) + shift_doc.end_time
    # Overnight shift: end_time < start_time means end falls on next day
    if shift_doc.end_time < shift_doc.start_time:
        shift_end_dt += timedelta(days=1)

    if in_time:
        diff = (get_datetime(in_time) - shift_start_dt).total_seconds()
        if diff > 0:
            values["custom_late_entry"] = _round_to_minute(diff)
        elif diff < 0:
            values["custom_early_entry"] = _round_to_minute(abs(diff))

    if out_time:
        diff = (get_datetime(out_time) - shift_end_dt).total_seconds()
        if diff > 0:
            values["custom_late_exit"] = _round_to_minute(diff)
        elif diff < 0:
            values["custom_early_exit"] = _round_to_minute(abs(diff))

    return values


def refresh_attendance_values(attendance_name, shift_doc, checkins):
    """Recompute the value fields of an existing Attendance from the day's
    checkins: working_hours, in_time, out_time, late_entry, early_exit and the
    custom shift-deviation fields.

    Writes through db.set_value so it works on submitted rows. NEVER touches
    status — status transitions belong to Attendance Fix / self-heal. Skipped
    (skip_auto_attendance) checkins are included: the flag only means "don't
    auto-process", the punch itself is real. Returns True if anything changed."""
    prepared = prepare_checkins_for_shift(checkins, shift_doc, include_skipped=True)
    if not prepared:
        return False

    (
        _status,
        working_hours,
        late_entry,
        early_exit,
        in_time,
        out_time,
    ) = shift_doc.get_attendance(prepared)

    current = frappe.db.get_value(
        "Attendance",
        attendance_name,
        ["attendance_date", "working_hours", "late_entry", "early_exit", "in_time", "out_time"],
        as_dict=True,
    )
    if not current:
        return False

    def _dt(value):
        return get_datetime(value) if value else None

    # Round to the field's own precision before comparing OR writing.
    # Attendance.working_hours is decimal(21,1) on hrms 15.49.2 (2 dp on later
    # releases), so the database itself rounds 8.32 down to 8.3 on write.
    # Comparing the unrounded computed value against the rounded stored one
    # made every call look like a change: the row was rewritten, and a repair
    # logged, on every single self-heal pass — for every Present day in the
    # 45-day window, on every run, without ever converging.
    hours_precision = get_field_precision(
        frappe.get_meta("Attendance").get_field("working_hours")
    )
    working_hours = flt(working_hours, hours_precision)

    updates = {}
    if flt(current.working_hours, hours_precision) != working_hours:
        updates["working_hours"] = working_hours
    if cint(current.late_entry) != cint(bool(late_entry)):
        updates["late_entry"] = cint(bool(late_entry))
    if cint(current.early_exit) != cint(bool(early_exit)):
        updates["early_exit"] = cint(bool(early_exit))
    if _dt(current.in_time) != _dt(in_time):
        updates["in_time"] = in_time
    if _dt(current.out_time) != _dt(out_time):
        updates["out_time"] = out_time

    if "in_time" in updates or "out_time" in updates:
        updates.update(
            compute_shift_deviations(shift_doc, current.attendance_date, in_time, out_time)
        )

    if not updates:
        return False
    frappe.db.set_value("Attendance", attendance_name, updates)
    return True


def sync_day(employee, punch_date):
    """Link the day's orphan punches to its existing Present / Half Day
    Attendance and refresh the row's computed values.

    Past dates only — today belongs to the realtime auto-attendance flow.
    Days with no Attendance yet, or marked Absent / WFH, are left alone:
    creating rows and changing status are Attendance Fix / self-heal
    territory. The one status change made here is policy 3.4: a leave day
    the person punched on becomes a Half Day (today included), and is then
    synced like any other. Returns True when the day had a row to sync."""
    from avinashgroup_app.biometric.attendance_override import half_day_if_came_in

    punch_date = getdate(punch_date)
    half_day_if_came_in(employee, punch_date)
    if punch_date >= getdate(today()):
        return False

    existing = frappe.db.get_value(
        "Attendance",
        {
            "employee": employee,
            "attendance_date": punch_date,
            "docstatus": ("<", 2),
            "status": ("in", ("Present", "Half Day")),
        },
        ["name", "status", "shift"],
        as_dict=True,
    )
    if not existing:
        return False

    checkins = get_day_checkins(employee, punch_date)
    if not checkins:
        return False

    orphans = {c.name for c in checkins if not c.attendance}
    if orphans:
        update_attendance_in_checkins(list(orphans), existing.name)
        for c in checkins:
            if c.name in orphans:
                c.attendance = existing.name
                if c.skip_auto_attendance:
                    # Linked logs are no longer skipped — clear stale poison flags.
                    frappe.db.set_value(
                        "Employee Checkin", c.name, "skip_auto_attendance", 0,
                        update_modified=False,
                    )
                    c.skip_auto_attendance = 0

    shift_doc = _resolve_shift_doc(existing.shift, checkins, employee)
    if shift_doc:
        refresh_attendance_values(existing.name, shift_doc, checkins)
    return True


def _resolve_shift_doc(shift_name, checkins, employee):
    if not shift_name:
        named = [c.shift for c in checkins if c.shift]
        shift_name = (
            Counter(named).most_common(1)[0][0]
            if named
            else frappe.db.get_value("Employee", employee, "default_shift")
        )
    if not shift_name:
        return None
    return frappe.get_cached_doc("Shift Type", shift_name)


# ---------------------------------------------------------------------------
# Employee Checkin doc-event handlers
# ---------------------------------------------------------------------------
#
# A punch entered, moved or deleted by hand on a PAST day re-marks that day the
# way the Monthly Attendance BS correction does (hr/punch_correction): punches
# pinned to the rostered shift, attendance rebuilt, overtime re-measured, and
# the punch stamped for the report's highlight. Before this, only a Present /
# Half Day row had its values refreshed (sync_day): a punch added to an Absent
# day changed nothing, and one HRMS gave to the default shift was ignored.
# Today, and days the correction refuses (paid, leave, no or overnight shift),
# keep the value-only sync_day.
#
# Never per punch during ingest: the device pipeline sets
# frappe.flags.in_biometric_day_reconcile and reconciles each day once itself,
# and HRMS auto attendance links punches with a query, firing no doc events.


def _manual(doc):
    return not frappe.flags.in_biometric_day_reconcile and doc.employee and doc.time


def _remark_or_sync(employee, day, note):
    from avinashgroup_app.hr.punch_correction import remark_from_form

    if not remark_from_form(employee, day, note):
        sync_day(employee, day)


def checkin_before_validate(doc, method=None):
    """Let a linked punch on a past day be moved. HRMS refuses any time change
    on a punch linked to an attendance ("cancel the attendance first"); the day
    is rebuilt in on_update anyway, so drop the link here when it will be. On a
    paid or leave day the link stays and HRMS's refusal stands."""
    if not _manual(doc) or doc.is_new() or not doc.attendance:
        return
    if not doc.has_value_changed("time"):
        return
    from avinashgroup_app.hr.punch_correction import can_detach

    before = doc.get_doc_before_save()
    days = {getdate(doc.time)} | ({getdate(before.time)} if before and before.time else set())
    if can_detach(doc.employee, days):
        doc.attendance = None


def checkin_after_insert(doc, method=None):
    """A checkin created outside the device pipeline (desk form, API, mobile).
    Pipeline inserts set frappe.flags.in_biometric_day_reconcile and are handled
    once per (employee, day) by the pipeline itself. A punch carrying a device
    id came from a device through some other door (HRMS's own checkin API);
    it is synced, not treated as a hand correction."""
    if not _manual(doc):
        return
    day = getdate(doc.time)
    relabel_day_checkins(doc.employee, day)
    if doc.device_id or day >= getdate(today()):
        sync_day(doc.employee, day)
        return
    from avinashgroup_app.hr.punch_correction import FORM_ADD_REASON, log_form_change, stamp_form_change

    clock = get_datetime(doc.time).strftime("%H:%M:%S")
    stamp_form_change(doc.name, None, FORM_ADD_REASON)
    _remark_or_sync(doc.employee, day, f"Punch {clock} added on Employee Checkin {doc.name}.")
    log_form_change(doc.employee, day, "Punch Added", None, clock, doc.name, FORM_ADD_REASON)


def checkin_on_update(doc, method=None):
    """A checkin's time or log_type was edited on the form. A move can affect
    two days (old and new), and both are re-marked."""
    if not _manual(doc) or doc.flags.in_insert:
        return  # an insert is after_insert's
    if not doc.has_value_changed("time") and not doc.has_value_changed("log_type"):
        return

    days = {getdate(doc.time)}
    before = doc.get_doc_before_save()
    if before and before.time:
        days.add(getdate(before.time))

    if not doc.has_value_changed("time"):
        # log_type only: the day's alternation decides it, nothing was moved.
        for day in sorted(days):
            relabel_day_checkins(doc.employee, day)
            sync_day(doc.employee, day)
        return

    from avinashgroup_app.hr.punch_correction import FORM_EDIT_REASON, log_form_change, stamp_form_change

    stamp_form_change(doc.name, before.time if before else None, FORM_EDIT_REASON)
    was = get_datetime(before.time).strftime("%Y-%m-%d %H:%M:%S") if before and before.time else "—"
    note = f"Punch {doc.name} moved on the Employee Checkin form: {was} → {get_datetime(doc.time).strftime('%Y-%m-%d %H:%M:%S')}."
    for day in sorted(days):
        relabel_day_checkins(doc.employee, day)
        _remark_or_sync(doc.employee, day, note)
    log_form_change(
        doc.employee, getdate(doc.time), "Punch Time Edited", was,
        get_datetime(doc.time).strftime("%Y-%m-%d %H:%M:%S"), doc.name, FORM_EDIT_REASON,
    )


def checkin_after_delete(doc, method=None):
    if not _manual(doc):
        return
    from avinashgroup_app.hr.punch_correction import FORM_DELETE_REASON, log_form_change

    day = getdate(doc.time)
    clock = get_datetime(doc.time).strftime("%H:%M:%S")
    relabel_day_checkins(doc.employee, day)
    _remark_or_sync(doc.employee, day, f"Punch {clock} ({doc.name}) deleted on the Employee Checkin form.")
    log_form_change(doc.employee, day, "Punch Deleted", clock, None, doc.name, FORM_DELETE_REASON)
