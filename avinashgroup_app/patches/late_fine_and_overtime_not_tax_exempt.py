"""Untick "Exempted from Income Tax" on late-fine and overtime components.

"late comers deduction" (Late Time) was ticked exempt, so a late fine lowered
the person's taxable pay as if it were a retirement contribution — and once the
retirement cap is switched on, tax_relief.retirement_excess would count it as
one. "Overtime" (Authorised Overtime) carried the tick too; on an earning it
does nothing, but it reads as if overtime were tax-free. Neither is: a fine is
pay withheld, overtime is pay. payroll/allowance._check_type_for_condition now
refuses the tick on both, so it cannot come back.
"""

import frappe


def execute():
	if not frappe.get_meta("Salary Component").has_field("custom_condition_type"):
		return
	for name in frappe.get_all(
		"Salary Component",
		filters={"custom_condition_type": ("in", ("Late Time", "Authorised Overtime")), "exempted_from_income_tax": 1},
		pluck="name",
	):
		frappe.db.set_value("Salary Component", name, "exempted_from_income_tax", 0, update_modified=False)
