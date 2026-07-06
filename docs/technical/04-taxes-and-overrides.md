# VAT / Excise / TDS, Doctype Overrides & Document Numbering — Technical Reference

> Chapter 4 of the technical documentation. Audience: developers.
> User-facing guide: [`../user_guide/04-buying-selling-vat.md`](../user_guide/04-buying-selling-vat.md)

This chapter covers the custom tax scheme, the nine ERPNext class overrides,
the branch-wise warehouse system, the voucher-numbering engine, credit control,
cheque bounce, vehicle-mandatory validation, stock adjustment, and the
legacy/dormant code you should *not* build on.

---

## 1. The custom VAT / Excise / TDS scheme

Replaces ERPNext's Item-Tax-Template VAT with a **per-line "Apply On"
selector** plus manual excise.

### 1.1 Custom fields

Item rows (PI/PO/PR/SQ items; SI/Quotation/SO/DN items):

| Field | Behavior |
|-------|----------|
| `custom_vat_apply_on` | Select `VAT 13%` / `VAT 0%` / `Amount`. JSON default is `VAT 0%` but every code path forces `VAT 13%` when empty — the effective default is 13% |
| `custom_vat_rate` | Percent, read-only (13 or 0) |
| `custom_vat_amount` | auto-calculated; editable only in `Amount` mode |
| `custom_excise_value` | always manual, never recalculated |
| `custom_total` | `base_net_amount + custom_excise_value` — the VAT base |
| `custom_subtype` | Link → Vehicle (PI items + JE accounts; see §7) |
| PI-only TDS | `custom_tds_apply_on` (`Percentage (%)`/`Amount`), `custom_tds_rate` (RO), `custom_tds_amount`, stock `apply_tds` |

Document level: PI — `custom_total_amount_including_excise`,
`custom_total_excise_amount`, `custom_total_vat_amount`,
`custom_total_tds_amount`, `custom_tax_withholding_category_custom` (a
**separate** Link to Tax Withholding Category so ERPNext's native TDS engine
never triggers). SI — `custom_excise`, `custom_vat`, excise/VAT totals.

### 1.2 Calculation rules (identical everywhere)

- `VAT 13%` → rate 13, `vat = custom_total × 0.13` (recalculated, RO)
- `VAT 0%` → rate 0, amount 0
- `Amount` → rate 0, manual amount kept

### 1.3 Taxes-table injection

Handlers write `Actual` rows into the standard `taxes` table, positioned:
Excise (account prefix **`348204`**, Add, pos 0) → VAT (account prefix
**`VAT`**, Add, pos 1) → TDS (account from the custom category's per-company
Accounts row, **Deduct**, pos 2). Accounts are resolved by prefix per company
(`find_account_by_prefix`), then `doc.calculate_taxes_and_totals()` folds them
into totals and standard GL. Selling/SI handlers zero a stale row (rather than
leaving old charges) when total becomes 0 but a tax row exists.

### 1.4 Handlers and wiring

| File | Doctypes | Events |
|------|----------|--------|
| `custom_code/common/purchase_taxes_handler.py` | PI, PO, PR, SQ (+ MR/RFQ warehouse-only) | `before_validate` (return qty sign + fill missing warehouse), `before_save` (full recompute + tax injection), `validate` (`validate_custom_fields` + `force_buying_warehouse`) |
| `custom_code/common/selling_taxes_handler.py` | Quotation, SO, DN | `before_validate`/`before_save`; the selling `validate` events route to `salesinvoice_taxes.validate_*` (warehouse forcing) |
| `custom_code/SalesInvoice/salesinvoice_taxes.py` | Sales Invoice (+ selling `validate_*` wrappers) | full recompute, tax injection, `force_selling_warehouse`, return signs |

TDS (PI only, `purchase_taxes_handler.py:173`): fires only when the document's
`custom_tax_withholding_category_custom` is set **and** the row's `apply_tds`
is checked. `Percentage (%)` mode pulls the rate from the category's first
`rates` row; `Amount` mode keeps the manual amount. Stale TDS rows are removed
when the account/total disappears.

