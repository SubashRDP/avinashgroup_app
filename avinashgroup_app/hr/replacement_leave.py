"""Credit replacement leave to Officer & Admin staff who worked a holiday.

Policy 2.2 (as corrected 2026-09-16) and 2.5: holiday work earns plant staff
overtime and officer / admin staff a replacement leave day, never both. The
Overtime Sheet already decides which: `hr.overtime.evaluate` writes
`entitlement = "Replacement Leave"` on the row. Until now nothing turned that
row into leave, so the day was promised on paper and never reached a balance.

The grant uses HRMS's own mechanism, a Compensatory Leave Request, submitted on
the employee's behalf. That keeps the standard audit trail (the request links
the Leave Allocation it created or topped up, and cancelling it takes the days
back) and HRMS's check that the date is a holiday on the employee's own list.

Turning up is the whole test (user, 2026-10-15): one punch on the day, or an
Attendance with an in-time, earns 1 FULL day — no hour thresholds, no ½ for a
Half Day, nothing for arriving late. HRMS's own attendance check wants a
Present day and gives a Half Day only ½, so the request this module files skips
it (ReplacementLeaveRequest); a request anybody files by hand keeps it.

    shown up (a punch, or attendance with an in-time)   1 day
    not shown up                                         nothing yet; the row says
                                                         why, and the next run
                                                         tries again

A day corrected afterwards (hr/punch_correction: a punch moved, added or
deleted, a shift changed) is checked again by `recheck_day`: granted if the
person now shows up, a ½ day from before this rule topped up to 1, taken back
if they no longer show up. A day already taken as leave is never taken back
(`used`: HRMS would let the balance go below zero): the row keeps the grant,
says so, and the caller warns.

When it runs:
  * Overtime Sheet on_submit, for dates already past;
  * the daily job `grant_pending`, for sheets approved ahead of the day and for
    attendance that arrived late (LOOKBACK_DAYS back);
  * Overtime Sheet on_cancel takes every granted day back, except one already
    taken as leave.

Deliberately narrow: it grants exactly what the sheet authorised, one row one
day. It never decides who is entitled (hr.overtime does) and never creates a
Leave Period. A company with no active Leave Period gets a logged error instead.
"""

from datetime import datetime, time

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, strip_html, today

from hrms.hr.doctype.compensatory_leave_request.compensatory_leave_request import (
	CompensatoryLeaveRequest,
)

from avinashgroup_app.hr.overtime import ENTITLEMENT_REPLACEMENT_LEAVE

# The Leave Type created by patches/setup_leave_types.py (is_compensatory).
REPLACEMENT_LEAVE_TYPE = "Replacement Leave"

# How far back the daily job keeps retrying a row whose attendance is missing.
# Two BS months: long enough for a late Attendance Fix, short enough that an
# old unworked row stops being retried.
LOOKBACK_DAYS = 62

GRANTED_NOTE = "1 day of replacement leave granted"
CANCELLED_NOTE = "Replacement leave taken back: sheet cancelled"


class ReplacementLeaveRequest(CompensatoryLeaveRequest):
	"""Compensatory Leave Request, minus HRMS's attendance check for our grants.

	HRMS refuses a full day unless Attendance says Present, and a Half Day gets
	½. The holiday-work policy grants a full day for turning up at all, which
	grant_row has already established from the punches, and says so with
	`flags.shown_up_on_holiday`. Every other request — one HR files by hand —
	goes through HRMS's check unchanged. Registered in hooks.override_doctype_class.
	"""

	def validate_attendance(self):
		if self.flags.shown_up_on_holiday:
			return
		super().validate_attendance()


def shown_up(employee, day):
	"""Whether the employee turned up on `day`: one punch is enough, or an
	attendance with an in-time (a day keyed in by hand has no punches)."""
	day = getdate(day)
	if frappe.db.exists(
		"Employee Checkin",
		{"employee": employee, "time": ("between", [datetime.combine(day, time.min), datetime.combine(day, time.max)])},
	):
		return True
	return bool(
		frappe.db.exists(
			"Attendance",
			{"employee": employee, "attendance_date": day, "docstatus": 1, "in_time": ("is", "set")},
		)
	)


