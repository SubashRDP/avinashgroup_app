"""Party-side account for a Customer/Supplier Payment Entry, picked from the party master.

Stock ERPNext fills Account Paid From (Receive) / Account Paid To (Pay) with the
party's receivable/payable account when the party is chosen, and never looks at
the Advance Account the user maintains in the party's Accounts table. Here the
form (public/js/payment_entry.js) asks this module which account to show:

- no invoice tagged in References -> the party's own Advance Account for the
  company, when that row has one
- invoices tagged, or no Advance Account on the party -> the party's default
  receivable/payable account (party row, then party group, then company default,
  exactly as stock get_party_account resolves it)

Deliberately narrow: this only suggests the account in the form. It does not
change what the server posts; on save, set_liability_account (and our
advance_account_patch.py on top of it) still decides the final account.
"""

import frappe

from erpnext.accounts.party import get_party_account

# Party types whose Accounts table carries an Advance Account column.
PARTY_TYPES_WITH_ADVANCE_ACCOUNT = frozenset(("Customer", "Supplier"))


@frappe.whitelist()
def get_party_accounts(party_type: str, party: str, company: str) -> dict:
	"""Return {"default_account", "advance_account"} for the party in this company.

	Called from the Payment Entry form. advance_account is None when the party's
	own Accounts row for the company has no Advance Account.
	"""
	frappe.has_permission("Payment Entry", throw=True)

	if party_type not in PARTY_TYPES_WITH_ADVANCE_ACCOUNT:
		return {"default_account": None, "advance_account": None}

	advance_account = frappe.db.get_value(
		"Party Account",
		{"parenttype": party_type, "parent": party, "company": company},
		"advance_account",
	)

	return {
		"default_account": get_party_account(party_type, party, company),
		"advance_account": advance_account or None,
	}
