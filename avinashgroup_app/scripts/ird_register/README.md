# The IRD CBMS register, and reconciling the books against it

`ird_filed.sql.gz` is the IRD's own side of the ledger: **179,790 records**
(172,881 sales + 6,909 returns) exported from the CBMS portal as 180 monthly
"Sales Data Sync Report" sheets and flattened into one table. It is what the IRD
actually holds, and it is the only authority on that question — `sync_status` on
a CBMS Bill records what our API call returned, which for imported legacy data
records nothing at all.

| | 79/80 | 80/81 | 81/82 | 82/83 |
| --- | --- | --- | --- | --- |
| NGG | 2,717 | 3,599 | 3,864 | 4,285 |
| NGI | — | 31,322 | 31,415 | 36,770 |
| NGK | 2,177 | 3,372 | 3,678 | 3,878 |
| NGN | 8,551 | 10,880 | 11,850 | 14,523 |

Nothing before 79/80 exists at the IRD for any company, and GEPL, GLMI and SGU
are not in the drop at all. FY 83/84 is not in it either. Outside those bounds
this data licenses no conclusion in either direction.

## Run it

```bash
cd ~/frappe-bench
gunzip -k apps/avinashgroup_app/avinashgroup_app/scripts/ird_register/ird_filed.sql.gz
S=apps/avinashgroup_app/avinashgroup_app/scripts/ird_register

bench --site ng-group.raindropinc.com mariadb < $S/ird_filed.sql      # loads the register (~19MB)
bench --site ng-group.raindropinc.com mariadb < $S/ird_reconcile.sql  # six reports, read-only
bench --site ng-group.raindropinc.com mariadb < $S/ird_apply_sync_status.sql   # writes; read the reports first
```

Everything joins on **`custom_branch_name`** — the per-branch running number that
`utils.cbms_invoice_number()` sends to CBMS and that `CBMS Bill.invoice_number`
is a copy of. The IRD holds that exact string (`NGN000001/82-83`), so the join is
string equality, not inference. Returns join on company as well: `RTN` numbers
repeat across companies.

The staging tables are `zz_`-prefixed and touch no Frappe doctype. Drop them when
you are done.

## The reports

| | |
| --- | --- |
| A | every IRD row → matched locally, or no local invoice. **Sanity gate**: if `no_local_invoice` is large, the join is wrong and B–F mean nothing |
| B | the IRD has the bill, we say Pending/Failed — what a retry would re-file |
| C | we say Synced, the register has no such number, split by docstatus |
| D | submitted, in range, never filed — with the rupee value |
| E | filed amount vs the invoice's grand total |
| F | credit notes submitted to the IRD twice |

`ird_missing_numbers.csv` is report D computed from the register alone: every
number absent from the IRD's own sequence, as 1,016 contiguous blocks with the BS
dates either side. 3,027 sales + 125 returns.

`export_local_numbers.sql` is the no-write alternative — dump the local side and
do the comparison off-box.

## What the register already establishes

- **~18,300 bills are filed that we call Pending or Failed.** NGG 80/81 and 81/82
  reconcile exactly (3,599 and 3,864, zero difference); NGK 82/83's 4,423
  "Failed" bills are 3,878 filed plus 545 genuinely absent. The failures are
  *retries* against bills the IRD already had.
- **`sync_status = 'Synced'` is not trustworthy.** Sampled against the register,
  9 of 10 NGK 81/82 and 7 of 10 NGN 82/83 bills flagged `is_synced = 0` are
  genuinely missing at the IRD. Where the two columns disagree in these years,
  `is_synced` is the one telling the truth.
- **693 credit notes were filed twice** — ₨18,834,903, ₨2,166,847 of VAT — mostly
  NGI 80/81. A duplicate credit-note number cannot exist locally, so the second
  row is a resubmission, not a second document. Only the IRD can correct it.
- **The register's arithmetic is clean.** Tax is 13% of taxable on all 179,790
  rows and total reconciles to within ₨10, with one exception: `NGN013496/82-83`
  is out by 5,660.18 — the same figure `cbms_health_check.sql` reports as NGN
  82/83's worst local VAT gap.

## Why this matters before CBMS is re-enabled

`enable_cbms = 0` on every company and the CBMS retry job is stopped. The day
someone turns CBMS back on, the retry sweeps ~23,000 Pending and ~5,260 Failed
bills and re-files what the IRD already holds — manufacturing at scale exactly
the duplicate this drop already shows 693 instances of. Marking the register's
verdict onto the records is what makes re-enabling safe.

Related: `../cbms_health_check.sql`.
