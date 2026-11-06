# fixed_assets

Fixed assets and Nepal tax depreciation (Income Tax Act 2058, Section 19 and Schedule-2).

## Entry points

| What | Where | Runs from |
|---|---|---|
| Put Asset Categories in tax pools, per-pool accumulated depreciation accounts, yearly WDV finance-book row at the pool rate | `tax_pools.setup(dry_run=True)` | `bench --site X console`, by hand; not a patch yet |
| Yearly WDV forced on pooled assets and categories (no monthly / day-based) | `nepal_wdv.enforce_yearly_on_asset` / `enforce_yearly_on_category` | Asset `before_validate` (first) / Asset Category `validate`; desk: Property Setter fixture hides Frequency, locks Method |
| First-year thirds rule (Schedule-2 s.2(5)) | `nepal_wdv.get_wdv_or_dd_depr_amount` | `regional_overrides["Nepal"]` in hooks.py |
| First depreciation date = fiscal year end | `nepal_wdv.set_first_depreciation_date` | Asset `before_validate` |
| Total Number of Depreciations from the tax pool (hidden from staff), and the Pool E rate from the useful life | `nepal_wdv.fill_from_tax_pool` | Asset `before_validate` |
| Total Number of Depreciations on a category, from its Tax Pool | `tax_pools.fill_category_years` | Asset Category `before_validate` |
| Yearly rows on Asar end (15 or 16 July) | `nepal_wdv.snap_rows_to_fiscal_year_end` | Asset Depreciation Schedule `validate` |

| JV Type + Document No on ERPNext's asset journals (depreciation, scrap) | `asset_journal_entries.set_jv_type` | Journal Entry `before_insert` |
| Category accounts must match its Tax Pool (refuses Pool A account on a Pool B category) | `tax_pools.validate_pool_accounts` | Asset Category `validate` |
| End-to-end check, rolled back | `scripts/check_fixed_assets.py <site>` | by hand, from `sites/` |

## Doctypes touched

- **Asset Category**: `custom_tax_pool` (Custom Field fixture), `non_depreciable_category`, `enable_cwip_accounting`, and the `accounts` rows; creates the two Pool E categories per company
- **Asset**: `custom_tax_pool` (fetched from the category) and `custom_useful_life_years` (Custom Field fixtures); a Pool E asset's finance-book rate and number of depreciations
- **Account**: creates `111190 Accumulated Depreciation` / `11119x` and `111290 Accumulated Amortization` / `11129x` per company; sets CWIP account type, and `555200` to Depreciation, when the account has no GL entries

No scheduled jobs. Rates and the +1/3 company list are constants at the top of `tax_pools.py` (`POOL_RATES`, `POOL_YEARS`, `EXTRA_THIRD_COMPANIES`).

Rules, sources and open decisions: [`docs/fixed-assets-tax-pools.md`](../../docs/fixed-assets-tax-pools.md).
