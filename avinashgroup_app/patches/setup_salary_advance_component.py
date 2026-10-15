"""The "Salary Advance" deduction that advance recovery posts on.

payroll/advance_recovery.py posts every instalment on this component, but no
site had it: the component was only ever made by the onboarding script, which
was never run here, so an Employee Advance could not be recovered from salary
at all. Made as a plain deduction — not prorated, hidden at zero, NOT exempt
from income tax (repaying a loan does not lower taxable pay).

Its account is the one the advance itself sits in, per company: the Company's
Default Employee Advance Account when set, else 148003 Staff Advance. HRMS posts
a slip deduction as a credit to the component's account, so the recovery
credits the advance account and clears the receivable — the same account
onboarding's PROPOSED_ACCOUNTS names. The section columns stay blank: an advance
is not a section's cost, and blank falls back to this account.
"""

import frappe

COMPONENT = "Salary Advance"
FALLBACK_ACCOUNT = "148003 - Staff Advance"


def execute():
	if frappe.db.exists("Salary Component", COMPONENT):
		doc = frappe.get_doc("Salary Component", COMPONENT)
	else:
		doc = frappe.new_doc("Salary Component")
		doc.salary_component = COMPONENT
		doc.salary_component_abbr = _free_abbr("ADV")
	doc.type = "Deduction"
	doc.depends_on_payment_days = 0
	doc.remove_if_zero_valued = 1
	doc.exempted_from_income_tax = 0
	if doc.meta.has_field("custom_is_attendance_driven"):
		doc.custom_is_attendance_driven = 0
	for company, abbr, default in frappe.get_all(
		"Company", fields=["name", "abbr", "default_employee_advance_account"], as_list=True
	):
		account = default or f"{FALLBACK_ACCOUNT} - {abbr}"
		if not frappe.db.exists("Account", {"name": account, "is_group": 0}):
			continue
		row = next((a for a in doc.accounts if a.company == company), None) or doc.append("accounts", {"company": company})
		if not row.account:
			row.account = account
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.save()


def _free_abbr(abbr):
	taken = set(frappe.get_all("Salary Component", pluck="salary_component_abbr"))
	n, candidate = 1, abbr
	while candidate in taken:
		n += 1
		candidate = f"{abbr}{n}"
	return candidate
