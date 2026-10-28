"""LC accounting — the Journal Entry behind every money step of a Letter of Credit.

ERPNext has no LC: an import paid through a bank LC shows up only as a bank
payment to the supplier, so the margin the bank blocks, the commission, SWIFT
and amendment charges, and the exchange difference between the invoice rate and
the bank's settlement rate are all booked by hand, if at all — and the charges
rarely reach the stock's landed cost. Each money step here posts one Journal
Entry through two accounts set per company in LC Settings:

    margin deposit    Dr LC Margin               / Cr Bank
    bank charge       Dr LC Charges Clearing     / Cr Bank
    settlement        Dr Supplier (at the invoice's booked rate, against the
                         Purchase Invoice — or as an advance when none is linked)
                      Dr/Cr Exchange Gain/Loss   (bank rate − booked rate)
                                                 / Cr LC Margin (margin used)
                                                 / Cr Bank (the rest)
    margin release    Dr Bank                    / Cr LC Margin
    landed cost       a Landed Cost Voucher credits LC Charges Clearing and
                      loads the stock (`make_landed_cost_voucher`)

Usance acceptance posts nothing: the supplier stays in Accounts Payable at the
invoice rate until the bank pays at maturity, and the maturity is tracked on the
shipment row. Opening the LC posts nothing either — an LC is a bank promise,
not a payment.

Boundary: this module only builds and posts entries. Which step may run when,
and the LC's status and totals, belong to `lc/lifecycle.py`.

Landmines:
* Every entry goes through the app's Journal Entry numbering (`custom_p_type`
  → Numbering Configuration). LC Settings → JV Type picks the rule; without one
  the JE's mandatory `custom_document_no` stays empty and the step fails.
* The supplier row of a settlement against a Purchase Invoice is valued by
  ERPNext at the *invoice's* conversion rate whatever we pass
  (JournalEntry.set_exchange_rate), so the exchange row is computed from that
  same rate or the entry would not balance.
* The Company's Exchange Gain/Loss account must be set (one demo company has
  none) — the settlement refuses to post without it.
"""

import frappe
from frappe import _
from frappe.utils import flt

# Accounts made by "Create Missing Accounts": (LC Company Account field, account
# name, parent group's account_name, root type). Both are current assets: margin
# is the company's money held by the bank, and charges wait there to be
# capitalised into stock by a Landed Cost Voucher.
LC_ACCOUNTS = (
	("margin_account", "LC Margin", "Current Assets", "Asset"),
	("charges_account", "LC Charges Clearing", "Current Assets", "Asset"),
)

# Lets lc/guards.py tell this module's own cancel from a user's.
INTERNAL_CANCEL_FLAG = "lc_internal_cancel"


def get_company_accounts(company):
	row = next(
		(r for r in frappe.get_cached_doc("LC Settings").company_accounts if r.company == company),
		None,
	)
	if not row or not row.margin_account or not row.charges_account:
		frappe.throw(
			_("Set the LC Margin and LC Charges Clearing accounts for {0} in LC Settings first.").format(company),
			title=_("LC accounts missing"),
		)
	return row


def _row(account, amount, side, cost_center, **extra):
	row = {"account": account, "cost_center": cost_center, f"{side}_in_account_currency": flt(amount, 2)}
	row.update(extra)
	return row


def _cost_center(lc):
	return frappe.get_cached_value("Company", lc.company, "cost_center")


# ── Posting ───────────────────────────────────────────────────────────────────


def make_journal_entry(lc, posting_date, rows, event, bank_entry=True):
	"""Insert and submit one JE for `event`. Returns its name."""
	je = frappe.new_doc("Journal Entry")
	je.update(
		{
			"company": lc.company,
			"posting_date": posting_date,
			"voucher_type": "Bank Entry" if bank_entry else "Journal Entry",
			# A Bank Entry needs a reference; the bank's LC number is the one
			# that appears on its advice.
			"cheque_no": lc.lc_no or lc.name,
			"cheque_date": posting_date,
			"user_remark": _("LC {0} ({1}), {2}: {3}").format(
				lc.lc_no or _("not opened"), lc.name, lc.supplier_name or lc.supplier, event
			),
			"letter_of_credit": lc.name,
			"multi_currency": int(any(
				frappe.get_cached_value("Account", r["account"], "account_currency") != lc.company_currency
				for r in rows
			)),
		}
	)
	jv_type = frappe.db.get_single_value("LC Settings", "jv_type")
	if jv_type and frappe.get_meta("Journal Entry").has_field("custom_p_type"):
		je.custom_p_type = jv_type

	for row in rows:
		je.append("accounts", row)
	# Posting / Reference Miti come from utils/bs_miti.py on the JE's validate.
	je.flags.ignore_permissions = True
	try:
		je.insert()
	except frappe.MandatoryError as e:
		if "custom_document_no" not in str(e):
			raise
		frappe.throw(
			_("Journal Type {0} has no numbering rule for {1}. Set another JV Type in LC Settings, or add a Numbering Configuration rule for it.").format(
				frappe.bold(je.get("custom_p_type") or _("(none)")), lc.company
			),
			title=_("Journal Type not numbered"),
		)
	je.submit()
	# The bank's advice is the statement line: nothing left to reconcile.
	frappe.db.set_value("Journal Entry", je.name, "clearance_date", posting_date)
	return je.name


