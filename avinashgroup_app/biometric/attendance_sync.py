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

Status is NEVER changed here. Absent→Present transitions, row creation and
deletion stay in Attendance Fix and the hourly self-heal, so HR keeps an
auditable trail of every status decision.
"""

from collections import Counter
from datetime import datetime, time, timedelta

import frappe
from frappe.utils import cint, flt, get_datetime, getdate, today

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
    """Alternation policy: IN, OUT, IN, ... with the day's LAST punch forced
    to OUT whenever there are at least two punches.

    With this site's calculation mode ("Strictly based on Log Type" + "First
    Check-in and Last Check-out"), plain alternation makes an odd punch count
    (someone forgot a midday punch) label the last punch IN, so the attendance
    loses its real out-time. Forcing the last punch to OUT keeps
    in_time = first punch and out_time = last punch for any count — the same
    result stock HRMS computes in "Alternating entries" mode."""
    if total >= 2 and idx == total - 1:
        return "OUT"
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

    updates = {}
    if flt(current.working_hours, 5) != flt(working_hours, 5):
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
    Days with no Attendance yet, or marked Absent / On Leave / WFH, are left
    alone: creating rows and changing status are Attendance Fix / self-heal
    territory. Returns True when the day had a row to sync."""
    punch_date = getdate(punch_date)
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

def checkin_after_insert(doc, method=None):
    """A checkin created outside the device pipeline (desk form, API, mobile):
    re-apply the day's alternation and sync the day's attendance. Pipeline
    inserts set frappe.flags.in_biometric_day_reconcile and are handled once
    per (employee, day) by the pipeline itself."""
    if frappe.flags.in_biometric_day_reconcile:
        return
    if not doc.employee or not doc.time:
        return
    day = getdate(doc.time)
    relabel_day_checkins(doc.employee, day)
    sync_day(doc.employee, day)


def checkin_on_update(doc, method=None):
    """A checkin's time or log_type was edited on the form. Stock HRMS blocks
    time edits on checkins already linked to an attendance, so only unlinked
    rows can move — but a move can still affect two days (old and new)."""
    if frappe.flags.in_biometric_day_reconcile:
        return
    if not doc.employee or not doc.time:
        return
    if not doc.has_value_changed("time") and not doc.has_value_changed("log_type"):
        return

    days = {getdate(doc.time)}
    before = doc.get_doc_before_save()
    if before and before.time:
        days.add(getdate(before.time))
    for day in sorted(days):
        relabel_day_checkins(doc.employee, day)
        sync_day(doc.employee, day)


def checkin_after_delete(doc, method=None):
    if frappe.flags.in_biometric_day_reconcile:
        return
    if not doc.employee or not doc.time:
        return
    day = getdate(doc.time)
    relabel_day_checkins(doc.employee, day)
    sync_day(doc.employee, day)
