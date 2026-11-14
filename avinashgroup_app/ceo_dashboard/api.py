"""Data behind the CEO Dashboard page (/app/ceo-dashboard).

The CEO wants one screen for the whole group that behaves like a Power BI
report: pick a period, click a company, a month, a customer segment or a
customer, and every other visual highlights or narrows to it at once. A round
trip per click would mean an ~8s query on ~290k Sales Invoices, so
`get_dashboard` sends one compact, pre-aggregated fact table and the browser
(public/js/ceo_dashboard.js) does all filtering in memory.

The fact table
--------------
Three fiscal years: the chosen one and the two before it. Two years back is
needed so "rolling 12 months" can be compared with the 12 months before, and
so the trend can show 24 continuous months.

- sales: [slot, company, customer, segment, kg, gas Rs, net Rs, bills]
- coll:  [slot, company, customer, received Rs]   (Payment Entry, Receive)

`slot` is a half-month position on one timeline: 24 slots per fiscal year,
two per fiscal month (Shrawan = month 1). The second slot of a month holds
only the days AFTER the "data through" day in the "data through" month; every
other day sits in the first slot. With that, any period (month, quarter, year
to date, rolling 12) is a slot range ending at the "data through" slot, and
"the same period last year" is that range minus 24 - like for like even inside
a part month. Slot 48 is 1 Shrawan of the chosen year.

"Data through"
--------------
Today (or the fiscal year's last day for a past year). Until 2026-11-11 it was
the last day with normal sales billing, so a data copy whose billing stops
early (demo-nggroup: 27 Aug 2026) did not compare a few stray bills with a
full year; the CEO asked for today instead, because purchases, journals and
payments go on after sales billing stops. Every part of the page (sales,
money, buying, credit) uses this one day.

Deliberately not here
---------------------
- Receivables, payables, cash and gas margin: money.py, a separate call so
  the page does not wait for the ledger. Sales Invoice outstanding_amount is
  not used anywhere: receipts went through unmatched Journal Entries.
- Fixed assets.
- Collections through Journal Entry; only Payment Entry is counted.
- Branch-level permissions. A group-level view gated by ROLES; only Company
  User Permissions narrow it (companies come from frappe.get_list). Figures
  are read with raw SQL for speed. The invoice drill-down
  (get_customer_invoices) goes through frappe.get_list, so it shows only
  invoices the user may open.

This module replaced data.py on 2026-11-08 (a new module name so running
gunicorn workers load it fresh instead of serving the old import).

Read-only: nothing in this module writes. See docs/ceo-dashboard.md.
"""

import datetime
import hashlib

import frappe
from frappe import _
from frappe.utils import getdate, today

from rdp_common_app.utils.bs_boundaries import ad_to_bs, get_bs_month_name, get_bs_month_range

# Who may open the page; mirrored in page/ceo_dashboard/ceo_dashboard.json.
ROLES = ("Group CEO", "System Manager", "Accounts Manager")

# The BS month a fiscal year starts in (Shrawan). Fiscal Year rows on these
# sites start on 1 Shrawan, e.g. 83/84 = 2026-07-17 = 2083-04-01.
FISCAL_START_BS_MONTH = 4

# Fiscal years sent: the chosen one and this many before it. Two by default
# (rolling 12 months against the 12 before needs 24 months of history). When
# several years are added together the page asks for more: every picked year
# plus one before the earliest, so each year is compared with the year before.
YEARS_BACK = 2
# Most years one answer may span (each adds ~0.6 MB and ~2 s cold).
MAX_YEARS_BACK = 6
SLOTS_PER_YEAR = 24

# Fixed company order, so a company keeps its colour whatever the filter.
# Abbreviations as on the sites (CLAUDE.md); unknown companies go last by name.
COMPANY_ORDER = ("NGI", "NGN", "NGG", "NGK", "GEPL", "GLMI", "SGU", "AGU", "GGU")

# Customer Group names differ per company ("Dealer", "Dealers", "Dealer
# (Chitwan)", "Bulk 14.2 KG", "Bulk Customers (Balaju)" ...). They are folded
# into three segments by the start of the name; anything else is "Other".
SEGMENTS = ("Dealer", "Bulk", "Other")

