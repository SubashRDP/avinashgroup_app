"""Written-down-value depreciation the way the Income Tax Act 2058 counts the first year.

Stock ERPNext pro-rates an asset's first year by days in use: an asset in use
from 1 Magh gets about 6/12 of a year. Schedule-2 s.2(5) instead adds a new
asset to its pool in thirds, by the Nepali month it was bought or first used:

    Shrawan - Poush   3/3 of cost this year
    Magh - Chaitra    2/3 this year, the rest next year
    Baisakh - Asar    1/3 this year, the rest next year

Done per asset, that is exactly: first-year depreciation = cost x rate x
(3, 2 or 1)/3, and every later year = written-down value x rate. Year two of
the pool (cost not yet added, plus the remainder) gives the same figure as
WDV on (cost - first-year depreciation); see docs/fixed-assets-depreciation-guide.md
Part 2. So the per-asset schedule ERPNext posts equals the legal pool figure.

Two hooks wire this in, both from hooks.py:

- ``regional_overrides["Nepal"]`` replaces ERPNext's
  ``get_wdv_or_dd_depr_amount`` (marked ``@erpnext.allow_regional`` for exactly
  this; India used it for its own 180-day rule). Setting
  ``flags.wdv_it_act_applied`` stops ERPNext from also pro-rating the first row
  by days.
- ``doc_events["Asset Depreciation Schedule"]["validate"]`` moves each yearly
  row onto its fiscal year's Asar end. ERPNext repeats the first date
  (e.g. 16 July) every year, but Asar end falls on 15 or 16 July, so some
  years' entries would otherwise post on 1 Shrawan, in the next fiscal year.
- ``doc_events["Asset"]["before_validate"]`` puts each yearly WDV row's first
  depreciation date at the end of the fiscal year (Asar end) the asset came into
  use, so the first row is that fiscal year.
- ``doc_events["Asset"]["before_validate"]`` also fills Total Number of
  Depreciations from the tax pool (the field is hidden from staff; Nepali law
  has no number of years) and sets a Pool E asset's rate.

Pool E (intangibles: software, trademarks) has no fixed rate. Schedule-2
s.1(2)(b) makes each intangible a class of its own and s.3(1) sets its rate at
100 / period of use, the period rounded to the nearest half year. The base and
thirds rule are the same as A-D (s.2(3), s.2(5) cover "any class"), and s.3(2)
gives the +1/3 to A-D only. So a Pool E asset is the same yearly WDV with a rate
of its own: a 5-year licence is 20%, a 3.3-year one rounds to 3.5 and is 28.57%.
``fill_from_tax_pool`` fills the rate and the number of yearly rows from the
asset's ``custom_useful_life_years``. The last row, in the fiscal year the
right expires, writes off what is left: an expired right is disposed of with
no proceeds, and s.4 makes that shortfall deductible.

This is the literal reading of the Act. Some secondary sources describe Pool E
as straight-line (cost / life each year). Which one the group files on is for
the tax adviser; see docs/fixed-assets-tax-pools.md.

Deliberately narrow:

- only Written Down Value rows with yearly frequency and no daily pro-rata;
  anything else gets stock ERPNext behaviour untouched;
- an existing asset (opening accumulated depreciation) gets full years, the
  thirds were already applied in earlier years' books;
- does not handle disposals, the Rs 2,000 small-pool write-off or the 7%
  repairs cap. Those work on the whole pool and belong to the tax report.
"""

import math

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, date_diff, flt, getdate

from erpnext.accounts.utils import get_fiscal_year
from erpnext.assets.doctype.asset.asset import get_item_details
from erpnext.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule import (
	_check_is_pro_rata,
	get_default_wdv_or_dd_depr_amount,
)

from rdp_common_app.utils.bs_boundaries import ad_to_bs, bs_to_ad

from avinashgroup_app.fixed_assets.tax_pools import years_for_pool

WDV = "Written Down Value"
YEARLY = 12  # frequency_of_depreciation, in months

# BS month number -> thirds of cost counted in the year of first use (Schedule-2 s.2(5)).
# Baisakh = 1 ... Asar = 3, Shrawan = 4 ... Poush = 9, Magh = 10 ... Chaitra = 12.
SHRAWAN = 4  # first BS month of the fiscal year
# A yearly row this close to an Asar end is that year's row; ERPNext lands it a day off.
FISCAL_YEAR_END_TOLERANCE_DAYS = 3

POOL_E = "E"
USEFUL_LIFE_FIELD = "custom_useful_life_years"  # Custom Field fixture "Asset-custom_useful_life_years"

THIRDS_BY_BS_MONTH = {**dict.fromkeys(range(4, 10), 3), **dict.fromkeys(range(10, 13), 2), **dict.fromkeys(range(1, 4), 1)}


def follows_schedule_2(fb_row) -> bool:
	return (
		fb_row.depreciation_method == WDV
		and int(fb_row.frequency_of_depreciation or 0) == YEARLY
		and not fb_row.daily_prorata_based
	)


