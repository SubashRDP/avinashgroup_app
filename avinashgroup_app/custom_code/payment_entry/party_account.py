"""Party accounts for a Customer/Supplier Payment Entry form.

The form (public/js/payment_entry.js) fills Account Paid From (Receive) /
Account Paid To (Pay) with default_account, and uses both accounts to tell
whether the user picked a different account by hand.

- default_account: the party's receivable/payable account (party row, then party
  group, then company default, as stock get_party_account resolves it)
- advance_account: the party's advance account (party row, then party group,
  then company default advance received / paid account)

This only fills the form. On save, advance_account_patch.py decides the final
account from the Unallocated Amount.
"""

import frappe

from erpnext.accounts.party import get_party_account, get_party_advance_account

# Party types whose Accounts table carries an Advance Account column.
PARTY_TYPES_WITH_ADVANCE_ACCOUNT = frozenset(("Customer", "Supplier"))


@frappe.whitelist()
def get_party_accounts(party_type: str, party: str, company: str) -> dict:
	"""Return {"default_account", "advance_account"} for the party in this company.

	Called from the Payment Entry form.
	"""
	frappe.has_permission("Payment Entry", throw=True)

	if party_type not in PARTY_TYPES_WITH_ADVANCE_ACCOUNT:
		return {"default_account": None, "advance_account": None}

	return {
		"default_account": get_party_account(party_type, party, company),
		"advance_account": get_party_advance_account(party_type, party, company) or None,
	}
