"""PDC accounting — the Journal Entry behind every step of a cheque's life.

ERPNext books a cheque as a Payment Entry the day it is entered, straight to the
bank. A post-dated cheque is not money in the bank: it sits in a drawer until its
date, may be deposited, may bounce. So each step here posts its own Journal Entry
through a holding account set per company in PDC Settings:

A cheque entered straight into a Payment Entry (no holding account) is bounced
by an entry that swaps that PE's own GL rows, and re-presented by one that
repeats them — see `payment_entry_rows` and `pdc/payment_entry_bounce.py`.

    Received cheque                          Issued cheque
    receive   Dr Cheques in Hand / Cr party  issue     Dr party / Cr Cheques Issued
    deposit   (no entry)
    clear     Dr Bank / Cr Cheques in Hand   clear     Dr Cheques Issued / Cr Bank
    bounce    Dr party / Cr Cheques in Hand  bounce    Dr Cheques Issued / Cr party
              (after clearing: Cr Bank)                (after clearing: Dr Bank)
    return    Dr party / Cr Cheques in Hand  stop      Dr Cheques Issued / Cr party
    re-deposit  same as receive

Party rows carry the invoice references, so a bounce re-opens exactly the invoices
the cheque paid; an advance is reversed on account and reconciled against it. A reversal is built from the settling entry's *current* party
rows, not from the cheque's References table: Payment Reconciliation may have
since applied an advance row to an invoice, and the reversal must follow it.

Boundary: this module only builds and posts entries. Which step is allowed when,
and the cheque's status, belong to `pdc/lifecycle.py`. Company currency only —
a party account in another currency is refused in the cheque's validate.

Landmine: every entry here goes through the app's Journal Entry numbering
(`custom_p_type` → Numbering Configuration). PDC Settings → JV Type picks which
rule numbers them; without one, the JE's mandatory `custom_document_no` stays
empty and the step fails with the JE's own error.
"""

import frappe
from frappe import _
from frappe.utils import flt

# Holding accounts made by "Create Missing Accounts", and the group each one is
# filed under. The groups are the names every company on avinas1 carries
# (account number + name, e.g. "140000 - Current Assets - NGI"), matched on
# account_name so the number is not assumed.
HOLDING_ACCOUNTS = (
	("cheques_in_hand_account", "Cheques in Hand", "Current Assets", "Asset"),
	("cheques_issued_account", "Cheques Issued", "Current Liabilities", "Liability"),
	("bounce_charges_account", "Cheque Bounce Charges", "Indirect Expenses", "Expense"),
)

# Lets pdc/invoice_guard.py tell this module's own cancel from a user's.
INTERNAL_CANCEL_FLAG = "pdc_internal_cancel"


def get_company_accounts(company, require_holding=True):
	row = next(
		(r for r in frappe.get_cached_doc("PDC Settings").company_accounts if r.company == company),
		None,
	)
	if not require_holding:
		# A Payment Entry cheque's bounce needs only the charges account.
		return row or frappe._dict()
	if not row or not row.cheques_in_hand_account or not row.cheques_issued_account:
		frappe.throw(
			_("Set the cheque holding accounts for {0} in PDC Settings first.").format(company),
			title=_("PDC accounts missing"),
		)
	return row


def holding_account(cheque):
	accounts = get_company_accounts(cheque.company)
	if cheque.cheque_type == "Received":
		return accounts.cheques_in_hand_account
	return accounts.cheques_issued_account


# ── Row builders ──────────────────────────────────────────────────────────────


def _party_row(cheque, amount, side, **extra):
	row = {
		"account": cheque.party_account,
		"party_type": cheque.party_type,
		"party": cheque.party,
		"cost_center": cheque.cost_center,
		f"{side}_in_account_currency": flt(amount),
	}
	row.update(extra)
	return row


def _plain_row(account, amount, side, cost_center=None):
	return {"account": account, "cost_center": cost_center, f"{side}_in_account_currency": flt(amount)}


def _settle_side(cheque):
	"""The party side of a settling entry: a customer is credited, a supplier debited."""
	return "credit" if cheque.cheque_type == "Received" else "debit"


def _other(side):
	return "debit" if side == "credit" else "credit"


