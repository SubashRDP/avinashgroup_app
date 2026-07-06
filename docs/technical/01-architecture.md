# Architecture Overview — avinashgroup_app

> Technical documentation, chapter 1 of 9. Audience: developers.
> The app runs on site **avinas1** (Frappe/ERPNext v15 bench at `/home/dell/frappe-v15`).

`avinashgroup_app` is the single custom app for the Avinash Group of companies
(Nepal — LP gas trading, dealerships, and allied businesses). It consolidates what
were previously three apps: the original avinashgroup customizations, plus
`biometric_integration` and `nepal_hrms`, which were merged in (2026-05) and
uninstalled — see `docs/migrate_from_biometric_and_nepal_hrms.md`.

## 1. Repository layout

```
apps/avinashgroup_app/
├── avinashgroup_app/                  # the Python package
│   ├── hooks.py                       # ALL wiring — start here for any feature
│   ├── modules.txt                    # single module: "Avinash Group App"
│   ├── patches.txt                    # migration patches (see §7)
│   ├── avinash_group_app/             # the Frappe module
│   │   ├── doctype/                   # 26 custom doctypes (see chapter 9)
│   │   ├── report/                    # 26 script reports (see chapter 8)
│   │   ├── page/document_generator/   # Document Generator desk page
│   │   └── custom/                    # exported custom-field JSON for core doctypes
│   ├── custom_code/                   # server-side business logic, grouped by area
│   │   ├── common/                    # purchase/selling VAT+TDS handlers & mapper
│   │   ├── SalesInvoice/              # SI taxes, credit control
│   │   ├── purchase_invoice/          # PI TDS engine
│   │   ├── payment_entry/             # cheque bounce
│   │   ├── Override/                  # ERPNext class overrides, naming engine
│   │   ├── CBMS/                      # Nepal IRD CBMS e-billing sync
│   │   ├── globalfilter/              # company-scoped link filtering
│   │   ├── document_generator/        # letter/PDF generation backend
│   │   ├── dynamic_approval.py        # dynamic approval workflow engine
│   │   ├── fiscal_year_filter.py      # per-user fiscal-year access control
│   │   ├── excise_ledger.py           # excise GL rewriting on PI
│   │   └── ... (misc — see chapter 4 & 6)
│   ├── biometric/                     # ZKTeco iclock protocol + attendance pipeline
│   ├── payroll/                       # attendance allowance
│   ├── utils/                         # audit_file_manager, fiscal_year_utils, ...
│   ├── scripts/                       # one-off maintenance scripts
│   ├── patches/                       # migration patch implementations
│   ├── fixtures/                      # Document Template fixtures
│   ├── public/js, public/css          # ~24 client scripts + desk CSS
│   └── templates/pages/               # customer/supplier portal pages
├── k40_bridge/                        # Windows desktop bridge for ZKTeco K40 devices
└── docs/                              # this documentation
```

**One Frappe module** — everything lives under module “Avinash Group App”
(`modules.txt`).

## 2. The eight functional domains

| # | Domain | Entry points | Chapter |
|---|--------|-------------|---------|
| 1 | **Dynamic Approval System** | `custom_code/dynamic_approval.py`, 4 doctypes, `approval_workflow_*.js` | [02](02-dynamic-approval.md) |
| 2 | **Biometric attendance** | `biometric/`, `k40_bridge/`, 6 doctypes | [03](03-biometric-attendance.md) |
| 3 | **VAT / TDS / doctype overrides** | `custom_code/common/`, `SalesInvoice/`, `Override/` | [04](04-taxes-and-overrides.md) |
| 4 | **CBMS (IRD e-billing)** | `custom_code/CBMS/`, 3 doctypes | [05](05-cbms-integration.md) |
| 5 | **Access control & audit** | `fiscal_year_filter.py`, `globalfilter/`, `utils/audit_file_manager.py` | [06](06-access-control-and-audit.md) |
| 6 | **Document Generator** | `custom_code/document_generator/`, desk page, 5 doctypes | [07](07-document-generator.md) |
| 7 | **Reports suite** | `avinash_group_app/report/` (26 reports) | [08](08-reports-reference.md) |
| 8 | **Portal pages** | `templates/pages/` | [08](08-reports-reference.md) §Portal |

