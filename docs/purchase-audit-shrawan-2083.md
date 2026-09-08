# Purchase Invoice audit — Shrawan 2083 (live)

**Site:** `ng-group.raindropinc.com` (production, read-only API access)
**Period:** 2026-07-17 → 2026-08-16 (Shrawan 2083)
**Population:** 1,625 submitted Purchase Invoices, 1,712 item rows
**Date of audit:** 2026-09-06

Seven identity checks were run over every submitted purchase invoice in the
period. Three failed. The rounding issues are worth pennies; **one is worth
Rs 3,710.96 and is a tax-credit exposure.**

| # | Check | Result |
|---|-------|--------|
| A | `grand_total` = `net_total` + `total_taxes_and_charges` | pass |
| B | `total_taxes_and_charges` = VAT + excise − TDS | **FAIL — 37 docs, Rs +3,710.96** |
| C | header VAT = sum of item `custom_vat_amount` | **FAIL — 7 docs, Rs +0.08** |
| D | header TDS = sum of item `custom_tds_amount` | **FAIL — 2 docs, Rs +0.03** |
| E | `custom_total_amount_including_excise` = item `custom_total` column | pass |
| F | `custom_total_amount_including_excise` = `net_total` + excise | pass |
| G | `grand_total` = item columns (VAT + excise − TDS) | fails on 32 docs — a consequence of B, not separate |

---

## Finding 1 — Stale VAT tax rows (Rs 3,710.96) — PRIORITY

**37 invoices carry a VAT charge in the taxes table while every item on
them is `VAT 0%` and `custom_vat_amount = 0`.** The VAT is real in the ledger: it
inflates `grand_total`, the supplier payable, and the input-VAT credit claimed.

`NGG-PI-83/84-00043-1` is the clearest case:

```
item 1   NGG-ITEM-00131   amount 3,078.00   custom_vat_apply_on "VAT 0%"   custom_vat_amount 0.00
tax row  VAT - NGG        charge_type Actual   tax_amount 400.14
grand_total 3,478.14      (should be 3,078.00)
```

Note that 400.14 is exactly 13% of 3,078.00 — the row was written while the item
was still `VAT 13%`, then the item was switched to `VAT 0%` and **the row was
never cleared**. On `NGN-PI-83/84-00105` the stale amount (95.25) bears no
relation to the current net (339.00) at all, confirming it is a leftover from an
earlier state of the document.

### Root cause

`custom_code/common/purchase_taxes_handler.py`, `update_taxes_table()`:

```python
if excise_account and total_excise != 0:
    update_or_create_tax_row(...)
    position += 1
else:
    remove_excise_tax_rows(doc)          # excise: cleaned up

if vat_account and total_vat != 0:
    update_or_create_tax_row(...)
    position += 1
                                         # VAT: NO else -- stale row survives

if tds_account and total_tds != 0:
    update_or_create_tax_row(...)
    position += 1
else:
    remove_tds_tax_rows(doc)             # TDS: cleaned up
```

Excise and TDS both clear their row when the total drops to zero. VAT does not.
When `total_vat` becomes 0 the branch is simply skipped and whatever row exists
is left untouched, with its old amount.

The Sales Invoice handler does not have this bug — `salesinvoice_taxes.py` guards
with `if vat_account and (total_vat != 0 or has_tax_row(doc, vat_account))`, so a
zeroed VAT updates the row to 0 instead of abandoning it. **This is
purchase-only.** Verified: 8,822 live Sales Invoices in the same period, zero
failures on checks A and B.

### Exposure by company

| Company | Invoices | Overstated VAT (Rs) |
|---------|---------:|--------------------:|
| Nepal Gas Udhyog (Narayani) Pvt. Ltd. | 28 | 2,510.58 |
| Nepal Gas Udhyog (Gandaki) Pvt. Ltd. | 3 | 1,200.42 |
| Grihalaxmi Metal Industries Pvt. Ltd | 1 | 0.01 |
| Nepal Gas Udhyog Pvt. Ltd. | 5 | -0.05 |

### All affected invoices

