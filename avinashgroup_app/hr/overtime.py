"""Overtime rules: what extra work the company authorised, and what it earns.

Policy (client meeting 2026-09-15, `docs/hr-decisions/00-policy-minutes-2026-09-15.txt`):
  5.1  overtime is tracked on a per-day sheet, and that sheet decides eligibility —
       a punch outside normal hours proves presence, not that the company asked;
  2.2  (as corrected 2026-09-16) and 2.5: for a holiday or Saturday worked, staff
       below officer level are paid overtime, officer and admin level get a
       replacement leave day instead — never both.

The design keeps three concerns apart so each can change without the others:

    POLICY          Employee Category    who is OT-eligible / gets replacement leave
    AUTHORISATION   Overtime Sheet       the company's approved request, per date
    RULES           this module          day type x category -> entitlement, hours

This module is the only place the rules live. The Overtime Sheet form calls
`evaluate()` for every row; downstream steps (attendance matching, payroll) call
`get_authorised()` and never re-derive anything.

The sheet records WHO was asked and FOR WHAT (work on a holiday, or overtime on a
working day) — never hours. Hours are measured from attendance at settlement, so
no typed time can ever disagree with the punches; `hours_outside_shift()` is the
measuring rule settlement uses.

Deliberately narrow:
  * no attendance here. What the company authorised and what the punches show are
    separate facts; matching them is the settlement step's job.
  * no money here. An entitlement type goes out; rates and amounts belong to
    salary components.
"""

from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import get_time, getdate

# ── Day types — resolved per EMPLOYEE, never per company: holiday lists differ
#    (Teej is a holiday only on the (Women) lists).
DAY_HOLIDAY = "Holiday"
DAY_WEEKLY_OFF = "Weekly Off"
DAY_WORKING = "Working Day"

# ── Work types — what HR says the person was asked for.
WORK_ON_HOLIDAY = "Work on Holiday"
WORK_OVERTIME = "Overtime"

# ── Entitlements — what an authorised, worked row turns into.
ENTITLEMENT_OVERTIME = "Overtime"
ENTITLEMENT_REPLACEMENT_LEAVE = "Replacement Leave"


class OvertimeRuleError(frappe.ValidationError):
	"""A row the policy does not allow. Raised with a sentence HR can act on."""


# ─────────────────────────────────────────────────────────────── day type ──


def get_day_type(employee, work_date):
	"""(day_type, description) for this employee on this date, from their own list.

	Employee's Holiday List first, company default second — the order salary slips
	and attendance use, so the three can never disagree about what a day is.
	"""
	from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

	holiday_list = get_holiday_list_for_employee(employee, raise_exception=False)
	row = (
		frappe.db.get_value(
			"Holiday",
			{"parent": holiday_list, "holiday_date": getdate(work_date)},
			["description", "weekly_off"],
			as_dict=True,
		)
		if holiday_list
		else None
	)
	if not row:
		return DAY_WORKING, None

	description = frappe.utils.strip_html(row.description or "").strip()
	if row.weekly_off:
		return DAY_WEEKLY_OFF, description or DAY_WEEKLY_OFF
	return DAY_HOLIDAY, description or DAY_HOLIDAY


# ────────────────────────────────────────────────────────────────── shift ──


def get_shift_window(employee, work_date):
	"""(shift_type, start_datetime, end_datetime) the employee is rostered on that date.

	Dated Shift Assignment first, Default Shift second — the same precedence HRMS
	uses. Resolved from the assignment's dates, not from a timestamp, so a shift is
	found even on a day with no punches. Returns (None, None, None) if unrostered.
	"""
	work_date = getdate(work_date)
	assignment = frappe.db.sql(
		"""select shift_type from `tabShift Assignment`
		where employee = %s and docstatus = 1 and status = 'Active'
		  and start_date <= %s and (end_date is null or end_date >= %s)
		order by start_date desc limit 1""",
		(employee, work_date, work_date),
	)
	shift_type = assignment[0][0] if assignment else frappe.db.get_value("Employee", employee, "default_shift")
	if not shift_type:
		return None, None, None

	start, end = frappe.db.get_value("Shift Type", shift_type, ["start_time", "end_time"])
	start_dt = datetime.combine(work_date, get_time(start))
	end_dt = datetime.combine(work_date, get_time(end))
	if end_dt <= start_dt:  # overnight shift
		end_dt += timedelta(days=1)
	return shift_type, start_dt, end_dt


# ─────────────────────────────────────────────────────────────── the rules ──


def get_category_rule(employee):
	"""(category, ot_eligible, compensatory_leave) — raises if the employee has none.

	No category means the policy cannot say what the person earns, so the row is
	refused rather than defaulted: a wrong default pays money or grants leave.
	"""
	category = frappe.db.get_value("Employee", employee, "custom_employee_category")
	if not category:
		raise OvertimeRuleError(
			_("{0} has no Employee Category — set it with the Employee Category Tool first").format(
				employee_label(employee)
			)
		)
	ot_eligible, compensatory_leave = frappe.db.get_value(
		"Employee Category", category, ["ot_eligible", "compensatory_leave"]
	)
	return category, bool(ot_eligible), bool(compensatory_leave)


