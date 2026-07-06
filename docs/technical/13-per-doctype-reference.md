# Per-Doctype Reference — What the App Does to Every Doctype

> Chapter 13 of the technical documentation. This is the **by-doctype** view:
> for each doctype, exactly what `avinashgroup_app` adds or overrides — fields,
> server hooks, client scripts, class overrides, reports — and why. It
> complements the by-feature chapters (2–8), which explain the mechanisms;
> here you look up a doctype and see everything done to it. Field lists are the
> live avinas1 definitions (authoritative — includes patch-added fields).
>
> Notation: **Fields** = app custom fields (the audit block is noted once
> below, not repeated). **Hooks** = server `doc_events`. **Class** =
> `override_doctype_class`. **JS** = client scripts. **→** points to the deep
> chapter.

## 0. Cross-cutting — applied to (almost) every doctype

Before the per-doctype list, three things the app does **universally**, so
individual entries below don't repeat them:

1. **Audit block** (chapter 6 §3). ~250 doctypes carry
   `custom_created_by` + `custom_created_on` + `custom_modified_by` (RO,
   stamped on save). Masters also get `custom_naming_series`; doctypes without
   a native company field also get `custom_company`. The ~85 doctypes in
   `AuditBase.doctypes` additionally run the audit `doc_events`
   (before_insert/before_save/validate/autoname/after_delete) which also do
   **company-matching validation** (chapter 6 §2) and **custom voucher
   numbering** (chapter 4 §4).
2. **Dynamic Approval** (chapter 2). Registered on `*` — `validate`,
   `before_save`, `on_update`, `before_workflow_action` fire on **every**
   doctype, but short-circuit instantly unless the doctype has the injected
   `custom_current_approver` field (i.e. was set up for approval).
