# Hooks inventory (HR and payroll)

Every hook in [`app_name`](../../avinashgroup_app/hooks.py#L4) in `hooks.py` that touches HR or payroll, plus the HR hooks that HRMS and `rdp_common_app` register on the same doctypes. Each row links the line that registers the hook and the line that defines the handler. Line numbers were checked on `develop` on 2026-10-12, with hrms 15.49.2 and rdp_common_app `develop`.

Back to the [README](README.md). The impact of each field these hooks read is on [impact-matrix.md](impact-matrix.md).

## How Frappe orders these hooks

You need this to read the tables below.

1. **Apps run in install order.** On avinas1 `tabInstalled Application` is `frappe, erpnext, avinashgroup_app, rdp_common_app, hrms`. So for any doctype, our handlers run **before** HRMS's handlers for the same event. HRMS was installed after us.
2. **Within one event, the controller method runs first, then the doctype's own hooks, then the `"*"` wildcard hooks.** See [`composer`](../../../frappe/frappe/model/document.py#L1361) in Frappe's `Document.hook`. Server Scripts run after all of these, but avinas1 has none (`tabServer Script` is empty).
3. **Within our app, handlers run in the order `hooks.py` registers them.** `doc_events` starts as [`AuditEventMapper.get_doc_events`](../../avinashgroup_app/utils/audit_file_manager.py#L471), so the audit handlers come first on every audited doctype. After that come the `_add_doc_event` calls, top to bottom.
4. **`override_doctype_class`: the last app wins.** Only one class per doctype can be active. We override Payroll Entry and Leave Policy Assignment. `rdp_common_app` overrides Salary Slip. HRMS overrides Employee. Nobody fights over a doctype.

So, for example, a Salary Slip's `validate` runs like this:

| # | Handler | Source |
|---|---|---|
| 0 | `SalarySlip.validate` (HRMS), as inherited/overridden by `BSSalarySlip` | controller |
| 1 | `audit_file_manager.validate`: company lock and company match | ours, audit |
| 2 | [`add_employee_allowances`](../../avinashgroup_app/hooks.py#L355) | ours |
| 3 | [`apply_tax_reliefs`](../../avinashgroup_app/hooks.py#L362) | ours |
| 4 | [`apply_income_tax_override`](../../avinashgroup_app/hooks.py#L366) | ours |
| 5 | [`validate_salary_slip`](../../avinashgroup_app/hooks.py#L373) (BS period guard) | ours |
| 6 | [`build_daily_breakdown`](../../avinashgroup_app/hooks.py#L376) | ours |
| 7 | [`set_bs_dates`](../../avinashgroup_app/hooks.py#L463) | ours, registered later in the file |
| 7b | erpnext's `"*"` validate handlers (e.g. service-level-agreement `apply`) | erpnext, wildcard (installed before us) |
| 8 | [`apply_engine_numbering`](../../avinashgroup_app/hooks.py#L422) | ours, wildcard |
| 9 | [`dynamic_approval.validate`](../../avinashgroup_app/hooks.py#L477) | ours, wildcard |

HRMS and rdp_common_app register no Salary Slip `doc_events`. Details are in [06-salary-slip.md](06-salary-slip.md).

## 1. Class overrides (`override_doctype_class`)

| Doctype | Class | Registered | Defined | Why |
|---|---|---|---|---|
| Payroll Entry | `AvinashPayrollEntry` | [`AvinashPayrollEntry`](../../avinashgroup_app/hooks.py#L509) | [`AvinashPayrollEntry`](../../avinashgroup_app/payroll/payroll_entry.py#L41) | Fills the period from a BS month and warns about missing attendance. Splits the accrual journal by section (O/O, S/D, F/P accounts), and refuses a bank entry without a Bank/Cash account. See [05-payroll-entry.md](05-payroll-entry.md) and [07-after-the-slip.md](07-after-the-slip.md). |
| Leave Policy Assignment | `BSLeavePolicyAssignment` | [`BSLeavePolicyAssignment`](../../avinashgroup_app/hooks.py#L507) | [`BSLeavePolicyAssignment`](../../avinashgroup_app/hr/leave_policy_assignment_bs.py#L40) | A mid-year assignment back-fills earned leave in BS months, matching the BS accrual job. See [01-masters.md](01-masters.md). |
| Salary Slip | `BSSalarySlip` (rdp_common_app) | [`BSSalarySlip`](../../../rdp_common_app/rdp_common_app/hooks.py#L149) | [`BSSalarySlip`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py#L47) | Puts slips on BS months: the period, `total_working_days` = BS month length, the proration denominator, and the tax months left. See [06-salary-slip.md](06-salary-slip.md). |
| Employee | `EmployeeMaster` (HRMS) | [`EmployeeMaster`](../../../hrms/hrms/hooks.py#L150) | [`EmployeeMaster`](../../../hrms/hrms/overrides/employee_master.py#L12) | Stock HRMS. Listed because our Employee `validate` hooks run alongside it. |

**Why the slip hooks are hooks, not a class.** `rdp_common_app` already owns the Salary Slip class, and a second `override_doctype_class` entry would silently replace it (the last app wins). That is why [`add_employee_allowances`](../../avinashgroup_app/hooks.py#L355) and the tax hooks are `validate` doc_events. The comment above that line in `hooks.py` says so.

## 2. Document events: HR and payroll doctypes

### Employee Checkin

| Event | Handler (registration) | Defined | Purpose |
|---|---|---|---|
| after_insert, on_update, after_delete | [`checkin_{_event}`](../../avinashgroup_app/hooks.py#L337) | [`checkin_after_insert`](../../avinashgroup_app/biometric/attendance_sync.py#L305), [`checkin_on_update`](../../avinashgroup_app/biometric/attendance_sync.py#L319), [`checkin_after_delete`](../../avinashgroup_app/biometric/attendance_sync.py#L339) | Keep the day's IN/OUT alternation (last punch OUT). Refresh the computed values of an existing Present or Half Day Attendance when punches are added, edited, deleted or arrive late. **Never changes status.** The device pipeline sets `in_biometric_day_reconcile` so these skip during bulk intake. See [02-checkin-to-attendance.md](02-checkin-to-attendance.md). |

### Attendance

Registered through `attendance_events` ([`attendance_events`](../../avinashgroup_app/hooks.py#L226)). They are on `validate`, **not `before_save`**: HRMS auto attendance inserts Attendance already submitted, and that path runs `before_submit`, never `before_save` (see the comment at lines 218–222 of `hooks.py`).

| Order | Handler (registration) | Defined | Purpose |
|---|---|---|---|
| 0 | audit `validate` (company lock and match) | [`validate`](../../avinashgroup_app/utils/audit_file_manager.py#L582) | Attendance is in [`"Attendance"`](../../avinashgroup_app/utils/audit_file_manager.py#L20) |
| 1 | [`set_holiday_flag`](../../avinashgroup_app/hooks.py#L228) | [`set_holiday_flag`](../../avinashgroup_app/payroll/attendance_allowance.py#L451) | Ticks `custom_worked_on_holiday` when the date is in the employee's (or company's) holiday list. Feeds the tea / meal / holiday-pay rules. |
| 2 | [`set_shift_deviation_fields`](../../avinashgroup_app/hooks.py#L229) | [`set_shift_deviation_fields`](../../avinashgroup_app/biometric/attendance_override.py#L8) | Fills a missing shift from the roster and writes the four late/early-entry/exit `custom_*` fields. |
| 3 | [`enforce_late_arrival_half_day`](../../avinashgroup_app/hooks.py#L230) | [`enforce_late_arrival_half_day`](../../avinashgroup_app/biometric/attendance_override.py#L55) | In more than `custom_half_day_if_late_by_hours` (2 h) after shift start → Half Day, with the other half Absent. Late Excused undoes it. |
| 4 | [`half_day_when_working_on_leave`](../../avinashgroup_app/hooks.py#L234) | [`half_day_when_working_on_leave`](../../avinashgroup_app/biometric/attendance_override.py#L145) | On approved leave but punched in → Half Day, other half Present (policy 3.4). |
| 5 | wildcard numbering, dynamic approval | see §3 | |

### Employee

| Order | Handler (registration) | Defined | Purpose |
|---|---|---|---|
| 0 | audit `validate` | [`validate`](../../avinashgroup_app/utils/audit_file_manager.py#L582) | Employee is audited ([`"Employee"`](../../avinashgroup_app/utils/audit_file_manager.py#L28)). |
| 1 | [`validate_unique_device_id`](../../avinashgroup_app/hooks.py#L343) | [`validate_unique_device_id`](../../avinashgroup_app/biometric/employee.py#L13) | One Attendance Device ID per company, so a punch maps to one person. |
| 2 | [`validate_womens_tax_rebate`](../../avinashgroup_app/hooks.py#L346) | [`validate_womens_tax_rebate`](../../avinashgroup_app/payroll/tax_relief.py#L195) | The Women's Tax Rebate tick is only allowed on a female employee. |
| 3 | [`validate_employee_holiday_rule`](../../avinashgroup_app/hooks.py#L349) | [`validate_employee_holiday_rule`](../../avinashgroup_app/hr/overtime.py#L136) | Overtime Eligible and Replacement Leave for Holiday Work are never ticked together (policy 2.2/2.5). |
| 4 | [`set_bs_dates`](../../avinashgroup_app/hooks.py#L463) | [`set_bs_dates`](../../avinashgroup_app/hr/bs_dates.py#L75) | BS (miti) copies of the AD dates. |
| 5 | HRMS [`validate_onboarding_process`](../../../hrms/hrms/hooks.py#L200) | [`validate_onboarding_process`](../../../hrms/hrms/overrides/employee_master.py#L29) | Stock HRMS. Runs after ours (install order). |

### Shift Type, Shift Assignment, Shift Request

| Doctype | Event | Handler (registration) | Defined | Purpose |
|---|---|---|---|---|
| Shift Type | validate | [`clear_invented_late_cutoff`](../../avinashgroup_app/hooks.py#L458) | [`clear_invented_late_cutoff`](../../avinashgroup_app/hr/shift_type_guard.py#L37) | Saving a Shift Type fills a blank Late Arrival Cutoff with the clock time of the save, which would half-day everyone from that minute. This handler clears it. |
| Shift Request | validate | [`validate_request`](../../avinashgroup_app/hooks.py#L430) | [`validate_request`](../../avinashgroup_app/hr/shift_change.py#L41) | Checks a "work a different shift" request. |
| Shift Request | validate | [`guard_paid_period`](../../avinashgroup_app/hooks.py#L439) | [`guard_paid_period`](../../avinashgroup_app/hr/shift_backdate.py#L80) | Refuses a backdated change that reaches into an already-paid period. |
| Shift Request | before_submit | [`prepare_request`](../../avinashgroup_app/hooks.py#L431) | [`prepare_request`](../../avinashgroup_app/hr/shift_backdate.py#L117) | Records which past days the change touches. Runs before the split below. |
| Shift Request | before_submit | [`make_room_for_request`](../../avinashgroup_app/hooks.py#L432) | [`make_room_for_request`](../../avinashgroup_app/hr/shift_change.py#L58) | Splits the standing open-ended Shift Assignment so HRMS can insert the requested one. |
| Shift Request | on_submit | [`rebuild_for_request`](../../avinashgroup_app/hooks.py#L440) | [`rebuild_for_request`](../../avinashgroup_app/hr/shift_backdate.py#L140) | Re-marks the past days' attendance on the new shift. |
| Shift Request | before_cancel | [`prepare_request`](../../avinashgroup_app/hooks.py#L431) | [`prepare_request`](../../avinashgroup_app/hr/shift_backdate.py#L117) | Same as before_submit, for the cancel. |
| Shift Request | on_cancel | [`close_gap_after_cancel`](../../avinashgroup_app/hooks.py#L434) | [`close_gap_after_cancel`](../../avinashgroup_app/hr/shift_change.py#L87) | Re-joins the split standing assignment. |
| Shift Request | on_cancel | [`rebuild_for_request`](../../avinashgroup_app/hooks.py#L440) | [`rebuild_for_request`](../../avinashgroup_app/hr/shift_backdate.py#L140) | Re-marks the past days on the restored shift. |
| Shift Assignment | validate | [`guard_paid_period`](../../avinashgroup_app/hooks.py#L439) | [`guard_paid_period`](../../avinashgroup_app/hr/shift_backdate.py#L80) | Refuses backdating into a paid period. |
| Shift Assignment | on_submit | [`rebuild_for_assignment`](../../avinashgroup_app/hooks.py#L443) | [`rebuild_for_assignment`](../../avinashgroup_app/hr/shift_backdate.py#L159) | Re-marks the affected past attendance. |
| Shift Assignment | before_cancel | [`prepare_assignment_cancel`](../../avinashgroup_app/hooks.py#L444) | [`prepare_assignment_cancel`](../../avinashgroup_app/hr/shift_backdate.py#L149) | Records the days the cancel touches. |
| Shift Assignment | on_cancel | [`rebuild_for_assignment`](../../avinashgroup_app/hooks.py#L443) | [`rebuild_for_assignment`](../../avinashgroup_app/hr/shift_backdate.py#L159) | Re-marks them after the cancel. |

Shift Type is also an audited master ([`"Shift Type"`](../../avinashgroup_app/utils/audit_file_manager.py#L110)). Shift Assignment and Shift Request are filtered by fiscal year (§5).

### Leave Allocation, Leave Application, Leave Policy Assignment

| Doctype | Event | Handler (registration) | Defined | Purpose |
|---|---|---|---|---|
| Leave Allocation, Leave Application | validate | [`validate_gender`](../../avinashgroup_app/hooks.py#L477) | [`validate_gender`](../../avinashgroup_app/hr/statutory_leave.py#L27) | Maternity leave for mothers only, paternity leave for fathers only. |
| Leave Allocation | validate | [`validate_within_policy`](../../avinashgroup_app/hooks.py#L481) | [`validate_within_policy`](../../avinashgroup_app/hr/leave_ceiling.py#L27) | A year can grant no more days than the employee's own Leave Policy (21 + 12, or 8 + 12 at Karnali). |
| Leave Application | validate | [`set_bs_dates`](../../avinashgroup_app/hooks.py#L463) | [`set_bs_dates`](../../avinashgroup_app/hr/bs_dates.py#L75) | BS dates. |
| Leave Application | wildcard | Dynamic Approval | see §3 | The `leave_application_dynamic_approval` patch set Leave Application up for Dynamic Approval. See [09-cross-cutting.md](09-cross-cutting.md). |
| Leave Policy Assignment | class | `BSLeavePolicyAssignment` | §1 | |

Both Leave Allocation and Leave Application are also audited and fiscal-year filtered.

### Overtime Sheet

| Order | Event | Handler (registration) | Defined | Purpose |
|---|---|---|---|---|
| 1 | on_submit | [`replacement_leave.on_sheet_submit`](../../avinashgroup_app/hooks.py#L450) | [`on_sheet_submit`](../../avinashgroup_app/hr/replacement_leave.py#L48) | For officers and admin staff, holiday work becomes a Compensatory Leave Request once attendance shows the day was worked. |
| 2 | on_cancel | [`on_sheet_cancel`](../../avinashgroup_app/hooks.py#L451) | [`on_sheet_cancel`](../../avinashgroup_app/hr/replacement_leave.py#L56) | Withdraws the replacement leave. |
| 3 | on_submit | [`overtime_settlement.on_sheet_submit`](../../avinashgroup_app/hooks.py#L450) | [`on_sheet_submit`](../../avinashgroup_app/hr/overtime_settlement.py#L189) | Measures the never-measured rows. Without this, overtime paid 0 on any sheet where nobody pressed "Measure from Attendance". |

The sheet's own controller (`OvertimeSheet.apply_rules`) runs on validate. See [04-overtime.md](04-overtime.md).

### Salary Component, Salary Structure, Salary Structure Assignment

| Doctype | Event | Handler (registration) | Defined | Purpose |
|---|---|---|---|---|
| Salary Component | validate | [`validate_salary_component`](../../avinashgroup_app/hooks.py#L469) | [`validate_salary_component`](../../avinashgroup_app/payroll/allowance.py#L319) | The allowance kind decides the attendance rule. Attendance-driven components get no payment-days proration and are removed if zero. Section (S/D, F/P) accounts must belong to the row's company. |
| Salary Structure | validate | [`validate_salary_structure`](../../avinashgroup_app/hooks.py#L470) | [`validate_salary_structure`](../../avinashgroup_app/payroll/allowance.py#L381) | No allowances in Earnings/Deductions (they live in Allowance Rates). Attendance-driven rows are tags with no amount. |
| Salary Structure | before_update_after_submit | [`guard_structure_rates`](../../avinashgroup_app/hooks.py#L471) | [`guard_structure_rates`](../../avinashgroup_app/payroll/allowance.py#L410) | On a submitted structure, a listed rate changes only through a Salary Revision. |
| Salary Structure Assignment | validate | [`validate_assignment_allowances`](../../avinashgroup_app/hooks.py#L472) | [`validate_assignment_allowances`](../../avinashgroup_app/payroll/allowance.py#L436) | The Allowances table takes allowances only, once each. A blank rate takes the structure's; a rate still 0 is refused. |

Salary Structure is audited. Salary Structure Assignment is fiscal-year filtered. See [01b-pay-masters.md](01b-pay-masters.md).

### Payroll Entry

| Order | Event | Handler | Defined | Purpose |
|---|---|---|---|---|
| 0 | validate (class) | `AvinashPayrollEntry.validate` | [`validate`](../../avinashgroup_app/payroll/payroll_entry.py#L42) | Fills the period from the BS month, calls HRMS's validate, then warns about missing attendance. |
| 1 | validate | audit | [`validate`](../../avinashgroup_app/utils/audit_file_manager.py#L582) | [`"Payroll Entry"`](../../avinashgroup_app/utils/audit_file_manager.py#L52) |
| 2 | validate | [`validate_payroll_entry`](../../avinashgroup_app/hooks.py#L372) | [`validate_payroll_entry`](../../avinashgroup_app/payroll/bs_period_guard.py#L45) | Refuses an entry whose dates are not the BS month of its posting date. |
| 3 | validate | [`set_bs_dates`](../../avinashgroup_app/hooks.py#L463) | [`set_bs_dates`](../../avinashgroup_app/hr/bs_dates.py#L75) | BS dates. |

### Salary Slip

The order is in the table at the top of this page. The handlers:

| Handler (registration) | Defined | Purpose |
|---|---|---|
| [`add_employee_allowances`](../../avinashgroup_app/hooks.py#L355) | [`add_employee_allowances`](../../avinashgroup_app/payroll/salary_slip.py#L33) | Fixed (Monthly, % of Initial Basic) allowances from the assignment's Allowances table, then the slip is recalculated. |
| [`apply_tax_reliefs`](../../avinashgroup_app/hooks.py#L362) | [`apply_tax_reliefs`](../../avinashgroup_app/payroll/tax_relief.py#L77) | Retirement-contribution cap and women's rebate, which HRMS's slab cannot express. |
| [`apply_income_tax_override`](../../avinashgroup_app/hooks.py#L366) | [`apply_income_tax_override`](../../avinashgroup_app/payroll/income_tax.py#L154) | Keeps the computed tax and lets HR type a tax figure by hand. Runs after the reliefs so the hand figure wins. |
| [`validate_salary_slip`](../../avinashgroup_app/hooks.py#L373) | [`validate_salary_slip`](../../avinashgroup_app/payroll/bs_period_guard.py#L70) | A slip's month must equal its Payroll Entry's. |
| [`build_daily_breakdown`](../../avinashgroup_app/hooks.py#L376) | [`build_daily_breakdown`](../../avinashgroup_app/payroll/daily_breakdown.py#L64) | The day-by-day table (Salary Slip Day). It only describes the slip and never blocks a save. |
| [`set_bs_dates`](../../avinashgroup_app/hooks.py#L463) | [`set_bs_dates`](../../avinashgroup_app/hr/bs_dates.py#L75) | BS dates and `custom_bs_month`. |

### Journal Entry (payroll journals)

| Event | Handler (registration) | Defined | Purpose |
|---|---|---|---|
| before_insert (placed **first** in the chain) | [`default_jv_type`](../../avinashgroup_app/hooks.py#L320) | [`default_jv_type`](../../avinashgroup_app/payroll/hr_journal.py#L30) | Journals that HRMS writes itself (the payroll accrual, advance payouts) get a JV Type, and the next Document No for a hand-numbered series, before numbering reads them. |
| validate | [`validate_journal_entry`](../../avinashgroup_app/hooks.py#L218) | vehicle_mandatory | Not HR, but it runs on the payroll journal too. |
| on_cancel | HRMS [`unlink_ref_doc_from_salary_slip`](../../../hrms/hrms/hooks.py#L193) | [`unlink_ref_doc_from_salary_slip`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L2150) | Stock HRMS. Cancelling the accrual JV unlinks it from the slips. |

### Other HR doctypes

| Doctype | Hooks | Notes |
|---|---|---|
| Employee Advance | audit; fiscal-year filter | Recovered through Prepare Payroll Inputs (`advance_recovery.py`), not a hook. See [05-payroll-entry.md](05-payroll-entry.md). |
| Additional Salary | fiscal-year filter only | Written by Prepare Payroll Inputs and Salary Revision; no doc_event of ours. |
| Holiday List | audit; HRMS cache invalidation ([`invalidate_cache`](../../../hrms/hrms/hooks.py#L174)) | |
| Attendance Fix | fiscal-year filter; controller does the work | See [02-checkin-to-attendance.md](02-checkin-to-attendance.md). |
| Salary Revision | controller only (`on_submit` / `on_cancel`) | See [08-changes-over-time.md](08-changes-over-time.md). |

## 3. Wildcard (`"*"`) hooks that land on every HR document

| Event | Handler (registration) | Defined | Effect on HR docs |
|---|---|---|---|
| validate, before_save | [`apply_engine_numbering`](../../avinashgroup_app/hooks.py#L422) | [`apply_engine_numbering`](../../avinashgroup_app/custom_code/Override/naming_series.py#L2913) | Numbering Configuration engine. It exits through a cached gate when no rule targets the doctype. Where a rule exists, the Fiscal Year lookup can throw on a date with no FY row. See [09-cross-cutting.md](09-cross-cutting.md). |
| after_delete | [`revert_engine_series_on_delete`](../../avinashgroup_app/hooks.py#L424) | [`revert_engine_series_on_delete`](../../avinashgroup_app/custom_code/Override/naming_series.py#L2929) | Gives the series back when a numbered doc is deleted. |
| validate | [`dynamic_approval.validate`](../../avinashgroup_app/hooks.py#L477) | [`validate`](../../avinashgroup_app/custom_code/dynamic_approval.py#L250) | Blocks edits while Pending Approval, except by the current approver (only on doctypes with a Dynamic Approval Setting). |
| before_save | [`dynamic_approval.before_save`](../../avinashgroup_app/hooks.py#L484) | [`before_save`](../../avinashgroup_app/custom_code/dynamic_approval.py#L338) | |
| on_update | [`dynamic_approval.on_update`](../../avinashgroup_app/hooks.py#L485) | [`on_update`](../../avinashgroup_app/custom_code/dynamic_approval.py#L501) | |
| before_workflow_action | [`dynamic_approval.before_workflow_action`](../../avinashgroup_app/hooks.py#L486) | [`before_workflow_action`](../../avinashgroup_app/custom_code/dynamic_approval.py#L366) | |
| on_submit, on_cancel, after_insert, on_update | [`sms_dispatch.on_submit`](../../avinashgroup_app/hooks.py#L490) and its siblings | [`on_submit`](../../avinashgroup_app/sparrow_sms/sms_dispatch.py#L533) | Sparrow SMS. Rules are data (SMS Notification Rule); avinas1 has none, so nothing is sent for HR docs. |

**Audit handlers** ([`get_doc_events`](../../avinashgroup_app/utils/audit_file_manager.py#L471)) register `before_insert`, `before_save`, `validate`, `autoname` and `after_delete` on every doctype in [`AuditBase.doctypes`](../../avinashgroup_app/utils/audit_file_manager.py#L10). The HR doctypes in it are Salary Structure, Attendance, Employee, Employee Advance, Overtime Sheet, Holiday List, Leave Application, Leave Allocation, Payroll Entry, Salary Slip, Journal Entry and Shift Type. Each handler does:

- `validate`: company-field lock and company match.
- `before_insert` / `before_save`: `custom_created_by`, `custom_created_on` and `custom_modified_by`.
- `autoname`: the legacy naming-series path.
- `after_delete`: series revert.

They run **before** every other handler of ours on the same event.

## 4. Scheduler jobs

> **avinas1 has the scheduler disabled** (`System Settings.enable_scheduler = 0`, read 2026-10-12). The last runs recorded in `tabScheduled Job Type` are on 2026-07-17. None of our four `daily_long` HR jobs has *ever* run on avinas1 (`last_execution` is NULL), and neither has the 13:10 digest. Everything in this table describes production behaviour; on avinas1, the work these jobs do happens only when a button is pressed or someone runs it by hand.

| Frequency | Job (registration) | Defined | Stopped on avinas1? | What it does |
|---|---|---|---|---|
| hourly | [`check_bridge_heartbeats`](../../avinashgroup_app/hooks.py#L514) | [`check_bridge_heartbeats`](../../avinashgroup_app/biometric/heartbeat.py#L26) | no (scheduler off) | Alerts when a K40/HTMS bridge stops pinging. |
| daily_long | [`heal_unlinked_checkins`](../../avinashgroup_app/hooks.py#L527) | [`heal_unlinked_checkins`](../../avinashgroup_app/biometric/attendance_self_heal.py#L58) | no | Repairs the days HRMS auto attendance could not mark. It only touches shifts with auto attendance **on**, and both avinas1 shift types have it off. |
| daily_long | [`allocate_earned_leaves_bs`](../../avinashgroup_app/hooks.py#L533) | [`allocate_earned_leaves_bs`](../../avinashgroup_app/hr/utils.py#L81) | no; never ran | Monthly earned leave on BS months. **Replaces** HRMS's `allocate_earned_leaves`, which is `stopped = 1` on avinas1, as required. |
| daily_long | [`switch_to_current_year_lists`](../../avinashgroup_app/hooks.py#L536) | [`switch_to_current_year_lists`](../../avinashgroup_app/hr/holiday_year_switch.py#L30) | no; never ran | On a fiscal year's first day, moves companies and employees onto that year's holiday lists. |
| daily_long | [`grant_pending`](../../avinashgroup_app/hooks.py#L524) | [`grant_pending`](../../avinashgroup_app/hr/replacement_leave.py#L68) | no; never ran | Replacement leave for holiday work whose attendance arrived after the sheet was submitted. |
| daily_long | [`measure_pending`](../../avinashgroup_app/hooks.py#L540) | [`measure_pending`](../../avinashgroup_app/hr/overtime_settlement.py#L200) | no; never ran | Measures overtime rows whose attendance arrived after submission (62-day look-back). |
| cron `10 13 * * *` | [`send_daily_attendance_digest`](../../avinashgroup_app/hooks.py#L562) | [`send_daily_attendance_digest`](../../avinashgroup_app/biometric/daily_digest.py#L76) | no; never ran | Midday mail of the day's attendance problems. Runs at :10 so it does not race HRMS's hourly auto attendance. |

HRMS jobs that matter here:

| Frequency | Job | Defined | Stopped on avinas1? | Note |
|---|---|---|---|---|
| hourly_long | [`update_last_sync_of_checkin`](../../../hrms/hrms/hooks.py#L224) | [`update_last_sync_of_checkin`](../../../hrms/hrms/hr/doctype/shift_type/shift_type.py#L377) | no | Moves Last Sync forward, which gates auto attendance. |
| hourly_long | [`process_auto_attendance_for_all_shifts`](../../../hrms/hrms/hooks.py#L225) | [`process_auto_attendance_for_all_shifts`](../../../hrms/hrms/hr/doctype/shift_type/shift_type.py#L411) | no | Only shifts with Enable Auto Attendance; none on avinas1. |
| hourly_long | [`process_auto_shift_creation`](../../../hrms/hrms/hooks.py#L226) | [`process_auto_shift_creation`](../../../hrms/hrms/hr/doctype/shift_schedule_assignment/shift_schedule_assignment.py#L121) | no | Shift Schedule Assignment. Our rotation uses Shift Assignment directly. |
| daily_long | [`allocate_earned_leaves`](../../../hrms/hrms/hooks.py#L238) | [`allocate_earned_leaves`](../../../hrms/hrms/hr/utils.py#L341) | **yes, stopped = 1** | Deliberately stopped by `setup_bs_leave_accrual`. If it is re-enabled, every earned-leave credit lands twice. |
| daily_long | [`process_expired_allocation`](../../../hrms/hrms/hooks.py#L236), [`generate_leave_encashment`](../../../hrms/hrms/hooks.py#L237) | [`process_expired_allocation`](../../../hrms/hrms/hr/doctype/leave_ledger_entry/leave_ledger_entry.py#L130), [`generate_leave_encashment`](../../../hrms/hrms/hr/utils.py#L317) | no | Stock leave housekeeping. |

`rdp_common_app` schedules only a revenue-deferral job ([`process_nepali_deferred_revenue_via_hook`](../../../rdp_common_app/rdp_common_app/hooks.py#L171)), which is not HR.

## 5. Permission and list hooks on HR doctypes

| Hook | Registration | Handler | HR doctypes covered | Effect |
|---|---|---|---|---|
| `permission_query_conditions` | [`permission_query_conditions`](../../avinashgroup_app/hooks.py#L388) | [`_make_query_conditions_for`](../../avinashgroup_app/custom_code/fiscal_year_filter.py#L487) | Every name in [`FILTERED_DOCTYPES`](../../avinashgroup_app/custom_code/fiscal_year_filter.py#L8). The HR ones are Additional Salary, Attendance, Attendance Fix, Attendance Request, Employee Advance, Leave Allocation / Application / Encashment / Ledger Entry / Adjustment, Overtime Slip, Payroll Entry, Salary Slip, Salary Structure Assignment, Salary Withholding, Shift Assignment, Shift Request, Expense Claim, Gratuity, Full and Final Statement. | List views show a user only the fiscal years their User Fiscal Year Access allows. |
| `has_permission` | [`has_permission`](../../avinashgroup_app/hooks.py#L394) | [`has_fiscal_year_permission`](../../avinashgroup_app/custom_code/fiscal_year_filter.py#L500) | same | Opening a single document outside the user's years is refused. |
| `frappe.client.get_list` override | [`filtered_get_list`](../../avinashgroup_app/hooks.py#L607) | [`filtered_get_list`](../../avinashgroup_app/custom_code/fiscal_year_filter.py#L562) | same | Applies the same filter to API list calls. |
| workflow overrides | [`get_transitions`](../../avinashgroup_app/hooks.py#L605), [`apply_workflow`](../../avinashgroup_app/hooks.py#L606) | [`get_transitions`](../../avinashgroup_app/custom_code/workflow_admin_bypass.py#L28), [`apply_workflow`](../../avinashgroup_app/custom_code/workflow_admin_bypass.py#L68) | Any doctype with a Workflow | Administrator / System Manager bypass. avinas1 has **no** Workflow records (`tabWorkflow` is empty), so this does nothing on HR docs today. |

Notable: Employee, Overtime Sheet, Salary Structure and Salary Revision are **not** fiscal-year filtered. A user with no access to a year still sees those.

## 6. JavaScript hooks

### `doctype_js` (form scripts added to stock doctypes)

| Doctype | Registration | Script | What it adds | Server calls |
|---|---|---|---|---|
| Attendance | [`attendance.js`](../../avinashgroup_app/hooks.py#L107) | [`render_checkin_log`](../../avinashgroup_app/public/js/attendance.js#L14) | Removes Nepal HRMS's old check-in log block. Adds **Repair from Check-ins** ([`add_repair_button`](../../avinashgroup_app/public/js/attendance.js#L85)). | [`repair_attendance_day`](../../avinashgroup_app/avinash_group_app/doctype/attendance_fix/attendance_fix.py#L524) |
| Payroll Entry | [`payroll_entry.js`](../../avinashgroup_app/hooks.py#L107) | [`BS_CALENDAR`](../../avinashgroup_app/public/js/payroll_entry.js#L8) | BS month calendar; locks posting/start/end/frequency once a BS month is chosen. Opens on the month after the last payroll. Adds **Nepal HRMS → Prepare Payroll Inputs** ([`Prepare Payroll Inputs`](../../avinashgroup_app/public/js/payroll_entry.js#L248)). | [`get_month`](../../avinashgroup_app/hr/bs_calendar.py#L148), [`month_calendar`](../../avinashgroup_app/payroll/payroll_month.py#L148), [`default_month`](../../avinashgroup_app/payroll/payroll_month.py#L121), [`trigger_for_payroll_entry`](../../avinashgroup_app/payroll/attendance_allowance.py#L62) |
| Payroll Entry (rdp_common_app) | [`payroll_entry.js`](../../../rdp_common_app/rdp_common_app/hooks.py#L58) | rdp_common_app | Loaded too. Frappe concatenates every app's doctype_js for a doctype, so both scripts are active. See [05-payroll-entry.md](05-payroll-entry.md). | |
| Salary Structure Assignment | [`salary_structure_assignment.js`](../../avinashgroup_app/hooks.py#L109) | [`Assignment Allowance`](../../avinashgroup_app/public/js/salary_structure_assignment.js#L18) | Picking an allowance fills the structure's rate. | [`get_rate_for_assignment`](../../avinashgroup_app/payroll/allowance.py#L209) |
| Salary Structure | [`salary_structure.js`](../../avinashgroup_app/hooks.py#L110) | [`custom_allowance_rates`](../../avinashgroup_app/public/js/salary_structure.js#L7) | Allowance Rates may only list allowances that are not Entered by Hand or Yearly. | none |
| Shift Type | [`shift_type.js`](../../avinashgroup_app/hooks.py#L112) | [`SHIFT_ROTATION`](../../avinashgroup_app/public/js/shift_type.js#L12) | **Move Staff to This Shift** on a rotational shift (`custom_in_rotation`). | [`preview`](../../avinashgroup_app/hr/shift_rotation.py#L111), [`rotate`](../../avinashgroup_app/hr/shift_rotation.py#L152) |

### `app_include_js` (loaded on every desk page)

| Script | Registration | Purpose |
|---|---|---|
| `hr_report_common.js` | [`hr_report_common.js`](../../avinashgroup_app/hooks.py#L41) | Shared cell renderers (stacked employee cell) for the HR/payroll reports. |
| `hr_workspace.js` | [`hr_workspace.js`](../../avinashgroup_app/hooks.py#L77) | Mounts the HR dashboard above the stock HR workspace for HR Manager, HR User and System Manager, and hides HRMS's onboarding there. It loads `hr_dashboard.js`, which calls [`get_dashboard`](../../avinashgroup_app/hr/hr_dashboard.py#L75) and [`get_menu`](../../avinashgroup_app/hr/hr_dashboard.py#L709). |
| `approval_workflow_common.js`, `approval_workflow_auto.js`, `approval_field_visibility.js` | [`approval_workflow_auto.js`](../../avinashgroup_app/hooks.py#L60) | The Dynamic Approval banner and reject dialog on any doctype set up for approval, including Leave Application. |
| `auto_fiscal_year.js`, `fiscal_year_cache.js` | [`auto_fiscal_year.js`](../../avinashgroup_app/hooks.py#L63) | Fiscal-year field defaults. Any HR doc with a fiscal-year field is affected. |

### Form scripts owned by our HR doctypes (not hooks, listed for completeness)

`attendance_fix.js`, `biometric_device.js`, `employee_category_tool.js`, `holiday_bulk_update.js`, `overtime_sheet.js`, `salary_revision.js`, all under `avinash_group_app/doctype/<name>/`.

## 7. Whitelisted endpoints in the HR/payroll code

These are what the buttons and the device bridge call. All are `@frappe.whitelist()`.

| Endpoint | Defined | Called by |
|---|---|---|
| `receive_attendance` | [`receive_attendance`](../../avinashgroup_app/biometric/api.py#L10) | K40/HTMS bridge (push of punches) |
| `ping` | [`ping`](../../avinashgroup_app/biometric/heartbeat.py#L101) | bridge heartbeat |
| `poll_commands` / `report_command_result` / `enqueue_command` | [`poll_commands`](../../avinashgroup_app/biometric/bridge_commands.py#L31), [`report_command_result`](../../avinashgroup_app/biometric/bridge_commands.py#L80), [`enqueue_command`](../../avinashgroup_app/biometric/bridge_commands.py#L128) | bridge command channel |
| `preview_digest` | [`preview_digest`](../../avinashgroup_app/biometric/daily_digest.py#L556) | HR, by hand |
| `repair_attendance_day` | [`repair_attendance_day`](../../avinashgroup_app/avinash_group_app/doctype/attendance_fix/attendance_fix.py#L524) | Attendance form button |
| `get_shift_roster` | [`get_shift_roster`](../../avinashgroup_app/avinash_group_app/doctype/attendance_fix/attendance_fix.py#L630) | Attendance Fix form |
| `get_month`, `get_default_month` | [`get_month`](../../avinashgroup_app/hr/bs_calendar.py#L148), [`get_default_month`](../../avinashgroup_app/hr/bs_calendar.py#L165) | Payroll Entry calendar |
| `default_month`, `month_calendar` | [`default_month`](../../avinashgroup_app/payroll/payroll_month.py#L121), [`month_calendar`](../../avinashgroup_app/payroll/payroll_month.py#L148) | Payroll Entry form |
| `trigger_for_payroll_entry` | [`trigger_for_payroll_entry`](../../avinashgroup_app/payroll/attendance_allowance.py#L62) | **Prepare Payroll Inputs** |
| `recompute_holiday_flags` | [`recompute_holiday_flags`](../../avinashgroup_app/payroll/attendance_allowance.py#L477) | By hand, after a holiday list changes |
| `get_rate_for_assignment` | [`get_rate_for_assignment`](../../avinashgroup_app/payroll/allowance.py#L209) | Salary Structure Assignment form |
| `measure` | [`measure`](../../avinashgroup_app/hr/overtime_settlement.py#L126) | Overtime Sheet **Measure from Attendance** |
| `preview` (overtime) | [`preview`](../../avinashgroup_app/hr/overtime.py#L223) | Overtime Sheet row preview |
| `preview`, `rotate`, `set_periods` (rotation) | [`preview`](../../avinashgroup_app/hr/shift_rotation.py#L111), [`rotate`](../../avinashgroup_app/hr/shift_rotation.py#L152), [`set_periods`](../../avinashgroup_app/hr/shift_rotation.py#L197) | Shift Type form |
| `roster` | [`roster`](../../avinashgroup_app/hr/shift_roster.py#L30) | shift roster view |
| `preview_accrual_dates` | [`preview_accrual_dates`](../../avinashgroup_app/hr/utils.py#L237) | Leave setup check |
| `get_dashboard`, `get_menu` | [`get_dashboard`](../../avinashgroup_app/hr/hr_dashboard.py#L75), [`get_menu`](../../avinashgroup_app/hr/hr_dashboard.py#L709) | HR dashboard |
| `Salary Revision.get_employees` | [`get_employees`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L423) | Salary Revision form |
| `Employee Category Tool.get_employees`, `bulk_assign` | [`get_employees`](../../avinashgroup_app/avinash_group_app/doctype/employee_category_tool/employee_category_tool.py#L29), [`bulk_assign`](../../avinashgroup_app/avinash_group_app/doctype/employee_category_tool/employee_category_tool.py#L64) | Employee Category Tool |
| `Holiday Bulk Update.apply` | [`apply`](../../avinashgroup_app/avinash_group_app/doctype/holiday_bulk_update/holiday_bulk_update.py#L42) | Holiday Bulk Update |
| `AvinashPayrollEntry.make_bank_entry` | [`make_bank_entry`](../../avinashgroup_app/payroll/payroll_entry.py#L55) | Payroll Entry **Make Bank Entry** |

## 8. Other hook types

| Hook | Registration | HR relevance |
|---|---|---|
| `page_renderer` | [`IclockRenderer`](../../avinashgroup_app/hooks.py#L11) → [`IclockRenderer`](../../avinashgroup_app/biometric/iclock.py#L35) | `/iclock/*`: the ZKTeco ADMS push endpoint. Devices post punches here directly, with no login. |
| `company_data_to_be_ignored` | [`company_data_to_be_ignored`](../../avinashgroup_app/hooks.py#L686) | "Biometric Device" and "Nepal BS Period" survive Company → Delete Transactions. |
| Client Scripts, Server Scripts, Notifications, Webhooks on avinas1 | n/a | None on any HR doctype (read 2026-10-12). The 7 client scripts are on buying and accounting doctypes. The 6 notifications are stock HRMS ones (Exit Interview, Training, Retention Bonus) plus "Notification for new fiscal year". |
| `fixtures` | [`fixtures`](../../avinashgroup_app/hooks.py#L619) | No HR fixtures. All HR custom fields come from **patches** (see [01b-pay-masters.md](01b-pay-masters.md), appendix). |
