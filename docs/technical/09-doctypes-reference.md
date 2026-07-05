# Custom Doctypes Reference — avinashgroup_app

> Chapter 9 of the technical documentation. The module "Avinash Group App" owns
> **41 doctypes**: **28 ship as files** under `avinash_group_app/doctype/`
> (below), and **13 are DB-only** (created via the Customize UI, not in the
> repo) — those are documented in
> [chapter 11 Part C](11-custom-fields-and-doctypes.md#part-c--db-only-custom-doctypes-in-the-module-not-in-the-repo).
> For the **full field list** of every file-based doctype see
> [chapter 11 Part B](11-custom-fields-and-doctypes.md#part-b--custom-doctype-fields);
> for exported custom fields on **core** ERPNext doctypes see
> [chapter 11 Part A](11-custom-fields-and-doctypes.md#part-a--custom-fields-on-core-doctypes).

## Dynamic Approval (chapter 2)

| Doctype | Kind | Role |
|---------|------|------|
| Dynamic Approval Setting | master (System Manager) | per doctype+company approval config; Setup Workflow button |
| Dynamic Approval Match Criteria | child | `section` + `field_name` = `field_value` equality rules |
| Dynamic Approval Fixed Approver | child | ordered fixed approvers per section |
| Dynamic Approval Approver | child (injected on targets) | the requester's per-document hierarchy rows |
| *(Dynamic Approval History)* | child, **created at runtime** | audit-log rows on target docs (no source JSON) |

## Biometric / Attendance (chapter 3)

| Doctype | Kind | Role |
|---------|------|------|
| Biometric Device | master | one per device/feed: serial (unique), company, sync stats, heartbeat alerting |
| Biometric Device Command | master | outbound-polled command queue (force_sync / test_connection) |
| Biometric Device Alert Recipient | child | alert emails |
| Attendance Fix | submittable | background attendance repair for a shift + date range |
| Attendance Fix Device | child | device filter rows |
| Employee Attendance Allowance | child (on Employee) | per-employee allowance rate/eligibility overrides |

## Taxes / Stock / Numbering (chapter 4)

| Doctype | Kind | Role |
|---------|------|------|
| Voucher Number Settings Item | child | per-doctype `voucher_no_digits` zero-pad width |
| Branch Wise Warehouse | child (on Item) | branch → buying/selling warehouse mapping (operative fields are site custom fields) |
| Stock Adjustment | submittable | quantity-only stock correction (rate must be 0); engine patch preserves stock value |
| Stock Adjustment Item | child | item/warehouse/qty rows |

## CBMS (chapter 5)

| Doctype | Kind | Role |
|---------|------|------|
| CBMS Config | one per company | enable flag, go-live date, IRD credentials, retry batch sizes |
| CBMS Bill | auto-created | one per submitted Sales Invoice; sync status/attempts/response |
| CBMS Bill Return | auto-created | one per submitted Sales Return (credit note) |

## Access control / Audit (chapter 6)

| Doctype | Kind | Role |
|---------|------|------|
| Fiscal Year Access Control | one per user | full-access flag or per-doctype fiscal-year grants |
| User Fiscal Year Access | child | doctype + fiscal year (or row-level full access) |
| Company Filter Config | one per doctype | which fields are company-filtered; `company_field` selector |
| Company Filter Field | child | plain / child-table / dynamic-link field rows |
| User Daily Entry Summary Settings | Single | tracked doctypes for the daily entry report |
| User Daily Entry Summary Doctype | child | one tracked doctype per row |

## Document Generator (chapter 7)

| Doctype | Kind | Role |
|---------|------|------|
| Document Template | master | HTML+Jinja letter template: inputs, data sources, header/footer, email settings |
| Document Template Input | child | generation-time input fields (incl. exclusive groups/sets) |
| Document Template Data Source | child | SQL (guarded SELECT) or Python (safe_exec) source |
| Document Template Company | child | company scoping |
| Generated Document | master (`DOC-GEN-.YYYY.-.#####`) | persisted rendered/edited output; status, payload snapshot, email status |

## Custom fields on core doctypes (`avinash_group_app/custom/*.json`)

Exported custom-field bundles (all also carry the audit block —
`custom_created_by/on`, `custom_modified_by`, plus `custom_abbr`/
`custom_company` on parents):

| File | Highlights |
|------|-----------|
| customer.json | credit fields `custom_amount_limit`, `custom_bill_count`, `custom_days_limit` |
| sales_invoice.json (28 fields) | excise/VAT totals, rounding adjustment, `custom_invoice_miti` + BS dates, vehicle no |
| sales_invoice_item.json | `custom_vat_apply_on/rate/amount`, `custom_excise_value`, `custom_total` |
| purchase_invoice.json (40 fields) | `custom_document_no`, `custom_name` (Voucher No), `custom_purchase_type`, TDS/VAT/excise totals, `custom_tax_withholding_category_custom`, IOC/PDO/refinery/store-receipt/miti/transport fields |
| purchase_invoice_item.json | VAT/TDS/excise item fields + `custom_subtype` (Vehicle) |
| purchase_order(.item).json | approval fields (`custom_reason`…), VAT/TDS/excise |
| purchase_receipt(.item).json | `custom_receipt_type`, voucher fields, IOC/miti, VAT/TDS/excise |
| supplier_quotation(.item).json | `custom_preferred_quotation`, VAT/TDS/excise |

Many more custom fields are installed programmatically (not exported):
`AuditFieldsManager` audit fields across ~85 doctypes, attendance-allowance
fields (patch), Document Generator image/signatory fields (patches), CBMS
`custom_reason_for_return` (patch), Employee Checkin / Shift Type company
fields (patches), and the Branch Wise Warehouse operative fields (site DB
only). `utils/export_field.py` can dump the live inventory to Excel.
