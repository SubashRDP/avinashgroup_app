import frappe
from datetime import datetime, timedelta
from frappe.utils import flt, getdate, get_datetime

from avinashgroup_app.biometric.attendance_sync import compute_shift_deviations
from avinashgroup_app.payroll.special_payout import REGULAR_SLIPS


def set_shift_deviation_fields(doc, method):
    """
    On Attendance validate: calculate and store the deviation between
    actual in/out times and the shift start/end times.

    - custom_late_entry  : how late the employee punched IN after shift start
    - custom_early_entry : how early the employee punched IN before shift start
    - custom_early_exit  : how early the employee punched OUT before shift end
    - custom_late_exit   : how late the employee punched OUT after shift end

    Only one of each pair will be non-zero at a time.
    Values are rounded to the nearest minute (>=30s rounds up, <30s rounds down).
    Duration fields store seconds as integers.

    The calculation itself lives in attendance_sync.compute_shift_deviations,
    shared with the refresh path that updates already-saved Attendance rows
    when late punches arrive.
    """
    doc.custom_late_entry = 0
    doc.custom_early_entry = 0
    doc.custom_early_exit = 0
    doc.custom_late_exit = 0

    if not doc.shift and doc.employee and doc.attendance_date:
        # Attendance marked by hand, or by anything but HRMS's auto-attendance,
        # arrives with no shift — and with no shift every deviation stays 0, so
        # late time, meals and the half-day rule all silently read nothing.
        # Take the shift rostered for that date, as HRMS would have.
        from avinashgroup_app.hr.overtime import get_shift_window

        doc.shift = get_shift_window(doc.employee, doc.attendance_date)[0]

    if not doc.shift:
        return

    try:
        shift = frappe.get_cached_doc("Shift Type", doc.shift)
        doc.update(
            compute_shift_deviations(shift, doc.attendance_date, doc.in_time, doc.out_time)
        )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Error calculating shift deviation for Attendance {doc.name}"
        )


def enforce_late_arrival_half_day(doc, method=None):
    """
    Before save: someone who turns up very late has worked half a day, whatever
    their hours add up to.

    Policy 1.2 (client meeting 2026-09-15): more than 2 hours late is a half day,
    and there is no grace period. The limit is `custom_half_day_if_late_by_hours`
    on the Shift Type — hours after that shift's own start, so it keeps meaning
    the same thing if the shift times change, and it does not have to be re-typed
    for every shift. Exactly that late is not a half day; any later is. 0 or
    blank switches the rule off for the shift.

    This is the only lateness cutoff. The older absolute clock-time cutoff
    (`custom_late_arrival_cutoff_time`) was removed on 2026-10-13: the form kept
    filling it with the time of the save, and a stray value half-dayed whole
    companies (patches/drop_late_arrival_cutoff.py).

    HR can waive one day with `custom_late_excused` — the traffic, the funeral,
    the thing the rule cannot know. The lateness stays recorded and visible in
    the reports; it just stops costing anything. Because HR ticks the box on a
    day the rule has already demoted, excusing also puts that day back to
    Present, but only when lateness is the sole reason it fell.
    """
    if not doc.shift or not doc.in_time:
        return
    if doc.get("custom_worked_on_holiday"):
        # Holiday work is not late: there is no shift start to arrive after
        # (user, 2026-10-15). set_holiday_flag runs earlier in validate.
        return
    if doc.get("custom_late_excused"):
        _undo_excused_late_half_day(doc)
        return
    if doc.status in ("On Leave", "Absent", "Half Day"):
        return

    try:
        shift = frappe.get_cached_doc("Shift Type", doc.shift)
        attendance_date = getdate(doc.attendance_date)
        midnight = datetime.combine(attendance_date, datetime.min.time())

        late_by_hours = flt(shift.get("custom_half_day_if_late_by_hours"))
        if late_by_hours <= 0 or shift.start_time is None:
            return
        cutoff = midnight + shift.start_time + timedelta(hours=late_by_hours)

        if get_datetime(doc.in_time) > cutoff:
            # Paid, but half: HRMS's own half-absent. Half Day Status "Absent"
            # with no leave type is counted as half a day absent by the salary
            # slip (get_half_absent_days), so nothing reads as leave.
            doc.status = "Half Day"
            doc.half_day_status = "Absent"
            doc.leave_type = None

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Error enforcing late-arrival Half Day for Attendance {doc.name}"
        )


