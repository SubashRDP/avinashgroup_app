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

Deliberately narrow:

- only Written Down Value rows with yearly frequency and no daily pro-rata;
  anything else gets stock ERPNext behaviour untouched;
- an existing asset (opening accumulated depreciation) gets full years, the
  thirds were already applied in earlier years' books;
- does not handle disposals, the Rs 2,000 small-pool write-off or the 7%
  repairs cap. Those work on the whole pool and belong to the tax report.
"""

import frappe
from frappe.utils import add_days, date_diff, flt, getdate

from erpnext.accounts.utils import get_fiscal_year
from erpnext.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule import (
	get_default_wdv_or_dd_depr_amount,
)

from rdp_common_app.utils.bs_boundaries import ad_to_bs, bs_to_ad

WDV = "Written Down Value"
YEARLY = 12  # frequency_of_depreciation, in months

# BS month number -> thirds of cost counted in the year of first use (Schedule-2 s.2(5)).
# Baisakh = 1 ... Asar = 3, Shrawan = 4 ... Poush = 9, Magh = 10 ... Chaitra = 12.
SHRAWAN = 4  # first BS month of the fiscal year
# A yearly row this close to an Asar end is that year's row; ERPNext lands it a day off.
FISCAL_YEAR_END_TOLERANCE_DAYS = 3

THIRDS_BY_BS_MONTH = {**dict.fromkeys(range(4, 10), 3), **dict.fromkeys(range(10, 13), 2), **dict.fromkeys(range(1, 4), 1)}


def follows_schedule_2(fb_row) -> bool:
	return (
		fb_row.depreciation_method == WDV
		and int(fb_row.frequency_of_depreciation or 0) == YEARLY
		and not fb_row.daily_prorata_based
	)


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
