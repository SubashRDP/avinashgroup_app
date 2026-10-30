# Payroll: complete reference

For the developer who maintains payroll in `avinashgroup_app`. It covers how every amount on a salary slip is worked out and adjusted, where the code is, and in what order it runs, from opening a Payroll Entry to the bank entry.

**Ground truth is the code.** Everything here was read from the code on `develop` at `202724b` (2026-10-28): this repo, `rdp_common_app`, and the installed `hrms` (15.59.0; see §1.4). Where the older docs disagree, the code wins, and §11 lists the disagreements. Anything not checked against code or data is marked **(unverified)**.

**References.** `path:line` paths are relative to this repo's root, e.g. `avinashgroup_app/payroll/payroll_entry.py:411`. Code in the other apps is written `hrms:…` (relative to `apps/hrms/hrms/`) or `rdp:…` (relative to `apps/rdp_common_app/rdp_common_app/`). Line numbers are for the commits above and will drift. Search for the function name if a line no longer matches.

**Numbers** use Nepali grouping (1,50,000; 19,54,000), as the other docs do.

**Where the data comes from.** `CLAUDE.md` names `avinas1` as the working site, but **`avinas1` does not exist on this machine.** This bench is `/home/frappe/frappe-bench`, not `/home/dell/frappe-v15`. Its Avinash sites are `avinasdemo.raindropinc.com` (the 7 companies, no payroll data), `sandboxavinas-demo.raindropinc.com` (also empty) and `demo-nggroup.raindropinc.com` (9 companies, 5 structures, 13 assignments, 35 Payroll Entries, 21 slips). Live figures in this document come from read-only `SELECT`s on **demo-nggroup** (labelled *demo*). Figures for avinas1 come from the 2026-10-12 snapshot in `docs/system-reference/01b-pay-masters.md`; they are labelled *avinas1 (docs)* and **were not re-verified**.

---

## Contents

