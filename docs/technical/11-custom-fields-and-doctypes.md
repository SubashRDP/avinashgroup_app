# Field Reference — Custom Fields & Doctype Fields

> Chapter 11 of the technical documentation. The exhaustive field-level
> reference: **Part A** every custom field added to core ERPNext doctypes
> (`custom/*.json`), **Part B** every field of the 28 custom doctypes.
> Layout-only Section/Column Breaks are summarized as counts (they carry no
> data); every data field is listed. `RO` = read-only, `NC` = no_copy, "miti" =
> Nepali Bikram Sambat date.

The cross-cutting field families (why they exist) are:

- **Audit block** — `audit_section`, `custom_created_by`, `custom_created_on`,
  `custom_modified_by` (all RO/NC, system-stamped by the audit engine,
  chapter 6 §3). Present on Customer, Sales Invoice, Purchase Invoice/Order/
  Receipt, Supplier Quotation.
- **VAT scheme** — item rows: `custom_vat_apply_on` (VAT 13% / VAT 0% /
  Amount), `custom_vat_rate` (RO), `custom_vat_amount`; parents:
  `custom_total_vat_amount` (chapter 4 §1).
- **Excise scheme** — item rows: `custom_excise_value`, `custom_total`;
  parents: `custom_total_excise_amount`, `custom_total_amount_including_excise`.
- **TDS scheme** (purchase side only) — `custom_tds_apply_on` / `custom_tds_rate`
  / `custom_tds_amount`; parents `custom_total_tds_amount`;
  `custom_tax_withholding_category_custom` on PI.
- **Voucher numbering** — `custom_abbr`/`custom_company_abbr`,
  `custom_document_no`, `custom_name` (Voucher No.), `custom_p_type_code`
  (chapter 4 §4).
- **Nepali/IRD** — `custom_fiscal_year`, the `*_miti` BS-date fields, AD/BS
  pairs, `custom_print_count` (SI, added by patch — chapter 4 §5a).
- **Petroleum/IOC** — `custom_pdo_no`, `custom_refinery`,
  `custom_ioc_challan_no/date/miti`, `custom_name_of_transportor`,
  `custom_vehicle_no`, item `custom_subtype` (→ Vehicle).
- **Credit control** (Customer) — `custom_amount_limit`, `custom_days_limit`,
  `custom_bill_count`.

Total: **182 custom fields** across 11 core doctypes (+2 doctypes carry only
property setters). Note `custom_print_count` is added by patch, not exported
here, so it isn't in the counts below.

---

# Part A — Custom fields on core doctypes

## Customer (11 fields, 4 property setters)

| Field | Type | Flags | Why |
|-------|------|-------|-----|
| `custom_company` | Link → Company | reqd | ties customer to a group company; drives abbr + filtering |
| `custom_abbr` | Data | hidden, fetch company.abbr | company abbreviation for naming/print |
| `custom_amount_limit` | Float | — | credit control: max outstanding |
| `custom_bill_count` | Int | — | credit control: max open unpaid bills |
| `custom_days_limit` | Int | — | credit control: max credit age (days) |
| audit block (4) | — | RO/NC | created/modified tracking |
| 2 layout breaks | Section/Column Break | structural | credit-limit + taxation layout |

## Sales Invoice (28 fields)

| Field | Type | Flags | Why |
|-------|------|-------|-----|
| `custom_abbr` | Data | reqd, RO, fetch company.abbr | voucher numbering / print |
| `custom_company_abbr` | Data | hidden, in_list_view | list view / naming |
| `custom_fiscal_year` | Data | allow_on_submit | Nepali FY label |
| `custom_invoice_miti` | Data | allow_on_submit | BS posting date (IRD) |
| `custom_created_on_ad` / `custom_created_on_bs` | Date / Data | — | AD + BS creation date pair |
| `custom_citytown` | Data | fetch customer_address.city | prints city/town on IRD invoice |
| `custom_vehicle_no` | Data | — | delivery vehicle number |
| `custom_excise` | Currency | hidden | working excise value |
| `custom_vat` | Currency | hidden | working VAT value |
| `custom_total_amount_including_excise` | Currency | — | excise scheme total |
| `custom_total_excise_amount` | Currency | — | rolled-up excise |
| `custom_total_excluding_excise` (label "Total") | Currency | hidden | working base excl. excise |
| `custom_total_vat_amount` | Currency | — | rolled-up VAT |
| `custom_difference_adjustment` | Currency (p3) | hidden | rounding tweak |
| `custom_difference_calculation_table` | Table → Amount Calculation for sales invoice | hidden | VAT/excise/difference calc rows |
| audit block (4) + 8 layout breaks | — | — | tracking + layout |
| *(`custom_print_count`)* | Int | RO/NC (added by patch) | IRD print-copy counter (chapter 4 §5a) |

