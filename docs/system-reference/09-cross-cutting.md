# 09 · Cross-cutting concerns

The machinery that is not one pipeline stage but can change, block or hide any HR/payroll document: approval workflow, naming and fiscal-year rules, the audit layer, list filtering, the read replica, scheduled jobs, permissions, SMS, the HR dashboard, and the tests.

Values marked "avinas1" were read from the database or `sites/avinas1/site_config.json` on 2026-10-12.

## Contents

1. [Dynamic Approval on HR documents](#1-dynamic-approval-on-hr-documents)
2. [Naming series and the Fiscal Year rule](#2-naming-series-and-the-fiscal-year-rule)
3. [The audit layer: who, company lock, company matching, track changes](#3-the-audit-layer)
4. [Fiscal-year access filter and Company Filter Config](#4-fiscal-year-access-filter-and-company-filter-config)
5. [Scheduler jobs](#5-scheduler-jobs)
6. [The read replica](#6-the-read-replica)
7. [Permissions and whitelisted methods](#7-permissions-and-whitelisted-methods)
8. [Sparrow SMS](#8-sparrow-sms)
9. [HR dashboard, HR workspace, report helpers](#9-hr-dashboard-hr-workspace-report-helpers)
10. [Tests and check scripts](#10-tests-and-check-scripts)

---

## 1. Dynamic Approval on HR documents

| | |
|---|---|
| **What** | A generic, data-driven multi-level approval: a **Dynamic Approval Setting** per (doctype, company, criteria) lists approvers by level; `setup_workflow` adds hidden fields (`custom_current_approver`, `custom_total_approval_levels`, `custom_current_approval_level`, `custom_approval_approvers`, …) and builds a Frappe **Workflow** named `… Approval Workflow` whose conditions compare those fields with the session user. |
| **Why** | One approval engine for every doctype, configured per company, instead of per-doctype workflows. For HR, it replaces HRMS's native `leave_approver`: patch leave_application_dynamic_approval [`execute`](../../avinashgroup_app/patches/leave_application_dynamic_approval.py#L20) hides `leave_approver` / `leave_approver_name` and sets HR Settings `leave_approver_mandatory_in_leave_application = 0` ("Leave Application is governed by the Dynamic Approval workflow"). |
| **Where** | Hooks on **every** doctype ("*"): [`validate`](../../avinashgroup_app/hooks.py#L478), [`before_save`](../../avinashgroup_app/hooks.py#L494), [`on_update`](../../avinashgroup_app/hooks.py#L495), [`before_workflow_action`](../../avinashgroup_app/hooks.py#L496). Code: [`_is_managed_doctype`](../../avinashgroup_app/custom_code/dynamic_approval.py#L44) (the gate), [`_get_config_for_doc`](../../avinashgroup_app/custom_code/dynamic_approval.py#L73), [`validate`](../../avinashgroup_app/custom_code/dynamic_approval.py#L250) (only the current approver may save while Pending; approved levels are frozen), [`before_workflow_action`](../../avinashgroup_app/custom_code/dynamic_approval.py#L366), [`on_update`](../../avinashgroup_app/custom_code/dynamic_approval.py#L501) (notifications), [`setup_workflow`](../../avinashgroup_app/custom_code/dynamic_approval.py#L1137) (System Manager only), [`_create_or_update_workflow`](../../avinashgroup_app/custom_code/dynamic_approval.py#L1322). Admin bypass of workflow role checks: [`BYPASS_WORKFLOW_NAMES`](../../avinashgroup_app/custom_code/workflow_admin_bypass.py#L7), [`get_transitions`](../../avinashgroup_app/custom_code/workflow_admin_bypass.py#L28), [`apply_workflow`](../../avinashgroup_app/custom_code/workflow_admin_bypass.py#L68), registered as [`workflow_admin_bypass.get_transitions`](../../avinashgroup_app/hooks.py#L615). Client: `approval_workflow_auto.js`, `approval_field_visibility.js` (global, `app_include_js`). |
| **Stock** | Frappe Workflow; HRMS's own leave approver (`Employee.leave_approver`, Department approvers) and the rule that a Leave Application must be Approved/Rejected before submit. |
| **HR bridge** | For a doctype whose `status` select has Approved/Rejected (Leave Application), the generated workflow also sets `status` when the workflow state reaches Approved/Rejected ([`bridge_status`](../../avinashgroup_app/custom_code/dynamic_approval.py#L1372)), so HRMS's submit check passes. |
| **Reads / Writes** | Dynamic Approval Setting (+ approvers, match criteria); writes the hidden fields, `Dynamic Approval History`, emails from the four Email Templates shipped as fixtures. |
| **Impacts downstream** | A Leave Application under approval stays `Open`/draft until the last level approves; Attendance is set `On Leave` only from a **submitted, Approved** leave ([02-checkin-to-attendance.md](02-checkin-to-attendance.md)); LWP leave cuts payment days on the slip ([06-salary-slip.md](06-salary-slip.md)). A leave stuck in approval at payroll time is simply not on the slip. |

### Config on avinas1 (2026-10-12)

| Item | Value |
|---|---|
| Dynamic Approval Settings | `Leave Application` for **NGI only**; `Purchase Order` for NGG, NGI, NGK, NGN, GLMI |
| Workflow records | **0** (`tabWorkflow` is empty) |
| `custom_current_approver` field on any doctype | **none** (no Custom Field, no DocField) |
| HR Settings `leave_approver_mandatory_in_leave_application` | 0 |
| Leave Applications | 2 |

**Consequence:** the gate `_is_managed_doctype` is false for every doctype, so **Dynamic Approval does nothing on avinas1 today**, not even for the NGI Leave Application setting. Leave Applications follow stock HRMS: whoever has write permission sets Status = Approved and submits. The native leave approver fields are hidden by the patch, so nothing routes a leave to a manager. Running `setup_workflow` for the setting would switch it on. (Doc-vs-DB: project notes describe a regenerated PO workflow on avinas1; it is not present now.)

### Gotchas

- Admin overrides in the workflow conditions are for **Administrator** only. A "System Manager may approve any Pending document silently" rule is described in project notes, but the develop code contains no such branch (only `frappe.session.user == "Administrator"` checks, e.g. in [`is_current_approver`](../../avinashgroup_app/custom_code/dynamic_approval.py#L1484)). Unverified whether it lives elsewhere.
- No-match / auto-approve path: a submitted document whose setting matches no criteria is "Auto-approved (no matching approval rule)"; project notes record that this path crashes with "Illegal Document Status" (unverified on HR doctypes).
- None of our own HR doctypes (Salary Revision, Payroll Adjustment, Overtime Sheet, Attendance Fix) has a setting; their approval is the Submit permission (section 7).

---

## 2. Naming series and the Fiscal Year rule

Two numbering systems run on HR documents.

### 2.1 The audited-doctype naming (`NAMING_CONFIG`)

| | |
|---|---|
| **What** | For every doctype in the audit list (section 3) that also appears in [`NAMING_CONFIG`](../../avinashgroup_app/custom_code/Override/naming_series.py#L17), the name is `<ABBR>-<PREFIX>-<FY>-<#####>` (or `<ABBR>-<PREFIX>-<#####>` without a fiscal year). |
| **Where** | `autoname` → [`naming_series_autoname`](../../avinashgroup_app/custom_code/Override/naming_series.py#L2941) → [`make_name_with_fiscal_year`](../../avinashgroup_app/custom_code/Override/naming_series.py#L627); `before_insert` → [`naming_requirements_before_insert`](../../avinashgroup_app/custom_code/Override/naming_series.py#L1810), which **throws "Missing Fiscal Year"** when no Fiscal Year row spans the document's date ([`get_fiscal_year_from_date`](../../avinashgroup_app/custom_code/Override/naming_series.py#L554)). Wired by [`AuditEventMapper`](../../avinashgroup_app/hooks.py#L259). |
| **Date used** | The first of `posting_date`, `transaction_date`, `attendance_date`, `custom_created_on` the document has. |

HR doctypes affected (prefix; fiscal year?):

| Doctype | Prefix | FY in name | Date the FY lookup uses | Example |
|---|---|---|---|---|
| Attendance | ATT | yes | `attendance_date` | `NGI-ATT-83/84-00001` |
| Salary Slip | SAL | yes | `posting_date` | |
| Payroll Entry | PAYR | yes | `posting_date` | `NGI-PAYR-83/84-00001` (avinas1) |
| Leave Application | LEAVE | yes | `posting_date` | |
| Leave Allocation | HR-LAL | yes | `custom_created_on` (the audit stamp) | |
| Employee Advance | EADV | yes | `posting_date` | |
| Expense Claim | EC.Type | yes | `posting_date` | |
| Employee | EMP | no | — | `NGI-EMP-00015` |
| Salary Structure | SAL-STR | no | — | (structures on avinas1 are named by hand, e.g. `NGI Staff 83/84`) |
| Holiday List, Designation, Shift Type | Holiday, DESIG, SHIFT | no | — | |

Not in the list, so stock naming: Employee Checkin, Additional Salary, Salary Structure Assignment, Shift Assignment, Shift Request, Compensatory Leave Request, Leave Policy Assignment. Our own doctypes use their own series (`SREV-.YYYY.-`, `PADJ-.YYYY.-`, …). Overtime Sheet is audited but has no `NAMING_CONFIG` entry.

**Why it matters for HR — the year-end trap.** The FY lookup throws when the date has no Fiscal Year. On the first day of a new BS year without the Fiscal Year record:

- every **Attendance** insert fails, including those made by HRMS auto attendance, self-heal and Attendance Fix — the punches stay unlinked;
- **Leave Allocation** made by `setup_year` fails unless an audit user is set ([`setup_year`](../../avinashgroup_app/hr/year_setup.py#L65) sets `frappe.flags.audit_user` for exactly this reason: run from bench there is no request, so `custom_created_on` was blank and "the numbering rule … refuses every one");
- the first **Payroll Entry** / **Salary Slip** of the year cannot be saved.

On avinas1 the latest Fiscal Year is **83/84** (ends 2027-07-16); 84/85 must exist, with all seven company rows, before 2027-07-17 (CLAUDE.md; [user-guide 8.7](../user-guide/08-raises-advances-bonuses-year-end.md) step 1).

### 2.2 The Numbering Configuration engine

Rule-driven document numbers on any doctype ([`apply_engine_numbering`](../../avinashgroup_app/custom_code/Override/naming_series.py#L2913), wildcard hooks [`apply_engine_numbering`](../../avinashgroup_app/hooks.py#L427)). Doctypes without an enabled rule exit through a cached gate. On avinas1 the enabled rules cover Journal Entry, Payment Entry, Purchase Invoice, Purchase Receipt and Sales Invoice only — **no HR doctype**. Indirect HR effect: the payroll accrual and bank journals are Journal Entries; [`default_jv_type`](../../avinashgroup_app/hooks.py#L325) gives them a JV Type before the numbering reads it ([07-after-the-slip.md](07-after-the-slip.md)).

---

## 3. The audit layer

[`AuditBase`](../../avinashgroup_app/utils/audit_file_manager.py#L9) lists the audited doctypes; [`AuditEventMapper`](../../avinashgroup_app/hooks.py#L259) registers five handlers on each. HR doctypes in the list: Attendance, Employee, Employee Advance, Expense Claim, [`Overtime Sheet`](../../avinashgroup_app/utils/audit_file_manager.py#L31), Holiday List, Leave Application, Leave Allocation, Payroll Entry, [`Salary Slip`](../../avinashgroup_app/utils/audit_file_manager.py#L67), Salary Structure, Shift Type, Designation, Appointment Letter, Interview, Job Applicant, Job Offer, Training Event.

| Event | Handler | Effect on HR documents |
|---|---|---|
| `before_insert` | [`before_insert`](../../avinashgroup_app/utils/audit_file_manager.py#L587) | Stamps `custom_created_by` / `custom_created_on` ([`set_audit_fields`](../../avinashgroup_app/utils/audit_file_manager.py#L552): the session user in a request, else `frappe.flags.audit_user`, else nothing) and runs the Fiscal Year check above |
| `before_save` | `before_save` | `custom_modified_by`; numbering helpers |
| `validate` | [`validate`](../../avinashgroup_app/utils/audit_file_manager.py#L582) | **Company lock** (company cannot change after naming), **company matching** (every Link listed in Company Filter Config must belong to the document's company, [`validate_company_matching`](../../avinashgroup_app/custom_code/globalfilter/globalfilter.py#L504)), document-number checks |
| `autoname` | [`autoname`](../../avinashgroup_app/utils/audit_file_manager.py#L595) | Name as in 2.1 |
| `after_delete` | `after_delete` | Steps the series back if the deleted document held the last number |

Background jobs (Attendance Fix, self-heal) run as Administrator without a request; they set `frappe.flags.audit_user` to record who triggered them.

**Track changes** (field-level Version history, read by the User Audit Trail report): turned on for every audited doctype by [`execute`](../../avinashgroup_app/patches/enable_track_changes_audited_doctypes.py#L25). On avinas1 it is on for Attendance, Attendance Fix, Employee, Employee Checkin, Additional Salary, Income Tax Slab, Leave Application, Overtime Sheet, Payroll Adjustment, Payroll Entry, Payroll Settings, Salary Revision, Salary Slip, Salary Structure, Salary Structure Assignment, Shift Type — and **off for Salary Component**. A change to a component's rate basis, multiplier, condition or accounts (the settings behind tea, meal, OT and late fine) leaves no Version record.

---

## 4. Fiscal-year access filter and Company Filter Config

### 4.1 Fiscal Year Access Control

| | |
|---|---|
| **What** | Per-user restriction of list views and document access to chosen fiscal years, per doctype. |
| **Where** | [`FILTERED_DOCTYPES`](../../avinashgroup_app/custom_code/fiscal_year_filter.py#L8), [`DATE_FIELD_MAP`](../../avinashgroup_app/custom_code/fiscal_year_filter.py#L103), [`_build_query_conditions`](../../avinashgroup_app/custom_code/fiscal_year_filter.py#L445), [`has_fiscal_year_permission`](../../avinashgroup_app/custom_code/fiscal_year_filter.py#L500), [`filtered_get_list`](../../avinashgroup_app/custom_code/fiscal_year_filter.py#L562); hooks `permission_query_conditions` / `has_permission` built from the tuple ([`permission_query_conditions`](../../avinashgroup_app/hooks.py#L393), [`has_permission`](../../avinashgroup_app/hooks.py#L399)) and the `frappe.client.get_list` override ([`filtered_get_list`](../../avinashgroup_app/hooks.py#L617)). |
| **Who is exempt** | Administrator and every **System Manager** ([`_is_admin`](../../avinashgroup_app/custom_code/fiscal_year_filter.py#L87)). A user with no Fiscal Year Access Control record has full access. |
| **HR doctypes filtered (date field)** | Additional Salary (`from_date`), Attendance (`attendance_date`), Attendance Fix (`from_date`), Attendance Request, Employee Advance, Leave Allocation (`from_date`), Leave Application (`posting_date`), Leave Encashment, Leave Ledger Entry, Payroll Entry, Salary Slip (`posting_date`), Salary Structure Assignment (`from_date`), Shift Assignment (`start_date`), Shift Request, Gratuity, Full and Final Statement, Expense Claim, … |
| **Config on avinas1** | No Fiscal Year Access Control record exists, so nobody is restricted. 16 of 23 enabled desk users are System Managers. |

Gotchas (latent — they bite only once someone is restricted):

- **Additional Salary is filtered on `from_date`**, which is blank on every one-off row (the engine, Payroll Adjustment and arrears all use `payroll_date`). A restricted user's list would hide all of them (a SQL comparison with NULL is false; unverified in the UI).
- **Salary Structure Assignment and Shift Assignment are filtered on their start date.** An assignment that started in an earlier year but is still in force (e.g. every 83/84 assignment, read in 84/85 before a rollover) is invisible to a user restricted to the current year.
- Our Overtime Sheet, Salary Revision and Payroll Adjustment are not in the tuple: never filtered.

### 4.2 Company Filter Config

Data-driven rules (doctype **Company Filter Config** + **Company Filter Field**) that make every Link picker show only records of the document's company (client: `company_filter.js`, `global_filter.js`) and, on audited doctypes, refuse a saved link to another company's record (server: [`CompanyValidator`](../../avinashgroup_app/custom_code/globalfilter/globalfilter.py#L291) via the audit `validate`). Cache cleared on save ([`clear_filter_config_cache`](../../avinashgroup_app/hooks.py#L383)).

HR rows on avinas1 (doctype → checked fields): Additional Salary → employee, ref_docname, department; Attendance → employee, department, leave_application, shift, attendance_request; Attendance Fix → employee, shift_type; Department → leave_block_list, payroll_cost_center, parent_department; Employee → department, default_shift, designation, holiday_list, branch, reports_to, payroll_cost_center, …; Employee Advance → employee, mode_of_payment, advance_account, department; Employee Checkin → employee, shift, attendance; Leave Allocation; Leave Application; Payroll Entry → employees, payroll_payable_account, payment_account, cost_center, bank_account, …; Salary Slip → employee, payroll_entry, earnings, deductions, journal_entry, salary_structure, …; Salary Structure → earnings, deductions, payment_account; Salary Structure Assignment → salary_structure, income_tax_slab, payroll_payable_account, payroll_cost_centers, employee, …; Shift Assignment → employee, shift_type, shift_request, …; Shift Type → holiday_list; Employee Tax Exemption Declaration → employee, payroll_period.

**Impact:** a Shift Type, Salary Structure, Income Tax Slab, holiday list or payable account of another company cannot be linked. That is the reason every company has its own Shift Types and structures ([01-masters.md](01-masters.md)). Salary Component is not company-scoped, so one component serves all seven companies, with per-company account rows.

---

## 5. Scheduler jobs

### 5.1 The scheduler is off on avinas1

System Settings `enable_scheduler = 0` on avinas1 (2026-10-12). Every `last_execution` in `tabScheduled Job Type` stops at **2026-07-17**; the jobs added since (the BS leave accrual, the holiday switch, replacement leave, overtime settlement, the daily digest) have **never run** here. Everything below describes what the job does when the scheduler runs (production); on avinas1 the work is done only by the buttons and hooks.

### 5.2 Inventory (HR/payroll-relevant)

| Job | App | Frequency | What it does | Stopped flag on avinas1 | Doc |
|---|---|---|---|---|---|
| [`check_bridge_heartbeats`](../../avinashgroup_app/biometric/heartbeat.py#L26) | ours | hourly | Emails when a K40 bridge stops pinging, and when it recovers | 0 | [02](02-checkin-to-attendance.md) |
| [`heal_unlinked_checkins`](../../avinashgroup_app/biometric/attendance_self_heal.py#L58) | ours | daily_long | Re-marks days with unlinked punches (last 45 days) on shifts with auto attendance | 0 | [02](02-checkin-to-attendance.md) |
| [`send_daily_attendance_digest`](../../avinashgroup_app/biometric/daily_digest.py#L76) | ours | cron `10 13 * * *` | Midday missed-punch / not-seen digest per company; :10 so it runs after HRMS's :00 auto attendance | 0 | [02](02-checkin-to-attendance.md) |
| [`allocate_earned_leaves_bs`](../../avinashgroup_app/hr/utils.py#L81) | ours | daily_long | Earned leave credited on BS month ends (replaces the stock job) | 0 | [01](01-masters.md) |
| [`switch_to_current_year_lists`](../../avinashgroup_app/hr/holiday_year_switch.py#L30) | ours | daily_long | On the year's first day, repoints companies and women to the new year's holiday lists | 0 | [01](01-masters.md) |
| [`grant_pending`](../../avinashgroup_app/hr/replacement_leave.py#L68) | ours | daily_long | Credits replacement leave for holiday work once attendance exists | 0 | [04](04-overtime.md) |
| [`measure_pending`](../../avinashgroup_app/hr/overtime_settlement.py#L200) | ours | daily_long | Measures OT rows whose attendance arrived after the sheet was submitted (last 62 days) | 0 | [04](04-overtime.md) |
| `process_auto_attendance_for_all_shifts` | hrms | hourly_long | Auto attendance from checkins, on shifts with *Enable Auto Attendance* | 0 | [02](02-checkin-to-attendance.md) |
| `update_last_sync_of_checkin` | hrms | hourly_long | Moves each shift's Last Sync of Checkin | 0 | [02](02-checkin-to-attendance.md) |
| `process_auto_shift_creation` | hrms | hourly_long | Shift Schedule Assignment → Shift Assignments | 0 | — |
| [`allocate_earned_leaves`](../../../hrms/hrms/hr/utils.py#L341) | hrms | daily_long | Stock earned-leave accrual on Gregorian months | **1 (stopped)** by [`execute`](../../avinashgroup_app/patches/setup_bs_leave_accrual.py#L22) — both running would credit twice | [01](01-masters.md) |
| `process_expired_allocation` | hrms | daily_long | Expires leave allocations at their end date | 0 | — |
| [`generate_leave_encashment`](../../../hrms/hrms/hr/utils.py#L317) | hrms | daily_long | Draft Leave Encashment on allocation expiry — **no-op**: HR Settings `auto_leave_encashment = 0` | 0 | [08](08-changes-over-time.md#8-joiners-leavers-final-settlement-leave-encashment) |
| birthday / anniversary / reminders, interview, job opening, daily work summary | hrms | various | Notifications; no pay effect | 0 | — |
| `process_nepali_deferred_revenue_via_hook` | rdp_common_app | daily | Deferred revenue on BS months — **not HR** | 0 | — |

Registrations: [`scheduler_events`](../../avinashgroup_app/hooks.py#L522) in our hooks.py; HRMS's in `hrms/hooks.py` `scheduler_events`.

Gotchas:

- With the scheduler off, the BS earned-leave balance on avinas1 does not grow by itself; the holiday switch will not happen on 1 Shrawan 2084; late-arriving OT rows stay at 0 hours until someone presses **Measure from Attendance**.
- The [`On a fiscal year's first day`](../../avinashgroup_app/hr/holiday_year_switch.py#L1) module notes of `hr/holiday_year_switch.py` say it is scheduled `daily`; it is registered under `daily_long` (same day, long queue). Cosmetic.
- Prepare Payroll Inputs is **not** scheduled. Nothing posts tea, meal, OT, late fine or advance instalments until HR presses the button ([05-payroll-entry.md](05-payroll-entry.md)).

---

## 6. The read replica

| | |
|---|---|
| **What** | A MariaDB replica on `127.0.0.1:3307`. With `read_from_replica: 1`, Frappe routes every function decorated `@frappe.read_only()` to it: Script/Query Report runs (`frappe.desk.query_report.run`, `generate_report_result`) and list views (`frappe.desk.reportview.get`, `get_count`, …). Writes always go to the master on `:3306`. |
| **Why** | Heavy reports (Cash Flow, GL, salary statement) do not load the master. |
| **HR reports that read it when on** | Every Script Report: Avinas Salary Statement, Salary Tax and SSF Deposit, Monthly Attendance BS, Work On Holiday BS, Yearly Leave Details BS, the attendance summary; and every HR list view. The HR dashboard (`get_dashboard`) and document forms are **not** `read_only` and always read the master. |
| **Config on avinas1** | `read_from_replica: 0`, `replica_host 127.0.0.1`, `replica_db_port 3307`. Set to 0 on 2026-10-08 because the replica had been stuck since 2026-09-29 and needs `sudo` to re-seed ([hr-handoff-2026-10-08.md §3](../hr-handoff-2026-10-08.md)). |

Consequences when it is on:

- **Replication lag after a write burst.** Right after Prepare Payroll Inputs (dozens of Additional Salary submits and slip re-saves) or a Payroll Entry submit, the Salary Statement and Deposit reports can show the previous figures until the replica catches up. Re-run the report; open the slip itself to see the truth.
- **A stuck replica is silent.** Lists then show stale rows, and a column added by a patch since the replica stopped appears "unknown" in list views while forms work (handoff §5).
- Doc drift: CLAUDE.md says `read_from_replica: 1` and points to `docs/db-master-slave-replication.md`; the flag is 0 and that runbook is no longer in `docs/` (removed in commit `601b374c`, "removed docs").

---

## 7. Permissions and whitelisted methods

### 7.1 Who can do what (DocPerm on avinas1)

| Doctype | HR Manager | HR User | Others |
|---|---|---|---|
| Salary Revision | all incl. submit/cancel | — | System Manager all |
| Payroll Adjustment | all | — | System Manager all |
| Overtime Sheet | all incl. submit/cancel | read/write/create, **no submit** | System Manager all |
| Attendance Fix | all | read | System Manager all |
| Employee Category, Holiday Bulk Update, Biometric Device | read/write/create | read | System Manager |
| Payroll Entry | all | — | — |
| Salary Slip | all | submit, no cancel | Employee / Employee Self Service: read (own, via HRMS user permission) |
| Salary Structure Assignment | all | submit, no cancel | System Manager read/write/create |
| Additional Salary | (Custom DocPerm) | read/write/create/submit | System Manager all |
| Leave Application | full | full | Leave Approver write/submit; Employee and Employee Self Service create; All read |

Enabled users with each role on avinas1: HR Manager 17, HR User 17, Leave Approver 16, System Manager 17 (16 of the 23 enabled desk users are System Managers), so in practice almost everyone can do everything.

### 7.2 Whitelisted methods and their checks

| Method | Check | Note |
|---|---|---|
| [`trigger_for_payroll_entry`](../../avinashgroup_app/payroll/attendance_allowance.py#L62) (Prepare Payroll Inputs) | Read on the Payroll Entry **and** create on Additional Salary (since 2026-10-12) | The writes still use `ignore_permissions`; the check is on the caller. The button shows only to users who can create Additional Salary |
| [`recompute_holiday_flags`](../../avinashgroup_app/payroll/attendance_allowance.py#L504) | Write on Attendance (since 2026-10-12) | Rewrites `custom_worked_on_holiday` on every Attendance row when called without dates |
| [`measure`](../../avinashgroup_app/hr/overtime_settlement.py#L126) | Overtime Sheet write | |
| [`repair_attendance_day`](../../avinashgroup_app/avinash_group_app/doctype/attendance_fix/attendance_fix.py#L524) | `only_for(HR Manager, System Manager)` | |
| [`get_rate_for_assignment`](../../avinashgroup_app/payroll/allowance.py#L209) | Salary Structure read | |
| [`get_structure_allowances`](../../avinashgroup_app/payroll/allowance.py#L219) | Salary Structure read | |
| `shift_rotation.rotate` / `set_periods` | Shift Assignment create/submit(/cancel) | |
| [`get_dashboard`](../../avinashgroup_app/hr/hr_dashboard.py#L75), [`get_menu`](../../avinashgroup_app/hr/hr_dashboard.py#L709) | `only_for(HR Manager, HR User, System Manager)`; pay blocks need Salary Slip read | |
| `SalaryRevision.get_employees` | doc method: needs write on the Salary Revision | |
| `biometric.api.receive_attendance`, `heartbeat.ping`, `bridge_commands.*` | Device must be a known, enabled Biometric Device ([02](02-checkin-to-attendance.md)) | Called by the bridge with an API key |

---

## 8. Sparrow SMS

Wildcard hooks on every doctype ([`on_submit`](../../avinashgroup_app/hooks.py#L479) … [`on_update`](../../avinashgroup_app/hooks.py#L495)) look up **SMS Notification Rule** records through a cached gate ([`_configured_doctypes`](../../avinashgroup_app/sparrow_sms/sms_dispatch.py#L262)). On avinas1 there are **no rules**, so no HR event sends an SMS (e.g. no "salary slip submitted" SMS). Adding a rule for Salary Slip / Leave Application is data, not code.

---

## 9. HR dashboard, HR workspace, report helpers

| Piece | What | Where |
|---|---|---|
| HR Dashboard page | One BS month for one company (or all): headcount, attendance, today, **month close** (attendance → overtime → payroll entry → slips → journal → paid), **statutory deposits** (TDS within 25 days, SSF within 15 days of the next BS month, from `Income Tax` and `SSF` deduction totals), Dashain deadline, decisions due (probation, contract, retirement), people away, **setup gaps** (no device ID, no default shift, no category, no payroll cost centre, joining date = birth date, no salary assignment), upcoming dates, devices. Read-only; figures computed the same way as the owning report | [`get_dashboard`](../../avinashgroup_app/hr/hr_dashboard.py#L75), [`_month_close`](../../avinashgroup_app/hr/hr_dashboard.py#L310), [`STATUTORY_DEPOSITS`](../../avinashgroup_app/hr/hr_dashboard.py#L52), [`SETUP_GAPS`](../../avinashgroup_app/hr/hr_dashboard.py#L506), page `avinash_group_app/page/hr_dashboard/`; commits `42ee34a`, `6bd993a` (2026-09-24) |
| HR workspace injection | Places the dashboard above HRMS's stock **HR** workspace after each render, without editing the HRMS workspace JSON (which developer mode would write into `apps/hrms`); hides HRMS's onboarding widget there | [`ROLES`](../../avinashgroup_app/public/js/hr_workspace.js#L16), [`place`](../../avinashgroup_app/public/js/hr_workspace.js#L31); loaded by [`hr_workspace.js`](../../avinashgroup_app/hooks.py#L77) |
| Report cell helper | `NepalHR.employeeCell`: name over ID in one clickable cell, shared by Monthly Attendance BS, Yearly Leave Details BS, Work On Holiday BS | [`employeeCell`](../../avinashgroup_app/public/js/hr_report_common.js#L73); loaded by [`hr_report_common.js`](../../avinashgroup_app/hooks.py#L41) |

Dashboard gotchas: the month-close "Journal" step counts any submitted non-Bank-Entry journal referencing the Payroll Entry and "Paid" any Bank Entry; it lists only companies with at least one salary assignment (GLMI, GEPL and SGU have none). The statutory block reads the `SSF` deduction as the full 31 % (employee 11 % + employer 20 % added as `SSF Addition`).

---

## 10. Tests and check scripts

Run from the bench root (`allow_tests` is on for avinas1). Suites marked "site data" run against avinas1's own records and skip a case whose data is missing; they are not hermetic.

| Suite | Covers | Run |
|---|---|---|
| [`TestAttendancePipeline`](../../avinashgroup_app/biometric/test_attendance_pipeline.py#L38) (12 tests) | Punch → employee by company device ID; IN/OUT alternation, last punch OUT; manual/edited/deleted checkins re-labelled; late punches refresh Present attendance (hook and self-heal paths); duplicate device ID refused; deviation fields and the late Half Day rule. Commits and cleans up after itself | `bench --site avinas1 run-tests --app avinashgroup_app --module avinashgroup_app.biometric.test_attendance_pipeline` |
| [`TestAllowance`](../../avinashgroup_app/payroll/test_allowance.py#L58) (25 tests) | Allowance kinds, structure Allowance Rates and the revision-only rule, assignment rows, fixed allowances on the slip (rate, % of Initial Basic, proration, tax projection), attendance allowances (row required, OT-eligible only, meal rule, previous month), journal by section | `… --module avinashgroup_app.payroll.test_allowance` |
| [`TestSheetMatching`](../../avinashgroup_app/payroll/test_payroll_checks.py#L25) and four more classes (7 tests, site data) | Guards from the October 2026 audit: sheet import matches by name, default payroll month, Make Bank Entry refuses a non-bank account, missing-attendance warning, section/account clash | `… --module avinashgroup_app.payroll.test_payroll_checks` |
| [`TestWomensRebate`](../../avinashgroup_app/payroll/test_tax_relief.py#L43), [`TestExemptionCaps`](../../avinashgroup_app/payroll/test_tax_relief.py#L95) (5 tests, site data) | Women's rebate and the retirement-contribution cap through every slip validate hook | `… --module avinashgroup_app.payroll.test_tax_relief` |
| [`TestBSCalendar`](../../avinashgroup_app/hr/test_bs_calendar.py#L38), [`TestPayrollEntryByMonth`](../../avinashgroup_app/hr/test_bs_calendar.py#L89) (6 tests) | FY month → dates, Nepal BS Period override, the slip's rule agreeing with the month lookup, default month, Payroll Entry from company + FY + month | `… --module avinashgroup_app.hr.test_bs_calendar` |
| [`TestShiftRotation`](../../avinashgroup_app/hr/test_shift_rotation.py#L42) (23 tests) | Rotational shift moves, bounded periods, refusals (paid months, fixed days), re-marking lived days; fully rolled back | `… --module avinashgroup_app.hr.test_shift_rotation` |
| rdp_common_app `test_bs_salary_slip.py` (5 tests) | The BS Salary Slip class (not ours; listed because our slips depend on it) | `bench --site avinas1 run-tests --app rdp_common_app --module rdp_common_app.nepal_hrms_common.tests.test_bs_salary_slip` |

Rolled-back check scripts in `avinashgroup_app/scripts/`: `check_payroll_bs_guards.py`, `check_year_rollover.py`, `check_leave_backfill_bs.py` (stub commits, roll back). **They hard-code `sites_path="/home/sijan/frappe-15/sites"`** (another developer's bench), so on this machine they need the path changed to `/home/dell/frappe-v15/sites` and must be run from `sites/` with `/home/dell/frappe-v15/env/bin/python` (CLAUDE.md explains the cwd rule).

Not covered by any test: Salary Revision arrears amounts, Payroll Adjustment, advance recovery, holiday backdate follow-up, Dynamic Approval on HR doctypes, the fiscal-year filter on HR doctypes.

See [impact-matrix.md](impact-matrix.md) and [hooks-inventory.md](hooks-inventory.md).
