import frappe
from datetime import datetime, timedelta
from frappe.utils import getdate, get_datetime

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
    """
    if not doc.shift or not doc.in_time:
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
        if absolute:
            cutoffs.append(midnight + absolute)
        if not cutoffs:
            return

        if get_datetime(doc.in_time) > min(cutoffs):
            doc.status = "Half Day"
            doc.leave_type = "Leave Without Pay"

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Error enforcing late-arrival Half Day for Attendance {doc.name}"
        )


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