def _undo_excused_late_half_day(doc):
    """Put an excused day back to Present, if lateness is why it is a Half Day.

    Only this rule's own signature is undone: Half Day, half-day status Absent,
    no leave type. A half day that carries a leave type was granted, not
    deducted, and is none of this rule's business.

    Short hours are checked as well, because they demote the same day
    independently: somebody two hours late who then left early has earned their
    half day on the hours alone, and excusing the lateness must not hand back
    what the hours took. Only when the hours clear the shift's own threshold is
    the day restored.
    """
    if doc.status != "Half Day" or doc.get("half_day_status") != "Absent" or doc.leave_type:
        return

    threshold = frappe.get_cached_value(
        "Shift Type", doc.shift, "working_hours_threshold_for_half_day"
    )
    if threshold and flt(doc.working_hours) < flt(threshold):
        return

    doc.status = "Present"
    doc.half_day_status = None


def check_late_excuse_change(doc, method=None):
    """Before Update after Submit: excusing a day is allowed only while it can still count.

    Late Excused and its reason can be changed on a submitted Attendance
    (patches/late_excuse_editable_after_submit.py), so HR no longer cancels and
    amends a day to excuse it. The fine is posted when the month's slips are made
    and again when they are submitted, so a change reaches pay on its own until
    the slip is submitted. After that it would change nothing, which HR would not
    see, so it is refused.
    """
    before = doc.get_doc_before_save()
    if not before or (
        before.get("custom_late_excused") == doc.get("custom_late_excused")
        and before.get("custom_late_excuse_reason") == doc.get("custom_late_excuse_reason")
    ):
        return
    if doc.get("custom_late_excused") and not (doc.get("custom_late_excuse_reason") or "").strip():
        frappe.throw(frappe._("Give the reason for excusing the late arrival."), title=frappe._("Reason Needed"))
    slip = frappe.db.get_value(
        "Salary Slip",
        {
            "employee": doc.employee,
            "docstatus": 1,
            "start_date": ("<=", doc.attendance_date),
            "end_date": (">=", doc.attendance_date),
            **REGULAR_SLIPS,
        },
        "name",
    )
    if slip:
        frappe.throw(
            frappe._(
                "Salary Slip {0} for this day is already submitted, so excusing the lateness would not change "
                "the pay. Cancel the slip first, or settle it as a Payroll Adjustment."
            ).format(slip),
            title=frappe._("Already Paid"),
        )


def apply_late_excuse_change(doc, method=None):
    """On Update after Submit: put the day's status where the late rule now says.

    Status cannot be changed through Update after Submit, so the same rules as a
    fresh save are run on the document and the result is written directly.
    Excused: a day the late rule made a Half Day goes back to Present. No longer
    excused: the rule applies again and may make it a Half Day.
    """
    before = doc.get_doc_before_save()
    if not before or before.get("custom_late_excused") == doc.get("custom_late_excused"):
        return
    enforce_late_arrival_half_day(doc)
    changed = {
        f: doc.get(f) for f in ("status", "half_day_status", "leave_type") if doc.get(f) != before.get(f)
    }
    if changed:
        doc.db_set(changed, update_modified=False)


def half_day_when_working_on_leave(doc, method=None):
    """
    Before save: an employee who comes in while on approved leave has worked half
    a day, not a whole day of leave.

    Policy 3.4 (client meeting 2026-09-15): "Reporting to office while on leave
    counts as a half day."

    HRMS's own `check_leave_record` has already forced the status to On Leave and
    filled in the leave application by the time this runs. The punch is the thing
    it does not know about: if there is one, the day becomes a Half Day, with the
    leave type kept so payroll still deducts the leave half. The attendance HRMS
    makes for an approved leave carries no in-time, so the day's punches count
    as well as an in-time typed on the form. A day inside a submitted salary
    slip stays On Leave: it was paid as leave.
    """
    if doc.status != "On Leave" or not doc.get("leave_application"):
        return
    if not (doc.in_time or _punched(doc.employee, doc.attendance_date)):
        return
    if _paid(doc.employee, doc.attendance_date):
        return

    doc.status = "Half Day"
    # The half they worked is present; the other half stays against their leave.
    if doc.meta.has_field("half_day_status"):
        doc.half_day_status = "Present"