## Sales Invoice Item (6 fields)

`custom_vat_apply_on` (Select VAT 13%/VAT 0%/Amount, JSON default VAT 0%),
`custom_vat_rate` (Percent, RO unless not-Amount), `custom_vat_amount`
(Currency p5, editable only in Amount mode), `custom_excise_value` (Currency,
NC), `custom_total` (Currency, NC = line incl. excise), + 1 section break.

## Purchase Invoice (40 fields — the largest bundle)

| Field | Type | Flags | Why |
|-------|------|-------|-----|
| `custom_document_no` | Int | reqd (except Grihalaxmi) | sequential document number |
| `custom_name` | Data | in_list_view | Voucher No. |
| `custom_purchase_type` | Link → Purchase Type | reqd (except Grihalaxmi), default "Purchase Other Service/Goods" | classifies purchase; drives P Type Code |
| `custom_p_type_code` | Data | RO, fetch purchase_type.purchase_type_code | voucher coding |
| `custom_fiscal_year` | Data | RO | Nepali FY |
| `custom_abbr` | Data | hidden, fetch company.abbr | numbering |
| `custom_tax_withholding_category_custom` | Link → Tax Withholding Category | — | the custom TDS category (keeps ERPNext TDS out) |
| `custom_total_amount_including_excise` / `custom_total_excise_amount` / `custom_total_vat_amount` / `custom_total_tds_amount` | Currency | NC | rolled-up excise/VAT/TDS |
| `custom_refinery` | Select (Barauni/Haldia/Paradip/Mathura/Durgapur/Karnal) | list/filter/search | petroleum source refinery |
| `custom_pdo_no` | Data | list/filter/search | Petroleum Delivery Order no |
| `custom_ioc_challan_no` / `_date` / `custom_ico_challan_miti` | Data/Date/Data | — | IOC challan (no / AD / BS) |
| `custom_store_receipt_no` / `_date` / `_miti` | Data/Date/Data | — | store receipt (GRN) refs |
| `custom_supplier_invoice_miti` | Data | — | supplier invoice BS date |
| `custom_nepali_miti` | Data | — | BS posting date |
| `custom_name_of_transportor` | Select (3 transporters) | — | freight transporter |
| `custom_vehicle_no` | Data | — | goods-receipt vehicle |
| `custom_voucher_receipt_no` | Data | hidden | internal receipt ref |
| `custom_memo` | Small Text | — | free-text note |
| audit block (4) + ~10 layout breaks | — | — | tracking + layout |

## Purchase Invoice Item (11 fields)

VAT trio (`custom_vat_apply_on`/`rate`/`amount`), TDS trio
(`custom_tds_apply_on` Percentage(%)/Amount, `custom_tds_rate` RO,
`custom_tds_amount`), `custom_excise_value`, `custom_total`, **`custom_subtype`
(Link → Vehicle** — the only place custom_subtype exists on an item table;
drives fleet/vehicle-expense tracking), + 2 layout breaks.

## Purchase Order (15 fields)

Approval fields: `custom_approver` (Link User "PO Reviewer", reqd),
`custom_po_request_approver` (Table → Purchase Order Request Approver),
`custom_reason` (Small Text, RO), `custom_remarks` (Small Text),
`workflow_state` (Link → Workflow State, hidden/NC). Plus the four excise/VAT/
TDS parent totals, audit block, `custom_abbr`, 1 layout break.

## Purchase Order Item (10) / Purchase Receipt Item (10) / Supplier Quotation Item (10)

Identical VAT + TDS + excise item field sets as PI Item (minus
`custom_subtype`), plus layout breaks.

## Purchase Receipt (32 fields)

`custom_document_no` (Data, reqd), `custom_name` (Voucher No),
`custom_receipt_type` (Link → Receipt type, reqd), `custom_p_type_code`
(fetch receipt_type.receipt_code, hidden), `custom_posting_miti`, the same
IOC/store-receipt/refinery/transporter/vehicle petroleum fields as PI,
`custom_remark`, the four excise/VAT/TDS totals, audit block, `custom_abbr`,
layout breaks.