def settlement_party_rows(cheque, cap_to_outstanding=False):
	"""Party rows that settle the cheque's invoices, plus an advance for the rest.

	`cap_to_outstanding` is for a re-deposit: an invoice may have been paid some
	other way while the cheque was bounced, so allocate only what is still open
	and book the difference as an advance.
	"""
	side = _settle_side(cheque)
	rows, allocated = [], 0.0

	for ref in cheque.references:
		amount = flt(ref.allocated_amount)
		if cap_to_outstanding:
			outstanding = flt(
				frappe.db.get_value(ref.reference_doctype, ref.reference_name, "outstanding_amount")
			)
			# Purchase invoices carry a positive outstanding too; returns are negative.
			amount = min(amount, max(outstanding, 0))
		if amount <= 0:
			continue
		rows.append(
			_party_row(
				cheque, amount, side,
				reference_type=ref.reference_doctype, reference_name=ref.reference_name,
			)
		)
		allocated += amount

	remainder = flt(cheque.amount) - allocated
	if remainder > 0.005:
		if not frappe.db.get_single_value("PDC Settings", "allow_on_account"):
			frappe.throw(
				_("{0} of this cheque is not allocated to any invoice, and PDC Settings does not allow advances.").format(
					frappe.format_value(remainder, {"fieldtype": "Currency"})
				)
			)
		rows.append(_party_row(cheque, remainder, side, is_advance="Yes"))

	return rows


def reversal_party_rows(cheque, settling_je):
	"""The settling entry's current party rows, debit and credit swapped.

	Returns (rows, advances). An invoice row keeps its invoice reference, which
	re-opens the invoice. An advance row cannot be reversed *against* the
	settling JE: ERPNext only lets a receivable row reference a Journal Entry
	when it is credited (a payable one when debited), and reversing a customer
	advance debits it. So the advance is reversed on account and returned in
	`advances`; `reconcile_advances` then matches the two in the Payment Ledger,
	so the customer is not left with an open advance and an open debit.
	"""
	rows, advances = [], []
	for r in frappe.get_all(
		"Journal Entry Account",
		filters={"parent": settling_je, "party": cheque.party, "account": cheque.party_account},
		fields=[
			"name", "debit_in_account_currency", "credit_in_account_currency",
			"reference_type", "reference_name", "is_advance", "cost_center",
		],
		order_by="idx",
	):
		amount = flt(r.debit_in_account_currency) or flt(r.credit_in_account_currency)
		side = "credit" if flt(r.debit_in_account_currency) else "debit"
		extra = {"cost_center": r.cost_center or cheque.cost_center}
		if r.reference_type in ("Sales Invoice", "Purchase Invoice"):
			extra.update(reference_type=r.reference_type, reference_name=r.reference_name)
		elif r.is_advance == "Yes" and not r.reference_type:
			advances.append(frappe._dict(
				voucher_type="Journal Entry", voucher_no=settling_je, voucher_detail_no=r.name, amount=amount,
				dr_or_cr=f"{_other(side)}_in_account_currency",
				cost_center=extra["cost_center"],
			))
		rows.append(_party_row(cheque, amount, side, **extra))
	if not rows:
		frappe.throw(_("Could not find the party rows of {0} to reverse.").format(settling_je))
	return rows, advances


