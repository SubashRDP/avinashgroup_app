# fixed_assets

Fixed assets and Nepal tax depreciation (Income Tax Act 2058, Section 19 and Schedule-2).

## Entry points

| What | Where | Runs from |
|---|---|---|
| Put Asset Categories in tax pools, create per-pool accumulated depreciation accounts | `tax_pools.setup(dry_run=True)` | `bench --site X console`, by hand; not a patch yet |

## Doctypes touched

- **Asset Category**: `custom_tax_pool` (Custom Field fixture), `non_depreciable_category`, `enable_cwip_accounting`, and the `accounts` rows
- **Account**: creates `111190 Accumulated Depreciation` and `11119x` children per company; sets CWIP account type when the account has no GL entries

No scheduled jobs, no doc_events.

Rules, sources and open decisions: [`docs/fixed-assets-tax-pools.md`](../../docs/fixed-assets-tax-pools.md).
