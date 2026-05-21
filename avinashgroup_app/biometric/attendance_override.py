import frappe
from datetime import datetime, timedelta
from frappe.utils import getdate, get_datetime, today


def _round_to_minute(seconds):
    """
    Round seconds to the nearest whole minute.
    >= 30 seconds → round up   (e.g. 30m 40s → 31m = 1860s)
    <  30 seconds → round down (e.g. 30m 20s → 30m = 1800s)
    """
    return int((int(seconds) + 30) / 60) * 60


def set_shift_deviation_fields(doc, method):
    """
    On Attendance before_save: calculate and store the deviation between
    actual in/out times and the shift start/end times.

    - custom_late_entry  : how late the employee punched IN after shift start
    - custom_early_entry : how early the employee punched IN before shift start
    - custom_early_exit  : how early the employee punched OUT before shift end
    - custom_late_exit   : how late the employee punched OUT after shift end

    Only one of each pair will be non-zero at a time.
    Values are rounded to the nearest minute (>=30s rounds up, <30s rounds down).
    Duration fields store seconds as integers.
    """
    doc.custom_late_entry = 0
    doc.custom_early_entry = 0
    doc.custom_early_exit = 0
    doc.custom_late_exit = 0

    if not doc.shift:
        return

    try:
        shift = frappe.get_cached_doc("Shift Type", doc.shift)
        attendance_date = getdate(doc.attendance_date)

        shift_start_dt = datetime.combine(attendance_date, datetime.min.time()) + shift.start_time
        shift_end_dt = datetime.combine(attendance_date, datetime.min.time()) + shift.end_time

        # Overnight shift: end_time < start_time means end falls on next day
        if shift.end_time < shift.start_time:
            shift_end_dt += timedelta(days=1)

        if doc.in_time:
            in_time = get_datetime(doc.in_time)
            diff = (in_time - shift_start_dt).total_seconds()
            if diff > 0:
                doc.custom_late_entry = _round_to_minute(diff)
            elif diff < 0:
                doc.custom_early_entry = _round_to_minute(abs(diff))

        if doc.out_time:
            out_time = get_datetime(doc.out_time)
            diff = (out_time - shift_end_dt).total_seconds()
            if diff > 0:
                doc.custom_late_exit = _round_to_minute(diff)
            elif diff < 0:
                doc.custom_early_exit = _round_to_minute(abs(diff))

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Error calculating shift deviation for Attendance {doc.name}"
        )


def reconcile_with_existing_attendance(doc, method=None):
    """Employee Checkin after_insert: link orphan punches to an existing
    Present/Half Day Attendance row for the same (employee, date).

    Scope is intentionally narrow — this hook never deletes, never cancels,
    never changes status. Absent → Present transitions, stale-row cleanup,
    and any other reconciliation go through the Attendance Fix doctype so
    HR has a submitted, auditable record of every change.

    Behavior:
    - Existing row is Present/Half Day and this checkin has no `attendance`
      link → set it. Pure data-correctness fix, no business decision.
    - Existing row is Absent → no-op. HR uses Attendance Fix to convert.
    - No existing row → no-op. HR uses Attendance Fix to materialize.

    Runs only for past-date punches; today's punches go through the normal
    real-time auto-attendance flow.
    """
    if not doc.employee or not doc.time or doc.attendance:
        return
    punch_date = getdate(doc.time)
    if punch_date >= getdate(today()):
        return

    existing = frappe.db.get_value(
        "Attendance",
        {
            "employee": doc.employee,
            "attendance_date": punch_date,
            "docstatus": ("<", 2),
            "status": ("in", ("Present", "Half Day")),
        },
        "name",
    )
    if not existing:
        return

    frappe.db.set_value(
        "Employee Checkin",
        doc.name,
        "attendance",
        existing,
        update_modified=False,
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