## Supplier Quotation (9 fields)

`custom_preferred_quotation` (Check — marks the chosen quote in the comparison
report), the four excise/VAT/TDS parent totals, audit block.

## Packed Item / Purchase Taxes and Charges (0 custom fields)

Property setters only: Packed Item makes `rate` read-only; Purchase Taxes and
Charges defaults `add_deduct_tax` to **Deduct**.

## ⚠️ Two field defects worth fixing

- `purchase_receipt_item.json`: `custom_excise_value` and `custom_total` have
  `depends_on` pointing at `custom_tds_apply_on=='Amount'` (copy-paste
  artifact — they should always show).
- `supplier_quotation_item.json`: `custom_tds_rate` `depends_on` references
  `custom_vat_apply_on` instead of `custom_tds_apply_on`.

---

# Part B — Custom doctype fields

28 doctypes: 2 submittable (Attendance Fix, Stock Adjustment), 1 single (User
Daily Entry Summary Settings), 15 child/istable, the rest standard. All carry
`track_changes: 1`. Structural Section/Column Breaks omitted; data fields
listed in full.

## Attendance Fix — submittable, `AF-.YYYY.-`

`shift_type` (Link Shift Type, reqd — scopes to this shift's employees),
`company` (Link, optional filter), `from_date`/`to_date` (Date, reqd),
`employee` (Link, optional single), `devices` (Table MultiSelect → Attendance
Fix Device — limit to these devices' checkins), `status` (Pending/Queued/
Running/Fixed/Failed, RO), `progress_percentage`/`progress_message` (RO,
realtime), counters `employees_processed` / `absent_rows_deleted` /
`attendance_created_or_updated` / `checkins_relinked` (RO), `log` (Long Text,
RO), `amended_from`.
**Perms:** HR Manager + System Manager full (submit/cancel/amend); HR User read.
**Controller:** `validate` (date order); `on_submit` (Queued + enqueue
`run_attendance_fix_in_background` on `long` queue, 14400 s); `_run_fix`
(per-employee×day reconciliation, savepoints, realtime progress);
`_resolve_employees`, `_reconcile_day`, `_prepare_checkins_for_shift`,
`_cancel_and_delete`; worker runs as Administrator crediting
`audit_user=owner`.

## Attendance Fix Device — child

`device` (Link Biometric Device, reqd).

## Biometric Device — `field:device_name`, title device_name

`device_name` (Data, reqd/unique), `device_serial` (Data, reqd/unique — matched
against bridge SN), `company` (Link, reqd), `device_ip` (informational),
`device_port` (Int, 4370), `enabled` (Check, 1 — off ⇒ punches rejected),
`device_model`, `connection_status` (Connected/Disconnected). Sync (RO):
`last_contact_time` (heartbeat basis), `last_sync_time`, `total_synced`,
`last_employee_sync`, `total_employees_synced`. Settings:
`clear_logs_after_sync` (1), `sync_interval` (30 min), `timeout` (5 s).
Alerting: `alert_threshold_minutes` (120), `alert_recipients` (Table).
`notes`.
**Perms:** HR Manager + System Manager full; HR User read.
**JS:** "Force Bridge Sync" button → `enqueue_command(force_sync)` then polls the
command row every 3 s up to 90 s.

## Biometric Device Alert Recipient — child

`email` (Data/Email, reqd), `recipient_name`.

## Biometric Device Command — `BDC-.#####`

`device` (Link, reqd), `command_type` (force_sync/test_connection, reqd),
`status` (Pending/Running/Done/Failed, RO), `requested_by`/`requested_at`
(RO), `started_at`/`completed_at` (RO), `attempts` ("Bridge Poll Count", RO),
`payload` (Long Text JSON), `result` (Long Text, RO).
**Perms:** HR Manager + System Manager; HR User read.
**Controller:** `before_insert` (stamp requester/time/status); `validate` (enum).

## Branch Wise Warehouse — child, **effectively empty**

Only a Section Break in the exported JSON — the operative fields
(`custom_branch`, `custom_buying_warehouse`, `custom_selling_warehouse`) live
as site-DB custom fields (chapter 4 §3).

## CBMS Bill — title invoice_number

**All fields RO** (system-written). `company`, `sales_invoice` (unique),
`invoice_number`, `invoice_date` (AD), `invoice_date_bs` (BS), `fiscal_year`,
`buyer_name`/`buyer_pan`/`seller_pan`, `total_sales`, `taxable_sales_vat`,
`vat`, `discount` (local only), `excisable_amount`/`excise`/`taxable_sales_hst`/
`hst` (Health Service Tax)/`amount_for_esf`/`esf` (Education Service Fee)/
`export_sales`/`tax_exempted_sales` (all default 0), `sync_status`
(Pending/Synced/Failed), `attempt_count`, `last_attempt`, `sync_response`,
`datetime_client`.
**Perms:** System Manager full; Accounts Manager read/report/print/email.

## CBMS Bill Return — title credit_note_number

Same amounts/sync structure as CBMS Bill, plus `ref_invoice_number` (the
original's running number — must be Synced first), `credit_note_number`,
`credit_note_date`/`_bs`, `reason_for_return` (default "Goods Returned"). All
RO. Same perms.

## CBMS Config — `field:company`

`company` (unique), `enable_cbms` (Check 0), `enable_from_date` (mandatory when
enabled — go-live cutoff), `username` (Data, reqd), `password` (Password,
reqd), `bill_retry_batch_size`/`return_retry_batch_size` (Int 50).
**Perms:** System Manager + Accounts Manager full.
**Controller:** `validate` (one config per company); whitelisted
`sync_failed_now`.

## Company Filter Config — `field:doctype_name`

`doctype_name` (Link, unique), `company_field` (Select company/custom_company),
`fields` (Table → Company Filter Field). **Perms:** System Manager only.
**Controller:** `on_update`/`on_trash` clear the config cache + ask to refresh.

## Company Filter Field — child

`fieldname` (reqd), `is_child_table` (Check) + `child_fieldname`,
`is_dynamic_link` (Check) + `dynamic_link_field`.

## Document Template — `field:template_name`, title template_name

`template_name` (unique), `target_doctype` (optional — email recipient),
`companies` (MultiSelect), `letter_head`, `print_orientation`,
`default_recipient_field` (email_id), `is_active`, `email_subject` (Jinja),
`inputs` / `data_sources` (Tables), `header_html`+`header_height` (25 mm),
`footer_html`+`footer_height` (15 mm), `body_html`, help HTML blocks.
**Perms:** System Manager + Document Template Manager full; Document Template
User read/print/report.
**Controller:** `validate` → dedup companies + dry-render Jinja.
**JS:** "Preview" (stub data).

## Document Template Company / Data Source / Input — children

- **Company:** `company` (Link, reqd).
- **Data Source:** `source_name` (→ `data.<name>`), `source_type` (SQL/Python),
  `description`, `query` (Code).
- **Input:** `fieldname`, `label`, `input_type` (Data/Link/Date/Select/Int/
  Float/Check), `options`, `reqd`, `exclusive_group`, `exclusive_set`.

## Dynamic Approval Approver — child (injected on targets)

`level` (Int, reqd), `approver` (Link User, reqd), `approver_name` (fetch).

## Dynamic Approval Fixed Approver — child

`section` (reqd), `approver` (Link User, reqd), `approver_name` (fetch).

## Dynamic Approval Match Criteria — child

`section` (reqd), `field_name` (Autocomplete, reqd), `field_value`
(Autocomplete, reqd).

## Dynamic Approval Setting — `autoname()` → `{doctype}-{abbr}-{hash6}`

`document_type` (Link, reqd), `company` (Link, reqd), `company_abbr` (fetch),
`is_active` (1), `approver_table_fieldname` (default
`custom_approval_approvers`), `current_level_fieldname` (default
`custom_current_approval_level`), `approver_fieldname` (⚠️ dead — unused),
`dept_config_html` (rules UI canvas), `match_criteria` / `approvers` (hidden
Tables), `setup_workflow_html`.
**Perms:** System Manager only.
**Controller:** `autoname`; `validate` (criteria rows complete).
**JS:** ~15 KB rules-card UI + Setup Workflow button.

## Employee Attendance Allowance — child (on Employee)

`salary_component` (Link, reqd), `eligible` (Check 1), `rate` (Currency —
override), `effective_from` (Date).

## Fiscal Year Access Control — `field:user`

`user` (Link, unique), `full_access` (Check 0), `access_details` (Table → User
Fiscal Year Access, shown when not full_access). **Perms:** System Manager only.
**Controller:** `on_update`/`on_trash` clear cache key `user_fiscal_access_{user}`
(⚠️ resolver uses a different key — chapter 6 §1.4).

## Generated Document — `DOC-GEN-.YYYY.-.#####`, title title

`title` (reqd), `template` (Link, reqd), `company`, `target_doctype`/
`reference_name`/`party` (RO), `status` (Draft/Finalized/Sent, RO),
`data_provider` (RO), `print_orientation` (RO snapshot), `payload` (JSON, RO),
`rendered_document` (HTML preview), `body_html` (RO — PDF/email source),
header/footer snapshot fields, `output_action`, `recipients`, `email_status`
(Not Sent/Queued/Sent/Failed), `error`.
**Perms:** System Manager + Document Template Manager full; Document Template
User CRUD `if_owner`.
**Controller:** `validate` → title default + recipients-required-when-Sent.
**JS:** "Edit in Generator" + sandboxed-iframe preview.

## Stock Adjustment — submittable, extends StockController

`posting_date` (reqd), `posting_time`, `company` (reqd), `adjustment_type`
(Loss/Gain, reqd), `reason` (reqd), `items` (Table → Stock Adjustment Item,
reqd), `created_by` (RO), `approved_by` (Link User), `amended_from`.
**Perms:** System Manager + Stock Manager full (submit/cancel).
**Controller:** `engine_patch.apply_patch()` at import (zero-rate rows survive
reposts); `validate` (≥1 item, qty>0, **rate must be 0**, warehouse company
matches); `on_submit`/`on_cancel` post & reverse SLEs (sign by Loss/Gain,
`incoming_rate=0`, `is_adjustment_entry=1`).
**JS:** item query stock-items-only, warehouse query non-group + company,
clears mismatched warehouses on company change.

## Stock Adjustment Item — child

`item_code` (Link, reqd), `item_name` (fetch), `warehouse` (Link, reqd), `uom`
(fetch stock_uom), `adjustment_qty` (Float p6, reqd), `rate` (Currency p6,
default 0 — must stay 0).

## User Daily Entry Summary Doctype — child

`document_type` (Link, reqd).

## User Daily Entry Summary Settings — Single

`description` (HTML help), `tracked_doctypes` (Table). **Perms:** System
Manager only.

## User Fiscal Year Access — child, `format:{user}.{#####}`

`doctype_name` (Link, reqd), `fiscal_year` (Link, mandatory unless row
full_access), `full_access` (Check — all fiscal years for that doctype).

## Voucher Number Settings Item — child

`doctype_name` (Link), `voucher_no_digits` (Int — zero-pad width, default 6).

---

**Controllers with real logic (10):** attendance_fix, biometric_device_command,
cbms_config, company_filter_config, document_template, dynamic_approval_setting,
fiscal_year_access_control, generated_document, stock_adjustment (+ the
`stock_adjustment/engine_patch.py`). All other controllers are `pass` stubs.
**Doctypes with JS (7):** attendance_fix, biometric_device, document_template,
dynamic_approval_setting, generated_document, stock_adjustment.

---

# Part C — DB-only custom doctypes (in the module, not in the repo)

The "Avinash Group App" module owns **41 doctypes** on avinas1. The 28 above
ship as files. The remaining **13 were created through the Customize UI**
(`custom = 1`) and live only in the site database — they have **no folder in
the repo**, so a `git clone` alone won't recreate them; they must be migrated
from the site or recreated. Several are load-bearing (they back custom fields
the code reads); a few are orphaned/legacy. This section documents all 13.

> ⚠️ Because these are DB-only, treat them as part of the data model but note
> they are **not version-controlled**. Consider exporting them as fixtures if
> they matter (Purchase Type / Receipt type / Payment - Receipt Type / JV Type
> / Vehicle List / the two approver tables and the SI calc table are the ones
> that matter).

## Code-list doctypes driving voucher numbering (chapter 4 §4)

| Doctype | Fields | Backs | Why |
|---------|--------|-------|-----|
| **Purchase Type** (`field:purchase_type`) | `purchase_type` (Data, unique), `purchase_type_code` (Data) | Purchase Invoice `custom_purchase_type` → fetches `custom_p_type_code` | classifies a purchase (gas/service/goods) and supplies the type code embedded in the voucher number; also filters the Gas Purchase & Purchase Register reports |
| **Receipt type** (`field:p_type`) | `p_type` (Data, unique), `receipt_code` (Data) | Purchase Receipt `custom_receipt_type` → `custom_p_type_code` | same idea for Purchase Receipts |
| **Payment - Receipt Type** (`field:p_type`) | `p_type` (Data, unique), `data_hrcj` ("Payment - Receipt Code"), `company` (Link) | Payment Entry `custom_p_type` | supplies the type code for Payment Entry voucher numbering |
| **JV Type** (`field:p_type`) | `p_type` (Data, unique), `jv_type_code` (Data), `company` (Link) | Journal Entry `custom_p_type` | supplies the JV type code (used by `voucher_no_console.update_journal_entry_custom_names`) |

## Approval helper tables

| Doctype | Fields | Backs | Why |
|---------|--------|-------|-----|
| **Purchase Order Request Approver** (child) | `level` (Int, reqd), `approver` (Link → Employee, reqd) | Purchase Order `custom_po_request_approver` | the PO's own multi-level approver list (predates / complements the generic Dynamic Approval) |
| **Material Request Approver** (child) | `level` (Int), `approver` (Link → Employee) | *(no live reference found)* | legacy MR approval table — superseded by Dynamic Approval |

## Sub-ledger / vehicle mapping

| Doctype | Fields | Backs | Why |
|---------|--------|-------|-----|
| **Vehicle List** (child) | `vehicle_list` (Link → Vehicle, reqd) | **Account** `custom_sub_type_list` | ⭐ the per-Account vehicle whitelist — the vehicle pickers on PI/JE (`pi.js`, `journal_entry.js`) and the `vehicle_mandatory` validation read `Account.custom_sub_type_list.vehicle_list` to decide which vehicles a vehicle-expense account allows (chapter 4 §7) |
| **Sub-Ledger Category** (`field:sub_ledger`, nested-set) | `sub_ledger` (Data, reqd/unique), `is_group` (Check), `parent_sub_ledger_category`/`old_parent` (Link self), `company` (Link), `table_dcoy` (Table → Sub-ledger table), `lft`/`rgt` (tree) | self + Sub-ledger table | a tree of sub-ledger categories (an earlier sub-classification scheme; the vehicle-expense report's "Sub-Ledger Category" filter references this concept — now largely replaced by the direct Vehicle link) |
| **Sub-ledger table** (child) | `sub_type_list` (Link → Sub-Ledger Category) | Sub-Ledger Category `table_dcoy` | child rows of the sub-ledger tree |

## Sales-invoice calculation tables

| Doctype | Fields | Backs | Why |
|---------|--------|-------|-----|
| **Amount Calculation for sales invoice** (child) | `item_code` (Data, reqd) | Sales Invoice `custom_difference_calculation_table` (hidden) | backing rows for the excise/VAT/rounding-difference reconciliation used by `override_rounding.py` (⚠️ that engine is dead code — chapter 4 §11, so this table is effectively dormant) |
| **Invoice Calculation** (child) | *(zero fields)* | *(nothing)* | empty orphan doctype — safe to delete |

## Other

| Doctype | Fields | Backs | Why |
|---------|--------|-------|-----|
| **Employee Cost Center Manager** (child) | `cost_center` (Link → Cost Center), `user` (Link → User) | **Employee** `custom_employee_cost_center_manager` | maps cost centres to a managing user on the Employee record; not referenced by documented app code (data-only) |
| **Material request table** (child) | `supplier`, `item`, `qty`, `uom`, `rate`, `amount`, `discount`, `taxable_amount`, `include_vat` (Check), `vat_13`, `total_amount` | *(no live reference found)* | a custom MR line table with VAT columns — orphaned/legacy |

**Status summary:** load-bearing → Purchase Type, Receipt type, Payment -
Receipt Type, JV Type, Vehicle List, Purchase Order Request Approver, Amount
Calculation for sales invoice. Dormant (backs dead code) → Amount Calculation
(via override_rounding). Orphaned/legacy → Invoice Calculation (empty),
Material Request Approver, Material request table, Employee Cost Center Manager,
Sub-Ledger Category + Sub-ledger table.

