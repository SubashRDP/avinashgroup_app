"""Field Duty: staff away from the office on official work count as at work.

Someone who punches in at 09:00, leaves at 10:00 for a site visit and never
comes back to punch out reads, from the device alone, as gone at 10:00: seven
hours early, fined through Late Time, no overtime for the evening the visit
ran into. Someone sent straight to a client in the morning has no punch at all
and reads Absent. HR used to fix that by hand on the month's sheet.

A submitted Field Duty says who was away on which day, from when to when, and
where. Those hours count as time at work, on top of the punches:

    effective IN  = the earlier of the first punch and the duty's From
    effective OUT = the later of the last punch and the duty's To

Everything that measures a day uses the effective times: late and early
minutes (biometric/attendance_sync.compute_shift_deviations, through
effective_times), overtime hours (overtime_settlement.measure_row) and the
meals that follow from them. The punches themselves are never changed; the
Attendance keeps the device's IN and OUT, and the report says the day was on
field duty.

A day with no punch at all is Present: on submit an Attendance is made (or an
Absent one is replaced), and if HRMS marks the day Absent later, the
Attendance validate hook (mark_present_if_on_duty) turns it Present.
A leave day stays leave. Field duty does not authorise overtime by itself:
the Overtime Sheet still decides who is paid for staying late (policy 5.1);
it only makes the hours measurable.

Submitting or cancelling re-measures the days already marked. Both are refused
once a salary slip covering a day is submitted. Many people and days go in one
sheet, by hand or from Excel (field_duty_import).

Entry points: the Field Duty doctype, effective_times (called wherever a day's
in/out is measured), mark_present_if_on_duty (Attendance validate), and the
whitelisted import in hr/field_duty_import.py.
"""

from datetime import datetime, time

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, to_timedelta, today

from avinashgroup_app.payroll.special_payout import REGULAR_SLIPS

DOCTYPE = "Field Duty"
ROW = "Field Duty Row"
DUTY_ROLES = ("HR Manager", "System Manager")
LEAVE_STATUSES = ("On Leave",)


def _installed():
	"""No table before `bench migrate`: no field duty can exist (as for Shift Early Closure)."""
	return frappe.db.table_exists(DOCTYPE)


def duty_window(employee, day, exclude=None):
	"""(from datetime, to datetime) the employee was on submitted field duty on `day`, or None.

	Several rows on one day merge into one span: the earliest From to the latest To.
	"""
	if not employee or not day or not _installed():
		return None
	day = getdate(day)
	params = {"employee": employee, "day": day, "exclude": exclude or ""}
	row = frappe.db.sql(
		f"""select min(r.from_time), max(r.to_time) from `tab{ROW}` r join `tab{DOCTYPE}` d on d.name = r.parent
		where d.docstatus = 1 and r.employee = %(employee)s and r.duty_date = %(day)s and d.name != %(exclude)s""",
		params,
	)
	if not row or row[0][0] is None:
		return None
	midnight = datetime.combine(day, time.min)
	return midnight + to_timedelta(row[0][0]), midnight + to_timedelta(row[0][1])


def effective_times(employee, day, in_time, out_time):
	"""(in, out) for measuring the day: the punches widened by any field duty that day."""
	window = duty_window(employee, day)
	if not window:
		return in_time, out_time
	start, end = window
	in_dt = get_datetime(in_time) if in_time else None
	out_dt = get_datetime(out_time) if out_time else None
	return (min(in_dt, start) if in_dt else start), (max(out_dt, end) if out_dt else end)


# ─────────────────────────────────────────────────────────────── the doctype ──


def validate_duty(doc):
	if not (doc.reason or "").strip():
		frappe.throw(_("Give the reason for the field duty."), title=_("Reason Needed"))
	seen = set()
	for row in doc.rows or []:
		label = _("Row {0}").format(row.idx)
		if frappe.db.get_value("Employee", row.employee, "company") != doc.company:
			frappe.throw(_("{0}: {1} does not work for {2}.").format(label, row.employee, doc.company))
		if to_timedelta(row.to_time) <= to_timedelta(row.from_time):
			frappe.throw(_("{0}: To ({1}) must be after From ({2}).").format(label, row.to_time, row.from_time))
		key = (row.employee, getdate(row.duty_date))
		if key in seen:
			frappe.throw(_("{0}: {1} is already on this sheet for {2}. Put the day on one row.").format(
				label, row.employee_name or row.employee, row.duty_date))
		seen.add(key)
		other = frappe.db.sql(
			f"""select d.name from `tab{ROW}` r join `tab{DOCTYPE}` d on d.name = r.parent
			where d.docstatus = 1 and d.name != %s and r.employee = %s and r.duty_date = %s limit 1""",
			(doc.name or "", row.employee, getdate(row.duty_date)),
		)
		if other:
			frappe.throw(_("{0}: {1} is already on field duty on {2} ({3}). Cancel or amend that one.").format(
				label, row.employee_name or row.employee, row.duty_date, frappe.get_desk_link(DOCTYPE, other[0][0])),
				title=_("Already On Field Duty"))


def _refuse_if_paid(doc):
	for row in doc.rows or []:
		slip = frappe.db.get_value(
			"Salary Slip",
			{"employee": row.employee, "docstatus": 1, "start_date": ("<=", row.duty_date), "end_date": (">=", row.duty_date), **REGULAR_SLIPS},
			"name",
		)
		if slip:
			frappe.throw(_("Row {0}: {1} is inside submitted salary slip {2}. Cancel the slip first.").format(
				row.idx, row.duty_date, slip), title=_("Already Paid"))


