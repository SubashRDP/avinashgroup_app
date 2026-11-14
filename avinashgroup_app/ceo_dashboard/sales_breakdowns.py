"""Extra cuts of sales for the CEO Dashboard: by district (drawn on a map of
Nepal), by branch, sales returns, and by pack size (cylinders sold).

The CEO asked for these on 2026-11-11: a district view "if and only if" it is
a map, branch-wise sales, and sales against sales returns.

- District: a bill carries the customer's city (Sales Invoice custom_citytown),
  which in practice is the district name, and a customer almost never changes
  it (11 customers of ~1,700 have two values on demo-nggroup). So this sends
  one district per customer, the city on most of their bills, and the page
  sums the sales rows it already holds: the map then follows every filter
  (period, company, segment, customer) with no extra rows. City values are
  matched to the map's district names (public/js/ceo_nepal_districts.json)
  through CITY_ALIASES for the spellings and towns seen in the data; a city
  that is neither is left off the map and counted as "no district".
- Branch: only bills that carry a branch (custom_branch) are sent, per day x
  company x branch x segment x inter-company. Most companies do not use
  branches (GEPL does on every bill), so "no branch on the bill" is worked out
  on the page as the company's sales minus its branch rows.
- Returns: bills with is_return, per day x company x segment x inter-company
  x reason. The free-text reason is folded into RETURN_REASONS.

- Pack size (added 2026-11-13): LP Gas is one item sold in several units of
  measure (14.2 KG, 5 KG, 50 KG, 450 KG, 1 MT, Kg). The page showed tonnes
  only; a gas business also counts cylinders. Sent per day x company x unit x
  segment x inter-company x district, net of returns, with the number of
  units billed. The page decides what to call a unit (PACK_CYLINDER_MAX_KG in
  ceo_dashboard.js); this only sends the unit's name and its weight in kg.

Rows carry the sales table's `slot` (timeline.py) and the AD date, like
buying.py, so they window and chart the same way. Read-only.
See docs/ceo-dashboard.md.
"""

import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import getdate

from avinashgroup_app.ceo_dashboard import api, money, timeline

CACHE_SECONDS = 1800

# City values on bills that are not a district's own name: other spellings of
# the district, and towns, mapped to the map's district names. From the
# distinct values on demo-nggroup, 2026-11-11; add to it as new ones appear.
CITY_ALIASES = {
	"chitwan": "Chitawan", "chiltwan": "Chitawan", "bharatpur": "Chitawan", "bharatpur chitwan": "Chitawan",
	"mangalpur": "Chitawan",
	"kapilvastu": "Kapilbastu",
	"madhyabindu": "Nawalpur", "nawalparasi east": "Nawalpur", "nawalparasi west": "Parasi",
	"makwanpur": "Makawanpur", "hetauda": "Makawanpur",
	"sindhupalchowk": "Sindhupalchok", "sindupalchok": "Sindhupalchok",
	"kavrepalanchowk": "Kabhrepalanchok", "kavre palanchowk": "Kabhrepalanchok", "kabhre": "Kabhrepalanchok",
	"kavre": "Kabhrepalanchok",
	"simara": "Bara", "jeetpur": "Bara",
	"pokhara": "Kaski",
	"ruphandehi": "Rupandehi", "parsha": "Parsa", "dhadhing": "Dhading", "subsari": "Sunsari",
	"kohalpu": "Banke", "kohalpur": "Banke", "nepalgunj": "Banke",
	"lallitpur": "Lalitpur", "godawari": "Lalitpur",
	"kathamandu": "Kathmandu", "kathamadu": "Kathmandu", "kathamndu": "Kathmandu", "kathmadnu": "Kathmandu",
	"kritipure": "Kathmandu", "kirtipur": "Kathmandu", "lainchour": "Kathmandu", "panipokhari": "Kathmandu",
}

# Return reasons are typed by hand ("Being sales return due to gas leakage.").
# They are folded into these, in this order; the last takes whatever is left.
RETURN_REASONS = ("Gas leakage", "Empty cylinder shortage", "Order cancelled", "Full return", "Other or not stated")


def _reason(text):
	t = (text or "").lower()
	if "leak" in t:
		return 0
	if "shortage" in t:
		return 1
	if "cancel" in t:
		return 2
	if "full return" in t:
		return 3
	return 4