def post_margin(lc, posting_date, amount, bank_account):
	"""Margin the bank blocks out of the company's account."""
	cc = _cost_center(lc)
	margin = get_company_accounts(lc.company).margin_account
	rows = [_row(margin, amount, "debit", cc), _row(bank_account, amount, "credit", cc)]
	return make_journal_entry(lc, posting_date, rows, _("Margin deposited"))


def post_margin_release(lc, posting_date, amount, bank_account):
	"""Unused margin back into the company's account when the LC closes."""
	cc = _cost_center(lc)
	margin = get_company_accounts(lc.company).margin_account
	rows = [_row(bank_account, amount, "debit", cc), _row(margin, amount, "credit", cc)]
	return make_journal_entry(lc, posting_date, rows, _("Margin released"))


def post_charge(lc, posting_date, amount, bank_account, label):
	cc = _cost_center(lc)
	clearing = get_company_accounts(lc.company).charges_account
	rows = [_row(clearing, amount, "debit", cc), _row(bank_account, amount, "credit", cc)]
	return make_journal_entry(lc, posting_date, rows, label)


def settlement_values(lc, shipment, exchange_rate, margin_applied):
	"""What a settlement would post, without posting it.

	Returns a dict: supplier account and the amount in its currency, the
	booked rate, the bank's debit in company currency (margin included), the
	part taken from the bank account, and the exchange difference (+ = loss).
	"""
	from erpnext.accounts.party import get_party_account

	fc_amount = flt(shipment.amount, 2)
	bank_total = flt(fc_amount * flt(exchange_rate), 2)
	margin_applied = flt(margin_applied, 2)
	if margin_applied > bank_total:
		frappe.throw(_("Margin used ({0}) cannot be more than the bank's debit ({1}).").format(margin_applied, bank_total))

	invoice = None
	if shipment.purchase_invoice:
		invoice = frappe.db.get_value(
			"Purchase Invoice", shipment.purchase_invoice,
			["credit_to", "conversion_rate", "currency", "docstatus", "outstanding_amount"], as_dict=True,
		)
		if not invoice or invoice.docstatus != 1:
			frappe.throw(_("Purchase Invoice {0} is not submitted.").format(shipment.purchase_invoice))
		account = invoice.credit_to
		booked_rate = flt(invoice.conversion_rate)
	else:
		account = get_party_account("Supplier", lc.supplier, lc.company)
		booked_rate = flt(exchange_rate)

	account_currency = frappe.get_cached_value("Account", account, "account_currency")
	if account_currency == lc.company_currency:
		supplier_amount = flt(fc_amount * booked_rate, 2)
		supplier_company_amount = supplier_amount
	elif account_currency == lc.currency:
		supplier_amount = fc_amount
		supplier_company_amount = flt(fc_amount * booked_rate, 2)
	else:
		frappe.throw(
			_("Supplier account {0} is in {1}; an LC in {2} can only settle a payable in {2} or {3}.").format(
				account, account_currency, lc.currency, lc.company_currency
			)
		)

	return frappe._dict(
		account=account,
		account_currency=account_currency,
		booked_rate=booked_rate,
		supplier_amount=supplier_amount,
		supplier_company_amount=supplier_company_amount,
		bank_total=bank_total,
		bank_paid=flt(bank_total - margin_applied, 2),
		margin_applied=margin_applied,
		exchange_difference=flt(bank_total - supplier_company_amount, 2),
		invoice=shipment.purchase_invoice,
	)


