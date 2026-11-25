"""LC accounting — the Journal Entry behind every money step of a Letter of Credit.

An import LC is kept the way Nepali importers keep an "LC account": every rupee
the import costs is debited to one ledger, LC Goods in Transit, until the goods
arrive; then the whole balance moves into stock or fixed assets at landed cost
(lc/transfer.py). Without it the bank's commission, SWIFT and amendment
charges, the marine insurance, the duty and the freight to the border land in
expense accounts and never reach the stock's value.

    margin deposit       Dr LC Margin                  / Cr Bank
    a cost (Add Cost)    Dr LC Goods in Transit (cost)
                         Dr Input VAT (VAT, if any)    / Cr Bank, or Cr the party on credit
    goods, sight         Dr LC Goods in Transit (LC amount × bank rate)
                                                       / Cr LC Margin (margin used) / Cr Bank
    goods, usance        accept the bill:  Dr LC Goods in Transit / Cr Supplier (at the acceptance rate)
                         pay at maturity:  Dr Supplier (acceptance rate)
                                           Dr/Cr Exchange Gain/Loss (bank rate − acceptance rate)
                                                       / Cr LC Margin / Cr Bank
    margin release       Dr Bank                       / Cr LC Margin
    residual on close    Dr/Cr the chosen account      / Cr/Dr LC Goods in Transit

The exchange difference of a usance bill goes to profit and loss, not into the
cost: the goods are valued at the rate on the day the liability arose.

Boundary: this module only builds and posts entries. Which step may run when,
and the LC's totals, belong to `lc/lifecycle.py`; the transfer to stock or
assets to `lc/transfer.py`.

Landmines:
* Every entry goes through the app's Journal Entry numbering (`custom_p_type`
  → Numbering Configuration). LC Settings → JV Type picks the rule; without one
  the JE's mandatory `custom_document_no` stays empty and the step fails.
* A supplier payable in the LC's currency (a USD creditor) is valued at the
  rate we pass; ERPNext only overrides the rate on rows that reference an
  invoice, and these never do.
"""

import frappe
from frappe import _
from frappe.utils import flt

# Accounts made by "Create Missing Accounts": (LC Company Account field, account
# name, parent group's account_name, root type). Both are current assets: margin
# is the company's money held by the bank, and goods in transit is the import's
# cost waiting to become stock or an asset.
LC_ACCOUNTS = (
	("margin_account", "LC Margin", "Current Assets", "Asset"),
	("transit_account", "LC Goods in Transit", "Current Assets", "Asset"),
)

# Lets lc/guards.py tell this module's own cancel from a user's.
INTERNAL_CANCEL_FLAG = "lc_internal_cancel"


def get_company_accounts(company):
	row = next(
		(r for r in frappe.get_cached_doc("LC Settings").company_accounts if r.company == company),
		None,
	)
	if not row or not row.margin_account or not row.transit_account:
		frappe.throw(
			_("Set the LC Margin and LC Goods in Transit accounts for {0} in LC Settings first.").format(company),
			title=_("LC accounts missing"),
		)
	return row


def vat_account(company):
	account = get_company_accounts(company).vat_account
	if not account:
		frappe.throw(_("Set the Input VAT account for {0} in LC Settings first.").format(company),
			title=_("VAT account missing"))
	return account


def _row(account, amount, side, cost_center, **extra):
	row = {"account": account, "cost_center": cost_center, f"{side}_in_account_currency": flt(amount, 2)}
	row.update(extra)
	return row


def cost_center(lc):
	return frappe.get_cached_value("Company", lc.company, "cost_center")


def supplier_payable(company, supplier, lc_currency, company_currency):
	"""(account, account currency) of a supplier's payable, refusing a third currency."""
	from erpnext.accounts.party import get_party_account

	account = get_party_account("Supplier", supplier, company)
	currency = frappe.get_cached_value("Account", account, "account_currency")
	if currency not in (company_currency, lc_currency):
		frappe.throw(_("Supplier account {0} is in {1}; it must be in {2} or {3}.").format(
			account, currency, company_currency, lc_currency))
	return account, currency


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
				lc.lc_no or "-", lc.name, lc.supplier_name or lc.supplier, event
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
	if bank_entry:
		# The bank's advice is the statement line: nothing left to reconcile.
		frappe.db.set_value("Journal Entry", je.name, "clearance_date", posting_date)
	return je.name