Return handling: `is_return` PI and SI force qty and `custom_vat_amount`
negative (`apply_return_qty_sign` / `apply_return_vat_sign`); DN is the only
selling doctype with return sign logic.

### 1.5 Cross-document mapping — `common/purchase_taxes_mapper.py`

`get_taxes_from_source` (whitelisted) returns doc- and item-level tax values;
called by `purchase_taxes_common.js` when a PO/PR/PI is created from a source
doc, matching items by link field then item_code. (The `after_mapping_*`
functions in the same file are unreferenced legacy.)

### 1.6 Client scripts

| Script | Load | Role |
|--------|------|------|
| `purchase_taxes_common.js` (v1.8) | global | PI/PO/PR/SQ: VAT/TDS defaults, live math mirror, field-visibility toggles per mode, return signs, source-doc tax population, TDS-rate fetch, PI due-date from Supplier `custom_payment_term_days`, warehouse forcing on save; wraps `frappe.call` around `get_item_details` to inject `custom_buying_warehouse` race-free |
| `selling_taxes_common.js` | global | Quotation/SO/DN mirror (no TDS) |
| `sales_invoice.js` (v10.5) | global | SI mirror + selling warehouse injection + due date from Customer `custom_days_limit` |
| `sales_warehouse_common.js` | global | Quotation/SO/DN warehouse injection + save sweep |
| `pi.js` (doctype_js PI) | PI | Vehicle picker for `custom_subtype`: allowed vehicles = the item's expense Account's `custom_sub_type_list.vehicle_list` |
| `journal_entry.js` (doctype_js JE) | JE | same vehicle picker keyed by account |

---

## 2. Doctype class overrides (`custom_code/Override/overrides.py`)

Registered in `hooks.py:230-240`. Two purposes: **(a)** preserve item
warehouses copied from source docs during `get_mapped_doc` flows
(`_restore_warehouse`, only at creation — never overwrites later user edits);
**(b)** soften ERPNext's "Warehouse is mandatory for stock Item" validation so
the app's own warehouse-forcing can run (either swallow `validate_warehouse`
exceptions or selectively pass only that specific ValidationError).

| Class | Restores warehouse from | Extra |
|-------|------------------------|-------|
| SalesOrder | Quotation Item | |
| DeliveryNote | Sales Order Item | |
| CustomSalesInvoice | Delivery Note Item, else Sales Order Item | |
| RequestforQuotation | Material Request Item | selective validate swallow |
| SupplierQuotation | RFQ Item | selective swallow |
| PurchaseOrder | Supplier Quotation Item | + `validate_workflow` bypass for Administrator on "Purchase Order Workflow" |
| PurchaseReceipt | Purchase Order Item | |
| PurchaseInvoice | Purchase Receipt Item, else PO Item | |
| MaterialRequest | — | `validate_workflow` bypass for Administrator on "Material Request One-Line Approver" |

Other overrides in `Override/`:

- **`get_item_details.py`** — wraps ERPNext's whitelisted `get_item_details`:
  applies the item-price patch, strips the `cmd` kwarg, delegates.
- **`auto_insert_item_price.py`** — idempotent monkey-patch (also a global
  `before_request` hook) making ERPNext's auto-created Item Prices carry
  `company`/`custom_company` from the transaction (Item Price company is
  mandatory on this site).
- **`query_report.py`** — report "Add Column" shows a Link field's display name
  instead of its id.

---

## 3. Branch-wise warehouse system

Mapping lives on **Item** child table `custom_branch_wise_warehouse` (child
doctype **Branch Wise Warehouse**; ⚠️ its operative fields `custom_branch`,
`custom_buying_warehouse`, `custom_selling_warehouse` are site-DB custom fields
— the exported JSON only has a placeholder). Item-level
`custom_buying_warehouse`/`custom_selling_warehouse` are the fallback.