def reconcile_advances(cheque, advances, reversal_je):
	"""Match each reversed advance against `reversal_je`.

	The same call Payment Reconciliation makes. Cancelling `reversal_je` (Undo
	Last Step) un-links it again, and ERPNext puts the advance back as open.

	A Journal Entry advance must reconcile, or the bounce fails. A Payment Entry
	advance is reconciled by re-saving that PE (ERPNext adds a reference row),
	which runs the PE's own update-after-submit hooks; if that refuses, the
	bounce still stands and the two stay open on account for Payment
	Reconciliation, with an Error Log naming the cheque.
	"""
	from erpnext.accounts.utils import reconcile_against_document

	for a in advances:
		args = frappe._dict(
			voucher_type=a.voucher_type or "Journal Entry", voucher_no=a.voucher_no,
			voucher_detail_no=a.voucher_detail_no,
			against_voucher_type="Journal Entry", against_voucher=reversal_je,
			account=cheque.party_account, party_type=cheque.party_type, party=cheque.party,
			is_advance="Yes", dr_or_cr=a.dr_or_cr, exchange_rate=1, difference_amount=0,
			unreconciled_amount=a.amount, unadjusted_amount=a.amount, allocated_amount=a.amount,
			grand_total=a.amount, outstanding_amount=a.amount, cost_center=a.cost_center,
		)
		if args.voucher_type == "Journal Entry":
			reconcile_against_document([args])
			continue
		frappe.db.savepoint("pdc_reconcile")
		try:
			reconcile_against_document([args])
		except Exception:
			frappe.db.rollback(save_point="pdc_reconcile")
			frappe.clear_last_message()
			frappe.log_error(
				title=f"PDC {cheque.name}: could not reconcile {a.voucher_no} with {reversal_je}",
				message=frappe.get_traceback(),
			)


# ── A cheque entered in Payment Entry ────────────────────────────────────────


def payment_entry_rows(cheque, payment_entry, swap, cap_to_outstanding=False):
	"""The Payment Entry's effect, rebuilt from its GL as Journal Entry rows.

	`swap=True` is the bounce: every GL row with debit and credit swapped — bank,
	party and any deductions (TDS and the like) — so the PE's whole effect is
	undone in one entry. `swap=False` is re-presenting the same cheque: the
	effect again, each invoice capped at what it still owes.

	Party rows: an invoice row keeps its invoice reference. The PE's own
	unallocated row (against_voucher = the PE) is its advance: reversed on
	account and returned in `advances` to reconcile, as for a JE advance.
	Returns (rows, advances).
	"""
	rows, advances = [], []
	for g in _payment_entry_gl(cheque, payment_entry):
		debit, credit = flt(g.debit_in_account_currency), flt(g.credit_in_account_currency)
		if swap:
			debit, credit = credit, debit
		side, amount = ("debit", debit) if debit else ("credit", credit)
		if not amount:
			continue
		cost_center = g.cost_center or cheque.cost_center

		if not g.party:
			rows.append(_plain_row(g.account, amount, side, cost_center))
			continue

		party_row = {"account": g.account, "party_type": g.party_type, "party": g.party,
			"cost_center": cost_center, f"{side}_in_account_currency": amount}
		if g.against_voucher_type in ("Sales Invoice", "Purchase Invoice") and g.against_voucher != payment_entry:
			if cap_to_outstanding:
				outstanding = max(flt(frappe.db.get_value(g.against_voucher_type, g.against_voucher, "outstanding_amount")), 0)
				if outstanding < amount:
					rest = amount - outstanding
					rows.append(dict(party_row, **{f"{side}_in_account_currency": rest, "is_advance": "Yes"}))
					amount = outstanding
					party_row[f"{side}_in_account_currency"] = amount
			if amount:
				party_row.update(reference_type=g.against_voucher_type, reference_name=g.against_voucher)
				rows.append(party_row)
		else:
			if not swap:
				party_row["is_advance"] = "Yes"
			elif g.against_voucher == payment_entry:
				advances.append(frappe._dict(
					voucher_type="Payment Entry", voucher_no=payment_entry, voucher_detail_no=None,
					amount=amount, dr_or_cr=f"{_other(side)}_in_account_currency", cost_center=cost_center,
				))
			rows.append(party_row)
	if not rows:
		frappe.throw(_("Payment Entry {0} has no ledger entries to work from.").format(payment_entry))
	return rows, advances


