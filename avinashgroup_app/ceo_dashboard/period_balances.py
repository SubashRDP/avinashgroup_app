"""Opening balance and movement of one period, for the CEO Dashboard's Money
figures when the period is a week, a month or a quarter.

money.py keeps ledger balances at month ends, which suits a year: the Money
charts draw the opening and each month end. For a shorter period the CEO does
not want the year's months (2026-11-11): only what the period opened with and
what happened in it, and no closing figure. A week's first day is not a month
end, so this reads the ledger for the exact dates:

- opening: the balance at the end of the day before `from_date`;
- in the period (`from_date`..`to_date`): debits and credits, apart.

Per account for cash and bank (and bank loans), per customer for receivables,
per supplier for payables, so the page can apply its company, segment,
customer, district and inter-company filters. What the two movements mean:

    cash and bank   debit = came in        credit = went out
                    (less transfers between our own cash / bank accounts)
    bank loans      credit = borrowed      debit = repaid
    customers       debit = billed         credit = received / credited
    suppliers       credit = billed to us  debit = paid / debited

Accounts are classified as in money.py (the same rules, repeated here because
money._build keeps them inline). Read-only. See docs/ceo-dashboard.md.
"""

import hashlib

import frappe
from frappe import _
from frappe.utils import getdate

from avinashgroup_app.ceo_dashboard import api, money

CACHE_SECONDS = 1800

# Longest period served: a quarter of BS months is at most 96 days.
MAX_DAYS = 100

_MOVES = (
	"SUM(IF(g.posting_date < %(a)s, g.debit - g.credit, 0)), "
	"SUM(IF(g.posting_date >= %(a)s, g.debit, 0)), "
	"SUM(IF(g.posting_date >= %(a)s, g.credit, 0))"
)


@frappe.whitelist()
def get_period_balances(fiscal_year, from_date, to_date, years_back=None):
	"""Opening balance (before `from_date`) and debits / credits within
	`from_date`..`to_date`, per cash or bank account, customer and supplier."""
	frappe.only_for(api.ROLES)
	companies = api._companies()
	if not companies:
		frappe.throw(_("You do not have access to any company."))
	names = tuple(c["name"] for c in companies)
	years = api._fiscal_years(fiscal_year, years_back)
	first = getdate(years[-1].year_start_date)
	through = money._through(years, names)
	a, b = getdate(from_date), getdate(to_date)
	if not (first <= a <= b <= through) or (b - a).days >= MAX_DAYS:
		frappe.throw(_("Pick a period of up to {0} days between {1} and {2}.").format(MAX_DAYS, first, through))

	key = "ceo_dashboard:period_balances:v2:{}:{}:{}".format(
		a.isoformat(), b.isoformat(), hashlib.md5("|".join(names).encode()).hexdigest()
	)
	cached = frappe.cache.get_value(key)
	if cached:
		return cached
	out = _build(companies, a, b)
	frappe.cache.set_value(key, out, expires_in_sec=CACHE_SECONDS)
	return out


