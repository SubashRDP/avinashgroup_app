"""Credit replacement leave to Officer & Admin staff who worked a holiday.

Policy 2.2 (as corrected 2026-09-16) and 2.5: holiday work earns plant staff
overtime and officer / admin staff a replacement leave day, never both. The
Overtime Sheet already decides which: `hr.overtime.evaluate` writes
`entitlement = "Replacement Leave"` on the row. Until now nothing turned that
row into leave, so the day was promised on paper and never reached a balance.

The grant uses HRMS's own mechanism, a Compensatory Leave Request, submitted on
the employee's behalf. That keeps the standard audit trail (the request links
the Leave Allocation it created or topped up, and cancelling it takes the days
back) and the standard checks: the date must be a holiday on the employee's own
list, and Attendance must show them present.

    Present / Work From Home   1 day
    Half Day                   ½ day
    no attendance / Absent     nothing yet; the row says why, and the next run
                               tries again (attendance is often marked late)

When it runs:
  * Overtime Sheet on_submit, for dates already past;
  * the daily job `grant_pending`, for sheets approved ahead of the day and for
    attendance that arrived late (LOOKBACK_DAYS back);
  * Overtime Sheet on_cancel takes every granted day back.

Deliberately narrow: it grants exactly what the sheet authorised, one row one
day. It never decides who is entitled (hr.overtime does) and never creates a
Leave Period. A company with no active Leave Period gets a logged error instead.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from avinashgroup_app.hr.overtime import ENTITLEMENT_REPLACEMENT_LEAVE

# The Leave Type created by patches/setup_leave_types.py (is_compensatory).
REPLACEMENT_LEAVE_TYPE = "Replacement Leave"

# How far back the daily job keeps retrying a row whose attendance is missing.
# Two BS months: long enough for a late Attendance Fix, short enough that an
# old unworked row stops being retried.
LOOKBACK_DAYS = 62

PRESENT_STATUSES = ("Present", "Work From Home")


def on_sheet_submit(doc, method=None):
	"""Grant what can be granted now. Hook: Overtime Sheet on_submit."""
	if getdate(doc.work_date) >= getdate(today()):
		return  # the day has not happened yet; the daily job picks it up
	for row in doc.employees:
		grant_row(doc, row)


def on_sheet_cancel(doc, method=None):
	"""Take back every day this sheet granted. Hook: Overtime Sheet on_cancel."""
	for row in doc.employees:
		if not row.compensatory_leave_request:
			continue
		request = frappe.get_doc("Compensatory Leave Request", row.compensatory_leave_request)
		if request.docstatus == 1:
			request.flags.ignore_permissions = True
			request.cancel()
		row.db_set("compensatory_leave_request", None, update_modified=False)


def grant_pending():
	"""Daily job: grant rows whose day has passed and whose attendance is now in."""
	sheets = frappe.get_all(
		"Overtime Sheet",
		filters={
			"docstatus": 1,
			"work_date": ("between", [add_days(today(), -LOOKBACK_DAYS), add_days(today(), -1)]),
		},
		pluck="name",
	)
	for name in sheets:
		sheet = frappe.get_doc("Overtime Sheet", name)
		for row in sheet.employees:
			if row.entitlement == ENTITLEMENT_REPLACEMENT_LEAVE and not row.compensatory_leave_request:
				grant_row(sheet, row)
		frappe.db.commit()


def grant_row(sheet, row):
	"""Grant one row's replacement leave if the attendance backs it. Returns the request name or None."""
	if row.entitlement != ENTITLEMENT_REPLACEMENT_LEAVE or row.compensatory_leave_request:
		return None

	attendance = frappe.db.get_value(
		"Attendance",
		{"employee": row.employee, "attendance_date": sheet.work_date, "docstatus": 1},
		["name", "status"],
		as_dict=True,
	)
	if not attendance or attendance.status not in PRESENT_STATUSES + ("Half Day",):
		note = (
			_("Replacement leave waits for attendance: marked {0}").format(attendance.status)
			if attendance
			else _("Replacement leave waits for attendance on this day")
		)
		row.db_set("settlement_note", note, update_modified=False)
		return None

	half_day = attendance.status == "Half Day"
	request = frappe.get_doc(
		{
			"doctype": "Compensatory Leave Request",
			"employee": row.employee,
			"leave_type": REPLACEMENT_LEAVE_TYPE,
			"work_from_date": sheet.work_date,
			"work_end_date": sheet.work_date,
			"half_day": 1 if half_day else 0,
			"half_day_date": sheet.work_date if half_day else None,
			"reason": _("Worked {0} on {1}, authorised by {2}").format(
				row.day_type or _("a holiday"), sheet.work_date, sheet.name
			),
		}
	)
	request.flags.ignore_permissions = True
	savepoint = f"replacement_leave_{row.name}"[:60]
	frappe.db.savepoint(savepoint)
	try:
		request.insert()
		request.submit()
	except frappe.ValidationError as e:
		# HRMS refuses with a sentence HR can act on (no Leave Period, not a
		# holiday on their list, …). Keep it on the row and in the Error Log.
		frappe.db.rollback(save_point=savepoint)
		frappe.clear_last_message()
		row.db_set("settlement_note", _("Replacement leave not granted: {0}").format(e), update_modified=False)
		frappe.log_error(
			title=f"Replacement leave not granted: {sheet.name} {row.employee}",
			message=frappe.get_traceback(),
		)
		return None

	row.db_set("compensatory_leave_request", request.name, update_modified=False)
	row.db_set(
		"settlement_note",
		_("{0} day of replacement leave granted").format("½" if half_day else "1"),
		update_modified=False,
	)
	return request.name
