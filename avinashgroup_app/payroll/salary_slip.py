"""Fixed allowances on the salary slip, from the employee's Allowances table.

A fixed allowance (gas, mobile recharge, HRA as a share of initial basic) used
to need its own row in the salary structure, with a formula reading a per-
person Employee field — so every new allowance was a structure edit and a new
custom field. Now a company lists it once as a `Company Allowance` (Fixed
Monthly or % of Initial Basic), the employee's Allowances table says who gets
it and at what rate, and this hook adds the row to the slip.

Why on the slip and not as a monthly Additional Salary: HRMS projects a slip's
non-additional earnings over the rest of the year when it computes income
tax, but treats a one-off Additional Salary as this month only. Posted that way,
a 1,500 a month allowance would be taxed as 1,500 a year. Rows added here carry
no `additional_salary`, so HRMS projects them like structure rows, and prorates
them by payment days when the component has Depends on Payment Days.

Why a hook and not a controller override: rdp_common_app already overrides the
Salary Slip class (BS months), Frappe v15 lets only the last-installed app's
override win, and on avinas1 that is rdp_common_app. So this runs on validate,
after HRMS has built the slip, and recalculates it — the same
`calculate_net_pay` HRMS itself runs — so gross, tax and net include the rows.

Boundary: attendance-based allowances stay with payroll/attendance_allowance.py
(posted as Additional Salary each month); "From Salary Structure" allowances
stay in the structure. A structure preview (for_preview) does not run validate
and so does not show these rows.
"""

import frappe
from frappe.utils import flt

from hrms.payroll.doctype.salary_slip.salary_slip import get_salary_component_data

from avinashgroup_app.payroll.company_allowance import (
	PERCENT_OF_INITIAL_BASIC,
	SLIP_CALCULATIONS,
	employee_gets,
	employee_rate,
	get_company_allowances,
	get_employee_allowance_rows,
)


def add_company_allowances(doc, method=None):
	"""Add, update or drop the slip rows of the company's fixed allowances.

	Hook: doc_events → Salary Slip → validate, ahead of the tax hooks. Leaves a
	submitted slip, and a slip without a structure, alone.
	"""
	if doc.docstatus != 0 or not doc.salary_structure:
		return

	allowances = [
		a for a in get_company_allowances(doc.company)
		if not a.is_attendance_based and a.calculation in SLIP_CALCULATIONS
	]
	managed = {a.salary_component for a in allowances}
	wanted = _wanted_amounts(doc, allowances)
	have = {
		d.salary_component: flt(d.default_amount)
		for d in doc.earnings
		if d.salary_component in managed and not d.additional_salary
	}
	if have == wanted:
		return

	# An allowance taken off the employee since the slip was last saved must
	# leave it, or it keeps being paid.
	doc.set(
		"earnings",
		[
			d for d in doc.earnings
			if d.additional_salary or d.salary_component not in managed or d.salary_component in wanted
		],
	)
	for component, amount in wanted.items():
		doc.update_component_row(get_salary_component_data(component), amount, "earnings", default_amount=amount)
	doc.calculate_net_pay()


def _wanted_amounts(doc, allowances) -> dict:
	"""{component: full-month amount} this employee should have on the slip."""
	if not allowances:
		return {}
	rows = get_employee_allowance_rows(doc.employee, doc.end_date)
	wanted = {}
	for allowance in allowances:
		row = rows.get(allowance.salary_component)
		if not employee_gets(allowance, row):
			continue
		amount = employee_rate(allowance, row)
		if allowance.calculation == PERCENT_OF_INITIAL_BASIC:
			initial_basic = frappe.db.get_value("Employee", doc.employee, "custom_initial_basic")
			amount = flt(initial_basic) * amount / 100
		if amount:
			wanted[allowance.salary_component] = flt(amount, 2)
	return wanted