## 3. hooks.py — the wiring map

`hooks.py` is deliberately the single source of truth for how features attach to
Frappe. It uses a helper `_add_doc_event(doctype, event, handler)` to merge
per-feature event dicts into one `doc_events` structure without clobbering
earlier registrations (`hooks.py:133-151`).

### 3.1 Base doc_events come from the audit engine

```python
doc_events = AuditEventMapper.get_doc_events()   # hooks.py:131
```

`AuditEventMapper` (`utils/audit_file_manager.py`) returns handlers that stamp
audit fields (`custom_created_by/on`, `custom_modified_by`, `custom_company`,
`custom_naming_series` / `custom_name` document numbering) on ~80 doctypes.
Every other feature is merged on top via `_add_doc_event`.

### 3.2 Per-doctype server events (merged on top)

| Doctype | Events → handlers |
|---------|-------------------|
| Purchase Invoice | `before_validate/before_save/validate` → purchase taxes; `validate` → vehicle-mandatory; `before_submit` → `excise_ledger.modify_gl_entries`; `on_submit` → `stock_revaluation` |
| Purchase Order / Purchase Receipt / Supplier Quotation | `before_save` + `validate` → purchase taxes handler |
| Material Request / Request for Quotation | `validate` → purchase taxes handler (warehouse defaults) |
| Sales Invoice | `before_validate/before_save/validate` → selling taxes; `on_submit` + `before_cancel` → CBMS sync; `before_print` → IRD print-copy counter (chapter 4 §5a) |
| Quotation / Sales Order / Delivery Note | `before_validate/before_save` → selling taxes handler; `validate` → salesinvoice_taxes validators |
| Journal Entry | `validate` → vehicle-mandatory |
| Attendance | `validate` → holiday flag, shift deviation, late-arrival half-day (uses `validate`, **not** `before_save`, because device-marked attendance is inserted already-submitted and `before_save` would never fire — `hooks.py:118-129`) |
| Employee Checkin | `after_insert` → reconcile with existing Attendance |
| Employee | `validate` → unique biometric device-ID check |
| Company Filter Config / Field | `on_update`/`on_trash` → clear filter cache |
| User | `on_update` → clear fiscal-year permission cache |
| `*` (all doctypes) | `validate`, `before_save`, `on_update`, `before_workflow_action` → `dynamic_approval` engine |

### 3.3 Class overrides (`override_doctype_class`, hooks.py:230)

Nine transactional doctypes get subclassed controllers from
`custom_code/Override/overrides.py`: Material Request, Purchase Order, Sales
Invoice, Sales Order, Delivery Note, Purchase Invoice, Purchase Receipt,
Supplier Quotation, Request for Quotation. See chapter 4.

### 3.4 Whitelisted-method overrides (`override_whitelisted_methods`, hooks.py:258)

| Core method | Replaced by | Why |
|-------------|------------|-----|
| `...request_for_quotation.create_supplier_quotation` | `templates/pages/rfq.py` | supplier portal RFQ with VAT/discount/attachments |
| `erpnext.stock.get_item_details.get_item_details` | `Override/get_item_details.py` | branch-wise warehouse resolution |
| `frappe.model.workflow.get_transitions` / `apply_workflow` | `workflow_admin_bypass.py` | System Manager bypass of workflow restrictions |
| `frappe.client.get_list` | `fiscal_year_filter.filtered_get_list` | fiscal-year access control on API list calls |
| `frappe.desk.query_report.get_data_for_custom_field` | `Override/query_report.py` | report “Add Column” shows Link titles not ids |

### 3.5 Other hooks

- `page_renderer = biometric.iclock.IclockRenderer` (`hooks.py:11`) — implements the
  ZKTeco **iclock/ADMS push protocol** as raw URL endpoints (`/iclock/...`).
- `before_request` → `auto_insert_item_price.patch_insert_item_price_set_company` —
  monkey-patches ERPNext so auto-created Item Prices get `company` stamped.
- `scheduler_events` (`hooks.py:242`): hourly biometric-bridge heartbeat check;
  every 5 min CBMS retry + reconciliation.