def post_margin(lc, posting_date, amount, bank_account):
	"""Margin the bank blocks out of the company's account."""
	cc = cost_center(lc)
	margin = get_company_accounts(lc.company).margin_account
	rows = [_row(margin, amount, "debit", cc), _row(bank_account, amount, "credit", cc)]
	return make_journal_entry(lc, posting_date, rows, _("Margin deposited"))


def post_margin_release(lc, posting_date, amount, bank_account):
	"""Unused margin back into the company's account when the LC closes."""
	cc = cost_center(lc)
	margin = get_company_accounts(lc.company).margin_account
	rows = [_row(bank_account, amount, "debit", cc), _row(margin, amount, "credit", cc)]
	return make_journal_entry(lc, posting_date, rows, _("Margin released"))


def post_cost(lc, posting_date, label, amount, vat_amount, bank_account=None, party=None):
	"""One cost: the cost into Goods in Transit, VAT to input VAT; paid by bank or owed to a party.

	`amount` is the part that goes into the landed cost, `vat_amount` the
	claimable VAT; either may be 0 but not both.
	"""
	cc = cost_center(lc)
	accounts = get_company_accounts(lc.company)
	total = flt(flt(amount, 2) + flt(vat_amount, 2), 2)
	rows = []
	if flt(amount) > 0:
		rows.append(_row(accounts.transit_account, amount, "debit", cc))
	if flt(vat_amount) > 0:
		rows.append(_row(vat_account(lc.company), vat_amount, "debit", cc))
	if party:
		account, currency = supplier_payable(lc.company, party, lc.company_currency, lc.company_currency)
		rows.append(_row(account, total, "credit", cc, party_type="Supplier", party=party))
		return make_journal_entry(lc, posting_date, rows, label, bank_entry=False)
	rows.append(_row(bank_account, total, "credit", cc))
	return make_journal_entry(lc, posting_date, rows, label)


def post_goods_payment(lc, posting_date, fc_amount, exchange_rate, margin_used, bank_account):
	"""Sight: the bank pays the supplier; the goods' value goes into Goods in Transit."""
	cc = cost_center(lc)
	accounts = get_company_accounts(lc.company)
	total = flt(flt(fc_amount) * flt(exchange_rate), 2)
	margin_used = flt(margin_used, 2)
	if margin_used > total:
		frappe.throw(_("Margin used ({0}) cannot be more than the payment ({1}).").format(margin_used, total))
	rows = [_row(accounts.transit_account, total, "debit", cc)]
	if margin_used > 0:
		rows.append(_row(accounts.margin_account, margin_used, "credit", cc))
	if total - margin_used > 0:
		rows.append(_row(bank_account, total - margin_used, "credit", cc))
	je = make_journal_entry(lc, posting_date, rows,
		_("Goods paid: {0} {1} at {2}").format(lc.currency, flt(fc_amount, 2), flt(exchange_rate)))
	return je, total


def post_acceptance(lc, posting_date, fc_amount, exchange_rate):
	"""Usance: the company accepts the bill; the supplier is owed it until maturity."""
	cc = cost_center(lc)
	accounts = get_company_accounts(lc.company)
	total = flt(flt(fc_amount) * flt(exchange_rate), 2)
	account, currency = supplier_payable(lc.company, lc.supplier, lc.currency, lc.company_currency)
	supplier_amount = flt(fc_amount, 2) if currency == lc.currency else total
	rows = [
		_row(accounts.transit_account, total, "debit", cc),
		_row(account, supplier_amount, "credit", cc, party_type="Supplier", party=lc.supplier,
			exchange_rate=flt(exchange_rate) if currency == lc.currency else 1),
	]
	je = make_journal_entry(lc, posting_date, rows,
		_("Bill accepted: {0} {1} at {2}").format(lc.currency, flt(fc_amount, 2), flt(exchange_rate)),
		bank_entry=False)
	return je, total


