# Avinas Vehicle Expense Report

Report path: `avinashgroup_app/avinash_group_app/report/avinas_vehicle_expense/`

Ticket: **TASK-2025-00306 — Vehicle Expense Summary Report Development** (rpl-live, project PRE0003)

## Purpose

A vehicle-wise summary of operating expenses, broken into three buckets —
**Fuel**, **Repair (R/M)**, and **Others** — pulled from both **Purchase Invoice**
and **Journal Entry** postings. One row per vehicle, with a grand total.

Per the spec attachment (`NGK & NGI Vehicle Expenses Details 82.83.xlsx`) the
report must work across companies (NGK, NGI, …) and support filtering by
Company, Date range, Fiscal Year, Department, and Vehicle.

## Expense bucket → account mapping

Buckets are decided by the **Account's `account_name`** using `LIKE` patterns
(case-insensitive), so the report is **company-agnostic** — it automatically
covers every company's accounts without any hardcoded account numbers or
company-abbreviation suffixes.

| Bucket | `account_name LIKE` | Accounts matched (verified on avinashlive2) |
|--------|---------------------|---------------------------------------------|
| **Fuel**   | `%Fuel Expenses%`        | `Fuel Expenses - O/O`, `Fuel Expenses - S/D`, `Fuel Expenses F/P` |
| **Repair** | `%R & M - Vehicles%`     | `R & M - Vehicles O/O`, `R & M - Vehicles S/D`, `R & M - Vehicles F/P` |
| **Others** | `%Other Vehicle Expenses%` | `Other Vehicle Expenses - O/O`, `Other Vehicle Expenses - S/D` |

> Note: the F/P fuel account is named `Fuel Expenses F/P` (no ` - ` separator),
> while O/O and S/D use `Fuel Expenses - O/O` / `- S/D`. The `%Fuel Expenses%`
> pattern catches all three and was verified to produce **no** false positives.

## Data sources & key fields

**Purchase Invoice** (`tabPurchase Invoice` + `tabPurchase Invoice Item`)
- `pic.expense_account` → joined to `tabAccount.name` for bucketing
- `pic.custom_subtype` → the **Vehicle** (custom Link field, label "Vehicle", links to `Vehicle` doctype)
- `pic.amount` → the value added to the bucket
- `pi.docstatus = 1`, dates from `pi.posting_date`

**Journal Entry** (`tabJournal Entry` + `tabJournal Entry Account`)
- `jea.account` → joined to `tabAccount.name` for bucketing
- `jea.custom_subtype` → the **Vehicle** (same custom field exists on JE Account)
- `jea.debit - jea.credit` → the value added to the bucket
- `je.docstatus = 1`, dates from `je.posting_date`

Both sides are combined with `UNION ALL`, then grouped by vehicle. Blank
vehicles (`vehicle_no IS NULL OR = ''`) are excluded.

## Filters

| Filter | Applied as |
|--------|------------|
| Company | `acc.company = %(company)s` — taken from the **Account's own company**, so each company only sees its own expense accounts |
| Department (O/O, S/D, F/P) | `acc.custom_department = %(department)s` — `custom_department` is a Link→Department on Account |
| Fiscal Year | resolves to `year_start_date`/`year_end_date`, applied on `posting_date` |
| Date Range | `posting_date >= period_start_date AND <= period_end_date` |
| Vehicle No | `<child>.custom_subtype = %(vehicle_no)s` |

## What was fixed (2026-06-21)

The original report was broken/incomplete:

1. **Hardcoded NGK-only accounts** — it listed explicit account names like
   `547136 - Fuel Allowance - O/O - NGK`. This (a) only worked for NGK and
   broke for NGI and every other company, and (b) used the wrong accounts
   (`Fuel Allowance` instead of `Fuel Expenses`). Replaced with dynamic
   `account_name LIKE` matching via a join to `tabAccount`.
2. **Company filter** moved from the document's `company` to `acc.company`.
3. **Department filter** — the old code pre-fetched accounts by
   `custom_department` and plucked `account_name`, then compared it against the
   full account `name` (`number - name - abbr`), which never matched. Replaced
   with a direct `acc.custom_department = %(department)s` condition.
4. Excluded blank vehicles from the output.

Commit: `8dde922` on branch `remove-fixtures`
(*fix(vehicle-expense): dynamic, company-agnostic account matching*) —
1 file changed, 43 insertions(+), 304 deletions(-).

## Known open items (not yet done)

1. **Vehicle filter doctype mismatch** — the report column and the JS filter
   still declare `options: "Sub-Ledger Category"`, but the actual
   `custom_subtype` field links to the **`Vehicle`** doctype. The JS filter and
   the column `options` should be changed to `Vehicle`, and the dropdown
   restricted to the selected company via `get_query` →
   `filters: { custom_company: <company> }` (the `Vehicle` doctype has a
   `custom_company` Link→Company field).
2. **Missing filters from spec** — **Month** and **Nepali Date (BS)** are
   required by the ticket but not yet implemented.
3. **Stale test file** — `test_avinas_vehicle_expense.py` imports a non-existent
   module (`vehicle_expense_report`) and functions (`get_pi_conditions`,
   `get_je_conditions`) that don't exist; it needs rewriting to match the
   current `build_conditions`/`prepare_filter_values` API.
