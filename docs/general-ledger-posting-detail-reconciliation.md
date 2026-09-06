# General Ledger Posting Detail — reconciliation against ERPNext's General Ledger

Every opening and closing balance this report produces, checked against the
figure ERPNext's own General Ledger gives for the same filters. Run on
`nepalgas`, all 7 companies, fiscal years 82/83 and 83/84.

Tolerance is 0.05. ERPNext carries float drift through its currency
conversion (its opening for one account reads `11246638568.07458`), so an
exact-equality test would fail on arithmetic noise rather than on a
disagreement about the figures.

## Result

| Filter shape | Comparisons | Matched | Worst delta |
| --- | ---: | ---: | ---: |
| Account | 56 | **56** | 0.000147 |
| Account + Party Type + Party | 11 | **11** | 0.000002 |
| Profit & Loss account | 14 | 4 | *differs by design — see below* |

**67 of 67 balance-sheet comparisons agree.** The largest
disagreement anywhere is 0.00015 on figures in the billions.

## The one deliberate difference: P&L opening balances

10 of 14 Profit & Loss comparisons differ, and they are meant to.

An Income or Expense account does not carry a balance across a year end — a
Period Closing Voucher sweeps it into retained earnings. **This site has run
none**, so ERPNext's General Ledger has nothing to stop it reaching back
through every year of history:

| Company | FY | Account | ERPNext opening | This report |
| --- | --- | --- | ---: | ---: |
| NGU (Narayani) Pvt. Ltd. | 83/84 | 411101 - LP Gas Sales - NG | -9,721,111,384.16 | **0.00** |
| NGU (Narayani) Pvt. Ltd. | 82/83 | 411101 - LP Gas Sales - NG | -8,518,124,027.53 | **0.00** |
| NGU (Gandaki) Pvt. Ltd. | 83/84 | 411101 - LP Gas Sales - NG | -7,449,693,245.72 | **0.00** |
| NGU (Gandaki) Pvt. Ltd. | 82/83 | 411101 - LP Gas Sales - NG | -6,517,611,691.97 | **0.00** |
| NGU (Karnali) Pvt. Ltd. | 83/84 | 411101 - LP Gas Sales - NG | -2,285,479,963.31 | **0.00** |
| NGU (Karnali) Pvt. Ltd. | 82/83 | 411101 - LP Gas Sales - NG | -1,965,848,277.24 | **0.00** |

`LP Gas Sales` opening at −9,721,111,384.16 is every sale the company has
ever made, presented as the balance brought into this year. This report
floors a P&L opening at the fiscal year start, so the account opens flat,
which is what a fiscal-year ledger should show. It is also the single
largest cost saved: that floor took the opening-balance query from 11.70s
to 0.04s.

Running Period Closing Vouchers for the closed years would make both reports
agree, and would speed up every balance report on the site.

## What was found and fixed getting here

| Defect | Effect | Commit |
| --- | --- | --- |
| Opening ignored Voucher Type / Subtype / Party | A month closed higher than the year containing it — opening was the whole account while the postings were one customer's invoices | `aa2f5fb` |
| Empty period returned nothing | Splitting a year in two left the second half blank instead of opening on the first half's closing | `21fb11e` |
| `is_opening` ignored entirely | 1,139 opening entries on 2025-07-17 counted as movement; every 82/83 section would open at zero and show 2,240,560,150.95 of imaginary activity | `c3c48f8` |
| Closing accumulated rather than derived | Section and grand closings disagreed by 4.5e-08 while displaying identically | `35f07f2` |
| Grand block restated a single section | The same figure printed four times on a one-account run | `2ccd14e` |

## Invariants held

Beyond the ERPNext comparison, four properties that must hold whatever the filters:

1. Grouping by Account, Party or Both gives the same totals
2. One account filtered equals that account's section in the full run
3. Consecutive periods join up — part 1's closing is part 2's opening, movements add to the whole
4. Three parties filtered separately sum to filtering them together

And with `is_opening` present, every balance-sheet account reconciles to raw
GL in both modes — 62 accounts with opening entries folded into the balance,
97 with them shown as postings, none off.

## Confirmed on live

Deployed to `ng-group` 2026-09-03 and re-checked there against the same
ERPNext General Ledger, on the six busiest accounts of all seven companies
for FY 83/84:

| | Comparisons | Matched |
| --- | ---: | ---: |
| Balance sheet | 36 | **36** |
| Profit & Loss (`411101 - LP Gas Sales`) | 5 | differs by the opening floor only |

Every P&L difference is the opening alone — subtract it and the closings
agree exactly, so the period movement is identical in both reports. NGK, for
instance, closes at -70,996,609.90 here against -2,356,476,573.21 in ERPNext,
a difference of -2,285,479,963.31, which is precisely the opening ERPNext
carries in and this report floors at the year start.

The reported contradiction that started this work is gone on live: for one
customer's Sales Invoices, fiscal year 83/84 and a month inside it now both
close at 719,727,746.63.

## Not covered

- **Voucher Type and Voucher Subtype** have no counterpart in ERPNext's
  General Ledger, so those filters are verified against raw GL rather than
  against another report.

