import frappe
from datetime import datetime, timedelta
from frappe.utils import getdate, get_datetime
from frappe.utils import get_time, get_datetime, get_traceback
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

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
    # Reset all deviation fields first
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


def cap_working_hours_to_shift_end(doc, method):
    """
    On Attendance before_submit: apply two rules based on OUT time vs shift end time:

    1. OUT after shift end        → keep actual out_time, cap working_hours to (shift_end - in_time)
    2. early_exit flagged by ERPNext → keep working_hours as-is (actual out - in),
                                       set status = Half Day, leave_type = Leave Without Pay

    IN time always stays as the actual checkin time.
    Skips if already On Leave / no shift / no in_time / no out_time.
    """
    if not doc.out_time or not doc.shift or not doc.in_time:
        return

    # Don't interfere with leave-based attendance
    if doc.status in ("On Leave", "Absent"):
        return

    try:
        shift = frappe.get_cached_doc("Shift Type", doc.shift)

        # shift.end_time / start_time are timedelta (seconds from midnight)
        attendance_date = getdate(doc.attendance_date)
        shift_end_dt = datetime.combine(attendance_date, datetime.min.time()) + shift.end_time

        # Overnight shift: end_time < start_time means end falls on the next day
        if shift.end_time < shift.start_time:
            shift_end_dt += timedelta(days=1)

        out_time = get_datetime(doc.out_time)

        if out_time > shift_end_dt:
            # --- Rule 1: Late exit — cap working_hours to shift end, keep actual out_time ---
            in_time = get_datetime(doc.in_time)
            doc.working_hours = round(
                float((shift_end_dt - in_time).total_seconds()) / 3600, 2
            )

        elif doc.early_exit:
            # --- Rule 2: Early exit (as flagged by ERPNext) — Half Day + LWP ---
            doc.status = "Half Day"
            doc.leave_type = "Leave Without Pay"
            # working_hours stays as calculated by ERPNext (actual out - in)

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Error in attendance override for Attendance {doc.name}"
        )


def create_compensatory_leave_on_holiday(doc, method):
    """
    On Attendance submit: if the employee punched IN and OUT on a holiday,
    auto-create and submit a Compensatory Leave Request so a leave day is allocated.
    """
    # Only process if employee actually worked (both checkins present)
    if not doc.in_time or not doc.out_time:
        return

    try:
        # Get holiday list for the employee (Employee → Company → Global Defaults)
       
        holiday_list = get_holiday_list_for_employee(doc.employee, raise_exception=False)
        if not holiday_list:
            return

        # Check if attendance_date is a holiday
        is_holiday = frappe.db.exists(
            "Holiday",
            {"parent": holiday_list, "holiday_date": doc.attendance_date}
        )
        if not is_holiday:
            return

        # Skip if a Compensatory Leave Request already exists for this employee + date
        already_exists = frappe.db.exists(
            "Compensatory Leave Request",
            {
                "employee": doc.employee,
                "work_from_date": doc.attendance_date,
                "work_end_date": doc.attendance_date,
                "docstatus": ["!=", 2],
            },
        )
        if already_exists:
            return

        # Find the compensatory leave type
        leave_type = frappe.db.get_value("Leave Type", {"is_compensatory": 1}, "name")
        if not leave_type:
            frappe.log_error(
                f"No Leave Type with 'Is Compensatory' found. "
                f"Cannot create compensatory leave for {doc.employee} on {doc.attendance_date}.",
                "Compensatory Leave Setup Missing"
            )
            return

        # Create and submit Compensatory Leave Request
        comp_leave = frappe.new_doc("Compensatory Leave Request")
        comp_leave.employee = doc.employee
        comp_leave.work_from_date = doc.attendance_date
        comp_leave.work_end_date = doc.attendance_date
        comp_leave.reason = f"Worked on holiday — auto-created from biometric punch"
        comp_leave.leave_type = leave_type
        comp_leave.insert(ignore_permissions=True)
        comp_leave.submit()

        frappe.logger("biometric").info(
            f"Compensatory Leave Request {comp_leave.name} created for "
            f"{doc.employee} on holiday {doc.attendance_date}"
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Error creating compensatory leave for Attendance {doc.name}"
        )



# Put end time if approved in out time

APPROVED_WORKFLOW_KEYWORDS = ("approve",)
REJECTED_WORKFLOW_KEYWORDS = ("reject",)


def _workflow_state(doc):
	return (doc.get("workflow_state") or "").strip().lower()


def _is_approved(doc):
	state = _workflow_state(doc)
	return any(keyword in state for keyword in APPROVED_WORKFLOW_KEYWORDS)


def _is_rejected(doc):
	state = _workflow_state(doc)
	return any(keyword in state for keyword in REJECTED_WORKFLOW_KEYWORDS)


def adjust_out_time(doc, method=None):
	"""
	Adjusts Attendance out_time to shift end time if earlier.
	Triggered before_save / before_submit.
	Only adjusts when workflow state is Approved.
	"""
	# Never change out_time for rejected records.
	if _is_rejected(doc):
		return

	# On submit path (Approve), enforce adjustment regardless of workflow_state label timing.
	if method != "before_submit" and not _is_approved(doc):
		return
	
	# Ensure we have required fields
	if not doc.attendance_date or not doc.out_time or not doc.shift:
		return
	
	try:
		# Get the shift dynamically from attendance doc.shift (the shift field in Attendance)
		shift = frappe.get_cached_doc("Shift Type", doc.shift)
		if not shift or not shift.end_time:
			return
		
		# Get shift end time
		shift_end = get_time(shift.end_time)
		
		# Convert out_time to datetime
		out_dt = get_datetime(doc.out_time)
		
		# Create shift_end_dt with same date as attendance_date
		shift_end_dt = get_datetime(doc.attendance_date).replace(
			hour=int(shift_end.hour or 0),
			minute=int(shift_end.minute or 0),
			second=0,
			microsecond=0
		)
		
		# If out_time is EARLIER than shift_end, adjust it
		if out_dt < shift_end_dt:
			doc.out_time = shift_end_dt
	
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Attendance Out Time Adjustment Failed")





# Automatically submit attendance if present full time 

def auto_submit_attendance(doc, method=None):
	"""
	Auto-submit Attendance if out_time >= shift end_time.
	Triggered on_update.
	"""
	# Ensure we have required fields
	if not doc.name or not doc.attendance_date or not doc.out_time or not doc.shift:
		return
	
	# Skip if already submitted
	if doc.docstatus != 0:
		return
	
	try:
		shift = frappe.get_cached_doc("Shift Type", doc.shift)
		if not shift or not shift.end_time:
			return
		
		shift_end = get_time(shift.end_time)
		shift_end_dt = get_datetime(doc.attendance_date).replace(
			hour=int(shift_end.hour or 0),
			minute=int(shift_end.minute or 0),
			second=0,
			microsecond=0
		)
		
		out_dt = get_datetime(doc.out_time)
		
		# Check if out_time >= shift end time
		if out_dt >= shift_end_dt:
			doc.workflow_state = "Approved"
			doc.status = "Present"
			doc.flags.ignore_permissions = True
			doc.submit()
	
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Attendance Auto Submit Failed")