"""Day-by-day data for the CEO Dashboard's time charts.

The charts follow the chosen period: a week or a month is drawn day by day, a
quarter week by week, a year month by month. The main fact table (api.py) is
half-month grain, which is enough for months but not for days, so for a week,
month or quarter the page asks here for that range and the same range a year
earlier, per day x company x segment x inter-company. Not per customer: a
quarter would be tens of thousands of rows; when one customer is selected the
page asks again with `customer`.

A separate module (not periods.py) so running gunicorn workers, which keep
modules they have already imported, load it fresh.

Read-only. See docs/ceo-dashboard.md.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from avinashgroup_app.ceo_dashboard import api, money

# Longest range served: a quarter of BS months is at most 96 days.
MAX_RANGE_DAYS = 100


@frappe.whitelist()
def get_daily(fiscal_year, from_date, to_date, prev_from, prev_to, customer=None, years_back=None, districts=None):
	"""Day-by-day totals for the charts of a week, month or quarter, and for the
	comparison range a year earlier: rows per day x company x segment x
	inter-company (not per customer, so a quarter stays small). With
	`customer`, only that customer's bills and receipts."""
	frappe.only_for(api.ROLES)
	companies = api._companies()
	if not companies:
		frappe.throw(_("You do not have access to any company."))
	names = tuple(c["name"] for c in companies)
	co_idx = {c["name"]: i for i, c in enumerate(companies)}
	years = api._fiscal_years(fiscal_year, years_back)
	first = getdate(years[-1].year_start_date)
	through = money._through(years, names)
	ranges = [(getdate(from_date), getdate(to_date)), (getdate(prev_from), getdate(prev_to))]
	for a, b in ranges:
		if not (first <= a <= b <= through) or (b - a).days >= MAX_RANGE_DAYS:
			frappe.throw(_("Pick a period of up to {0} days between {1} and {2}.").format(MAX_RANGE_DAYS, first, through))
	params = {"a": ranges[0][0], "b": ranges[0][1], "pa": ranges[1][0], "pb": ranges[1][1], "names": names, "cust": customer}
	only = " AND si.customer = %(cust)s" if customer else ""
	if districts and not customer:
		# Districts picked on the map: only the customers placed in them
		# (sales_breakdowns keeps one district per customer).
		from avinashgroup_app.ceo_dashboard import sales_breakdowns

		codes_in = sales_breakdowns.customers_in_districts(fiscal_year, years_back, [d.strip() for d in districts.split(",") if d.strip()])
		if not codes_in:
			return {"sales": [], "coll": []}
		params["in_districts"] = tuple(codes_in)
		only = " AND si.customer IN %(in_districts)s"

	frappe.db.sql("SET SESSION SQL_BIG_SELECTS = 1")
	raw = frappe.db.sql(
		f"""SELECT si.posting_date, si.company, si.customer, IFNULL(cg.customer_group_name, ''),
			SUM(IF(sii.stock_uom = 'Kg', sii.stock_qty, 0)),
			SUM(IF(sii.stock_uom = 'Kg', sii.base_net_amount, 0)),
			SUM(sii.base_net_amount)
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabCustomer Group` cg ON cg.name = si.customer_group
		WHERE si.docstatus = 1 AND si.company IN %(names)s{only}
			AND (si.posting_date BETWEEN %(a)s AND %(b)s OR si.posting_date BETWEEN %(pa)s AND %(pb)s)
		GROUP BY si.posting_date, si.company, si.customer, si.customer_group""",
		params,
	)
	coll_raw = frappe.db.sql(
		f"""SELECT si.posting_date, si.company, si.party, SUM(si.base_received_amount)
		FROM `tabPayment Entry` si
		WHERE si.docstatus = 1 AND si.payment_type = 'Receive' AND si.party_type = 'Customer' AND si.company IN %(names)s
			{only.replace("si.customer", "si.party")}
			AND (si.posting_date BETWEEN %(a)s AND %(b)s OR si.posting_date BETWEEN %(pa)s AND %(pb)s)
		GROUP BY si.posting_date, si.company, si.party""",
		params,
	)

	# Inter-company flag and segment per customer, as api.py works them out.
	codes = tuple({r[2] for r in raw} | {r[2] for r in coll_raw})
	group_names = [api._name_tokens(n) for n in frappe.get_all("Company", pluck="name")]
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
	for d, company, cust, group, kg, gas, amt in raw:
		k = (getdate(d).isoformat(), co_idx[company], api._segment(group), info.get(cust, (0, 0))[1])
		x = sales.setdefault(k, [0.0, 0.0, 0.0])
		x[0] += float(kg or 0)
		x[1] += float(gas or 0)
		x[2] += float(amt or 0)
	coll = {}
	for d, company, party, amt in coll_raw:
		seg, internal = info.get(party, (len(api.SEGMENTS) - 1, 0))
		k = (getdate(d).isoformat(), co_idx[company], seg, internal)
		coll[k] = coll.get(k, 0.0) + float(amt or 0)

	return {
		# [AD date, company, segment, inter-company, kg, gas Rs, net Rs]
		"sales": [[*k, round(v[0], 1), round(v[1]), round(v[2])] for k, v in sales.items()],
		# [AD date, company, segment, inter-company, received Rs]
		"coll": [[*k, round(v)] for k, v in coll.items()],
	}