def on_sheet_submit(doc, method=None):
	"""Grant what can be granted now. Hook: Overtime Sheet on_submit."""
	if getdate(doc.work_date) >= getdate(today()):
		return  # the day has not happened yet; the daily job picks it up
	for row in doc.employees:
		grant_row(doc, row)


def on_sheet_cancel(doc, method=None):
	"""Take back every day this sheet granted. Hook: Overtime Sheet on_cancel.

	A day already taken as leave is kept: taking it back would leave the person
	owing leave they were given (a balance below zero, which HRMS lets through
	here). The row says so and HR is warned.
	"""
	kept = []
	for row in doc.employees:
		if not row.compensatory_leave_request:
			continue
		request = frappe.get_doc("Compensatory Leave Request", row.compensatory_leave_request)
		if request.docstatus == 1 and used(request):
			row.db_set("settlement_note", _used_note(request.name), update_modified=False)
			kept.append(f"{row.employee_name or row.employee} ({request.name})")
			continue
		if request.docstatus == 1:
			request.flags.ignore_permissions = True
			request.cancel()
		row.db_set("compensatory_leave_request", None, update_modified=False)
		row.db_set("settlement_note", _(CANCELLED_NOTE), update_modified=False)
	if kept:
		frappe.msgprint(
			_("Replacement leave kept because it has already been taken: {0}. Cancel or change that leave first if the day should not count.").format(
				", ".join(kept)
			),
			title=_("Leave already used"),
			indicator="orange",
		)


def used(request):
	"""Whether taking this grant back would put the Replacement Leave balance
	below zero — the day (or part of it) has been taken, or is approved to be."""
	from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

	days = 0.5 if request.half_day else date_diff(request.work_end_date, request.work_from_date) + 1
	balance = get_leave_balance_on(
		request.employee, request.leave_type, getdate(today()), consider_all_leaves_in_the_allocation_period=True
	)
	return flt(balance) < flt(days)


def _used_note(request):
	return _("Kept {0}: already used, so it was not taken back").format(request)


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
			if row.entitlement != ENTITLEMENT_REPLACEMENT_LEAVE:
				continue
			if not row.compensatory_leave_request:
				grant_row(sheet, row)
			elif _is_half_day_grant(row.compensatory_leave_request):
				_resync_row(sheet, row)  # a ½ day from before the full-day rule
		frappe.db.commit()


def grant_row(sheet, row):
	"""Grant one row's replacement leave if the person turned up. Returns the request name or None."""
	if row.entitlement != ENTITLEMENT_REPLACEMENT_LEAVE or row.compensatory_leave_request:
		return None

	if not shown_up(row.employee, sheet.work_date):
		row.db_set("settlement_note", _("Replacement leave waits: no punch on this day yet"), update_modified=False)
		return None

	request = frappe.get_doc(
		{
			"doctype": "Compensatory Leave Request",
			"employee": row.employee,
			"leave_type": REPLACEMENT_LEAVE_TYPE,
			"work_from_date": sheet.work_date,
			"work_end_date": sheet.work_date,
			"half_day": 0,
			"reason": _("Worked {0} on {1}, authorised by {2}").format(
				row.day_type or _("a holiday"), sheet.work_date, sheet.name
			),
		}
	)
	request.flags.ignore_permissions = True
	request.flags.shown_up_on_holiday = True
	savepoint = f"replacement_leave_{row.name}"[:60]
	frappe.db.savepoint(savepoint)
	# The Leave Allocation HRMS creates is numbered by fiscal year, which the
	# naming engine reads from custom_created_on — stamped only for a desk
	# request or an explicit audit user. Without one, every grant from the daily
	# job failed with "Date field … is required for Leave Allocation".
	audit_user = frappe.flags.audit_user
	frappe.flags.audit_user = audit_user or frappe.session.user
	try:
		request.insert()
		request.submit()
	except frappe.ValidationError as e:
		# HRMS refuses with a sentence HR can act on (no Leave Period, not a
		# holiday on their list, …). Keep it on the row and in the Error Log.
		frappe.db.rollback(save_point=savepoint)
		frappe.clear_last_message()
		row.db_set("settlement_note", _("Replacement leave not granted: {0}").format(strip_html(str(e))), update_modified=False)
		frappe.log_error(
			title=f"Replacement leave not granted: {sheet.name} {row.employee}",
			message=frappe.get_traceback(),
		)
		return None
	finally:
		frappe.flags.audit_user = audit_user

	row.db_set("compensatory_leave_request", request.name, update_modified=False)
	row.db_set("settlement_note", _(GRANTED_NOTE), update_modified=False)
	return request.name