| Invoice | Date | Net total | VAT tax row | Grand total | Overstated |
|---------|------|----------:|------------:|------------:|-----------:|
| `GLMI-PI-83/84-00006` | 2026-08-14 | 3,503.00 | 402.85 | 3,905.85 | **+0.01** |
| `NGG-PI-83/84-00043-1` | 2026-08-07 | 3,078.00 | 400.14 | 3,478.14 | **+400.14** |
| `NGG-PI-83/84-00045` | 2026-08-07 | 3,078.00 | 400.14 | 3,478.14 | **+400.14** |
| `NGG-PI-83/84-00047` | 2026-08-08 | 2,739.00 | 400.14 | 3,139.14 | **+400.14** |
| `NGN-PI-83/84-00006-1` | 2026-07-20 | 678.00 | 88.14 | 766.14 | **+88.14** |
| `NGN-PI-83/84-00008` | 2026-07-20 | 339.00 | 88.14 | 427.14 | **+88.14** |
| `NGN-PI-83/84-00010` | 2026-07-20 | 339.00 | 88.14 | 427.14 | **+88.14** |
| `NGN-PI-83/84-00012` | 2026-07-20 | 678.00 | 88.14 | 766.14 | **+88.14** |
| `NGN-PI-83/84-00014` | 2026-07-21 | 678.00 | 88.14 | 766.14 | **+88.14** |
| `NGN-PI-83/84-00016` | 2026-07-21 | 678.00 | 88.14 | 766.14 | **+88.14** |
| `NGN-PI-83/84-00066-1` | 2026-08-03 | 678.00 | 88.14 | 766.14 | **+88.14** |
| `NGN-PI-83/84-00069` | 2026-08-04 | 339.00 | 88.14 | 427.14 | **+88.14** |
| `NGN-PI-83/84-00071` | 2026-08-04 | 339.00 | 88.14 | 427.14 | **+88.14** |
| `NGN-PI-83/84-00073` | 2026-08-05 | 339.00 | 88.14 | 427.14 | **+88.14** |
| `NGN-PI-83/84-00079` | 2026-08-06 | 678.00 | 88.14 | 766.14 | **+88.14** |
| `NGN-PI-83/84-00080` | 2026-08-06 | 678.00 | 88.14 | 766.14 | **+88.14** |
| `NGN-PI-83/84-00082` | 2026-08-06 | 693.66 | 88.14 | 781.80 | **+88.14** |
| `NGN-PI-83/84-00084` | 2026-08-06 | 1,032.66 | 88.14 | 1,120.80 | **+88.14** |
| `NGN-PI-83/84-00085` | 2026-08-07 | 1,032.66 | 88.14 | 1,120.80 | **+88.14** |
| `NGN-PI-83/84-00086` | 2026-08-09 | 339.00 | 88.14 | 427.14 | **+88.14** |
| `NGN-PI-83/84-00088` | 2026-08-09 | 339.00 | 88.14 | 427.14 | **+88.14** |
| `NGN-PI-83/84-00090` | 2026-08-09 | 774.00 | 88.14 | 862.14 | **+88.14** |
| `NGN-PI-83/84-00092` | 2026-08-09 | 339.00 | 88.14 | 427.14 | **+88.14** |
| `NGN-PI-83/84-00099-1` | 2026-08-11 | 1,032.66 | 95.25 | 1,127.91 | **+95.25** |
| `NGN-PI-83/84-00093` | 2026-08-11 | 1,032.66 | 88.14 | 1,120.80 | **+88.14** |
| `NGN-PI-83/84-00095` | 2026-08-11 | 339.00 | 88.14 | 427.14 | **+88.14** |
| `NGN-PI-83/84-00097` | 2026-08-11 | 1,032.66 | 88.14 | 1,120.80 | **+88.14** |
| `NGN-PI-83/84-00101` | 2026-08-12 | 678.00 | 95.25 | 773.25 | **+95.25** |
| `NGN-PI-83/84-00103` | 2026-08-13 | 678.00 | 95.25 | 773.25 | **+95.25** |
| `NGN-PI-83/84-00105` | 2026-08-13 | 339.00 | 95.25 | 434.25 | **+95.25** |
| `NGN-PI-83/84-00107` | 2026-08-16 | 339.00 | 95.25 | 434.25 | **+95.25** |
| `NGN-PI-83/84-00109` | 2026-08-16 | 499.00 | 95.25 | 594.25 | **+95.25** |
| `NGI-PI-83/84-00023` | 2026-08-11 | 88.50 | 11.50 | 100.00 | **-0.01** |
| `NGI-PI-83/84-00024` | 2026-08-12 | 88.50 | 11.50 | 100.00 | **-0.01** |
| `NGI-PI-83/84-00025` | 2026-08-12 | 88.50 | 11.50 | 100.00 | **-0.01** |
| `NGI-PI-83/84-00026-1` | 2026-08-12 | 88.50 | 11.50 | 100.00 | **-0.01** |
| `NGI-PI-83/84-00038-1` | 2026-08-16 | 88.50 | 11.50 | 100.00 | **-0.01** |

