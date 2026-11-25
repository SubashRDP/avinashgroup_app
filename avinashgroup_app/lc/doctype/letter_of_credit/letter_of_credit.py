"""Letter of Credit — one import LC, kept as its own cost file from opening to stock.

An LC here stands on its own: it is not made from a Purchase Order and settles
no Purchase Invoice. It names the supplier, the currency and amount, the goods
(item group, item, description, qty, rate) and where each line goes when it
arrives (stock or a fixed asset). Submitting it means the bank has opened it
(LC No. needed); the margin the bank took is posted then.

After submit, everything that moves money is a button running
`lc/lifecycle.py` (costs, goods payment / acceptance, maturity, transfer,
close), each adding a History row. The shipment fields (depart date, reach
date, B/L, Pragyapan) and the amendable terms (amount, tolerance, expiry,
maturity) may be edited on the submitted form; the status follows the dates.

Validation here carries the Nepal Rastra Bank rules that bind the terms
(thresholds live in LC Settings, because NRB changes them):
* a sight LC at or above the BCI threshold (USD 50,000) needs a Business
  Credibility Information report on the beneficiary, not older than a year;
* a trading firm's usance may not exceed 180 days.

Cancel is only for an LC with no step after opening: later entries are real
bank events, undone one at a time with Undo Last Step, newest first.

Deliberately thin: posting in `lc/accounting.py`, steps in `lc/lifecycle.py`,
the transfer in `lc/transfer.py`.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, date_diff, flt, getdate

from avinashgroup_app.custom_code.Override.naming_series import make_name_with_fiscal_year
from avinashgroup_app.lc import accounting, lifecycle


def check_usance_limit(firm_type, drafts_at, usance_days):
	cap = cint(frappe.db.get_single_value("LC Settings", "trading_usance_cap_days"))
	if drafts_at == "Usance" and firm_type == "Trading" and cap and cint(usance_days) > cap:
		frappe.throw(
			_("A trading firm's usance LC may not exceed {0} days (NRB). This LC asks for {1}.").format(cap, usance_days),
			title=_("Usance too long"),
		)


class LetterofCredit(Document):
	# The JEs and Stock Entries this LC posts link back to it; they are
	# cancelled by the LC itself, so Frappe's back-link check must not refuse
	# the cancel first.
	ignore_linked_doctypes = ("Journal Entry", "GL Entry", "Payment Ledger Entry", "Stock Entry",
		"Stock Ledger Entry", "Asset")

	def autoname(self):
		# NGI-LC-00001-83/84: same company + BS fiscal year shape as the rest of the app.
		self.name = make_name_with_fiscal_year("LC", self, sequence_length=5)

	def validate(self):
		self.set_missing_values()
		self.validate_terms()
		self.validate_items()
		self.validate_shipment_dates()
		self.prepare_new_costs()
		if self.docstatus == 0:
			self.status = "Draft"

	def before_update_after_submit(self):
		# Frappe skips validate() on Update of a submitted doc: the amendable
		# terms, goods rows and shipment dates are checked here instead. Only
		# allow-on-submit fields may be written.
		self.set_amounts()
		self.validate_terms()
		self.validate_items()
		self.validate_shipment_dates()
		before = self.get_doc_before_save()
		self.flags.removed_costs = lifecycle.check_cost_edits(self, before) if before else []
		self.prepare_new_costs()

	def prepare_new_costs(self):
		"""Cost rows typed into the grid and not posted yet: check and complete them."""
		new = [r for r in self.costs if lifecycle.is_unposted_cost(r)]
		if new and self.status in lifecycle.CLOSED_STATUSES:
			frappe.throw(_("{0} is {1}: no more costs can be added.").format(self.name, _(self.status)))
		for row in new:
			lifecycle.prepare_cost_row(self, row)

	def post_new_costs(self):
		for row in self.costs:
			if lifecycle.is_unposted_cost(row):
				lifecycle.post_cost_row(self, row)

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
		if not flt(self.exchange_rate):
			self.exchange_rate = self.rate_to_company()
		if not flt(self.margin_percent):
			self.margin_percent = self.default_margin_percent()
		if self.items and not flt(self.lc_amount):
			self.lc_amount = sum(flt(i.qty) * flt(i.rate) for i in self.items)
		self.set_amounts()

	def set_amounts(self):
		self.base_lc_amount = flt(flt(self.lc_amount) * flt(self.exchange_rate), 2)
		self.required_margin = flt(self.base_lc_amount * flt(self.margin_percent) / 100, 2)
		if self.drafts_at == "Usance" and not self.maturity_date and self.departure_date and cint(self.usance_days):
			self.maturity_date = add_days(self.departure_date, cint(self.usance_days))

	def default_margin_percent(self):
		settings = frappe.get_cached_doc("LC Settings")
		key = "margin_" + ("trading" if self.firm_type == "Trading" else "industry")
		if cint(self.e_payment_customs):
			key += "_epay"
		return flt(settings.get(key))

	def rate_to_company(self, to_currency=None):
		"""The rate on record from the LC currency (0 when ERPNext has none)."""
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
		if not 0 <= flt(self.tolerance_plus) <= 100:
			frappe.throw(_("Tolerance + % must be between 0 and 100."))
		if self.expiry_date and getdate(self.expiry_date) < getdate(self.posting_date):
			frappe.throw(_("The expiry date cannot be before the open date."))
		if self.latest_shipment_date and self.expiry_date and getdate(self.latest_shipment_date) > getdate(self.expiry_date):
			frappe.throw(_("The latest shipment date cannot be after the expiry date."))
		if self.drafts_at == "Sight":
			self.usance_days = 0
			self.maturity_date = None
		check_usance_limit(self.firm_type, self.drafts_at, self.usance_days)
		if self.bank_account:
			company, is_company_account = frappe.db.get_value(
				"Bank Account", self.bank_account, ["company", "is_company_account"])
			if company != self.company or not is_company_account:
				frappe.throw(_("{0} is not a bank account of {1}.").format(self.bank_account, self.company))
		if self.docstatus == 1:
			booked = sum(flt(c.fc_amount) for c in self.costs if c.cost_group == "Goods")
			if lifecycle.max_amount(self) + 0.005 < booked:
				frappe.throw(_("{0} {1} is already paid or accepted; the LC amount cannot go below it.").format(
					self.currency, flt(booked, 2)))

	def validate_items(self):
		before = self.get_doc_before_save() if self.docstatus == 1 else None
		if before and before.transferred_on:
			# Rows are history once transferred: their cost is in stock or an asset.
			old = [(i.item_code, flt(i.qty), flt(i.rate), i.transfer_to) for i in before.items]
			new = [(i.item_code, flt(i.qty), flt(i.rate), i.transfer_to) for i in self.items]
			if old != new:
				frappe.throw(_("The goods were transferred on {0}; undo the transfer to change them.").format(
					frappe.format(before.transferred_on, "Date")))
		self.total_qty = 0
		total = 0
		for i in self.items:
			i.currency = self.currency
			i.amount = flt(flt(i.qty) * flt(i.rate), 2)
			total += i.amount
			self.total_qty += flt(i.qty)
			if not i.description:
				i.description = i.item_name or i.item_code or i.item_group
			if i.item_code and not i.uom:
				i.uom = frappe.get_cached_value("Item", i.item_code, "stock_uom")
			if i.item_code and not i.item_group:
				i.item_group = frappe.get_cached_value("Item", i.item_code, "item_group")
			if i.transfer_to == "Fixed Asset":
				i.warehouse = None
				if i.item_code and not i.asset_category:
					i.asset_category = frappe.get_cached_value("Item", i.item_code, "asset_category")
		self.items_total = flt(total, 2)
		if self.items_total and abs(self.items_total - flt(self.lc_amount)) > 0.005:
			frappe.msgprint(
				_("The goods total {0} {1} differs from the LC amount {0} {2}.").format(
					self.currency, self.items_total, flt(self.lc_amount, 2)),
				indicator="orange", alert=True,
			)

	def validate_shipment_dates(self):
		if self.departure_date and getdate(self.departure_date) < getdate(self.posting_date):
			frappe.throw(_("The goods cannot depart before the LC was opened."))
		if self.arrival_date and not self.departure_date:
			frappe.throw(_("Fill the Depart Date before the Reach Date."))
		if self.arrival_date and getdate(self.arrival_date) < getdate(self.departure_date):
			frappe.throw(_("The Reach Date cannot be before the Depart Date."))
		if self.latest_shipment_date and self.departure_date and getdate(self.departure_date) > getdate(self.latest_shipment_date):
			frappe.msgprint(_("The goods departed after the latest shipment date: the bank will call it a discrepancy unless the LC was amended."),
				indicator="orange", alert=True)
		before = self.get_doc_before_save() if self.docstatus == 1 else None
		if before and before.transferred_on and not self.arrival_date:
			frappe.throw(_("The goods are transferred; the Reach Date cannot be cleared."))

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
		if not self.lc_no:
			frappe.throw(_("Give the LC No. the bank issued."))
		if not self.bank_account:
			frappe.throw(_("Choose the Issuing Bank Account."))
		duplicate = frappe.db.get_value(
			"Letter of Credit", {"lc_no": self.lc_no, "bank": self.bank, "docstatus": 1, "name": ["!=", self.name]}, "name")
		if duplicate:
			frappe.throw(_("LC No. {0} of this bank is already recorded as {1}.").format(self.lc_no, duplicate))
		if flt(self.margin_amount) < 0:
			frappe.throw(_("The margin cannot be negative."))
		self.validate_bci()
		accounting.get_company_accounts(self.company)

	def on_submit(self):
		je = None
		values = {"status": "Open"}
		if flt(self.margin_amount) > 0:
			je = accounting.post_margin(self, self.posting_date, flt(self.margin_amount, 2), self.bank_gl_account)
			values["margin_deposited"] = flt(self.margin_amount, 2)
		lifecycle.record_event(self, "Opened", self.posting_date, values, journal_entry=je,
			amount=flt(self.margin_amount) or None, remarks=_("LC No. {0}, {1}").format(self.lc_no, self.bank or ""))
		# Costs typed into the draft (the opening commission, say) post now.
		self.post_new_costs()

	def on_update_after_submit(self):
		for old in self.flags.removed_costs or []:
			lifecycle.remove_cost_row(self, old)
		self.post_new_costs()
		# Costs, dates (depart / reach) or amended terms changed: recompute totals and status.
		lifecycle.refresh_position(self)

	def before_cancel(self):
		later = [e.event for e in self.events if e.event != "Opened"]
		if later:
			frappe.throw(
				_("{0} has later steps ({1}). Undo them first (Undo Last Step), then cancel.").format(
					self.name, ", ".join(later)),
				title=_("Cannot cancel"),
			)

	def on_cancel(self):
		for row in self.events:
			accounting.cancel_journal_entry(row.journal_entry)
		self.db_set("status", "Cancelled")