3. **Fiscal-year access** (chapter 6 §1). The 77 transaction doctypes in
   `FILTERED_DOCTYPES` get `permission_query_conditions` + `has_permission`
   (list/read filtering by the user's allowed fiscal years).

Doctypes whose **only** customization is the audit block (≈250 of the 379) are
not listed individually — e.g. most CRM/HR/manufacturing/quality masters. The
entries below are the doctypes with app-specific fields, hooks, JS, overrides,
or reports.

---

## 1. Selling transactions

### Sales Invoice — the most heavily customized doctype

- **Fields (23):** `custom_vat`/`custom_excise` + `custom_total_vat_amount`/
  `custom_total_excise_amount`/`custom_total_amount_including_excise`/
  `custom_total_excluding_excise`/`custom_total_amount` (VAT+excise scheme);
  `custom_difference_adjustment` + `custom_difference_calculation_table`
  (→ Amount Calculation for sales invoice) (rounding recon, dormant);
  `custom_abbr`/`custom_company_abbr`/`custom_fiscal_year`/`custom_invoice_miti`
  (numbering + Nepali date); `custom_created_on_ad`/`custom_created_on_bs`;
  `custom_vehicle_no`; `custom_citytown`; `custom_narration`;
  **`custom_reason_for_return`** (CBMS, patch); **`custom_print_count`** (IRD
  copies, patch); audit block.
- **Class:** `CustomSalesInvoice` — restores warehouse from DN/SO item, softens
  warehouse-mandatory (chapter 4 §2).
- **Hooks:** `before_validate`/`before_save`/`validate` → selling taxes
  (`salesinvoice_taxes.py`); `on_submit` + `before_cancel` → **CBMS** sync
  (chapter 5); `before_print` → **IRD print-copy** counter (chapter 4 §5a);
  audit + dynamic-approval + fiscal-year.
- **JS:** `sales_invoice.js` (VAT UI, selling-warehouse injection, due date from
  Customer `custom_days_limit`); `si.js` **not loaded** (dormant credit
  control).
- **Reports:** Sales Register, One Lakh Above, all 3 Sales Analysis, Party
  Ledger (via GL), Sales Stock Ledger. Portal: `/customer_statement`,
  `/product_wise_invoice_details`.
- → chapters 4, 5, 8, 12.

### Sales Invoice Item

- **Fields (7):** `custom_vat_apply_on` (VAT 13%/0%/Amount), `custom_vat_rate`,
  `custom_vat_amount`, `custom_vat` (Float), `custom_excise_duty`,
  `custom_excise_value`, `custom_total`. → the VAT/excise line scheme
  (chapter 4 §1).

### Quotation / Sales Order / Delivery Note

- **Fields:** parent totals `custom_total_amount(_including_excise)` /
  `custom_total_excise_amount` / `custom_total_vat_amount` / `custom_excise`;
  DN adds `custom_abbr`; audit block. Item children (Quotation/SO/DN Item, 7
  each): the same VAT/excise line set as Sales Invoice Item.
- **Class:** `SalesOrder` (restore from Quotation Item), `DeliveryNote` (from SO
  Item) — warehouse restore + soften mandatory (chapter 4 §2).
- **Hooks:** `before_validate`/`before_save` → selling taxes handler;
  `validate` → `salesinvoice_taxes.validate_quotation/_sales_order/
  _delivery_note` (warehouse forcing). DN returns force negative signs.
- **JS:** `selling_taxes_common.js` (VAT UI), `sales_warehouse_common.js`
  (warehouse injection).
- → chapter 4 §1–3.

---

## 2. Buying transactions

### Purchase Invoice — second most customized

- **Fields (28):** VAT+excise+**TDS** totals (`custom_total_vat_amount`/
  `_excise_amount`/`_tds_amount`/`_amount_including_excise`);
  `custom_tax_withholding_category_custom` (the custom TDS category);
  numbering `custom_purchase_type` (→ Purchase Type) / `custom_p_type_code` /
  `custom_document_no` / `custom_name` / `custom_abbr` / `custom_fiscal_year`;
  Nepali dates `custom_nepali_miti` / `custom_supplier_invoice_miti`;
  petroleum `custom_pdo_no` / `custom_refinery` / `custom_ioc_challan_no/date` /
  `custom_ico_challan_miti` / `custom_store_receipt_no/date/miti` /
  `custom_voucher_receipt_no` / `custom_name_of_transportor` /
  `custom_vehicle_no`; `custom_memo`; audit block.
- **Class:** `PurchaseInvoice` — restore warehouse from PR/PO item.
- **Hooks:** `before_validate`/`before_save`/`validate` → purchase taxes
  (`purchase_taxes_handler.py`); `validate` → **vehicle-mandatory**;
  `before_submit` → **excise_ledger** (party-tag TDS-payable GL);
  `on_submit` → **stock_revaluation** (backdated notice); audit + approval +
  fiscal-year.
- **JS:** `pi.js` (vehicle picker for `custom_subtype`); `purchase_taxes_common.js`
  (global, VAT/TDS UI + buying-warehouse injection).
- **Reports:** Purchase Register, Advance Tax TDS, Gas Purchase, One Lakh Above,
  Vehicle Expense (JE+PI), Party Ledger.
- → chapters 4, 8, 12.

### Purchase Invoice Item

- **Fields (9):** VAT trio + TDS trio (`custom_tds_apply_on` Percentage/Amount,
  `custom_tds_rate`, `custom_tds_amount`) + `custom_excise_value` +
  `custom_total` + **`custom_subtype` (→ Vehicle)** — the only item table with
  the vehicle link.

### Purchase Order

- **Fields (14):** VAT/excise/TDS totals; **approval** `custom_approver` (PO
  Reviewer), `custom_po_request_approver` (→ Purchase Order Request Approver),
  `custom_reason`, `custom_remarks`, `workflow_state`; `custom_miti`,
  `custom_abbr`; audit block.
- **Class:** `PurchaseOrder` — restore from Supplier Quotation Item + Administrator
  workflow bypass on "Purchase Order Workflow".
- **Hooks:** `before_save` + `validate` → purchase taxes handler.
- **JS:** `purchase_taxes_common.js`.

### Purchase Receipt

- **Fields (24):** VAT/excise/TDS totals; numbering `custom_receipt_type`
  (→ Receipt type) / `custom_p_type_code` / `custom_document_no` /
  `custom_name` / `custom_abbr`; `custom_posting_miti`; the same petroleum/
  IOC/store-receipt/transporter/vehicle fields as PI; `custom_remark`; audit.
- **Class:** `PurchaseReceipt` — restore from PO Item.
- **Hooks:** `before_save` + `validate` → purchase taxes handler.

### Supplier Quotation

- **Fields (10):** `custom_preferred_quotation` (Check — drives the comparison
  report), `custom_miti`/`custom_valid_miti`, VAT/excise/TDS totals, audit.
- **Class:** `SupplierQuotation` — restore from RFQ Item.
- **Hooks:** `before_save` + `validate` → purchase taxes handler.
- **Reports:** Custom Supplier Quotation Comparison. Portal: `/rfq/<name>`.

### Purchase Order Item / Purchase Receipt Item / Supplier Quotation Item

- **Fields (8 each):** VAT trio + TDS trio + `custom_excise_value` +
  `custom_total`.

### Material Request

- **Fields (7):** `custom_transaction_miti`, `custom_required_miti`,
  `custom_fiscal_year`, `custom_abbr`, audit.
- **Class:** `MaterialRequest` — Administrator workflow bypass on "Material
  Request One-Line Approver" + soften warehouse-mandatory.
- **Hooks:** `validate` → purchase taxes handler (warehouse defaults).
- **JS:** `material_request.js` (branch warehouse + approval reject dialog).

### Request for Quotation

- **Fields (5):** `custom_miti`, `custom_required_miti`, audit.
- **Class:** `RequestforQuotation` — restore from MR Item + soften mandatory.
- **Hooks:** `validate` → purchase taxes handler. Whitelisted
  `create_supplier_quotation` overridden by the RFQ portal (chapter 4 §9).

---

## 3. Accounting

### Payment Entry

- **Fields (13):** numbering `custom_p_type` (→ Payment - Receipt Type) /
  `custom_p_type_code` / `custom_document_no` / `custom_document_word` /
  `custom_name` / `custom_abbr` / `custom_fiscal_year`; `custom_posting_miti` /
  `custom_chequereference_miti`; `custom_remark`; audit.
- **Hooks:** audit (numbering) + approval + fiscal-year. **No** class override.
- **JS:** `payment_entry.js` — **Cheque Bounce** button (posts reversing GL,
  chapter 4 §5) + `auto_update_document_no.js` (auto document number) + party
  scoping.
- **Reports:** Receipt Register, Party Ledger.

### Journal Entry

- **Fields (12):** numbering `custom_p_type` (→ JV Type) / `custom_p_type_code`
  / `custom_document_no` / `custom_document_word` / `custom_name` /
  `custom_abbr` / `custom_fiscal_year`; `custom_posting_miti` /
  `custom_reference_miti`; audit.
- **Hooks:** `validate` → **vehicle-mandatory** (accounts rows); audit
  (numbering) + approval + fiscal-year.
- **JS:** `journal_entry.js` (vehicle picker for `accounts.custom_subtype`) +
  `auto_update_document_no.js`.
- **Reports:** Vehicle Expense (JE lines), Party Ledger (JE split per account),
  Loan Summary / Net Position / financial statements (via GL).

### GL Entry / Journal Entry Account

- GL Entry: audit block only, plus it's the source for most financial reports;
  patch `add_gl_entry_fin_stmt_agg_index` adds the consolidated-report index.
  `excise_ledger.modify_gl_entries` party-tags TDS-payable lines at PI submit.

### Bank Account / Cost Center / Tax Withholding Category / Warehouse / Fiscal Year / Account

- **Account (5 fields):** `custom_sub_type_list` (→ **Vehicle List** — the
  per-account vehicle whitelist the vehicle pickers read), `custom_department`,
  audit. → chapters 4 §7, 11 Part C.
- The rest: audit block only (Cost Center, Tax Withholding Category, Warehouse,
  Fiscal Year, Bank Account + naming series).

---

## 4. HR / Payroll / Attendance

### Attendance

- **Fields (8):** `custom_worked_on_holiday` (Check),
  `custom_late_entry`/`custom_early_entry`/`custom_early_exit`/`custom_late_exit`
  (Duration — shift deviations), audit.
- **Hooks (all `validate`):** `set_holiday_flag` (payroll),
  `set_shift_deviation_fields`, `enforce_late_arrival_half_day` (biometric).
  Uses `validate` not `before_save` because device attendance inserts
  already-submitted (chapter 3 §3).
- **JS:** `attendance.js` — read-only Checkin Log table.
- **Reports:** Monthly Attendance BS, Monthly Attendance Summary BS, Work On
  Holiday BS. → chapter 3.

### Employee Checkin

- **Fields (3):** `custom_company` (fetch from employee), audit.
- **Hooks:** `after_insert` → `reconcile_with_existing_attendance` (chapter 3).
- Patch `add_company_to_employee_checkin`; `company_scoped_attendance_device_id`.

### Employee — heavily extended (28 fields)

- **App fields:** `custom_document_user` (signatory User for Document
  Generator), `custom_signature_image`, `custom_ot_eligibility` (attendance
  allowances), `custom_attendance_allowances` (→ Employee Attendance
  Allowance), `custom_employee_cost_center_manager` (→ Employee Cost Center
  Manager), `custom_pan`, `custom_ssf_id_no`, `custom_citizenship_number`,
  `custom_districtplace_of_issue`, `custom_date_of_citizenship_issue`,
  `custom_abbr`, audit.
- **Hooks:** `validate` → `validate_unique_device_id` (device id unique per
  company).
- *(Note: many other Employee custom fields — grade, default_shift,
  leave_approver, employment_type, health_insurance_*, ifsc/micr, pan_number,
  payroll_cost_center — are **HRMS-provided**, not this app's.)*
- → chapters 3, 7.

### Payroll Entry

- **Fields (3):** audit only.
- **JS:** `payroll_entry.js` — **Calculate Attendance Allowances** button
  (chapter 3 §6).

### Salary Component (10 fields)

- **App fields:** `custom_is_attendance_driven`, `custom_condition_type`,
  `custom_threshold_hours`, `custom_time_offset_hours`, `custom_unit`,
  `custom_default_rate`, `custom_summary_group`, `component_type`, audit —
  the attendance-allowance rule definition (chapter 3 §6).

### Additional Salary

- **Fields (3):** `custom_source` (tags allowance drafts as "Nepal HRMS
  Attendance Allowance"), audit.

### Shift Type

- **Fields (4):** `custom_company` (patch), `custom_late_arrival_cutoff_time`
  (drives the auto Half-Day rule), audit. Shift Types are per-company.

### Salary Slip / Leave Application / Leave Allocation / Expense Claim / Department

- **Salary Slip:** audit only. **Report:** Avinas Salary Statement.
- **Leave Application:** audit; patch `leave_application_dynamic_approval` brings
  it under Dynamic Approval (native leave_approver fields hidden). **Report:**
  Yearly Leave Details BS.
- **Leave Allocation:** audit. **Report:** Yearly Leave Details BS (allocations).
- **Department (7):** HRMS approver tables + `payroll_cost_center` (mostly
  HRMS-provided) + audit.

---

## 5. Stock

### Stock Adjustment (custom doctype — chapter 9/11)

Quantity-only correction; `engine_patch.py` preserves stock value through
reposts. Not to be confused with core Stock Entry.

### Stock Entry / Stock Reconciliation / Batch / Serial No / Landed Cost Voucher

- **Stock Entry (3):** audit only.
- **Stock Reconciliation (5):** `custom_abbr`, `custom_posting_miti`, audit.
- **Batch (5):** company + naming series + audit.
- **Landed Cost Voucher (4):** `custom_remarks` + audit.
- **Reports:** Sales Stock Ledger (via Sales Invoice + SLE).

---

## 6. Masters

### Customer (8 fields)

- **Fields:** `custom_company`, `custom_abbr`, **credit control**
  `custom_amount_limit` / `custom_bill_count` / `custom_days_limit`, audit.
- **JS (doctype_js):** `party_duplicate_check.js` (same-company duplicate
  name/tax_id warning), `party_default_account.js` (default accounts row).
- **Hooks:** audit + company-matching. Company scoping via Company Filter.
- → chapter 4 §10.

### Supplier (7 fields)

- **Fields:** `custom_company`, `custom_abbr`, `custom_territory`,
  **`custom_payment_term_days`** (auto PI due date), audit.
- **JS:** `party_duplicate_check.js`, `party_default_account.js`.

### Item (12 fields)

- **Fields:** `custom_company`, `custom_abbr`… actually `custom_code`,
  `custom_hs_code`, `custom_item_type`, `custom_excise_duty`,
  `custom_is_depend_on_branch`, **`custom_buying_warehouse`** /
  **`custom_selling_warehouse`** / **`custom_branch_wise_warehouse`**
  (→ Branch Wise Warehouse — the per-branch warehouse map), audit.
- **JS:** `item_default_account.js` (default item-defaults row).
- **Overrides:** Item Price auto-company stamping (`auto_insert_item_price.py`);
  `get_item_details` wrapped for branch warehouse.
- → chapter 4 §3.

### Item Price (5 fields)

- **Fields:** `custom_company` (mandatory — auto-stamped),
  `custom_total_vat_inclusive`, audit. In `master_doctypes` for naming series.

### Company (10 fields — mostly HRMS/payroll)

- **App field:** `custom_document_stamp` (Attach Image — used by Document
  Generator letters). Others (payroll payable/advance/expense accounts, basic/
  hra/arrear components) are HR-payroll config. Per-company: CBMS Config,
  Company Filter, numbering abbr, `tax_id` (CBMS seller PAN).

### Address / Contact / Branch / Item Group / Customer Group / Supplier Group / Asset Category

- Company + naming series + audit (some add domain fields: Address
  `tax_category`/`is_your_company_address`; Contact `is_billing_contact`;
  Branch is used by branch-wise warehouse). Company scoping applies.

---

## 7. Custom & DB-only doctypes

The 28 file-based custom doctypes are in [chapter 9](09-doctypes-reference.md) +
[chapter 11 Part B](11-custom-fields-and-doctypes.md#part-b--custom-doctype-fields);
the 13 DB-only ones (Purchase Type, Receipt type, Payment - Receipt Type, JV
Type, Vehicle List, the approver/calc tables, Sub-Ledger Category…) in
[chapter 11 Part C](11-custom-fields-and-doctypes.md#part-c--db-only-custom-doctypes-in-the-module-not-in-the-repo).

---

## 8. Everything else (audit block only)

The remaining ~250 doctypes with custom fields carry **only** the audit block
(`custom_created_by`/`custom_created_on` + often `custom_modified_by`, plus
`custom_company`/`custom_naming_series` where applicable) and, if audited, the
audit `doc_events`. No other app behavior. This covers most CRM (Lead,
Opportunity, Prospect, Campaign…), HR (the many Employee-* and Leave-* masters,
Interview, Appraisal…), manufacturing (BOM, Work Order, Job Card, Operation,
Routing, Workstation…), quality, projects, and setup doctypes. They inherit the
cross-cutting behavior in §0 but have no dedicated fields, hooks, JS, or
reports of their own.