# Three years cost ~5s cold on demo-nggroup and barely move minute to minute.
CACHE_SECONDS = 1800

# How many invoices the drill-down panel lists.
DRILL_INVOICES = 12

# Words dropped before comparing a customer name with a company name.
_LEGAL_WORDS = {"pvt", "p", "ltd", "private", "limited", "the"}


# ---------------------------------------------------------------- endpoints


@frappe.whitelist()
def get_dashboard(fiscal_year=None, force=0, years_back=None):
	"""Fact tables for `fiscal_year` (default: the current one) and the
	`years_back` years before it (default YEARS_BACK, at most MAX_YEARS_BACK).
	Throws PermissionError for users without ROLES."""
	frappe.only_for(ROLES)
	companies = _companies()
	if not companies:
		frappe.throw(_("You do not have access to any company."))

	years = _fiscal_years(fiscal_year, years_back)
	key = "ceo_dashboard:v2:{}:{}:{}".format(
		years[0].name, len(years) - 1, hashlib.md5("|".join(c["name"] for c in companies).encode()).hexdigest()
	)
	if not int(force or 0):
		cached = frappe.cache.get_value(key)
		if cached:
			return cached

	out = _build(years, companies)
	frappe.cache.set_value(key, out, expires_in_sec=CACHE_SECONDS)
	return out


@frappe.whitelist()
def get_customer_invoices(customer, from_date, to_date):
	"""Latest submitted Sales Invoices of one customer between two AD dates,
	read through frappe.get_list so the user's permissions apply."""
	frappe.only_for(ROLES)
	rows = frappe.get_list(
		"Sales Invoice",
		filters={"customer": customer, "docstatus": 1, "posting_date": ["between", [from_date, to_date]]},
		fields=["name", "posting_date", "company", "base_net_total", "total_qty", "is_return"],
		order_by="posting_date desc, name desc",
		limit_page_length=DRILL_INVOICES,
	)
	for r in rows:
		r["posting_date_bs"] = _bs_label(getdate(r.posting_date))
	return rows


# ---------------------------------------------------------------- helpers


def _companies():
	"""Companies the user can see, in COMPANY_ORDER, as [{name, abbr}]."""
	rows = frappe.get_all("Company", fields=["name", "abbr"])
	# Every endpoint is gated by frappe.only_for(ROLES), so the role itself is
	# the right to see the group's figures: a user holding only "Group CEO" has
	# no Company read permission of their own and frappe.get_list would give
	# them nothing. A Company User Permission still narrows the list.
	allowed = frappe.permissions.get_user_permissions(frappe.session.user).get("Company")
	if allowed:
		names = {p.get("doc") for p in allowed}
		rows = [r for r in rows if r.name in names]
	rank = {abbr: i for i, abbr in enumerate(COMPANY_ORDER)}
	rows.sort(key=lambda r: (rank.get(r.abbr, len(rank)), r.name))
	return [{"name": r.name, "abbr": r.abbr} for r in rows]


def _years_back(years_back):
	try:
		n = int(years_back or YEARS_BACK)
	except (TypeError, ValueError):
		n = YEARS_BACK
	return min(max(n, YEARS_BACK), MAX_YEARS_BACK)


def _fiscal_years(name, years_back=None):
	"""[chosen, one before, two before, ...] as dicts with name/start/end. A year
	with no Fiscal Year row gets the same dates a year earlier, so the
	comparison is empty rather than an error."""
	if not name:
		name = frappe.db.get_value(
			"Fiscal Year",
			{"year_start_date": ("<=", today()), "year_end_date": (">=", today()), "disabled": 0},
			"name",
		)
		if not name:
			frappe.throw(_("No Fiscal Year covers today."))
	cur = frappe.db.get_value("Fiscal Year", name, ["name", "year_start_date", "year_end_date"], as_dict=True)
	if not cur:
		frappe.throw(_("Fiscal Year {0} not found.").format(name))
	years = [cur]
	for _i in range(_years_back(years_back)):
		later = years[-1]
		start = getdate(later.year_start_date)
		prev = frappe.db.get_value(
			"Fiscal Year",
			{"year_end_date": start - datetime.timedelta(days=1)},
			["name", "year_start_date", "year_end_date"],
			as_dict=True,
		) or frappe._dict(
			name=None, year_start_date=start.replace(year=start.year - 1), year_end_date=start - datetime.timedelta(days=1)
		)
		years.append(prev)
	return years


