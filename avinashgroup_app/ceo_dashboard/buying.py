"""Purchases for the CEO Dashboard's "Buying" section.

The Buying panel used to hold one ledger balance ("we owe suppliers"), which
said nothing about what the group buys. The CEO asked for it to show buying
properly (2026-11-11): how much was bought, what, from whom, by which company,
and how much was paid to suppliers, for the same period and filters as the
rest of the page.

Purchases are few (demo-nggroup: ~5,000 Purchase Invoices in three years), so
this sends them at day grain, already summed per day x company x supplier x
category, plus the half-month `slot` the sales fact table uses (api.py). The
page windows them by slot like sales, and draws them day by day or month by
month like the sales chart.

What the figures are:
- purchases: Purchase Invoice item net amount (after discount, before VAT).
- LP Gas bought: stock qty of items bought by the Kg in the "LP Gas" / "Gas"
  item groups; categories below.
- paid: Payment Entries of type Pay to a Supplier.
- categories, from the Item Group name (the group codes differ per company,
  the names do not): LP Gas, Direct expenses (mostly transport), Indirect
  expenses, Fixed assets (item flagged as fixed asset), Other.

Shown as the books have them. Read-only. See docs/ceo-dashboard.md.
"""

import datetime
import hashlib

import frappe
from frappe import _
from frappe.utils import getdate

from avinashgroup_app.ceo_dashboard import api, money

CACHE_SECONDS = 1800

CATEGORIES = ("LP Gas", "Direct expenses", "Indirect expenses", "Fixed assets", "Other")


def _category(group_name, is_fixed_asset, by_kg):
	name = (group_name or "").strip().lower()
	if is_fixed_asset:
		return 3
	if by_kg and ("gas" in name):
		return 0
	if name.startswith("lp gas"):
		return 0
	if name.startswith("expenses (direct)"):
		return 1
	if name.startswith("expenses (indirect)"):
		return 2
	return 4


@frappe.whitelist()
def get_buying(fiscal_year=None, years_back=None, force=0):
	"""Purchase and supplier-payment rows over the same timeline as
	api.get_dashboard (the chosen year and `years_back` before)."""
	frappe.only_for(api.ROLES)
	companies = api._companies()
	if not companies:
		frappe.throw(_("You do not have access to any company."))
	years = api._fiscal_years(fiscal_year, years_back)
	key = "ceo_dashboard:buying:v1:{}:{}:{}".format(
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
	starts = [getdate(y.year_start_date) for y in years]  # newest first
	bs = api._BS()
	thr_fm, thr_day = bs(through)

	def slot(d):
		# Same rule as api._build: 24 half-month slots per fiscal year, the late
		# half of the data-through month holding only days after that day.
		y = next(i for i, s in enumerate(starts) if d >= s)
		fm, day = bs(d)
		late = 1 if fm == thr_fm and day > thr_day else 0
		return (len(years) - 1 - y) * api.SLOTS_PER_YEAR + (fm - 1) * 2 + late

	params = {"a": first, "b": through, "names": names}
	frappe.db.sql("SET SESSION SQL_BIG_SELECTS = 1")
	raw = frappe.db.sql(
		"""SELECT pi.posting_date, pi.company, pi.supplier, IFNULL(ig.item_group_name, ''),
			pii.is_fixed_asset, pii.stock_uom = 'Kg',
			SUM(IF(pii.stock_uom = 'Kg', pii.stock_qty, 0)), SUM(pii.base_net_amount), COUNT(DISTINCT pi.name)
		FROM `tabPurchase Invoice` pi
		JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		LEFT JOIN `tabItem Group` ig ON ig.name = pii.item_group
		WHERE pi.docstatus = 1 AND pi.company IN %(names)s AND pi.posting_date BETWEEN %(a)s AND %(b)s
		GROUP BY pi.posting_date, pi.company, pi.supplier, pii.item_group, pii.is_fixed_asset, pii.stock_uom = 'Kg'""",
		params,
	)
	pay_raw = frappe.db.sql(
		"""SELECT posting_date, company, party, SUM(base_paid_amount)
		FROM `tabPayment Entry`
		WHERE docstatus = 1 AND payment_type = 'Pay' AND party_type = 'Supplier'
			AND company IN %(names)s AND posting_date BETWEEN %(a)s AND %(b)s
		GROUP BY posting_date, company, party""",
		params,
	)

	suppliers, sup_idx = [], {}

	def sup(code):
		i = sup_idx.get(code)
		if i is None:
			i = sup_idx[code] = len(suppliers)
			suppliers.append(code)
		return i

	slots = {}

	def slot_of(d):
		s = slots.get(d)
		if s is None:
			s = slots[d] = slot(d)
		return s

	rows = {}
	for d, company, supplier, group, fixed, by_kg, kg, amt, n in raw:
		d = getdate(d)
		k = (slot_of(d), d.isoformat(), co_idx[company], sup(supplier), _category(group, fixed, by_kg))
		x = rows.setdefault(k, [0.0, 0.0, 0])
		x[0] += float(kg or 0) if k[4] == 0 else 0.0   # LP Gas kg only
		x[1] += float(amt or 0)
		x[2] += int(n)
	pay = {}
	for d, company, party, amt in pay_raw:
		d = getdate(d)
		k = (slot_of(d), d.isoformat(), co_idx[company], sup(party))
		pay[k] = pay.get(k, 0.0) + float(amt or 0)

	group_names = [api._name_tokens(n) for n in frappe.get_all("Company", pluck="name")]
	info = {}
	if suppliers:
		for code, sname, internal in frappe.db.sql(
			"SELECT name, supplier_name, is_internal_supplier FROM `tabSupplier` WHERE name IN %s",
			(tuple(suppliers),),
		):
			info[code] = (sname or code, 1 if internal or api._is_group_company(sname, group_names) else 0)

	return {
		"version": 1,
		"fiscal_year": years[0].name,
		"through": through.isoformat(),
		"categories": list(CATEGORIES),
		# [code, name, inter-company 0/1]
		"suppliers": [[c, *info.get(c, (c, 0))] for c in suppliers],
		# [slot, AD date, company, supplier, category, LP Gas kg, net Rs, bills]
		# (a bill with lines in two categories counts once in each)
		"rows": [[*k, round(v[0], 1), round(v[1]), v[2]] for k, v in rows.items()],
		# [slot, AD date, company, supplier, paid Rs]
		"pay": [[*k, round(v)] for k, v in pay.items()],
		"generated": frappe.utils.now(),
	}