def post_settlement(lc, shipment, posting_date, exchange_rate, bank_account, margin_applied):
	"""The bank pays the supplier for one shipment. Returns (je_name, values)."""
	cc = _cost_center(lc)
	v = settlement_values(lc, shipment, exchange_rate, margin_applied)

	supplier_row = _row(
		v.account, v.supplier_amount, "debit", cc,
		party_type="Supplier", party=lc.supplier, exchange_rate=v.booked_rate if v.account_currency != lc.company_currency else 1,
	)
	if v.invoice:
		supplier_row.update(reference_type="Purchase Invoice", reference_name=v.invoice)
	else:
		supplier_row["is_advance"] = "Yes"
	rows = [supplier_row]

	if abs(v.exchange_difference) >= 0.01:
		gain_loss = frappe.get_cached_value("Company", lc.company, "exchange_gain_loss_account")
		if not gain_loss:
			frappe.throw(
				_("Set the Exchange Gain / Loss Account on Company {0}: this settlement has an exchange difference of {1}.").format(
					lc.company, v.exchange_difference
				),
				title=_("Exchange account missing"),
			)
		side = "debit" if v.exchange_difference > 0 else "credit"
		rows.append(_row(gain_loss, abs(v.exchange_difference), side, cc))

	if v.margin_applied > 0:
		rows.append(_row(get_company_accounts(lc.company).margin_account, v.margin_applied, "credit", cc))
	if v.bank_paid > 0:
		rows.append(_row(bank_account, v.bank_paid, "credit", cc))

	name = make_journal_entry(
		lc, posting_date, rows,
		_("Shipment {0} settled at {1}").format(shipment.shipment_no, flt(exchange_rate)),
	)
	return name, v


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


# ── Landed cost ───────────────────────────────────────────────────────────────


def capitalised_charges(lc):
	"""Charges already moved into stock by submitted Landed Cost Vouchers of this LC."""
	clearing = get_company_accounts(lc.company).charges_account
	return flt(frappe.db.sql(
		"""select sum(t.base_amount) from `tabLanded Cost Taxes and Charges` t
		join `tabLanded Cost Voucher` v on v.name = t.parent
		where v.docstatus = 1 and v.letter_of_credit = %s and t.expense_account = %s""",
		(lc.name, clearing),
	)[0][0])


@frappe.whitelist()
def make_landed_cost_voucher(name):
	"""Draft Landed Cost Voucher: the LC's receipts, and its charges not yet capitalised."""
	lc = frappe.get_doc("Letter of Credit", name)
	lc.check_permission("read")
	frappe.has_permission("Landed Cost Voucher", "create", throw=True)
	clearing = get_company_accounts(lc.company).charges_account
	pending = flt(lc.charges_total) - capitalised_charges(lc)
	if pending < 0.01:
		frappe.throw(_("All bank charges of {0} are already in a Landed Cost Voucher.").format(lc.name))

	receipts = []
	for s in lc.shipments:
		if s.purchase_receipt:
			receipts.append(("Purchase Receipt", s.purchase_receipt))
		elif s.purchase_invoice and frappe.db.get_value("Purchase Invoice", s.purchase_invoice, "update_stock"):
			receipts.append(("Purchase Invoice", s.purchase_invoice))
	if not receipts:
		frappe.throw(_("Link a Purchase Receipt (or a stock-updating Purchase Invoice) to a shipment first."))

	lcv = frappe.new_doc("Landed Cost Voucher")
	lcv.company = lc.company
	lcv.letter_of_credit = lc.name
	lcv.distribute_charges_based_on = "Amount"
	for doctype, docname in dict.fromkeys(receipts):
		doc = frappe.db.get_value(doctype, docname, ["supplier", "posting_date", "base_grand_total"], as_dict=True)
		lcv.append("purchase_receipts", {
			"receipt_document_type": doctype, "receipt_document": docname,
			"supplier": doc.supplier, "posting_date": doc.posting_date, "grand_total": doc.base_grand_total,
		})
	lcv.append("taxes", {
		"description": _("Bank charges of LC {0} ({1})").format(lc.lc_no or lc.name, lc.name),
		"expense_account": clearing,
		"account_currency": lc.company_currency,
		"exchange_rate": 1,
		"amount": pending,
		"base_amount": pending,
	})
	lcv.get_items_from_purchase_receipts()
	out = lcv.as_dict()
	out.update({"name": None, "__islocal": 1, "__unsaved": 1, "docstatus": 0})
	for table in lcv.meta.get_table_fields():
		for row in out.get(table.fieldname) or []:
			row.update({"name": None, "parent": None, "__islocal": 1, "docstatus": 0})
	return out
