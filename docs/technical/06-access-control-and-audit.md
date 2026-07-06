# Access Control, Company Filtering & Audit — Technical Reference

> Chapter 6 of the technical documentation. Audience: developers.
> User-facing guide: [`../user_guide/08-admin-setup.md`](../user_guide/08-admin-setup.md)

Four related subsystems: **fiscal-year access control**, **company filtering**,
**audit trail**, and **user daily entry summary**.

Path note: doctypes/reports live under `avinashgroup_app/avinash_group_app/…`
(with underscore); custom code and utils under `avinashgroup_app/…` directly.

---

## 1. Fiscal-Year Access Control

Restricts which fiscal years' transactions a user can see.
Core file: `custom_code/fiscal_year_filter.py`.

### 1.1 Scope

- `FILTERED_DOCTYPES` (`:8-84`) — 77 transaction doctypes (Sales Invoice,
  Purchase Invoice, Payment Entry, Journal Entry, Stock Entry, Attendance,
  Leave Application, Salary Slip…). Anything not in the tuple is never
  filtered.
- `DATE_FIELD_MAP` (`:103-179`) — per-doctype date field used for the
  comparison (`Attendance → attendance_date`, `Sales Order →
  transaction_date`…); fallback `posting_date`.

### 1.2 Who is restricted

- `_is_admin` (`:87-100`): **Administrator or any System Manager always
  bypasses** all checks.
- `_get_user_fiscal_access(user)` (`:196-256`, `@request_cache`): reads the
  user's `Fiscal Year Access Control` record.
  **No record → full access (allow-all default).** `full_access=1` → full
  access. Otherwise child rows (`User Fiscal Year Access`) build
  `{doctype: "__full_access__" | [fiscal years]}`. A legacy fallback
  (`:259-301`) reads the pre-migration per-User custom fields.

### 1.3 Enforcement — three live layers

| Layer | Function | Wired at |
|-------|----------|----------|
| List views / reports (SQL WHERE) | `_build_query_conditions` (`:445-484`) via generated `query_conditions_<slug>` functions (`:487-497`) | `hooks.py:214-217` `permission_query_conditions` |
| Direct document access | `has_fiscal_year_permission` (`:500-538`) | `hooks.py:220-223` `has_permission` |
| Client API `frappe.client.get_list` | `filtered_get_list` (`:541-581`) injects date filters or returns `[]` | `hooks.py:263` `override_whitelisted_methods` |

Query conditions return `""` (no restriction), `"1=0"` (no access), or
`(BETWEEN 'from' AND 'to' OR ...)` per allowed fiscal year, dates escaped.
`has_fiscal_year_permission` is permissive when the doc has no parseable date
(`:525-526`).

### 1.4 Known gaps / quirks (documented on purpose)

- **No write-time block**: `validate_fiscal_year_access` (`:390-429`) and
  `apply_fiscal_year_filter_to_list` (`:342-387`) are defined but **not wired**
  in hooks.py — a user can still *save* a document dated outside their range;
  they just won't see it afterwards.
- **Cache invalidation is per-request only**: the resolver uses
  `@request_cache` (in-memory, dies at request end), but the invalidation
  hooks (`clear_user_fiscal_cache` on User update, the controller's
  `on_update`/`on_trash`) delete *redis* keys that the resolver never writes —
  and the two key formats don't even match each other
  (`user_fiscal_access_*` vs `_get_user_fiscal_access_*`). Net effect: changes
  apply on the next request anyway; the redis clears are no-ops.
- An older `FISCAL_YEAR_ACCESS.md` claim that bypass is by
  `user_type == "System User"` is stale — bypass is Administrator/System
  Manager role.

### 1.5 Doctypes

- **Fiscal Year Access Control** — autoname `field:user` (one per user);
  fields `user` (Link, unique reqd), `full_access` (Check), `access_details`
  (Table → User Fiscal Year Access). System Manager only; track_changes.
- **User Fiscal Year Access** (child) — `doctype_name` (Link → DocType, reqd),
  `fiscal_year` (Link, mandatory unless row `full_access`), `full_access`
  (Check = all fiscal years for that doctype).
- Patch `migrate_fiscal_year_access_control.py` migrates the legacy per-User
  custom-field config and deletes those fields.

### 1.6 Related: default fiscal year helper

