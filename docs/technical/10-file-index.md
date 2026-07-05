# Complete File Index — Every File, Where It Is & Why

> Chapter 10 of the technical documentation. The exhaustive map: every source
> file in the app, what it is, why it exists, and whether it is **wired**
> (active in `hooks.py`/`__init__.py`), **console** (run manually), or
> **dead/legacy** (present but unreferenced). `__init__.py` package markers and
> `__pycache__` are omitted. Deep behavior lives in chapters 2–9; this chapter
> is the index that guarantees nothing is missed.

Legend: 🟢 wired · 🔧 console/setup only · 🟠 dead/legacy · 📄 data/asset · 🧪 test

## Root of the app (`apps/avinashgroup_app/`)

| File | What / why | Status |
|------|-----------|--------|
| `README.md` | Frappe boilerplate: install + pre-commit note, MIT | 📄 |
| `license.txt` | MIT license text (placeholders unfilled) | 📄 |
| `pyproject.toml` | package metadata; **dependency `nepali-datetime`** (BS dates for CBMS); ruff config (line 110, tab indent, double quotes) | 📄 |
| `.pre-commit-config.yaml` | pre-commit hooks: ruff (import-sort + lint + format), prettier (js/vue/scss), eslint, standard checks | 📄 |
| `.editorconfig` | LF, UTF-8, tab size 4 (py/js), 2-space for JSON | 📄 |
| `.gitignore` | `.pyc`, `__pycache__`, `node_modules`, egg-info, swap files | 📄 |
| `CURRENT_CHANGES_DOCUMENTATION.txt` | ⚠️ **stale** mid-session scratch log (Apr 2026) about a dynamic-approval default-section idea + a reverted JE search handler — superseded by chapter 2 | 🟠 |
| `IMPLEMENTATION_SUMMARY.md` | fiscal-year access implementation writeup (May 2026) — superseded by chapter 6 | 🟠 |
| `FISCAL_YEAR_ACCESS.md` | fiscal-year access user/dev guide — superseded by chapter 6; ⚠️ its "System User bypass" claim is wrong (it's Administrator/System Manager) | 🟠 |
| `testing.md` | ⭐ **current & unique** — 38 KB adversarial test plan + partial live run for the naming-series engine (60+ cases, race/TOCTOU risks, real findings: duplicate `custom_name` in PI/PR with no unique index, Grihalaxmi bypass, dotted-key loss). The authoritative testing reference | 📄 |
| `Document_Numbering_System.pdf` | design/spec PDF for voucher numbering (belongs under docs/ ideally) | 📄 |
| `wkhtmltox_0.12.6.1-3.jammy_amd64.deb` | ⚠️ 17 MB vendored wkhtmltopdf installer — should not be in the repo; make it an install step | 📄 |
| `create_test_sq.py` | throwaway seed script — creates 3 Supplier Quotations for Grihalaxmi; run via `bench execute` | 🔧🧪 |

## Package root (`avinashgroup_app/`)

| File | What / why | Status |
|------|-----------|--------|
| `hooks.py` | **the wiring hub** — all events, includes, overrides, scheduler, fixtures (chapter 1 §3) | 🟢 |
| `__init__.py` | app version + applies `regional_deletion_override.apply_patch()` at import (chapter 4 §5) | 🟢 |
| `modules.txt` | single module "Avinash Group App" | 📄 |
| `patches.txt` | migration patch order (see Patches table below) | 📄 |
| `create_test_sq.py` (package copy) | duplicate of the root seed script | 🔧🧪 |
| `test_data.py`, `test_stock_adj.py` | ad-hoc developer test scripts (not the automated suite) | 🧪 |

## `custom_code/` — server business logic

### Top level

| File | What / why | Chapter | Status |
|------|-----------|---------|--------|
| `dynamic_approval.py` | the whole configurable approval engine (`*`-hooked) | 2 | 🟢 |
| `workflow_admin_bypass.py` | overrides `get_transitions`/`apply_workflow`; Administrator bypass; fires `before_workflow_action` for all users | 2 | 🟢 |
| `workflow.py` | `set_reject_reason` — stores reject reason to `custom_reason` or a comment | 2 | 🟢 |
| `workflow_material_request.py` | thin legacy alias of `set_reject_reason` | 2 | 🟠 |
| `update_workflows.py` | `run()` rebuilds all Dynamic Approval workflows | 2 | 🔧 |
| `create_log_doctype.py` | bootstraps the runtime **Dynamic Approval History** child doctype | 2 | 🔧 |
| `fiscal_year_filter.py` | fiscal-year access control (list SQL, has_permission, get_list override) | 6 | 🟢 |
| `excise_ledger.py` | only `modify_gl_entries` (PI before_submit) party-tags TDS-payable GL; rest is dead GLMI code | 4 | 🟢+🟠 |
| `stock_revaluation.py` | backdated-PI repost notice + nightly repost helpers (nightly job not scheduled) | 4 | 🟢+🔧 |
| `stock_health_check.py` | `run()` stock diagnostics | 4 | 🔧 |
| `vehicle_mandatory.py` | Vehicle mandatory on vehicle-expense JE/PI lines | 4 | 🟢 |
| `regional_deletion_override.py` (+`.md`) | lets Admin/System Manager delete submitted Nepal-company docs | 4 | 🟢 |
| `regional_deletion_override.md` | short design note for the above | — | 📄 |
| `override_rounding.py` | 71 KB excise-inclusive tax/rounding recompute — unwired, 57% commented | 4 | 🟠 |
| `voucher_no_console.py` | console backfills of `custom_name` (PI/JE) | 4 | 🔧 |
| `api.py` | fiscal-year/naming legacy helpers + `create_created_by_and_created_on_fields` installer/backfill | 4/6 | 🔧🟠 |
| `custom_customer.py` | misnamed — locks company on two *test* doctypes | 4 | 🔧 |
| `custom_itemname.py` | `CustomItem.autoname` override — never registered | 4 | 🟠 |

### `custom_code/common/`

| File | What / why | Status |
|------|-----------|--------|
| `purchase_taxes_handler.py` | VAT/Excise/TDS + warehouse forcing for PI/PO/PR/SQ (+MR/RFQ) | 🟢 |
| `selling_taxes_handler.py` | VAT/Excise for Quotation/SO/DN | 🟢 |
| `purchase_taxes_mapper.py` | `get_taxes_from_source` (JS-used); `after_mapping_*` unreferenced | 🟢+🟠 |

### `custom_code/SalesInvoice/`

| File | What / why | Status |
|------|-----------|--------|
| `salesinvoice_taxes.py` | SI VAT/Excise + selling `validate_*` warehouse forcing (the live SI handler) | 🟢 |
| `print_count.py` | IRD print-copy counter on `before_print` (chapter 4 §5a) | 🟢 |
| `salesinvoice_customer.py` | customer credit checks — called only by unloaded `si.js` | 🟠 |
| `credit_control.py` | alternate credit engine — dead + `debugpy` breakpoint trap | 🟠 |

### `custom_code/Override/`

| File | What / why | Status |
|------|-----------|--------|
| `overrides.py` | 9 doctype class overrides (warehouse restore + soften warehouse-mandatory) | 🟢 |
| `naming_series.py` | 31 KB voucher-numbering engine (`custom_name`, `custom_document_no`, branch series) | 🟢 |
| `get_item_details.py` | wraps `get_item_details` (item-price patch + cmd strip) | 🟢 |
| `auto_insert_item_price.py` | `before_request` patch stamping company on auto Item Prices | 🟢 |
| `query_report.py` | report "Add Column" shows Link titles not ids | 🟢 |
| `company_field_lock.py` | `validate_company_field_lock` (wired via audit) + read-only property setter | 🟢+🔧 |
| `setup_company_lock.py` | console tools for the company lock | 🔧 |

### `custom_code/CBMS/` (chapter 5)

| File | What / why | Status |
|------|-----------|--------|
| `sales_invoice_hooks.py` | on_submit/before_cancel; payload mapping; CBMS doc creation | 🟢 |
| `api_client.py` | HTTP client to IRD; payload builders; result recording | 🟢 |
| `scheduler.py` | 5-min retry + reconcile jobs | 🟢 |
| `utils.py` | BS-date / fiscal-year / invoice-number helpers | 🟢 |

### `custom_code/globalfilter/` (chapter 6)

| File | What / why | Status |
|------|-----------|--------|
| `globalfilter.py` | company-matching validation + filtered link searches + config cache | 🟢 |

### `custom_code/document_generator/` (chapter 7)

| File | What / why | Status |
|------|-----------|--------|
| `api.py` | all whitelisted endpoints (instantiate/save/pdf/email/preview) | 🟢 |
| `providers.py` | context builders, SQL/Python source runners, safety guards | 🟢 |
| `pdf.py` | pdfkit/wkhtmltopdf wrapper (margin control) | 🟢 |
| `styles.py` | print-safe HTML wrapper + CSS | 🟢 |

### `custom_code/payment_entry/` and `purchase_invoice/`

| File | What / why | Status |
|------|-----------|--------|
| `payment_entry/cheque_bounce.py` | reversing GL entry on cheque bounce (button) | 🟢 |
| `purchase_invoice/purchase_invoice_taxes_tds.py` | superseded alternate PI tax handler | 🟠 |

## `biometric/` (chapter 3)

| File | What / why | Status |
|------|-----------|--------|
| `iclock.py` | ZKTeco ADMS `/iclock/*` page renderer | 🟢 |
| `api.py` | `receive_attendance` bridge endpoint | 🟢 |
| `utils.py` | `process_attendance_records`, checkin reconciliation, `assert_known_device` | 🟢 |
| `attendance_override.py` | shift-deviation fields, late half-day, checkin↔attendance reconcile | 🟢 |
| `employee.py` | unique device-id per company | 🟢 |
| `heartbeat.py` | `ping` + hourly dead-bridge alerting | 🟢 |
| `bridge_commands.py` | poll/report command tunnel | 🟢 |
| `test_attendance_pipeline.py` | the main automated test suite | 🧪 |

## `payroll/`

| File | What / why | Status |
|------|-----------|--------|
| `attendance_allowance.py` | holiday flag hook + attendance-driven Additional Salary engine (chapter 3 §6) | 🟢 |

## `utils/`

| File | What / why | Status |
|------|-----------|--------|
| `audit_file_manager.py` | audit-field engine + **`AuditEventMapper` — the base doc_events map** (chapter 6 §3) | 🟢 |
| `fiscal_year_utils.py` | `get_default_fiscal_year()` BS FY label helper (JS-used) | 🟢 |
| `export_field.py` | export all custom fields to Excel | 🔧 |

## `scripts/`

| File | What / why | Status |
|------|-----------|--------|
| `cleanup_audit_fields.py` | remove audit/naming fields + property setters from a doctype | 🔧 |
| `pad_custom_name.py` | zero-pad `custom_name` numbers to 6 digits (dry-run default) | 🔧 |

## `templates/pages/` — portal & web pages (chapters 4 §9, 8 §5)

| File | What / why | Status |
|------|-----------|--------|
| `customer_statement.py` + `.html` | `/customer_statement` — customer's own Party-Ledger statement + PDF; `_resolve_request` security; excludes deposit/security accounts | 🟢 |
| `product_wise_invoice_details.py` + `.html` | `/product_wise_invoice_details` — reuses the report's `build_rows(include_agent=False)`; per-customer security | 🟢 |
| `place_order.py` + `.html` | `/place_order` — LP Gas Sales Order placement | 🟢 |
| `rfq.py` + `.html` | supplier RFQ portal override (`create_supplier_quotation`) + attachment upload | 🟢 |

## `public/js/` — client scripts

Loaded globally via `app_include_js` (🟢g) or per-form via `doctype_js` (🟢f);
`si.js`/`purchase_invoice.js` are **not loaded** (🟠).

| File | Load | What / why |
|------|------|-----------|
| `fiscal_year_cache.js` | 🟢g | once-a-day client cache of the default BS fiscal year |
| `approval_workflow_common.js` | 🟢g | hides Approve/Reject for non-approvers; reject-reason dialog |
| `approval_workflow_auto.js` | 🟢g | generic approval progress banner + reject binding |
| `approval_field_visibility.js` | 🟢g | disables form for non-approvers; locks approved rows; driver-field visibility |
| `sales_invoice.js` | 🟢g | SI VAT UI + selling warehouse injection + due date |
| `purchase_taxes_common.js` | 🟢g | PI/PO/PR/SQ VAT/TDS UI, warehouse injection, source population |
| `selling_taxes_common.js` | 🟢g | Quotation/SO/DN VAT UI |
| `sales_warehouse_common.js` | 🟢g | Quotation/SO/DN warehouse injection |
| `global_filter.js` | 🟢g | row-level company-mismatch guard on item/supplier child rows |
| `company_filter.js` | 🟢g | the company dropdown-filter engine |
| `payment_entry.js` | 🟢g | cheque-bounce button + party scoping |
| `auto_update_document_no.js` | 🟢g | auto-fills `custom_document_no` on PR/PI/PE/JE |
| `report_print_orientation.js` | 🟢g | report Portrait/Landscape dialog + PDF styling shims |
| `vehicle_mandatory.js` | 🟢g | client mirror of vehicle-mandatory validation |
| `material_request.js` | 🟢f | MR warehouse forcing + reject dialog |
| `pi.js` | 🟢f | PI vehicle picker (`custom_subtype`) |
| `journal_entry.js` | 🟢f | JE vehicle picker |
| `attendance.js` | 🟢f | Attendance "Checkin Log" table |
| `payroll_entry.js` | 🟢f | "Calculate Attendance Allowances" button |
| `party_duplicate_check.js` | 🟢f | Customer/Supplier duplicate name/tax_id warning |
| `party_default_account.js` | 🟢f | Customer/Supplier default-accounts row |
| `item_default_account.js` | 🟢f | Item default row |
| `si.js` | 🟠 | credit-control UI — **not loaded** (feature dormant) |
| `purchase_invoice.js` | 🟠 | **not loaded** |

## `public/css/`

| File | What / why | Status |
|------|-----------|--------|
| `desk_focus.css` | orange focus ring + dropdown highlight | 🟢g |
| `report_print_portrait.css` | portrait print CSS injected dynamically on report routes | 🟢 (dynamic) |

## `fixtures/`

| File | What / why | Status |
|------|-----------|--------|
| `document_template.json` | the two balance-confirmation Document Templates (chapter 7 §6) | 📄 |

## `translations/`

| File | What / why | Status |
|------|-----------|--------|
| `en.csv` | single override: "Avinas Vehicle Expense" → "Nepal Gas Vehicle Expense" | 📄 |

## `patches/` — one line each (order in `patches.txt`)

**Pre-model-sync:** `create_document_generator_roles` (roles),
`rename_vocher_number_settings` (fix misspelled doctype).

**Post-model-sync:** `setup_attendance_allowance` (Salary Component rule
fields), `v1_add_biometric_device_serial` (backfill serial),
`user_fiscal_year_access_fields` (deprecated no-op),
`migrate_fiscal_year_access_control` (legacy→new doctype),
`cleanup_document_generator_sections` (drop old block doctypes),
`create_document_generator_image_fields` (stamp/signature),
`create_document_generator_signatory_field` (Employee→User signatory),
`leave_application_dynamic_approval` (Leave App under approval),
`enable_track_changes_audited_doctypes` (Version history),
`add_creation_index_daily_entry` ((owner, creation) index),
`create_cbms_custom_fields` (`custom_reason_for_return`),
`add_gl_entry_fin_stmt_agg_index` (consolidated-report index),
`vehicle_mandatory_property_setters` (run twice: add then remove setters),
`add_company_to_employee_checkin`, `company_scoped_attendance_device_id`
(drop global-unique device-id index), `add_company_to_shift_type`,
`add_sales_invoice_print_count` (`custom_print_count` for IRD copies).
`seed_company_filter_config` is present but **commented out** in patches.txt.

## Doctypes, custom fields & reports

- Custom doctypes: **28 file-based** (folders under
  `avinash_group_app/doctype/`) + **13 DB-only** (in the module but created via
  Customize UI — *not in the repo*, so `git clone` won't recreate them). Full
  reference: [chapter 9](09-doctypes-reference.md) +
  [chapter 11 Parts B & C](11-custom-fields-and-doctypes.md).
  The 13 DB-only ones: Purchase Type, Receipt type, Payment - Receipt Type, JV
  Type (voucher-code lists); Vehicle List (Account→Vehicle map); Purchase Order
  Request Approver, Material Request Approver (approval tables); Amount
  Calculation for sales invoice, Invoice Calculation (SI calc tables);
  Sub-Ledger Category + Sub-ledger table; Employee Cost Center Manager;
  Material request table.
- Custom fields on core doctypes (`custom/*.json`):
  [chapter 11](11-custom-fields-and-doctypes.md).
- Reports (26) + `page/document_generator/`: [chapter 8](08-reports-reference.md)
  and the [reports appendix](12-reports-appendix.md).

## `.claude/settings.local.json`

Local Claude Code settings for this app dir — not application code.
