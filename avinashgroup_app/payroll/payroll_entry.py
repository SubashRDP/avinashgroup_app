"""The payroll journal posts each section's pay to that section's own account.

The chart keeps every staff cost three ways — O/O (Admin & Accounts), S/D
(Marketing), F/P (Plant) — and the client's salary sheet charges each person
by department. HRMS's accrual journal groups slip amounts by (component, cost
centre) and takes ONE account per component and company
(`PayrollEntry.get_salary_component_account`), so all of it landed on O/O.

This override groups by (component, cost centre, section) instead, where the
section is the employee's Department → `custom_payroll_section`, and takes the
account for that section from the component's Company Allowance. A component
with no Company Allowance keeps HRMS's account.

Boundary: only the expense (earning) and deduction rows of the accrual
journal. Employee-advance recoveries and the payable side are HRMS's own
logic, untouched. Replaces the Salary-Expenses-only routing that used to live
in payroll/hr_journal.py. Registered via override_doctype_class.
"""

import frappe
from frappe import _
from frappe.utils import flt

from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry

from avinashgroup_app.payroll.company_allowance import (
	get_company_allowance,
	get_section,
	has_section_accounts,
	section_account,
)


class AvinashPayrollEntry(PayrollEntry):
	def get_salary_component_total(
		self,
		component_type=None,
		employee_wise_accounting_enabled=False,
	):
		"""HRMS's own loop (hrms 15, payroll_entry.py), keyed by section too."""
		salary_components = self.get_salary_components(component_type)
		if not salary_components:
			return

		component_dict = {}
		missing_section = set()
		for item in salary_components:
			if not self.should_add_component_to_accrual_jv(component_type, item):
				continue

			section = self.section_for(item, missing_section)
			employee_cost_centers = self.get_payroll_cost_centers_for_employee(
				item.employee, item.salary_structure
			)
			employee_advance = self.get_advance_deduction(component_type, item)

			for cost_center, percentage in employee_cost_centers.items():
				amount_against_cost_center = flt(item.amount) * percentage / 100

				if employee_advance:
					self.add_advance_deduction_entry(
						item, amount_against_cost_center, cost_center, employee_advance
					)
				else:
					key = (item.salary_component, cost_center, section)
					component_dict[key] = component_dict.get(key, 0) + amount_against_cost_center

				if employee_wise_accounting_enabled:
					self.set_employee_based_payroll_payable_entries(
						component_type, item.employee, amount_against_cost_center
					)

		if missing_section:
			frappe.throw(
				_(
					"Set Payroll Section on the Department of these employees, so their pay "
					"posts to the right account: {0}"
				).format(", ".join(sorted(missing_section)))
			)

		return self.get_account(component_dict=component_dict)

	def section_for(self, item, missing_section: set):
		"""The employee's section, if this component posts by section at all."""
		allowance = get_company_allowance(self.company, item.salary_component)
		if not allowance or not has_section_accounts(allowance):
			return None
		section = get_section(item.employee)
		if not section:
			missing_section.add(item.employee)
		return section

	def get_account(self, component_dict=None):
		account_dict = {}
		for (component, cost_center, section), amount in component_dict.items():
			allowance = get_company_allowance(self.company, component)
			account = (allowance and section_account(allowance, section)) or self.get_salary_component_account(
				component
			)
			accounting_key = (account, cost_center)
			account_dict[accounting_key] = account_dict.get(accounting_key, 0) + amount
		return account_dict