class _BS:
	"""Memoised AD date -> (fiscal month 1..12, BS day)."""

	def __init__(self):
		self.memo = {}

	def __call__(self, d):
		hit = self.memo.get(d)
		if hit is None:
			bs = ad_to_bs(d)
			hit = self.memo[d] = ((bs.month - FISCAL_START_BS_MONTH) % 12 + 1, bs.day)
		return hit


def _bs_label(d):
	"""'11 Bhadra 2083' for an AD date."""
	bs = ad_to_bs(d)
	return f"{bs.day} {get_bs_month_name(bs.month)} {bs.year}"


def _segment(group_name):
	name = (group_name or "").strip().lower()
	for i, seg in enumerate(SEGMENTS[:-1]):
		if name.startswith(seg.lower()):
			return i
	return len(SEGMENTS) - 1


def _name_tokens(name):
	words = "".join(ch if ch.isalnum() else " " for ch in (name or "").lower()).split()
	return [w for w in words if w not in _LEGAL_WORDS]


def _is_group_company(customer_name, group_names):
	"""True when the customer is one of our own companies.

	Group companies sell gas to each other (NGI -> GEPL, NGG -> NGN ...), about
	Rs 10 Cr of 83/84's Rs 89.8 Cr on demo-nggroup, and none of those Customers
	has is_internal_customer set. Counting them adds the same gas twice to the
	group total, so the page hides them by default. Matched on the name with
	"Pvt. Ltd." and punctuation dropped; "Grishma Enterprises Pvt.Ltd.
	(Anamnagar)" still matches, "Grihalaxmi Gas Company" does not match
	"Grihalaxmi Metal Industries".
	"""
	tokens = _name_tokens(customer_name)
	return any(g and tokens[: len(g)] == g for g in group_names)


def _data_through(cur_start, upto, company_names):
	"""The "data through" day: `upto` (today, or the fiscal year's last day).
	Kept as the one place every module asks, so the rule can change in one
	spot; `cur_start` and `company_names` are no longer needed by the rule."""
	return getdate(upto)


def _month_bounds(years):
	"""AD [start, end] of every fiscal month on the timeline, oldest first
	(index = slot // 2)."""
	out = []
	for y in reversed(years):
		start_bs = ad_to_bs(getdate(y.year_start_date))
		for fm in range(12):
			bs_month = (FISCAL_START_BS_MONTH - 1 + fm) % 12 + 1
			bs_year = start_bs.year + (1 if bs_month < FISCAL_START_BS_MONTH else 0)
			s, e = get_bs_month_range(bs_year, bs_month)
			out.append([s.isoformat(), e.isoformat()])
	return out


