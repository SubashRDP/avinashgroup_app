"""Fixed allowances on the salary slip, from the employee's Allowances table.

Dearness, other, fuel, gas, education, HRA and any allowance added later are
not structure rows: each employee's own rows (Employee → Allowances) say what
they get, so a new allowance needs no new field and no new structure. This hook
puts those rows on the slip (amounts from payroll/allowance.py
`fixed_allowance_amounts`).

Why on the slip and not as a monthly Additional Salary: HRMS projects a slip's
non-additional earnings over the rest of the year when it computes income
tax, but treats a one-off Additional Salary as this month only, so it would
under-tax. Rows added here carry no `additional_salary`: HRMS projects them
like structure rows, and prorates them by payment days when the component has
Depends on Payment Days.

Why a hook and not a controller override: rdp_common_app already overrides the
Salary Slip class (BS months), and Frappe v15 lets only one app's override
win. So this runs on validate, after HRMS has built the slip, and recalculates
it with HRMS's own `calculate_net_pay` so gross, tax and net include the rows.

Boundary: attendance allowances are posted as Additional Salary by Prepare
Payroll Inputs (payroll/attendance_allowance.py). A structure's Preview Salary
Slip does not run validate, so it shows the structure's lines only.
"""

import frappe
from frappe.utils import flt

from hrms.payroll.doctype.salary_slip.salary_slip import get_salary_component_data

from avinashgroup_app.payroll.allowance import FIXED_KINDS, fixed_allowance_amounts


def add_employee_allowances(doc, method=None):
	"""Add, update or drop the slip rows of the employee's fixed allowances.

	Hook: doc_events → Salary Slip → validate, ahead of the tax hooks. Leaves a
	submitted slip, and a slip without a structure, alone.
	"""
	if doc.docstatus != 0 or not doc.salary_structure or not doc.employee:
		return

	wanted = fixed_allowance_amounts(doc.employee, doc.company, doc.end_date)
	managed = {
		d.salary_component
		for d in doc.earnings
		if not d.additional_salary
		and frappe.get_cached_value("Salary Component", d.salary_component, "custom_allowance_kind") in FIXED_KINDS
	} | set(wanted)
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
		[d for d in doc.earnings if d.additional_salary or d.salary_component not in managed or d.salary_component in wanted],
	)
	for component, amount in wanted.items():
		doc.update_component_row(get_salary_component_data(component), amount, "earnings", default_amount=amount)
	doc.calculate_net_pay()