def apply_duty(doc, cancelling=False):
	"""Field Duty on_submit / on_cancel: put each past day right.

	By now the duty's own docstatus is saved, so effective_times sees it on
	submit and no longer sees it on cancel: one path for both.
	  * a day already marked Present / Half Day: late, early and overtime re-measured
	  * a day with no attendance, or an Absent one (not leave): marked Present on submit;
	    on cancel, an attendance this duty made for a day with no punch is cancelled
	  * a leave day: left as leave
	"""
	_refuse_if_paid(doc)
	note = (_("Field Duty {0} cancelled: measured from the punches again.") if cancelling
		else _("On field duty ({0}): the hours away count as time at work.")).format(doc.name)
	updated = 0
	for row in doc.rows or []:
		day = getdate(row.duty_date)
		if day > getdate(today()):
			continue  # a future day is measured when it is marked (the Attendance hooks read the duty)
		if _apply_day(doc, row, cancelling, note):
			updated += 1
	doc.db_set("attendance_updated", updated)
	if updated:
		frappe.msgprint(_("{0} attendance day(s) updated.").format(updated), alert=True)


def _attendance(employee, day):
	return frappe.db.get_value(
		"Attendance",
		{"employee": employee, "attendance_date": day, "docstatus": 1},
		["name", "status", "shift", "in_time", "out_time", "company", "leave_type", "leave_application"],
		as_dict=True,
	)


def _apply_day(doc, row, cancelling, note):
	from avinashgroup_app.biometric.attendance_sync import get_day_checkins

	day = getdate(row.duty_date)
	att = _attendance(row.employee, day)
	if att and (att.status in LEAVE_STATUSES or att.leave_type or att.leave_application) and att.status != "Half Day":
		return False

	if cancelling and att and att.name == row.attendance and not get_day_checkins(row.employee, day):
		# Made by this duty for a day with no punch: without the duty there is nothing to mark.
		frappe.get_doc("Attendance", att.name).add_comment("Info", note)
		frappe.get_doc("Attendance", att.name).cancel()
		return True

	if att and att.status in ("Present", "Half Day", "Work From Home"):
		return _remeasure(att, note)

	if cancelling:
		return False
	# No attendance, or Absent: the person was at work, away from the office.
	if att:
		old = frappe.get_doc("Attendance", att.name)
		old.add_comment("Info", note)
		old.cancel()
	new = frappe.get_doc(
		{
			"doctype": "Attendance",
			"employee": row.employee,
			"attendance_date": day,
			"company": doc.company,
			"status": "Present",
			"amended_from": att.name if att else None,
		}
	)
	new.insert()  # validate: shift from the roster, minutes from the effective times
	new.submit()
	new.add_comment("Info", note)
	frappe.db.set_value(ROW, row.name, "attendance", new.name, update_modified=False)
	return True


def _remeasure(att, note):
	"""Late / early / overtime of an already-marked day, from its effective times."""
	from avinashgroup_app.biometric.attendance_sync import compute_shift_deviations, is_half_day_leave
	from avinashgroup_app.hr.shift_backdate import _remeasure_overtime

	if not att.shift:
		return False
	row = frappe.db.get_value("Attendance", att.name, ["employee", "attendance_date"], as_dict=True)
	in_t, out_t = effective_times(row.employee, row.attendance_date, att.in_time, att.out_time)
	values = compute_shift_deviations(
		frappe.get_cached_doc("Shift Type", att.shift), row.attendance_date, in_t, out_t,
		company=att.company, half_day=is_half_day_leave(att),
	)
	frappe.db.set_value("Attendance", att.name, values, update_modified=False)
	frappe.get_doc("Attendance", att.name).add_comment("Info", note)
	_remeasure_overtime(row.employee, row.attendance_date, row.attendance_date)
	return True


def mark_present_if_on_duty(doc, method=None):
	"""Attendance validate: a day the person spent on submitted field duty is not Absent.

	HRMS marks a day with no punch Absent at the shift's end; for someone sent
	out on duty that day the Absent is wrong. Leave is left alone."""
	if doc.status != "Absent" or doc.leave_type or doc.get("leave_application"):
		return
	if duty_window(doc.employee, doc.attendance_date):
		doc.status = "Present"


def duty_notes_between(company, start, end):
	"""{(employee, date): "Field duty 10:00-17:30 (Butwal: delivery)"} for the report, one query."""
	if not _installed():
		return {}
	filters = "and d.company = %(company)s" if company else ""
	rows = frappe.db.sql(
		f"""select r.employee, r.duty_date, r.from_time, r.to_time, r.place, r.purpose
		from `tab{ROW}` r join `tab{DOCTYPE}` d on d.name = r.parent
		where d.docstatus = 1 and r.duty_date between %(start)s and %(end)s {filters}
		order by r.from_time""",
		{"company": company, "start": getdate(start), "end": getdate(end)},
		as_dict=True,
	)
	parts = {}
	for r in rows:
		where = ": ".join(x for x in (r.place, r.purpose) if x)
		span = f"{str(to_timedelta(r.from_time))[:-3]}-{str(to_timedelta(r.to_time))[:-3]}"
		parts.setdefault((r.employee, getdate(r.duty_date)), []).append(frappe.utils.escape_html(f"{span} ({where})" if where else span))
	return {k: _("Field duty {0}").format(", ".join(v)) for k, v in parts.items()}
