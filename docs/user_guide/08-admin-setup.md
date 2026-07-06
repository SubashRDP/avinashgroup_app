# Administrator Setup — User Guide

For System Managers. Every feature's setup checklist in one place. Console
commands run via `bench --site avinas1 console` (or
`bench --site avinas1 execute <dotted.path>`).

<a id="approvals"></a>
## 1. Dynamic Approvals

1. **Dynamic Approval Setting** → New: pick the **Document Type** and
   **Company**; keep the default fieldnames.
2. In the **rule cards** area, *Add Section*: give it a name, add **criteria**
   (field = value pairs — ALL must match; the rule with the most matching
   criteria wins) and the ordered **fixed approvers**.
   ⚠️ A section with *no* criteria matches nothing — for a catch-all rule add
   one always-true criterion (e.g. company = that company).
3. Click **Setup Workflow** (button, System Manager only). This injects the
   approval fields onto the document type and creates/updates the
   "<DocType> Approval Workflow" (Draft → Pending Approval → Approved /
   Rejected).
4. Documents with **no matching rule auto-approve** — verify your criteria
   cover what you intend.
5. After changing the engine or Setting fields, rebuild all workflows:
   `from avinashgroup_app.custom_code import update_workflows; update_workflows.run()`
6. Rejection reasons are stored in the document's `custom_reason` field if it
   exists (e.g. Purchase Order), otherwise as a comment.
7. Only the literal **Administrator** account bypasses approver checks (one
   level at a time); System Managers do not.

## 2. Biometric devices & the bridge

1. Per device: **Biometric Device** → New — name, **hardware serial** (must
   match exactly; unknown serials are rejected), **Company**, enabled.
2. Per employee: set **Attendance Device ID** (unique within the company),
   correct Company, and a Shift Assignment. Shift Types need their Company
   set and auto-attendance enabled.
3. Bridge PC (per site): install `K40BridgeSetup.exe` on an always-on Windows
   machine on the device LAN. In the wizard: ERPNext URL + an **API
   key/secret** for a bridge user (needs Employee Checkin create, Biometric
   Device read/write, Employee read), then one row per device (name, type,
   IP/port or HTMS folder, serial, company). Test Connection → Save & Start.
4. Verify: tap a finger, check the Employee Checkin list.
5. Alerts: fill **Alert Recipients** + threshold on each device.
6. Optional Shift Type extras: `custom_late_arrival_cutoff_time` enables the
   automatic Half-Day rule.

## 3. Attendance allowances

1. Mark each allowance **Salary Component**: *attendance driven*, condition
   type, unit, default rate, optional summary group (groups columns in the
   summary report).
2. Employee overrides: Employee → **Attendance Allowances** table; OT-type
   rules also need the employee's **OT Eligibility** checkbox.
3. HR runs **Calculate Attendance Allowances** on each Payroll Entry.

## 4. CBMS (IRD e-billing)

One **CBMS Config** per company: Enable + **Enable From Date** + IRD
username/password. No test mode — production endpoints only. Monitor the CBMS
Bill list; errors are in each record's Sync Response and in the Error Log.
Immediate manual retry (rarely needed):
`frappe.get_doc("CBMS Config", "<company>").sync_failed_now("<company>")`.

## 5. Fiscal-year access control

- **Default is full access.** A user is restricted only once a **Fiscal Year
  Access Control** record exists for them: either *Full Access*, or rows of
  (Document Type → specific Fiscal Year / all years).
- Administrator and anyone with **System Manager always bypass**.
- It restricts *seeing* (lists, reports, direct opens, API) — it does **not**
  block saving a document dated outside the range.
- Changes take effect on the user's next request.

## 6. Company filtering

- **Company Filter Config** (one per doctype) + **Company Filter Field** rows
  define which Link fields are filtered to the document's company (plain,
  child-table, or dynamic-link fields).
- Saving clears the server cache; users must **refresh their browser** to pick
  up config changes.
- Server-side "Company Mismatch" validation runs on save for all audited
  doctypes regardless of the JS.

## 7. Audit fields, numbering & company lock

- Audit fields (`created by/on`, `modified by`, company, naming series) are
  stamped automatically on ~85 doctypes. Manage per doctype from the console —
  **always pass an explicit list** (no argument = all ~85 doctypes):
  ```python
  from avinashgroup_app.utils.audit_file_manager import AuditFieldsManager, update_custom_company_reqd
  AuditFieldsManager(["Item Price"]).create_fields()
  AuditFieldsManager(["Item Price"]).verify_fields()
  AuditFieldsManager(["Item Price"]).remove_fields()
  update_custom_company_reqd()
  ```
- Voucher zero-pad width per doctype: **Voucher Number Settings** (child rows:
  doctype → digits, default 6).
- Company-field lock (read-only after first save) — runtime block is always
  on; to also grey the field in the UI:
  ```python
  from avinashgroup_app.custom_code.Override import setup_company_lock
  setup_company_lock.quick_setup(); setup_company_lock.verify_setup()
  ```
- Track-changes for the audit trail and the `(owner, creation)` /
  GL-aggregation indexes are installed by `bench --site avinas1 migrate`.

## 8. User Daily Entry Summary

**User Daily Entry Summary Settings** (single) → add the doctypes to track
(keep the list short — one query each per report run), then `migrate` to build
the indexes.

## 9. Document Generator

1. Roles come from migrate: *Document Template Manager* (authors),
   *Document Template User* (generates own documents only).
2. One-time assets: Company → **Document Stamp** image; Employee →
   **Signature Image** and **Document User** (link to the User who signs —
   deliberately separate from the employee's login user).
3. The two balance-confirmation templates ship as fixtures; new templates are
   authored per the technical guide
   ([`../technical/07-document-generator.md`](../technical/07-document-generator.md) §7).

## 10. Housekeeping & diagnostics

| Task | Command |
|------|---------|
| Stock health check (negative stock, zero-valuation sales, repost queue) | `bench --site avinas1 execute avinashgroup_app.custom_code.stock_health_check.run` |
| Restart failed valuation reposts | console → `avinashgroup_app.custom_code.stock_revaluation.reprocess_all_pending()` |
| Export all custom fields to Excel | console → `avinashgroup_app.utils.export_field.export_custom_fields_to_excel()` |
| Pad voucher numbers to 6 digits (dry run) | console → `avinashgroup_app.scripts.pad_custom_name.run(dry_run=1)` |
| Remove audit/naming fields from a doctype | `avinashgroup_app.scripts.cleanup_audit_fields.run(["<DocType>"])` |
| DB replication runbook | `docs/db-master-slave-replication.md` |

## 11. Deployment reminders

- After editing client JS: bump its `?v=` in `hooks.py`, `bench build`,
  restart, and have users hard-refresh.
- After Python changes on live: `bench restart`.
- `bench --site avinas1 migrate` after pulling — patches are idempotent.
- The dev server can mask real errors behind a 500 BrokenPipeError page —
  check the console/logs, not the HTTP response.
