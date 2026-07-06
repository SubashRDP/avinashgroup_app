# avinashgroup_app — Documentation Index

Complete documentation for the Avinash Group custom app (site **avinas1**,
Frappe/ERPNext v15). Two sets:

- **Technical reference** (`technical/`) — for developers. Verified against the
  code on 2026-07-05; where older docs in this folder disagree, the technical
  chapters win.
- **User guide** (`user_guide/`) — task-oriented, for accountants, HR,
  purchase/sales staff and administrators.

## Technical reference

| # | Chapter | Covers |
|---|---------|--------|
| 1 | [Architecture Overview](technical/01-architecture.md) | repo layout, hooks.py wiring map, conventions, patches, fixtures, dev workflow |
| 2 | [Dynamic Approval System](technical/02-dynamic-approval.md) | the `*`-hooked approval engine, doctypes, generated workflow, admin bypass, JS |
| 3 | [Biometric Attendance & K40 Bridge](technical/03-biometric-attendance.md) | iclock/ADMS, bridge architecture, checkin pipeline, Attendance Fix, allowance engine |
| 4 | [VAT/Excise/TDS, Overrides & Numbering](technical/04-taxes-and-overrides.md) | the Apply-On tax scheme, 9 class overrides, warehouses, voucher numbering, GL patches, dead-code inventory |
| 5 | [CBMS Integration](technical/05-cbms-integration.md) | IRD e-billing sync, payloads, retry/reconcile schedulers, status model |
| 6 | [Access Control & Audit](technical/06-access-control-and-audit.md) | fiscal-year access, company filtering, audit trail, daily entry summary |
| 7 | [Document Generator](technical/07-document-generator.md) | template engine, data sources, PDF/email pipeline, security, authoring |
| 8 | [Reports & Portal Pages](technical/08-reports-reference.md) | all 20+ financial/sales reports, print/PDF infrastructure, portals |
| 9 | [Doctypes Reference](technical/09-doctypes-reference.md) | all 26 custom doctypes + exported custom-field bundles (quick map) |
| 10 | [Complete File Index](technical/10-file-index.md) | **every source file** — location, purpose, why, and wired/console/dead status |
| 11 | [Field Reference](technical/11-custom-fields-and-doctypes.md) | **every custom field** on core doctypes (182) + **every field** of all **41** module doctypes (28 file-based + 13 DB-only) |
| 12 | [Reports Appendix](technical/12-reports-appendix.md) | full per-report detail: sources, all filters, columns, logic, why |
| 13 | [Per-Doctype Reference](technical/13-per-doctype-reference.md) | **by doctype** — for each doctype, everything the app did to it (fields, hooks, JS, overrides, reports, why) |
| 14 | [Site Customization Inventory](technical/14-site-customization-inventory.md) | **full avinas1 audit — code + database**: every doctype's custom fields, property setters, client scripts, print formats, notifications, permissions (incl. DB-only items not in the repo) |

**Two ways to navigate:**
- **By feature** — chapters 2–8 explain each mechanism (approvals, VAT, CBMS…).
- **By doctype** — [chapter 13](technical/13-per-doctype-reference.md) lists,
  per doctype, everything done to it. [Chapter 10 (File Index)](technical/10-file-index.md)
  does the same for source files ("where is X and why").

## User guide

| # | Chapter | Audience |
|---|---------|----------|
| 1 | [Overview](user_guide/01-overview.md) | everyone |
| 2 | [Approvals](user_guide/02-approvals.md) | requesters & approvers |
| 3 | [Attendance & HR](user_guide/03-attendance-hr.md) | HR |
| 4 | [Buying, Selling & VAT](user_guide/04-buying-selling-vat.md) | accounts, purchase, sales |
| 5 | [CBMS / IRD e-Billing](user_guide/05-cbms-billing.md) | accounts |
| 6 | [Document Generator](user_guide/06-document-generator.md) | accounts/admin |
| 7 | [Reports](user_guide/07-reports.md) | all report users |
| 8 | [Administrator Setup](user_guide/08-admin-setup.md) | System Managers |

## Other documents in this folder

Feature/change docs kept for depth and history (the technical chapters link to
them where relevant):

- `Documentation of avinash group.md` — earlier developer overview (reports +
  customizations); still a good quick reference, superseded where it conflicts
- `stock_ledger_guide.md` — how ERPNext's stock ledger engine works (context
  for Stock Adjustment / revaluation)
- `sales_stock_ledger_fixes.md` — Sales Stock Ledger fix history
- `vehicle_expense_report.md` — Vehicle Expense report spec & status
- `user_daily_entry_summary.md` — full feature doc for the daily entry summary
- `customer supplier item duplicate checks and default accounts.md` — the
  master-form client helpers
- `product wise invoice customer portal.md` — the customer portal feature doc
- `migrate_from_biometric_and_nepal_hrms.md` — historical app-consolidation
  runbook (endpoints therein are legacy)
- `db-master-slave-replication.md` — database replication ops runbook
- ⚠️ `dynamic_approval_guide.md`, `dynamic_approval_workflow.md`,
  `dynamic_workflow.md` — **stale** in places; read
  [technical/02-dynamic-approval.md](technical/02-dynamic-approval.md) §9
  before trusting them

## Bridge (separate component)

- `../k40_bridge/README.md` and `../k40_bridge/SETUP.md` — the Windows K40
  Bridge install & configuration runbooks.
