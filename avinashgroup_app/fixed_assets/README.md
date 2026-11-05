# fixed_assets

Fixed assets and Nepal tax depreciation (Income Tax Act 2058, Section 19 and Schedule-2).

## Entry points

| What | Where | Runs from |
|---|---|---|
| Put Asset Categories in tax pools, per-pool accumulated depreciation accounts, yearly WDV finance-book row at the pool rate | `tax_pools.setup(dry_run=True)` | `bench --site X console`, by hand; not a patch yet |
| First-year thirds rule (Schedule-2 s.2(5)) | `nepal_wdv.get_wdv_or_dd_depr_amount` | `regional_overrides["Nepal"]` in hooks.py |
| First depreciation date = fiscal year end | `nepal_wdv.set_first_depreciation_date` | Asset `before_validate` |
| Pool E (intangible) rate and rows from the asset's useful life | `nepal_wdv.set_pool_e_rate` | Asset `before_validate` |
| Yearly rows on Asar end (15 or 16 July) | `nepal_wdv.snap_rows_to_fiscal_year_end` | Asset Depreciation Schedule `validate` |

## Doctypes touched

- **Asset Category**: `custom_tax_pool` (Custom Field fixture), `non_depreciable_category`, `enable_cwip_accounting`, and the `accounts` rows; creates the two Pool E categories per company
- **Asset**: `custom_tax_pool` (fetched from the category) and `custom_useful_life_years` (Custom Field fixtures); a Pool E asset's finance-book rate and number of depreciations
- **Account**: creates `111190 Accumulated Depreciation` / `11119x` and `111290 Accumulated Amortization` / `11129x` per company; sets CWIP account type, and `555200` to Depreciation, when the account has no GL entries

No scheduled jobs. Rates and the +1/3 company list are constants at the top of `tax_pools.py` (`POOL_RATES`, `POOL_YEARS`, `EXTRA_THIRD_COMPANIES`).

Rules, sources and open decisions: [`docs/fixed-assets-tax-pools.md`](../../docs/fixed-assets-tax-pools.md).