def _build(companies, a, b):
	names = tuple(c["name"] for c in companies)
	co_idx = {c["name"]: i for i, c in enumerate(companies)}
	group_names = [api._name_tokens(n) for n in frappe.get_all("Company", pluck="name")]
	params = {"a": a, "b": b}
	frappe.db.sql("SET SESSION SQL_BIG_SELECTS = 1")

	# Cash (0), bank (1) and bank loans (2), classified as money.py does.
	accounts = {}
	for name, company, account_name, root, atype in frappe.db.sql(
		"""SELECT name, company, account_name, root_type, account_type FROM `tabAccount`
		WHERE is_group = 0 AND company IN %s AND account_type IN ('Cash', 'Bank')""",
		(names,),
	):
		if root == "Asset":
			kind = 0 if atype == "Cash" else 1
		elif root == "Liability" and not api._is_group_company(account_name, group_names):
			kind = 2
		else:
			continue
		accounts[name] = (co_idx[company], kind, account_name)

	cash = []
	if accounts:
		for account, opening, dr, cr in frappe.db.sql(
			f"""SELECT g.account, {_MOVES} FROM `tabGL Entry` g
			WHERE g.is_cancelled = 0 AND g.account IN %(accounts)s AND g.posting_date <= %(b)s
			GROUP BY g.account""",
			{**params, "accounts": tuple(accounts)},
		):
			co, kind, label = accounts[account]
			opening, dr, cr = float(opening or 0), float(dr or 0), float(cr or 0)
			if kind == 2:
				opening, dr, cr = -opening, cr, dr   # loans: opening owed, borrowed, repaid
			if round(opening) or round(dr) or round(cr):
				cash.append([co, kind, label, round(opening), round(dr), round(cr)])

	# Money moved between our own cash and bank accounts (a cash deposit, a
	# bank-to-bank transfer) debits one of them and credits another in the same
	# voucher. It neither came in nor went out, so the page takes it off both
	# sides: per company, the smaller of a voucher's debits and credits on
	# cash / bank accounts.
	transfers = []
	own = tuple(name for name, (_co, kind, _label) in accounts.items() if kind < 2)
	if own:
		for company, amount in frappe.db.sql(
			"""SELECT t.company, SUM(LEAST(t.dr, t.cr)) FROM (
				SELECT g.company, SUM(g.debit) dr, SUM(g.credit) cr FROM `tabGL Entry` g
				WHERE g.is_cancelled = 0 AND g.account IN %(accounts)s AND g.posting_date BETWEEN %(a)s AND %(b)s
				GROUP BY g.company, g.voucher_type, g.voucher_no
				HAVING dr > 0 AND cr > 0) t
			GROUP BY t.company""",
			{**params, "accounts": own},
		):
			if round(float(amount or 0)):
				transfers.append([co_idx[company], round(float(amount))])

	def party_rows(party_type, account_type):
		accts = frappe.db.sql(
			"SELECT name FROM `tabAccount` WHERE is_group = 0 AND company IN %s AND account_type = %s",
			(names, account_type),
			pluck=True,
		)
		if not accts:
			return []
		return frappe.db.sql(
			f"""SELECT g.company, g.party, {_MOVES} FROM `tabGL Entry` g
			WHERE g.is_cancelled = 0 AND g.party_type = %(pt)s AND g.account IN %(accounts)s AND g.posting_date <= %(b)s
			GROUP BY g.company, g.party""",
			{**params, "pt": party_type, "accounts": tuple(accts)},
		)

	recv_raw = [r for r in party_rows("Customer", "Receivable") if r[1]]
	info = {}
	codes = tuple({r[1] for r in recv_raw})
	if codes:
		for code, cname, group, internal in frappe.db.sql(
			"""SELECT c.name, c.customer_name, IFNULL(cg.customer_group_name, ''), c.is_internal_customer
			FROM `tabCustomer` c LEFT JOIN `tabCustomer Group` cg ON cg.name = c.customer_group
			WHERE c.name IN %s""",
			(codes,),
		):
			info[code] = (cname or code, api._segment(group), 1 if internal or api._is_group_company(cname, group_names) else 0)
	recv = []
	for company, code, opening, dr, cr in recv_raw:
		opening, dr, cr = round(float(opening or 0)), round(float(dr or 0)), round(float(cr or 0))
		if opening or dr or cr:
			cname, seg, internal = info.get(code, (code, len(api.SEGMENTS) - 1, 0))
			recv.append([co_idx[company], code, cname, seg, internal, opening, dr, cr])

	pay_raw = [r for r in party_rows("Supplier", "Payable") if r[1]]
	sinfo = {}
	codes = tuple({r[1] for r in pay_raw})
	if codes:
		for code, sname, internal in frappe.db.sql(
			"SELECT name, supplier_name, is_internal_supplier FROM `tabSupplier` WHERE name IN %s", (codes,)
		):
			sinfo[code] = (sname or code, 1 if internal or api._is_group_company(sname, group_names) else 0)
	pay = []
	for company, code, opening, dr, cr in pay_raw:
		opening, dr, cr = -round(float(opening or 0)), round(float(dr or 0)), round(float(cr or 0))
		if opening or dr or cr:
			sname, internal = sinfo.get(code, (code, 0))
			pay.append([co_idx[company], code, sname, internal, opening, cr, dr])

	return {
		"version": 2,
		"from": a.isoformat(),
		"to": b.isoformat(),
		# [company, 0 cash / 1 bank / 2 bank loan, account, opening, came in (loan: borrowed), went out (loan: repaid)]
		"cash": cash,
		# [company, Rs moved between its own cash / bank accounts in the period]
		"transfers": transfers,
		# [company, customer code, name, segment, inter-company, opening (+ owed / - advance), billed, received]
		"recv": recv,
		# [company, supplier code, name, inter-company, opening (+ we owe / - advance), billed to us, paid]
		"pay": pay,
		"generated": frappe.utils.now(),
	}
