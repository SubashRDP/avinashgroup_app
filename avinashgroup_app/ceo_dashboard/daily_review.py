"""Daily Business Review: the six figures management goes through every morning,
read from the reports the accounts team already uses.

Why it exists: the meeting walks the same six topics every day (bank balance,
loans, the day's sales, collection, gas stock in MT, debtors), and each one
already has a Script Report in this app. Opening six reports and setting their
filters every morning is the slow part, so this page runs those reports for
one date and lays their totals side by side. Clicking a card opens the full
report with the same filters.

Deliberately not here: any figure of its own. Every number is taken from the
report's own output (its total row, or its rows summed), so the page and the
report can never disagree. Nothing is corrected or flagged; the books are
shown as they are (the user's rule for the CEO dashboard, 2026-11-09).

Source reports (avinash_group_app/report/):

    bank        Net Position of Cash and Bank   per company, From = To = the day
    loans       Loan Summary                    all companies, balance on the day
    sales       Sales Report Summary            all companies, the day
    collection  Receipt Register                per company, Customer Wise Summary
    stock       Stock Balance (With Zero Values) per company, its LP Gas item group
    debtors     Debtors Summary                 Monthly view of the day's BS month

Each section is cached for CACHE_SECONDS per date, because two of them are
slow (stock ~4.5 s and bank ~1.6 s per company, debtors ~7 s). Refresh on the
page skips the cache. Read-only. See docs/ceo-dashboard.md, "Daily Business Review".
"""

import importlib
import re

import frappe
from frappe.utils import add_days, flt, getdate, today

from rdp_common_app.utils.bs_boundaries import ad_to_bs

from avinashgroup_app.ceo_dashboard.api import ROLES, _companies

REPORTS = "avinashgroup_app.avinash_group_app.report."

# Long enough to cover a meeting (the page is opened on several screens at
# once), short enough that a morning's new entries show up within minutes.
CACHE_SECONDS = 600

# Item Group name of bulk LP Gas in every gas company. The group itself has a
# per-company code (NGI-IGR-00006, NGK-IGR-00021, ...), so it is looked up by
# this name.
GAS_ITEM_GROUP_NAME = "LP Gas"

SECTIONS = ("bank", "loans", "sales", "collection", "stock", "debtors")


@frappe.whitelist()
def get_section(section, date=None, refresh=0):
	"""One card's figures for `date` (default today).

	Returns {"date", "section", ...section fields}. Raises PermissionError for
	users outside ROLES and ValidationError for an unknown section."""
	frappe.only_for(ROLES)
	if section not in SECTIONS:
		frappe.throw(f"Unknown section {section}")
	day = str(getdate(date or today()))
	key = f"ceo_daily_review|{section}|{day}|{frappe.session.user}"
	cache = frappe.cache()
	if not int(refresh or 0):
		hit = cache.get_value(key)
		if hit:
			return hit
	out = globals()[f"_{section}"](day)
	out.update({"section": section, "date": day})
	cache.set_value(key, out, expires_in_sec=CACHE_SECONDS)
	return out


@frappe.whitelist()
def get_meta(date=None):
	"""The day's Bikram Sambat date and the companies, for the page header."""
	frappe.only_for(ROLES)
	day = getdate(date or today())
	bs = ad_to_bs(day)
	return {"date": str(day), "bs": [bs.year, bs.month, bs.day], "today": today(), "companies": _companies()}


# ---------------------------------------------------------------- helpers


def _run(report, filters):
	"""execute() of one of this app's Script Reports: (columns, data)."""
	module = importlib.import_module(f"{REPORTS}{report}.{report}")
	res = module.execute(frappe._dict(filters))
	return res[0], res[1]


def _crdr(text):
	"""Loan Summary prints balances as "1,234.00 Cr" / "5.00 Dr" / "-".
	Cr (owed to the bank) is positive."""
	if text in (None, "", "-"):
		return 0.0
	m = re.match(r"\s*([\d,.\-]+)\s*(Cr|Dr)?", str(text))
	if not m:
		return 0.0
	v = flt(m.group(1).replace(",", ""))
	return -v if m.group(2) == "Dr" else v


