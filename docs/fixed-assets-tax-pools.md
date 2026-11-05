# Fixed assets and tax depreciation pools

Accountant-facing version with worked examples: [fixed-assets-depreciation-guide.md](fixed-assets-depreciation-guide.md). Desk user steps: [fixed-assets-user-guide.md](fixed-assets-user-guide.md). Hands-on checks: [fixed-assets-manual-test.md](fixed-assets-manual-test.md).

## The law (Income Tax Act 2058, as amended up to Finance Act 2083)

Tax depreciation is per **pool**, reducing balance (s.19, Schedule-2). It is
compulsory: s.19(1) says "shall" (changed from "may" by the Finance Acts from 2060 on).

| Pool | Assets | Rate (Sch-2 s.3(1)) |
|---|---|---|
| A | Buildings, permanent structures | 5% |
| B | Computers, data processing equipment, furniture, fixtures, office equipment | 25% |
| C | Automobiles, buses, minibuses | 20% |
| D | Construction/excavation equipment, plant, everything not listed elsewhere | 15% |
| E | Intangibles, one class per asset (s.1(2)(b)) | 100 / period of use, rounded to the nearest half year; no +1/3 |
| - | Land | not depreciable (s.2(aak)) |

- **Base** (s.2(3)): opening base minus last year's depreciation, plus additions,
  minus disposal proceeds; never below zero. Depreciation = closing base x rate.
- **Thirds rule for additions** (s.2(5)): Shrawan-Poush 3/3, Magh-Chaitra 2/3,
  Baisakh-Asar 1/3; the rest goes in next year.
- **Small balance** (s.2(6)): a pool below Rs 2,000 after depreciation is written off.
- **Disposal** (s.4): proceeds above the pool base are income; a dissolved pool's
  shortfall is a deductible loss.
- **Repairs** (s.16): deductible up to 7% of the pool's closing base; excess joins
  the pool next year.
- **+1/3 rate** (s.3(2)) on A-D for special (manufacturing) industries s.11(2kha),
  transport infrastructure s.11(3cha), BOT/power projects s.11(3tha)/s.19(2).
  Cooperatives removed by Finance Act 2082. Compulsory, not optional
  (Supreme Court, Triveni Spinning 074-RB-0345).
- **50%** first-year depreciation on assets generating power for own use; **100%**
  for fiscal printers / cash machines (s.3(3), s.3(4)).
- Generators, ATMs, lockers used commercially go in **Pool B**, not D
  (Supreme Court 073-RB-0146, 075-RB-0158).

Finance Act 2083 did not change depreciation. Not yet checked word for word
against IRD's official Nepali consolidation (amended by Finance Act 2082,
ird.gov.np/content/13405); secondary sources used: ICAN 2058 Act PDF (to 2067),
nepallaws.com Schedule II (2080/04/21), actnepal.com (to FA 2078), ICAN and SAR
Finance Act 2082 summaries, Baker Tilly Tax Fact 2025/26.

## How ERPNext is set up for it

ERPNext depreciates per asset; the tax figure needs pools. So:

1. Every Asset Category carries **Tax Pool** (`custom_tax_pool`) and points at its
   pool's accounts: `1111 0x` fixed asset, `1111 9x` accumulated depreciation
   (contra, same last digit), `5551 0x` depreciation expense. Land is
   `non_depreciable_category`. WIP categories use CWIP accounting and capitalise
   into the pool of what they become. `avinashgroup_app/fixed_assets/tax_pools.py`
   does this, dry run first, and adds a yearly WDV finance-book row at the pool rate.
2. `fixed_assets/nepal_wdv.py` applies the thirds rule to the first year
   (`regional_overrides["Nepal"]`), sets the first date to the fiscal year end and
   snaps yearly rows to Asar end. Tested 2026-11-05: see the guide, section 3.5.
3. **Pool E** (built 2026-11-05). `tax_pools.setup` creates `111290 Accumulated
   Amortization` under `111200 Intangible Assets` (`111291`, `111293`), types
   `555200 Amortization A/c` as Depreciation, and creates two categories per
   company: **Software (Pool E)** on `111201` and **Brands, Trademarks &
   Copyrights (Pool E)** on `111203`. Not `111202 Right of Use Assets` (NFRS 16
   lease) or `111204 Goodwill` (tax treatment unconfirmed). The rate is per
   asset: the Asset's **Useful Life (Years)** (`custom_useful_life_years`) gives
   rate = 100 / life and the number of yearly rows (`nepal_wdv.set_pool_e_rate`);
   the last row, in the expiry year, writes off the rest. Literal reading of
   s.3(1) + s.2(3); secondary sources teach straight line, so **tax adviser to
   confirm**. Tested on demo-nggroup in a rolled-back transaction: 1 Shrawan /
   Bhadra / Magh starts, 3.3 -> 3.5 years rounding, missing life refused.
4. *(not built)* A Schedule-2 tax depreciation report on top of the pool field.

ERPNext's own asset journals (depreciation, scrap, value adjustment) carry no
JV Type / Document No, both mandatory here; `fixed_assets/asset_journal_entries.py`
fills them through `payroll.hr_journal.fill_system_journal` (Journal Entry
`before_insert`). Without it the daily depreciation job fails silently.

Re-check everything (rolled back): `cd sites && ../env/bin/python
../apps/avinashgroup_app/avinashgroup_app/scripts/check_fixed_assets.py <site>`.

Workers must be restarted (`bench restart`) to load the new hooks before desk
users see the thirds rule.

## Open decisions

- **Pool E method**: literal reducing balance at 100 / life (built) or straight
  line. Tax adviser.

- ~~Book depreciation method~~ **Decided 2026-11-05: follow the law.** Written down
  value at the Schedule-2 rates, yearly, first year by the thirdsbut  rule (not by days).
  Built via ERPNext's `regional_overrides["Nepal"]` hook on
  `asset_depreciation_schedule.get_wdv_or_dd_depr_amount`.
- **Special industry +1/3**: GLMI almost certainly; the gas companies need the tax adviser.
- **Opening pool balances** per company from the last filed return.
- `345109 Provision for Accumulated Depreciation` (a liability) is no longer used by
  categories; what to do with any balance on it is for the accountant.

## demo-nggroup state (applied 2026-11-05)

Left for a person (the script reports these as TODO):
- SGU has no Asset Categories at all.
- NGK "WIP" category: no pool in its name.
- No matching CWIP account: GEPL WIP Filling Plant / Civil Work, NGI WIP Civil Work,
  NGN WIP Vehicle.
- AGU, GGU are not on the pool chart (standard ERPNext chart) and are skipped.
