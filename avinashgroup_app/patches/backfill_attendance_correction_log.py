"""Seed the Attendance Correction Log with corrections made before it existed.

Punches stamped `custom_time_edited` and Shift Assignments stamped
`custom_shift_corrected` were corrected by hand before the log was added; each
gets one entry, from its stamps, so the log starts complete. An entry already
naming the same punch or assignment is not duplicated, so the patch is safe to
re-run.
"""

import frappe
from frappe.utils import add_days, getdate


def execute():
	if not frappe.db.exists("DocType", "Attendance Correction Log"):
		return
	_punches()
	_shifts()


def _punches():
	if not frappe.get_meta("Employee Checkin").has_field("custom_time_edited"):
		return
	logged = set(frappe.get_all("Attendance Correction Log", filters={"employee_checkin": ("is", "set")}, pluck="employee_checkin"))
	for c in frappe.get_all(
		"Employee Checkin",
		filters={"custom_time_edited": 1},
		fields=["name", "employee", "time", "attendance", "custom_original_time", "custom_edit_reason",
			"custom_edited_by", "custom_edited_on"],
	):
		if c.name in logged:
			continue
		_insert(
			c.employee, getdate(c.time),
			"Punch Time Edited" if c.custom_original_time else "Punch Added",
			c.custom_original_time and str(c.custom_original_time), str(c.time),
			c.custom_edit_reason, c.custom_edited_by, c.custom_edited_on,
			attendance=c.attendance, employee_checkin=c.name,
		)


def _shifts():
	if not frappe.get_meta("Shift Assignment").has_field("custom_shift_corrected"):
		return
	logged = set(frappe.get_all("Attendance Correction Log", filters={"shift_assignment": ("is", "set")}, pluck="shift_assignment"))
	for a in frappe.get_all(
		"Shift Assignment",
		filters={"custom_shift_corrected": 1, "docstatus": 1},
		fields=["name", "employee", "shift_type", "start_date", "end_date", "custom_corrected_from_shift",
			"custom_shift_correction_reason", "custom_shift_corrected_by", "custom_shift_corrected_on"],
	):
		if a.name in logged:
			continue
		day = getdate(a.start_date)
		while day <= getdate(a.end_date or a.start_date):
			_insert(
				a.employee, day, "Shift Changed", a.custom_corrected_from_shift, a.shift_type,
				a.custom_shift_correction_reason, a.custom_shift_corrected_by, a.custom_shift_corrected_on,
				shift_assignment=a.name,
			)
			day = getdate(add_days(day, 1))


def _insert(employee, day, kind, old, new, reason, user, on, **refs):
	person = frappe.db.get_value("Employee", employee, ["employee_name", "company"], as_dict=True) or {}
	frappe.get_doc(
		{
			"doctype": "Attendance Correction Log",
			"employee": employee,
			"employee_name": person.get("employee_name"),
			"company": person.get("company"),
			"attendance_date": day,
			"correction_type": kind,
			"source": "Monthly Attendance BS" if reason and "Employee Checkin form" not in reason else "Employee Checkin Form",
			"old_value": old,
			"new_value": new,
			"reason": reason,
			"done_by": user,
			"done_by_name": frappe.utils.get_fullname(user) if user else None,
			"done_on": on,
			**refs,
		}
	).insert(ignore_permissions=True)