def _payment_entry_gl(cheque, payment_entry):
	"""The PE's GL rows as the payment posted them.

	When the PE books advances in a separate party account, reconciling its
	advance against this cheque's bounce entry makes ERPNext add a pair of rows
	to the PE: one against the bounce JE, and its offset against the PE itself.
	Neither is the payment, so both are left out.
	"""
	own_entries = set(frappe.get_all("Journal Entry", {"pdc_cheque": cheque.name}, pluck="name"))
	gl = frappe.get_all(
		"GL Entry",
		filters={"voucher_type": "Payment Entry", "voucher_no": payment_entry, "is_cancelled": 0},
		fields=["name", "account", "party_type", "party", "debit_in_account_currency", "credit_in_account_currency",
			"against_voucher_type", "against_voucher", "cost_center"],
		order_by="creation asc, name asc",
	)
	dropped = set()
	for g in gl:
		if g.against_voucher_type != "Journal Entry" or g.against_voucher not in own_entries:
			continue
		dropped.add(g.name)
		offset = next((
			o for o in reversed(gl)
			if o.name not in dropped and o.account == g.account and o.party == g.party
			and o.against_voucher == payment_entry
			and flt(o.debit_in_account_currency) == flt(g.credit_in_account_currency)
			and flt(o.credit_in_account_currency) == flt(g.debit_in_account_currency)
		), None)
		if offset:
			dropped.add(offset.name)
	return [g for g in gl if g.name not in dropped]


def payment_entry_bank_account(payment_entry):
	pe = frappe.db.get_value("Payment Entry", payment_entry, ["payment_type", "paid_to", "paid_from"], as_dict=True)
	return pe.paid_to if pe.payment_type == "Receive" else pe.paid_from


def post_represent(cheque, posting_date):
	"""A bounced Payment Entry cheque presented again: the PE's effect, dated today."""
	rows, _advances = payment_entry_rows(cheque, cheque.payment_entry, swap=False, cap_to_outstanding=True)
	name = make_journal_entry(cheque, posting_date, rows, _("Re-presented"), bank_entry=True)
	frappe.db.set_value("Journal Entry", name, "clearance_date", posting_date)
	return name


# ── Posting ───────────────────────────────────────────────────────────────────


def make_journal_entry(cheque, posting_date, rows, event, bank_entry=False, jv_type=None):
	"""Insert and submit one JE for `event`. Returns its name.

	`jv_type` is the JE's custom_p_type (its numbering series); the bounce dialog
	lets the user pick it, every other step uses PDC Settings → JV Type.
	"""
	je = frappe.new_doc("Journal Entry")
	je.update(
		{
			"company": cheque.company,
			"posting_date": posting_date,
			"voucher_type": "Bank Entry" if bank_entry else "Journal Entry",
			"cheque_no": cheque.cheque_no,
			"cheque_date": cheque.cheque_date,
			"user_remark": _("PDC {0}: cheque {1} {2} — {3}").format(
				cheque.name, cheque.cheque_no, cheque.party_name or cheque.party, event
			),
			"pdc_cheque": cheque.name,
			# Lets the Payment Entry list its bounce / re-present entries (Connections).
			"pdc_payment_entry": cheque.get("payment_entry"),
		}
	)
	jv_type = jv_type or frappe.db.get_single_value("PDC Settings", "jv_type")
	if jv_type and frappe.get_meta("Journal Entry").has_field("custom_p_type"):
		je.custom_p_type = jv_type

	for row in rows:
		row.setdefault("cost_center", cheque.cost_center)
		je.append("accounts", row)
	# Posting / Reference Miti come from utils/bs_miti.py on the JE's validate.
	je.flags.ignore_permissions = True
	try:
		je.insert()
	except frappe.MandatoryError as e:
		# The numbering engine fills custom_document_no only when the JV Type has
		# a Numbering Configuration rule for the company; the bare field name is
		# all ERPNext would say.
		if "custom_document_no" not in str(e):
			raise
		frappe.throw(
			_("Journal Type {0} has no numbering rule for {1}. Pick another Journal Type, or add a Numbering Configuration rule for it.").format(
				frappe.bold(je.get("custom_p_type") or _("(none)")), cheque.company
			),
			title=_("Journal Type not numbered"),
		)
	je.submit()
	_drop_advance_account_notice()
	return je.name


# ERPNext's JE validate_advance_accounts pops this up for any JE touching the
# company's default advance account. A bounce must reverse an advance booked
# there, and reconcile_advances does the matching the notice says is missing,
# so on the cheque's own entries it only alarms the user.
ADVANCE_ACCOUNT_NOTICE = "Making Journal Entries against advance accounts"


def _drop_advance_account_notice():
	log = getattr(frappe.local, "message_log", None)
	if log:
		frappe.local.message_log = [
			m for m in log if ADVANCE_ACCOUNT_NOTICE not in str(m.get("message") if isinstance(m, dict) else m)
		]