def half_day_if_came_in(employee, day):
    """Policy 3.4 for a leave day already saved: On Leave from a leave
    application, and the person punched that day → Half Day, other half Present,
    leave kept. Returns the attendance changed, or None.

    The validate hook above cannot see these: HRMS updates an existing row for a
    leave with db_set (no hooks), and punches that arrive after the leave link to
    the row without saving it. Called when a leave is submitted
    (`on_leave_submit`), when a day's punches are synced
    (attendance_sync.sync_day) and by the per-day repair (Attendance Fix,
    self-heal). A day inside a submitted salary slip is left alone: it was paid
    as leave."""
    day = getdate(day)
    name = frappe.db.get_value(
        "Attendance",
        {
            "employee": employee,
            "attendance_date": day,
            "docstatus": 1,
            "status": "On Leave",
            "leave_application": ("is", "set"),
        },
        "name",
    )
    if not name or not _punched(employee, day):
        return None
    if _paid(employee, day):
        return None
    frappe.db.set_value("Attendance", name, {"status": "Half Day", "half_day_status": "Present"})
    frappe.get_doc("Attendance", name).add_comment(
        "Info", "Came in while on leave: Half Day, leave kept (policy 3.4)."
    )
    return name


def on_leave_submit(doc, method=None):
    """Leave Application on_submit, after HRMS has marked the days: any day of
    the leave the person punched on becomes a Half Day (policy 3.4)."""
    if doc.status != "Approved":
        return
    day = getdate(doc.from_date)
    while day <= getdate(doc.to_date):
        half_day_if_came_in(doc.employee, day)
        day += timedelta(days=1)


def on_leave_cancel(doc, method=None):
    """Leave Application on_cancel, after HRMS's cancel_attendance: a past day of
    the leave the person punched on is marked again from the punches.

    HRMS cancels every On Leave and Half Day attendance in the leave's dates and
    marks nothing in their place, so a day someone came in (a Half Day under
    policy 3.4, or a late half day caught in the range) was left with no
    attendance at all. Days with no punch stay unmarked — absence is HRMS's call
    — and today or later is left to the day's own marking. Re-marked through
    hr/punch_correction, whose guards skip paid and other refused days.
    """
    from frappe.utils import add_days, today

    from avinashgroup_app.biometric.attendance_sync import get_day_checkins
    from avinashgroup_app.hr.punch_correction import Refused, day_context, remark_day

    day, last = getdate(doc.from_date), min(getdate(doc.to_date), getdate(add_days(today(), -1)))
    note = frappe._("Marked again from the punches after leave {0} was cancelled.").format(doc.name)
    while day <= last:
        if get_day_checkins(doc.employee, day):
            savepoint = f"leave_cancel_{day:%Y%m%d}"
            frappe.db.savepoint(savepoint)
            try:
                existing, shift_doc = day_context(doc.employee, day)
                if not existing:
                    remark_day(doc.employee, day, None, shift_doc, note)
            except Refused:
                frappe.db.rollback(save_point=savepoint)
            except Exception:
                frappe.db.rollback(save_point=savepoint)
                frappe.log_error(
                    title=f"Re-marking after leave cancel failed: {doc.employee} {day}",
                    message=frappe.get_traceback(),
                )
        day += timedelta(days=1)


def _punched(employee, day):
    day = getdate(day)
    start = datetime.combine(day, datetime.min.time())
    return bool(
        frappe.db.exists(
            "Employee Checkin",
            {"employee": employee, "time": ("between", [start, start + timedelta(days=1, microseconds=-1)])},
        )
    )


def _paid(employee, day):
    """Whether a submitted salary slip covers `day`."""
    day = getdate(day)
    return bool(
        frappe.db.exists(
            "Salary Slip",
            # A Dashain / encashment payout slip does not pay the days.
            {"employee": employee, "docstatus": 1, "start_date": ("<=", day), "end_date": (">=", day), **REGULAR_SLIPS},
        )
    )