TAX_POOLS = ("A", "B", "C", "D", "E")  # Asset Category custom_tax_pool values that depreciate
SCHEDULE_2_ROW = {
	# Schedule-2 s.2(2): written-down value (depreciation base x rate), counted
	# once per income year. There is no monthly, quarterly or day-based figure.
	"depreciation_method": WDV,
	"frequency_of_depreciation": YEARLY,
	"daily_prorata_based": 0,
}


def _force_yearly_rows(doc) -> list[str]:
	"""Set every depreciation row to Schedule-2's method and yearly frequency; returns what changed."""
	changed = []
	for row in doc.get("finance_books") or []:
		for field, value in SCHEDULE_2_ROW.items():
			if (row.get(field) or 0) != value:
				changed.append(f"row {row.idx}: {row.meta.get_label(field)} {row.get(field)!r} -> {value!r}")
				row.set(field, value)
	return changed


def enforce_yearly_on_asset(doc, method=None):
	"""Asset before_validate (first in the chain): a pooled asset depreciates yearly WDV.

	Draft assets only; a submitted asset's schedule changes through ERPNext's
	own flows. Without this a row set to monthly (1) or with daily pro-rata
	silently drops back to stock ERPNext arithmetic, which is not the law.
	"""
	if doc.docstatus != 0 or not doc.calculate_depreciation or not doc.asset_category:
		return
	if frappe.get_cached_value("Asset Category", doc.asset_category, "custom_tax_pool") not in TAX_POOLS:
		return
	if _force_yearly_rows(doc):
		frappe.msgprint(
			_("Depreciation set to Written Down Value, yearly (12 months): Income Tax Act Schedule-2 counts it once per income year."),
			alert=True,
		)


def enforce_yearly_on_category(doc, method=None):
	"""Asset Category validate: same rule on the rows a new asset copies."""
	if doc.get("custom_tax_pool") in TAX_POOLS:
		_force_yearly_rows(doc)


def first_year_fraction(available_for_use_date) -> float:
	"""1, 2/3 or 1/3 by the BS month the asset came into use."""
	return THIRDS_BY_BS_MONTH[ad_to_bs(getdate(available_for_use_date)).month] / 3


def get_wdv_or_dd_depr_amount(
	asset,
	fb_row,
	depreciable_value,
	yearly_opening_wdv,
	schedule_idx,
	prev_depreciation_amount,
	has_wdv_or_dd_non_yearly_pro_rata,
	asset_depr_schedule,
	prev_per_day_depr,
):
	"""Regional override (Nepal) of ERPNext's WDV amount; same signature and return shape."""
	if not follows_schedule_2(fb_row):
		return get_default_wdv_or_dd_depr_amount(
			asset,
			fb_row,
			depreciable_value,
			schedule_idx,
			prev_depreciation_amount,
			has_wdv_or_dd_non_yearly_pro_rata,
			asset_depr_schedule,
			prev_per_day_depr,
		)

	amount = flt(depreciable_value) * flt(fb_row.rate_of_depreciation) / 100
	if schedule_idx == 0:
		# Full year by default (existing asset); the thirds rule for a new one.
		asset_depr_schedule.flags.wdv_it_act_applied = True
		if not flt(asset_depr_schedule.opening_accumulated_depreciation):
			amount *= first_year_fraction(asset.available_for_use_date)
	return amount, None


def set_first_depreciation_date(doc, method=None):
	"""Asset before_validate: first yearly WDV date = fiscal year end of the year in use.

	Only for a new asset; an existing asset's first date depends on how many
	years were already booked, so the person entering it keeps control.
	"""
	if not doc.calculate_depreciation or doc.is_existing_asset or not doc.available_for_use_date:
		return
	if not doc.get("finance_books") and doc.item_code and doc.asset_category:
		# The desk form copies the category's rows before saving; an import or API
		# call does not, and ERPNext only copies them later in validate, after this
		# hook, then dates them on the month end. Copy them here so they get the
		# fiscal year end like a desk-entered asset.
		doc.set(
			"finance_books",
			get_item_details(doc.item_code, doc.asset_category, doc.gross_purchase_amount),
		)
	fiscal_year_end = get_fiscal_year(doc.available_for_use_date, company=doc.company)[2]
	for row in doc.get("finance_books") or []:
		if follows_schedule_2(row):
			row.depreciation_start_date = fiscal_year_end


def asar_end_near(ad_date):
	"""The fiscal-year end (last day of Asar) nearest to ad_date.

	None past the converter's calendar (BS 2100, about 2043 AD): the 90-year
	building schedules run that far, and those rows keep ERPNext's date.
	"""
	try:
		bs_year = ad_to_bs(getdate(ad_date)).year
		ends = [add_days(bs_to_ad(y, SHRAWAN, 1), -1) for y in (bs_year, bs_year + 1)]
	except ValueError:
		return None
	return min(ends, key=lambda end: abs(date_diff(end, ad_date)))


