"""Letter of Credit — one import LC the company opens through its bank for a supplier.

The draft is the LC application (Bi.Bi.Ni Form 3 terms); submitting it means the
application went to the bank (status Applied). Everything after — the bank's
LC number and margin, charges, amendments, shipments, acceptance, settlement,
customs proof, closing — is a button on the submitted form that runs
`lc/lifecycle.py` and adds a History row.

Validation here carries the Nepal Rastra Bank rules that bind the terms
themselves (thresholds live in LC Settings, because NRB changes them):
* a sight LC at or above the BCI threshold (USD 50,000) needs a Business
  Credibility Information report on the beneficiary, not older than a year;
* a trading firm's usance may not exceed 180 days;
* the Nepal border customs point must be named.

Cancel is only for an LC that has not moved past its application (no step after
Applied except charges are undone first): later entries are real bank events,
so they are undone one at a time with Undo Last Step, newest first.

Deliberately thin: posting in `lc/accounting.py`, steps in `lc/lifecycle.py`.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff, flt, getdate

from avinashgroup_app.custom_code.Override.naming_series import make_name_with_fiscal_year
from avinashgroup_app.lc import accounting, lifecycle

# The documents almost every import LC asks for (MT700 field 46A); a new LC
# starts with these as its checklist. (document, originals, copies)
DEFAULT_DOCUMENTS = (
	("Commercial Invoice", 3, 3),
	("Packing List", 3, 3),
	("Bill of Lading / Airway Bill / Consignment Note", 3, 0),
	("Certificate of Origin", 1, 2),
	("Insurance Certificate", 1, 1),
	("Bill of Exchange (Draft)", 1, 0),
)


def check_usance_limit(firm_type, drafts_at, usance_days):
	cap = cint(frappe.db.get_single_value("LC Settings", "trading_usance_cap_days"))
	if drafts_at == "Usance" and firm_type == "Trading" and cap and cint(usance_days) > cap:
		frappe.throw(
			_("A trading firm's usance LC may not exceed {0} days (NRB). This LC asks for {1}.").format(cap, usance_days),
			title=_("Usance too long"),
		)


class LetterofCredit(Document):
	# The JEs this LC posts link back to it; they are cancelled in on_cancel,
	# so Frappe's back-link check must not refuse the cancel first.
	ignore_linked_doctypes = ("Journal Entry", "GL Entry", "Payment Ledger Entry", "Landed Cost Voucher")

	def autoname(self):
		# NGI-LC-83/84-00001: same company + BS fiscal year shape as the rest of the app.
		self.name = make_name_with_fiscal_year("LC", self, sequence_length=5)

	def validate(self):
		self.set_missing_values()
		self.validate_terms()
		self.validate_purchase_orders()
		if self.docstatus == 0:
			self.status = "Draft"

	def company_row(self):
		return next(
			(r for r in frappe.get_cached_doc("LC Settings").company_accounts if r.company == self.company),
			None,
		)

	def set_missing_values(self):
		self.company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		if self.supplier and not self.supplier_name:
			self.supplier_name = frappe.db.get_value("Supplier", self.supplier, "supplier_name")
		if self.bank_account:
			self.bank, self.bank_gl_account = frappe.db.get_value("Bank Account", self.bank_account, ["bank", "account"])
		row = self.company_row()
		self.firm_type = (row.firm_type if row else None) or "Industry"
		if not flt(self.margin_percent):
			self.margin_percent = self.default_margin_percent()
		self.required_margin = flt(flt(self.lc_amount) * self.rate_to_company() * flt(self.margin_percent) / 100, 2)
		if not self.documents:
			for document, originals, copies in DEFAULT_DOCUMENTS:
				self.append("documents", {"document": document, "originals": originals, "copies": copies})
		if not self.presentation_days:
			self.presentation_days = 21

	def default_margin_percent(self):
		settings = frappe.get_cached_doc("LC Settings")
		key = "margin_" + ("trading" if self.firm_type == "Trading" else "industry")
		if cint(self.e_payment_customs):
			key += "_epay"
		return flt(settings.get(key))

	def rate_to_company(self, to_currency=None):
		"""Today's rate from the LC currency (0 when ERPNext has none)."""
		from erpnext.setup.utils import get_exchange_rate

		to_currency = to_currency or self.company_currency
		if not self.currency or self.currency == to_currency:
			return 1
		return flt(get_exchange_rate(self.currency, to_currency, self.posting_date))

	def validate_terms(self):
		if flt(self.lc_amount) <= 0:
			frappe.throw(_("LC Amount must be more than zero."))
		if self.currency == self.company_currency:
			frappe.throw(_("An import LC is in the supplier's currency, not {0}.").format(self.company_currency))
		for field in ("tolerance_plus", "tolerance_minus"):
			if not 0 <= flt(self.get(field)) <= 100:
				frappe.throw(_("{0} must be between 0 and 100.").format(self.meta.get_label(field)))
		if getdate(self.latest_shipment_date) > getdate(self.expiry_date):
			frappe.throw(_("The latest shipment date cannot be after the expiry date."))
		if getdate(self.expiry_date) < getdate(self.posting_date):
			frappe.throw(_("The expiry date cannot be before the application date."))
		if self.drafts_at == "Usance" and cint(self.usance_days) <= 0:
			frappe.throw(_("Give the usance period in days."))
		if self.drafts_at == "Sight":
			self.usance_days = 0
		check_usance_limit(self.firm_type, self.drafts_at, self.usance_days)
		if self.bank_account:
			company, is_company_account = frappe.db.get_value(
				"Bank Account", self.bank_account, ["company", "is_company_account"])
			if company != self.company or not is_company_account:
				frappe.throw(_("{0} is not a bank account of {1}.").format(self.bank_account, self.company))

	def validate_purchase_orders(self):
		seen = set()
		for row in self.purchase_orders:
			if row.purchase_order in seen:
				frappe.throw(_("Row {0}: {1} is listed twice.").format(row.idx, row.purchase_order))
			seen.add(row.purchase_order)
			po = frappe.db.get_value("Purchase Order", row.purchase_order,
				["docstatus", "company", "supplier", "currency", "transaction_date", "grand_total"], as_dict=True)
			if not po or po.docstatus != 1:
				frappe.throw(_("Row {0}: {1} is not a submitted Purchase Order.").format(row.idx, row.purchase_order))
			if po.company != self.company or po.supplier != self.supplier:
				frappe.throw(_("Row {0}: {1} is not an order on {2} in {3}.").format(
					row.idx, row.purchase_order, self.supplier, self.company))
			if po.currency != self.currency:
				frappe.throw(_("Row {0}: {1} is in {2}; the LC is in {3}.").format(
					row.idx, row.purchase_order, po.currency, self.currency))
			row.transaction_date = po.transaction_date
			row.grand_total = po.grand_total
			if not flt(row.amount):
				row.amount = po.grand_total

	def validate_bci(self):
		"""NRB: a sight LC at or above the threshold needs a fresh BCI report on the beneficiary."""
		settings = frappe.get_cached_doc("LC Settings")
		threshold = flt(settings.bci_threshold_usd)
		if self.drafts_at != "Sight" or not threshold:
			return
		rate = 1 if self.currency == "USD" else self.rate_to_company("USD")
		if not rate:
			frappe.msgprint(
				_("No {0} → USD exchange rate on record, so the BCI threshold was not checked.").format(self.currency),
				indicator="orange", alert=True,
			)
			return
		if flt(self.lc_amount) * rate < threshold:
			return
		if not self.bci_reference or not self.bci_date:
			frappe.throw(
				_("A sight LC of USD {0} or more needs a BCI report on the beneficiary (NRB). Fill BCI Report Reference and Date.").format(
					frappe.format_value(threshold, {"fieldtype": "Float", "precision": 0})),
				title=_("BCI report needed"),
			)
		validity = cint(settings.bci_validity_days)
		if validity and date_diff(self.posting_date, self.bci_date) > validity:
			frappe.throw(_("The BCI report is dated {0}: more than {1} days old.").format(
				frappe.format(self.bci_date, "Date"), validity), title=_("BCI report too old"))

	def before_submit(self):
		if not self.bank_account:
			frappe.throw(_("Choose the Issuing Bank Account."))
		if not self.customs_point:
			frappe.throw(_("Name the Nepal customs point (NRB requires it in the LC)."))
		self.validate_bci()
		accounting.get_company_accounts(self.company)
		self.validate_supplier_account()

	def validate_supplier_account(self):
		from erpnext.accounts.party import get_party_account

		account = get_party_account("Supplier", self.supplier, self.company)
		currency = frappe.get_cached_value("Account", account, "account_currency")
		if currency not in (self.company_currency, self.currency):
			frappe.throw(_("Supplier account {0} is in {1}; it must be in {2} or {3}.").format(
				account, currency, self.company_currency, self.currency))

	def on_submit(self):
		self.status = "Applied"
		lifecycle.record_event(self, "Applied", self.posting_date, {"status": "Applied"},
			remarks=_("Application to {0}").format(self.bank or self.bank_account))

	def before_cancel(self):
		later = [e.event for e in self.events if e.event != "Applied"]
		if self.status != "Applied" or later:
			frappe.throw(
				_("{0} is {1} and has later steps ({2}). Undo them first (Undo Last Step), then cancel.").format(
					self.name, _(self.status), ", ".join(later) or "—"),
				title=_("Cannot cancel"),
			)

	def on_cancel(self):
		for row in self.events:
			accounting.cancel_journal_entry(row.journal_entry)
		self.db_set("status", "Cancelled")