def recheck_day(employee, day):
	"""Bring replacement leave for (employee, day) in line with the corrected punches.

	Called by hr/punch_correction after a day is re-marked. Returns one line per
	row acted on, for the user; a line starting "⚠" means HRMS refused to take
	a grant back (the caller logs it).
	"""
	lines = []
	for row_name, sheet_name in frappe.db.sql(
		"""select r.name, s.name from `tabOvertime Sheet Employee` r
		join `tabOvertime Sheet` s on s.name = r.parent
		where s.docstatus = 1 and r.employee = %s and s.work_date = %s and r.entitlement = %s""",
		(employee, getdate(day), ENTITLEMENT_REPLACEMENT_LEAVE),
	):
		sheet = frappe.get_doc("Overtime Sheet", sheet_name)
		row = next(r for r in sheet.employees if r.name == row_name)
		line = _resync_row(sheet, row)
		if line:
			lines.append(line)
	return lines


def _resync_row(sheet, row):
	"""Grant, top up or take back one row's leave. Returns a line for the user, or None."""
	present = shown_up(row.employee, sheet.work_date)
	request = row.compensatory_leave_request
	if present and not request:
		granted = grant_row(sheet, row)
		return _("{0}: 1 day of replacement leave granted ({1})").format(sheet.work_date, granted) if granted else None
	if present and not _is_half_day_grant(request):
		return None
	if not request:
		return None

	# A ½ day from before the full-day rule, or a grant the day no longer backs.
	if not present and used(frappe.get_doc("Compensatory Leave Request", request)):
		row.db_set("settlement_note", _used_note(request), update_modified=False)
		return "⚠ " + _("{0}: replacement leave {1} kept — it has already been taken").format(sheet.work_date, request)
	savepoint = f"replacement_resync_{row.name}"[:60]
	frappe.db.savepoint(savepoint)
	try:
		doc = frappe.get_doc("Compensatory Leave Request", request)
		doc.flags.ignore_permissions = True
		# The sheet row links the request; it is unlinked straight after. A
		# refusal for used leave (Leave Allocation going negative) still stands.
		doc.flags.ignore_links = True
		if doc.docstatus == 1:
			doc.cancel()
	except frappe.ValidationError as e:
		frappe.db.rollback(save_point=savepoint)
		frappe.clear_last_message()
		note = _("Kept {0}: could not be taken back ({1})").format(request, frappe.utils.strip_html(str(e)))
		row.db_set("settlement_note", note, update_modified=False)
		return "⚠ " + _("{0}: replacement leave {1} kept — {2}").format(
			sheet.work_date, request, frappe.utils.strip_html(str(e))
		)

	row.db_set("compensatory_leave_request", None, update_modified=False)
	row.compensatory_leave_request = None
	if present:
		granted = grant_row(sheet, row)
		return _("{0}: ½ day replaced by 1 day of replacement leave ({1})").format(sheet.work_date, granted)
	row.db_set("settlement_note", _("Replacement leave taken back: no punch on this day"), update_modified=False)
	return _("{0}: replacement leave {1} taken back — no punch on this day any more").format(sheet.work_date, request)


def _is_half_day_grant(request):
	return bool(request and frappe.db.get_value("Compensatory Leave Request", request, "half_day"))
