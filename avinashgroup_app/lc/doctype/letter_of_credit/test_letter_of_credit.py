"""Letter of Credit tests: the lifecycle, its entries, and every guard.

They run against an existing company (Grihalaxmi, which has an Exchange
Gain/Loss account and company bank accounts) and copy one of its submitted
stock-updating Purchase Invoices into a USD invoice for a throw-away supplier,
so the settlement has a real invoice at a booked rate to clear. Everything is
rolled back. Runner: docs/lc-management.md §Tests (`bench run-tests` fails at
bootstrap on the dev bench).
"""

import unittest

import frappe
from frappe.utils import add_days, flt, nowdate

from avinashgroup_app.lc import accounting, lifecycle
from avinashgroup_app.lc.install import ensure_company_accounts

COMPANY = "Grihalaxmi Metal Industries Pvt. Ltd"
BOOKED_RATE = 133.0  # the Purchase Invoice's conversion rate
BANK_RATE = 135.0    # the bank's settlement rate: a loss of 2 per USD


def _gl(voucher, account):
	return flt(frappe.db.sql(
		"select sum(debit) - sum(credit) from `tabGL Entry` where voucher_no = %s and account = %s and is_cancelled = 0",
		(voucher, account),
	)[0][0])


class TestLetterOfCredit(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		frappe.db.savepoint("lc_class")
		ensure_company_accounts([COMPANY])
		frappe.db.set_single_value("LC Settings", "jv_type", "Bank Entry")
		frappe.clear_document_cache("LC Settings", "LC Settings")
		cls.accounts = accounting.get_company_accounts(COMPANY)
		cls.bank_account = frappe.get_all(
			"Bank Account", filters={"company": COMPANY, "is_company_account": 1, "account": ["is", "set"]},
			pluck="name", limit=1)[0]
		cls.bank_gl = frappe.db.get_value("Bank Account", cls.bank_account, "account")
		cls.supplier = cls.make_supplier()
		cls.invoice = cls.make_usd_invoice(cls.supplier, 10000)

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback(save_point="lc_class")

	def setUp(self):
		frappe.db.savepoint("lc_test")

	def tearDown(self):
		frappe.db.rollback(save_point="lc_test")
		frappe.clear_document_cache("LC Settings", "LC Settings")

	# ── fixtures ──────────────────────────────────────────────────────────────

	@classmethod
	def make_supplier(cls):
		# Supplier Groups are company-scoped here: borrow one a company supplier uses.
		group = frappe.db.get_value("Supplier", {"custom_company": COMPANY}, "supplier_group")
		doc = frappe.get_doc({
			"doctype": "Supplier", "supplier_name": "LC Test Steel Exporter", "supplier_group": group,
			"default_currency": "USD", "country": "India",
			"custom_company": COMPANY,  # the app's Supplier naming needs a company
		})
		# ERPNext wants a USD invoice booked to a USD payable: give the supplier one.
		usd = cls.make_usd_payable()
		doc.append("accounts", {"company": COMPANY, "account": usd, "advance_account": usd})
		doc.insert(ignore_permissions=True)
		return doc.name

	@classmethod
	def make_usd_payable(cls):
		name = frappe.db.get_value("Account", {"company": COMPANY, "account_name": "LC Test Creditors USD"}, "name")
		if name:
			return name
		parent = frappe.db.get_value("Account", frappe.db.get_value(
			"Account", {"company": COMPANY, "account_type": "Payable", "is_group": 0, "account_currency": "NPR"},
			"name"), "parent_account")
		account = frappe.get_doc({
			"doctype": "Account", "company": COMPANY, "account_name": "LC Test Creditors USD",
			"parent_account": parent, "account_type": "Payable", "account_currency": "USD", "is_group": 0,
		})
		account.insert(ignore_permissions=True)
		return account.name

	@classmethod
	def make_usd_invoice(cls, supplier, usd):
		template = frappe.get_all(
			"Purchase Invoice", filters={"company": COMPANY, "docstatus": 1, "update_stock": 1, "is_return": 0},
			pluck="name", limit=1, order_by="creation desc")[0]
		pi = frappe.copy_doc(frappe.get_doc("Purchase Invoice", template))
		pi.supplier = supplier
		pi.supplier_name = "LC Test Steel Exporter"
		pi.currency = "USD"
		pi.conversion_rate = BOOKED_RATE
		pi.posting_date = nowdate()
		pi.set_posting_time = 1
		pi.bill_no = "LC-TEST-INV"
		# Addresses, contacts and price list belong to the template's supplier.
		for field in ("supplier_address", "address_display", "contact_person", "contact_display",
				"contact_mobile", "contact_email", "shipping_address", "shipping_address_display",
				"buying_price_list", "price_list_currency", "plc_conversion_rate"):
			if pi.meta.has_field(field):
				pi.set(field, None)
		pi.plc_conversion_rate = 1
		# The copy carries the template's voucher numbers; Purchase Invoices on the
		# test site are numbered by hand, so give it a fresh one.
		for field in ("custom_name", "custom_fact_numbering"):
			if pi.meta.has_field(field):
				pi.set(field, None)
		if pi.meta.has_field("custom_document_no"):
			pi.custom_document_no = str(900000000 + int(frappe.generate_hash(length=5), 16))
		pi.taxes = []
		pi.taxes_and_charges = None
		pi.items = pi.items[:1]
		row = pi.items[0]
		row.qty = 1
		row.received_qty = 1
		row.rate = usd
		row.price_list_rate = usd
		row.discount_percentage = 0
		row.purchase_order = row.po_detail = row.purchase_receipt = row.pr_detail = None
		pi.credit_to = None
		pi.payment_schedule = []
		pi.flags.ignore_permissions = True
		pi.insert()
		# The app may already submit a Purchase Invoice on insert; submit only if not.
		pi = frappe.get_doc("Purchase Invoice", pi.name)
		if pi.docstatus == 0:
			pi.flags.ignore_permissions = True
			pi.submit()
		return pi.name

	def make_lc(self, submit=True, **kw):
		lc = frappe.new_doc("Letter of Credit")
		lc.update({
			"company": COMPANY, "supplier": self.supplier, "currency": "USD", "lc_amount": 10000,
			"tolerance_plus": 5, "tolerance_minus": 5, "drafts_at": "Sight",
			"expiry_date": add_days(nowdate(), 90), "latest_shipment_date": add_days(nowdate(), 60),
			"customs_point": "Birgunj", "bank_account": self.bank_account,
			"bci_reference": "BCI-TEST-1", "bci_date": nowdate(),
		})
		lc.update(kw)
		lc.insert()
		if submit:
			lc.submit()
		return lc

	def act(self, lc, action, **kw):
		lifecycle.ACTIONS[action](frappe.get_doc("Letter of Credit", lc.name), **kw)
		return frappe.get_doc("Letter of Credit", lc.name)

	def opened(self, margin=200000, **kw):
		lc = self.make_lc(**kw)
		return self.act(lc, "open", lc_no="LC-001-TEST", issue_date=nowdate(), margin=margin)

	# ── tests ─────────────────────────────────────────────────────────────────

	def test_sight_lc_end_to_end(self):
		lc = self.make_lc()
		self.assertEqual(lc.status, "Applied")
		self.assertTrue(lc.documents, "default document checklist")
		self.assertEqual(lc.firm_type, "Industry")

		lc = self.act(lc, "add_charge", charge_type="LC Opening Commission", amount=5000)
		lc = self.act(lc, "open", lc_no="LC-001-TEST", issue_date=nowdate(), margin=200000)
		self.assertEqual(lc.status, "Opened")
		self.assertEqual(flt(lc.margin_balance), 200000)
		opened_je = lc.events[-1].journal_entry
		self.assertEqual(_gl(opened_je, self.accounts.margin_account), 200000)
		self.assertEqual(_gl(opened_je, self.bank_gl), -200000)

		lc = self.act(lc, "add_shipment", transport_doc_no="BL-1", transport_doc_date=nowdate(), amount=10000,
			purchase_invoice=self.invoice)
		self.assertEqual(flt(lc.available_amount), 500)
		lc = self.act(lc, "docs_received", shipment_no=1, posting_date=nowdate())
		lc = self.act(lc, "settle", shipment_no=1, posting_date=nowdate(), exchange_rate=BANK_RATE)

		s = lc.shipments[0]
		self.assertEqual(s.status, "Settled")
		self.assertEqual(flt(s.amount_npr), 1350000)
		self.assertEqual(flt(s.margin_applied), 200000, "last drawing uses all the margin")
		self.assertEqual(flt(s.exchange_difference), 20000)
		self.assertEqual(lc.status, "Settled")
		je = s.settlement_journal_entry
		gain_loss = frappe.get_cached_value("Company", COMPANY, "exchange_gain_loss_account")
		self.assertEqual(_gl(je, gain_loss), 20000)
		self.assertEqual(_gl(je, self.accounts.margin_account), -200000)
		self.assertEqual(_gl(je, self.bank_gl), -1150000)
		self.assertAlmostEqual(flt(frappe.db.get_value("Purchase Invoice", self.invoice, "outstanding_amount")), 0, 2)

		lc = self.act(lc, "customs_proof", shipment_no=1, customs_declaration_no="PRG-77", customs_date=nowdate())
		self.assertTrue(lc.shipments[0].customs_proof_submitted_on)
		lc = self.act(lc, "close", posting_date=nowdate())
		self.assertEqual(lc.status, "Closed")
		self.assertEqual(flt(lc.margin_balance), 0)

	def test_close_releases_unused_margin(self):
		lc = self.opened(partial_shipment="Allowed")
		lc = self.act(lc, "close", posting_date=nowdate())
		self.assertEqual(flt(lc.margin_released), 200000)
		je = lc.events[-1].journal_entry
		self.assertEqual(_gl(je, self.bank_gl), 200000)

	def test_settlement_without_invoice_is_an_advance(self):
		lc = self.opened()
		lc = self.act(lc, "add_shipment", transport_doc_no="BL-2", transport_doc_date=nowdate(), amount=4000)
		lc = self.act(lc, "docs_received", shipment_no=1)
		lc = self.act(lc, "settle", shipment_no=1, exchange_rate=BANK_RATE, margin_applied=0)
		s = lc.shipments[0]
		self.assertEqual(flt(s.exchange_difference), 0)
		self.assertEqual(lc.status, "Partly Settled")
		row = frappe.db.get_value("Journal Entry Account",
			{"parent": s.settlement_journal_entry, "party": self.supplier}, ["is_advance", "debit"], as_dict=True)
		self.assertEqual(row.is_advance, "Yes")
		self.assertEqual(flt(row.debit), 540000)

	def test_usance_accept_sets_maturity(self):
		lc = self.opened(drafts_at="Usance", usance_days=90, usance_basis="B/L Date")
		lc = self.act(lc, "add_shipment", transport_doc_no="BL-3", transport_doc_date=nowdate(), amount=10000)
		lc = self.act(lc, "docs_received", shipment_no=1)
		with self.assertRaises(frappe.ValidationError):
			self.act(lc, "settle", shipment_no=1, exchange_rate=BANK_RATE)  # not accepted yet
		lc = self.act(lc, "accept", shipment_no=1)
		self.assertEqual(str(lc.shipments[0].maturity_date), str(add_days(nowdate(), 90)))

	def test_trading_usance_limit(self):
		row = next(r for r in frappe.get_doc("LC Settings").company_accounts if r.company == COMPANY)
		frappe.db.set_value("LC Company Account", row.name, "firm_type", "Trading")
		frappe.clear_document_cache("LC Settings", "LC Settings")
		with self.assertRaises(frappe.ValidationError):
			self.make_lc(submit=False, drafts_at="Usance", usance_days=200)
		lc = self.make_lc(submit=False, drafts_at="Usance", usance_days=180)
		self.assertEqual(lc.margin_percent, 10)

	def test_bci_required_for_large_sight_lc(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_lc(lc_amount=60000, bci_reference=None, bci_date=None)
		with self.assertRaises(frappe.ValidationError):
			self.make_lc(lc_amount=60000, bci_date=add_days(nowdate(), -400))
		# Below the threshold, and usance at any amount, need no BCI report.
		self.make_lc(lc_amount=40000, bci_reference=None, bci_date=None)
		self.make_lc(lc_amount=60000, bci_reference=None, bci_date=None, drafts_at="Usance", usance_days=60)

	def test_tolerance_and_dates_guard_shipments(self):
		lc = self.opened()
		with self.assertRaises(frappe.ValidationError):
			self.act(lc, "add_shipment", transport_doc_no="BL", transport_doc_date=nowdate(), amount=10600)
		with self.assertRaises(frappe.ValidationError):
			self.act(lc, "add_shipment", transport_doc_no="BL", transport_doc_date=add_days(nowdate(), 61), amount=100)
		lc = self.act(lc, "add_shipment", transport_doc_no="BL", transport_doc_date=nowdate(), amount=10500)
		self.assertEqual(flt(lc.available_amount), 0)

	def test_partial_shipment_not_allowed(self):
		lc = self.opened(partial_shipment="Not Allowed")
		with self.assertRaises(frappe.ValidationError):
			self.act(lc, "add_shipment", transport_doc_no="BL", transport_doc_date=nowdate(), amount=5000)

	def test_amendment_and_undo(self):
		lc = self.opened()
		new_expiry = str(add_days(nowdate(), 120))
		lc = self.act(lc, "amend", changes={"lc_amount": 12000, "expiry_date": new_expiry}, charge=1500)
		self.assertEqual(flt(lc.lc_amount), 12000)
		self.assertEqual(len(lc.amendments), 2)
		self.assertEqual(flt(lc.charges_total), 1500)
		charge_je = lc.events[-1].journal_entry

		lifecycle.undo_last_step(frappe.get_doc("Letter of Credit", lc.name))
		lc = frappe.get_doc("Letter of Credit", lc.name)
		self.assertEqual(flt(lc.lc_amount), 10000)
		self.assertFalse(lc.amendments)
		self.assertFalse(lc.charges)
		self.assertEqual(frappe.db.get_value("Journal Entry", charge_je, "docstatus"), 2)

	def test_undo_settlement_restores_shipment(self):
		lc = self.opened()
		lc = self.act(lc, "add_shipment", transport_doc_no="BL", transport_doc_date=nowdate(), amount=10000,
			purchase_invoice=self.invoice)
		lc = self.act(lc, "docs_received", shipment_no=1)
		lc = self.act(lc, "settle", shipment_no=1, exchange_rate=BANK_RATE)
		je = lc.shipments[0].settlement_journal_entry
		lifecycle.undo_last_step(frappe.get_doc("Letter of Credit", lc.name))
		lc = frappe.get_doc("Letter of Credit", lc.name)
		self.assertEqual(lc.shipments[0].status, "Docs Received")
		self.assertFalse(lc.shipments[0].settlement_journal_entry)
		self.assertEqual(lc.status, "Opened")
		self.assertEqual(flt(lc.margin_balance), 200000)
		self.assertEqual(frappe.db.get_value("Journal Entry", je, "docstatus"), 2)
		self.assertAlmostEqual(flt(frappe.db.get_value("Purchase Invoice", self.invoice, "outstanding_amount")), 10000, 2)

	def test_guards_on_linked_documents(self):
		lc = self.opened()
		lc = self.act(lc, "add_shipment", transport_doc_no="BL", transport_doc_date=nowdate(), amount=10000,
			purchase_invoice=self.invoice)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Purchase Invoice", self.invoice).cancel()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Journal Entry", lc.events[1].journal_entry).cancel()
		other = self.make_lc()
		other = self.act(other, "open", lc_no="LC-002-TEST", margin=0)
		with self.assertRaises(frappe.ValidationError):
			self.act(other, "add_shipment", transport_doc_no="BL", transport_doc_date=nowdate(), amount=100,
				purchase_invoice=self.invoice)

	def test_cancel_only_before_later_steps(self):
		lc = self.make_lc()
		lc = self.act(lc, "add_charge", amount=100)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Letter of Credit", lc.name).cancel()
		lifecycle.undo_last_step(frappe.get_doc("Letter of Credit", lc.name))
		lc = frappe.get_doc("Letter of Credit", lc.name)
		lc.cancel()
		self.assertEqual(frappe.db.get_value("Letter of Credit", lc.name, "status"), "Cancelled")

	def test_landed_cost_voucher_takes_pending_charges(self):
		lc = self.opened()
		lc = self.act(lc, "add_charge", charge_type="SWIFT Charge", amount=1500)
		lc = self.act(lc, "add_shipment", transport_doc_no="BL", transport_doc_date=nowdate(), amount=10000,
			purchase_invoice=self.invoice)
		out = accounting.make_landed_cost_voucher(lc.name)
		self.assertEqual(out["letter_of_credit"], lc.name)
		self.assertEqual(flt(out["taxes"][0]["amount"]), 1500)
		self.assertEqual(out["purchase_receipts"][0]["receipt_document"], self.invoice)
		self.assertTrue(out["items"])

	def test_make_from_purchase_order_and_hint(self):
		hint = lifecycle.purchase_order_hint("does-not-exist")
		self.assertIsNone(hint)

	def test_reports_digest_and_print(self):
		from avinashgroup_app.lc import notifications
		from avinashgroup_app.lc.report.lc_cost_sheet import lc_cost_sheet
		from avinashgroup_app.lc.report.lc_margin_and_charges import lc_margin_and_charges
		from avinashgroup_app.lc.report.lc_maturity import lc_maturity
		from avinashgroup_app.lc.report.lc_register import lc_register

		lc = self.opened(drafts_at="Usance", usance_days=5, latest_shipment_date=add_days(nowdate(), 3))
		lc = self.act(lc, "add_charge", amount=2500)
		lc = self.act(lc, "add_shipment", transport_doc_no="BL-R", transport_doc_date=nowdate(), amount=6000)
		lc = self.act(lc, "docs_received", shipment_no=1)
		lc = self.act(lc, "accept", shipment_no=1)

		_cols, rows = lc_register.execute({"company": COMPANY})
		self.assertIn(lc.name, [r.name for r in rows])
		_cols, rows = lc_maturity.execute({"company": COMPANY})
		self.assertEqual([r.days for r in rows if r.name == lc.name], [5])
		_cols, rows = lc_margin_and_charges.execute({"company": COMPANY})
		self.assertTrue(any(flt(r.pending) >= 2500 for r in rows))
		_cols, rows = lc_cost_sheet.execute({"letter_of_credit": lc.name})
		self.assertEqual(flt(rows[0].charges), 2500)

		digest = notifications.digest_rows(days_ahead=15)
		self.assertIn(lc.name, [r.name for r in digest["shipping"]])
		self.assertIn(lc.name, [r.name for r in digest["maturing"]])
		html = frappe.render_template("avinashgroup_app/lc/templates/lc_digest.html",
			{"rows": digest, "today": frappe.utils.getdate(), "days": 15})
		self.assertIn(lc.name, html)
		self.assertIn("LC-001-TEST", frappe.get_print("Letter of Credit", lc.name, print_format="LC Summary"))