def _fy_start(day):
	"""Start of the fiscal year holding `day` (any company's row will do: the
	group shares one fiscal calendar)."""
	start = frappe.db.get_value(
		"Fiscal Year", {"year_start_date": ["<=", day], "year_end_date": [">=", day]}, "year_start_date"
	)
	return str(start or day)


# ---------------------------------------------------------------- sections


def _bank(day):
	"""Net Position of Cash and Bank, From = To = day, for every company."""
	rows = []
	for co in _companies():
		_cols, data = _run("net_position_of_cash_and_bank", {"company": co["name"], "from_date": day, "to_date": day})
		accts = [r for r in data if r.get("code")]
		if not accts:
			continue
		s = lambda f, rs=accts: sum(flt(r.get(f)) for r in rs)
		cash = [r for r in accts if r.get("cash_book") == "Yes"]
		bank = [r for r in accts if r.get("cash_book") != "Yes"]
		rows.append({
			"co": co["name"], "abbr": co["abbr"],
			"opening": s("opening"), "receipts": s("receipts"), "payments": s("payments"), "closing": s("closing"),
			"cash": s("closing", cash), "bank": s("closing", bank),
			"accounts": sorted(
				[{"name": r.get("description"), "closing": flt(r.get("closing")), "cash": r.get("cash_book") == "Yes"} for r in accts],
				key=lambda a: -abs(a["closing"]),
			)[:8],
		})
	return {"rows": rows}


def _loans(day):
	"""Loan Summary on `day` and the day before (for the change)."""
	def read(to_date):
		cols, data = _run("loan_summary", {"from_date": _fy_start(day), "to_date": to_date})
		abbr = {c["fieldname"]: c["label"] for c in cols if c.get("fieldname") not in ("loan_type", "total")}
		return abbr, data

	abbr, data = read(day)
	_a, before = read(str(add_days(day, -1)))
	total_row = lambda rows, label: next((r for r in rows if r.get("loan_type") == label), {})
	grand = total_row(data, "Total Loan Amount")
	types = []
	for r in data:
		label = r.get("loan_type")
		if not label or label == "Ratio":
			continue
		if r.get("_bold"):
			continue
		v = _crdr(r.get("total"))
		if v:
			types.append({"label": label, "value": v})
	return {
		"total": _crdr(grand.get("total")),
		"before": _crdr(total_row(before, "Total Loan Amount").get("total")),
		"short": _crdr(total_row(data, "Total Short-term Loan").get("total")),
		"long": _crdr(total_row(data, "Total Long Term Loan").get("total")),
		"types": types,
		"companies": [
			{"abbr": a, "value": _crdr(grand.get(f))} for f, a in abbr.items() if _crdr(grand.get(f))
		],
		"fy_start": _fy_start(day),
	}


def _sales_day(day, companies):
	"""Sales Report Summary for one day: per-company totals and items."""
	_cols, data = _run("sales_report_summary", {
		"report_type": "Sales Report Summary", "company": [c["name"] for c in companies],
		"date_filter_type": "Date Range", "from_date": day, "to_date": day,
	})
	by_name = {c["name"]: c["abbr"] for c in companies}
	out, items, cur = [], {}, None
	for r in data:
		if r.get("_section"):
			cur = r.get("item_name")
			continue
		name = r.get("item_name")
		if not name or not cur:
			continue
		if name == "Total":
			out.append({
				"co": cur, "abbr": by_name.get(cur, cur), "kg": flt(r.get("stock_qty")),
				"taxable": flt(r.get("taxable_amount")), "vat": flt(r.get("vat_amount")), "amount": flt(r.get("total_amount")),
			})
			cur = None
			continue
		it = items.setdefault(f"{name}|{r.get('uom') or ''}", {"item": name, "uom": r.get("uom"), "qty": 0, "kg": 0, "taxable": 0})
		it["qty"] += flt(r.get("qty")); it["kg"] += flt(r.get("stock_qty")); it["taxable"] += flt(r.get("taxable_amount"))
	return out, sorted(items.values(), key=lambda i: -i["taxable"])


