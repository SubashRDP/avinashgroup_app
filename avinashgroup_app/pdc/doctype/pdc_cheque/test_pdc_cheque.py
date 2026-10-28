"""PDC Cheque — the whole lifecycle against real invoices, rolled back.

Covers:
- received: submit → deposit → clear; GL lands in holding then bank; invoice paid
- bounce before clearing re-opens the invoice; bounce charges (expense / recovered)
- bounce / return / undo of a cheque carrying an advance (reconciled, nothing left open)
- bounce after clearing comes out of the bank
- re-deposit after a bounce re-settles the invoice and clears again
- return of a cheque in hand; replace a bounced cheque, cancel the replacement
- undo last step cancels the step's JE and restores the fields
- issued cheque: issue → clear, and stop
- guards: early deposit, stale cheque, duplicate number, over-allocation,
  cancelling a settled invoice, cancelling a cheque's JE directly, cancelling a
  deposited cheque
- bulk deposit carries on past a failing cheque
- SMS only when PDC Settings and Sparrow SMS both say so

Uses an existing submitted Sales / Purchase Invoice with an outstanding amount
(the site's own data: building an invoice from scratch here runs through every
selling hook in the app) and rolls everything back. Runner: docs/pdc-management.md.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, flt, nowdate

from avinashgroup_app.pdc import lifecycle, notifications, payment_entry_bounce
from avinashgroup_app.pdc.install import apply_settings_defaults, ensure_company_accounts
from avinashgroup_app.pdc.invoice_guard import block_invoice_cancel

AMOUNT = 1000


def _invoice(doctype, company=None):
	party_field = "customer" if doctype == "Sales Invoice" else "supplier"
	filters = {"docstatus": 1, "outstanding_amount": [">", AMOUNT * 50]}
	if company:
		filters["company"] = company
	if doctype == "Sales Invoice":
		filters["is_return"] = 0
	for inv in frappe.get_all(
		doctype, filters=filters, fields=["name", "company", party_field + " as party"],
		order_by="posting_date desc", limit=200,
	):
		if frappe.db.get_value("Account", {"company": inv.company, "account_type": "Bank", "is_group": 0}):
			return inv
	return None


class TestPDCCheque(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		# Prefer a company that has both kinds of open invoice, so the issued test runs.
		pi = _invoice("Purchase Invoice")
		cls.si = (pi and _invoice("Sales Invoice", pi.company)) or _invoice("Sales Invoice")
		if not cls.si:
			raise unittest.SkipTest("no Sales Invoice with an outstanding amount on this site")
		cls.company = cls.si.company
		cls.bank = frappe.db.get_value("Account", {"company": cls.company, "account_type": "Bank", "is_group": 0})
		apply_settings_defaults()
		ensure_company_accounts([cls.company])
		settings = frappe.get_doc("PDC Settings")
		settings.update({
			"allow_on_account": 1, "block_duplicate_cheque": 1, "cheque_validity_months": 6,
			"send_sms": 0,
		})
		if not settings.jv_type and frappe.db.exists("JV Type", "Bank Entry"):
			settings.jv_type = "Bank Entry"
		settings.save()
		cls.accounts = next(r for r in settings.company_accounts if r.company == cls.company)

	def outstanding(self, name=None, doctype="Sales Invoice"):
		return flt(frappe.db.get_value(doctype, name or self.si.name, "outstanding_amount"))

	def balance(self, account):
		return flt(frappe.db.sql(
			"select sum(debit) - sum(credit) from `tabGL Entry` where account=%s and is_cancelled=0",
			account,
		)[0][0])

	def make(self, cheque_date=None, amount=AMOUNT, allocate=AMOUNT, cheque_no=None, submit=True, **kw):
		doc = frappe.get_doc({
			"doctype": "PDC Cheque", "cheque_type": "Received", "company": self.company,
			"posting_date": nowdate(), "party_type": "Customer", "party": self.si.party,
			"cheque_no": cheque_no or frappe.generate_hash(length=8), "cheque_date": cheque_date or nowdate(),
			"amount": amount, "bank_name": "Test Bank", "bank_account": self.bank,
		})
		if allocate:
			doc.append("references", {"reference_doctype": "Sales Invoice", "reference_name": self.si.name,
				"allocated_amount": allocate})
		doc.update(kw)
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def reload(self, doc):
		return frappe.get_doc("PDC Cheque", doc.name)

	# ── received ────────────────────────────────────────────────────────────

	def test_receive_deposit_clear(self):
		before = self.outstanding()
		hold0, bank0 = self.balance(self.accounts.cheques_in_hand_account), self.balance(self.bank)

		c = self.make()
		self.assertEqual(c.status, "In Hand")
		self.assertAlmostEqual(self.outstanding(), before - AMOUNT)
		self.assertAlmostEqual(self.balance(self.accounts.cheques_in_hand_account), hold0 + AMOUNT)

		lifecycle.deposit(self.reload(c), nowdate(), self.bank)
		self.assertEqual(self.reload(c).status, "Deposited")
		self.assertAlmostEqual(self.balance(self.bank), bank0)  # deposit posts nothing

		lifecycle.clear(self.reload(c), nowdate())
		c = self.reload(c)
		self.assertEqual(c.status, "Cleared")
		self.assertAlmostEqual(self.balance(self.bank), bank0 + AMOUNT)
		self.assertAlmostEqual(self.balance(self.accounts.cheques_in_hand_account), hold0)
		clear_je = c.events[-1].journal_entry
		self.assertEqual(str(frappe.db.get_value("Journal Entry", clear_je, "clearance_date")), nowdate())
		self.assertEqual([e.event for e in c.events], ["Received", "Deposited", "Cleared"])

	def test_advance_for_unallocated(self):
		c = self.make(amount=AMOUNT * 2, allocate=AMOUNT)
		self.assertAlmostEqual(c.unallocated_amount, AMOUNT)
		rows = frappe.get_all("Journal Entry Account", {"parent": c.events[0].journal_entry, "is_advance": "Yes"},
			pluck="credit_in_account_currency")
		self.assertEqual([flt(r) for r in rows], [AMOUNT])

	def open_balance(self, *vouchers):
		"""What the Payment Ledger still shows open against these vouchers (AR / AP view)."""
		return flt(frappe.db.sql(
			"""select sum(amount) from `tabPayment Ledger Entry`
			where delinked = 0 and against_voucher_no in %s""",
			(vouchers,),
		)[0][0])

	def test_bounce_and_undo_advance_only_cheque(self):
		# Regression: reversing an advance used to reference the receipt JE, which
		# ERPNext refuses for a debit to a receivable ("only if account gets credited").
		c = self.make(allocate=0)
		receipt = c.events[0].journal_entry
		lifecycle.deposit(self.reload(c), nowdate(), self.bank)
		lifecycle.bounce(self.reload(c), nowdate(), "Insufficient Funds", charges=100)
		bounce_je = self.reload(c).events[-1].journal_entry
		self.assertEqual(self.reload(c).status, "Bounced")
		self.assertAlmostEqual(self.open_balance(receipt, bounce_je), 0)

		lifecycle.undo_last_step(self.reload(c))
		self.assertEqual(self.reload(c).status, "Deposited")
		self.assertAlmostEqual(self.open_balance(receipt, bounce_je), -AMOUNT)  # the advance is open again

		lifecycle.clear(self.reload(c), nowdate())
		lifecycle.bounce(self.reload(c), nowdate(), "Insufficient Funds")
		lifecycle.redeposit(self.reload(c), nowdate(), self.bank)
		lifecycle.bounce(self.reload(c), nowdate(), "Account Closed")
		self.assertEqual(self.reload(c).status, "Bounced")

	def test_return_cheque_with_advance(self):
		c = self.make(amount=AMOUNT * 2, allocate=AMOUNT)
		lifecycle.return_cheque(self.reload(c), nowdate())
		ret = self.reload(c).events[-1].journal_entry
		self.assertAlmostEqual(self.open_balance(c.events[0].journal_entry, ret), 0)

	def test_bounce_before_clearing_reopens_invoice(self):
		before = self.outstanding()
		expense0 = self.balance(self.accounts.bounce_charges_account)
		c = self.make()
		lifecycle.deposit(self.reload(c), nowdate(), self.bank)
		lifecycle.bounce(self.reload(c), nowdate(), "Insufficient Funds", charges=200)
		c = self.reload(c)
		self.assertEqual(c.status, "Bounced")
		self.assertAlmostEqual(self.outstanding(), before)
		self.assertAlmostEqual(self.balance(self.accounts.bounce_charges_account), expense0 + 200)

	def test_bounce_charges_recovered_from_customer(self):
		c = self.make()
		lifecycle.deposit(self.reload(c), nowdate(), self.bank)
		lifecycle.bounce(self.reload(c), nowdate(), "Insufficient Funds", charges=150, recover_charges=1)
		je = self.reload(c).events[-1].journal_entry
		party_debit = frappe.get_all("Journal Entry Account",
			{"parent": je, "party": self.si.party, "reference_type": ["is", "not set"]},
			pluck="debit_in_account_currency")
		self.assertIn(150, [flt(x) for x in party_debit])

	def test_bounce_after_clearing_and_redeposit(self):
		before = self.outstanding()
		bank0 = self.balance(self.bank)
		c = self.make()
		lifecycle.deposit(self.reload(c), nowdate(), self.bank)
		lifecycle.clear(self.reload(c), nowdate())
		lifecycle.bounce(self.reload(c), nowdate(), "Signature Mismatch")
		self.assertAlmostEqual(self.balance(self.bank), bank0)
		self.assertAlmostEqual(self.outstanding(), before)

		lifecycle.redeposit(self.reload(c), nowdate(), self.bank)
		c = self.reload(c)
		self.assertEqual((c.status, c.presentation_count), ("Deposited", 2))
		self.assertAlmostEqual(self.outstanding(), before - AMOUNT)
		lifecycle.clear(c, nowdate())
		self.assertAlmostEqual(self.balance(self.bank), bank0 + AMOUNT)

	def test_return_in_hand(self):
		before = self.outstanding()
		c = self.make()
		lifecycle.return_cheque(self.reload(c), nowdate(), "Customer asked for it back")
		self.assertEqual(self.reload(c).status, "Returned")
		self.assertAlmostEqual(self.outstanding(), before)

	def test_replace_and_cancel_replacement(self):
		c = self.make()
		lifecycle.deposit(self.reload(c), nowdate(), self.bank)
		lifecycle.bounce(self.reload(c), nowdate(), "Insufficient Funds")
		new = frappe.get_doc(lifecycle.make_replacement(c.name))
		new.cheque_no = "R" + c.cheque_no
		new.cheque_date = nowdate()
		new.insert()
		new.submit()
		original = self.reload(c)
		self.assertEqual((original.status, original.replaced_by), ("Replaced", new.name))

		new.reload()
		new.cancel()
		original = self.reload(c)
		self.assertEqual((original.status, original.replaced_by), ("Bounced", None))

	def test_undo_last_step(self):
		bank0 = self.balance(self.bank)
		c = self.make()
		lifecycle.deposit(self.reload(c), nowdate(), self.bank)
		lifecycle.clear(self.reload(c), nowdate())
		clear_je = self.reload(c).events[-1].journal_entry

		lifecycle.undo_last_step(self.reload(c))
		c = self.reload(c)
		self.assertEqual((c.status, c.clearance_date), ("Deposited", None))
		self.assertEqual(frappe.db.get_value("Journal Entry", clear_je, "docstatus"), 2)
		self.assertAlmostEqual(self.balance(self.bank), bank0)

		lifecycle.undo_last_step(c)
		c = self.reload(c)
		self.assertEqual((c.status, c.deposit_date), ("In Hand", None))
		self.assertRaises(frappe.ValidationError, lifecycle.undo_last_step, c)
		c.cancel()
		self.assertEqual(self.reload(c).status, "Cancelled")

	# ── issued ──────────────────────────────────────────────────────────────

	def test_issued_clear_and_stop(self):
		pi = _invoice("Purchase Invoice", self.company)
		if not pi:
			self.skipTest("no Purchase Invoice with an outstanding amount in " + self.company)
		before = self.outstanding(pi.name, "Purchase Invoice")
		bank0 = self.balance(self.bank)

		def issue():
			doc = frappe.get_doc({
				"doctype": "PDC Cheque", "cheque_type": "Issued", "company": self.company,
				"posting_date": nowdate(), "party_type": "Supplier", "party": pi.party,
				"cheque_no": frappe.generate_hash(length=8), "cheque_date": nowdate(),
				"amount": AMOUNT, "bank_account": self.bank,
				"references": [{"reference_doctype": "Purchase Invoice", "reference_name": pi.name,
					"allocated_amount": AMOUNT}],
			}).insert()
			doc.submit()
			return doc

		c = issue()
		self.assertEqual(c.status, "Issued")
		self.assertAlmostEqual(self.outstanding(pi.name, "Purchase Invoice"), before - AMOUNT)
		lifecycle.clear(self.reload(c), nowdate())
		self.assertAlmostEqual(self.balance(self.bank), bank0 - AMOUNT)

		adv = frappe.get_doc({
			"doctype": "PDC Cheque", "cheque_type": "Issued", "company": self.company,
			"posting_date": nowdate(), "party_type": "Supplier", "party": pi.party,
			"cheque_no": frappe.generate_hash(length=8), "cheque_date": nowdate(),
			"amount": AMOUNT, "bank_account": self.bank,
		}).insert()
		adv.submit()
		lifecycle.bounce(self.reload(adv), nowdate(), "Insufficient Funds")
		self.assertEqual(self.reload(adv).status, "Bounced")

		s = issue()
		lifecycle.return_cheque(self.reload(s), nowdate())
		self.assertEqual(self.reload(s).status, "Returned")
		self.assertAlmostEqual(self.outstanding(pi.name, "Purchase Invoice"), before - AMOUNT)

	# ── guards ──────────────────────────────────────────────────────────────

	def test_cannot_deposit_early_or_stale(self):
		early = self.make(cheque_date=add_days(nowdate(), 10))
		self.assertRaises(frappe.ValidationError, lifecycle.deposit, self.reload(early), nowdate(), self.bank)
		stale = self.make(cheque_date=add_months(nowdate(), -7))
		self.assertRaises(frappe.ValidationError, lifecycle.deposit, self.reload(stale), nowdate(), self.bank)

	def test_duplicate_and_over_allocation(self):
		c = self.make(cheque_no="DUP-PDC-1")
		self.assertRaises(frappe.ValidationError, self.make, cheque_no="DUP-PDC-1")
		over = self.outstanding() + 1
		self.assertRaises(frappe.ValidationError, self.make, amount=over, allocate=over)
		self.assertRaises(frappe.ValidationError, self.make, amount=AMOUNT, allocate=AMOUNT + 1)
		self.assertTrue(c.name)

	def test_cancel_guards(self):
		c = self.make()
		# Called directly: on an IRD-synced invoice the CBMS guard refuses first.
		si = frappe.get_doc("Sales Invoice", self.si.name)
		self.assertRaisesRegex(frappe.ValidationError, "post-dated cheque", block_invoice_cancel, si)
		je = frappe.get_doc("Journal Entry", c.events[0].journal_entry)
		self.assertRaises(frappe.ValidationError, je.cancel)
		lifecycle.deposit(self.reload(c), nowdate(), self.bank)
		self.assertRaises(frappe.ValidationError, self.reload(c).cancel)

	def test_bulk_deposit_continues_past_failure(self):
		ok = self.make()
		early = self.make(cheque_date=add_days(nowdate(), 5))
		result = lifecycle.bulk_action([ok.name, early.name], "deposit", nowdate(), self.bank)
		self.assertEqual(result["done"], [ok.name])
		self.assertEqual([f["name"] for f in result["failed"]], [early.name])
		self.assertEqual(self.reload(ok).status, "Deposited")
		self.assertEqual(self.reload(early).status, "In Hand")

	# ── SMS ─────────────────────────────────────────────────────────────────

	def test_sms_follows_switches(self):
		# after_commit callbacks never run: the test transaction is rolled back.
		c = self.make()
		frappe.db.set_single_value("Sparrow SMS Settings", "enabled", 1)

		def switches(**values):
			frappe.db.set_single_value("PDC Settings", values)
			frappe.clear_document_cache("PDC Settings", "PDC Settings")

		switches(send_sms=0, sms_on_bounce=1)
		self.assertFalse(notifications.send_party_sms(c, "bounce"))
		switches(send_sms=1, sms_on_bounce=0)
		self.assertFalse(notifications.send_party_sms(c, "bounce"))
		switches(send_sms=1, sms_on_bounce=1)
		self.assertTrue(notifications.send_party_sms(c, "bounce"))
		frappe.db.set_single_value("Sparrow SMS Settings", "enabled", 0)
		self.assertFalse(notifications.send_party_sms(c, "bounce"))
		switches(send_sms=0)


def _payment_entry(payment_type="Receive", where=""):
	party_type = "Customer" if payment_type == "Receive" else "Supplier"
	names = frappe.db.sql(
		f"""select pe.name from `tabPayment Entry` pe
		where pe.docstatus = 1 and pe.payment_type = %s and pe.party_type = %s
		and ifnull(pe.custom_cheque_bounce, '') = '' and ifnull(pe.pdc_cheque, '') = '' {where}
		order by pe.posting_date desc limit 1""",
		(payment_type, party_type), pluck=True,
	)
	return frappe.get_doc("Payment Entry", names[0]) if names else None


class TestPaymentEntryBounce(FrappeTestCase):
	"""Cheques entered straight into Payment Entry: bounce, undo, re-present, replace.

	Uses the site's own submitted Payment Entries and rolls everything back.
	"""

	INVOICE_PE = """and pe.unallocated_amount = 0
		and exists(select 1 from `tabPayment Entry Reference` r where r.parent = pe.name
			and r.reference_doctype in ('Sales Invoice', 'Purchase Invoice'))"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		apply_settings_defaults()
		cls.pe = _payment_entry(where=cls.INVOICE_PE)
		if not cls.pe:
			raise unittest.SkipTest("no Receive Payment Entry against invoices on this site")
		ensure_company_accounts([cls.pe.company])

	# Every test bounces the same Payment Entry, so each one starts clean.
	def setUp(self):
		frappe.db.savepoint("pe_bounce_test")

	def tearDown(self):
		frappe.db.rollback(save_point="pe_bounce_test")

	def invoice_outstanding(self, pe=None):
		pe = pe or self.pe
		return {r.reference_name: flt(frappe.db.get_value(r.reference_doctype, r.reference_name, "outstanding_amount"))
			for r in pe.references if r.reference_doctype in ("Sales Invoice", "Purchase Invoice")}

	def bank_balance(self, account):
		return flt(frappe.db.sql(
			"select sum(debit) - sum(credit) from `tabGL Entry` where account=%s and is_cancelled=0", account)[0][0])

	def test_bounce_undo_represent(self):
		before = self.invoice_outstanding()
		bank = self.pe.paid_to
		bank0 = self.bank_balance(bank)

		name = payment_entry_bounce.bounce(self.pe.name, nowdate(), "Insufficient Funds", charges=250)
		c = frappe.get_doc("PDC Cheque", name)
		self.assertEqual((c.status, c.payment_entry), ("Bounced", self.pe.name))
		self.assertEqual(c.events[0].payment_entry, self.pe.name)
		self.assertIsNone(c.events[0].journal_entry)  # the PE is the receipt; no entry of its own
		self.assertEqual(frappe.db.get_value("Journal Entry", c.events[-1].journal_entry, "pdc_payment_entry"), self.pe.name)
		if frappe.get_meta("Journal Entry").has_field("custom_posting_miti"):
			from avinashgroup_app.utils.bs_miti import ad_to_miti

			self.assertEqual(frappe.db.get_value("Journal Entry", c.events[-1].journal_entry, "custom_posting_miti"),
				ad_to_miti(nowdate()))
		connections = payment_entry_bounce.get_payment_entry_dashboard({})
		self.assertEqual(connections.non_standard_fieldnames["Journal Entry"], "pdc_payment_entry")
		self.assertEqual(frappe.db.get_value("Payment Entry", self.pe.name, ["custom_cheque_bounce", "pdc_cheque"]),
			("Cheque Bounced", name))
		reopened = self.invoice_outstanding()
		for inv, amount in before.items():
			allocated = sum(flt(r.allocated_amount) for r in self.pe.references if r.reference_name == inv)
			self.assertAlmostEqual(reopened[inv], amount + allocated)
		self.assertAlmostEqual(self.bank_balance(bank), bank0 - flt(self.pe.received_amount) - 250)

		# Cancelling the original PE would reverse it twice.
		self.assertRaises(frappe.ValidationError, frappe.get_doc("Payment Entry", self.pe.name).run_method, "before_cancel")
		# A second bounce of the same cheque is refused.
		self.assertRaises(frappe.ValidationError, payment_entry_bounce.bounce, self.pe.name, nowdate(), "Other")

		payment_entry_bounce.undo_bounce(self.pe.name)  # the PE's "Undo Bounce" button
		self.assertEqual(frappe.get_value("PDC Cheque", name, "status"), "Cleared")
		self.assertFalse(frappe.db.get_value("Payment Entry", self.pe.name, "custom_cheque_bounce"))
		self.assertEqual(self.invoice_outstanding(), before)

		# Bouncing again reuses the same record.
		self.assertEqual(payment_entry_bounce.bounce(self.pe.name, nowdate(), "Insufficient Funds"), name)
		lifecycle.represent(frappe.get_doc("PDC Cheque", name), nowdate())
		c = frappe.get_doc("PDC Cheque", name)
		self.assertEqual((c.status, c.presentation_count), ("Cleared", 2))
		# The bounce is no longer the latest step: undo it on the record, newest first.
		self.assertRaisesRegex(frappe.ValidationError, "latest step", payment_entry_bounce.undo_bounce, self.pe.name)
		self.assertEqual(self.invoice_outstanding(), before)
		self.assertFalse(frappe.db.get_value("Payment Entry", self.pe.name, "custom_cheque_bounce"))

	def test_replace_with_new_payment_entry(self):
		name = payment_entry_bounce.bounce(self.pe.name, nowdate(), "Account Closed")
		draft = payment_entry_bounce.make_replacement_payment_entry(name)
		new = frappe.get_doc(draft)
		new.reference_no = "REPL-" + frappe.generate_hash(length=6)
		new.reference_date = nowdate()
		new.insert()
		new.submit()
		c = frappe.get_doc("PDC Cheque", name)
		self.assertEqual((c.status, c.replaced_by_payment_entry), ("Replaced", new.name))
		self.assertEqual(frappe.db.get_value("Payment Entry", self.pe.name, "custom_cheque_bounce"), "Cheque Bounced")

		new.reload()
		new.cancel()
		c = frappe.get_doc("PDC Cheque", name)
		self.assertEqual((c.status, c.replaced_by_payment_entry), ("Bounced", None))

	def test_unallocated_payment_entry(self):
		pe = _payment_entry(where="and pe.unallocated_amount > 0")
		if not pe:
			self.skipTest("no Receive Payment Entry with an unallocated amount")
		ensure_company_accounts([pe.company])
		name = payment_entry_bounce.bounce(pe.name, nowdate(), "Insufficient Funds")
		je = frappe.get_doc("PDC Cheque", name).events[-1].journal_entry
		open_ = flt(frappe.db.sql(
			"select sum(amount) from `tabPayment Ledger Entry` where delinked=0 and party=%s and against_voucher_no in %s",
			(pe.party, (pe.name, je)))[0][0])
		self.assertAlmostEqual(open_, 0)
		lifecycle.represent(frappe.get_doc("PDC Cheque", name), nowdate())
		self.assertEqual(frappe.db.get_value("PDC Cheque", name, "status"), "Cleared")

	def test_supplier_payment_bounce(self):
		pe = _payment_entry("Pay", where=self.INVOICE_PE)
		if not pe:
			self.skipTest("no Pay Payment Entry against invoices")
		before = self.invoice_outstanding(pe)
		name = payment_entry_bounce.bounce(pe.name, nowdate(), "Insufficient Funds")
		self.assertEqual(frappe.db.get_value("PDC Cheque", name, ["cheque_type", "status"]), ("Issued", "Bounced"))
		self.assertTrue(all(self.invoice_outstanding(pe)[k] > v for k, v in before.items()))

	def test_old_style_bounce_refused(self):
		old = frappe.db.get_value("GL Entry",
			{"voucher_type": "Payment Entry", "remarks": ["like", "Cheque Bounce -%"], "is_cancelled": 0}, "voucher_no")
		if not old:
			self.skipTest("no Payment Entry bounced the old way on this site")
		self.assertRaisesRegex(frappe.ValidationError, "old Cheque Bounce", payment_entry_bounce.bounce, old, nowdate(), "Other")

	def test_bounce_with_chosen_journal_type(self):
		types = frappe.get_all("JV Type", pluck="name")
		default = frappe.db.get_single_value("PDC Settings", "jv_type")
		for jv_type in [t for t in types if t != default]:
			frappe.db.savepoint("jv_try")
			try:
				name = payment_entry_bounce.bounce(self.pe.name, nowdate(), "Insufficient Funds", jv_type=jv_type)
			except frappe.ValidationError as e:
				frappe.db.rollback(save_point="jv_try")
				self.assertIn("numbering rule", str(e))  # an unnumbered type says so plainly
				continue
			je = frappe.get_doc("PDC Cheque", name).events[-1].journal_entry
			self.assertEqual(frappe.db.get_value("Journal Entry", je, "custom_p_type"), jv_type)
			return
		self.skipTest("no second numbered JV Type for " + self.pe.company)

