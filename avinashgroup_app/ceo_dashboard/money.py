"""Money figures for the CEO Dashboard: cash and bank, bank loans, what
customers owe us, what we owe suppliers, and the gas margin per kg.

Why a separate endpoint: the sales fact table (api.py) is cheap to cache and
the page must not wait for the ledger. These figures come from the GL (~1M GL
Entries on demo-nggroup, ~6 s cold), so the page asks for them in a second
call and fills the money tiles when they arrive.

What the figures are, exactly
-----------------------------
- Cash and bank: GL balance of leaf accounts with root type Asset and account
  type Cash or Bank. Account type "Bank" is also set on term / HP / TR loans
  (root type Liability, so they can be picked in a Payment Entry) and on
  inter-company current accounts; those are NOT cash. Loans are reported
  separately as "bank loans"; an account whose name is one of our companies
  is inter-company and left out.
- Customers owe us / we owe suppliers: GL balance per party on Receivable /
  Payable accounts. Positive = owed, negative = advance. This is the ledger's
  view of every party; the "Credit and dues" section is credit control's view
  of customers with limits (credit_snapshot.py) and differs from it by design.
- Gas margin per kg: sale price minus purchase price of goods sold by the Kg.
  The Stock Ledger cannot be used: every Sales Invoice stock entry on these
  sites has valuation rate 0, so cost of goods sold reads as zero. Purchase
  price = Purchase Invoice items in Kg, per company per fiscal month. Months
  without gas purchase bills have no margin; the page says how much of the
  volume the margin covers.

Balances are "as of" the dashboard's data-through day (api._data_through), and
at every fiscal month end on the 36-month timeline, so a balance can be drawn
as a trend and compared with a year earlier.

Deliberately not here: fixing anything. The books on the data copies contain
figures that cannot be right (a Rs 1,130 Cr test Purchase Invoice, a bank
account at minus Rs 113 Cr, Rs 116 Cr "cash in hand"). They are shown as they
are, without flags or commentary (the user's decision, 2026-11-09); the
people who own the books fix them.

Read-only. See docs/ceo-dashboard.md.
"""

import bisect
import datetime
import hashlib

import frappe
from frappe.utils import add_years, getdate, today

from avinashgroup_app.ceo_dashboard import api

# Cold build ~6 s on demo-nggroup; balances barely move minute to minute.
CACHE_SECONDS = 1800

# Suppliers sent with their largest open bill (the rest are summed per company).
TOP_SUPPLIERS = 40


@frappe.whitelist()
def get_money(fiscal_year=None, force=0, years_back=None):
	"""Balances and gas purchase cost for the CEO Dashboard. Same companies,
	timeline and data-through day as api.get_dashboard."""
	frappe.only_for(api.ROLES)
	companies = api._companies()
	if not companies:
		frappe.throw(frappe._("You do not have access to any company."))
	years = api._fiscal_years(fiscal_year, years_back)   # same timeline as get_dashboard
	key = "ceo_dashboard:money:v1:{}:{}:{}".format(
		years[0].name, len(years) - 1, hashlib.md5("|".join(c["name"] for c in companies).encode()).hexdigest()
	)
	if not int(force or 0):
		cached = frappe.cache.get_value(key)
		if cached:
			return cached
	out = _build(years, companies)
	frappe.cache.set_value(key, out, expires_in_sec=CACHE_SECONDS)
	return out


def _through(years, names):
	cur = years[0]
	cur_start, cur_end = getdate(cur.year_start_date), getdate(cur.year_end_date)
	upto = min(getdate(today()), cur_end)
	return api._data_through(cur_start, upto, names) if upto >= cur_start else cur_end


def _balance_columns(points, sign="g.debit - g.credit"):
	"""SQL for one balance column per date in `points` (balance on that day)."""
	return ", ".join(f"SUM(IF(g.posting_date <= %s, {sign}, 0))" for _p in points)


