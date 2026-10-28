"""PDC Cheque — one post-dated cheque, received from a customer or issued to a supplier.

Submitting the cheque books it into the holding account (Cheques in Hand /
Cheques Issued) against the invoices it pays; it does not touch the bank. Every
later step — deposit, clear, bounce, re-deposit, return, replace — is a button
on the submitted form that runs `pdc/lifecycle.py` and adds a History row.

A cheque entered straight into a Payment Entry gets a record too, made by
`pdc/payment_entry_bounce.py` when it bounces: it starts Cleared, its opening
History row points at the Payment Entry, and it posts no entry of its own.

Cancel is only for a cheque that has not moved yet (In Hand / Issued): once it
has been deposited or bounced, its later entries are real bank events, so they
are undone one at a time with Undo Last Step, newest first.

Deliberately thin: field defaults and validation here; posting in
`pdc/accounting.py`, steps in `pdc/lifecycle.py`.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from avinashgroup_app.custom_code.Override.naming_series import make_name_with_fiscal_year
from avinashgroup_app.pdc import accounting, lifecycle, notifications

INVOICE_FOR_PARTY = {"Customer": "Sales Invoice", "Supplier": "Purchase Invoice"}


class PDCCheque(Document):
	# The JEs this cheque posts link back to it; they are cancelled in on_cancel,
	# so Frappe's back-link check must not refuse the cancel first.
	ignore_linked_doctypes = ("Journal Entry", "GL Entry", "Payment Ledger Entry")

	def autoname(self):
		# NGI-PDC-82/83-00001: same company + BS fiscal year shape as the rest of the app.
		self.name = make_name_with_fiscal_year("PDC", self, sequence_length=5)

	def validate(self):
		self.set_missing_values()
		self.validate_party()
		self.validate_references()
		self.validate_duplicate()
		if self.docstatus == 0:
			self.status = "Draft"

	def set_missing_values(self):
		from erpnext.accounts.party import get_party_account

		if not self.party_type:
			self.party_type = "Customer" if self.cheque_type == "Received" else "Supplier"
		if self.party and not self.party_name:
			title_field = frappe.get_meta(self.party_type).get_title_field()
			self.party_name = frappe.db.get_value(self.party_type, self.party, title_field) or self.party
		if self.party and not self.party_account:
			self.party_account = get_party_account(self.party_type, self.party, self.company)
		if self.party and not self.mobile_no:
			self.mobile_no = notifications.party_mobile(self.party_type, self.party)
		if not self.cost_center:
			self.cost_center = frappe.get_cached_value("Company", self.company, "cost_center")
		self.currency = frappe.get_cached_value("Company", self.company, "default_currency")

	def validate_party(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be more than zero."))
		if self.cheque_type == "Issued" and not self.bank_account:
			frappe.throw(_("Choose the Company Bank Account the cheque is written on."))

		company, currency, account_type = frappe.get_cached_value(
			"Account", self.party_account, ["company", "account_currency", "account_type"]
		)
		if company != self.company:
			frappe.throw(_("Party Account {0} does not belong to {1}.").format(self.party_account, self.company))
		if account_type not in ("Receivable", "Payable"):
			frappe.throw(_("Party Account {0} is not a receivable or payable account.").format(self.party_account))
		if currency and currency != self.currency:
			frappe.throw(
				_("Party Account {0} is in {1}. PDC Cheque works in company currency only.").format(
					self.party_account, currency
				)
			)

	def validate_references(self):
		expected = INVOICE_FOR_PARTY.get(self.party_type)
		party_field = "customer" if expected == "Sales Invoice" else "supplier"
		seen = set()
		total = 0.0
		for ref in self.references:
			if ref.reference_doctype != expected:
				frappe.throw(_("Row {0}: a {1} cheque can only settle a {2}.").format(ref.idx, self.party_type, expected))
			if ref.reference_name in seen:
				frappe.throw(_("Row {0}: {1} is listed twice.").format(ref.idx, ref.reference_name))
			seen.add(ref.reference_name)

			inv = frappe.db.get_value(
				ref.reference_doctype, ref.reference_name,
				["docstatus", "company", party_field, "outstanding_amount", "grand_total", "due_date",
					"debit_to" if expected == "Sales Invoice" else "credit_to"],
				as_dict=True,
			)
			if not inv or inv.docstatus != 1:
				frappe.throw(_("Row {0}: {1} is not a submitted invoice.").format(ref.idx, ref.reference_name))
			if inv.company != self.company or inv.get(party_field) != self.party:
				frappe.throw(_("Row {0}: {1} is not an invoice of {2} in {3}.").format(
					ref.idx, ref.reference_name, self.party, self.company))
			ref.outstanding_amount = inv.outstanding_amount
			ref.grand_total = inv.grand_total
			ref.due_date = inv.due_date
			ref.account = inv.get("debit_to") or inv.get("credit_to")
			if ref.account != self.party_account:
				frappe.throw(_("Row {0}: {1} is booked to {2}, not the cheque's party account {3}.").format(
					ref.idx, ref.reference_name, ref.account, self.party_account))
			if flt(ref.allocated_amount) <= 0:
				frappe.throw(_("Row {0}: allocated amount must be more than zero.").format(ref.idx))
			# A Payment Entry's invoices are already paid by it; nothing to check.
			if self.docstatus == 0 and not self.payment_entry and flt(ref.allocated_amount) > flt(inv.outstanding_amount) + 0.005:
				frappe.throw(_("Row {0}: {1} has only {2} outstanding.").format(
					ref.idx, ref.reference_name, frappe.format_value(inv.outstanding_amount, {"fieldtype": "Currency"})))
			total += flt(ref.allocated_amount)

		self.total_allocated = total
		self.unallocated_amount = flt(self.amount) - total
		if self.unallocated_amount < -0.005:
			frappe.throw(_("Invoices are allocated {0} more than the cheque amount.").format(
				frappe.format_value(-self.unallocated_amount, {"fieldtype": "Currency"})))
		if self.unallocated_amount > 0.005 and not frappe.db.get_single_value("PDC Settings", "allow_on_account"):
			frappe.throw(_("Allocate the full cheque amount to invoices; advances are switched off in PDC Settings."))

	def validate_duplicate(self):
		if self.payment_entry or not frappe.db.get_single_value("PDC Settings", "block_duplicate_cheque"):
			return
		filters = {
			"cheque_no": self.cheque_no, "party": self.party, "cheque_type": self.cheque_type,
			"docstatus": 1, "name": ["!=", self.name],
			"status": ["not in", ["Cancelled"]],
		}
		if self.bank_name:
			filters["bank_name"] = self.bank_name
		existing = frappe.db.get_value("PDC Cheque", filters, "name")
		if existing:
			frappe.throw(_("Cheque {0} of {1} is already entered as {2}.").format(
				self.cheque_no, self.party_name or self.party, existing), title=_("Duplicate cheque"))

	def before_submit(self):
		if self.payment_entry:
			return
		# Two cheques for the same invoice submitted together must not both pass
		# the outstanding check: lock the invoices, then check again.
		for ref in self.references:
			outstanding = frappe.db.get_value(
				ref.reference_doctype, ref.reference_name, "outstanding_amount", for_update=True
			)
			if flt(ref.allocated_amount) > flt(outstanding) + 0.005:
				frappe.throw(_("Row {0}: {1} now has only {2} outstanding.").format(
					ref.idx, ref.reference_name, outstanding))
		if self.replacement_of:
			original = frappe.get_doc("PDC Cheque", self.replacement_of)
			if original.status not in ("Bounced", "Returned"):
				frappe.throw(_("{0} is {1}; only a bounced or returned cheque can be replaced.").format(
					original.name, original.status))
		accounting.get_company_accounts(self.company)

	def on_submit(self):
		if self.payment_entry:
			return self.open_from_payment_entry()
		event = "Received" if self.cheque_type == "Received" else "Issued"
		status = "In Hand" if self.cheque_type == "Received" else "Issued"
		je = accounting.post_settlement(self, self.posting_date, _(event))
		self.status = status
		lifecycle.record_event(self, event, self.posting_date, {"status": status}, journal_entry=je,
			account=self.bank_account if self.cheque_type == "Issued" else None)
		if self.replacement_of:
			lifecycle.mark_replaced(frappe.get_doc("PDC Cheque", self.replacement_of), self)
		if self.cheque_type == "Received":
			notifications.send_party_sms(self, "receipt")

	def open_from_payment_entry(self):
		"""The Payment Entry already paid the invoices and hit the bank: start Cleared."""
		pe = frappe.db.get_value("Payment Entry", self.payment_entry,
			["posting_date", "clearance_date"], as_dict=True)
		cleared_on = pe.clearance_date or pe.posting_date
		lifecycle.record_event(
			self, self.cheque_type, pe.posting_date,
			{
				"status": "Cleared", "clearance_date": cleared_on, "deposit_date": pe.posting_date,
				"deposit_account": self.bank_account, "presentation_count": 1,
			},
			payment_entry=self.payment_entry, account=self.bank_account,
			remarks=_("Entered in Payment Entry {0}").format(self.payment_entry),
		)

	def before_cancel(self):
		opening = ("In Hand", "Issued", "Cleared") if self.payment_entry else ("In Hand", "Issued")
		if self.status not in opening or len(self.events) > 1:
			frappe.throw(
				_("Cheque {0} is {1}. Undo its later steps first (Undo Last Step), then cancel.").format(
					self.name, self.status),
				title=_("Cannot cancel"),
			)

	def on_cancel(self):
		for row in self.events:
			accounting.cancel_journal_entry(row.journal_entry)
		self.db_set("status", "Cancelled")
		if self.replacement_of:
			lifecycle.unmark_replaced(frappe.get_doc("PDC Cheque", self.replacement_of), self)
