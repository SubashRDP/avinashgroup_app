"""Day-by-day series for the CEO Dashboard's "Compare" chart.

The CEO wants to put lines side by side on one chart: sales against purchase
bills against expenses against money received, and one fiscal year against
another, read at any grain from a whole half-year down to a single day
(2026-11-11). The main fact table (api.py) is half-month grain, which cannot
be re-cut into weeks or days, so this endpoint sends every day of the
timeline for each series. The rows are small (demo-nggroup, three years:
sales ~7.5k rows per day x company x segment, purchases ~400 per day x
company, expenses ~550), so the browser re-buckets them on every click with
no further round trip.

What each series is:
- sales:  Sales Invoice items, net amount (after discount, before VAT) and kg
          of items sold by the kg, per day x company x segment x inter-company.
- coll:   Payment Entry receipts from customers, per day x company x segment
          x inter-company.
- buy:    Purchase Invoice base net total and kg of items bought by the kg,
          per day x company x inter-company (supplier named like one of our
          companies).
- exp:    GL Entry debit minus credit on accounts with root type Expense, per
          day x company. Shown as the books have it: on demo-nggroup a test
          Purchase Invoice's depreciation sits in here.

Not here: per-customer rows (a customer selection does not apply to this
chart) and fixes to the books. Read-only. See docs/ceo-dashboard.md.
"""

import hashlib

import frappe
from frappe import _
from frappe.utils import getdate

from avinashgroup_app.ceo_dashboard import api, money

CACHE_SECONDS = 1800


@frappe.whitelist()
def get_series(fiscal_year=None, years_back=None, force=0):
	"""Daily rows for sales, collections, purchases and expenses over the same
	timeline as api.get_dashboard (the chosen year and `years_back` before)."""
	frappe.only_for(api.ROLES)
	companies = api._companies()
	if not companies:
		frappe.throw(_("You do not have access to any company."))
	years = api._fiscal_years(fiscal_year, years_back)
	key = "ceo_dashboard:series:v1:{}:{}:{}".format(
		years[0].name, len(years), hashlib.md5("|".join(c["name"] for c in companies).encode()).hexdigest()
	)
	if not int(force or 0):
		cached = frappe.cache.get_value(key)
		if cached:
			return cached
	out = _build(years, companies)
	frappe.cache.set_value(key, out, expires_in_sec=CACHE_SECONDS)
	return out


def _build(years, companies):
	names = tuple(c["name"] for c in companies)
	co_idx = {c["name"]: i for i, c in enumerate(companies)}
	first = getdate(years[-1].year_start_date)
	through = money._through(years, names)
	group_names = [api._name_tokens(n) for n in frappe.get_all("Company", pluck="name")]
	params = {"a": first, "b": through, "names": names}

	frappe.db.sql("SET SESSION SQL_BIG_SELECTS = 1")
	raw = frappe.db.sql(
		"""SELECT si.posting_date, si.company, si.customer, IFNULL(cg.customer_group_name, ''),
			SUM(IF(sii.stock_uom = 'Kg', sii.stock_qty, 0)), SUM(sii.base_net_amount)
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabCustomer Group` cg ON cg.name = si.customer_group
		WHERE si.docstatus = 1 AND si.company IN %(names)s AND si.posting_date BETWEEN %(a)s AND %(b)s
		GROUP BY si.posting_date, si.company, si.customer, si.customer_group""",
		params,
	)
	coll_raw = frappe.db.sql(
		"""SELECT posting_date, company, party, SUM(base_received_amount)
		FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Receive' AND party_type = 'Customer'
			AND company IN %(names)s AND posting_date BETWEEN %(a)s AND %(b)s
		GROUP BY posting_date, company, party""",
		params,
	)
	buy_raw = frappe.db.sql(
		"""SELECT pi.posting_date, pi.company, pi.supplier_name,
			SUM(IF(pii.stock_uom = 'Kg', pii.stock_qty, 0)), SUM(pii.base_net_amount)
		FROM `tabPurchase Invoice` pi
		JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		WHERE pi.docstatus = 1 AND pi.company IN %(names)s AND pi.posting_date BETWEEN %(a)s AND %(b)s
		GROUP BY pi.posting_date, pi.company, pi.supplier_name""",
		params,
	)
	exp_raw = frappe.db.sql(
		"""SELECT g.posting_date, g.company, SUM(g.debit - g.credit)
		FROM `tabGL Entry` g JOIN `tabAccount` a ON a.name = g.account
		WHERE g.is_cancelled = 0 AND a.root_type = 'Expense'
			AND g.company IN %(names)s AND g.posting_date BETWEEN %(a)s AND %(b)s
		GROUP BY g.posting_date, g.company""",
		params,
	)

	codes = tuple({r[2] for r in raw} | {r[2] for r in coll_raw})
	info = {}
	if codes:
		for code, cname, group, internal in frappe.db.sql(
			"""SELECT c.name, c.customer_name, IFNULL(cg.customer_group_name, ''), c.is_internal_customer
			FROM `tabCustomer` c LEFT JOIN `tabCustomer Group` cg ON cg.name = c.customer_group
			WHERE c.name IN %s""",
			(codes,),
		):
			info[code] = (api._segment(group), 1 if internal or api._is_group_company(cname, group_names) else 0)

	sales = {}
	for d, company, cust, group, kg, amt in raw:
		k = (getdate(d).isoformat(), co_idx[company], api._segment(group), info.get(cust, (0, 0))[1])
		x = sales.setdefault(k, [0.0, 0.0])
		x[0] += float(kg or 0)
		x[1] += float(amt or 0)
	coll = {}
	for d, company, party, amt in coll_raw:
		seg, internal = info.get(party, (len(api.SEGMENTS) - 1, 0))
		k = (getdate(d).isoformat(), co_idx[company], seg, internal)
		coll[k] = coll.get(k, 0.0) + float(amt or 0)
	buy = {}
	for d, company, supplier, kg, amt in buy_raw:
		k = (getdate(d).isoformat(), co_idx[company], 1 if api._is_group_company(supplier, group_names) else 0)
		x = buy.setdefault(k, [0.0, 0.0])
		x[0] += float(kg or 0)
		x[1] += float(amt or 0)
	exp = {(getdate(d).isoformat(), co_idx[company]): float(v or 0) for d, company, v in exp_raw}

	return {
		"version": 1,
		"fiscal_year": years[0].name,
		"through": through.isoformat(),
		# [AD date, company, segment, inter-company, kg, net Rs]
		"sales": [[*k, round(v[0], 1), round(v[1])] for k, v in sales.items()],
		# [AD date, company, segment, inter-company, received Rs]
		"coll": [[*k, round(v)] for k, v in coll.items()],
		# [AD date, company, inter-company supplier, kg, net Rs]
		"buy": [[*k, round(v[0], 1), round(v[1])] for k, v in buy.items()],
		# [AD date, company, Rs]
		"exp": [[*k, round(v)] for k, v in exp.items()],
		"generated": frappe.utils.now(),
	}