Resolution per item row: branch row matching the doc's `custom_branch` →
item-level fallback → leave ERPNext's value (a manually chosen warehouse is
preserved when no mapping exists). Enforced in three layers: JS `frappe.call`
wrap of `get_item_details` (race-free), JS `before_save` sweeps, and the server
`force_buying_warehouse`/`force_selling_warehouse` in the `validate` hooks
(these win over ERPNext).

---

## 4. Voucher numbering engine (`Override/naming_series.py`, 31 KB)

**Wiring:** not directly in hooks.py — dispatched by `AuditEventMapper`
(`utils/audit_file_manager.py`) on `autoname`, `validate`, `before_save`,
`before_insert`, `after_delete` for every audited doctype (chapter 6 §3.3).

> The type codes embedded in voucher numbers come from **DB-only code-list
> doctypes**: Purchase Type, Receipt type, Payment - Receipt Type, JV Type
> (each maps a type name → a code, fetched into `custom_p_type_code`). They are
> not in the repo — see [chapter 11 Part C](11-custom-fields-and-doctypes.md#part-c--db-only-custom-doctypes-in-the-module-not-in-the-repo).

- `NAMING_CONFIG` (`:28-530`) — ~100 doctypes → prefix / sequence length /
  fiscal-year flag / return prefix (e.g. Sales Invoice `SB`/`SRTN`, PI
  `PI`/`PRTN`, PR `GRN`, JE `JE`, PE `PAY.REC`). FY pattern:
  `{abbr}-{prefix}-{fy}-{#######}`, date from
  `posting_date → transaction_date → attendance_date → custom_created_on`.
- `AUTO_NUMBER_CONFIG` (`:532-562`) — which (doctype, type-field, types) get
  the **auto-incrementing `custom_document_no`**: PR "Other Purchase Receipt";
  PI "Purchase Return"; PE "Bank Customers Receipt"/"NOC Payment"/"Contra
  Voucher- cash to bank"; JE "Bank Entry"/"Party Journal"/"Debit Note"/"Credit
  Note". A user-typed number is **left untouched** (`:750-757`) — number+word
  (`custom_document_word`, e.g. `65A`) together identify the voucher.
- `set_custom_name_field` (`:782`) assembles the human voucher no:
  `custom_name = "{abbr}-{p_type_code}-{doc_no}{word}-{fy}{amend_suffix}"` →
  e.g. **`SGU-RC-000006-82/83`**. Zero-pad width from **Voucher Number
  Settings Item** (`voucher_no_digits`, default 6). Company "Grihalaxmi Metal
  Industries Pvt. Ltd" gets a blank custom_name by design.
- `validate_custom_name_unique` (`:857`) — voucher uniqueness among
  docstatus<2 (cancelled excluded so amendments reuse numbers);
  `validate_document_no` — positive integer only.
- `set_custom_branch_name` (`:933`) — per-branch series
  `{abbr}-{branch_code}-{seq6}-{fy}` via `getseries`, **only** for company
  `Grishma Enterprises Pvt. Ltd.` (`BRANCH_CODE_CONFIG`, `:9-25`); other
  companies fall back to `doc.name`. This is what CBMS uses as the invoice
  number (chapter 5).
- `revert_series_on_delete` (`:1011`) — decrements `tabSeries` if the deleted
  doc held the highest number, so numbers are reused.
- `get_next_custom_document_no` (whitelisted) — preview for
  `public/js/auto_update_document_no.js` (PR/PI/PE/JE forms auto-fill
  `custom_document_no` on load and when series-scope fields change).

Console backfills: `custom_code/voucher_no_console.py` (legacy, zfill 5) and
`scripts/pad_custom_name.py` (pad to 6 digits, dry-run by default).

---

## 5a. IRD print-copy labeling (`SalesInvoice/print_count.py`)

**Why:** Nepal IRD e-billing rules require the software to count how many times
an invoice is printed and to label reprints as copies of the original:

```
1st print  → Tax Invoice
2nd print  → Copy of Original
3rd print  → Copy of Original 2
nth print  → Copy of Original (n-1)
```

**Wiring:** Sales Invoice `before_print` (`hooks.py:82`).

- The counter (`custom_print_count`, an Int custom field added by patch
  `add_sales_invoice_print_count`) increments **only on an actual print** —
  detected by `is_actual_print()` (`print_count.py:32-36`): the browser Print
  button (`trigger_print=1`) or a PDF/server-print `cmd` in
  `PRINT_OUTPUT_CMDS` (`download_pdf`, `download_multi_pdf`, `print_by_server`,
  weasyprint). Rendering the Print **preview** does **not** consume a number.
- `before_print` (`print_count.py:39-66`): submitted invoice + real print →
  atomic `UPDATE ... SET custom_print_count = custom_print_count + 1` then
  `frappe.db.commit()` (printview/download are GET requests, so it must commit
  explicitly to survive request-end rollback). Otherwise (preview / draft /
  cancelled) it stamps `stored + 1` **in memory only** — the render shows the
  title the next print *will* get, without consuming it.
- The print format reads `custom_print_count` to choose the title.

## 5. GL manipulation

- **`custom_code/excise_ledger.py`** — only `modify_gl_entries` (`:657`) is
  wired (PI `before_submit`): monkey-patches the instance's `get_gl_entries` so
  TDS-payable GL lines (accounts under `348100 - TDS Payable - {abbr}`) get
  `party_type="Supplier"` + `party` stamped — TDS ledgers reconcile per
  supplier. ⚠️ Everything else in this 32 KB file is dead code with hardcoded
  `GLMI` accounts — do not revive.
- **`custom_code/payment_entry/cheque_bounce.py`** —
  `make_cheque_bounce_entry(pe)` (whitelisted; "Cheque Bounce" button on
  submitted Payment Entries, `payment_entry.js`): posts a full debit↔credit
  swap of the PE's GL (same voucher_type/no, posting_date today, remarks
  `Cheque Bounce - {name}`, `update_outstanding="Yes"` → invoice outstanding
  reopens), sets `custom_cheque_bounce="Cheque Bounced"`. Duplicate-guarded.
  The PE itself is not cancelled.
