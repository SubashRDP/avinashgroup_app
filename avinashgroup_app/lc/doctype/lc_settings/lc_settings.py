"""LC Settings — per-company LC accounts, the NRB limits the LC form checks, and the digest.

One row per company in Company Accounts; a company without a row cannot submit a
Letter of Credit. "Create Missing Accounts" (lc/install.py) fills the rows for
every company that has none, so the seven companies are not done by hand.

The NRB figures are settings, not constants, because NRB revises its forex
circular several times a year (four times in 2026 alone).
"""

import frappe
from frappe import _
from frappe.model.document import Document


class LCSettings(Document):
	def validate(self):
		seen = set()
		for row in self.company_accounts:
			if row.company in seen:
				frappe.throw(_("Row {0}: {1} is listed twice.").format(row.idx, row.company))
			seen.add(row.company)
			for field in ("margin_account", "transit_account", "vat_account"):
				account = row.get(field)
				if account and frappe.get_cached_value("Account", account, "company") != row.company:
					frappe.throw(_("Row {0}: {1} does not belong to {2}.").format(row.idx, account, row.company))
			if row.margin_account == row.transit_account:
				frappe.throw(_("Row {0}: LC Margin and LC Goods in Transit must be different accounts.").format(row.idx))
			if row.transit_account and frappe.get_cached_value("Account", row.transit_account, "account_type") == "Stock":
				# The transfer's Stock Entry credits this account as its Difference
				# Account, which ERPNext refuses for a Stock-type account.
				frappe.throw(_("Row {0}: LC Goods in Transit must not be a Stock-type account.").format(row.idx))


@frappe.whitelist()
def create_missing_accounts():
	frappe.only_for(("System Manager", "Accounts Manager"))
	from avinashgroup_app.lc.install import ensure_company_accounts

	return ensure_company_accounts()
