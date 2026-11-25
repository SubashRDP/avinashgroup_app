"""Letter of Credit tests: the cost file, its entries, the transfer, and every guard.

They run against an existing company (Grihalaxmi, which has an Exchange
Gain/Loss account, company bank accounts, warehouses and Asset Categories) with
a throw-away supplier, one stock item and one fixed-asset item. Everything is
rolled back. Runner: docs/lc-management.md §Tests (`bench run-tests` fails at
bootstrap on the dev bench).

The worked example (sight LC, USD 10,000 at 135):
    goods 1,350,000 + commission 5,000 + SWIFT 1,500 + insurance 3,000
    + import duty 40,000 + excise 10,000 + freight 20,000   = 1,429,500 landed
    customs VAT 30,000 + freight VAT 2,600                  =    32,600 VAT, not in cost
    shared by value: steel 8,000 / 10,000 → 1,143,600, machine 2,000 → 285,900
"""

import unittest

import frappe
from frappe.utils import add_days, flt, nowdate

from avinashgroup_app.lc import accounting, lifecycle, transfer
from avinashgroup_app.lc.install import ensure_company_accounts, ensure_cost_types

COMPANY = "Grihalaxmi Metal Industries Pvt. Ltd"
BANK_RATE = 135.0


def _gl(voucher, account):
	return flt(frappe.db.sql(
		"select sum(debit) - sum(credit) from `tabGL Entry` where voucher_no = %s and account = %s and is_cancelled = 0",
		(voucher, account),
	)[0][0])


def _party_balance(supplier):
	return flt(frappe.db.sql(
		"select sum(credit) - sum(debit) from `tabGL Entry` where party_type = 'Supplier' and party = %s and is_cancelled = 0",
		supplier,
	)[0][0])


