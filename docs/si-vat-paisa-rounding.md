# Sales Invoice VAT — paisa rounding

Commit `f53925e` on `develop`.

## What changed

Every **amount and total** on a Sales Invoice (and Quotation / Sales Order /
Delivery Note) is now rounded to 2 dp (paisa) at the point it is computed, and
each total is built from the already-rounded lines. Only **rate** fields
(`rate`, `price_list_rate`, `net_rate`, `custom_vat_rate`) keep more decimals.

Fields moved from `flt(x, 5)` to `flt(x, 2)`: `custom_total`, `custom_vat_amount`,
`custom_total_amount`, `custom_total_amount_including_excise`,
`custom_total_excise_amount`, `custom_excise`, `custom_total_vat_amount`, and the
JS `custom_expected_grand_total` preview.

Files: `custom_code/SalesInvoice/salesinvoice_taxes.py`,
`custom_code/common/selling_taxes_handler.py`,
`public/js/sales_invoice.js`, `public/js/selling_taxes_common.js`.

### Printed tax breakup

The VAT/excise tax rows are `charge_type="Actual"`. ERPNext's
`calculate_taxes_and_totals` splits an Actual row across items proportionally by
net amount and rounds each share independently — that split (not
`custom_vat_amount`) feeds the printed "Taxable Amount / VAT" table
(`other_charges_calculation`), so on `NGK-SB-83/84-00527` it printed VAT **237.00**
for a line whose VAT is 236.99.

`pin_item_wise_tax_detail()` (in both handlers, called from `update_taxes_table`
before `calculate_taxes_and_totals`) now writes `item_wise_tax_detail` from the
item rows and sets `dont_recompute_tax = 1`, so ERPNext leaves it alone and the
breakup shows exactly the item VAT column.

## Why

The item VAT column and the header VAT disagreed by a paisa. Per-line VAT was
computed at precision 5 and rounded to 2 only when written, but the header summed
the precision-5 values and rounded once:

| | Before | After |
|---|---|---|
| Item 1 VAT (taxable 1823.01) | 236.9913 | 236.99 |
| Item 2 VAT (taxable 93.26) | 12.1238 | 12.12 |
| Header VAT / tax row | 249.12 | **249.11** |
| Grand total | 2165.39 | **2165.38** |

Example: ng-group `NGK-SB-83/84-00527`.

## Impact

- **New invoices** — VAT column, header VAT, tax row, grand total and the
  "Total Amount" preview all foot. Grand total can move by 1 paisa vs the old
  behaviour.
- **Trade-off** — per-line rounding can leave the VAT total 1 paisa off
  `round(total_taxable × 13%, 2)`. Accepted so the column foots.
- **Existing submitted invoices** — not backfilled; stored totals unchanged.
  `NGK-SB-83/84-00527` still holds 249.12 until amended. If a bill was already
  filed to IRD at the old figure, correcting it later creates a CBMS mismatch.
- **Reports** reading these fields (Sales Register, Sales Bill Details, …) now
  show 2 dp.
- **Deploy** — JS files changed: run `bench build --app avinashgroup_app` and
  clear cache after pulling.