def snap_rows_to_fiscal_year_end(doc, method=None):
	"""Asset Depreciation Schedule validate: put yearly WDV rows on Asar end.

	Leaves posted rows (journal entry made), the disposal-date row, and any row
	not within FISCAL_YEAR_END_TOLERANCE_DAYS of a year end (ERPNext's final
	pro-rata leftover row) exactly where ERPNext put them.
	"""
	if not follows_schedule_2(doc):
		return
	disposal_date = frappe.db.get_value("Asset", doc.asset, "disposal_date")
	for row in doc.get("depreciation_schedule") or []:
		if row.journal_entry or (disposal_date and getdate(row.schedule_date) == getdate(disposal_date)):
			continue
		end = asar_end_near(row.schedule_date)
		if end and 0 < abs(date_diff(end, row.schedule_date)) <= FISCAL_YEAR_END_TOLERANCE_DAYS:
			row.schedule_date = end


def rounded_useful_life(years) -> float:
	"""Period of use to the nearest half year (Schedule-2 s.3(1)); 3.2 -> 3.0, 3.25 -> 3.5.

	Never below half a year, so a three-month licence still gets a rate (200%,
	which the first row caps at the whole cost).
	"""
	return max(math.floor(flt(years) * 2 + 0.5) / 2, 0.5)


def fiscal_year_index(ad_date) -> int:
	"""BS year in which the fiscal year containing ad_date starts (2083/84 -> 2083)."""
	bs = ad_to_bs(getdate(ad_date))
	return bs.year if bs.month >= SHRAWAN else bs.year - 1


def pool_e_rows(available_for_use_date, years: float) -> int:
	"""Yearly rows from the fiscal year the right starts to the one it expires in.

	A 5-year licence from 1 Shrawan ends on the last day of Asar five years on:
	5 rows. The same licence from Bhadra runs into a sixth fiscal year: 6 rows.
	"""
	start = getdate(available_for_use_date)
	expiry = add_days(add_months(start, int(years * 12)), -1)
	return fiscal_year_index(expiry) - fiscal_year_index(start) + 1


def fill_from_tax_pool(doc, method=None):
	"""Asset before_validate: Total Number of Depreciations, and a Pool E asset's rate.

	Total Number of Depreciations is hidden from staff (Property Setter
	fixtures), so it is always set here from the category's Tax Pool:
	A-D get tax_pools.POOL_YEARS (at least one more than an existing asset's
	booked years), E gets the rows to its expiry year and 100 / useful life.

	Draft assets only; a submitted asset's schedule is changed through ERPNext's
	own Asset Value Adjustment / Repair flows. Throws when a depreciating asset's
	category has no pool, or a Pool E asset has no useful life, since neither
	has a count or rate without it.
	"""
	if doc.docstatus != 0 or not doc.calculate_depreciation or not doc.asset_category:
		return
	rows = [row for row in doc.get("finance_books") or [] if follows_schedule_2(row)]
	if not rows:
		return
	# Still None on a new asset at before_validate; ERPNext's pro-rata test compares it.
	doc.opening_number_of_booked_depreciations = cint(doc.opening_number_of_booked_depreciations)

	pool = frappe.get_cached_value("Asset Category", doc.asset_category, "custom_tax_pool")
	if pool == POOL_E:
		_set_pool_e(doc, rows)
		return
	years = years_for_pool(pool)
	if not years:
		frappe.throw(
			_("Asset Category {0} has no Tax Pool, so the depreciation years cannot be set. Ask Accounts.").format(
				doc.asset_category
			),
			title=_("Tax Pool needed"),
		)
	for row in rows:
		row.total_number_of_depreciations = max(years, doc.opening_number_of_booked_depreciations + 1)


def _set_pool_e(doc, rows):
	"""Rate = 100 / useful life and the yearly rows up to the year the right expires."""
	if flt(doc.get(USEFUL_LIFE_FIELD)) <= 0:
		frappe.throw(
			_("{0} is in Pool E: enter its Useful Life (Years), the licence or right's period of use.").format(
				doc.asset_category
			),
			title=_("Useful life needed"),
		)
	if not doc.available_for_use_date:
		return  # ERPNext's own validation asks for it

	years = rounded_useful_life(doc.get(USEFUL_LIFE_FIELD))
	count = pool_e_rows(doc.available_for_use_date, years)
	for row in rows:
		row.rate_of_depreciation = flt(100 / years, row.precision("rate_of_depreciation") or 9)
		# ERPNext adds a part-year row of its own when the first year is not a
		# whole year (in use after 1 Shrawan), dated on the expiry date. That row
		# is the expiry year's write-off, so it is not counted again here.
		# ERPNext's own test decides it, so the two cannot disagree; it needs
		# the first depreciation date, set by set_first_depreciation_date above.
		adds_part_year = bool(row.depreciation_start_date) and _check_is_pro_rata(doc, row)
		row.total_number_of_depreciations = max(count - adds_part_year, 1)