def _pack_kg(uom, factor):
	"""Kg in one unit, read from the unit's name ("14.2 KG", "1 MT"). The
	conversion factor on the bill line is the fallback only: some lines carry
	another unit's factor (a "5 KG" line with 14.2)."""
	m = re.match(r"^\s*([\d.]+)\s*(kg|mt)\s*$", uom or "", re.I)
	if m:
		return float(m.group(1)) * (1000.0 if m.group(2).lower() == "mt" else 1.0)
	return 1.0 if (uom or "").lower() == "kg" else float(factor or 0)


def _district_names():
	path = frappe.get_app_path("avinashgroup_app", "public", "js", "ceo_nepal_districts.json")
	with open(path) as f:
		return [d["name"] for d in json.load(f)["districts"]]


def customers_in_districts(fiscal_year, years_back, district_names):
	"""Customer codes placed in any of `district_names` (the map's names), for
	charts.get_daily when districts are picked on the map."""
	out = get_breakdowns(fiscal_year, years_back)
	wanted = {i for i, name in enumerate(out["districts"]) if name in set(district_names)}
	return [c for c, i in out["customer_district"].items() if i in wanted]


@frappe.whitelist()
def get_breakdowns(fiscal_year=None, years_back=None, force=0):
	"""District per customer, branch sales rows and sales-return rows over the
	same timeline as api.get_dashboard."""
	frappe.only_for(api.ROLES)
	companies = api._companies()
	if not companies:
		frappe.throw(_("You do not have access to any company."))
	years = api._fiscal_years(fiscal_year, years_back)
	key = "ceo_dashboard:breakdowns:v3:{}:{}:{}".format(
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
	slot = timeline.slotter(years, through)
	params = {"a": first, "b": through, "names": names}
	group_names = [api._name_tokens(n) for n in frappe.get_all("Company", pluck="name")]
	frappe.db.sql("SET SESSION SQL_BIG_SELECTS = 1")

	# ---------------------------------------------------------- district
	districts = _district_names()
	by_lower = {d.lower(): i for i, d in enumerate(districts)}
	alias = {k: by_lower[v.lower()] for k, v in CITY_ALIASES.items() if v.lower() in by_lower}
	best = {}   # customer -> (bills, district index or -1), the city on most of their bills
	unmapped = {}
	for customer, city, n in frappe.db.sql(
		"""SELECT customer, TRIM(custom_citytown), COUNT(*) FROM `tabSales Invoice`
		WHERE docstatus = 1 AND company IN %(names)s AND posting_date BETWEEN %(a)s AND %(b)s
			AND IFNULL(custom_citytown, '') != ''
		GROUP BY customer, TRIM(custom_citytown)""",
		params,
	):
		k = (city or "").lower()
		i = by_lower.get(k, alias.get(k, -1))
		if i < 0:
			unmapped[city] = unmapped.get(city, 0) + int(n)
		if customer not in best or n > best[customer][0]:
			best[customer] = (n, i)

	def district_of(customer):
		return best[customer][1] if customer in best else -1

	# ---------------------------------------------------------- branch
	branches, br_idx = [], {}
	for name, label, company in frappe.db.sql("SELECT name, branch, custom_company FROM `tabBranch`"):
		br_idx[name] = len(branches)
		branches.append([name, label or name, co_idx.get(company, -1)])
	seg_internal = {}

	def cust(code, group):
		x = seg_internal.get(code)
		if x is None:
			cname, internal = frappe.db.get_value("Customer", code, ["customer_name", "is_internal_customer"]) or (code, 0)
			x = seg_internal[code] = 1 if internal or api._is_group_company(cname, group_names) else 0
		return api._segment(group), x

	branch_rows = {}
	for d, company, branch, customer, group, kg, amt, n in frappe.db.sql(
		"""SELECT si.posting_date, si.company, si.custom_branch, si.customer, IFNULL(cg.customer_group_name, ''),
			SUM(IF(sii.stock_uom = 'Kg', sii.stock_qty, 0)), SUM(sii.base_net_amount), COUNT(DISTINCT si.name)
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabCustomer Group` cg ON cg.name = si.customer_group
		WHERE si.docstatus = 1 AND si.company IN %(names)s AND si.posting_date BETWEEN %(a)s AND %(b)s
			AND IFNULL(si.custom_branch, '') != ''
		GROUP BY si.posting_date, si.company, si.custom_branch, si.customer, si.customer_group""",
		params,
	):
		if branch not in br_idx:
			continue
		d = getdate(d)
		seg, internal = cust(customer, group)
		k = (slot(d), d.isoformat(), co_idx[company], br_idx[branch], seg, internal, district_of(customer))
		x = branch_rows.setdefault(k, [0.0, 0.0, 0])
		x[0] += float(kg or 0)
		x[1] += float(amt or 0)
		x[2] += int(n)

	# ---------------------------------------------------------- returns
	returns = {}
	for d, company, customer, group, reason, kg, amt, n in frappe.db.sql(
		"""SELECT si.posting_date, si.company, si.customer, IFNULL(cg.customer_group_name, ''),
			si.custom_reason_for_return,
			SUM(IF(sii.stock_uom = 'Kg', sii.stock_qty, 0)), SUM(sii.base_net_amount), COUNT(DISTINCT si.name)
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabCustomer Group` cg ON cg.name = si.customer_group
		WHERE si.docstatus = 1 AND si.is_return = 1 AND si.company IN %(names)s
			AND si.posting_date BETWEEN %(a)s AND %(b)s
		GROUP BY si.posting_date, si.company, si.customer, si.customer_group, si.custom_reason_for_return""",
		params,
	):
		d = getdate(d)
		seg, internal = cust(customer, group)
		k = (slot(d), d.isoformat(), co_idx[company], seg, internal, _reason(reason), district_of(customer))
		x = returns.setdefault(k, [0.0, 0.0, 0])
		x[0] -= float(kg or 0)    # returns are negative on the bill; sent as positive amounts returned
		x[1] -= float(amt or 0)
		x[2] += int(n)

	# ---------------------------------------------------------- pack size
	packs, pack_idx = [], {}   # [unit name, kg in one unit]
	pack_rows = {}
	for d, company, uom, customer, group, factor, qty, kg, amt, n in frappe.db.sql(
		"""SELECT si.posting_date, si.company, sii.uom, si.customer, IFNULL(cg.customer_group_name, ''),
			MAX(sii.conversion_factor), SUM(sii.qty), SUM(sii.stock_qty), SUM(sii.base_net_amount),
			COUNT(DISTINCT si.name)
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabCustomer Group` cg ON cg.name = si.customer_group
		WHERE si.docstatus = 1 AND si.company IN %(names)s AND si.posting_date BETWEEN %(a)s AND %(b)s
			AND sii.stock_uom = 'Kg'
		GROUP BY si.posting_date, si.company, sii.uom, si.customer, si.customer_group""",
		params,
	):
		uom = uom or "Kg"
		i = pack_idx.get(uom)
		if i is None:
			i = pack_idx[uom] = len(packs)
			packs.append([uom, _pack_kg(uom, factor)])
		d = getdate(d)
		seg, internal = cust(customer, group)
		k = (slot(d), d.isoformat(), co_idx[company], i, seg, internal, district_of(customer))
		x = pack_rows.setdefault(k, [0.0, 0.0, 0.0, 0])
		x[0] += float(qty or 0)
		x[1] += float(kg or 0)
		x[2] += float(amt or 0)
		x[3] += int(n)

	return {
		"version": 2,
		"fiscal_year": years[0].name,
		"districts": districts,
		# customer code -> district index (customers whose city is on the map)
		"customer_district": {c: i for c, (_n, i) in best.items() if i >= 0},
		# city values that matched no district: {city: bills}, to extend CITY_ALIASES from
		"unmapped_cities": dict(sorted(unmapped.items(), key=lambda kv: -kv[1])[:30]),
		# [branch code, branch name, company]
		"branches": branches,
		# [slot, AD date, company, branch, segment, inter-company, district (-1 none), kg, net Rs, bills]
		"branch_rows": [[*k, round(v[0], 1), round(v[1]), v[2]] for k, v in branch_rows.items()],
		"reasons": list(RETURN_REASONS),
		# [slot, AD date, company, segment, inter-company, reason, district (-1 none), kg returned, Rs returned, return bills]
		"returns": [[*k, round(v[0], 1), round(v[1]), v[2]] for k, v in returns.items()],
		# [unit of measure on the bill, kg in one unit]
		"packs": packs,
		# [slot, AD date, company, pack, segment, inter-company, district (-1 none), units, kg, net Rs, bills]
		"pack_rows": [[*k, round(v[0], 2), round(v[1], 1), round(v[2]), v[3]] for k, v in pack_rows.items()],
		"generated": frappe.utils.now(),
	}