def post_settlement(cheque, posting_date, event, cap_to_outstanding=False):
	"""Receipt / issue / re-deposit: holding account against the party."""
	party_rows = settlement_party_rows(cheque, cap_to_outstanding=cap_to_outstanding)
	holding_side = _other(_settle_side(cheque))
	rows = party_rows + [_plain_row(holding_account(cheque), cheque.amount, holding_side, cheque.cost_center)]
	return make_journal_entry(cheque, posting_date, rows, event)


def post_clearance(cheque, posting_date, bank_account):
	"""Holding account into (or out of) the bank. Marked cleared for Bank Reconciliation."""
	hold = holding_account(cheque)
	if cheque.cheque_type == "Received":
		rows = [
			_plain_row(bank_account, cheque.amount, "debit", cheque.cost_center),
			_plain_row(hold, cheque.amount, "credit", cheque.cost_center),
		]
	else:
		rows = [
			_plain_row(hold, cheque.amount, "debit", cheque.cost_center),
			_plain_row(bank_account, cheque.amount, "credit", cheque.cost_center),
		]
	name = make_journal_entry(cheque, posting_date, rows, _("Cleared"), bank_entry=True)
	# The bank statement already shows it, so there is nothing left to reconcile.
	frappe.db.set_value("Journal Entry", name, "clearance_date", posting_date)
	return name


def post_bounce(cheque, posting_date, settling, after_clearance, bank_account,
		charges=0, recover_charges=False, jv_type=None):
	"""Undo the settlement: the party owes (or is owed) again, invoices re-open.

	Before clearing the money never left the holding account; after clearing it
	comes back out of the bank. Bank charges ride in the same entry.
	`settling` is (doctype, name): a Journal Entry, or the Payment Entry the
	cheque was entered in — whose own bank row is then the offset.
	"""
	settling_type, settling_name = settling
	if settling_type == "Payment Entry":
		rows, advances = payment_entry_rows(cheque, settling_name, swap=True)
	else:
		rows, advances = reversal_party_rows(cheque, settling_name)
		offset = bank_account if after_clearance else holding_account(cheque)
		offset_side = "credit" if cheque.cheque_type == "Received" else "debit"
		rows.append(_plain_row(offset, cheque.amount, offset_side, cheque.cost_center))

	charges = flt(charges)
	if charges > 0:
		if not bank_account:
			frappe.throw(_("A bank account is needed to book bounce charges."))
		if recover_charges and cheque.cheque_type == "Received":
			# On-account debit: the customer owes the charge too.
			rows.append(_party_row(cheque, charges, "debit"))
		else:
			expense = get_company_accounts(cheque.company, require_holding=False).bounce_charges_account
			if not expense:
				frappe.throw(_("Set a Bounce Charges account for {0} in PDC Settings.").format(cheque.company))
			rows.append(_plain_row(expense, charges, "debit", cheque.cost_center))
		rows.append(_plain_row(bank_account, charges, "credit", cheque.cost_center))

	name = make_journal_entry(
		cheque, posting_date, rows, _("Bounced"), bank_entry=bool(after_clearance or charges > 0),
		jv_type=jv_type,
	)
	reconcile_advances(cheque, advances, name)
	return name


def post_reversal(cheque, posting_date, settling, event):
	"""Return a received cheque, or stop an issued one, before it ever reached a bank."""
	rows, advances = reversal_party_rows(cheque, settling[1])
	side = "credit" if cheque.cheque_type == "Received" else "debit"
	rows.append(_plain_row(holding_account(cheque), cheque.amount, side, cheque.cost_center))
	name = make_journal_entry(cheque, posting_date, rows, event)
	reconcile_advances(cheque, advances, name)
	return name


def cancel_journal_entry(name):
	if not name or frappe.db.get_value("Journal Entry", name, "docstatus") != 1:
		return
	frappe.flags[INTERNAL_CANCEL_FLAG] = True
	try:
		je = frappe.get_doc("Journal Entry", name)
		je.flags.ignore_permissions = True
		je.cancel()
	finally:
		frappe.flags[INTERNAL_CANCEL_FLAG] = False