def default_work_type(day_type):
	"""The work type a day implies: a holiday or Saturday is holiday work, else overtime."""
	return WORK_ON_HOLIDAY if day_type in (DAY_HOLIDAY, DAY_WEEKLY_OFF) else WORK_OVERTIME


def evaluate(employee, work_date, work_type=None):
	"""Apply the policy to one row. Returns a dict the form writes back; raises
	OvertimeRuleError for a row the policy refuses.

	`work_type` defaults to what the day implies for this employee.

	    Work on Holiday   day must be a Holiday / Weekly Off for this person
	                        Plant (OT-eligible)      -> Overtime
	                        Officer & Admin (leave)  -> Replacement Leave
	    Overtime          day must be a Working Day for this person
	                        OT-eligible only, and a shift must exist — settlement
	                        measures hours outside it -> Overtime
	"""
	day_type, day_name = get_day_type(employee, work_date)
	category, ot_eligible, compensatory_leave = get_category_rule(employee)
	shift = get_shift_window(employee, work_date)[0]
	work_type = work_type or default_work_type(day_type)
	on_holiday = day_type in (DAY_HOLIDAY, DAY_WEEKLY_OFF)
	date_label = frappe.utils.formatdate(work_date)

	result = {
		"work_type": work_type,
		"day_type": day_type,
		"day_name": day_name,
		"employee_category": category,
		"shift": shift,
	}

	if work_type == WORK_ON_HOLIDAY:
		if not on_holiday:
			raise OvertimeRuleError(
				_("{0}: {1} is a working day for them — choose Overtime, not Work on Holiday").format(
					employee_label(employee), date_label
				)
			)
		if ot_eligible:
			result["entitlement"] = ENTITLEMENT_OVERTIME
		elif compensatory_leave:
			result["entitlement"] = ENTITLEMENT_REPLACEMENT_LEAVE
		else:
			raise OvertimeRuleError(
				_("{0}: category {1} earns nothing for holiday work").format(employee_label(employee), category)
			)
		return result

	if work_type != WORK_OVERTIME:
		raise OvertimeRuleError(_("Unknown work type {0}").format(work_type))

	if on_holiday:
		raise OvertimeRuleError(
			_("{0}: {1} is {2} for them — choose Work on Holiday, not Overtime").format(
				employee_label(employee), date_label, (day_name or day_type)
			)
		)
	if not ot_eligible:
		raise OvertimeRuleError(
			_("{0} ({1}) is not eligible for overtime on a working day").format(
				employee_label(employee), category
			)
		)
	if not shift:
		raise OvertimeRuleError(
			_("{0} has no shift on {1}, so overtime beyond it cannot be measured").format(
				employee_label(employee), date_label
			)
		)
	result["entitlement"] = ENTITLEMENT_OVERTIME
	return result


@frappe.whitelist()
def preview(employee, work_date, work_type=None):
	"""Form helper: evaluate a row live. Returns {"ok": bool, ...result or "message"}."""
	if not (employee and work_date):
		return {"ok": False, "message": ""}
	try:
		return {"ok": True, **evaluate(employee, work_date, work_type or None)}
	except OvertimeRuleError as e:
		return {"ok": False, "message": str(e)}


# ──────────────────────────────────────────────────────────────── read API ──


def get_authorised(work_date, company=None):
	"""Authorised extra work on a date: {employee: {...row, "sheet": name}}.

	Submitted Overtime Sheets only — a draft or a sheet pending approval is a
	request, not an authorisation. This is the single question settlement asks.
	"""
	sheet = frappe.qb.DocType("Overtime Sheet")
	row = frappe.qb.DocType("Overtime Sheet Employee")
	query = (
		frappe.qb.from_(row)
		.join(sheet)
		.on(row.parent == sheet.name)
		.select(
			sheet.name.as_("sheet"),
			row.employee,
			row.work_type,
			row.day_type,
			row.entitlement,
			row.shift,
		)
		.where((sheet.docstatus == 1) & (sheet.work_date == getdate(work_date)))
	)
	if company:
		query = query.where(sheet.company == company)
	return {r.employee: r for r in query.run(as_dict=True)}


def was_authorised(employee, work_date):
	return employee in get_authorised(work_date)


# ──────────────────────────────────────────────────────────────── helpers ──


def employee_label(employee):
	return frappe.db.get_value("Employee", employee, "employee_name") or employee


def hours_outside_shift(in_time, out_time, shift_start, shift_end):
	"""Hours of [in_time, out_time] before the shift starts or after it ends.

	The overtime measure for a working day, used at settlement with the actual
	punches. All four are datetimes; a punch window that does not overlap the
	shift counts in full.
	"""
	if not (in_time and out_time) or out_time <= in_time:
		return 0.0
	worked = (out_time - in_time).total_seconds()
	overlap = max((min(out_time, shift_end) - max(in_time, shift_start)).total_seconds(), 0)
	return round((worked - overlap) / 3600, 2)
