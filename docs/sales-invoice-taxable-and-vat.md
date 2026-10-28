# Sales Invoice taxable sales and VAT: every place they are calculated

The taxable sales amount and the VAT amount of a Sales Invoice are worked out in more than one place before they reach CBMS (Nepal IRD's billing API), and again when the invoice is printed or reported. This page lists each place side by side: where it is, when it runs, which fields and formula it uses, and what it writes or shows. It ends with the concrete differences and the questions the code does not answer.

Scope: `avinashgroup_app`, plus ERPNext core where our code calls into it. `rdp_common_app` was searched and has no Sales Invoice taxable/VAT code (its only hit is `nepal_hrms_common/payroll/salary_slip_bs.py`, which is payroll). Purchase-side code is out of scope (`custom_code/excise_ledger.py` is hooked on Purchase Invoice only, `hooks.py:131`).

Last checked against the code: 28 October 2026. Read-only review, no code was changed.

---

## 1. Vocabulary

| Field | Where | Meaning |
|---|---|---|
| `base_net_amount` | Sales Invoice Item (core) | Line amount after document discount (when discount is on Net Total), company currency, **excludes excise**. |
| `custom_excise_value` | Sales Invoice Item | Manual excise per line. Forced negative on returns. |
| `custom_total` | Sales Invoice Item | `base_net_amount + custom_excise_value`, 2 dp. The app's "taxable base" per line. |
| `custom_vat_apply_on` | Sales Invoice Item | `VAT 13%` (default), `VAT 0%`, or `Amount` (manual VAT). |
| `custom_vat_amount` | Sales Invoice Item | Per-line VAT, 2 dp. |
| `custom_total_amount` | Sales Invoice | Sum of `base_net_amount` (excise excluded). |
| `custom_total_amount_including_excise` | Sales Invoice | Sum of `custom_total`. |
| `custom_total_vat_amount` | Sales Invoice | Sum of `custom_vat_amount`. |
| `net_total` / `total_taxes_and_charges` / `grand_total` | Sales Invoice (core) | Core totals. `net_total` is the sum of item `net_amount` and excludes excise. `total_taxes_and_charges` is excise plus VAT, because both are `Actual` tax rows (see 3.1). |

Core baseline: `erpnext/controllers/taxes_and_totals.py:354` `calculate_net_total` sets `net_total = sum(item.net_amount)` (`:363`); `:676`/`:685` `set_discount_amount` / `apply_discount_amount` spread a Net Total discount over the items. Core knows nothing about excise or `custom_total`.

---

## 2. Summary table

"NT" = `doc.net_total`. "TT" = `custom_total_amount_including_excise`. "VAT hdr" = `custom_total_vat_amount`.

| # | Place | File:line | When | Taxable formula | VAT formula | Output |
|---|---|---|---|---|---|---|
| 1 | Server tax pipeline | `custom_code/SalesInvoice/salesinvoice_taxes.py:9` `before_save_salesinvoice` (calls `:99`, `:141`, `:183`, `:306`, `:504`) | Sales Invoice `validate` (`hooks.py:174`) | per line `flt(base_net_amount + custom_excise_value, 2)`; header TT = sum | VAT 13%: per line `flt(custom_total*13/100, 2)`; VAT 0%: 0; Amount: manual. Header = sum of lines | item fields, header fields, Excise and VAT `Actual` tax rows |
| 2 | Client form totals | `public/js/sales_invoice.js:591` `sync_custom_totals` | Form edit, hooked into `_calculate_taxes_and_totals` (`:663`) | same as 1 | same as 1; on returns a positive VAT is forced negative | same fields, in the browser |
| 3 | CBMS field build | `custom_code/CBMS/sales_invoice_hooks.py:118` `build_cbms_fields` (with `:84`, `:92`) | Sales Invoice `on_submit` (`:293`), also CBMS backfill | `abs(sum(custom_total))` of lines where `apply_on != 'VAT 0%'`; export invoice: 0 | `_booked_vat`: `abs(sum(custom_vat_amount))` for `VAT 13%`/`Amount` lines, else `custom_total_vat_amount`, else VAT-named tax rows | CBMS Bill / CBMS Bill Return fields |
| 4 | CBMS send | `custom_code/CBMS/api_client.py:42` `_amount`, `:71` / `:100` payload builders | At send (submit, retry, Sync Now) | `flt(bill.taxable_sales_vat, 2)` | `flt(bill.vat, 2)` | JSON to IRD |
| 5 | Legacy annexure import | `legacy_annexure_import/sales_book.py:152-153, 281-282` | Manual import run | read from the sheet column, not computed | read from the sheet column | CBMS Bill / Return rows created as Synced |
| 6 | Print, glmi / grihalaxmi family (6 formats) | `templates/print_formats/grihalaxmi_invoice.html:34-44, 200-208` (same pattern in the others) | At print | `TT or net_total` | `custom_total_vat_amount`, else sum of tax rows whose text contains "vat" | printed Taxable / VAT |
| 7 | Print, Nepal Gas / Aarati / Gita / NG return family (8 formats) | `nepal_gas_invoice.html:352`, `nepal_gas_invoice_half.html:84`, `gita_invoice.html:296` | At print | `net_total` | same VAT rule as 6 | printed Taxable / VAT |
| 8 | Print, Epson HTML (2 formats) | `avinash_invoice_epson.html:206-214`, `grishma_invoice_epson.html:205-213` | At print | `doc.total` / `doc.net_total` row | `doc.total_taxes_and_charges` (excise plus VAT) | printed footer |
| 9 | ESC/P invoice builders (6 files) | `custom_code/printing/escp_invoice.py:232-283`, `escp_gandaki.py:198-251`, `escp_karnali.py:202-253`, `escp_narayani.py:192-245`, `escp_grishma.py:221-279`, `escp_ngi_udyog.py:218-268` | At print (dot-matrix job) | `net_total` | `custom_total_vat_amount`, else tax rows containing "vat" | ESC/P stream |
| 10 | ESC/P Avinash slip | `custom_code/printing/escp_avinash_slip.py:222-223` | At print | `doc.total` | `doc.total_taxes_and_charges` | ESC/P stream |
| 11 | CBMS reports | `report/materialized_report/materialized_report.py:222-238` and `materialized_return_report.py:125-137` | Report run | reads `bill.taxable_sales_vat`; also derives `amount = total_sales + tax_exempted_sales - vat` | reads `bill.vat` | report rows |
| 12 | Sales Register | `report/sales_register_report/sales_register_report.py:561-573` | Report run | `SUM(custom_total)` for `VAT 13%`/`Amount` lines of customers whose territory is exactly `Nepal` | `SUM(custom_vat_amount)` for the same lines | register columns |
| 13 | Sales Report Summary | `report/sales_report_summary/sales_report_summary.py:458-459` | Report run | `SUM(custom_total)`, all lines | `SUM(custom_vat_amount)` | summary rows |
| 14 | Sales Analysis (product-wise, customer-wise) | `sales_analysis_product_wise_invoice_details.py:166-167`, `sales_analysis_customer_wise_details.py:166-168` | Report run | `SUM(sii.amount + sii.custom_excise_value)` | `SUM(custom_vat_amount)` | value / vat columns |
| 15 | Sales Bill Details | `report/sales_bill_details/sales_bill_details.py:281-283` | Report run | header `TT` | header `custom_total_vat_amount` | row |
| 16 | One Lakh Above | `report/one_lakh_above_transactions/one_lakh_above_transactions.py:90-106` | Report run | `+/-abs(sii.amount)` when `custom_vat_amount != 0` | none | taxable / exempt split |
| 17 | `override_rounding.py` | `custom_code/override_rounding.py:6-584` | Not wired (see 3.17) | `custom_excise_duty * qty` + `amount` | recomputed tax rows | none, dead code |

17 distinct places. Places 1 and 2 are meant to agree and do. Place 3 is the only one that produces the CBMS figures.

---

## 3. Details

### 3.1 Server tax pipeline (`salesinvoice_taxes.py`)

Runs inside the `validate` doc event (`hooks.py:173-176`, not `before_save`; the comment at `hooks.py:164-172` explains why). Order inside `before_save_salesinvoice` (`:9`):

1. `ensure_vat_apply_on_defaults` (`:86`): blank `custom_vat_apply_on` becomes `VAT 13%`.
2. `restore_return_item_taxes` (`:196`) and `apply_return_excise_sign` (`:229`): on returns, the `Amount`-mode VAT and the excise are copied back from the original invoice, scaled by `abs(qty)/abs(src.qty)` (`:222-226`), because those fields are `no_copy`.
3. `calculate_custom_total` (`:99`): `item.custom_total = flt(base_net_amount + custom_excise_value, 2)` (`:112`).
4. `calculate_item_vat_amounts` (`:141`): `VAT 13%` sets rate 13 and `custom_vat_amount = flt(custom_total * 13 / 100, 2)` (`:166`). `VAT 0%` sets 0. `Amount` keeps the typed value and forces the rate to 0.
5. `apply_return_vat_sign` (`:242`): on returns every `custom_vat_amount` is set to `-abs(...)`.
6. `calculate_total_vat_amount` (`:183`): `custom_total_vat_amount = flt(sum(custom_vat_amount), 2)`.
7. `calculate_total_excise_amount` (`:128`) and `calculate_total_amount_including_excise` (`:120`).
8. `update_taxes_table` (`:306`): writes an Excise row and a VAT row as `charge_type = "Actual"` with `tax_amount` = the header sums (`:427-478`), and pins `item_wise_tax_detail` to the per-line values (`:363`).
9. `calculate_custom_total_amount` (`:504`): `custom_total_amount = sum(base_net_amount)` (excise excluded).
10. `doc.calculate_taxes_and_totals()` (core), then payment schedule refresh.

Rounding: each line to 2 dp, headers are sums of 2 dp lines. Discount: whatever core already put in `base_net_amount` (Net Total discount is in it; a Grand Total discount is not). Currency: company currency (`base_net_amount`). Exempt: a `VAT 0%` line still has `custom_total` but VAT 0. `validate_salesinvoice` (`:520`, `assert_taxes_table_built` `:539`) throws if VAT or excise was computed but the tax row is missing.

Consequence: because the VAT and excise rows are `Actual`, core's `total_taxes_and_charges` = excise + VAT, and `grand_total = net_total + excise + VAT`. `net_total` itself never contains excise.

### 3.2 Client form totals (`public/js/sales_invoice.js`)

`sync_custom_totals` (`:591-649`) is a field-for-field copy of 3.1 (its own docstring at `:576-584` says so). `custom_total = flt(base_net_amount + excise, 2)` (`:605`); VAT 13% `flt(total*13/100, 2)` (`:618`); VAT 0% 0; Amount `flt(item.custom_vat_amount, 2)` (`:625`). Return rule differs in form only: `if (is_return && vat > 0) vat = -Math.abs(vat)` (`:628`), the server forces negative on every row. Writes headers `custom_total_amount_including_excise`, `custom_total_vat_amount`, `custom_total_amount`, `custom_excise` (`:640-643`). It is chained onto core's `_calculate_taxes_and_totals` by `install_custom_totals_hook` (`:663`). The server recomputes everything on save, so the browser figures are display only.

`public/js/selling_taxes_common.js` has the same arithmetic (`:226-247`) but registers only Quotation, Sales Order and Delivery Note (`:3`), not Sales Invoice.

### 3.3 CBMS field build (`CBMS/sales_invoice_hooks.py`)

Called by `create_cbms_bill` (`:200`) and `create_cbms_bill_return` (`:217`) from `on_submit`, and by `backfill.py:208` (`_create_and_enqueue`). Nothing is read from the CBMS doc later; these values are frozen at creation.

- `_line_value(item)` (`:84-89`): returns `flt(item.get("custom_total"))`. Its docstring says "else base_net_amount" but the code has no fallback.
- `taxable_sales` (`:133-139`): `abs(sum(_line_value(item) for items where custom_vat_apply_on != "VAT 0%"))`. So `Amount` lines are taxable, and so is a line whose `custom_vat_apply_on` is empty.
- `exempt_sales` (`:127-132`): `abs(sum(...))` of the `VAT 0%` lines.
- `vat = _booked_vat(si)` (`:92-115`): `abs(sum(custom_vat_amount))` over lines with `VAT 13%` or `Amount`; if that is 0, `custom_total_vat_amount`; if that is 0, `sum(base_tax_amount)` of tax rows whose `account_head` starts with `VAT`.
- `excise` (`:145`): `abs(sum(custom_excise_value))`; `excisable_amount` = `abs(sum(item.amount))` of lines with excise (uses `amount`, not `base_net_amount`, despite the comment).
- Export (`is_export_invoice` `:72`: currency not NPR, or customer territory outside Nepal): `export_sales = sales_invoice.grand_total`, `taxable_sales = 0`, `total_sales = abs(grand_total)` (`:157-160`). Otherwise `export_sales = 0`, `total_sales = abs(grand_total) - exempt_sales` (`:162-163`).
- `discount` (`:165-167`): `abs(discount_amount)` only when `apply_discount_on == "Net Total"`.
- Output (`:189-190`): `taxable_sales_vat = flt(taxable_sales, 2)`, `vat = flt(vat, 2)`. Sign is dropped with `abs`, so a Sales Return produces positive amounts on CBMS Bill Return.

### 3.4 CBMS send (`api_client.py`)

`_amount` (`:42-46`) is `flt(value, 2)`. `_build_bill_payload` (`:71-90`) and `_build_return_payload` (`:100-118`) put `total_sales`, `taxable_sales_vat`, `vat` and the `_other_sales_fields` (`:49-61`) through it. No recomputation: it reads the stored CBMS doc. HST and ESF are sent as stored (0).

### 3.5 Legacy annexure import (`legacy_annexure_import/sales_book.py`)

Creates CBMS Bill / Return rows for pre-CBMS invoices from a spreadsheet: `taxable = flt(raw[COL["taxable"]])`, `vat = flt(raw[COL["vat"]])` (`:152-153`), `total_sales = grand_total - exempt` (`:157`), written at `:281-282` with `sync_status = "Synced"` and `discount = 0`. Not derived from the Sales Invoice at all. Signs are as in the sheet.

### 3.6 Print formats, glmi / grihalaxmi family

Files: `glmi_return`, `glmi_sales_test`, `grihalaxmi_invoice`, `grihalaxmi_invoice_half`, `grihalaxmi_invoice_return`, `grihalaxmi_invoice_half_return`. Pattern (`grihalaxmi_invoice.html:34-44`):
`taxable = custom_total_amount_including_excise or net_total`; `vat = custom_total_vat_amount`, and only if that is 0, the sum of `t.tax_amount` over tax rows where `'vat'` appears in `description + account_head` (lowercased); `grand_total = rounded_total or grand_total`. Printed at `:200` (taxable), `:204` (VAT), `:208` (grand).

### 3.7 Print formats, Nepal Gas / Aarati / Gita / NG return family

Files: `nepal_gas_invoice` (`:352`), `nepal_gas_invoice_a5` (`:368`), `nepal_gas_invoice_a5_overlay` (`:369`), `nepal_gas_invoice_half` (`:84`), `nepal_gas_invoice_overlay` (`:115`), `ng_group_return_half` (`:69`), `aarati_invoice` (`:234`), `gita_invoice` (`:296`). Taxable = `doc.net_total`. VAT uses the same stored-else-tax-rows rule as 3.6 (`ns2` at e.g. `nepal_gas_invoice_half.html:76`, `aarati_invoice.html:56`). Grand total is `rounded_total or grand_total` in the Nepal Gas formats, but plain `doc.grand_total` in `aarati_invoice.html:242` and `gita_invoice.html:298`. The Nepal Gas formats label the VAT row "13% VAT".

### 3.8 Print formats, Epson HTML

`avinash_invoice_epson.html:206-214` prints `doc.total`, then `doc.total_taxes_and_charges` in the row under it, then `doc.grand_total`. `grishma_invoice_epson.html:205-213` is the same layout. Nothing is derived; whatever core holds is shown. The middle figure is excise plus VAT.

### 3.9 ESC/P invoice builders

Six files share one pattern: `vat = doc.get("custom_total_vat_amount") or 0`, falling back to tax rows with "vat" in the text; `grand = rounded_total or grand_total`; then taxable is printed as `_money(doc.net_total)` and VAT as `_money(vat)`. Lines: `escp_invoice.py:232-237, 282-283`; `escp_gandaki.py:198-203, 250-251`; `escp_karnali.py:202-207, 252-253`; `escp_narayani.py:192-197, 244-245`; `escp_grishma.py:221-226, 278-279`; `escp_ngi_udyog.py:218, 268`.

### 3.10 ESC/P Avinash slip

`escp_avinash_slip.py:222-223`: taxable row `_money(doc.total)`, VAT row `_money(doc.total_taxes_and_charges)`; `grand = doc.get("grand_total")` (`:181`). Same as 3.8, no `custom_*` fields.

### 3.11 CBMS Activity-style reports (Materialized Report, Materialized Return Report)

Both read `bill.taxable_sales_vat` and `bill.vat` from the CBMS doc (`materialized_report.py:233-234, 284-285`; `materialized_return_report.py:134-135, 183-184`), so they show exactly what was sent. They also derive two columns in SQL: `amount = total_sales + tax_exempted_sales - vat` (`:231` / `:132`) and `total_amount = total_sales + tax_exempted_sales`. `cbms_activity_report` and `invoice_activity_report` do not touch these figures.

### 3.12 Sales Register (`sales_register_report.py`)

`get_data` (`:541-600`), one row per invoice: `total_sales = si.custom_total_amount_including_excise` (`:569`); `taxable_sales = SUM(custom_total)` where `custom_vat_apply_on IN ('VAT 13%','Amount') AND c.territory = 'Nepal'` (`:572`); `vat = SUM(custom_vat_amount)` for the same condition (`:573`); `tax_free_sale` = `VAT 0%` lines with territory `Nepal` (`:570`); `export_npr` = `VAT 13%`/`Amount` lines with `c.territory != 'Nepal'` (`:571`). Returns are shown with `abs()` (`:525-530`). Excise is inside `custom_total`, so it is inside taxable.

### 3.13 Sales Report Summary

`:458-459`: `SUM(sii.custom_total) AS taxable_amount`, `SUM(sii.custom_vat_amount) AS vat_amount`, grouped by item/UOM/price list. No `custom_vat_apply_on` filter, so `VAT 0%` lines are inside "taxable". Returns are included or excluded by a filter (`:421`), and are negative when included. `total_amount = taxable + vat` (`:496`).

### 3.14 Sales Analysis (product-wise and customer-wise)

`SUM(sii.amount + sii.custom_excise_value) AS value`, `SUM(sii.custom_vat_amount) AS vat` (`sales_analysis_product_wise_invoice_details.py:166-167`, `sales_analysis_customer_wise_details.py:166-168`). `sii.amount` is the line amount in invoice currency before any document-level discount, not `base_net_amount`. Returns are negative.

### 3.15 Sales Bill Details

`:281-283`: `si.custom_total_amount_including_excise AS amount_before_vat`, `si.custom_total_vat_amount AS vat_amount`, `si.grand_total`. Header fields as saved by 3.1.

### 3.16 One Lakh Above Transactions

`_fetch_sales_rows` (`:83`, SQL `:90-106`): a line counts as taxable if `COALESCE(sii.custom_vat_amount,0) != 0`, with value `+/-abs(sii.amount)` (negative for returns); otherwise it counts as exempted. No VAT figure is produced. It uses `sii.amount`, not `custom_total`, so excise is excluded and the sign is forced by `is_return`.

### 3.17 `override_rounding.py` (not wired)

`recalculate_taxes_on_custom_total` (`:6`), `override_totals_on_submit` (`:426`), `override_totals_before_submit` (`:505`) and friends recompute `custom_total = amount + custom_excise_duty * qty` (`:439-445`), overwrite `base_net_total`, `base_grand_total` and rounding, using fields (`custom_excise_duty`, `custom_difference_calculation_table`) that the live pipeline does not use. A search of `hooks.py` and the app for `override_rounding` finds only comments inside the file itself, so none of this runs on Sales Invoice today. Listed so nobody mistakes it for a live calculation.

---

## 4. Where they differ

### 4.1 Places that agree

| Group | Members | What they share |
|---|---|---|
| Line base and per-line VAT | 1, 2, (selling_taxes_common.js for other doctypes) | `custom_total = base_net_amount + excise`, VAT = `flt(custom_total*13/100, 2)` per line, header = sum of lines. |
| Header copies of 1 | 6 (taxable branch), 12 (`total_sales` column), 15 | Read `custom_total_amount_including_excise` and/or `custom_total_vat_amount` as saved. |
| Line-level SUM of `custom_total` / `custom_vat_amount` | 3, 12, 13 | Same per-line figures, different filters (see 4.2). |
| Net-total printers | 7, 9 | Taxable = `doc.net_total`; VAT = stored `custom_total_vat_amount` else VAT-named tax rows. |
| Stored CBMS values | 4, 11 | Read the frozen CBMS doc as is. |

### 4.2 Concrete discrepancies

1. **Excise inside or outside "taxable".** CBMS taxable (`sales_invoice_hooks.py:133-139`, via `custom_total`) includes excise. The formats in 3.7 and the ESC/P builders in 3.9 print `doc.net_total` (`nepal_gas_invoice.html:352`, `escp_invoice.py:282`), which excludes excise (core `taxes_and_totals.py:363`). The VAT beside it is computed on `net + excise` (`salesinvoice_taxes.py:166`). On any invoice with excise, the printed taxable x 13% does not equal the printed VAT, and the printed taxable is lower than `taxable_sales_vat` sent to CBMS by the excise amount. The 3.6 formats print `custom_total_amount_including_excise or net_total`, so they match CBMS here. Sales Register (`:572`), Sales Report Summary (`:458`), Sales Bill Details (`:281`) also include excise.

2. **Exempt lines in "taxable".** CBMS excludes `VAT 0%` lines from taxable (`:137`). Sales Report Summary sums `custom_total` for every line (`sales_report_summary.py:458`), so its "Taxable Amount" includes zero-rated lines. The print formats in 3.6 use the header sum (`TT`), which also includes `VAT 0%` lines, and so do 3.7, 3.9 (`net_total`).

3. **How "taxable" is detected.** CBMS and Sales Register use `custom_vat_apply_on` (`!= 'VAT 0%'` at `sales_invoice_hooks.py:137`; `IN ('VAT 13%','Amount')` at `sales_register_report.py:572`). One Lakh Above uses `custom_vat_amount != 0` (`one_lakh_above_transactions.py:97`). An `Amount`-mode line with VAT typed as 0, or a `VAT 13%` line whose net is 0, is taxable for CBMS and exempt for One Lakh Above. A blank `custom_vat_apply_on` is taxable in CBMS (it is `!= 'VAT 0%'`) but excluded from Sales Register's `IN` list.

4. **Export / domestic test.** CBMS: `is_export_invoice` (`:72-81`) is true when currency is not NPR or the territory is outside Nepal by ancestry; blank territory and `All Territories` are domestic. Sales Register uses plain `c.territory = 'Nepal'` / `!= 'Nepal'` (`:570-573`): a child territory of Nepal counts as export, `All Territories` counts as export, a NULL territory counts as neither (SQL `NULL != 'Nepal'`), and currency is ignored. A domestic invoice to a non-`Nepal` territory customer appears in CBMS taxable but in the register's `export_npr`.

5. **Export invoices keep VAT but lose taxable.** In the export branch `taxable_sales = 0` (`:159`) but `vat` is still `_booked_vat` (`:140`, `:190`). An export invoice with `VAT 13%` lines sends `taxable_sales_vat = 0` with a non-zero `vat`. Sales Register would report that VAT under a non-Nepal territory as `vat = 0` (`:573` requires `= 'Nepal'`).

6. **Export amount currency and sign.** `export_sales = sales_invoice.grand_total` (`:158`): transaction currency, signed, includes VAT and excise. `total_sales` on the next line is `abs(grand_total)`. For a foreign-currency invoice `grand_total` is not `base_grand_total`, while every `custom_total` is company currency. For an export credit note `export_sales` goes out negative and `total_sales` positive.

7. **Sign convention.** CBMS builder drops the sign with `abs` (`:133, :140`), so a Sales Return reports positive amounts. Sales Analysis (`:166-167`) and Sales Report Summary keep returns negative. One Lakh Above forces the sign from `is_return` (`:98`). Sales Register converts returns to positive (`:525-530`). Compare like with like only after normalising.

8. **Line amount source.** Taxable uses `base_net_amount` in `custom_total` (3.1), but `excisable_amount` uses `item.amount` (`sales_invoice_hooks.py:148-151`), and Sales Analysis (`:166`) and One Lakh Above (`:98`) use `sii.amount`. `amount` is before document discount and in transaction currency. With a Net Total discount, `amount` is higher than `base_net_amount`, so those reports show a larger taxable value than the one CBMS gets, and CBMS also reports the discount separately (`:165-167`).

9. **Grand Total discount.** `discount` is sent only when `apply_discount_on == "Net Total"` (`:166`). With a Grand Total discount, `base_net_amount` and so `custom_total` are not reduced, but `grand_total` is. `total_sales = abs(grand_total) - exempt` (`:163`) is then lower than `taxable_sales_vat + vat`, and `discount` is 0. (Reading from code only; not tested on data.)

10. **No fallback for a missing `custom_total`.** The docstring of `_line_value` (`:85-88`) promises `base_net_amount` when `custom_total` is not set; the code (`:89`) does not. A line with a null `custom_total` (a document that predates the field) adds 0 to taxable, while `_booked_vat` does have a three-step fallback (`:98-115`). Taxable and VAT can therefore be sourced differently on the same old invoice.

11. **VAT source differs from taxable source.** Taxable is a sum over lines of `custom_total`. VAT is a sum over lines of `custom_vat_amount` limited to `VAT 13%`/`Amount` lines (`:98-102`), with header and tax-row fallbacks. Sales Register and Sales Report Summary sum `custom_vat_amount` without the apply-on filter on Summary (`:459`) and with the territory condition on Register (`:573`). Because a `VAT 0%` line's amount is 0, the filter changes nothing unless the data was edited by hand.

12. **Print VAT fallback is a text search.** Prints (3.6, 3.7, 3.9) fall back to summing every tax row whose `description + account_head` contains `vat` when `custom_total_vat_amount` is 0 (`nepal_gas_invoice_a5_overlay.html:164-170`, `escp_invoice.py:232-236`). `_booked_vat` instead tests `account_head` starting with `VAT` (`sales_invoice_hooks.py:109-111`). Different matching rules, and the printed one is substring-based on two fields.

13. **Epson and slip formats show combined tax as VAT.** `doc.total_taxes_and_charges` (`avinash_invoice_epson.html:210`, `grishma_invoice_epson.html:209`, `escp_avinash_slip.py:223`) is excise plus VAT. On an invoice with excise the figure printed on the VAT row is not the VAT sent to CBMS. Their taxable row is `doc.total` / `doc.net_total` (before excise).

14. **Rounding of the grand total.** Prints show `rounded_total or grand_total` in most formats but `grand_total` alone in `aarati_invoice.html:242`, `gita_invoice.html:298`, `escp_avinash_slip.py:181`. CBMS `total_sales` uses unrounded `grand_total` (`:160, :163`) and never `rounded_total`. A printed grand total can differ from CBMS `total_sales` by the rounding adjustment.

15. **Return sign handling client vs server.** Server forces every return row negative (`salesinvoice_taxes.py:253`); the form only flips positive VAT (`sales_invoice.js:628`). The server value wins on save, so the form can briefly show a different sign.

16. **Dead alternative.** `override_rounding.py` (3.17) is a third formula (`amount + custom_excise_duty*qty`) but is not called.

### 4.3 Which differences can move the CBMS figure away from the invoice or the VAT report

- Items 1, 3, 4, 8 and 9 give different taxable figures between CBMS (`build_cbms_fields`) and what the invoice prints or the Sales Register shows for the same invoice.
- Items 5 and 6 only touch export invoices, and only CBMS Bill fields `taxable_sales_vat`, `vat`, `export_sales`.
- Items 7 and 14 are presentation differences (sign, rounding) that make a reconciliation look wrong without any underlying disagreement.
- CBMS values are frozen when the bill row is created. If the invoice's `custom_*` fields change after that (only possible before submit, since the bill is created on submit), nothing updates the bill. The CBMS reports (3.11) then show the frozen values, which is the intent.

---

## 5. Open questions

1. **Does the data contain invoices with excise where the net_total prints are in use?** The code shows the mismatch in 4.2 item 1; how many `Nepal Gas` or `Aarati` invoices carry `custom_excise_value` was not queried.
2. **Is `custom_total` ever null on a submitted invoice on avinas1?** If yes, 4.2 item 10 produces taxable 0 on the CBMS Bill. Not checked against the database.
3. **Grand Total discount in practice.** Is `apply_discount_on = "Grand Total"` ever used? If so 4.2 item 9 applies. Not checked.
4. **Foreign-currency or non-`Nepal` territory customers.** How many exist, and which report is the authority for them (4.2 items 4 to 6).
5. **`custom_total` computed before step 10 of 3.1.** `calculate_custom_total` runs before the final `calculate_taxes_and_totals()` call. The pipeline runs after core's own pass in `validate`, so `base_net_amount` should already be final, but whether a discount spread can change `base_net_amount` between the two passes was not traced.
6. **Taxable for the `Amount` mode.** `Amount` lines count as taxable in CBMS and Register. Whether the manual `custom_vat_amount` is meant to be on top of `custom_total * 13%` is a business rule the code does not state.
7. **`custom_total_amount` vs `custom_total_amount_including_excise` naming.** Two similarly named header fields differ by excise (3.1 step 9 and `sales_invoice.js:640-642`). Any custom print or report outside this repository (Print Format records stored in the database, Server Scripts, Custom Reports) was not searched; only files in the apps were read.
8. **POS Invoice.** No POS-specific code touching these figures was found in `hooks.py` or `custom_code/`.
