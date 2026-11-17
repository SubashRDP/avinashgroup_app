"""Make a Bank Account from a Bank-type Account.

Called by the popup in public/js/account.js after a new Account of type
"Bank" is saved.
"""

import frappe
from frappe import _


@frappe.whitelist()
def has_bank_account(account):
	"""True if a Bank Account is already linked to this Account."""
	return bool(frappe.db.exists("Bank Account", {"account": account}))


@frappe.whitelist()
def create_bank_account(account, bank, bank_account_no):
	"""Create a company Bank Account linked to the given Account.

	account_name : the Account's own name, without number and company
	bank         : picked in the popup
	bank_account_no : typed in the popup
	account      : the Account itself
	company      : same company as the Account
	"""
	acc = frappe.get_doc("Account", account)

	if acc.account_type != "Bank":
		frappe.throw(_("Account {0} is not of type Bank").format(account))

	if has_bank_account(account):
		frappe.throw(_("A Bank Account is already linked to {0}").format(account))

	bank_account = frappe.get_doc(
		{
			"doctype": "Bank Account",
			"account_name": acc.account_name,
			"bank": bank,
			"bank_account_no": bank_account_no,
			"is_company_account": 1,
			"company": acc.company,
			"account": acc.name,
		}
	)
	bank_account.insert()
	return bank_account.name
