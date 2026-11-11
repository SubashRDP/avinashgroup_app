"""Day-range figures for the CEO Dashboard's "Week" period.

The main fact table (api.py) is kept at half-month grain so three fiscal years
fit in one ~1.8 MB answer; a week cannot be cut out of it. When the user picks
a week, the page asks for just that week here: the same row shape as api.py,
for the week and for the same weekdays 52 weeks earlier, and folds the rows
into its in-memory table so every chart and filter works as for a month.

Weeks are picked by the page (Sunday to Saturday, week 1 starting on the
fiscal year's first day); this module only checks the range: inside the chosen
fiscal year, not past its data-through day, at most MAX_DAYS long.

Read-only. See docs/ceo-dashboard.md.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import getdate

from avinashgroup_app.ceo_dashboard import api, money

# A week; the page never asks for more.
MAX_DAYS = 7

# The comparison is the same weekdays a year earlier: 52 weeks back.
COMPARE_DAYS = 364


@frappe.whitelist()
def get_days(fiscal_year, from_date, to_date):
	"""Sales and receipts for from_date..to_date and the same days 52 weeks
	earlier. Throws if the range is outside the fiscal year or too long."""
	frappe.only_for(api.ROLES)
	companies = api._companies()
	if not companies:
		frappe.throw(_("You do not have access to any company."))
	names = tuple(c["name"] for c in companies)
	co_idx = {c["name"]: i for i, c in enumerate(companies)}
	years = api._fiscal_years(fiscal_year)
	start, end = getdate(years[0].year_start_date), getdate(years[0].year_end_date)
	through = money._through(years, names)
	a, b = getdate(from_date), getdate(to_date)
	if not (start <= a <= b <= min(end, through)) or (b - a).days >= MAX_DAYS:
		frappe.throw(_("Pick a week inside fiscal year {0}, up to {1}.").format(years[0].name, api._bs_label(through)))
	pa, pb = a - datetime.timedelta(days=COMPARE_DAYS), b - datetime.timedelta(days=COMPARE_DAYS)
	params = {"a": a, "b": b, "pa": pa, "pb": pb, "names": names}

	frappe.db.sql("SET SESSION SQL_BIG_SELECTS = 1")
	sales = {}
	for cur, company, cust, group, kg, gas, amt, n in frappe.db.sql(
		"""SELECT si.posting_date >= %(a)s, si.company, si.customer, IFNULL(cg.customer_group_name, ''),
			SUM(IF(sii.stock_uom = 'Kg', sii.stock_qty, 0)),
			SUM(IF(sii.stock_uom = 'Kg', sii.base_net_amount, 0)),
			SUM(sii.base_net_amount),
			COUNT(DISTINCT si.name)
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabCustomer Group` cg ON cg.name = si.customer_group
		WHERE si.docstatus = 1 AND si.company IN %(names)s
			AND (si.posting_date BETWEEN %(a)s AND %(b)s OR si.posting_date BETWEEN %(pa)s AND %(pb)s)
		GROUP BY 1, si.company, si.customer, si.customer_group""",
		params,
	):
		k = (int(cur), co_idx[company], cust, api._segment(group))
		row = sales.setdefault(k, [0.0, 0.0, 0.0, 0])
		row[0] += float(kg or 0)
		row[1] += float(gas or 0)
		row[2] += float(amt or 0)
		row[3] += int(n)

	coll = {}
	for cur, company, party, amt in frappe.db.sql(
		"""SELECT posting_date >= %(a)s, company, party, SUM(base_received_amount)
		FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Receive' AND party_type = 'Customer' AND company IN %(names)s
			AND (posting_date BETWEEN %(a)s AND %(b)s OR posting_date BETWEEN %(pa)s AND %(pb)s)
		GROUP BY 1, company, party""",
		params,
	):
		k = (int(cur), co_idx[company], party)
		coll[k] = coll.get(k, 0.0) + float(amt or 0)

	codes = tuple({k[2] for k in sales} | {k[2] for k in coll})
	group_names = [api._name_tokens(n) for n in frappe.get_all("Company", pluck="name")]
	customers = {}
	if codes:
		for code, cname, group, internal in frappe.db.sql(
			"""SELECT c.name, c.customer_name, IFNULL(cg.customer_group_name, ''), c.is_internal_customer
			FROM `tabCustomer` c LEFT JOIN `tabCustomer Group` cg ON cg.name = c.customer_group
			WHERE c.name IN %s""",
			(codes,),
		):
			customers[code] = [cname or code, api._segment(group), 1 if internal or api._is_group_company(cname, group_names) else 0]

	return {
		"fiscal_year": years[0].name,
		"from": a.isoformat(),
		"to": b.isoformat(),
		"prev_from": pa.isoformat(),
		"prev_to": pb.isoformat(),
		"prev_label": f"{api._bs_label(pa)} – {api._bs_label(pb)}",
		# [1 this week / 0 a year earlier, company, customer code, segment, kg, gas Rs, net Rs, bills]
		"sales": [[*k, round(v[0], 1), round(v[1]), round(v[2]), v[3]] for k, v in sales.items()],
		# [1 / 0, company, customer code, received Rs]
		"coll": [[*k, round(v)] for k, v in coll.items()],
		# code -> [name, segment, inter-company]
		"customers": customers,
	}
