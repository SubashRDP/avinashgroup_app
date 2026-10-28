"""PDC Settings — holding accounts per company, cheque rules, digest and SMS switches.

One row per company in Company Accounts; a company without a row cannot submit
a PDC Cheque. "Create Missing Accounts" (pdc/install.py) fills the rows for every
company that has none, so the seven companies do not have to be done by hand.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class PDCSettings(Document):
	def validate(self):
		seen = set()
		for row in self.company_accounts:
			if row.company in seen:
				frappe.throw(_("Row {0}: {1} is listed twice.").format(row.idx, row.company))
			seen.add(row.company)
			for field in ("cheques_in_hand_account", "cheques_issued_account", "bounce_charges_account"):
				account = row.get(field)
				if account and frappe.get_cached_value("Account", account, "company") != row.company:
					frappe.throw(_("Row {0}: {1} does not belong to {2}.").format(row.idx, account, row.company))
			if row.cheques_in_hand_account == row.cheques_issued_account:
				frappe.throw(_("Row {0}: Cheques in Hand and Cheques Issued must be different accounts.").format(row.idx))


@frappe.whitelist()
def create_missing_accounts():
	frappe.only_for(("System Manager", "Accounts Manager"))
	from avinashgroup_app.pdc.install import ensure_company_accounts

	return ensure_company_accounts()