class TestLetterOfCredit(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		frappe.db.savepoint("lc_class")
		ensure_company_accounts([COMPANY])
		ensure_cost_types()
		frappe.db.set_single_value("LC Settings", "jv_type", "Bank Entry")
		frappe.clear_document_cache("LC Settings", "LC Settings")
		cls.accounts = accounting.get_company_accounts(COMPANY)
		cls.bank_account = frappe.get_all(
			"Bank Account", filters={"company": COMPANY, "is_company_account": 1, "account": ["is", "set"]},
			pluck="name", limit=1)[0]
		cls.bank_gl = frappe.db.get_value("Bank Account", cls.bank_account, "account")
		cls.supplier = cls.make_supplier("LC Test Steel Exporter")
		cls.insurer = cls.make_supplier("LC Test Insurance Co")
		cls.warehouse = frappe.get_all("Warehouse", filters={"company": COMPANY, "is_group": 0}, pluck="name", limit=1)[0]
		cls.category = frappe.get_all("Asset Category Account", filters={"company_name": COMPANY},
			pluck="parent", limit=1)[0]
		cls.asset_account = transfer.fixed_asset_account(cls.category, COMPANY)
		cls.steel = cls.make_item("LC-TEST-STEEL", stock=True)
		cls.machine = cls.make_item("LC-TEST-MACHINE", stock=False)

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
	def make_supplier(cls, name):
		# Supplier Groups are company-scoped here: borrow one a company supplier uses.
		group = frappe.db.get_value("Supplier", {"custom_company": COMPANY}, "supplier_group")
		doc = frappe.get_doc({
			"doctype": "Supplier", "supplier_name": name, "supplier_group": group, "country": "Nepal",
			"custom_company": COMPANY,  # the app's Supplier naming needs a company
		})
		doc.insert(ignore_permissions=True)
		return doc.name

	@classmethod
	def make_item(cls, code, stock):
		# Item Groups are company-scoped too: borrow one of the company's own items.
		group = frappe.db.get_value("Item", {"is_stock_item": 1, "disabled": 0, "custom_company": COMPANY}, "item_group")
		doc = frappe.get_doc({
			"doctype": "Item", "item_code": code, "item_name": code, "item_group": group, "stock_uom": "Nos",
			"is_stock_item": 1 if stock else 0, "is_fixed_asset": 0 if stock else 1,
			"asset_category": None if stock else cls.category,
			"custom_company": COMPANY,  # the app's Item naming needs a company
		})
		doc.insert(ignore_permissions=True)
		return doc.name

	def make_lc(self, submit=True, items=None, **kw):
		lc = frappe.new_doc("Letter of Credit")
		lc.update({
			"company": COMPANY, "supplier": self.supplier, "currency": "USD", "lc_amount": 10000,
			"lc_no": "TEST-LC-" + frappe.generate_hash(length=6), "posting_date": nowdate(),
			"expiry_date": add_days(nowdate(), 120), "drafts_at": "Sight", "exchange_rate": 133,
			"bank_account": self.bank_account, "set_warehouse": self.warehouse,
		})
		for row in items if items is not None else [
			{"item_code": self.steel, "description": "MS plate", "qty": 100, "rate": 80, "transfer_to": "Stock"},
			{"item_code": self.machine, "description": "Press", "qty": 1, "rate": 2000, "transfer_to": "Fixed Asset"},
		]:
			lc.append("items", row)
		lc.update(kw)
		lc.insert(ignore_permissions=True)
		if submit:
			lc.submit()
		return frappe.get_doc("Letter of Credit", lc.name)

	def step(self, lc, action, **kw):
		lifecycle.run_action(lc.name, action, **kw)
		return frappe.get_doc("Letter of Credit", lc.name)

	def arrive(self, lc):
		lc.departure_date = nowdate()
		lc.arrival_date = nowdate()
		lc.save(ignore_permissions=True)
		return frappe.get_doc("Letter of Credit", lc.name)

	def book_example_costs(self, lc):
		for cost_type, amount, vat, via in (
			("LC Commission", 5000, 0, "Bank"),
			("SWIFT Charge", 1500, 0, "Bank"),
			("Marine Insurance", 3000, 0, "Party"),
			("Import Duty (ID)", 40000, 0, "Bank"),
			("Excise Duty (ED)", 10000, 0, "Bank"),
			("Customs VAT", 30000, 0, "Bank"),
			("Freight up to Border", 20000, 2600, "Party"),
		):
			lc = self.step(lc, "add_cost", cost_type=cost_type, amount=amount, vat_amount=vat, paid_via=via,
				party=self.insurer if via == "Party" else None)
		return lc

	# ── the whole run ─────────────────────────────────────────────────────────

	def test_sight_run_to_stock_and_asset(self):
		lc = self.make_lc(margin_amount=50000)
		self.assertEqual(lc.status, "Open")
		self.assertEqual(lc.margin_balance, 50000)
		self.assertEqual(_gl(lc.events[0].journal_entry, self.accounts.margin_account), 50000)

		lc = self.book_example_costs(lc)
		self.assertEqual(lc.bank_charges, 6500)
		self.assertEqual(lc.insurance_cost, 3000)
		self.assertEqual(lc.customs_cost, 50000)
		self.assertEqual(lc.freight_cost, 20000)
		self.assertEqual(lc.vat_total, 32600)
		vat_je = next(c.journal_entry for c in lc.costs if c.cost_type == "Customs VAT")
		self.assertEqual(_gl(vat_je, self.accounts.vat_account), 30000)
		self.assertEqual(_gl(vat_je, self.accounts.transit_account), 0)
		self.assertEqual(_party_balance(self.insurer), 3000 + 22600)

		# The last payment uses all the margin by default.
		lc = self.step(lc, "pay_goods", fc_amount=10000, exchange_rate=BANK_RATE)
		pay = lc.costs[-1]
		self.assertEqual(pay.amount, 1350000)
		self.assertEqual(pay.margin_used, 50000)
		self.assertEqual(_gl(pay.journal_entry, self.bank_gl), -1300000)
		self.assertEqual(lc.margin_balance, 0)
		self.assertEqual(lc.goods_pending_fc, 0)
		self.assertEqual(lc.total_cost, 1429500)
		self.assertEqual(accounting.transit_balance(lc), 1429500)

		lc.departure_date = nowdate()
		lc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Letter of Credit", lc.name, "status"), "In Transit")
		lc = self.arrive(frappe.get_doc("Letter of Credit", lc.name))
		self.assertEqual(lc.status, "Arrived")

		lc = self.step(lc, "transfer")
		self.assertEqual(lc.status, "Transferred")
		steel, machine = lc.items
		self.assertAlmostEqual(steel.allocated_cost, 1143600, places=0)
		self.assertEqual(machine.allocated_cost, 285900)
		self.assertAlmostEqual(steel.landed_rate, 11436, places=2)
		se = frappe.get_doc("Stock Entry", steel.stock_entry)
		self.assertEqual(se.docstatus, 1)
		self.assertEqual(se.letter_of_credit, lc.name)
		self.assertAlmostEqual(se.items[0].valuation_rate, 11436, places=2)
		self.assertEqual(_gl(machine.asset_journal_entry, self.asset_account), 285900)
		asset = frappe.get_doc("Asset", machine.asset)
		self.assertEqual(asset.docstatus, 0)
		self.assertEqual(asset.gross_purchase_amount, 285900)
		self.assertEqual(asset.letter_of_credit, lc.name)
		self.assertAlmostEqual(accounting.transit_balance(lc), 0, places=1)

		lc = self.step(lc, "close", residual_account=frappe.get_cached_value("Company", COMPANY, "round_off_account"))
		self.assertEqual(lc.status, "Closed")
		self.assertEqual(accounting.transit_balance(lc), 0)

	def test_costs_typed_into_the_grid(self):
		# Typed into the draft: posted on submit.
		lc = self.make_lc(submit=False)
		lc.append("costs", {"cost_type": "LC Commission", "amount": 5000})
		lc.save(ignore_permissions=True)
		self.assertFalse(lc.costs[0].journal_entry)
		self.assertEqual(lc.costs[0].cost_group, "Bank Charges")
		lc.submit()
		lc = frappe.get_doc("Letter of Credit", lc.name)
		self.assertTrue(lc.costs[0].journal_entry)
		self.assertEqual(lc.bank_charges, 5000)

		# Added on the submitted LC: posted on Update.
		lc.append("costs", {"cost_type": "SWIFT Charge", "amount": 1500})
		lc.append("costs", {"cost_type": "Documentation Charge", "amount": 800, "vat_amount": 104})
		lc.append("costs", {"cost_type": "Marine Insurance", "amount": 3000, "paid_via": "Party", "party": self.insurer})
		lc.append("costs", {"cost_type": "Customs VAT", "amount": 30000})
		lc.save(ignore_permissions=True)
		lc = frappe.get_doc("Letter of Credit", lc.name)
		self.assertTrue(all(c.journal_entry for c in lc.costs))
		self.assertEqual(lc.bank_charges, 7300)
		self.assertEqual(lc.insurance_cost, 3000)
		self.assertEqual(lc.vat_total, 30104)
		self.assertEqual(accounting.transit_balance(lc), 10300)
		self.assertEqual(_party_balance(self.insurer), 3000)
		self.assertEqual(len(lc.events), 6)  # Opened + five costs

		# A posted row cannot be changed in place.
		lc.costs[1].amount = 1600
		with self.assertRaises(frappe.ValidationError):
			lc.save(ignore_permissions=True)

		# Deleting it cancels its entry and its History row.
		lc = frappe.get_doc("Letter of Credit", lc.name)
		swift = lc.costs[1]
		lc.costs.remove(swift)
		lc.save(ignore_permissions=True)
		lc = frappe.get_doc("Letter of Credit", lc.name)
		self.assertEqual(frappe.db.get_value("Journal Entry", swift.journal_entry, "docstatus"), 2)
		self.assertEqual(lc.bank_charges, 5800)
		self.assertEqual(len(lc.events), 5)
		self.assertEqual(accounting.transit_balance(lc), 8800)

		# Undo still takes the newest step (the Customs VAT row) off cleanly.
		lifecycle.undo_last_step(lc)
		lc = frappe.get_doc("Letter of Credit", lc.name)
		self.assertEqual(lc.vat_total, 104)
		self.assertEqual(lc.bank_charges, 5800)

	def test_usance_accept_then_pay_at_maturity(self):
		lc = self.make_lc(drafts_at="Usance", usance_days=90, maturity_date=add_days(nowdate(), 90), margin_amount=20000)
		with self.assertRaises(frappe.ValidationError):
			self.step(lc, "pay_goods", fc_amount=10000, exchange_rate=BANK_RATE)
		lc = self.step(lc, "accept_bill", fc_amount=10000, exchange_rate=133)
		bill = lc.costs[-1]
		self.assertEqual(bill.amount, 1330000)
		self.assertEqual(lc.goods_cost, 1330000)
		self.assertEqual(lc.acceptance_outstanding_fc, 10000)
		self.assertEqual(_party_balance(self.supplier), 1330000)

		preview = lifecycle.maturity_preview(lc.name, bill.name, BANK_RATE)
		self.assertEqual(preview.exchange_difference, 20000)
		self.assertEqual(preview.margin_used, 20000)

		lc = self.step(lc, "pay_maturity", cost_row=bill.name, exchange_rate=BANK_RATE)
		bill = lc.costs[-1]
		self.assertEqual(bill.exchange_difference, 20000)
		gain_loss = frappe.get_cached_value("Company", COMPANY, "exchange_gain_loss_account")
		self.assertEqual(_gl(bill.maturity_journal_entry, gain_loss), 20000)
		self.assertEqual(_party_balance(self.supplier), 0)
		# The loss is not cost: the goods stay at the acceptance rate.
		self.assertEqual(lc.total_cost, 1330000)
		self.assertEqual(lc.acceptance_outstanding_fc, 0)
		self.assertEqual(lc.margin_balance, 0)

	def test_undo_transfer_and_payment(self):
		lc = self.make_lc()
		lc = self.step(lc, "pay_goods", fc_amount=10000, exchange_rate=BANK_RATE)
		lc = self.step(self.arrive(lc), "transfer")
		se, asset, je = lc.items[0].stock_entry, lc.items[1].asset, lc.items[1].asset_journal_entry

		lifecycle.undo_last_step(frappe.get_doc("Letter of Credit", lc.name))
		lc = frappe.get_doc("Letter of Credit", lc.name)
		self.assertEqual(lc.status, "Arrived")
		self.assertFalse(lc.transferred_on)
		self.assertFalse(lc.items[0].stock_entry)
		self.assertEqual(frappe.db.get_value("Stock Entry", se, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Journal Entry", je, "docstatus"), 2)
		self.assertFalse(frappe.db.exists("Asset", asset))
		self.assertEqual(accounting.transit_balance(lc), 1350000)

		pay_je = lc.costs[-1].journal_entry
		lifecycle.undo_last_step(lc)
		lc = frappe.get_doc("Letter of Credit", lc.name)
		self.assertFalse(lc.costs)
		self.assertEqual(lc.goods_pending_fc, 10000)
		self.assertEqual(frappe.db.get_value("Journal Entry", pay_je, "docstatus"), 2)

	def test_undo_refused_once_asset_submitted(self):
		lc = self.make_lc(items=[{"item_code": self.machine, "description": "Press", "qty": 1, "rate": 10000,
			"transfer_to": "Fixed Asset"}])
		lc = self.step(lc, "pay_goods", fc_amount=10000, exchange_rate=BANK_RATE)
		lc = self.step(self.arrive(lc), "transfer")
		frappe.db.set_value("Asset", lc.items[0].asset, "docstatus", 1)  # as if the user submitted it
		with self.assertRaises(frappe.ValidationError):
			lifecycle.undo_last_step(lc)

	# ── guards ────────────────────────────────────────────────────────────────

	def test_cannot_cancel_lc_documents_from_their_forms(self):
		lc = self.make_lc()
		lc = self.step(lc, "add_cost", cost_type="SWIFT Charge", amount=1500)
		je = frappe.get_doc("Journal Entry", lc.costs[0].journal_entry)
		with self.assertRaises(frappe.ValidationError):
			je.cancel()
		lc = self.step(lc, "pay_goods", fc_amount=10000, exchange_rate=BANK_RATE)
		lc = self.step(self.arrive(lc), "transfer")
		se = frappe.get_doc("Stock Entry", lc.items[0].stock_entry)
		with self.assertRaises(frappe.ValidationError):
			se.cancel()

	def test_goods_cannot_exceed_lc_amount_and_tolerance(self):
		lc = self.make_lc(tolerance_plus=5)
		lc = self.step(lc, "pay_goods", fc_amount=10400, exchange_rate=BANK_RATE)
		with self.assertRaises(frappe.ValidationError):
			self.step(lc, "pay_goods", fc_amount=200, exchange_rate=BANK_RATE)
		lc.lc_amount = 9000  # amendment below what is already paid
		with self.assertRaises(frappe.ValidationError):
			lc.save(ignore_permissions=True)

	def test_transfer_needs_arrival_goods_and_targets(self):
		lc = self.make_lc()
		with self.assertRaises(frappe.ValidationError):
			self.step(lc, "transfer")  # not arrived, goods not paid
		lc = self.arrive(lc)
		self.assertTrue(any("goods payment" in p for p in transfer.preview(lc)["problems"]))
		lc = self.step(lc, "pay_goods", fc_amount=10000, exchange_rate=BANK_RATE)
		lc.items[0].item_code = self.machine  # a fixed-asset item sent to stock
		lc.save(ignore_permissions=True)
		lc = frappe.get_doc("Letter of Credit", lc.name)
		self.assertTrue(any("not a stock item" in p for p in transfer.preview(lc)["problems"]))

	def test_close_needs_transfer_and_clears_late_cost(self):
		lc = self.make_lc()
		lc = self.step(lc, "pay_goods", fc_amount=10000, exchange_rate=BANK_RATE)
		with self.assertRaises(frappe.ValidationError):
			self.step(lc, "close")
		lc = self.step(self.arrive(lc), "transfer")
		lc = self.step(lc, "add_cost", cost_type="Documentation Charge", amount=700)  # after the transfer
		with self.assertRaises(frappe.ValidationError):
			self.step(lc, "close")
		expense = frappe.get_cached_value("Company", COMPANY, "round_off_account")
		lc = self.step(lc, "close", residual_account=expense)
		self.assertEqual(lc.status, "Closed")
		self.assertAlmostEqual(accounting.transit_balance(lc), 0, places=2)

	def test_cancel_only_before_any_step(self):
		lc = self.make_lc(margin_amount=10000)
		lc = self.step(lc, "add_cost", cost_type="LC Commission", amount=2000)
		with self.assertRaises(frappe.ValidationError):
			lc.cancel()
		lifecycle.undo_last_step(frappe.get_doc("Letter of Credit", lc.name))
		lc = frappe.get_doc("Letter of Credit", lc.name)
		margin_je = lc.events[0].journal_entry
		lc.cancel()
		self.assertEqual(frappe.db.get_value("Letter of Credit", lc.name, "status"), "Cancelled")
		self.assertEqual(frappe.db.get_value("Journal Entry", margin_je, "docstatus"), 2)

	def test_submit_needs_lc_no(self):
		lc = self.make_lc(submit=False, lc_no=None)
		with self.assertRaises(frappe.ValidationError):
			lc.submit()

	# ── NRB rules ─────────────────────────────────────────────────────────────

	def test_trading_firm_usance_limit_and_margin(self):
		settings = frappe.get_doc("LC Settings")
		row = next(r for r in settings.company_accounts if r.company == COMPANY)
		row.firm_type = "Trading"
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("LC Settings", "LC Settings")
		with self.assertRaises(frappe.ValidationError):
			self.make_lc(submit=False, drafts_at="Usance", usance_days=181)
		lc = self.make_lc(submit=False, drafts_at="Usance", usance_days=180)
		self.assertEqual(lc.margin_percent, flt(settings.margin_trading))

	def test_bci_needed_for_large_sight_lc(self):
		items = [{"item_code": self.steel, "description": "MS plate", "qty": 1000, "rate": 60, "transfer_to": "Stock"}]
		lc = self.make_lc(submit=False, items=items, lc_amount=60000)
		with self.assertRaises(frappe.ValidationError):
			lc.submit()
		lc = self.make_lc(items=items, lc_amount=60000, bci_reference="BCI-1", bci_date=nowdate())
		self.assertEqual(lc.status, "Open")

	# ── output ────────────────────────────────────────────────────────────────

	def test_reports_digest_and_print(self):
		from avinashgroup_app.lc import notifications
		from avinashgroup_app.lc.report.lc_cost_sheet import lc_cost_sheet
		from avinashgroup_app.lc.report.lc_margin_and_charges import lc_margin_and_charges
		from avinashgroup_app.lc.report.lc_maturity import lc_maturity
		from avinashgroup_app.lc.report.lc_register import lc_register

		lc = self.make_lc(drafts_at="Usance", usance_days=30, maturity_date=add_days(nowdate(), 10))
		lc = self.book_example_costs(lc)
		lc = self.step(lc, "accept_bill", fc_amount=10000, exchange_rate=133)

		_cols, rows = lc_cost_sheet.execute({"letter_of_credit": lc.name})
		total = next(r for r in rows if r.get("particulars") == "Total Landed Cost")
		self.assertEqual(total["amount"], lc.total_cost)
		self.assertEqual(total["vat"], 32600)
		items_total = rows[-1]
		self.assertAlmostEqual(items_total["amount"], lc.total_cost, places=1)

		_cols, rows = lc_register.execute({"company": COMPANY})
		self.assertIn(lc.name, [r.name for r in rows])
		_cols, rows = lc_maturity.execute({"company": COMPANY})
		self.assertIn(lc.name, [r.name for r in rows])
		_cols, rows = lc_margin_and_charges.execute({"company": COMPANY})
		self.assertTrue(any(flt(r.customs_cost) >= 50000 for r in rows))

		digest = notifications.digest_rows(days_ahead=15)
		self.assertIn(lc.name, [r.name for r in digest["maturing"]])

		for print_format in ("LC Summary", "LC Cost Sheet"):
			html = frappe.get_print("Letter of Credit", lc.name, print_format=print_format)
			self.assertIn(lc.lc_no, html)
			self.assertIn("Import Duty (ID)" if print_format == "LC Cost Sheet" else "Total Landed Cost", html)