def _build(years, companies):
	names = tuple(c["name"] for c in companies)
	co_idx = {c["name"]: i for i, c in enumerate(companies)}
	through = _through(years, names)
	through_ly = getdate(add_years(through, -1))
	bounds = api._month_bounds(years)
	# Balance points: every month end up to the data-through month, then the
	# data-through day itself and the same day a year earlier.
	month_ends = [getdate(e) for _s, e in bounds]
	last_month = next(i for i, (s, e) in enumerate(bounds) if getdate(s) <= through <= getdate(e))
	points = [min(month_ends[i], through) for i in range(last_month + 1)] + [through, through_ly]
	n_months = last_month + 1

	group_names = [api._name_tokens(n) for n in frappe.get_all("Company", pluck="name")]

	# ------------------------------------------------ cash, bank and loans
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

	cash_rows = []
	if accounts:
		for row in frappe.db.sql(
			f"""SELECT g.account, {_balance_columns(points)}
			FROM `tabGL Entry` g
			WHERE g.is_cancelled = 0 AND g.account IN %s AND g.posting_date <= %s
			GROUP BY g.account""",
			(*points, tuple(accounts), through),
		):
			co, kind, label = accounts[row[0]]
			vals = [round(float(v or 0)) for v in row[1:]]
			if kind == 2:
				vals = [-v for v in vals]   # loans: positive = we owe the bank
			if any(vals):
				# [company, kind 0 cash / 1 bank / 2 loan, account name, month-end balances..., now, a year earlier]
				cash_rows.append([co, kind, label, vals[:n_months], vals[-2], vals[-1]])

	# ------------------------------------------------ customers and suppliers
	def party_balances(party_type, account_type, sign):
		accts = frappe.db.sql(
			"""SELECT name FROM `tabAccount` WHERE is_group = 0 AND company IN %s AND account_type = %s""",
			(names, account_type),
			pluck=True,
		)
		if not accts:
			return []
		frappe.db.sql("SET SESSION SQL_BIG_SELECTS = 1")
		return frappe.db.sql(
			f"""SELECT g.company, g.party, {_balance_columns(points, sign)}
			FROM `tabGL Entry` g
			WHERE g.is_cancelled = 0 AND g.party_type = %s AND g.account IN %s AND g.posting_date <= %s
			GROUP BY g.company, g.party""",
			(*points, party_type, tuple(accts), through),
		)

	# Receivables are sent per party for "now" and "a year earlier" (the page
	# filters them by customer, segment and inter-company), and as month-end
	# totals per company x segment x inter-company for the trend.
	recv_raw = party_balances("Customer", "Receivable", "g.debit - g.credit")
	cust_codes = tuple({r[1] for r in recv_raw if r[1]})
	cust_info = {}
	if cust_codes:
		for code, cname, group, internal in frappe.db.sql(
			"""SELECT c.name, c.customer_name, IFNULL(cg.customer_group_name, ''), c.is_internal_customer
			FROM `tabCustomer` c LEFT JOIN `tabCustomer Group` cg ON cg.name = c.customer_group
			WHERE c.name IN %s""",
			(cust_codes,),
		):
			cust_info[code] = (cname or code, api._segment(group), 1 if internal or api._is_group_company(cname, group_names) else 0)

	recv, recv_m = [], {}
	for row in recv_raw:
		co, code = co_idx[row[0]], row[1]
		if not code:
			continue
		vals = [float(v or 0) for v in row[2:]]
		cname, seg, internal = cust_info.get(code, (code, len(api.SEGMENTS) - 1, 0))
		if round(vals[-2]) or round(vals[-1]):
			# [company, customer code, name, segment, inter-company, balance now, a year earlier]
			recv.append([co, code, cname, seg, internal, round(vals[-2]), round(vals[-1])])
		key = (co, seg, internal)
		m = recv_m.setdefault(key, [[0.0] * n_months, [0.0] * n_months])
		for i in range(n_months):
			# owed and advances apart, so a selection's trend is "owed", not owed minus advances
			m[0 if vals[i] > 0 else 1][i] += vals[i]

	pay_raw = party_balances("Supplier", "Payable", "g.credit - g.debit")
	sup_codes = tuple({r[1] for r in pay_raw if r[1]})
	sup_info = {}
	if sup_codes:
		for code, sname, internal in frappe.db.sql(
			"""SELECT name, supplier_name, is_internal_supplier FROM `tabSupplier` WHERE name IN %s""",
			(sup_codes,),
		):
			sup_info[code] = (sname or code, 1 if internal or api._is_group_company(sname, group_names) else 0)

	pay, pay_m = [], {}
	for row in pay_raw:
		co, code = co_idx[row[0]], row[1]
		if not code:
			continue
		vals = [float(v or 0) for v in row[2:]]
		sname, internal = sup_info.get(code, (code, 0))
		if round(vals[-2]) or round(vals[-1]):
			pay.append([co, code, sname, internal, round(vals[-2]), round(vals[-1]), None])
		m = pay_m.setdefault((co, internal), [[0.0] * n_months, [0.0] * n_months])
		for i in range(n_months):
			m[0 if vals[i] > 0 else 1][i] += vals[i]

	# The largest open bill of the suppliers we owe most, so a page can say
	# "most of this is one bill" and link to it.
	pay.sort(key=lambda r: -r[4])
	top = [r for r in pay[:TOP_SUPPLIERS] if r[4] > 0]
	if top:
		biggest = {}
		for supplier, company, name, posting_date, outstanding in frappe.db.sql(
			"""SELECT supplier, company, name, posting_date, outstanding_amount FROM `tabPurchase Invoice`
			WHERE docstatus = 1 AND outstanding_amount > 0 AND supplier IN %s AND company IN %s AND posting_date <= %s
			ORDER BY outstanding_amount DESC""",
			(tuple(r[1] for r in top), names, through),
		):
			biggest.setdefault((co_idx[company], supplier), [name, posting_date.isoformat(), round(float(outstanding))])
		for r in top:
			r[6] = biggest.get((r[0], r[1]))

	# ------------------------------------------------ gas purchase cost
	month_starts = [getdate(s) for s, _e in bounds]
	buy = {}
	for company, d, kg, amt in frappe.db.sql(
		"""SELECT pi.company, pi.posting_date, SUM(pii.stock_qty), SUM(pii.base_net_amount)
		FROM `tabPurchase Invoice` pi JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		WHERE pi.docstatus = 1 AND pii.stock_uom = 'Kg' AND pi.company IN %s AND pi.posting_date BETWEEN %s AND %s
		GROUP BY pi.company, pi.posting_date""",
		(names, month_starts[0], through),
	):
		m = bisect.bisect_right(month_starts, getdate(d)) - 1
		k = (m, co_idx[company])
		x = buy.setdefault(k, [0.0, 0.0])
		x[0] += float(kg or 0)
		x[1] += float(amt or 0)

	return {
		"version": 1,
		"fiscal_year": years[0].name,
		"through": through.isoformat(),
		"through_ly": through_ly.isoformat(),
		"through_ly_label": api._bs_label(through_ly),
		"months": n_months,
		# [company, 0 cash / 1 bank / 2 bank loan, account name, [month-end balance], now, a year earlier]
		"cash": cash_rows,
		# [company, customer code, name, segment, inter-company, owed now (+) / advance (-), a year earlier]
		"recv": recv,
		# [company, segment, inter-company, [month-end owed], [month-end advances]]
		"recv_m": [[*k, [round(v) for v in m[0]], [round(v) for v in m[1]]] for k, m in recv_m.items()],
		# [company, supplier code, name, inter-company, we owe now (+) / advance (-), a year earlier,
		#  largest open bill [name, date, outstanding] or null]
		"pay": pay,
		# [company, inter-company, [month-end owed], [month-end advances]]
		"pay_m": [[*k, [round(v) for v in m[0]], [round(v) for v in m[1]]] for k, m in pay_m.items()],
		# [month index, company, kg bought, Rs]   (Purchase Invoice items in Kg)
		"buy": [[m, co, round(v[0], 1), round(v[1])] for (m, co), v in buy.items() if m >= 0],
		"generated": frappe.utils.now(),
	}
