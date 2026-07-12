import frappe
from datetime import datetime
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
    Before save: if Shift Type has custom_late_arrival_cutoff_time and the
    employee's first check-in is after that time, force status to Half Day
    (Leave Without Pay) regardless of total working hours.

    Cutoff blank on the Shift Type disables this rule for that shift.
    """
    if not doc.shift or not doc.in_time:
        return
    if doc.status in ("On Leave", "Absent", "Half Day"):
        return

    try:
        shift = frappe.get_cached_doc("Shift Type", doc.shift)
        cutoff = shift.get("custom_late_arrival_cutoff_time")
        if not cutoff:
            return

        attendance_date = getdate(doc.attendance_date)
        cutoff_dt = datetime.combine(attendance_date, datetime.min.time()) + cutoff
        in_time = get_datetime(doc.in_time)

        if in_time > cutoff_dt:
            doc.status = "Half Day"
            doc.leave_type = "Leave Without Pay"

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Error enforcing late-arrival Half Day for Attendance {doc.name}"
        )
