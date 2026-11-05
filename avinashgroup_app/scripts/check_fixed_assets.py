"""End-to-end check of the fixed-asset setup (fixed_assets/). Everything is rolled back.

Creates test items and assets on one company, checks the category wiring, the
Schedule-2 thirds rule at every boundary date for pools A-D, the year-two
written-down value, Asar-end dates, existing assets, the monthly fallback,
Land, depreciation posting (accounts, JV Type, Document No), scrapping and
Pool E, then rolls the whole transaction back. Nothing it creates survives.

Run from sites/ (see CLAUDE.md for why):

    cd sites && ../env/bin/python ../apps/avinashgroup_app/avinashgroup_app/scripts/check_fixed_assets.py <site> [company]

Needs tax_pools.setup applied on the site and a Location. Item group and
company default to NGI's; pass another company that has the pool chart.
"""
import sys
import traceback

import frappe
from frappe.utils import add_days, flt, getdate

frappe.init(site=sys.argv[1], sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
frappe.clear_cache()

from rdp_common_app.utils.bs_boundaries import ad_to_bs, bs_to_ad
from avinashgroup_app.fixed_assets import tax_pools
from avinashgroup_app.fixed_assets.nepal_wdv import asar_end_near

RESULTS = []
COMPANY = sys.argv[2] if len(sys.argv) > 2 else "Nepal Gas Udhyog Pvt. Ltd."
LOC = frappe.db.get_value("Location", {}, "name")


def check(name, ok, detail=""):
	RESULTS.append((("PASS" if ok else "FAIL"), name, detail))


def run(name, fn):
	frappe.db.savepoint("t")
	try:
		fn()
	except Exception as e:
		RESULTS.append(("ERROR", name, f"{type(e).__name__}: {e}"))
		traceback.print_exc()
		frappe.db.rollback(save_point="t")
	frappe.local.message_log = []


def account_number(name):
	return frappe.db.get_value("Account", name, "account_number") if name else None


# ---------------------------------------------------------------- T1 setup
def t_idempotent():
	log = tax_pools.setup(dry_run=True)
	pending = [l for l in log if l.startswith(("CREATE", "UPDATE", "FIX"))]
	pool_e = [l for l in pending if any(k in l for k in ("Amortization", "Pool E", "555200"))]
	other = [l for l in pending if l not in pool_e]
	check("T1 setup re-run changes nothing for pools A-D", not other, "; ".join(other[:3]))
	RESULTS.append(("INFO", f"T1 Pool E setup not yet applied on demo: {len(pool_e)} pending changes", ""))


def t_categories():
	bad = []
	cats = frappe.get_all("Asset Category", fields=["name", "asset_category_name", "custom_tax_pool", "non_depreciable_category"])
	for c in cats:
		doc = frappe.get_doc("Asset Category", c.name)
		pool = c.custom_tax_pool
		if not pool:
			if "wip" == c.asset_category_name.strip().lower():
				continue  # NGK "WIP", known TODO
			bad.append(f"{c.name} no pool")
			continue
		for row in doc.accounts:
			fa = account_number(row.fixed_asset_account)
			if pool == "Not Depreciable":
				if not c.non_depreciable_category or row.accumulated_depreciation_account or row.depreciation_expense_account:
					bad.append(f"{c.name} land not clean")
				continue
			acc = account_number(row.accumulated_depreciation_account)
			exp = account_number(row.depreciation_expense_account)
			acc_type = frappe.db.get_value("Account", row.accumulated_depreciation_account, ["account_type", "root_type"])
			if not (fa and acc == "11119" + fa[-1] and exp == tax_pools.DEPRECIATION_EXPENSE.get(fa)):
				bad.append(f"{c.name} accounts {fa}/{acc}/{exp}")
			if acc_type != ("Accumulated Depreciation", "Asset"):
				bad.append(f"{c.name} accumulated type {acc_type}")
		if pool in tax_pools.POOL_RATES:
			fb = [r for r in doc.finance_books if not r.finance_book]
			ok = len(fb) == 1 and fb[0].depreciation_method == "Written Down Value" and fb[0].frequency_of_depreciation == 12 \
				and flt(fb[0].rate_of_depreciation) == tax_pools.POOL_RATES[pool] and fb[0].total_number_of_depreciations == tax_pools.POOL_YEARS[pool]
			if not ok:
				bad.append(f"{c.name} finance book")
	check(f"T2 all {len(cats)} categories wired to their pool", not bad, "; ".join(bad[:5]))


# ---------------------------------------------------------------- helpers
def category_for(pool):
	rows = frappe.get_all("Asset Category", filters={"custom_tax_pool": pool, "custom_company": COMPANY}, pluck="name", order_by="name")
	rows = [r for r in rows if "wip" not in frappe.db.get_value("Asset Category", r, "asset_category_name").lower()]
	return rows[0]


_items = {}


def item_for(category):
	if category not in _items:
		item = frappe.get_doc({
			"doctype": "Item", "item_code": f"ZZTEST-{category}", "item_name": f"ZZTEST {category}",
			"item_group": frappe.db.get_value("Item", {"is_fixed_asset": 1}, "item_group") or "All Item Groups", "stock_uom": "Unit", "is_stock_item": 0,
			"is_fixed_asset": 1, "asset_category": category,
			"item_defaults": [{"company": COMPANY}], "custom_company": COMPANY,
		}).insert(ignore_permissions=True)
		_items[category] = item.name
	return _items[category]


def make_asset(category, in_use, cost=300000, existing=False, opening=0, booked=0, start=None, freq=None, submit=False, life=None):
	a = frappe.get_doc({
		"doctype": "Asset", "company": COMPANY, "item_code": item_for(category), "asset_category": category,
		"asset_name": f"ZZTEST {category} {in_use}", "location": LOC, "purchase_date": in_use,
		"available_for_use_date": in_use, "gross_purchase_amount": cost, "purchase_amount": cost,
		"net_purchase_amount": cost, "calculate_depreciation": 1, "is_existing_asset": int(existing),
		"opening_accumulated_depreciation": opening, "opening_number_of_booked_depreciations": booked,
		"custom_company": COMPANY,
	})
	if life is not None:
		a.custom_useful_life_years = life
	for r in frappe.get_doc("Asset Category", category).finance_books:
		row = {k: r.get(k) for k in ("finance_book", "depreciation_method", "total_number_of_depreciations", "frequency_of_depreciation", "rate_of_depreciation", "daily_prorata_based")}
		if freq:
			row["frequency_of_depreciation"] = freq
			row["total_number_of_depreciations"] = row["total_number_of_depreciations"] * (12 // freq)
		if start:
			row["depreciation_start_date"] = start
		a.append("finance_books", row)
	a.flags.ignore_mandatory = True
	a.insert()
	if submit:
		a.submit()
	return a


def schedule(asset):
	name = frappe.db.get_value("Asset Depreciation Schedule", {"asset": asset.name, "docstatus": ["<", 2]}, "name", order_by="creation desc")
	return frappe.get_doc("Asset Depreciation Schedule", name)


def bs(y, m, d):
	return bs_to_ad(y, m, d)


def fy_end(bs_year):  # fiscal year that ENDS in Asar of bs_year
	return add_days(bs_to_ad(bs_year, 4, 1), -1)


# ---------------------------------------------------------------- T3 thirds rule
BOUNDARIES = [  # (label, BS date, thirds)
	("1 Shrawan 2082", (2082, 4, 1), 3),
	("last day Poush 2082", (2082, 9, None), 3),
	("1 Magh 2082", (2082, 10, 1), 2),
	("last day Chaitra 2082", (2082, 12, None), 2),
	("1 Baisakh 2083", (2083, 1, 1), 1),
	("last day Asar 2083", (2083, 3, None), 1),
]


def bs_date(y, m, d):
	if d is None:  # last day of month
		ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
		return add_days(bs_to_ad(ny, nm, 1), -1)
	return bs_to_ad(y, m, d)


def t_thirds_pool(pool):
	def fn():
		cat = category_for(pool)
		rate = tax_pools.POOL_RATES[pool] / 100
		cost = 120000
		bad = []
		for label, (y, m, d), thirds in BOUNDARIES:
			day = bs_date(y, m, d)
			a = make_asset(cat, day, cost=cost)
			rows = schedule(a).depreciation_schedule
			exp1 = round(cost * rate * thirds / 3, 2)
			exp2 = round((cost - exp1) * rate, 2)
			if flt(rows[0].depreciation_amount) != exp1 or flt(rows[1].depreciation_amount) != exp2:
				bad.append(f"{label}: got {rows[0].depreciation_amount}/{rows[1].depreciation_amount} want {exp1}/{exp2}")
			if getdate(rows[0].schedule_date) != getdate(fy_end(2083)):
				bad.append(f"{label}: first date {rows[0].schedule_date} want {fy_end(2083)}")
			if round(sum(flt(r.depreciation_amount) for r in rows), 2) != cost:
				bad.append(f"{label}: total {sum(flt(r.depreciation_amount) for r in rows)}")
		check(f"T3 Pool {pool} ({cat}) thirds rule at 6 boundary dates + year 2 + total = cost", not bad, "; ".join(bad[:3]))
	return fn


# ---------------------------------------------------------------- T4 Asar-end dates
def t_dates():
	a = make_asset(category_for("B"), bs_date(2082, 5, 3))
	rows = schedule(a).depreciation_schedule
	bad = []
	for r in rows[:-1]:  # last row is ERPNext's pro-rata leftover
		end = asar_end_near(r.schedule_date)
		if end and getdate(end) != getdate(r.schedule_date):
			bad.append(f"{r.schedule_date} vs Asar end {end}")
		elif end and ad_to_bs(getdate(r.schedule_date)).month != 3:
			bad.append(f"{r.schedule_date} not in Asar")
	check(f"T4 every yearly row on Asar end ({len(rows) - 1} rows)", not bad, "; ".join(bad[:3]))


# ---------------------------------------------------------------- T5 existing asset
def t_existing():
	# Bought 2080/81, one year already booked (full, since Shrawan), now entering ERPNext.
	cost, rate = 100000, 0.25
	opening = 25000
	a = make_asset(category_for("B"), bs_date(2080, 5, 1), cost=cost, existing=True, opening=opening, booked=1,
		start=fy_end(2082))
	rows = schedule(a).depreciation_schedule
	exp = round((cost - opening) * rate, 2)
	check("T5 existing asset: first row is a full year on the written-down value", flt(rows[0].depreciation_amount) == exp,
		f"got {rows[0].depreciation_amount} want {exp}")


# ---------------------------------------------------------------- T6 yearly enforced
def t_monthly():
	"""Someone sets an asset to monthly with daily pro-rata: it is put back to yearly WDV."""
	a = make_asset(category_for("B"), bs_date(2082, 10, 1), freq=1)
	fb = a.finance_books[0]
	rows = schedule(a).depreciation_schedule
	ok = (fb.frequency_of_depreciation == 12 and fb.depreciation_method == "Written Down Value"
		and flt(rows[0].depreciation_amount) == round(300000 * 0.25 * 2 / 3, 2))
	cat = frappe.get_doc("Asset Category", category_for("C"))
	cat.finance_books[0].frequency_of_depreciation = 3
	cat.finance_books[0].depreciation_method = "Straight Line"
	cat.save()
	cat.reload()
	ok_cat = cat.finance_books[0].frequency_of_depreciation == 12 and cat.finance_books[0].depreciation_method == "Written Down Value"
	check("T6 monthly / straight-line on an asset or category is put back to yearly WDV", ok and ok_cat,
		f"asset freq {fb.frequency_of_depreciation} first {rows[0].depreciation_amount}; category {cat.finance_books[0].frequency_of_depreciation} {cat.finance_books[0].depreciation_method}")


# ---------------------------------------------------------------- T7 land
def t_land():
	cat = frappe.get_all("Asset Category", filters={"custom_tax_pool": "Not Depreciable", "custom_company": COMPANY}, pluck="name")[0]
	try:
		make_asset(cat, bs_date(2082, 5, 1))
		check("T7 Land refuses depreciation", False, "asset with depreciation was accepted")
	except frappe.ValidationError as e:
		check("T7 Land refuses depreciation", "non-depreciable" in str(e), str(e)[:80])


# ---------------------------------------------------------------- T8 posting
def t_posting():
	from erpnext.assets.doctype.asset.depreciation import make_depreciation_entry
	cat = category_for("D")
	a = make_asset(cat, bs_date(2081, 11, 5), cost=200000, existing=True, start=fy_end(2082), submit=True)  # Falgun 81/82
	sch = schedule(a)
	make_depreciation_entry(sch.name, date="2026-07-31")
	sch.reload()
	posted = [r for r in sch.depreciation_schedule if r.journal_entry]
	bad = []
	posting_info = []
	if len(posted) != 2:
		bad.append(f"{len(posted)} rows posted, want 2 (81/82, 82/83)")
	exp = [round(200000 * 0.15 * 2 / 3, 2)]
	exp.append(round((200000 - exp[0]) * 0.15, 2))
	for r, e in zip(posted, exp):
		if flt(r.depreciation_amount) != e:
			bad.append(f"{r.schedule_date} {r.depreciation_amount} want {e}")
		gl = frappe.get_all("GL Entry", filters={"voucher_no": r.journal_entry, "is_cancelled": 0}, fields=["account", "debit", "credit", "posting_date"])
		dr = {account_number(g.account) for g in gl if g.debit}
		cr = {account_number(g.account) for g in gl if g.credit}
		acc_row = frappe.get_doc("Asset Category", cat).accounts[0]
		want_dr, want_cr = {account_number(acc_row.depreciation_expense_account)}, {account_number(acc_row.accumulated_depreciation_account)}
		if dr != want_dr or cr != want_cr:
			bad.append(f"GL dr {dr} cr {cr} want {want_dr}/{want_cr}")
		jv, docno = frappe.db.get_value("Journal Entry", r.journal_entry, ["custom_p_type", "custom_document_no"])
		if not jv or not docno:
			bad.append(f"JE {r.journal_entry} JV Type {jv!r} Document No {docno!r}")
		posting_info.append(f"{r.journal_entry} {jv} #{docno} Dr {want_dr} Cr {want_cr}")
		if any(getdate(g.posting_date) != getdate(r.schedule_date) for g in gl):
			bad.append("GL date != schedule date")
		fy = frappe.db.get_value("Journal Entry", r.journal_entry, "posting_date")
		if ad_to_bs(getdate(fy)).month != 3:
			bad.append(f"posted on {fy}, not Asar")
	check(f"T8 depreciation posts on Asar end to the pool's accounts, numbered ({cat})", not bad, "; ".join(bad[:4]))
	RESULTS.append(("INFO", "T8 " + " | ".join(posting_info), ""))
	return a


# ---------------------------------------------------------------- T9 scrap
def t_scrap():
	from erpnext.assets.doctype.asset.depreciation import make_depreciation_entry, scrap_asset
	a = make_asset(category_for("C"), bs_date(2081, 6, 1), cost=500000, existing=True, start=fy_end(2082), submit=True)
	make_depreciation_entry(schedule(a).name, date="2026-07-31")
	scrap_asset(a.name)
	a.reload()
	sch = frappe.get_doc("Asset Depreciation Schedule", frappe.db.get_value("Asset Depreciation Schedule", {"asset": a.name, "status": "Active"}, "name"))
	last = [r for r in sch.depreciation_schedule if r.journal_entry][-1]
	bad = []
	if a.status != "Scrapped":
		bad.append(f"status {a.status}")
	if getdate(last.schedule_date) != getdate(a.disposal_date):
		bad.append(f"last posted row {last.schedule_date} not disposal date {a.disposal_date} (must not be snapped)")
	if not a.journal_entry_for_scrap:
		bad.append("no scrap JE")
	check("T9 scrap: part-year depreciation to scrap date, then scrap entry", not bad, "; ".join(bad))


# ---------------------------------------------------------------- T10 Pool E
def t_pool_e():
	from avinashgroup_app.fixed_assets import nepal_wdv
	bad = []
	for y, want in ((3.2, 3.0), (3.25, 3.5), (5, 5.0), (0.2, 0.5)):
		if nepal_wdv.rounded_useful_life(y) != want:
			bad.append(f"round {y} -> {nepal_wdv.rounded_useful_life(y)} want {want}")
	if nepal_wdv.pool_e_rows(bs_date(2082, 4, 1), 5) != 5 or nepal_wdv.pool_e_rows(bs_date(2082, 5, 1), 5) != 6:
		bad.append("pool_e_rows 5y licence: want 5 rows from 1 Shrawan, 6 from Bhadra")
	# Temporarily treat a Pool B category as Pool E (rolled back).
	cat = category_for("B")
	frappe.db.set_value("Asset Category", cat, "custom_tax_pool", "E")
	frappe.clear_cache()
	if not frappe.get_meta("Asset").has_field("custom_useful_life_years"):
		RESULTS.append(("INFO", "T10 Asset-custom_useful_life_years not installed on demo; testing via attribute", ""))
	cost = 100000
	for label, day, thirds, rows_want in (("1 Shrawan", bs_date(2082, 4, 1), 3, 5), ("1 Magh", bs_date(2082, 10, 1), 2, 6)):
		a = make_asset(cat, day, cost=cost, life=5)
		fb = a.finance_books[0]
		rows = schedule(a).depreciation_schedule
		first = round(cost * 0.20 * thirds / 3, 2)
		if flt(fb.rate_of_depreciation) != 20:
			bad.append(f"{label}: rate {fb.rate_of_depreciation} want 20")
		if flt(rows[0].depreciation_amount) != first:
			bad.append(f"{label}: first {rows[0].depreciation_amount} want {first}")
		if len(rows) != rows_want:
			bad.append(f"{label}: {len(rows)} rows want {rows_want}")
		if round(sum(flt(r.depreciation_amount) for r in rows), 2) != cost:
			bad.append(f"{label}: total != cost")
	try:
		make_asset(cat, bs_date(2082, 5, 1), life=0)
		bad.append("asset without useful life accepted")
	except frappe.ValidationError:
		pass
	check("T10 Pool E: 100/life rate, half-year rounding, thirds, write-off in expiry year, life required", not bad, "; ".join(bad[:4]))


# ---------------------------------------------------------------- T11 no rows given
def t_no_rows():
	"""An import / API asset with no depreciation rows still gets the fiscal-year end."""
	cat = category_for("B")
	a = frappe.get_doc({
		"doctype": "Asset", "company": COMPANY, "custom_company": COMPANY, "item_code": item_for(cat), "asset_category": cat,
		"asset_name": "ZZTEST no rows", "location": LOC, "purchase_date": bs_date(2082, 10, 1),
		"available_for_use_date": bs_date(2082, 10, 1), "gross_purchase_amount": 300000, "calculate_depreciation": 1,
	})
	a.flags.ignore_mandatory = True
	a.insert()
	rows = schedule(a).depreciation_schedule
	ok = getdate(a.finance_books[0].depreciation_start_date) == getdate(fy_end(2083)) and flt(rows[0].depreciation_amount) == 50000
	check("T11 asset saved without depreciation rows (import/API) still gets Asar end + thirds", ok,
		f"start {a.finance_books[0].depreciation_start_date}, first {rows[0].depreciation_amount}")


# ---------------------------------------------------------------- run
run("T1", t_idempotent)
run("T2", t_categories)
for p in ("A", "B", "C", "D"):
	run(f"T3{p}", t_thirds_pool(p))
run("T4", t_dates)
run("T5", t_existing)
run("T6", t_monthly)
run("T7", t_land)
run("T8", t_posting)
run("T9", t_scrap)
run("T10", t_pool_e)
run("T11", t_no_rows)

frappe.db.rollback()
left = frappe.db.count("Asset", {"asset_name": ["like", "ZZTEST%"]}) + frappe.db.count("Item", {"item_code": ["like", "ZZTEST%"]})
print("\n==== RESULTS ====")
for status, name, detail in RESULTS:
	print(f"{status:5} {name}" + (f"  -> {detail}" if detail and status != "PASS" else ""))
print(f"rolled back; test records left: {left}")
sys.exit(int(any(r[0] in ("FAIL", "ERROR") for r in RESULTS)))