- `app_include_js` — 14 globally loaded scripts (fiscal-year cache, approval UI,
  company filter, VAT calculators, document numbering, report print orientation…).
- `app_include_css` — `desk_focus.css` only.
- `doctype_js` — per-form scripts for Material Request, Purchase Invoice, Journal
  Entry, Attendance, Payroll Entry, Customer, Supplier, Item.
- `permission_query_conditions` + `has_permission` — generated per doctype in
  `FILTERED_DOCTYPES` for fiscal-year access control (chapter 6).
- `fixtures` — exports the two balance-confirmation **Document Template** records.

## 4. Shared conventions

- **Company scoping.** Most masters carry `custom_company`; transactions use the
  standard `company`. The Company Filter system (chapter 6) restricts link
  dropdowns and blocks cross-company saves. Report filter dropdowns come from
  whitelisted `get_company_*` helpers.
- **Nepali (BS) dates.** Transactions carry Miti custom fields
  (`custom_invoice_miti`, `custom_nepali_miti`, `custom_posting_miti`); attendance
  and payroll reports work in Bikram Sambat months.
- **Custom VAT scheme.** Line-level `custom_vat_apply_on` ∈ {`VAT 13%`, `VAT 0%`,
  `Amount`}, plus excise and a custom TDS field set — chapter 4.
- **Numbers.** Indian lakh/crore grouping (`en_IN`), currency NPR.
- **Script reports.** All synchronous script reports; heavy queries written to stay
  under Frappe's 15 s prepared-report auto-switch.
- **Console-applied setup.** Several features are installed per-site from the bench
  console rather than by migrate (workflow install, audit-field creation, company
  lock). Each feature's chapter has its Setup block. Run via
  `bench --site avinas1 console` or `bench --site avinas1 execute <dotted.path>`.

## 5. Client-asset versioning

Every entry in `app_include_js` carries a `?v=` query (`hooks.py:13-28`). **Bump
the version when you edit a script** — this is the cache-buster; without it desk
users keep the stale copy until a hard refresh.

## 6. Fixtures

`fixtures/document_template.json` exports exactly two Document Template records —
“Customer Balance Confirmation” and “Vendor Balance Confirmation” — filtered by
name in `hooks.py:274-281` so site-specific templates are not dragged along.

## 7. Patches (patches.txt)

Pre-model-sync:
- `create_document_generator_roles` — creates the Document Generator roles
- `rename_vocher_number_settings` — renames the voucher-number settings doctype

Post-model-sync (in order): `setup_attendance_allowance`,
`v1_add_biometric_device_serial`, `user_fiscal_year_access_fields`,
`migrate_fiscal_year_access_control`, `cleanup_document_generator_sections`,
`create_document_generator_image_fields`,
`create_document_generator_signatory_field`, `leave_application_dynamic_approval`,
`enable_track_changes_audited_doctypes`, `add_creation_index_daily_entry`,
`create_cbms_custom_fields`, `add_gl_entry_fin_stmt_agg_index`,
`vehicle_mandatory_property_setters` (run twice — second run removes the property
setters in favour of per-row JS validation), `add_company_to_employee_checkin`,
`company_scoped_attendance_device_id`, `add_company_to_shift_type`,
`add_sales_invoice_print_count` (adds `custom_print_count` for IRD copy
labeling).

(Per-patch details are in each feature's chapter.)

## 8. Development workflow

- Default branch: `develop`. Pre-commit hooks: ruff, eslint, prettier, pyupgrade.
- After changing Python: `bench restart` (live) / auto-reload (dev).
- After changing client JS: bump `?v=` in `hooks.py`, `bench build --app
  avinashgroup_app` if assets are imported, then hard-refresh.
- Migrations: `bench --site avinas1 migrate`.
- Tests: `bench --site avinas1 run-tests --app avinashgroup_app --module
  avinashgroup_app.biometric.test_attendance_pipeline` (the attendance pipeline
  suite is currently the main automated test).

## 9. Operational notes

- The avinas1 dev server masks real errors: any server error can render as a 500
  `BrokenPipeError` page. Check `bench --site avinas1 console` / logs instead of
  trusting the HTTP response.
- Database replication runbook: `docs/db-master-slave-replication.md`.