def maturity_values(lc, acceptance, exchange_rate, margin_used):
	"""What paying an accepted bill at `exchange_rate` would post, without posting it."""
	booked = flt(acceptance.amount, 2)
	bank_total = flt(flt(acceptance.fc_amount) * flt(exchange_rate), 2)
	margin_used = flt(margin_used, 2)
	if margin_used > bank_total:
		frappe.throw(_("Margin used ({0}) cannot be more than the bank's debit ({1}).").format(margin_used, bank_total))
	return frappe._dict(
		booked=booked, booked_rate=flt(acceptance.exchange_rate), bank_total=bank_total,
		margin_used=margin_used, bank_paid=flt(bank_total - margin_used, 2),
		exchange_difference=flt(bank_total - booked, 2),
	)


def post_maturity_payment(lc, acceptance, posting_date, exchange_rate, margin_used, bank_account):
	"""The bank pays an accepted bill at maturity. Returns (je_name, values)."""
	cc = cost_center(lc)
	accounts = get_company_accounts(lc.company)
	v = maturity_values(lc, acceptance, exchange_rate, margin_used)
	account, currency = supplier_payable(lc.company, lc.supplier, lc.currency, lc.company_currency)
	supplier_row = _row(
		account, flt(acceptance.fc_amount, 2) if currency == lc.currency else v.booked, "debit", cc,
		party_type="Supplier", party=lc.supplier,
		exchange_rate=v.booked_rate if currency == lc.currency else 1,
		reference_type="Journal Entry", reference_name=acceptance.journal_entry,
	)
	rows = [supplier_row]
	if abs(v.exchange_difference) >= 0.01:
		gain_loss = frappe.get_cached_value("Company", lc.company, "exchange_gain_loss_account")
		if not gain_loss:
			frappe.throw(
				_("Set the Exchange Gain / Loss Account on Company {0}: this payment has an exchange difference of {1}.").format(
					lc.company, v.exchange_difference),
				title=_("Exchange account missing"),
			)
		rows.append(_row(gain_loss, abs(v.exchange_difference), "debit" if v.exchange_difference > 0 else "credit", cc))
	if v.margin_used > 0:
		rows.append(_row(accounts.margin_account, v.margin_used, "credit", cc))
	if v.bank_paid > 0:
		rows.append(_row(bank_account, v.bank_paid, "credit", cc))
	je = make_journal_entry(lc, posting_date, rows,
		_("Bill paid at maturity: {0} {1} at {2}").format(lc.currency, flt(acceptance.fc_amount, 2), flt(exchange_rate)))
	return je, v


def transit_balance(lc):
	"""What LC Goods in Transit still holds for this LC, from the GL (Dr − Cr)."""
	account = get_company_accounts(lc.company).transit_account
	return flt(frappe.db.sql(
		"""select sum(g.debit) - sum(g.credit) from `tabGL Entry` g
		where g.account = %(account)s and g.is_cancelled = 0 and (
			(g.voucher_type = 'Journal Entry' and g.voucher_no in
				(select name from `tabJournal Entry` where letter_of_credit = %(lc)s and docstatus = 1))
			or (g.voucher_type = 'Stock Entry' and g.voucher_no in
				(select name from `tabStock Entry` where letter_of_credit = %(lc)s and docstatus = 1)))""",
		{"account": account, "lc": lc.name},
	)[0][0], 2)


def post_residual(lc, posting_date, amount, account):
	"""Clear what is left in Goods in Transit (a late cost, rounding) to `account` on close."""
	cc = cost_center(lc)
	transit = get_company_accounts(lc.company).transit_account
	if amount > 0:
		rows = [_row(account, amount, "debit", cc), _row(transit, amount, "credit", cc)]
	else:
		rows = [_row(transit, -amount, "debit", cc), _row(account, -amount, "credit", cc)]
	return make_journal_entry(lc, posting_date, rows, _("Goods in Transit cleared on close"), bank_entry=False)


def cancel_journal_entry(name):
	if not name or frappe.db.get_value("Journal Entry", name, "docstatus") != 1:
		return
	frappe.flags[INTERNAL_CANCEL_FLAG] = True
	try:
		je = frappe.get_doc("Journal Entry", name)
		je.flags.ignore_permissions = True
		je.flags.ignore_links = True  # the LC's own rows still point at it
		je.cancel()
	finally:
		frappe.flags[INTERNAL_CANCEL_FLAG] = False