### Fix

Give VAT the same cleanup the other two have:

```python
if vat_account and (total_vat != 0 or has_tax_row(doc, vat_account)):
    update_or_create_tax_row(doc, vat_account, total_vat, position,
                             f"VAT - {doc.company}", "Actual", "Add")
    position += 1
```

`has_tax_row()` already exists in the module. This mirrors the sales handler:
when VAT falls to zero the row is rewritten to 0 rather than left stale.

Forward-only. The 37 existing invoices keep their inflated totals until
amended — see Recommendations.

---

## Finding 2 — VAT rounding drift (Rs +0.08)

Fixed in commit `ab93a90` (not yet deployed to live). Per-line VAT was computed
at 5 dp while ERPNext's `round_floats_in()` stores each item row at 2 dp, so the
header summed unrounded values and landed above the item column.

| Invoice | Date | Charged | Should be | Diff |
|---------|------|--------:|----------:|-----:|
| `NGI-PI-83/84-00052-4` | 2026-08-16 | 414,002.60 | 414,002.58 | +0.02 |
| `NGI-PI-83/84-00023` | 2026-08-11 | 11.51 | 11.50 | +0.01 |
| `NGI-PI-83/84-00024` | 2026-08-12 | 11.51 | 11.50 | +0.01 |
| `NGI-PI-83/84-00025` | 2026-08-12 | 11.51 | 11.50 | +0.01 |
| `NGI-PI-83/84-00026-1` | 2026-08-12 | 11.51 | 11.50 | +0.01 |
| `NGI-PI-83/84-00038-1` | 2026-08-16 | 11.51 | 11.50 | +0.01 |
| `NGI-PI-83/84-00044-1` | 2026-08-16 | 792.71 | 792.70 | +0.01 |

Month totals: VAT charged **61,325,246.06**, item columns **61,325,245.98**.

This matters because `purchase_register_report` — the government VAT Purchase
Book (खरिद खाता, Rule 23(1)(chha)) — sums the **item** field, while the GL input
credit comes from the tax row. The filed book and the ledger disagree on these
seven documents.

Only `NGI` invoices appear: they are the multi-line gas invoices (20+ rows), and
drift accumulates per line. Single-line invoices cannot drift more than half a
paisa.

---

## Finding 3 — TDS rounding drift (Rs +0.03)

Same mechanism, same commit.

| Invoice | Date | Deducted | Should be | Diff |
|---------|------|---------:|----------:|-----:|
| `NGI-PI-83/84-00052-4` | 2026-08-16 | 49,158.61 | 49,158.59 | +0.02 |
| `GLMI-PI-83/84-00006` | 2026-08-14 | 52.55 | 52.54 | +0.01 |

Month totals: TDS deducted **418,823.02**, item columns **418,822.99**. Unlike
VAT this is money actually withheld from suppliers, so the 3 paisa was over-withheld.

*Caveat:* the API rejected `apply_tds` as a queryable field, so the "should be"
column sums `custom_tds_amount` across all item rows while the server totals only
rows with `apply_tds` ticked. If any row carries an amount with the box unticked
these two figures would differ. The VAT figures have no such caveat.

---

## Checks that passed

- **`grand_total` arithmetic is sound.** Every one of the 1,625 invoices satisfies
  `grand_total = net_total + total_taxes_and_charges`. Where the grand total is
  wrong (Finding 1) it is wrong because the tax row feeding it is wrong, not
  because the addition is.
- **Excise is consistent** — header, item column and `net_total + excise` all agree
  on every invoice.
- **Sales is clean** — 8,822 live Sales Invoices in the same period, zero failures
  on checks A and B. A 500-invoice sample also showed no VAT column drift, though
  all 500 happened to be single-line, so that sample cannot detect accumulation.

---

## Recommendations

1. **Fix the stale VAT row** (Finding 1) and deploy. It is a three-line change and
   it is the only finding with material money attached.
2. **Deploy `ab93a90`** (Findings 2 and 3) to live — it is committed but unpushed,
   and needs `bench build` + `sudo supervisorctl restart frappe-bench-web:`.
3. **Decide on the 37 existing invoices.** Rs 3,710.96 of input VAT has been
   claimed on zero-rated purchases across four companies. Amending submitted
   invoices is disruptive, but this is a tax position, not a rounding cosmetic —
   it should be a conscious decision by whoever signs the VAT return, not left to
   default.
4. **Leave the paisa differences alone.** Rs 0.08 and Rs 0.03 across a month do not
   justify amending live submitted documents.