def _sales(day):
	companies = _companies()
	rows, items = _sales_day(day, companies)
	before, _i = _sales_day(str(add_days(day, -1)), companies)
	return {"rows": rows, "items": items[:8], "before": before}


def _collection_day(day, companies):
	rows, customers = [], []
	for co in companies:
		_cols, data = _run("receipt_register", {"view": "Customer Wise Summary", "company": co["name"], "from_date": day, "to_date": day})
		lines = [r for r in data if not r.get("is_total") and r.get("customer_name")]
		if not lines:
			continue
		rows.append({"co": co["name"], "abbr": co["abbr"], "amount": sum(flt(r.get("net_amount")) for r in lines), "customers": len(lines)})
		customers += [{"name": r.get("customer_name"), "abbr": co["abbr"], "amount": flt(r.get("net_amount"))} for r in lines]
	return rows, customers


def _collection(day):
	companies = _companies()
	rows, customers = _collection_day(day, companies)
	before, _c = _collection_day(str(add_days(day, -1)), companies)
	return {"rows": rows, "top": sorted(customers, key=lambda c: -c["amount"])[:8], "before": before}


def _stock(day):
	"""Stock Balance (With Zero Values) of each company's LP Gas item group, in Kg."""
	groups = frappe.get_all("Item Group", filters={"item_group_name": GAS_ITEM_GROUP_NAME, "is_group": 0}, pluck="name")
	# Item Group codes start with the company abbreviation (NGI-IGR-00006).
	rows = []
	for co in _companies():
		group = next((g for g in groups if g.startswith(f"{co['abbr']}-")), None)
		if not group:
			continue
		_cols, data = _run("stock_balance_(with_zero_values)", {
			"company": co["name"], "from_date": day, "to_date": day, "item_group": group, "valuation_field_type": "Currency",
		})
		lines = [r for r in data if r.get("warehouse") and r.get("stock_uom") == "Kg"]
		if not lines:
			continue
		s = lambda f: sum(flt(r.get(f)) for r in lines)
		rows.append({
			"co": co["name"], "abbr": co["abbr"], "group": group,
			"opening": s("opening_qty"), "in": s("in_qty"), "out": s("out_qty"), "closing": s("bal_qty"),
			"warehouses": [{"name": r.get("warehouse"), "closing": flt(r.get("bal_qty"))} for r in lines],
		})
	return {"rows": rows}


def _debtors(day):
	"""Debtors Summary, Monthly view: the day's row and the row before it."""
	bs = ad_to_bs(getdate(day))
	_cols, data = _run("debtors_summary", {"view": "Monthly", "bs_year": bs.year, "bs_month": str(bs.month)})
	label = f"{bs.year}.{bs.month:02d}.{bs.day:02d}"
	days = [r for r in data if re.match(r"^\d{4}\.\d{2}\.\d{2}$", str(r.get("date") or ""))]
	i = next((k for k, r in enumerate(days) if r["date"] == label), None)
	if i is None:
		return {"rows": [], "bs": [bs.year, bs.month, bs.day]}
	cur, prev = days[i], days[i - 1] if i > 0 else {}
	abbrs = [c["abbr"] for c in _companies()]
	rows = [
		{"abbr": a, "gas": flt(cur.get(f"{a}_gas")), "cyl": flt(cur.get(f"{a}_cyl")), "total": flt(cur.get(f"{a}_total")),
		 "before": flt(prev.get(f"{a}_total"))}
		for a in abbrs if cur.get(f"{a}_total") is not None and (flt(cur.get(f"{a}_total")) or flt(cur.get(f"{a}_gas")))
	]
	return {
		"rows": rows, "bs": [bs.year, bs.month, bs.day],
		"gas": flt(cur.get("total_gas")), "cyl": flt(cur.get("total_cyl")), "total": flt(cur.get("grand_total")),
		"before": flt(prev.get("grand_total")) if prev else None,
	}