`utils/fiscal_year_utils.py::get_default_fiscal_year()` computes the Nepali BS
fiscal year label (`"82/83"`; Shrawan→Ashadh via
`rdp_common_app.utils.bs_boundaries`). Consumed by
`public/js/fiscal_year_cache.js` (`window.FiscalYearCache`, once-per-day
client cache, midnight rollover). This is a convenience for form scripts —
**not** part of access enforcement.

---

## 2. Company Filter System

Ensures every Link selection on a document belongs to the document's company.
Core file: `custom_code/globalfilter/globalfilter.py`.

### 2.1 Server side

- `FILTER_CONFIG` (`:12-170`) — hardcoded fallback config per doctype:
  `company_field` (`company`/`custom_company`), top-level `fields`,
  `child_tables`. Covers the Asset family, masters, and the full
  buying/selling chain. ⚠️ The party-aware custom validation for Journal
  Entry / Payment Entry / Bank Account is **commented out** in
  `CompanyValidator.validate()` (`:479-494`).
- `_resolve_company_field(linked_doctype)` (`:216-235`): Company → `name`,
  else `company`, else `custom_company`, else skip. Customer/Supplier scoped
  via the `Allowed To Transact With` child table (`:238-257`).
- **`CompanyValidator`** (`:290-496`) — 3-phase validator: collect all linked
  values (zero DB), one batch query per linked doctype, then compare each
  value's company to the parent's. Human-readable mismatch errors.
- `validate_company_matching(doc, method)` (`:503-520`) — the entry point;
  **throws** on mismatch (warns instead during data import). Wired via the
  audit engine: `audit_file_manager.validate` calls it for every audited
  doctype (§3).
- `get_filter_config()` (`:527-636`, whitelisted) — the JS config. Redis-cached
  (`company_filter_config`); built from the **Company Filter Config** /
  **Company Filter Field** doctypes; falls back to `FILTER_CONFIG` when the
  tables are empty. Pre-resolves `__filter_keys__` = `{linked_doctype:
  company_field}` so the client never needs meta lookups.
- `clear_filter_config_cache` — wired on Config/Field `on_update`/`on_trash`
  (`hooks.py:204-207`).
- Whitelisted searches used by `set_query`: `search_party` (`:655-712`) and the
  generic dynamic-link `search_link_by_company` (`:719-779`).

### 2.2 Client side

- `public/js/company_filter.js` (`avinash.filter_engine`) — on `app_ready`
  loads the config, then for each configured doctype: `set_query` filters on
  every configured field (dynamic links delegate to
  `search_link_by_company`); on company change, `validate_and_clear` clears
  mismatched top-level values (orange alert) and removes mismatched child rows.
  Preserves pre-existing `get_query` from the form's own scripts.
- `public/js/global_filter.js` — row-level guard: hooks `item_code` on 12 item
  child tables (+ RFQ `supplier`); a selected value whose company mismatches
  the parent is cleared with a red "Company Mismatch" message. Catches what
  dropdown filtering can't (paste/programmatic set).

### 2.3 Doctypes

- **Company Filter Config** — autoname `field:doctype_name`; `company_field`
  Select; `fields` Table. Controller clears the cache and asks users to
  refresh.
- **Company Filter Field** (child) — `fieldname`, `is_child_table` +
  `child_fieldname`, `is_dynamic_link` + `dynamic_link_field`.
- Patch `seed_company_filter_config.py` seeds the tables from `FILTER_CONFIG`
  (currently commented out in patches.txt).

---

## 3. Audit Trail

Core file: `utils/audit_file_manager.py`.

### 3.1 What is audited

`AuditBase.doctypes` (`:10-111`) — ~85 doctypes (masters + all transactions).
`AuditBase.master_doctypes` (`:116-145`) — the subset that also gets a
`custom_naming_series` field.

### 3.2 Fields and stamping

`AuditFieldsManager` (`:149-462`) installs per-doctype custom fields: an
`audit_section` break, `custom_company` (Link, reqd — only when the doctype
has no native company field), `custom_naming_series` (masters), and
`custom_created_by` / `custom_created_on` / `custom_modified_by` (read-only,
no-copy, print-hide). `set_audit_fields` (`:551-578`) populates them on save
(session user; background jobs honor `frappe.flags.audit_user`).

⚠️ `AuditFieldsManager()` with **no argument targets all ~85 doctypes** —
always pass an explicit list when running from the console.

### 3.3 The event map — the app's doc_events backbone