def _build(years, companies):
	bs = _BS()
	names = tuple(c["name"] for c in companies)
	co_idx = {c["name"]: i for i, c in enumerate(companies)}
	cur = years[0]
	cur_start, cur_end = getdate(cur.year_start_date), getdate(cur.year_end_date)
	first = getdate(years[-1].year_start_date)
	starts = [getdate(y.year_start_date) for y in years]  # newest first

	upto = min(getdate(today()), cur_end)
	through = _data_through(cur_start, upto, names) if upto >= cur_start else cur_end
	thr_fm, thr_day = bs(through)

	def slot(d):
		y = next(i for i, s in enumerate(starts) if d >= s)
		fm, day = bs(d)
		late = 1 if fm == thr_fm and day > thr_day else 0
		return (len(years) - 1 - y) * SLOTS_PER_YEAR + (fm - 1) * 2 + late

	customers, cust_idx = [], {}

	def customer(code):
		i = cust_idx.get(code)
		if i is None:
			i = cust_idx[code] = len(customers)
			customers.append(code)
		return i

	frappe.db.sql("SET SESSION SQL_BIG_SELECTS = 1")
	raw = frappe.db.sql(
		"""SELECT si.company, si.posting_date, si.customer, IFNULL(cg.customer_group_name, ''),
			SUM(IF(sii.stock_uom = 'Kg', sii.stock_qty, 0)),
			SUM(IF(sii.stock_uom = 'Kg', sii.base_net_amount, 0)),
			SUM(sii.base_net_amount),
			COUNT(DISTINCT si.name)
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabCustomer Group` cg ON cg.name = si.customer_group
		WHERE si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s AND si.company IN %s
		GROUP BY si.company, si.posting_date, si.customer, si.customer_group""",
		(first, upto, names),
	)

	sales, last_buy, first_buy = {}, {}, {}
	excluded = {"bills": 0, "amount": 0.0}
	for company, d, cust, group, kg, amt_gas, amt, n in raw:
		d = getdate(d)
		if d > through:
			excluded["bills"] += n
			excluded["amount"] += float(amt or 0)
			continue
		c = customer(cust)
		if amt_gas or amt:
			if d > last_buy.get(c, datetime.date.min):
				last_buy[c] = d
			if d < first_buy.get(c, datetime.date.max):
				first_buy[c] = d
		k = (slot(d), co_idx[company], c, _segment(group))
		row = sales.get(k)
		if row is None:
			sales[k] = [float(kg or 0), float(amt_gas or 0), float(amt or 0), int(n)]
		else:
			row[0] += float(kg or 0)
			row[1] += float(amt_gas or 0)
			row[2] += float(amt or 0)
			row[3] += int(n)

	raw = frappe.db.sql(
		"""SELECT company, posting_date, party, SUM(base_received_amount)
		FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Receive' AND party_type = 'Customer'
			AND posting_date BETWEEN %s AND %s AND company IN %s
		GROUP BY company, posting_date, party""",
		(first, through, names),
	)
	coll = {}
	for company, d, party, amt in raw:
		k = (slot(getdate(d)), co_idx[company], customer(party))
		coll[k] = coll.get(k, 0.0) + float(amt or 0)

	group_names = [_name_tokens(n) for n in frappe.get_all("Company", pluck="name")]
	info = {}
	if customers:
		for name, cname, group, internal in frappe.db.sql(
			"""SELECT c.name, c.customer_name, IFNULL(cg.customer_group_name, ''), c.is_internal_customer
			FROM `tabCustomer` c LEFT JOIN `tabCustomer Group` cg ON cg.name = c.customer_group
			WHERE c.name IN %s""",
			(tuple(customers),),
		):
			info[name] = (cname, _segment(group), 1 if internal or _is_group_company(cname, group_names) else 0)

	labels = {}

	def label(d):
		if d not in labels:
			labels[d] = _bs_label(d)
		return labels[d]

	cust_out = []
	for i, code in enumerate(customers):
		cname, seg, internal = info.get(code, (code, len(SEGMENTS) - 1, 0))
		lb, fb = last_buy.get(i), first_buy.get(i)
		cust_out.append(
			[code, cname or code, seg, lb.isoformat() if lb else None, label(lb) if lb else None, internal,
			 fb.isoformat() if fb else None]
		)

	return {
		"version": 2,
		"fiscal_year": cur.name,
		"years": [y.name for y in reversed(years)],  # oldest first, one per 24 slots
		"fiscal_years": frappe.get_all(
			"Fiscal Year", filters={"disabled": 0}, order_by="year_start_date desc", pluck="name", limit=6
		),
		"today": getdate(today()).isoformat(),
		"through": through.isoformat(),
		"through_label": label(through),
		"through_slot": (len(years) - 1) * SLOTS_PER_YEAR + (thr_fm - 1) * 2,
		"through_day": thr_day,
		"thin": through < upto,
		"excluded": {"bills": excluded["bills"], "amount": round(excluded["amount"])},
		"months": [get_bs_month_name((FISCAL_START_BS_MONTH - 1 + i) % 12 + 1) for i in range(12)],
		"month_bounds": _month_bounds(years),
		"companies": companies,
		"segments": list(SEGMENTS),
		# [code, name, segment, last bill AD, last bill BS label, inter-company 0/1, first bill AD]
		"customers": cust_out,
		# [slot, company, customer, segment, kg, gas Rs, net Rs, bills]
		"sales": [[*k, round(v[0], 1), round(v[1]), round(v[2]), v[3]] for k, v in sales.items()],
		# [slot, company, customer, received Rs]
		"coll": [[*k, round(v)] for k, v in coll.items()],
		"generated": frappe.utils.now(),
	}
