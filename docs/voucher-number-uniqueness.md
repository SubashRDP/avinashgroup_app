# Voucher number uniqueness

How a voucher number (`custom_name` on Journal Entry, Payment Entry, Purchase
Invoice, Purchase Receipt; `custom_branch_name` on Sales Invoice) is kept
unique. Code: `custom_code/Override/naming_series.py`.

## The rule

**One voucher number per company per fiscal year.** The same number may repeat
in another fiscal year or another company.

Why: the old ERPs restarted every series each fiscal year and numbered each
company on its own, and the legacy number is imported verbatim (copied from
Fact Numbering) with no year in it. Grishma's `GEPL-CN00106` is a 79/80 credit
note *and* an 80/81 one; NGK holds `NGK/000001` in 77/78 and 79/80.

## How the fiscal year is found

From a date, never from the stored `custom_fiscal_year` field (blank on almost
every row; only the desk form fills it). The date is the rule's **Document Date
Field**, else posting date, else transaction date; `get_fiscal_year_from_date`
finds the Fiscal Year row whose range contains it. The duplicate check matches
the year as a date range (`_number_scope_filters` → `_fiscal_year_bounds`).

## Where it is enforced

| Layer | What |
|---|---|
| `_validate_unique_number` (engine rules) and `validate_custom_name_unique` (no rule) | reject a repeat inside company + fiscal year: *"Number X is already used by Y in Company / 80/81"* |
| `_lock_number_scope` | MariaDB named lock per doctype + field + company + year + number, held until commit/rollback, so two users saving the same number at the same instant cannot both pass the check. The check after it is a locking read (`FOR UPDATE`) so it sees the other user's commit. |

There is **no DB unique index** on `custom_name`. It used to be unique across
the whole table, which made the code fall back to a whole-table check and
rejected every 80/81 row whose number also existed in 79/80 (192 rows in one
Grishma import). `patches/scope_custom_name_to_company_fiscal_year` drops it and
keeps a plain index. A unique index cannot express "per fiscal year" without a
stored, always-filled year column — hence the lock instead.

## Gotchas

- A field that *is* DB-unique still gets a whole-table check
  (`_number_scope_filters` returns `{}`), because scoping below the index would
  only turn a readable error into an IntegrityError.
- Document No. (`custom_document_no`) is a separate check with its own scope
  (Group Document No. By) and its own lock (the tabSeries counter row).
- Background workers load code at start: after deploying, `bench restart` or
  Data Import keeps running the old check.