- **`custom_code/stock_revaluation.py`** — `on_purchase_invoice_submit` (PI
  `on_submit`): for backdated update-stock PIs, msgprints that valuation
  reposting runs in the nightly job. Helpers `nightly_process_pending_reposts`
  (restarts failed Repost Item Valuation, `long` queue), whitelisted
  `reprocess_all_pending` / `get_repost_status`. ⚠️ The nightly job is **not**
  in `scheduler_events` — invoke manually or schedule separately.
- **`custom_code/regional_deletion_override.py`** — monkey-patch applied at app
  import (`__init__.py`): Administrator/System Manager may delete submitted
  transactions of Nepal companies; everyone else falls through to ERPNext's
  regional guard.

---

## 6. Credit control (⚠️ currently dormant)

`SalesInvoice/salesinvoice_customer.py` — whitelisted
`check_customer_credit_limit_on_load` / `_on_save` reading Customer
`custom_days`, `custom_amount`, `custom_bill_count` (outstanding from Customer
Ledger Summary; overdue via SQL). These are called only from `public/js/si.js`,
**which is not loaded by hooks.py** — so the feature is currently unwired.
`SalesInvoice/credit_control.py` is dead (largely commented out and contains a
`debugpy.listen()+wait_for_client()` that would hang requests). A third variant
`validate_sales_invoice` inside `salesinvoice_taxes.py:412` is also unwired.
Note the field mismatch between variants (`custom_days/amount` vs
`custom_days_limit/amount_limit` on Customer). **To re-enable credit control,
pick one implementation, reconcile field names, and wire it explicitly.**

---

## 7. Vehicle-mandatory validation (`custom_code/vehicle_mandatory.py`)