1. [Architecture](#1-architecture)
2. [Execution trace](#2-execution-trace)
3. [Masters and data model](#3-masters-and-data-model)
4. [Every earning and deduction](#4-every-earning-and-deduction)
5. [Income tax in full](#5-income-tax-in-full)
6. [Accounting](#6-accounting)
7. [Company differences](#7-company-differences)
8. [Scheduled jobs, permissions, background behaviour](#8-scheduled-jobs-permissions-background-behaviour)
9. [Gotchas, silent failures, error messages](#9-gotchas-silent-failures-error-messages)
10. [Open questions and pending work](#10-open-questions-and-pending-work)
11. [Stale docs](#11-stale-docs)
12. [How to test](#12-how-to-test)

---

## 1. Architecture

### 1.1 Who owns what

| App | Owns | Payroll-relevant pieces |
|---|---|---|
| **hrms** 15.59.0 | The payroll engine | `SalarySlip` (structure formulas, proration, Additional Salary, the tax projection and slab), `PayrollEntry` (Get Employees, slip creation and submission, accrual JV, bank entry), Additional Salary, Leave Encashment, Employee Advance, Income Tax Slab, Payroll Period, Tax Exemption Declaration / Proof |
| **rdp_common_app** | Bikram Sambat months | `BSSalarySlip` (`rdp:nepal_hrms_common/payroll/salary_slip_bs.py:47`), the **only** Salary Slip class override; the **Nepal HRMS Settings** switch (`rdp:nepal_hrms_common/doctype/nepal_hrms_settings/nepal_hrms_settings.py:31`); `utils/bs_boundaries.py` (BS calendar); a Payroll Entry form script that sets BS dates (`rdp:public/js/payroll_entry.js`) |
| **avinashgroup_app** (this repo) | Everything company-specific | Payroll Entry class override; Salary Slip `doc_events` hooks (allowances, tax reliefs, tax override, payout slip, guards, daily breakdown); the attendance engine (tea, meals, OT, late fine); advances; Dashain; leave encashment; accounts by section; JV numbering; custom doctypes (Overtime Sheet, Payroll Adjustment, Salary Revision, Structure Allowance Rate, Assignment Allowance, Salary Slip Day) |

### 1.2 Class overrides (`override_doctype_class`)

| DocType | Class | Declared at |
|---|---|---|
| Salary Slip | `rdp_common_app.nepal_hrms_common.payroll.salary_slip_bs.BSSalarySlip` | `rdp:hooks.py:149` |
| Payroll Entry | `avinashgroup_app.payroll.payroll_entry.AvinashPayrollEntry` | `avinashgroup_app/hooks.py:574` |
| Leave Encashment | `avinashgroup_app.payroll.leave_encashment.SettlementLeaveEncashment` | `avinashgroup_app/hooks.py:572` |
| Compensatory Leave Request | `avinashgroup_app.hr.replacement_leave.ReplacementLeaveRequest` | `avinashgroup_app/hooks.py:577` |

Checked at runtime on demo: `get_controller("Salary Slip")` is `BSSalarySlip(hrms SalarySlip)`, and Payroll Entry is `AvinashPayrollEntry(hrms PayrollEntry)`.

### 1.3 Install order, and why it matters

On every Avinash site on this bench, the global `installed_apps` is

```
["frappe", "erpnext", "avinashgroup_app", "rdp_common_app", "hrms"]
```

(`tabDefaultValue`, `defkey='installed_apps'`; the same on avinasdemo, demo-nggroup and sandboxavinas-demo).

Three consequences:

1. **Only one Salary Slip class can win.** Frappe takes the last app's `override_doctype_class` entry. `rdp_common_app` comes after us, so a Salary Slip class in this app would be silently ignored. That is why everything this app does to a slip is a **`doc_events` hook**, not a subclass (stated at `avinashgroup_app/payroll/salary_slip.py:16` and `avinashgroup_app/payroll/tax_relief.py:40`).
2. **Hook order is app order, then `"*"`.** `Document.hook` (`frappe/model/document.py:1361`) runs the controller method first, then `doc_events[doctype][method]` in the order `get_doc_hooks()` merged them (our app before hrms), then `doc_events["*"][method]`. Within this app, the order is the order of the `_add_doc_event` calls in `hooks.py`, after the audit handlers that `AuditEventMapper.get_doc_events()` (`avinashgroup_app/utils/audit_file_manager.py:471`) registers first.
3. **A fresh site must install `rdp_common_app` and `hrms` before payroll runs.** Our code imports both at module load (`hrms.payroll…`, `rdp_common_app.utils.bs_boundaries`).

### 1.4 Versions

- `hrms/__init__.py` says **15.59.0**, not the 15.49.2 named in older docs. `tabInstalled Application` lists two rows for frappe and erpnext (15.72.3 / 15.80.0 and 15.66.0 / 15.78.1), so migrations have run across versions. `BSSalarySlip.get_working_days_details` copes with both signatures (`rdp:…/salary_slip_bs.py:122`).
- `nepali-datetime` **1.0.8.5** is installed. Commit `6d5e044` requires it: 1.0.8.4 had Ashwin 2083 one day short, so it ended on 16 Oct. With 1.0.8.5, Ashwin 2083 is **2026-09-17 → 2026-10-17** (31 days) and Kartik starts **2026-10-18** (checked with `get_salary_period` on demo). Entries and slips made before the upgrade still carry an Ashwin that ends 2026-10-16 (§9).

### 1.5 The BS engine switch

`is_bs_payroll_enabled(company)` (`rdp:…/nepal_hrms_settings.py:31`) is true when Nepal HRMS Settings has `process_payroll_in_nepali_month = 1`, and, while `restrict_to_nepal_companies` is on, the company's country is Nepal. When it is off, `BSSalarySlip` behaves exactly like stock HRMS and `bs_period_guard` does nothing.

- *avinas1 (docs)*: on. `hr/year_setup.py:201` `ensure_nepali_payroll` turns it on.
- *demo*: **off**. `tabSingles` has no Nepal HRMS Settings row, so `get_single_value` returns 0. That is why the demo slips show `total_working_days` = 26 (holidays excluded, Payroll Settings `include_holidays_in_total_working_days` = 0) rather than 31.

---

## 2. Execution trace

### 2.0 The whole month at a glance

```
Payroll Entry (new)  ──validate──►  fill_from_bs_month, Get Employees, warnings, BS guard
       │ Submit
       ▼
before_submit: check_ready_for_slips → HRMS: duplicate check, payable-account check, attendance check
on_submit (HRMS) → create_salary_slips (ours)
       ├─ check_ready_for_slips
       ├─ prepare_payroll_inputs("Slips created")
       │     tea / meal / OT / late fine → submitted Additional Salary   (attendance_allowance)
       │     advance instalments        → submitted Additional Salary   (advance_recovery)
       │     [Settle Leave] leave recovery → submitted Additional Salary (leave_encashment.recover_month)
       │     line in Payroll Inputs Log
       └─ HRMS create_salary_slips → one draft Salary Slip per employee (≤30 inline, >30 queued)
                 └─ Salary Slip validate chain (§2.3)
"Submit Salary Slip" button → submit_salary_slips (ours)
       ├─ check_ready_for_slips
       ├─ prepare_payroll_inputs("Slips submitted")  (re-posts, replacing the month's lines)
       ├─ refresh_draft_slips (re-save every draft)
       ├─ cap_recoveries → warn_shortfalls
       └─ HRMS submit_salary_slips → each slip.submit() → make_accrual_jv_entry (ours: by section)
                                                       → hr_journal.default_jv_type on the JE
"Make Bank Entry" → make_bank_entry (ours: account checks) → HRMS: draft Bank/Cash Entry
```

### 2.1 Opening and saving a Payroll Entry

| # | Trigger | Function | Reads | Writes | Throws / shows |
|---|---|---|---|---|---|
| 1 | Form `onload` | JS `avinashgroup_app/public/js/payroll_entry.js:214` → `default_month` `avinashgroup_app/payroll/payroll_month.py:121` | last non-cancelled Payroll Entry of the company; BS calendar (`hr/bs_calendar.py`) | sets Fiscal Year + Month (BS) on the form | — |
| 2 | Form `refresh` | JS `payroll_entry.js:243`: `lock_bs_dates` (posting/start/end/frequency read-only once the FY and month are chosen), `draw_month_calendar` → `month_calendar` `payroll_month.py:148` | the FY's 12 months and the entries already made for each | — | — |
| 2a | Form, `payroll_frequency` change | `rdp:public/js/payroll_entry.js` → `get_bs_period_for_date` (`rdp:…/nepal_bs_period.py:168`) | Nepal BS Period / calendar | start/end on the form, after a 600 ms delay | — The server overwrites these on save (#4), so the two scripts cannot leave the dates wrong |
| 3 | Save → `validate` | `AvinashPayrollEntry.validate` `avinashgroup_app/payroll/payroll_entry.py:321`, step 1: `check_payout` `payroll_entry.py:276` | `custom_payout_type`, `custom_pay_dashain`, `custom_festival_component`, `custom_bs_month` | A payout entry gets `validate_attendance` = 0, `custom_pay_dashain` / `custom_pay_leave_encashment` set to match the payout. A monthly entry gets `custom_pay_dashain` cleared | msgprint "Dashain not paid on the salary"; throws "… is not a festival allowance (tick Festival Allowance …)", "… is paid in …; this entry is for …. Change the month." |
| 4 | same | step 2: `fill_from_bs_month` `payroll_month.py:45` (drafts only) | `custom_fiscal_year`, `custom_bs_month` → `hr/bs_calendar.month_period`; Company defaults | `start_date`, `end_date`, `posting_date` (= month end), `payroll_frequency` = Monthly, `currency`, `exchange_rate` = 1, `payroll_payable_account` and `cost_center` if blank; the employee list when it is empty or the month changed (→ #6) | "Set Default Payroll Payable Account on Company …, or choose one on this entry." |
| 5 | same | step 3: HRMS `PayrollEntry.validate` `hrms:payroll/doctype/payroll_entry/payroll_entry.py:45` | — | `number_of_employees`, `status` | — |
| 6 | called from #4, or the Get Employees button | `AvinashPayrollEntry.fill_employee_details` `payroll_entry.py:371` | HRMS `get_salary_structure` / `get_filtered_employees` (the same query as HRMS); submitted slips of **the same kind** (`slip_kind_filter`, `avinashgroup_app/payroll/special_payout.py:81`) for these dates | `employees`, `number_of_employees`; HRMS's withheld-salary flags | Falls back to HRMS's own method when nobody is found, which throws "No employees found …" |
| 7 | same | step 4 (new entry or start date changed): `warn_missing_attendance` `payroll_month.py:77` (monthly only), `warn_missing_tax_history` `avinashgroup_app/payroll/income_tax.py:122` → `tax_history_gaps` `income_tax.py:61` | submitted Attendance in the month; Payroll Settings; earlier monthly slips this tax year; the assignment's `taxable_earnings_till_date` / `tax_deducted_till_date` | — | orange "Attendance missing", "Tax history missing" (warnings only) |
| 8 | `validate` hooks | `audit_file_manager.validate`; `bs_period_guard.validate_payroll_entry` `avinashgroup_app/payroll/bs_period_guard.py:45`; `hr.bs_dates.set_bs_dates` | the posting date's BS month (`hr/bs_calendar.month_of_date`) | the BS miti fields | "Posting date is in another BS month" (BS engine on only) |
| 9 | `"*"` validate hooks | `naming_series.apply_engine_numbering`, `dynamic_approval.validate`, `utils.bs_miti.set_mitis` | Numbering Configuration (`NGI-PAYR-83/84-…`) | name parts, mitis | naming throws if no Fiscal Year covers the date |

### 2.2 Submitting the Payroll Entry (which makes the slips)

Frappe's order on submit (`frappe/model/document.py:1120`): `before_validate` → `validate` (#3–#9 again; `fill_from_bs_month` and the warnings skip a docstatus-1 doc) → `before_submit` → DB write → `on_submit`.

| # | Trigger | Function | Reads | Writes | Throws |
|---|---|---|---|---|---|
| 10 | `before_submit` | `AvinashPayrollEntry.before_submit` `payroll_entry.py:330` → `check_ready_for_slips` `payroll_entry.py:213` | for each employee: a submitted Salary Structure Assignment with `from_date` ≤ the slip start (the month's first day, or the joining day if later); whether any enabled component has S/D or F/P accounts for the company (`has_section_accounts`, `avinashgroup_app/payroll/allowance.py:139`); the employee's Department → `custom_payroll_section` (`get_section`, `allowance.py:162`) | — | **"Payroll cannot run yet"**: "Nothing was posted. Fix these, or remove the people …", followed by one line per person ("salary assignment starts …; it must start on or before …", "no submitted salary assignment", "Department … has no Payroll Section", "no Department") |
| 11 | same | warnings again (#7), then HRMS `before_submit` `hrms:…/payroll_entry.py:58`: `validate_existing_salary_slips` (overridden, `payroll_entry.py:338`), `validate_payroll_payable_account`, unmarked attendance | non-cancelled slips for these dates **of the same kind**; the payable account's `account_type` | — | "Duplicate Entry: Salary Slip already exists for … for the given dates"; "Account type cannot be set for payroll payable account …"; "Cannot submit. Attendance is not marked for some employees." (only with Validate Attendance) |
| 12 | `on_submit` | HRMS `on_submit` `hrms:…/payroll_entry.py:64` | — | `status` = Submitted | — |
| 13 | → | `AvinashPayrollEntry.create_salary_slips` `payroll_entry.py:411`: `check_ready_for_slips` again, then `prepare_payroll_inputs(self, "Slips created")` `payroll_entry.py:50` | see #14–#16 | see #14–#16 | as #10 |
| 14 | → | **attendance lines**: `create_additional_salaries(entry, commit=False)` `avinashgroup_app/payroll/attendance_allowance.py:153` | enabled components with `custom_is_attendance_driven`; per employee: the assignment's Allowances, submitted Attendance in the period, Overtime Sheets, Employee ticks; skips anyone whose **monthly** slip covering the month end is already submitted (`paid_employees`, `attendance_allowance.py:242`) | For each (employee, component): deletes this source's earlier row for the same payroll date (`_delete_existing_draft` `attendance_allowance.py:792`, which also deletes the draft slip's line that links it, then cancels and deletes it), then inserts and **submits** a new Additional Salary (`_make_additional_salary` `attendance_allowance.py:829`) with `payroll_date` = month end, `custom_source` = "Nepal HRMS Attendance Allowance", `custom_quantity`, `custom_rate`, and `deduct_full_tax_on_selected_payroll_date` = 1 for earnings | Never throws. A failure rolls back to a per-row savepoint, is listed as "skipped", writes an Error Log titled "Nepal HRMS Attendance Allowance: <emp>/<component>", and shows an alert |
| 15 | → | **advances**: `post_recoveries(entry)` `avinashgroup_app/payroll/advance_recovery.py:67` | open Employee Advances with `repay_unclaimed_amount_from_salary`; `custom_monthly_instalment`, `custom_recover_from`; the relieving date | Cancels this month's earlier "Advance Recovery" rows (`clear_month` `advance_recovery.py:150`), then inserts and submits a `Salary Advance` deduction per advance (ref Employee Advance). **HRMS updates the advance's `return_amount` on Additional Salary submit** (`hrms:payroll/doctype/additional_salary/additional_salary.py:217`), i.e. now, before any slip is submitted | — (returns `[]` if the "Salary Advance" component does not exist) |
| 16 | → | **leave recovery**, only when the monthly entry has **Settle Leave** (`custom_pay_leave_encashment`) ticked: `_recover_leave` `payroll_entry.py:152` → `recover_month` `avinashgroup_app/payroll/leave_encashment.py:341` | due settlements (`due_encashments` `leave_encashment.py:210`: a relieving date in the month, or an allocation ending in it); `settlement_balance` `leave_encashment.py:413` | Clears and reposts a submitted "Leave Recovery" deduction per settlement whose balance is below zero | — (logs "not before …" if run before the month's first day) |
| 17 | → | `append_inputs_log` `payroll_entry.py:97` | — | `custom_payroll_inputs_log` via `db_set` (or a comment on an unmigrated site) | — |
| 18 | → | HRMS `create_salary_slips` `hrms:…/payroll_entry.py:218` | — | 30 employees or fewer: `create_salary_slips_for_employees` `hrms:…/payroll_entry.py:1462` inline. More than 30: `status` = Queued and the job is enqueued (§8.3) | Any exception: rollback, `log_payroll_failure` `hrms:…/payroll_entry.py:1441` → `status` = Failed, `error_message` set; the button "Create Salary Slips" retries |
| 19 | per employee | `frappe.get_doc({"doctype": "Salary Slip", …}).insert()` | the entry's dates, posting date, `payroll_entry` | a draft slip; see §2.3 | see §2.3 |

### 2.3 The Salary Slip validate chain, in exact order

Read from `frappe.get_doc_hooks()` on demo and from `hooks.py`. Every save and every submit runs it. On submit the slip's `docstatus` is already 1 while `validate` runs.

| Order | What runs | Where | Does |
|---|---|---|---|
| 0 | `before_insert` | `audit_file_manager.before_insert` | audit fields |
| 1 | `before_validate` hook | `special_payout.set_slip_payout_type` `special_payout.py:159` (hooked `hooks.py:374`) | Drafts made by an entry copy the entry's `custom_payout_type` (blank = monthly salary) |
| 2 | **controller** | `BSSalarySlip.validate` `rdp:…/salary_slip_bs.py:265` → **HRMS `SalarySlip.validate`** `hrms:payroll/doctype/salary_slip/salary_slip.py:152` | **HRMS core.** Salary withholding, status, active employee, `validate_dates`, `check_existing` (`:300`), `get_date_details` (BS override `rdp:…:60`: start/end from the posting date's BS month, or a Nepal BS Period record), working and payment days (BS override `rdp:…:122` → `get_bs_payment_days` `rdp:…:166`), `set_salary_structure_assignment`, **`calculate_net_pay`** (`hrms:…:826`: structure rows by formula, Additional Salary (`:1331`), tax components (`:1351`) → the tax projection (§5)), year-to-date figures, leave balances |
| 3 | validate hook | `audit_file_manager.validate` | audit |
| 4 | validate hook | `special_payout.build_payout_slip` `special_payout.py:166` (`hooks.py:375`) | **Payout slips only.** Adds the payout's Additional Salary rows, re-runs allowances and net pay so the slip is the merged month, computes the payout tax, then drops everything except the payout rows and the tax row. Throws "Nothing to pay: … has no … to be paid between … and …" |
| 5 | validate hook | `salary_slip.add_employee_allowances` `avinashgroup_app/payroll/salary_slip.py:33` (`hooks.py:381`) | **Monthly slips, drafts only.** Puts the assignment's Monthly and % of Initial Basic allowances on the slip with `update_component_row` (prorated), drops allowances no longer on the assignment, then calls HRMS `calculate_net_pay()` again. **HRMS core runs again here**, including the whole tax projection, now with the allowances in it |
| 6 | validate hook | `tax_relief.apply_tax_reliefs` `avinashgroup_app/payroll/tax_relief.py:77` (`hooks.py:388`) | Monthly slips. Recomputes the tax row with the retirement-cap excess and the women's rebate; does nothing if neither applies |
| 7 | validate hook | `income_tax.apply_income_tax_override` `avinashgroup_app/payroll/income_tax.py:156` (`hooks.py:390`) | Copies the tax row into `custom_income_tax_computed`; if `custom_override_income_tax` is ticked, replaces it with `custom_income_tax_override` and recomputes the net. Throws "No income tax Salary Component is set up, so it cannot be overridden." |
| 8 | validate hook | `bs_period_guard.validate_salary_slip` `bs_period_guard.py:70` (`hooks.py:399`) | Throws "Slip and payroll entry disagree on the month" when the slip's start ≠ the entry's start |
| 9 | validate hook | `daily_breakdown.build_daily_breakdown` `avinashgroup_app/payroll/daily_breakdown.py:64` (`hooks.py:402`) | Rebuilds `custom_daily_breakdown` (Salary Slip Day rows). Never throws; a failure goes to the Error Log. Empties the table on a payout slip |
| 10 | validate hook | `hr.bs_dates.set_bs_dates` (`hooks.py:485`) | BS miti fields. Note that this, not the daily breakdown, is the last of our Salary Slip hooks, despite the comment at `hooks.py:400` |
| 11 | `"*"` validate | ERPNext SLA and transaction-deletion checks, `naming_series.apply_engine_numbering`, `dynamic_approval.validate`, `utils.bs_miti.set_mitis` | numbering (`NGI-SAL-83/84-00001`), approval, mitis |
| 12 | `before_save` / `before_submit` | `audit_file_manager.before_save`; `"*"`: `naming_series`, `dynamic_approval.before_save` | — |
| 13 | `on_submit` (submit only) | HRMS `SalarySlip.on_submit` `hrms:…/salary_slip.py:207` | "Net Pay cannot be less than 0"; status; loan repayment; the email unless `via_payroll_entry`; marks a linked Leave Encashment Paid |

**Where HRMS core runs between ours:** at step 2 (the full HRMS validate), again inside step 4 (`calculate_net_pay` and `update_component_row` on a payout slip) and step 5 (`calculate_net_pay` on a monthly draft). Steps 6 and 7 work on the figures HRMS left on the document (`total_taxable_earnings…`, `remaining_sub_periods`, `previous_total_paid_taxes`).

**On submit, step 5 does nothing.** `apply_employee_allowances` returns at `docstatus != 0` (`salary_slip.py:48`). The allowance rows the draft already has stay as they are: HRMS's `calculate_component_amounts` (`hrms:…:1146`) adds and updates structure and Additional Salary rows, but does not delete rows it did not make. The tax HRMS recomputes at step 2 still sees them. See §9 for the payout-slip consequence.

### 2.4 Submit Salary Slip

| # | Trigger | Function | Reads | Writes | Throws |
|---|---|---|---|---|---|
| 20 | "Submit Salary Slip" button (HRMS form) | `AvinashPayrollEntry.submit_salary_slips` `payroll_entry.py:428` | — | — | — |
| 21 | → | `check_ready_for_slips` (#10) | | | "Payroll cannot run yet" |
| 22 | → | `prepare_payroll_inputs(self, "Slips submitted")` (#14–#17) | attendance and sheets **as they are now** | replaces the month's attendance lines and advance lines. The rows that draft slips link are deleted first | — |
| 23 | → | `refresh_draft_slips` `attendance_allowance.py:109` | every draft slip of the entry | `slip.save()` each, which runs §2.3 so the drafts pick up the new Additional Salary | anything §2.3 throws |
| 24 | → | `cap_recoveries` `avinashgroup_app/payroll/recovery_cap.py:33` → `cap_slip` `recovery_cap.py:45` (monthly entry only) | drafts with `net_pay` < 0; their deduction rows from "Leave Recovery" then "Advance Recovery" | `_reduce` `recovery_cap.py:82`: cancels the Additional Salary and posts a smaller copy (none at 0); re-saves the slip | — |
| 25 | → | `warn_shortfalls` `payroll_entry.py:196` | the cuts | log line "Recoveries cut to the pay" | msgprint "Collect Outside Payroll" |
| 26 | → | HRMS `submit_salary_slips` `hrms:…/payroll_entry.py:282` → `submit_salary_slips_for_employees` `:1544` (more than 30 slips: queued) | drafts of this entry with no `journal_entry` | each `slip.submit()` (§2.3 with docstatus 1). A slip with `net_pay` < 0, or one that raises `ValidationError`, is listed as unsubmitted and the rest go on | msg "Could not submit some Salary Slips: …" |
| 27 | → | HRMS `make_accrual_jv_entry` `hrms:…/payroll_entry.py:531` → **ours** `get_salary_component_total` `payroll_entry.py:468` → `section_for` `:516` → `get_account` `:525` | the submitted slips' Salary Detail rows; cost centres; Employee Advance refs | `component_dict` keyed by (component, cost centre, **section**) → account through `section_account` `allowance.py:130`, falling back to HRMS `get_salary_component_account` (`hrms:…:308`) | "Set Payroll Section on the Department of these employees, so their pay posts to the right account: …"; HRMS "Please set account in Salary Component …" |
| 28 | JE insert | `hr_journal.default_jv_type` `avinashgroup_app/payroll/hr_journal.py:30` (first `before_insert` of Journal Entry, `hooks.py:323`) | the JE's accounts reference a Payroll Entry or Employee Advance | `custom_p_type` = the voucher type (Journal Entry), and `custom_document_no` = the next number of a hand-numbered series, with `custom_document_no_manual` = 1 | — |
| 29 | → | HRMS `make_journal_entry` `hrms:…/payroll_entry.py:608` | — | the accrual JE, **submitted**; `journal_entry` set on the slips | any JE error, re-raised (whole submission rolls back, entry Failed) |
| 30 | → | HRMS emails the slips (`email_salary_slip`), `salary_slips_submitted` = 1 | Payroll Settings `email_salary_slip_to_employee` (1 on demo) | — | — |

### 2.5 Bank entry

| # | Trigger | Function | Reads | Writes | Throws |
|---|---|---|---|---|---|
| 31 | "Make Bank Entry" | `AvinashPayrollEntry.make_bank_entry` `payroll_entry.py:447` | the **saved** `payment_account` and its `account_type` | — | "Choose the Payment Account and press Update to save it, then make the bank entry."; "Payment Account … is a … account. Salary is paid from a Bank or Cash account." |
| 32 | → | HRMS `make_bank_entry` `hrms:…/payroll_entry.py:882` → `set_accounting_entries_for_bank_entry` `:1017` | submitted slips' earnings and deductions (net of statistical / tax-only components) | a **draft** Bank Entry (Cash Entry when the account is Cash): Cr payment account, Dr payroll payable with the Payroll Entry reference. `hr_journal.default_jv_type` sets JV Type = Bank Entry; the Bank Entry series numbers itself | — |

The accountant submits the bank entry by hand.

### 2.6 The separate Dashain / leave-encashment payout run

Since `c3a5585` (2026-10-26) both are paid by a **second Payroll Entry for the same month** with **Payout** (`custom_payout_type`) = "Dashain Allowance" or "Leave Encashment". The monthly entry never carries them.

| # | Trigger | Function | Does |
|---|---|---|---|
| P1 | Save | `check_payout` `payroll_entry.py:276` | `validate_attendance` = 0; Dashain: `custom_pay_dashain` = 1, the component must be ticked `custom_is_festival_allowance` and its Pay Month must match the entry's month. Encashment: `custom_pay_leave_encashment` = 1 |
| P2 | Get Employees | `fill_employee_details` `payroll_entry.py:371` | Leaves out only people already paid on a **payout slip of this kind** for these dates, so the salary slip does not hide them |
| P3 | Submit → `create_salary_slips` | `prepare_payroll_inputs` → `_pay_dashain` `payroll_entry.py:117` | `make_festival_adjustment` `avinashgroup_app/payroll/festival_allowance.py:244` builds (or rebuilds) the draft **Payroll Adjustment** (one row per person with Basic, service days and factor, §4.13), which is **submitted** here. Its `on_submit` (`avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py:83`) inserts and submits one Additional Salary per row (`deduct_full_tax_on_selected_payroll_date` = 1). The entry gets `custom_festival_adjustment` |
| P3′ | same, encashment | `_pay_leave_encashment` `payroll_entry.py:134` → `encash_month` `leave_encashment.py:270` | For each due settlement: deletes earlier drafts, inserts a Leave Encashment (priced by `price_encashment` `leave_encashment.py:116`), deletes it again if 0 days or 0 amount, and submits the rest. HRMS's on_submit writes the Additional Salary; `mark_additional_salary` (`leave_encashment.py:158`) sets full-tax and the source, `link_additional_salary` (`:172`) writes it back on the encashment. Does nothing before the month's first day |
| P4 | Additional Salary validate | `special_payout.tag_additional_salary` `special_payout.py:103` (`hooks.py:503`) | An earning that is a Leave Encashment's, or of a festival component, gets `custom_payout_type` and **`disabled` = 1**. HRMS's `get_additional_salaries` (`hrms:payroll/doctype/additional_salary/additional_salary.py:252`) only reads `disabled = 0`, so no monthly slip sees it. Throws "… is paid once, on its own payout; it cannot be recurring." |
| P5 | same | `drop_employees_not_due` `payroll_entry.py:168` | Deletes from the entry everyone with no submitted payout Additional Salary in the month (`employees_due` `special_payout.py:140`), and logs "Not due". Throws "Nothing to pay: Nobody on this entry has … to be paid between … and …" if nobody is left |
| P6 | HRMS makes the slips | Salary Slip §2.3 step 4 | `build_payout_slip` reduces each slip to the payout rows plus the tax row (§5.9) |
| P7 | Submit Salary Slip | `submit_salary_slips` | inputs re-run (already paid: nothing new), drafts refreshed, **no recovery cap** on a payout entry, then HRMS submits and posts the accrual JE: Dr the Dashain / encashment expense, Cr TDS, Cr payable |
| P8 | Bank entry | as #31–#32 | its own bank entry |

The two entries are independent. HRMS's `check_existing` (`hrms:…/salary_slip.py:300`) compares only slips **of the same Payroll Entry** when the slip has one, so the payout slip and the salary slip can share dates. Our duplicate check and Get Employees compare a slip only with slips of its own kind.

### 2.7 Cancel order

**Cancelling a submitted Payroll Entry** (HRMS `cancel` `hrms:…/payroll_entry.py:119`; queued when it has more than 50 slips):

1. `before_cancel`: nothing of ours.
2. HRMS `on_cancel` (`:107`): `delete_linked_salary_slips` (`:135`). Each submitted slip is **cancelled** (Salary Slip `on_cancel` `hrms:…/salary_slip.py:249`: status, linked Leave Encashment back to Unpaid, loan) and then **deleted**.
3. `cancel_linked_journal_entries` (`:144`): every **submitted** JE with an account row referencing the entry, i.e. the accrual JE and a submitted bank entry. Our JE `before_cancel` guards (`pdc.invoice_guard.block_je_cancel`, `lc.guards.block_je_cancel`) run; HRMS `unlink_ref_doc_from_salary_slip` runs on JE cancel.
4. Flags reset: `salary_slips_created` = `salary_slips_submitted` = 0, status Cancelled.

**What it leaves behind (no code of ours handles any of this):**

- the month's attendance Additional Salary (submitted; a later run of the same month replaces them);
- **advance recoveries, still submitted**, so each Employee Advance still shows the instalment as returned. Only a new run of the same month (`clear_month`) gives it back;
- Leave Recovery rows;
- the Dashain **Payroll Adjustment** and its Additional Salary (submitted), and submitted **Leave Encashments**: a new payout entry for the month finds them "already paid" (`paid_already` `festival_allowance.py:204`; "already encashed") and pays nothing;
- a **draft** bank entry (only submitted JEs are cancelled);
- the Payroll Inputs Log.

**Undoing a paid month cleanly:** cancel the bank entry → cancel the Payroll Entry (slips and accrual JE go) → for a payout, cancel the Payroll Adjustment (`payroll_adjustment.py:113` cancels its Additional Salary) or the Leave Encashments (HRMS cancels their Additional Salary through the `additional_salary` link) → make a new entry. To change one person, cancel their slip; their month counts as unpaid again and the next run re-posts their lines.

**Other cancels:** a Salary Revision (`salary_revision.py:308`) cancels its arrears Additional Salary and the new assignments, and puts raised structure rates back. An Overtime Sheet's `on_cancel` only withdraws replacement leave (`hr/replacement_leave.on_sheet_cancel`). The OT Additional Salary already posted stays until the month is run again.

---

## 3. Masters and data model

### 3.1 How a person's pay is assembled

```
Salary Component  ── what it is, how it is counted, which accounts (O/O, S/D, F/P per company)
Salary Structure  ── formula rows: Basic, SSF Addition, SSF, Income Tax (+ optional Late Fine tag)
   └ Allowance Rates (Structure Allowance Rate)  ── the usual rate; fills forms, raised by Salary Revision; payroll never reads it
Salary Structure Assignment  ── base, Initial Basic, SSF Applicable, Income Tax Slab, openings
   └ Allowances (Assignment Allowance)  ── what THIS person gets, at what rate (no row = not paid)
Employee  ── OT Eligible / Replacement Leave / Late Fine Exempt / Women's Tax Rebate; Department
Department  ── Payroll Section (Admin & Accounts / Marketing / Plant)
Additional Salary  ── every variable amount: tea, meal, OT, late fine, advances, arrears, Dashain, encashment, adjustments
```

### 3.2 Salary Component

The stock fields we rely on are `type`, `depends_on_payment_days`, `is_tax_applicable`, `exempted_from_income_tax`, `variable_based_on_taxable_salary`, `round_to_the_nearest_integer`, `remove_if_zero_valued` and `accounts`.

Custom fields (made by patches, not fixtures; the patch named is the one that creates the field):

| Field | Type / options | Patch | Read by | Purpose |
|---|---|---|---|---|
| `custom_is_allowance` | Check | `setup_allowance_kinds` | `validate_salary_structure` `allowance.py:465`, `_check_allowance_row` `:439`, `_gets` `attendance_allowance.py:737` | Paid from the assignment's Allowances; refused in a structure's Earnings |
| `custom_allowance_kind` | Monthly / % of Initial Basic / Per Day Present / Per Meal / Per Overtime Hour / Entered by Hand / Yearly | `setup_allowance_kinds`, `allowance_rate_list` | `validate_salary_component` `allowance.py:368`, `fixed_allowance_amounts` `:332` | How it is counted (`FIXED_KINDS` `allowance.py:73`; `ATTENDANCE_KIND_CONDITION` `:75`) |
| `custom_is_attendance_driven` | Check | `setup_attendance_allowance` | `get_attendance_driven_components` `attendance_allowance.py:697` | Priced by the attendance engine |
| `custom_condition_type` | Working Hours ≥ Threshold / Status = Present / Status = Half Day / Worked on Holiday / Meal Entitlement / Early Entry Before / Late Stay After / Late Arrival After / Authorised Overtime / Late Time | `setup_attendance_allowance`, `setup_overtime_and_late_fine` | `evaluate_rule` `attendance_allowance.py:297` | The daily rule. "Working Hours ≥ Threshold" is an option that **no code evaluates** (it returns 0) |
| `custom_unit` | Per Day / Per Hour / Flat per Period | `setup_attendance_allowance` | `_qty_for_employee` `:275`, `_per_unit` `:536` | Unit of the quantity; ignored for OT, Late Time and Meal |
| `custom_time_offset_hours` | Float | `setup_attendance_allowance`, `meal_on_authorised_overtime` | `_meals_for_day` `:383`, `evaluate_rule` `:369` | Early/late threshold (meal: 1.5 h) |
| `custom_threshold_hours` | Float | `setup_attendance_allowance` | **nothing** | dead |
| `custom_default_rate` | — | older patches | **nothing** | superseded by Allowance Rates |
| `custom_summary_group` | Data | `setup_attendance_allowance` | Monthly Attendance BS report | report grouping only |
| `custom_half_day_counts` | Full Day / Half Day / Not At All | `setup_half_day_allowance_rule` | `evaluate_rule` `:320` | Tea on a half day (Full Day) |
| `custom_pay_on_holiday` | Pay / Do Not Pay | `setup_pay_on_holiday_field` (blank → Pay) | `evaluate_rule` `:309` | Tea on a worked holiday. Blank = Pay |
| `custom_max_per_day` | Int | `setup_meal_rule_fields` | `_meals_for_day` `:417` | Meal cap (2) |
| `custom_rate_basis` | Fixed Rate / Hourly Basic × Multiplier | `setup_overtime_and_late_fine` | `_resolve_rate` `:755`, `rate_is_computed` `allowance.py:182` | Price from basic (OT and late fine always are) |
| `custom_rate_multiplier` | Float | same | `_resolve_rate` | Late fine 1. OT is hard-coded 1.5 (`OVERTIME_MULTIPLIER` `attendance_allowance.py:49`); the field is ignored for OT |
| `custom_rate_days_per_month` | Float, blank = BS month days | `setup_ot_rate_fields` | `_hourly_basic` `:505` | Divisor override (30 restores the Excel rule) |
| `custom_rate_hours_per_day` | Float, blank = 8 | same | `_hourly_basic` | Hours per day |
| `custom_attendance_month` | Same as Salary / Previous Month | `setup_allowance_kinds` | `_attendance_period` `:686` | Count the previous BS month instead |
| `custom_ot_eligible_only` | Check | `setup_allowance_kinds` | `_skip_for_eligibility` `:667` | Only OT-eligible staff (meal); OT always, the late fine never |
| `custom_is_festival_allowance` + `custom_festival_pay_month`, `custom_festival_min_service_days`, `custom_festival_prorate`, `custom_festival_include_daily_wage`, `custom_festival_include_leavers` | Check / Select / Int / Check | `setup_festival_allowance` | `festival_components` `festival_allowance.py:67`, `compute_rows` `:131`, `payout_type_for` `special_payout.py:86` | Dashain rules (§4.13) |

On **Salary Component Account** (the Accounts child): `custom_account_marketing` (S/D) and `custom_account_plant` (F/P) (`setup_allowance_kinds`). The stock `account` is O/O.

Validation on save: `validate_salary_component` (`allowance.py:368`, hooked `hooks.py:491`).
- Every account must belong to the row's company and must not be a group.
- An allowance needs a kind. An attendance kind forces `custom_is_attendance_driven` and the matching condition (and Unit = Per Hour for OT); any other kind forces attendance-driven off.
- An attendance-driven component gets `depends_on_payment_days` = 0 and `remove_if_zero_valued` = 1.
- `_check_type_for_condition` (`:418`): Authorised Overtime must be an Earning and Late Time a Deduction, and neither may be Exempted from Income Tax.

### 3.3 Salary Structure and Structure Allowance Rate

- Rows (onboarding `structure_rows`, `avinashgroup_app/payroll/onboarding.py:187`): Basic `base` (payment days on), SSF Addition `B * 0.20 if custom_ssf_applicable else 0` (off), SSF `B * 0.31 if custom_ssf_applicable else 0` (off), Late Fine (blank tag), Income Tax (slab). `B` is the prorated Basic, so the SSF rows must not be prorated again.
- `custom_allowance_rates` (child **Structure Allowance Rate**: `allowance`, `rate`, `unit`). It only fills forms (`get_structure_allowances` `allowance.py:231`, `get_rate_for_assignment` `:221`), fills a blank rate on an assignment (`validate_assignment_allowances` `:520`), and is what Salary Revision "Raise Rate" changes. **Payroll never reads it.**
- `custom_daily_wage` (Check): read only by `festival_allowance.monthly_basic` (`festival_allowance.py:112`). Daily-wage labour is otherwise outside payroll.
- Hooks: `validate_salary_structure` (`allowance.py:465`) refuses an allowance in Earnings or Deductions and blanks the formula of attendance-driven rows. `guard_structure_rates` (`:494`, `before_update_after_submit`) refuses a changed listed rate unless `frappe.flags.in_salary_revision` is set.

### 3.4 Salary Structure Assignment and Assignment Allowance

| Field | Meaning | Read by |
|---|---|---|
| `base` (stock) | Monthly basic | formula `base`; `_hourly_basic` (OT, late fine); Dashain; encashment |
| `custom_initial_basic` | What HRA is a % of (NGI, NGN) | `fixed_allowance_amounts` |
| `custom_ssf_applicable` | In the SSF | the SSF/SSFA formulas; slab row 1 condition (SST waiver) |
| `income_tax_slab` (stock) | That year's slab | `get_income_tax_slabs` `hrms:…/salary_slip.py:1618` |
| `taxable_earnings_till_date`, `tax_deducted_till_date` (stock, allow on submit) | Openings for months paid outside the system | `get_opening_for` `hrms:…:1657` (only when the assignment starts inside the payroll period) |
| `custom_allowances` (child **Assignment Allowance**: `allowance`, `rate`, `unit`, `effective_from`) | The person's allowances | `get_employee_allowance_rows` `allowance.py:285` (a row whose `effective_from` is later than the date is not yet in force) |

Which assignment applies: `current_assignment(employee, on_date)` (`allowance.py:270`), the latest submitted with `from_date` ≤ the date. The slip passes its **end date**. HRMS picks its own assignment for the structure (`set_salary_structure_assignment`). Revisions are therefore dated on the 1st of a BS month, which Salary Revision enforces (`salary_revision.py:229`).

### 3.5 Employee

| Field | Read by | Effect |
|---|---|---|
| `custom_ot_eligibility` (Overtime Eligible) | `_skip_for_eligibility`, `_meals_for_day`, `hr/overtime.evaluate` | OT and meals only for these people |
| `custom_compensatory_leave` (Replacement Leave for Holiday Work) | `hr/overtime.evaluate` | A holiday worked earns leave, not OT. `validate_employee_holiday_rule` (`hr/overtime.py:136`) refuses both ticks |
| `custom_late_fine_exempt` | `_skip_for_eligibility` `attendance_allowance.py:678` | No late fine |
| `custom_womens_tax_rebate` | `women_rebate_fraction` `tax_relief.py:189` | Rebate; `validate_womens_tax_rebate` (`:202`) refuses it for a non-female employee |
| `department` | `get_section` | Payroll section |
| `date_of_joining`, `relieving_date` | BS payment days, Dashain, advances (a leaver repays in full), encashment | — |
| `custom_pan`, `custom_ssf_id_no` | reports | — |

### 3.6 Department

`custom_payroll_section` (Select: Admin & Accounts / Marketing / Plant), created by `setup_allowance_kinds` and seeded by name. `SECTION_ACCOUNT_FIELD` (`allowance.py:94`) maps it to `account` / `custom_account_marketing` / `custom_account_plant`.

### 3.7 Payroll Entry custom fields

| Field | Purpose |
|---|---|
| `custom_fiscal_year`, `custom_bs_month` | The month being paid; everything else is filled from them (`fill_from_bs_month`) |
| `custom_month_calendar` | HTML calendar |
| `custom_payout_type` (blank / Dashain Allowance / Leave Encashment) | Payout entry (patch `setup_special_payout`) |
| `custom_pay_dashain`, `custom_festival_component`, `custom_festival_cutoff` | Dashain (cut-off defaults to the month's last day) |
| `custom_pay_leave_encashment` ("Settle Leave") | Monthly entry: leave **recovery** only. Encashment entry: set automatically |
| `custom_festival_adjustment` | Link to the Dashain Payroll Adjustment |
| `custom_payroll_inputs_log` | One dated line per run (`append_inputs_log`) |
| `custom_posting_miti`, `custom_start_miti`, `custom_end_miti` | BS dates |

### 3.8 Salary Slip custom fields

`custom_payout_type`; `custom_income_tax_computed`, `custom_override_income_tax`, `custom_income_tax_override` (patch `setup_income_tax`); `custom_retirement_excess`, `custom_women_rebate` (patch `setup_tax_exemptions`); `custom_daily_breakdown` (Table **Salary Slip Day**: `line_type` Day / Month End, `miti`, `date`, `weekday`, `attendance`, `paid_day`, `fixed_pay`, `earned`, `deducted`, `detail`, `day_total`, `balance`); `custom_bs_month`, mitis.

### 3.9 Additional Salary custom fields

`custom_source` (the source tag, e.g. "Nepal HRMS Attendance Allowance", "Advance Recovery", "Leave Recovery", "Leave Encashment"); `custom_payout_type`; `custom_quantity`, `custom_rate` (read by the Avinas Salary Statement); `custom_created_by` / `custom_created_on`. The stock `disabled` field is reused to hide payout rows (§2.6 P4).

### 3.10 Other custom fields

- Employee Advance: `custom_monthly_instalment`, `custom_recover_from` (`setup_advance_recovery`).
- Leave Type: `custom_encash_at_year_end`, `custom_encash_at_separation`, `custom_encashment_days_per_month`. Leave Encashment: `custom_occasion`, `custom_monthly_basic`, `custom_days_per_month`, `custom_rate_per_day` (`setup_leave_encashment`).
- Income Tax Slab: `custom_women_rebate_percent`. Employee Tax Exemption Category: `custom_is_retirement_contribution`, `custom_cap_percent_of_income` (`setup_tax_exemptions`).
- Attendance: `custom_worked_on_holiday` (set by `set_holiday_flag` `attendance_allowance.py:554`, resynced on a Holiday List edit by `resync_holiday_flags` `:579`), `custom_late_entry`, `custom_early_entry`, `custom_early_exit`, `custom_late_exit` (Duration, seconds), `custom_late_excused`, `custom_late_excuse_reason`.

### 3.11 Custom doctypes

| DocType | Submittable | Key fields | Controller | Role |
|---|---|---|---|---|
| **Overtime Sheet** (`OTS-.YYYY.-`) | yes | `company`, `work_date`, `department`, `reason`, `employees` → **Overtime Sheet Employee** (`employee`, `work_type` Work on Holiday / Overtime, `day_type`, `entitlement` Overtime / Replacement Leave, `shift`, `worked_hours`, `attendance`, `settlement_note`, `compensatory_leave_request`) | `avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.py:33`: per-row `hr/overtime.evaluate` (`hr/overtime.py:150`), all refusals at once ("Rows the policy does not allow"), "Authorised Twice" when someone is already on another live sheet for that date | Authorises OT. Hours are measured on submit or by the daily job (§4.10) |
| **Payroll Adjustment** (`PADJ-.YYYY.-`) | yes | `company`, `payroll_date`, `payroll_entry`, `source`, `cutoff_date`, `adjustments` → **Payroll Adjustment Row** (`employee`, `salary_component`, `amount`, `note`, `additional_salary`, Dashain working: `date_of_joining`, `base_amount`, `service_days`, `year_days`, `prorate_factor`) | `payroll_adjustment.py:30`: no duplicate (employee, component), same company, amount > 0, amount ≤ `base_amount` when set. `on_submit` posts one submitted Additional Salary per row (earnings with full tax) and refreshes drafts; `on_cancel` cancels them | One-off amounts (Load/Unload, Dashain) |
| **Salary Revision** (`SREV-.YYYY.-`) | yes | `effective_date` (1st of a BS month), `default_increment_percent`, `pay_arrears`, `arrears_payout_date`, `employees` → **Salary Revision Row**, `allowance_changes` → **Salary Revision Allowance** (Raise Rate / Add / Stop / Change Rate) | `salary_revision.py` | New assignments plus arrears (§4.12) |
| **Structure Allowance Rate**, **Assignment Allowance**, **Salary Slip Day** | child tables | see §3.3, §3.4, §3.8 | — | — |

Permissions (DocType JSON): Overtime Sheet: HR Manager / System Manager full, HR User read/write/create. Payroll Adjustment and Salary Revision: HR Manager / System Manager.

---

## 4. Every earning and deduction

### 4.0 Two rules that apply to everything

**Proration.** Stock HRMS prorates a row whose `depends_on_payment_days` is ticked as `amount × payment_days / total_working_days` (`hrms:…/salary_slip.py:1821`). With the BS engine on:

- `total_working_days` = the days of the BS month (29–32) (`rdp:…/salary_slip_bs.py:111`, `:150`);
- `payment_days` = days employed in the month − `leave_without_pay` − `absent_days` (`get_bs_payment_days` `rdp:…:166`). Holidays count as paid. HRMS counts a half day as 0.5 absent (`daily_wages_fraction_for_half_day` = 0.5) because Payroll Settings `payroll_based_on` = Attendance. Unmarked days follow `consider_unmarked_attendance_as`: Present on avinas1 (docs) and on demo.

Attendance-driven components are never prorated: their count already excludes absences.

**Where a variable amount reaches the slip.** Only as **submitted Additional Salary** dated inside the slip's period. HRMS adds them (`add_additional_salary_components` `hrms:…:1331`) with `default_amount` = 0 and `additional_amount` = the amount. Ours carry `deduct_full_tax_on_selected_payroll_date` = 1 on earnings, so their tax is charged in full in their own month (§5.5).

### 4.1 The running example

An NGI staff member, **Ashwin 2083** (2026-09-17 → 2026-10-17, 31 days), BS engine on.

- Assignment: `base` 30,000, `custom_initial_basic` 24,000, SSF Applicable ✓. Allowances: HRA 25 %, Dearness 2,000, Gas 1,690, Tea & Conveyance 235, Meal 75, Overtime.
- Employee: Overtime Eligible ✓, not Late Fine Exempt.
- Month: 1 day Absent, 1 Half Day, 26 days on which they came (the half day and one holiday worked included). One submitted Overtime Sheet: a working day with 4 h 30 m outside the shift, and on that day they stayed 1.5 h or more after the shift. 37 minutes late (plus early exit) across the month, none excused.
- Payment days = 31 − 1 − 0.5 = **29.5**.

| Line | Formula | Amount |
|---|---|---|
| Basic | 30,000 × 29.5 / 31 | 28,548.39 |
| SSF Addition | B × 0.20 | 5,709.68 |
| House Rent Allowance | 24,000 × 25 % = 6,000 × 29.5 / 31 | 5,709.68 |
| Dearness Allowance | 2,000 × 29.5 / 31 | 1,903.23 |
| Gas Allowance | 1,690 × 29.5 / 31 | 1,608.23 |
| Tea & Conveyance | 26 × 235 | 6,110.00 |
| Overtime | 4.5 h × (30,000 / 31 / 8 × 1.5 = 181.4516) | 816.53 |
| Meal | 1 × 75 | 75.00 |
| **Gross** | | **50,480.74** |
| SSF | B × 0.31 | 8,850.00 |
| Late Fine | 37 / 60 h × (30,000 / 31 / 8 = 120.9677) | 74.60 |
| Income Tax | SSF member, projected year under 10,00,000 → 0 (§5) | 0.00 |
| **Net pay** | | **41,556.14** |

The OT and late-fine rates were computed with the real code (`30000/31/8*1.5*4.5` = 816.53; `30000/31/8*37/60` = 74.60).

### 4.2 Basic

- **Formula:** structure row `base`, `depends_on_payment_days` = 1.
- **Rate:** the assignment's `base`.
- **Code:** HRMS `add_structure_components` and `eval_condition_and_formula` (`hrms:…:1166`, `:1250`). The formula's eval scope is `get_data_for_eval` (`hrms:…:1217`): assignment fields, then the slip, then the **Employee's** fields (which win on a name clash), then component abbreviations.
- **Proration:** BS payment days (§4.0).
- **Example:** 28,548.39.

### 4.3 SSF Addition (earning) and SSF (deduction)

- **Formulas:** SSFA `B * 0.20 if custom_ssf_applicable else 0`; SSF `B * 0.31 if custom_ssf_applicable else 0`. Neither row is a payment-days row.
- **Meaning:** the fund takes 31 % of basic: 20 % paid by the employer (shown as an earning so it appears in the gross and is taxed) and 11 % by the employee. Both leave through the one SSF deduction. Net effect on take-home: −11 % of B.
- **Tax:** SSFA is `is_tax_applicable` = 1. SSF is `exempted_from_income_tax` = 1, so HRMS subtracts it from taxable earnings (`get_taxable_earnings` `hrms:…:1725`, when the slab has `allow_tax_exemption`). It is also the retirement contribution that the s.63 cap limits (§5.6).
- **Rate:** `custom_ssf_applicable` on the assignment.
- **Code:** structure rows only; no Python.
- **Example:** SSFA 5,709.68, SSF 8,850.00 (28,548.39 × 0.31 = 8,850.0009).

### 4.4 HRA (% of Initial Basic)

- **Formula:** `custom_initial_basic × rate / 100` (`fixed_allowance_amounts` `allowance.py:332`), placed on the slip by `apply_employee_allowances` (`salary_slip.py:46`) through `update_component_row(…, default_amount=amount)`, so it is prorated like a structure row and **projected** for tax (it carries no `additional_salary`).
- **Rate:** the assignment row's Rate (NGI 25 %, NGN 27 %; `onboarding.py:56` PROFILES).
- **Proration:** yes, if the component has `depends_on_payment_days` = 1 (true on avinas1 (docs) and demo).
- **Example:** 6,000 × 29.5 / 31 = 5,709.68.

### 4.5 The other monthly allowances

Dearness, Other, Fixed, Fuel, Maintenance, Transport, Gas, Education: kind **Monthly**. The amount is the assignment row's Rate; the code and proration are the same as HRA. An allowance taken off the assignment is removed from the draft on its next save (`salary_slip.py:68`). Gas 1,690 and Education 2,780 are NGI's usual rates (NGN: 1,690.27 and 1,250). The usual rate is only the starting value on the form.

### 4.6 Tea & Conveyance (Per Day Present)

- **Rule:** `evaluate_rule` (`attendance_allowance.py:297`) with condition "Status = Present".
  - Present (any status other than Absent, On Leave or Half Day) → 1.
  - Half Day → per `custom_half_day_counts`: Full Day → 1, Half Day → 0.5, Not At All → 0.
  - Absent or On Leave → 0.
  - A worked holiday (`custom_worked_on_holiday`) pays unless `custom_pay_on_holiday` = "Do Not Pay" (`:309`). Blank = Pay.
- **Gate:** a Tea row on the assignment (`_gets` `:737`).
- **Rate:** that row's Rate (NGI 235 old staff / 40 new; NGN 265; `onboarding.py:56`).
- **Amount:** `qty × rate`, rounded to 2 decimals (`_priced` `:261`), posted as Additional Salary (§2.2 #14).
- **Proration:** none.
- **Example:** 26 × 235 = 6,110.

### 4.7 Meal (Per Meal)

- **Rule:** `_meals_for_day` (`attendance_allowance.py:383`). Paid only when all of these hold:
  - the person is OT Eligible;
  - a submitted Overtime Sheet names them that day with entitlement Overtime (`_on_overtime_sheet` `:437`);
  - the day is Present or Half Day.
- **Working day:** 1 meal if `custom_early_entry` ≥ `custom_time_offset_hours` (1.5 h), plus 1 if `custom_late_exit` ≥ 1.5 h.
- **Holiday on the sheet:** `holiday_meals(holiday_hours_worked(row))` (`:429`). First IN to last OUT, exact: 8 h or more → 2, 6 h or more → 1, less → 0 (`HOLIDAY_MEAL_HOURS` `:426`). Checked: 5.99 h → 0, 6 h → 1, 7.88 h → 1, 8 h → 2.
- **Cap:** `custom_max_per_day` (2).
- **Rate:** the Meal row on the assignment (NGI and NGN 75; NGG 100).
- **Example:** 1 × 75.

### 4.8 Overtime (Authorised Overtime)

- **Hours:** `_authorised_overtime_hours` (`attendance_allowance.py:463`) = Σ `worked_hours` of submitted Overtime Sheet rows for that employee and date with entitlement Overtime. `worked_hours` is written by settlement (`hr/overtime_settlement.py:81` `measure_row`):
  - working day: `hours_outside_shift(in, out, shift_start, shift_end)` (`hr/overtime.py:320`) = (worked − overlap with the shift) / 3600, exact to the second;
  - holiday or weekly off: `holiday_hours_worked` (`hr/shift_day.py:138`), first IN to last OUT;
  - 0 with a note when there is no attendance, the day is Absent on a working day, there is only one punch, or there is no shift.
- **Rounding:** none since `4a83b82` (patch `overtime_exact_to_the_second`).
- **Rate:** `overtime_rate` (`:525`) = `base / days / hours × 1.5`, where days = `custom_rate_days_per_month` or the BS month's length, and hours = `custom_rate_hours_per_day` or 8. The multiplier is hard-coded at 1.5 (`OVERTIME_MULTIPLIER` `:49`), not read from the component.
- **Gate:** OT Eligible (`_skip_for_eligibility` `:667`). No assignment row is needed (`_gets` returns True).
- **Example:** 30,000 / 31 / 8 = 120.9677 an hour; × 1.5 = 181.4516; × 4.5 = **816.53**.

### 4.9 Late fine (Late Time)

- **Quantity:** `(late_minutes + early_exit_minutes) / 60` from `hr/shift_day.measure_day` (`evaluate_rule` `:345`). 0 on a day marked `custom_late_excused`.
- **Rate:** always from basic, whatever the component says (`_resolve_rate` `:771`): `base / days / hours × multiplier (blank = 1)`, i.e. one minute = basic / month days / 8 / 60.
- **Who:** everyone except those ticked **Late Fine Exempt** (`:678`). No structure row is needed any more (`_gets` returns True for Late Time).
- **Cap:** none.
- **Tax:** a Deduction that is not exempt, so it does **not** lower taxable income (§5.2).
- **Example:** 37 min → 0.6167 h × 120.9677 = **74.60**.
- The older "Late Arrival After" condition still exists (`:357`). It is not fined on a holiday or on a Half Day, and it uses `custom_time_offset_hours`.

### 4.10 Advance recovery and the recovery cap

- **Outstanding** = `paid_amount − claimed_amount − return_amount` (`advance_recovery.py:34`).
- **Monthly:** `min(custom_monthly_instalment or owed, owed)`, from the month `custom_recover_from` onwards (`:100`).
- **Leaver** (relieving date inside the month): the whole outstanding amount, ignoring the instalment and the start date (`:90`).
- Posted as a submitted "Salary Advance" deduction that references the advance (HRMS keeps the balance: `hrms:…/additional_salary.py:217`). In the accrual JE it is credited to the advance account with the employee as party (`get_advance_deduction`, `hrms:…/payroll_entry.py:404`).
- **Cap** (`recovery_cap.py:45`): before submission, any draft whose net pay is below zero has its Leave Recovery cut first, then its advance, until the net is 0. The rest is reported for collection outside payroll. A cut advance stays owed on the Employee Advance.
- **Example:** an advance of 50,000 with 20,000 already returned leaves 30,000 owed; an instalment of 5,000 posts 5,000. If the person leaves this month, 30,000 is posted. With a net before the advance of 12,000, the slip would go to −18,000; the cap cuts the recovery to 12,000, the net is 0, "collect 18,000 outside payroll" is shown, and the advance still shows 18,000 outstanding.

### 4.11 Leave recovery

`recover_month` (`leave_encashment.py:341`), only when the monthly entry has Settle Leave ticked, and only at a settlement: a relieving date in the month, or an allocation ending in it.

- `short = −settlement_balance`, where the settlement balance is HRMS's balance plus the month's credit still due (`_credit_still_due` `:419`).
- Amount = `short × per_day_rate` (`per_day_rate` `:95`: base ÷ the Leave Type's `custom_encashment_days_per_month`, or the BS month's days).
- **Example:** −3 days in Kartik 2083 (30 days) at a base of 30,000 → 1,000 a day → **3,000** deducted.

### 4.12 Arrears (Salary Revision)

`arrears` (`salary_revision.py:271`) = `arrears_for` (`:519`) + the change in attendance rates.

- `arrears_for`: Σ over the **monthly** slips already submitted from the effective date of `monthly_difference × payment_days / total_working_days`.
- `monthly_difference` (`monthly_increase` `:257`) = Δbase + Δdearness + Δ(other Monthly and %-of-Initial-Basic allowances).
- Tea and meal: (new rate − old rate) × the quantity those months counted (`attendance_qty_paid` `:537`, re-counted with the engine's own rules).
- Paid by `pay_the_arrears` (`:398`) as a submitted **Salary Arrears** Additional Salary on `arrears_payout_date`, with full tax. `ensure_arrears_component` (`:562`) creates the component with `round_to_the_nearest_integer` = 1.
- **SSF Addition and SSF are not in the difference.** The rise's 20 % and 31 % for the back months are never paid or deducted (§10).
- **Example:** a rise effective 1 Shrawan, agreed in Ashwin. Shrawan paid 31/31 and Bhadra 29.5/31; +2,000 basic and +500 dearness give a monthly difference of 2,500. 2,500 + 2,500 × 29.5 / 31 = 4,879.03. Tea 235 → 250 over 26 + 24 days adds 750. Total **5,629.03**, which the slip shows rounded to 5,629.

### 4.13 Dashain (festival allowance)

`compute_rows` (`festival_allowance.py:131`).

- Basic = the assignment's `base` on the cut-off (× BS month days for a Daily Wage structure, `monthly_basic` `:112`).
- `service_factor` (`:84`): service days = cut-off − joining; year days = cut-off − the same date a year earlier (365 or 366). The factor is 1 if they joined on or before that date, else service ÷ year days, clamped to 0..1.
- `festival_amount` (`:104`) = `min(basic, basic × factor)`. With Prorate off, any service pays the full basic.
- **Left out:**
  - another company;
  - already paid this payroll period;
  - joined on or after the cut-off;
  - left before the cut-off (unless Include Leavers is ticked; a leaver is counted to the relieving date);
  - under Minimum Service Days;
  - daily wage (unless included);
  - no assignment.
- Paid on its **own payout slip** (§2.6), taxed by §5.9.
- **Example** (computed with the code): joined 2026-01-10, cut-off 2026-10-17 → 280 / 365 = 0.767123; 30,000 × 0.767123 = **23,013.70**. Joined 2025-10-17 → factor 1 → the full basic.

### 4.14 Leave encashment

- `price_encashment` (`leave_encashment.py:116`, Leave Encashment validate, after HRMS has set the balance and capped the days).
- Occasion: **Year End** when dated the allocation's last day, **Separation** when dated the relieving date. Anything else throws, and so does an occasion the Leave Type does not allow.
- Rate per day = base ÷ (`custom_encashment_days_per_month` or the BS month's days); amount = `encashment_days × rate`.
- A second encashment of the same allocation is refused.
- `SettlementLeaveEncashment.set_leave_balance` (`:404`) adds the month's credit still due, so a settlement made before the month-end accrual job has run still counts that month.
- Paid on its **own payout slip**.
- **Example:** Ashadh 2084 has 32 days (checked); a base of 30,000 gives 937.50 a day; 6.5 days → **6,093.75**.

### 4.15 Others

- **Load/Unload Allowance** (Entered by Hand): a Payroll Adjustment row, i.e. an Additional Salary with full tax, on the monthly slip.
- **Daily Wage**: disabled; daily labour is paid in cash outside payroll (decided 2026-10-08).
- **Dashain Bonus** (DB): an old component, not used by the Dashain flow (the flow uses the component ticked Festival Allowance). The demo site has a "Dashain Alllowance" component (three l's) ticked.

---

## 5. Income tax in full

### 5.1 The pieces

| Piece | Where it lives | Notes |
|---|---|---|
| Payroll Period | `<FY> - <ABBR>`, 2026-07-17 → 2027-07-16, one per company (made by `hr/year_setup.ensure_payroll_period`, `hr/year_setup.py:335`) | No period → no tax and a message ("Start and end dates not in a valid Payroll Period …") |
| Income Tax Slab | `Nepal 83/84 - <ABBR>`, effective 2026-07-17, `allow_tax_exemption` = 1, standard exemption 0, `custom_women_rebate_percent` = 10 (same on demo) | Read **from the assignment** (`get_income_tax_slabs` `hrms:…/salary_slip.py:1618`), not by date. Throws "Income Tax Slab not set in Salary Structure Assignment …", "… is disabled", "… must be effective on or before Payroll Period Start Date …". Seed table: `FY_8384_SLABS` (`income_tax.py:31`), `TAX_SLABS_BY_YEAR` (`:45`), `WOMEN_REBATE_BY_YEAR` (`:54`) |
| Tax component | "Income Tax" (IT), `variable_based_on_taxable_salary` = 1, on every structure | `add_tax_components` (`hrms:…:1351`) |

### 5.2 Annual taxable income: the projection

`compute_taxable_earnings_for_year` (`hrms:…/salary_slip.py:877`) runs inside `calculate_net_pay` (from `add_tax_components`):

```
previous_taxable_earnings   = Σ taxable earnings on SUBMITTED slips this period that start AND end
                              between the period start and this slip's start (get_salary_slip_details :1662)
                            + opening taxable_earnings_till_date (get_opening_for :1657)
                            − Σ exempted deductions (SSF) on those slips                    (:1642)
current_structured          = this slip's taxable earnings at payment days, excluding Additional Salary,
                              minus this slip's exempt deductions                            (:1725, :919)
future_structured           = the same at FULL month × (round(remaining_sub_periods) − 1)      (:919)
current_additional          = this slip's Additional Salary earnings (tea, OT, arrears, Dashain …)
other_incomes               = Employee Other Income for the period                          (:1924)
total_exemption_amount      = Tax Exemption Declaration (or Proof) total + standard exemption (:1897)

total_taxable_earnings      = previous + current_structured + future_structured + current_additional
                              + other_incomes + unclaimed_benefits − total_exemption_amount
…_without_full_tax_addl     = total_taxable_earnings − current additional earnings with "full tax"
```

- **Remaining months.** HRMS's `get_period_factor` (`hrms:payroll/doctype/payroll_period/payroll_period.py:102`) counts AD months to the period end, or to the relieving date. `BSSalarySlip.compute_current_and_future_taxable_earnings` (`rdp:…/salary_slip_bs.py:225`) replaces this with `get_bs_months_between(slip start, payroll period end)`, counting both ends (checked: Ashwin 2083 → **10**, Ashadh 2084 → 1). **It ignores the relieving date** (§9).
- **"Till Date" openings.** `taxable_earnings_till_date` and `tax_deducted_till_date` on the assignment count only when that assignment's `from_date` is inside the payroll period (`get_opening_for`). Months paid outside the system (Shrawan 2083 from Excel) must be entered there. `tax_history_gaps` (`income_tax.py:61`) warns otherwise.
- **Payout slips are "previous" slips too.** An earlier month's Dashain or encashment slip has dates inside the range, so HRMS counts its earnings and tax. A payout slip in the **same** month is not "previous" (its end is after this slip's start); `other_payouts_taxable` (`special_payout.py:255`) covers that case for payouts.
- **Fines do not lower taxable income.** Only deductions with `exempted_from_income_tax` (SSF, a CIT component) are subtracted.

### 5.3 The slab rows and their conditions

On the 83/84 slabs (avinas1 (docs) and demo are identical):

| From | To | % | Condition |
|---|---|---|---|
| 0 | 10,00,000 | 1 | `not custom_ssf_applicable` |
| 10,00,001 | 15,00,000 | 10 | |
| 15,00,001 | 25,00,000 | 20 | |
| 25,00,001 | 40,00,000 | 27 | |
| 40,00,001 | — | 29 | |

`calculate_tax_by_tax_slab` (`hrms:…:2227`) skips a row whose condition is false (`eval_tax_slab_condition` `:2268`). The condition is evaluated against `get_data_for_eval`, where the assignment's `custom_ssf_applicable` is in scope. The first row is the 1 % **Social Security Tax (SST)**, waived for SSF members.

So for an SSF member there is no tax below 10,00,000. A non-SSF person pays 1 % from the first rupee. HRMS's "+1" makes the 0-based band cost 0.01 more: 4,00,000 → 4,000.01 (computed with the code).

The tax is computed only above `tax_relief_limit`; a marginal relief (`calculate_tax_with_marginal_relief`) and "other taxes and charges" are applied when the slab has them. Neither is used on these slabs.

### 5.4 The month's tax (HRMS)

`calculate_variable_tax` (`hrms:…:1570`):

```
previous_total_paid_taxes = Σ tax on earlier submitted slips this period + opening tax_deducted_till_date (:1711)
total_structured_tax      = slab(total_taxable_earnings_without_full_tax_addl)
current_structured_tax    = (total_structured_tax − previous_total_paid_taxes) / remaining_sub_periods
full_tax_on_additional    = slab(total_taxable_earnings) − total_structured_tax      (only if any "full tax" additional)
current_tax_amount        = max(0, current_structured_tax + full_tax_on_additional)
```

### 5.5 "Full tax" Additional Salary

Every Additional Salary this app posts for an earning sets `deduct_full_tax_on_selected_payroll_date` = 1:

- attendance lines (`attendance_allowance.py:850`);
- Payroll Adjustment rows (`payroll_adjustment.py:96`);
- arrears (`salary_revision.py:412`);
- encashment (`leave_encashment.py:168`).

Its whole marginal tax is therefore taken in that month, not spread over the remaining months. Without it HRMS treats a one-off as if no later month paid anything (the docstring's example: 6 of tax instead of the sheet's 70.69).

### 5.6 Retirement cap (s.63) and the add-back

`apply_tax_reliefs` (`tax_relief.py:77`), monthly slips only, after HRMS:

1. `retirement_categories` (`:57`): active exemption categories with `custom_is_retirement_contribution` = 1. None → no cap.
2. `retirement_excess` (`:131`):
   - contributions = previous exempt deductions (`previous_taxable_earnings_before_exemption − previous_taxable_earnings`) + this slip's exempt deductions (at payment days) + the full-month figure × (⌈remaining⌉ − 1) + **declared** retirement (`declared_retirement` `:170`: CIT/PF paid directly, from the Declaration, or from the Proof in the last month);
   - assessable = `total_taxable_earnings + total_exemption_amount` + the three exempt parts;
   - cap = the **lower** of the category's `max_amount` and `assessable × custom_cap_percent_of_income / 100` (`retirement_cap` `:66`);
   - excess = max(contributions − cap, 0).
3. The excess is **added back** to taxable income before the slab is applied (see §5.8).

Configuration:
- *avinas1 (docs)*: "Retirement Contribution", max 5,00,000, ✓ retirement, 33.333333 %.
- *demo*: the category exists but `custom_is_retirement_contribution` = 0, so **no cap** applies there.

Every exempt deduction counts as a retirement contribution. That is why `_check_type_for_condition` refuses "exempt" on OT and the late fine.

### 5.7 Insurance (life, health, building) and other declared exemptions

**How they are entered.** HR files an **Employee Tax Exemption Declaration** for the person and payroll period (`83/84 - <ABBR>`), with one row per sub-category and the premium actually paid. In the period's last month, an **Employee Tax Exemption Proof Submission** replaces it.

Categories:

| Sub-category | avinas1 (docs) cap | demo cap |
|---|---|---|
| Life Insurance | 40,000 | 40,000 |
| Health Insurance | 20,000 | 20,000 |
| (Private) Building Insurance | 10,000 | **5,000** |
| Category "Insurance Premium" | 70,000 | **65,000** |
| Retirement Contribution: CIT paid directly, Provident Fund paid directly | 5,00,000 each | 5,00,000 each |

**Where the caps apply.** In HRMS, when the declaration is saved: `get_total_exemption_amount` (`hrms:hr/utils.py:278`) takes each row as `min(amount, sub-category max)`, sums them per category and caps the sum at the category max. The result is the declaration's `total_exemption_amount` (`hrms:payroll/doctype/employee_tax_exemption_declaration/employee_tax_exemption_declaration.py:35`; Proof: `exemption_amount`). `test_insurance_is_cut_to_each_limit` (`avinashgroup_app/payroll/test_tax_relief.py:99`) checks that an amount 5,000 over each limit is cut back to the limit.

**Where the slip reads them.** `get_total_exemption_amount` (`hrms:…/salary_slip.py:1897`) on the slip:
- the submitted Declaration's `total_exemption_amount` for the employee and period;
- or, when `deduct_tax_for_unsubmitted_tax_exemption_proof` is set (always in the period's last month, `hrms:…:877`; also when ticked on the Payroll Entry), the Proof's `exemption_amount`.

There is no code of ours in this path: `tax_relief.py` only reads the declaration again for the CIT/PF part of the retirement cap.

**How they reduce tax.** The whole year's exemption is subtracted from the projected annual income (§5.2), so each month's tax = (slab of the reduced year − tax already paid) ÷ months left. A declaration filed mid-year lowers the remaining months' tax. If the Proof is lower or missing in Ashadh, the tax saved earlier is taken back in that month.

*Data:* 0 declarations and 0 proofs on demo; 0 on avinas1 (docs, 2026-10-12).

### 5.8 Women's rebate, then the relief formula

`women_rebate_fraction` (`tax_relief.py:189`) = slab `custom_women_rebate_percent` / 100, only for an Employee with gender Female and `custom_womens_tax_rebate` ticked.

`apply_tax_reliefs` then recomputes, using HRMS's own intermediate figures (`tax_relief.py:95–327`):

```
structured     = slab(total_taxable_earnings_without_full_tax_addl + excess) × (1 − rebate)
current        = (structured − previous_total_paid_taxes) / remaining_sub_periods
full_tax_addl  = slab(total_taxable_earnings + excess) × (1 − rebate) − structured     (if any full-tax additional)
tax row        = max(current + full_tax_addl, 0)
```

It also writes `custom_retirement_excess` and `custom_women_rebate`, adds the excess to `annual_taxable_amount`, and resets `income_tax_deducted_till_date`, `current_month_income_tax`, `future_income_tax_deductions`, `total_income_tax` and the net. With no excess and no rebate the slip is left exactly as HRMS made it.

### 5.9 Manual override

`apply_income_tax_override` (`income_tax.py:156`) runs after the reliefs:
- `custom_income_tax_computed` = the tax row (with reliefs);
- if `custom_override_income_tax` is ticked, the row = `custom_income_tax_override` and the net is recomputed;
- with no tax row and an override amount, it appends a row of the first `variable_based_on_taxable_salary` Deduction component.

The override is per slip. The next month's HRMS projection subtracts what this slip actually deducted, so the year corrects itself.

### 5.10 The special-payout tax method

`payout_tax` (`special_payout.py:234`), called from `build_payout_slip` while the slip still holds HRMS's figures for the **merged** month (monthly pay plus the payout):

```
A      = total_taxable_earnings (merged) + other payout slips' taxable earnings, same dates (other_payouts_taxable)
         + retirement_excess(merged slip)
P      = the payout's taxable amount
tax    = max(0, (slab(A) − slab(A − P)) × (1 − women's rebate))
```

That is the whole tax the payout adds to the year, charged in the payout. Then:
- the payout rows are fixed at their full amount (never prorated);
- the deductions are reduced to the single tax row;
- gross, net and year-to-date figures are recomputed (`special_payout.py:290–306`).

The month's salary slip does not see the payout and charges the year's structured tax as before; the next month's slip sums both earlier slips.

### 5.11 Fully worked example

**Sita**, NGI, SSF member, female, Women's Tax Rebate ✓, slab rebate 10 %. Retirement category as on avinas1 (5,00,000; 33.333333 %). Slip: **Ashwin 2083**. Shrawan and Bhadra were paid in the system on the same pay.

Monthly pay (a full month, no absence): Basic 1,50,000; SSF Addition 30,000; HRA 25 % of Initial Basic 1,20,000 = 30,000; Dearness 5,000. Earnings 2,15,000. SSF 46,500 (exempt). This month there are also **Salary Arrears of 10,000** (full tax).

Declaration: Life 50,000 (cap 40,000), Health 25,000 (cap 20,000), Building 8,000 (cap 10,000) → `total_exemption_amount` = 68,000.

**Step 1: projection (HRMS, `hrms:…:877`, `rdp:…:225`)**

| Figure | Working | Value |
|---|---|---|
| remaining_sub_periods | Ashwin → Ashadh (`get_bs_months_between`) | 10 |
| previous_taxable_earnings | 2 × (2,15,000 − 46,500) | 3,37,000 |
| current_structured | 2,15,000 − 46,500 | 1,68,500 |
| future_structured | 1,68,500 × (10 − 1) | 15,16,500 |
| current_additional (full tax) | arrears | 10,000 |
| total_exemption_amount | declaration | 68,000 |
| **total_taxable_earnings** | 3,37,000 + 1,68,500 + 15,16,500 + 10,000 − 68,000 | **19,64,000** |
| without full-tax additional | 19,64,000 − 10,000 | 19,54,000 |

**Step 2: what HRMS alone would deduct (`hrms:…:1570`).** slab(19,54,000) = 50,000 (10 % band) + (19,54,000 − 15,00,000) × 20 % = 1,40,800. Suppose Shrawan and Bhadra deducted 11,430 each, so previous_total_paid_taxes = 22,860. Current = (1,40,800 − 22,860) / 10 = 11,794. Full tax on the arrears = slab(19,64,000) − slab(19,54,000) = 1,42,800 − 1,40,800 = 2,000. **HRMS: 13,794.**

**Step 3: retirement cap (`tax_relief.py:131`)**

| Figure | Working | Value |
|---|---|---|
| previous exempt | 2 × 46,500 | 93,000 |
| current exempt | | 46,500 |
| future exempt | 46,500 × (⌈10⌉ − 1) | 4,18,500 |
| declared CIT/PF | | 0 |
| contributions | | 5,58,000 |
| assessable | 19,64,000 + 68,000 + 5,58,000 | 25,90,000 |
| cap | min(5,00,000, 25,90,000 × 33.333333 % = 8,63,333.32) | 5,00,000 |
| **excess** | 5,58,000 − 5,00,000 | **58,000** |

**Step 4: reliefs (`tax_relief.py:77`)**

| Figure | Working | Value |
|---|---|---|
| structured | slab(19,54,000 + 58,000 = 20,12,000) = 1,52,400 × 0.9 | 1,37,160 |
| current | (1,37,160 − 22,860) / 10 | 11,430 |
| full_tax_addl | slab(20,22,000) = 1,54,400 × 0.9 = 1,38,960 − 1,37,160 | 1,800 |
| **tax row** | | **13,230** |

The slip shows `custom_retirement_excess` 58,000 and `custom_women_rebate` 10. (The 11,430 assumed for Shrawan and Bhadra is what the same projection gives over 12 months: 1,37,160 / 12.)

**Step 5: override (`income_tax.py:156`).** `custom_income_tax_computed` = 13,230. Not overridden.

**Net pay:** 2,25,000 − 46,500 − 13,230 = **1,65,270**.

**The same month's Dashain payout** (§5.10). Sita has more than a year's service, so the Dashain allowance = 1,50,000. To keep the arithmetic separate, take the merged slip without the arrears: A = 19,54,000 + 1,50,000 + excess 58,000 = 21,62,000. Payout tax = (slab(21,62,000) − slab(20,12,000)) × 0.9 = (1,82,400 − 1,52,400) × 0.9 = **27,000**. The payout slip pays 1,50,000 − 27,000 = **1,23,000**.

The slab values (1,40,800; 1,52,400; 1,82,400) were computed with HRMS's `calculate_tax_by_tax_slab` on the demo NGI slab.

### 5.12 Small earners

The running example in §4.1 projects to about 5 lakh a year:
- as an SSF member: **0 tax** (row 1 is skipped);
- if not in the SSF: 1 % SST, about 5,000 a year, which HRMS spreads over the remaining months, plus full tax in the month on tea and OT.

---

## 6. Accounting

### 6.1 The accrual JE (on Submit Salary Slip)

HRMS `make_accrual_jv_entry` (`hrms:…/payroll_entry.py:531`), with our grouping:

- **Earnings:** Dr `section_account(company, component, section)`: the O/O `account`, `custom_account_marketing` for Marketing, or `custom_account_plant` for Plant. A blank S/D or F/P falls back to O/O (`allowance.py:130`). With no row for the company, HRMS throws "Please set account in Salary Component …".
- **Deductions:** Cr the component's account for the section. An advance deduction is Cr the advance account with party = employee (`hrms:…:416`).
- **Payable:** Cr the Payroll Payable account (the company's `default_payroll_payable_account`, filled by `fill_from_bs_month`) for the net.
- **Section** = Employee → Department → `custom_payroll_section`. It is required only for components that have S/D or F/P accounts (`section_for` `payroll_entry.py:516`).
- **Cost centre:** HRMS's Employee Cost Center split, or the entry's cost centre (`get_payroll_cost_centers_for_employee` `hrms:…:474`).

### 6.2 The JE fields (`hr_journal.py`)

Every Journal Entry needs `custom_p_type` (JV Type) and `custom_document_no`. HRMS knows neither, so `default_jv_type` (`hr_journal.py:30`, first `before_insert`) handles a JE that references a Payroll Entry or Employee Advance:

- JV Type = its `voucher_type` if a JV Type of that name exists, else "Journal Entry";
- for a hand-numbered series, the next number from the naming engine (`naming_series._docno_scope` / `_draw_next_document_no`), with `custom_document_no_manual` = 1;
- an auto-numbered series (Bank Entry) draws its own number.

JV Types on demo: Journal Entry, Bank Entry, Cash Entry, Opening Entry, Party Journal, Credit Note, Debit Note, Contract Form, Cylinder Deposit Slip, Cash/Bank or Contra Voucher.

### 6.3 The intended mapping

`PROPOSED_ACCOUNTS` (`onboarding.py:652`), a proposal applied by `map_component_accounts` (`:663`):

| Component | Account (O/O; S/D and F/P twins found by name, `sibling_account` `allowance.py:144`) |
|---|---|
| every earning | 547101 Salary Expenses (O/O), 547102 (S/D), 547103 (F/P) |
| SSF | 347302 SSF Payable |
| Income Tax | 348102 11112 TDS-Remuneration Income Tax |
| Salary Advance | 148003 Staff Advance |
| Late Fine | 547101 Salary Expenses (a fine reduces the salary cost; no fines-income account exists) |

The chart also has per-allowance expense accounts (547104/5/6 HRA, 547107/8/9 Fixed, 547110/1/2 Other, 547113/4/5 Overtime, 547130/1/2 Meal, 547136/7/8 Fuel, 547145/6/7 Dashain), which demo NGI uses.

### 6.4 What is mapped, per company

*avinas1 (docs, 2026-10-12, not re-verified):*

| Company | Mapping | Consequence |
|---|---|---|
| NGI | all 22 active components; earnings and the Late Fine with all three sections; SSF / Income Tax / Advance O/O | posts |
| NGN | 10 components, O/O only; **Tea and Meal rows without an account** | Tea/Meal lines stop the JE ("Please set account …") |
| NGG | only a Meal row, without an account | cannot post |
| NGK, GLMI, GEPL, SGU | none | cannot post |

*demo (queried):*

| Company | Mapping |
|---|---|
| NGI | 16 components with S/D and F/P. **SSF → 347305 CIT Payable** and **SSF Addition → 347302 SSF Payable**. An earning debited to a liability, and the SSF deduction credited to CIT: wrong if copied to a live site. Income Tax → 348108 11211 TDS-SST; the late fine ("late comers deduction") → 545200 Tax, Fines & Penalties |
| GEPL | Salary Advance; Meal O/O + S/D |
| GLMI, NGG, NGK, NGN, SGU | Salary Advance only |

---

## 7. Company differences

**Code-defined** (`onboarding.py:56` PROFILES, from each company's Falgun 2082 sheet):

| | NGI | NGN | NGG | NGK | GLMI / GEPL / SGU |
|---|---|---|---|---|---|
| Pay model | Initial basic | Initial basic | Grade scale | Grade scale | not onboarded |
| HRA (% of Initial Basic) | 25 % | 27 % | — | — | — |
| Gas / Education (usual) | 1,690 / 2,780 | 1,690.27 / 1,250 | — | — | — |
| Tea old / new staff | 235 / 40 | 265 / 40 | — | — | — |
| Meal | 75 | 75 | 100 | — | — |
| Per-person columns | dearness, other, fuel | same | fixed, dearness, other, fuel | fixed, dearness, other, fuel, maintenance | — |
| Sheet matching | by code | by code | by name | by name | — |
| Leave (policy, `hooks.py:514`) | 21 + 12 | 21 + 12 | 21 + 12 | **8 + 12** | — |

**avinas1 (docs, 2026-10-12, not re-verified):**

- Structures: NGI, NGN, NGG and NGK "Staff 83/84"; GLMI, GEPL and SGU have no structure and no active staff.
- Submitted assignments: NGI 87 (83 SSF), NGN 63 (53 SSF), NGG 27 (27), NGK 18 (15). 70 active employees had no assignment.
- Department section: NGG had 27 of 27 staff without a section.
- Accounts: as §6.4.

**demo (queried):**

- Active employees: NGI 108, NGN 77, NGG 55, NGK 44, GLMI 13, GEPL 2.
- OT Eligible: NGI 6, GLMI 1; Replacement Leave NGI 4; Late Fine Exempt NGI 1; Women's Rebate none.
- No Department: NGI 96, NGN 77, NGG 55, GLMI 12, GEPL 2, NGK 14. Sections exist only at NGI (5 A&A, 2 Marketing, 5 Plant) and GLMI (1 A&A).
- Structures: all NGI ("NGI Staff 83/84", "salary Test", "me", and two cancelled); every payroll entry is NGI's.
- The Income Tax Slabs are identical for all seven companies.

---

## 8. Scheduled jobs, permissions, background behaviour

### 8.1 Jobs that affect pay

| Job | Frequency | Effect if it never runs |
|---|---|---|
| `hr.overtime_settlement.measure_pending` (`hr/overtime_settlement.py:224`) | daily_long | A sheet submitted on or before its work day is never measured, so **OT and holiday meals pay 0** (on submit, `on_sheet_submit` `:213` measures only sheets for past days) |
| `hr.replacement_leave.grant_pending` | daily_long | no replacement leave |
| `hr.utils.allocate_earned_leaves_bs` | daily_long | no monthly leave credit, which changes encashment and recovery. HRMS's `allocate_earned_leaves` must stay **stopped**: it is stopped on demo and on avinasdemo |
| `hr.holiday_year_switch.switch_to_current_year_lists` | daily_long | holiday lists stay on the old year, so holiday flags and tea/OT on holidays are wrong |
| `biometric.attendance_self_heal.heal_unlinked_checkins` | daily_long | unrepaired days, i.e. absences that cut pay |
| HRMS `generate_leave_encashment` | daily_long | not stopped, but a no-op while HR Settings `auto_leave_encashment` = 0 (it is 0 on demo) |
| HRMS `process_auto_attendance_for_all_shifts` | hourly_long | no automatic Attendance |

**The scheduler on avinas1: cannot be verified here**, because the site is not on this machine. The session notes (`docs/session-2026-10-12-payroll.md` §13, D1) record it as off and ask whether to turn it on. On *this* bench the scheduler is **running**: `frappe schedule` and two workers are up; System Settings `enable_scheduler` = 1 and `pause_scheduler` = 0 on the demo sites; the jobs above last ran 2026-10-29 00:00–00:01 on demo-nggroup and avinasdemo. With the scheduler off on avinas1, every row above is "never runs". To check there: `bench --site avinas1 doctor`, or `SELECT value FROM tabSingles WHERE doctype='System Settings' AND field='enable_scheduler'`.

### 8.2 Permissions

- Payroll Entry: HR Manager (demo DocPerm). Our server methods call HRMS's `check_permission("write")` (inside `create_salary_slips` / `submit_salary_slips`).
- Everything the run writes (Additional Salary, Payroll Adjustment submit, Leave Encashment, recovery cuts) uses `flags.ignore_permissions`. Once someone may submit the entry, the run is not stopped for lack of Additional Salary rights.
- Additional Salary DocPerm on demo: HR User and System Manager only (no HR Manager row). The old "Prepare Payroll Inputs" endpoint `trigger_for_payroll_entry` (`attendance_allowance.py:79`) checks `has_permission("Additional Salary", "create")`, but nothing calls it any more.
- Salary Slip: Employee read; HR User read/write/create/submit; HR Manager full.

### 8.3 Background behaviour

- **More than 30 employees**: HRMS enqueues slip creation and slip submission (`hrms:…/payroll_entry.py:241`, `:286`; status "Queued"). Our inputs are posted, and the recovery cap runs, **in the request, before** `frappe.enqueue`. `enqueue_after_commit` defaults to False (`frappe/utils/background_jobs.py:67`). In principle a worker could start before the request commits and build slips without the new Additional Salary **(unverified race)**. A queued run needs **workers**, not the scheduler.
- `refresh_draft_slips` re-saves every draft **synchronously** in the Submit request (87 NGI slips, each running §2.3), which risks a request timeout **(unverified)**.
- A failure inside HRMS's slip creation or submission rolls back, sets the entry to Failed and stores `error_message` with a link to the Error Log.
- Cancelling an entry with more than 50 slips is queued.
- `create_additional_salaries` is called with `commit=False` from the run. `measure_sheet` and `measure_pending` commit by themselves.

---

## 9. Gotchas, silent failures, error messages

### 9.1 Silent failures (no error, wrong money)

| # | What | Why | Code |
|---|---|---|---|
| 1 | OT 0 for a sheet made ahead of the day | Measured only on submit for past dates, or by the daily job | `overtime_settlement.py:213`, `:224` |
| 2 | A component not in the employee's structure is not paid | Non-allowance attendance components (other than OT and the late fine) need a structure row | `_gets` `attendance_allowance.py:752` |
| 3 | Allowance not paid | No row on the assignment, or `effective_from` in the future | `allowance.py:285` |
| 4 | Pay lost on unmarked days, or not | `consider_unmarked_attendance_as` (Present) and `include_holidays_in_total_working_days` exist only as site data | Payroll Settings |
| 5 | A leaver's tax is projected to the year end | The BS override counts months to `payroll_period.end_date`, not the relieving date | `rdp:…/salary_slip_bs.py:246` |
| 6 | Payout tax on **submit** may differ from the draft | At docstatus 1 `apply_employee_allowances` returns False (`salary_slip.py:48`), so the merged-month projection in `build_payout_slip` (`special_payout.py:279`) leaves out the fixed allowances (HRA, Dearness …). This matters only where the payout straddles a slab boundary; the payout test uses an employee without allowances **(read from code, not reproduced)** | `special_payout.py:279` |
| 7 | Advance shows "returned" though no slip paid it | HRMS updates `return_amount` on Additional Salary submit, at slip creation; cancelling the Payroll Entry does not cancel the recovery | §2.7 |
| 8 | A paid Dashain or encashment cannot be re-run after cancelling its entry | The Payroll Adjustment and Leave Encashments stay submitted and count as "already paid" | `festival_allowance.py:204`, `leave_encashment.py:284` |
| 9 | Dashain paid twice | Unticking `disabled` on a payout Additional Salary puts it on the monthly slip too | `special_payout.py:50` (docstring) |
| 10 | A slip made by hand is refused | HRMS's `check_existing` compares every slip when there is no entry, so a payout slip that month blocks it | `hrms:…/salary_slip.py:300` |
| 11 | SST charged for a whole year | `custom_ssf_applicable` wrong on the assignment | slab row 1 |
| 12 | 83/84 rates in 84/85 | The slab comes from the assignment; `year_rollover` must make new assignments | `year_rollover.py:50` |
| 13 | The late fine reduces the salary expense | It is mapped to the salary expense account (by design) | `onboarding.py:652` |
| 14 | Arrears without SSF | SSFA and SSF are not in `monthly_increase` | `salary_revision.py:257` |
| 15 | A new site seeds tea as "Do Not Pay" on holidays | `COMPONENTS` in onboarding still says so, while the rule since 2026-10-15 is Pay | `onboarding.py:142` |
| 16 | Old Ashwin dates | Entries and slips made with nepali-datetime 1.0.8.4 end Ashwin on 2026-10-16. With the BS engine on, re-saving such a draft entry now fails "Posting date is in another BS month" (the period is 09-17 → 10-17) **(unverified on avinas1)**. The tests hard-code `ASHWIN = ("2026-09-17", "2026-10-16")` | `test_special_payout.py:18` |
| 17 | Leftover draft bank entry | Cancelling the Payroll Entry cancels only submitted JEs | `hrms:…/payroll_entry.py:144` |
| 18 | The daily breakdown is wrong but the save succeeds | Failures go to the Error Log | `daily_breakdown.py:75` |
| 19 | 0.01 more SST | HRMS's "+1" on a 0-based band | `hrms:…:2227` |
| 20 | Retirement cap off without a word | Untick `custom_is_retirement_contribution` and no cap applies (as on demo) | `tax_relief.py:57` |

### 9.2 Messages that send users to a button that no longer exists

The "Prepare Payroll Inputs" button is gone; the run posts inputs itself. These still name it:

- `hr/punch_correction.py:659` and `hr/leave_from_report.py:190` (user-facing): "Run Prepare Payroll Inputs on its Payroll Entry before submitting". The right advice is "press Submit Salary Slip; it re-posts first".
- Docstrings and comments: `payroll/salary_slip.py:21`, `payroll/allowance.py:34,37,61,482`, `payroll/daily_breakdown.py:17,208`, `report/avinas_salary_statement/avinas_salary_statement.py:18`, `patches/setup_additional_salary_quantity.py:3,29` (the Quantity field's description), `patches/allowance_rate_list.py:125`.
- Endpoints with no caller left: `attendance_allowance.trigger_for_payroll_entry` (`:79`), `leave_encashment.encash_for_payroll_entry` (`:236`; its docstring still describes a "Leave Encashment button"), `festival_allowance.get_defaults` (`:232`, "the dialog"). `make_festival_adjustment` (`:244`) is whitelisted but called only from `_pay_dashain`.

### 9.3 Error messages and their causes

`frappe.throw` texts in the payroll path:

| Message | Raised at | Cause |
|---|---|---|
| Payroll cannot run yet: "Nothing was posted. Fix these …" | `payroll_entry.py:267` | an assignment starting after the slip start; no assignment; no Department; no Payroll Section (when the company posts by section) |
| Set Payroll Section on the Department of these employees … | `payroll_entry.py:507` | the accrual JE needs the section |
| Nothing to pay (entry) | `payroll_entry.py:181` | a payout entry where nobody is due |
| Nothing to pay (slip): "… has no … to be paid between …" | `special_payout.py:181` | a payout slip without payout Additional Salary |
| … is paid once, on its own payout; it cannot be recurring. | `special_payout.py:117` | recurring Dashain or encashment |
| … is not a festival allowance … / … is paid in …; this entry is for … | `payroll_entry.py:302`, `:308`; `festival_allowance.py:259`, `:263` | wrong component or month |
| Draft … already holds … for this year … | `festival_allowance.py:285` | another entry's Dashain draft |
| The Payroll Entry has no employees yet / This Payroll Entry is cancelled. | `festival_allowance.py:293`, `:255`; `leave_encashment.py:262`, `:254` | — |
| Choose the Payment Account and press Update … / Payment Account … is a … account … | `payroll_entry.py:458`, `:461` | bank entry |
| Duplicate Entry: Salary Slip already exists for … | `payroll_entry.py:359` | same kind, same dates |
| Set Default Payroll Payable Account on Company … | `payroll_month.py:68` | — |
| Posting date is in another BS month | `bs_period_guard.py:53` | posting date outside the paid month |
| Slip and payroll entry disagree on the month | `bs_period_guard.py:77` | dates changed after the slips were made |
| No income tax Salary Component is set up, so it cannot be overridden. | `income_tax.py:184` | override without a tax component |
| Women's Tax Rebate is only for female employees … | `tax_relief.py:205` | Employee validate |
| Cannot work out the hourly wage for …: no month length given | `attendance_allowance.py:520` | no month days (should not happen; logged as skipped) |
| Choose the Allowance Kind / Accounts row … is not an account of … / … is a group account | `allowance.py:392`, `:383`, `:387` | Salary Component |
| Wrong Type: … must be Earning / Deduction · Not Tax-Exempt | `allowance.py:421`, `:431` | OT as a deduction, a fine as an earning, or either exempt |
| … row …: … is an allowance. List its rate under Allowance Rates … | `allowance.py:475` | allowance in a structure |
| … is not an allowance / … is a … allowance and is paid when entered / rate cannot be negative / listed twice | `allowance.py:445–461` | rate tables |
| Use a Salary Revision | `allowance.py:511` | a listed rate edited on a submitted structure |
| Allowances row …: type …'s rate for this person, or remove the row … | `allowance.py:537` | no rate on the row or the structure |
| … already encashes this allocation · Leave is encashed at year end … or at separation … · … is not encashed at … · … has no salary assignment on … | `leave_encashment.py:133`, `:136`, `:144`, `:148` | encashment date or settings |
| No Leave Period for … covers … | `leave_encashment.py:295` | logged as left out |
| A salary revision must start on the first day of a BS month … | `salary_revision.py:236` | — |
| Row …: amount must be more than zero · … already has a … row · … belongs to … · is more than …'s basic … capped at 100 % | `payroll_adjustment.py:41–57` | — |
| Rows the policy does not allow · Authorised Twice · … is not approved yet, so there is nothing to settle | `overtime_sheet.py:75`, `:92`; `overtime_settlement.py:64` | — |
| Tick either Overtime Eligible or Replacement Leave …, not both | `hr/overtime.py:139` | Employee |

HRMS messages users meet: "Please set account in Salary Component …" (`hrms:…/payroll_entry.py:317`); "Account type cannot be set for payroll payable account …" (`:101`); "Cannot submit. Attendance is not marked for some employees." (`:62`); "Salary Slip of employee … already created for this period" (`hrms:…/salary_slip.py:330`); "Net Pay cannot be less than 0" (`:209`); "Income Tax Slab not set in Salary Structure Assignment …" (`:1622`); "No employees found …" (`payroll_entry.py:202`). The user-facing fixes for all of these are in `docs/user-guide/10-troubleshooting.md` (see §11 for the rows that are out of date).

---

## 10. Open questions and pending work

From `docs/session-2026-10-12-payroll.md` §13, with what has changed since:

- **D1: turn the scheduler on for avinas1?** Still open, and more urgent now that OT measuring depends on it (§8.1).
- **D2:** was Bhadra paid from Excel? If so, its submitted journals double-count it.
- **D3:** does a non-SSF person get the 20 % in cash? The system pays it to nobody without SSF.
- **D4:** cap on the late fine (none). **D5:** fine leaving early (yes today). **D6:** warn above 4 h/day or 24 h/week of OT (no).
- **Accountant:** the Shrawan 2083 openings (`taxable_earnings_till_date` / `tax_deducted_till_date`); the account mapping for NGG, NGK, NGN Tea/Meal and GLMI/GEPL/SGU (§6.4); a CIT deduction component if anyone pays CIT through payroll.
- **84/85:** add `"84/85"` to `TAX_SLABS_BY_YEAR` and `WOMEN_REBATE_BY_YEAR` (`income_tax.py:45`, `:54`) or enter the slabs by hand; create Fiscal Year 84/85 with all seven companies; run `setup_year('84/85')` before 2027-07-17.
- **Done since 2026-10-12:** leave encashment at year end (`c3a5585`); paying Dashain in its own run (`c3a5585`).
- **Raised by this review:**
  1. a leaver's tax projection (§9 #5);
  2. the payout tax on submit (§9 #6);
  3. SSF on arrears (§9 #14);
  4. cancel leaves recoveries and payouts behind (§2.7);
  5. the >30-employee enqueue race (§8.3);
  6. the stale "Prepare Payroll Inputs" messages (§9.2);
  7. onboarding's tea "Do Not Pay" seed (§9 #15);
  8. `ASHWIN` dates in the tests after nepali-datetime 1.0.8.5 (§9 #16);
  9. the demo NGI SSF / SSF Addition accounts (§6.4).
- **Not built:** a setup-checklist report; tuition, remote-area and disability reliefs; the six-stage reconciliation against real figures; the Falgun parity drop after 8 October (not investigated).

---

## 11. Stale docs

> The standalone payroll docs named below (payroll-handover, payroll-ngi, allowances, overtime-sheet, employee-category, session-2026-10-12-payroll and the three HTML manuals) were removed on 2026-10-29; this file replaces them. They remain in git history.

Audited against the code on 2026-10-29 (`202724b`). Severity: **WB** = describes wrong behaviour, **SW** = stale wording (mostly the removed "Prepare Payroll Inputs" button), **U** = could not be verified (needs avinas1 data). Grouped; the most consequential rows first.

### 11.1 Cross-cutting (true of most payroll docs)

| Claim in the docs | What the code does | Sev |
|---|---|---|
| HR presses **Prepare Payroll Inputs** (`trigger_for_payroll_entry`) before submitting; re-press after attendance changes | No button (`public/js/payroll_entry.js:243` adds none). Inputs post inside `create_salary_slips` / `submit_salary_slips` (`payroll/payroll_entry.py:411`, `:428`) via `prepare_payroll_inputs` (`:50`), atomically (`commit=False`) | WB/SW — in system-reference 01, 01b, 02, 03, 04, 05, 06, 07, 08, 09, README, impact-matrix, hooks-inventory; salary-code-map; allowances.md; payroll-ngi.md; payroll/README.md; session-2026-10-12 |
| Dashain / leave encashment via **buttons** on the Payroll Entry, writing **drafts** HR submits, paid on the month's (Bhadra/Ashwin/Ashadh) slip | A separate **Payout** Payroll Entry (`custom_payout_type`); `_pay_dashain` / `_pay_leave_encashment` **submit** the Payroll Adjustment / Leave Encashments; paid on their own payout slip (`special_payout.py`) | WB — 01b:139,322; 08-changes-over-time:200,204,276,283; salary-code-map §11; allowances.md:60; payroll-handover:280-283; payroll-ngi:340; user-guide 10-troubleshooting:133; payroll/README:10 |
| OT rounded to the nearest ½ hour (7:53 → 8) | Exact to the second (`hr/overtime.py:320`, `hr/shift_day.py`) | WB — 05 §5.6.1; payroll-handover:77; payroll-ngi:267 |
| Tea not paid on a worked holiday (Tea `Pay on Holiday` = Do Not Pay) | Paid unless the component says Do Not Pay; blank = Pay (`attendance_allowance.py:309`); commit `f85d16d` says avinas1's Tea is Pay. Only onboarding still seeds Do Not Pay (`onboarding.py:142`) | WB/U — 01b:164,179; 02:240; 05 §5.6.1; 06:357; impact-matrix:38,73,128; salary-code-map:294; allowances.md:15 |
| A holiday on an OT sheet earns **2 meals** (even at 0 measured hours) | 8 h → 2, 6 h → 1, less → 0, first IN to last OUT (`HOLIDAY_MEAL_HOURS` `attendance_allowance.py:426`) | WB — 04-overtime:220; impact-matrix; salary-code-map 4.14; allowances.md:97 |
| Late fine only for people whose structure lists the Late Fine row | Everyone not Late Fine Exempt (`_gets` `attendance_allowance.py:746`) | WB — 01b:265; 05 §5.6.3, 5.9; salary-code-map 4.6 |
| Overtime needs an Overtime row on the assignment; rate = Rate Basis × Multiplier (1.5) | No row needed; 1.5 is a constant (`OVERTIME_MULTIPLIER` `:49`), the component's multiplier is ignored for OT (`:767`) | WB — 04-overtime:252; 01b:167; impact-matrix:126; salary-code-map 4.7/4.8, 295 |
| Advance recovery = min(instalment, outstanding) | A leaver repays the whole balance in the relieving month (`advance_recovery.py:90`), cut to net 0 by `recovery_cap` | WB — 05 §5.7; 08:252; salary-code-map 4.19; payroll-ngi:289 |
| A recovery larger than the last pay blocks submission; reduce it by hand | `cap_recoveries` cuts it and names the rest (`recovery_cap.py:45`) | WB — user-guide 08:189 (ch.10 is right) |
| Line numbers / hrms "v15.49.2" | hrms 15.59.0 is installed; ~141 of ~177 `hooks.py#L` anchors and ~111 of 226 hrms anchors are off (hooks.py by +5 up to ~line 400, ~+30 near `override_doctype_class`); avinashgroup_app code anchors are essentially all correct | SA — all system-reference files, salary-code-map:3,10 |

### 11.2 Per document

| Doc | Says | Code does | Sev |
|---|---|---|---|
| system-reference/06-salary-slip.md §6.0 (20-32) | Validate order starts audit → `add_employee_allowances` | `set_slip_payout_type` (before_validate) and `build_payout_slip` come first (`hooks.py:374-375`); allowances/reliefs skip payout slips | WB |
| system-reference/hooks-inventory.md:14, 16-30, 139-150, 164-165, 237, 270-272 | Overrides only Payroll Entry & Leave Policy Assignment; no payout hooks; Additional Salary has mark/link only; JS calls `get_defaults`, `make_festival_adjustment`, `encash_for_payroll_entry`, `trigger_for_payroll_entry` | Also Leave Encashment & Compensatory Leave Request (`hooks.py:572,577`); `tag_additional_salary` (`:503`) sets `disabled=1`; the JS calls none of those endpoints | WB |
| system-reference/05-payroll-entry.md:21, 72, 5.2, 5.5, 5.8 | before_submit = attendance warning → HRMS; "Pay Dashain" / "Settle Leave (encash or recover)" on the salary entry; one failure leaves allowances committed; HRMS's Get Employees | Also `check_ready_for_slips` / `check_payout`; salary entry clears Pay Dashain and Settle Leave only recovers; run is atomic; Get Employees overridden per slip kind (`payroll_entry.py:371`) | WB |
| system-reference/07-after-the-slip.md §7.1 | Submit Salary Slip is "All HRMS"; negative slips stay draft | Ours first: checks, re-post, `refresh_draft_slips`, `cap_recoveries` (`payroll_entry.py:428-444`) | WB |
| system-reference/08-changes-over-time.md 8a | Separation encashment only on the stock form | `encash_month` also makes Separation encashments on the payout entry | WB |
| system-reference/09-cross-cutting.md:175, 219 | Nothing posts tea until HR presses the button; permission row for the button | Posted by slip create/submit; no button | WB |
| system-reference/01-masters.md:61,73 | OT Eligible Only tick governs OT | OT is always OT-only; the late fine ignores the tick (`:670`) | SW |
| system-reference/01b-pay-masters.md §6.5, §8, §9 config | avinas1 counts and mappings (2026-10-12) | Not re-checkable here | U |
| salary-code-map.md §8, 5.2/5.7, 11.10 | `add_employee_allowances` first; before_submit contents; `encash_for_payroll_entry` as a step | `build_payout_slip` first; `check_ready_for_slips`; endpoint unused | WB |
| allowances.md:16, 123 | Structure carries a Late Fine line; every slip has a Daily Breakdown | Not needed; payout slips have none (`daily_breakdown.py:70`) | SW |
| payroll-handover.md:80, 191 | Engine writes Payroll Adjustment rows via an Allowance Category rate chain; missing category → no tea | Writes submitted Additional Salary; rate from the assignment row; Allowance Category unused | WB |
| payroll-ngi.md:283-287 | Tea/Meal from Allowance Category; Daily Wage paid | Assignment row Rate; Daily Wage disabled, paid outside payroll | WB |
| overtime-sheet.md:102, 105-109 | Payroll reads `get_measured_hours`; paying OT is future work | Payroll reads `_authorised_overtime_hours` (`attendance_allowance.py:463`); `get_measured_hours` has no caller; built | WB |
| session-2026-10-12-payroll.md:218, 391-392, 410-411 | Leave encashment and Dashain payment not built; button-permission test plan | Both built (`c3a5585`); button gone | SW |
| user-guide/04-overtime-and-meals.md:109 | Meal falls back to the company rate | No assignment Meal row → no meal (`_gets` `:750`) | WB |
| user-guide/06-salary-slip.md | Every slip has a Daily Breakdown; no mention of payout slips | Payout slips: payout + tax only, no breakdown | SW |
| user-guide/08 §8.5 | "Leave encashment for this month opens on …" | Raised only by the unused `encash_for_payroll_entry`; the payout path logs "not before …" then throws "Nobody on this entry has …" | SW |
| user-guide/10-troubleshooting.md "Everyone is paid for fewer days (26 of 31)" | Cause: Include holidays in total working days off | With the BS engine on, `total_working_days` is always the BS month length; 26/31 means Nepal HRMS Settings is **off** (as on demo) | WB |
| payroll/README.md:8, 13, 15 | Entry point Prepare Payroll Inputs; daily_breakdown "last"; payroll_entry = journal + payouts | Slip create/submit; `set_bs_dates` runs after it; it also posts inputs, pre-checks, caps, guards the bank entry | WB/SW |
| Code docstrings: `salary_slip.py:21`, `allowance.py:33-37,482`, `advance_recovery.py:17`, `attendance_allowance.py:79-115`, `daily_breakdown.py:17,24,208`, `festival_allowance.py:232,246` ("writes only a draft"), `leave_encashment.py:1-5,237-248` ("button … rides this entry's slips"), `payroll_entry.py:25-27`, `special_payout.py:28,169` / `hooks.py:372,400` ("first"/"last") | Button-era wording, or order claims | As §2 | SW (festival/leave_encashment: WB) |

Full per-line audit (1,734 anchors checked) was produced alongside this document and is summarised here; re-run `python3 docs/tools/check_reference_links.py` for the doc-tooling view.

---

## 12. How to test

### 12.1 Test files

| File | Tests | Covers |
|---|---|---|
| `avinashgroup_app/payroll/test_allowance.py` | 26 | allowance kinds, rate tables, assignment rows, proration |
| `avinashgroup_app/payroll/test_payroll_checks.py` | 16 | re-run removes what is no longer due, permission on `trigger_for_payroll_entry`, proration on re-save, tax-history warning, new-year slab |
| `avinashgroup_app/payroll/test_tax_relief.py` | 5 | women's rebate, insurance caps |
| `avinashgroup_app/payroll/test_festival_allowance.py` | 17 | service factor, Dashain rows and rules |
| `avinashgroup_app/payroll/test_leave_encashment.py` | 8 | pricing, occasions |
| `avinashgroup_app/payroll/test_leave_recovery.py` | 5 | negative balances |
| `avinashgroup_app/payroll/test_payroll_recoveries.py` | 6 | paid months skipped, leavers repay in full, no slip below zero |
| `avinashgroup_app/payroll/test_special_payout.py` | 7 | payout slip contents and tax, order independence, duplicate refusal, leaver encashment on its own slip (submits real entries, rolled back) |
| `avinashgroup_app/hr/test_*.py` | 52 | BS calendar, leave from report, punch correction, replacement leave, shift rotation |

These tests run against the site's real data: they pick existing NGI employees and structures, skip when the data is missing, and roll back. Many hard-code NGI 83/84 names and dates. **Not run for this document** (they write inside a transaction, and this review was read-only).

### 12.2 The direct runner

`bench run-tests` fails on this bench while building test records (session notes §12), so run the suites directly. Adapted to this machine: replace the site with `avinas1` where it exists. The cwd must be `sites/`, because Frappe's logger paths are relative to it:

```bash
cd /home/frappe/frappe-bench/sites          # /home/dell/frappe-v15/sites on the avinas1 machine
cat > /tmp/run.py <<'EOF'
import sys, unittest, frappe
frappe.init(site="demo-nggroup.raindropinc.com", sites_path="."); frappe.connect(); frappe.flags.in_test = True
s = unittest.TestSuite()
for n in sys.argv[1:]: s.addTests(unittest.defaultTestLoader.loadTestsFromName(n))
ok = unittest.TextTestRunner(verbosity=2).run(s).wasSuccessful()
frappe.db.rollback(); sys.exit(not ok)
EOF
../env/bin/python /tmp/run.py \
  avinashgroup_app.payroll.test_payroll_checks \
  avinashgroup_app.payroll.test_allowance \
  avinashgroup_app.payroll.test_tax_relief \
  avinashgroup_app.payroll.test_special_payout \
  avinashgroup_app.payroll.test_festival_allowance \
  avinashgroup_app.payroll.test_leave_encashment \
  avinashgroup_app.payroll.test_leave_recovery \
  avinashgroup_app.payroll.test_payroll_recoveries
```

Some tests stub `frappe.db.commit` themselves (e.g. `TestPrepareInputsRerun`), because the engine commits. Others submit Payroll Entries. Run them only on a copy, never on a live site.

### 12.3 Other checks

- `python3 docs/tools/check_reference_links.py` checks the `#L` anchors in `docs/system-reference` (session notes §14).
- A slip's arithmetic without saving it: build a Salary Slip in memory and call `slip.run_method("validate")`, as `test_special_payout.slip_in_memory` does (`test_special_payout.py:89`). Then read `total_taxable_earnings`, `remaining_sub_periods`, `custom_retirement_excess` and the tax row.
- The resolved hook order: `frappe.get_doc_hooks()["Salary Slip"]` in a standalone script (this is how §2.3 was checked).
