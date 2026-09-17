"""Who the company called in to work on a holiday.

Policy, client meeting of 2026-09-15 (`docs/hr-decisions/00-policy-minutes-2026-09-15.txt`):
overtime for holiday work is tracked on a per-day sheet, and that sheet decides
eligibility (5.1). A punch on a holiday proves someone was on site; it does not
prove the company asked them to be. Only work the company called for earns
overtime (Plant) or replacement leave (Officer & Admin, 2.2 as corrected).

The sheet is the `Holiday Duty Sheet` doctype, approved through Dynamic Approval.
This module is the read side: the question every later step asks.

Deliberately narrow:
  * only SUBMITTED sheets count. A draft or a sheet still pending approval is a
    request, not a call-in.
  * it does not look at attendance. Someone who came without being on a sheet is
    fixed by adding them to a sheet (backdated sheets are allowed for exactly
    this), not by guessing from punches here.
"""

import frappe
from frappe.utils import getdate


def get_called_employees(holiday_date, company=None):
	"""Employees on a submitted Holiday Duty Sheet for `holiday_date`.

	Returns {employee: {"sheet": name, "from_time", "to_time", "planned_hours"}}.
	"""
	sheet = frappe.qb.DocType("Holiday Duty Sheet")
	row = frappe.qb.DocType("Holiday Duty Sheet Employee")
	query = (
		frappe.qb.from_(row)
		.join(sheet)
		.on(row.parent == sheet.name)
		.select(sheet.name, row.employee, row.from_time, row.to_time, row.planned_hours)
		.where((sheet.docstatus == 1) & (sheet.holiday_date == getdate(holiday_date)))
	)
	if company:
		query = query.where(sheet.company == company)

	return {
		r.employee: {
			"sheet": r.name,
			"from_time": r.from_time,
			"to_time": r.to_time,
			"planned_hours": r.planned_hours,
		}
		for r in query.run(as_dict=True)
	}


def was_called(employee, holiday_date):
	"""True if `employee` is on a submitted Holiday Duty Sheet for that date."""
	return employee in get_called_employees(holiday_date)


def get_holiday_for_employee(employee, holiday_date):
	"""(is_holiday, description) for the employee's own holiday list on that date.

	Uses the employee's list first and the company default second — the same
	order salary slips and attendance use — so a woman on a (Women) list sees Teej
	as a holiday and a man does not.
	"""
	from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

	holiday_list = get_holiday_list_for_employee(employee, raise_exception=False)
	if not holiday_list:
		return False, None

	row = frappe.db.get_value(
		"Holiday",
		{"parent": holiday_list, "holiday_date": getdate(holiday_date)},
		["description", "weekly_off"],
		as_dict=True,
	)
	if not row:
		return False, None
	description = frappe.utils.strip_html(row.description or "").strip()
	return True, description or ("Weekly Off" if row.weekly_off else "Holiday")