Vehicle expense lines must carry a Vehicle (`custom_subtype`). Account matched
by name patterns `("Fuel Expenses", "R & M - Vehicles", "Other Vehicle
Expenses")`. Wired on JE `validate` (rows in `accounts` by `account`) and PI
`validate` (rows in `items` by `expense_account`); throws per offending row,
with a hint when the Account's `custom_sub_type_list` has no vehicles
configured. That per-account vehicle whitelist is the **Vehicle List** child
doctype (DB-only — [chapter 11 Part C](11-custom-fields-and-doctypes.md#sub-ledger--vehicle-mapping)),
attached to Account as `custom_sub_type_list`. Client mirror
`vehicle_mandatory.js` (per-row on purpose — avoids
Frappe's shared-docfield mandatory-propagation bug). Property-setter approach
was tried and removed (patch run twice) because `mandatory_depends_on` isn't
server-enforced.

---

## 8. Stock Adjustment (doctype `stock_adjustment` + child items)

Submittable, quantity-only stock correction (System/Stock Manager).
`validate`: ≥1 item, `adjustment_qty > 0`, **`rate` must be 0** (value
movements must use Stock Entry), warehouse must belong to the company.
`on_submit`/`on_cancel` post SLEs (sign +1 Gain / −1 Loss, `incoming_rate=0`,
`is_adjustment_entry=1`) and repost future SLE/GLE.

**`engine_patch.py`** (applied at module import) monkey-patches
`update_entries_after.process_sle` so zero-rate Stock Adjustment SLEs
**preserve the warehouse's stock value** (qty changes,
`stock_value_difference=0`, valuation rate re-derived) — and this survives
reposts triggered by later backdated vouchers. Background:
`docs/stock_ledger_guide.md` and `docs/sales_stock_ledger_fixes.md`.

Diagnostics: `custom_code/stock_health_check.py` (`bench --site avinas1
execute avinashgroup_app.custom_code.stock_health_check.run`) — negative-stock
flag, negative SLE balances, zero-valuation sales SLEs, repost job status,
backdated update-stock PIs.

---

## 9. Portal & supplier flows (server side)

`templates/pages/rfq.py` overrides ERPNext's `create_supplier_quotation`
(supplier portal): copies document-level discounts, seeds per-line VAT custom
fields, runs `calculate_taxes_and_totals`, saves with `ignore_permissions`,
re-links uploaded Files. `upload_portal_item_attachment` (whitelisted) stores
base64 portal uploads as private Files. (Customer portal pages: chapter 8 §5.)

---

## 10. Master-form helpers (client-only)

- `party_duplicate_check.js` (Customer/Supplier): same-company duplicate
  name/tax_id → non-blocking Yes/No confirm.
- `party_default_account.js` / `item_default_account.js`: auto-add one default
  accounts/item-defaults row with Company from `custom_company`, kept in sync.
- See `docs/customer supplier item duplicate checks and default accounts.md`.

---

## 11. Legacy / dead code inventory (do not build on)

| File | Status |
|------|--------|
| `custom_code/override_rounding.py` (71 KB) | unwired; 57% commented; excise-inclusive recompute superseded by the live handlers |
| `custom_code/purchase_invoice/purchase_invoice_taxes_tds.py` | superseded alternate PI handler (Percentage-based VAT) — not wired |
| `SalesInvoice/credit_control.py` | dead + debugpy trap |
| `public/js/si.js`, `purchase_invoice.js` | not loaded by hooks |
| `custom_code/api.py` naming/fiscal helpers | superseded by naming_series.py (the created_by installer/backfill parts are still useful console tools) |
| `custom_itemname.py` (`CustomItem`) | never registered |
| `custom_customer.py` | misnamed; only locks company on two *test* doctypes |
| `excise_ledger.py` everything except `modify_gl_entries` | dead, hardcoded GLMI accounts |
| `purchase_taxes_mapper.after_mapping_*` | unreferenced |
| `workflow_material_request.py` | thin legacy alias of `workflow.set_reject_reason` |

Console-only utilities (live but manual): `setup_company_lock.py` /
`company_field_lock.py` setup functions (the `validate_company_field_lock`
runtime guard **is** wired via the audit map), `update_workflows.run()`,
`create_log_doctype.py`, `voucher_no_console.py`, `stock_health_check.py`,
`api.create_created_by_and_created_on_fields` / `populate_...`.