`AuditEventMapper.get_doc_events()` (`:466-492`) is what `hooks.py:131`
assigns as the base `doc_events`. For every audited doctype:

| Event | Dispatcher does |
|-------|-----------------|
| `before_insert` | `set_audit_fields` + naming requirements |
| `before_save` | `set_audit_fields` + naming save handling |
| `validate` | company-field lock check + **`validate_company_matching`** (company filter §2) + naming validate |
| `autoname` | custom naming series (chapter 4 §naming) |
| `after_delete` | revert the number series |

So audit stamping, company matching, and custom document numbering all ride
this one map; feature-specific handlers are merged on top with
`_add_doc_event`.

### 3.4 Change history and report

- **WHO** → the custom fields on each row. **WHAT** → Frappe's `Version`
  doctype; patch `enable_track_changes_audited_doctypes.py` switches on
  `track_changes` for every audited doctype (only edits after the patch
  generate Versions).
- **User Audit Trail** report (`report/user_audit_trail/`, roles: System
  Manager, Auditor, Accounts Manager, HR Manager): filters user* / from-to
  dates* / action / document types. "Created" rows from `custom_created_by`;
  "Modified" rows parsed from `Version.data` JSON (field diffs, child-row
  add/remove, humanized docstatus). Only doctypes the *running* user can read
  are shown. Document column links to the record.

---

## 4. User Daily Entry Summary

Per user + day: counts of documents **created** (`owner`), by doctype and
docstatus. Full feature doc: `docs/user_daily_entry_summary.md`.

- **User Daily Entry Summary Settings** (Single, System Manager) — child table
  of tracked doctypes. Untracked = one aggregate SQL per doctype per run, so
  keep the list short.
- Report (`report/user_daily_entry_summary/`): filters user*, date* (default
  today), document types. One conditional-aggregate query per doctype
  (`SUM(docstatus=…)` over `owner + creation` day window). Count cells are
  drill-down links to the filtered list view. Always runs fresh
  (`ignore_prepared_report`).
- Patch `add_creation_index_daily_entry.py` adds a composite
  `(owner, creation)` index to each tracked table.
- Caveat: bulk-imported docs count against the importing account.

---

## 5. Utility scripts & misc assets

| File | Purpose |
|------|---------|
| `utils/export_field.py` | `export_custom_fields_to_excel()` — dump all `custom_*` fields to a timestamped `.xlsx` in `private/files/` (inventory/audit tooling) |
| `scripts/cleanup_audit_fields.py` | remove naming/company/audit custom fields + property setters from doctypes dropped from the audit list; restores original autoname; never renames records |
| `scripts/pad_custom_name.py` | zero-pad the numeric run in `custom_name` to 6 digits (PR/PI/JE/PE); dry-run by default; skips collisions |
| `public/js/auto_update_document_no.js` | auto-fills `custom_document_no` on new PR/PI/PE/JE via `naming_series.get_next_custom_document_no` (chapter 4 §naming) |
| `public/css/desk_focus.css` | cosmetic — orange focus ring + dropdown highlight, tunable via CSS variables |
| `public/css/report_print_portrait.css` | injected dynamically by `report_print_orientation.js` only on query-report routes (loading it globally would restyle doctype print formats) |
| `scripts/pad_custom_name.py` / `voucher_no_console.py` | voucher-number backfills (chapter 4 §4) |

---

## 6. Admin setup checklists

**Fiscal-year access** — ensure Fiscal Year records have correct start/end
dates; create a Fiscal Year Access Control per restricted user; either check
Full Access or add per-doctype rows (specific FY or row-level full access).
Users **without** a record have full access. Admin/System Managers always
bypass.

**Company filter** — manage Company Filter Config records (one per doctype);
add Company Filter Field rows for plain, child-table, or dynamic-link fields.
Cache clears on save; users must refresh the browser.

**Audit trail** — migrate (installs fields + track_changes); grant
Auditor/Accounts Manager/HR Manager for the report. Console management:
```python
from avinashgroup_app.utils.audit_file_manager import AuditFieldsManager, update_custom_company_reqd
AuditFieldsManager(["Item Price"]).create_fields()   # always pass a list!
AuditFieldsManager(["Item Price"]).verify_fields()
AuditFieldsManager(["Item Price"]).remove_fields()
update_custom_company_reqd()
```

**Daily entry summary** — add tracked doctypes in the Settings single; migrate
for the index; run the report.
