import frappe
from datetime import datetime, timedelta
from frappe.utils import flt, getdate, get_datetime

from avinashgroup_app.biometric.attendance_sync import compute_shift_deviations


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
    for every shift.

    `custom_late_arrival_cutoff_time`, the older absolute cutoff, still applies
    where it is set; the earlier of the two wins. Blank the hours (0) and clear
    the cutoff to switch the rule off for a shift.

    HR can waive one day with `custom_late_excused` — the traffic, the funeral,
    the thing the rule cannot know. The lateness stays recorded and visible in
    the reports; it just stops costing anything. Because HR ticks the box on a
    day the rule has already demoted, excusing also puts that day back to
    Present, but only when lateness is the sole reason it fell.
    """
    if not doc.shift or not doc.in_time:
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

        cutoffs = []
        late_by_hours = shift.get("custom_half_day_if_late_by_hours")
        if late_by_hours and shift.start_time is not None:
            cutoffs.append(midnight + shift.start_time + timedelta(hours=float(late_by_hours)))
        absolute = shift.get("custom_late_arrival_cutoff_time")
        # A cutoff at or before the shift starts cannot mean "late": it would
        # make a half day of everybody who turned up on time. Saving a Shift
        # Type leaves this field holding the clock time of the save unless it
        # is cleared, and that quietly cost 2,423 of 2,808 days a half day on
        # the first run of test attendance.
        if absolute and shift.start_time is not None and absolute > shift.start_time:
            cutoffs.append(midnight + absolute)
        if not cutoffs:
            return

        if get_datetime(doc.in_time) > min(cutoffs):
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


def half_day_when_working_on_leave(doc, method=None):
    """
    Before save: an employee who comes in while on approved leave has worked half
    a day, not a whole day of leave.

    Policy 3.4 (client meeting 2026-09-15): "Reporting to office while on leave
    counts as a half day."

    HRMS's own `check_leave_record` has already forced the status to On Leave and
    filled in the leave application by the time this runs. The punch is the thing
    it does not know about: if there is one, the day becomes a Half Day, with the
    leave type kept so payroll still deducts the leave half.
    """
    if doc.status != "On Leave" or not doc.in_time:
        return
    if not doc.get("leave_application"):
        return

    doc.status = "Half Day"
    # The half they worked is present; the other half stays against their leave.
    if doc.meta.has_field("half_day_status"):
        doc.half_day_status = "Present"
