"""A company's payroll payable account must have no Account Type.

HRMS refuses a Payroll Entry whose payable account has one ("Account type
cannot be set for payroll payable account ..."): the salary liability is
booked per employee, not per party. The chart came with Salary Payable typed
"Payable" (NGN) or "Liability" (NGG, NGK); only NGI's was blank. Clears the
type on each company's Default Payroll Payable Account and nothing else.
"""

import frappe


def execute():
	for account in frappe.get_all(
		"Company", filters={"default_payroll_payable_account": ("is", "set")}, pluck="default_payroll_payable_account"
	):
		if frappe.db.get_value("Account", account, "account_type"):
			frappe.db.set_value("Account", account, "account_type", "")
