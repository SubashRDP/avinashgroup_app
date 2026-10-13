# Salary code map: punch to journal

Every function that turns a biometric punch into a salary slip and its journal, in the order it runs. Each link opens the file at the line: Ctrl/Cmd+click it in VS Code's editor, or click it in the Markdown preview. The CodeTour `.tours/salary-calculation.tour` walks the same rows one at a time (CodeTour extension → *Start Tour*). Line numbers were checked against `develop`, hrms v15.49.2 and rdp_common_app on 2026-10-12. Re-run the link check after a large edit (see the end of this page).

Three apps take part. Only this one is edited here:

| App | Owns |
|---|---|
| `avinashgroup_app` (this repo) | Device intake, attendance rules, overtime, Prepare Payroll Inputs, slip hooks, section accounts on the journal |
| `hrms` v15.49.2 (`../hrms`, never edited) | Auto attendance, Payroll Entry, the Salary Slip engine, the accrual journal |
| `rdp_common_app` (`../rdp_common_app`, not edited from here) | `BSSalarySlip`: the Salary Slip class override that puts slips on BS months |

## The pipeline

```
 Device punch ──► Employee Checkin ──► Attendance ──────────────┐
 (ADMS / bridge)   stage 1              stage 2                  │
                                          │                      │
                     Overtime Sheet ◄─────┘ (hours measured)     │
                     stage 3                                     │
                          │                                      ▼
                          └──► Prepare Payroll Inputs ──► Additional Salary (tea, meal, OT, late fine, advance)
                               stage 4                         │
                                                               ▼
 Payroll Entry (BS month) ──► Salary Slip: HRMS core ──► BS override ──► our validate hooks
 stage 5                       stage 6                    stage 7          stage 8
                                                                              │
                         Submit Salary Slip ──► accrual Journal Entry ──► Bank Entry
                         stage 9
```

Stage 10 is the setup data (components, structures, assignments, revisions) that every stage above reads. Stage 11 is the two once-a-year payments (Dashain allowance, leave encashment), which reach the slip as Additional Salary like stage 4.

## 1. Punch → Employee Checkin

| # | Function | File | What it does | Settings / data it reads |
|---|---|---|---|---|
| 1.1 | `IclockRenderer.render` | @@avinashgroup_app/biometric/iclock.py::render@@ | Page renderer for `/iclock/*` (ZKTeco ADMS push); `cdata` goes to `_handle_cdata`, every other endpoint is answered `OK`. | `hooks.py` `page_renderer`; query `SN` |
| 1.2 | `_handle_cdata` | @@avinashgroup_app/biometric/iclock.py::_handle_cdata@@ | GET returns the config block; POST with `table=ATTLOG` parses the punches and commits; other tables are acknowledged only. | Request body |
| 1.3 | `_process_attlog` | @@avinashgroup_app/biometric/iclock.py::_process_attlog@@ | Drops the batch if the serial is unknown, splits tab-separated lines into `{user_id, timestamp}`, hands them to `process_attendance_records`. | Biometric Device |
| 1.4 | `receive_attendance` | @@avinashgroup_app/biometric/api.py::receive_attendance@@ | Whitelisted POST used by the bridge (push model): checks the device, validates the JSON list, calls `process_attendance_records`. | Biometric Device |
| 1.5 | `assert_known_device` | @@avinashgroup_app/biometric/utils.py::assert_known_device@@ | Throws PermissionError (403) unless a Biometric Device with this `device_serial` is enabled. | Biometric Device `device_serial`, `enabled` |
| 1.6 | `process_attendance_records` | @@avinashgroup_app/biometric/utils.py::process_attendance_records@@ | Groups punches by (device user ID, date), finds the employee, reconciles each group under its own savepoint; returns synced / skipped / failed lists. | Biometric Device `company`, `duplicate_threshold_seconds` |
| 1.7 | `resolve_employee_for_punch` | @@avinashgroup_app/biometric/utils.py::resolve_employee_for_punch@@ | The employee whose `attendance_device_id` is the user ID in the device's company; on a miss, the device's Allowed Employees list. | Employee `attendance_device_id`; Biometric Device Allowed Employee |
| 1.8 | `_reconcile_day_checkins` | @@avinashgroup_app/biometric/utils.py::_reconcile_day_checkins@@ | Keeps existing checkins, drops new punches inside the duplicate threshold, inserts the rest as Employee Checkin, relabels IN/OUT, then calls `sync_day`. | Employee Checkin of the day |
| 1.9 | `desired_log_type` | @@avinashgroup_app/biometric/attendance_sync.py::desired_log_type@@ | IN, OUT, IN … in time order, with the day's last punch forced to OUT when there are two or more. | — |
| 1.10 | `sync_day` | @@avinashgroup_app/biometric/attendance_sync.py::sync_day@@ | Past days only: links the day's unlinked checkins to an existing Present / Half Day Attendance and refreshes its values. Never changes status. | Attendance, Employee Checkin |
| 1.11 | `refresh_attendance_values` | @@avinashgroup_app/biometric/attendance_sync.py::refresh_attendance_values@@ | Recomputes working hours, in/out, late/early flags (via `ShiftType.get_attendance`) and the four deviation fields; writes only what changed, with `db.set_value`. | Shift Type |
| 1.12 | `checkin_{_event}` | @@avinashgroup_app/hooks.py::=attendance_sync.checkin_{_event}@@ | Registers `checkin_after_insert` / `checkin_on_update` / `checkin_after_delete` on Employee Checkin. | — |
| 1.13 | `checkin_after_insert` | @@avinashgroup_app/biometric/attendance_sync.py::checkin_after_insert@@ | A checkin made on the desk or by API: relabel the day and `sync_day`. Skipped while the device pipeline inserts (`in_biometric_day_reconcile`). | — |
| 1.14 | `checkin_on_update` | @@avinashgroup_app/biometric/attendance_sync.py::checkin_on_update@@ | Time or log type edited: relabel and sync the old and the new day. | — |
| 1.15 | `checkin_after_delete` | @@avinashgroup_app/biometric/attendance_sync.py::checkin_after_delete@@ | Checkin deleted: relabel and sync its day. | — |
| 1.16 | `validate_unique_device_id` | @@avinashgroup_app/biometric/employee.py::validate_unique_device_id@@ | Employee validate: refuses two employees of one company with the same Attendance Device ID, so a punch maps to one person. | Employee `attendance_device_id`, `company` |

## 2. Checkin → Attendance

HRMS marks attendance from checkins every hour; our Attendance hooks then apply the late and leave rules; self-heal (nightly) and Attendance Fix repair what HRMS could not mark. There is no `mark_auto_attendance` function in hrms v15.49.2: the entry point is `process_auto_attendance_for_all_shifts`.

| # | Function | File | What it does | Settings / data it reads |
|---|---|---|---|---|
| 2.1 | `process_auto_attendance_for_all_shifts` | @@../hrms/hrms/hooks.py::=process_auto_attendance_for_all_shifts@@ | HRMS `hourly_long` scheduler entry. | — |
| 2.2 | `process_auto_attendance_for_all_shifts` | @@../hrms/hrms/hr/doctype/shift_type/shift_type.py::process_auto_attendance_for_all_shifts@@ | Runs `process_auto_attendance` on every Shift Type with Enable Auto Attendance. | Shift Type `enable_auto_attendance` |
| 2.3 | `ShiftType.process_auto_attendance` | @@../hrms/hrms/hr/doctype/shift_type/shift_type.py::process_auto_attendance@@ | Needs auto attendance, Process Attendance After and Last Sync set; groups unlinked checkins by (employee, shift start), marks each, then marks absents. | Shift Type `process_attendance_after`, `last_sync_of_checkin` |
| 2.4 | `ShiftType.get_employee_checkins` | @@../hrms/hrms/hr/doctype/shift_type/shift_type.py::get_employee_checkins@@ | Checkins of this shift that are unlinked, not skipped, not offshift, and whose shift ended before Last Sync. | Employee Checkin |
| 2.5 | `EmployeeCheckin.fetch_shift` | @@../hrms/hrms/hr/doctype/employee_checkin/employee_checkin.py::fetch_shift@@ | Sets the checkin's shift and its start/end and actual start/end from the employee's shift; `offshift` when none. | Shift Assignment, Employee `default_shift` |
| 2.6 | `ShiftType.get_attendance` | @@../hrms/hrms/hr/doctype/shift_type/shift_type.py::get_attendance@@ | Status from the hour thresholds (Absent / Half Day / Present), late entry and early exit from the grace periods. | Shift Type thresholds and grace periods |
| 2.7 | `calculate_working_hours` | @@../hrms/hrms/hr/doctype/employee_checkin/employee_checkin.py::calculate_working_hours@@ | Hours, in-time and out-time by the shift's check-in/out mode and calculation basis. | Shift Type `determine_check_in_and_check_out`, `working_hours_calculation_based_on` |
| 2.8 | `mark_attendance_and_link_log` | @@../hrms/hrms/hr/doctype/employee_checkin/employee_checkin.py::mark_attendance_and_link_log@@ | Submits a new Attendance (or updates a leave half day) and links the checkins; on a ValidationError flags them `skip_auto_attendance`. | — |
| 2.9 | `ShiftType.mark_absent_for_dates_with_no_attendance` | @@../hrms/hrms/hr/doctype/shift_type/shift_type.py::mark_absent_for_dates_with_no_attendance@@ | Marks Absent on this shift's days that have no attendance. | Holiday List, Shift Assignment |
| 2.10 | `Attendance.validate` | @@../hrms/hrms/hr/doctype/attendance/attendance.py::validate@@ | HRMS checks (status, joining date, duplicates, overlapping shift, employee status), then `check_leave_record`. | — |
| 2.11 | `Attendance.check_leave_record` | @@../hrms/hrms/hr/doctype/attendance/attendance.py::check_leave_record@@ | An approved Leave Application on the date sets leave type and status On Leave (Half Day on its half-day date). | Leave Application |
| 2.12 | `attendance_events` | @@avinashgroup_app/hooks.py::=attendance_events = {@@ | Our Attendance `validate` hooks, run in this order (on `validate`, so they also fire for attendance submitted on insert). | — |
| 2.13 | `set_holiday_flag` | @@avinashgroup_app/payroll/attendance_allowance.py::set_holiday_flag@@ | Ticks `custom_worked_on_holiday` when the date is in the employee's Holiday List (or the company default). | Employee `holiday_list`, Company `default_holiday_list` |
| 2.14 | `set_shift_deviation_fields` | @@avinashgroup_app/biometric/attendance_override.py::set_shift_deviation_fields@@ | Fills a missing shift from the roster (`get_shift_window`), then writes the four `custom_*` deviation fields. | Shift Type |
| 2.15 | `compute_shift_deviations` | @@avinashgroup_app/biometric/attendance_sync.py::compute_shift_deviations@@ | Seconds of late/early entry and early/late exit against shift start and end, rounded to the minute. | Shift Type `start_time`, `end_time` |
| 2.16 | `enforce_late_arrival_half_day` | @@avinashgroup_app/biometric/attendance_override.py::enforce_late_arrival_half_day@@ | In-time strictly after shift start + `custom_half_day_if_late_by_hours` (0 = off) → Half Day with `half_day_status` Absent; an excused day goes to `_undo_excused_late_half_day`. | Shift Type `custom_half_day_if_late_by_hours`; Attendance `custom_late_excused` |
| 2.17 | `_undo_excused_late_half_day` | @@avinashgroup_app/biometric/attendance_override.py::_undo_excused_late_half_day@@ | Puts an excused late half day back to Present, unless it has a leave type or the hours are below the half-day threshold. | Shift Type `working_hours_threshold_for_half_day` |
| 2.18 | `half_day_when_working_on_leave` | @@avinashgroup_app/biometric/attendance_override.py::half_day_when_working_on_leave@@ | On Leave from a leave application but punched in → Half Day, `half_day_status` Present, leave type kept. | Attendance `leave_application` |
| 2.19 | `heal_unlinked_checkins` | @@avinashgroup_app/biometric/attendance_self_heal.py::heal_unlinked_checkins@@ | Daily (`daily_long`, midnight): every (employee, day) of the last 45 days with unlinked checkins, whose shift has auto attendance on and has ended, goes through `reconcile_employee_day`. | Shift Type `enable_auto_attendance`, `last_sync_of_checkin`, `process_attendance_after` |
| 2.20 | `reconcile_employee_day` | @@avinashgroup_app/avinash_group_app/doctype/attendance_fix/attendance_fix.py::reconcile_employee_day@@ | A non-Absent day: link orphan punches and refresh values. An Absent or empty day with punches: replace it with attendance built by `get_attendance` + `mark_attendance_and_link_log`. | Employee Checkin, Attendance |
| 2.21 | `AttendanceFix.on_submit` | @@avinashgroup_app/avinash_group_app/doctype/attendance_fix/attendance_fix.py::on_submit@@ | HR's Attendance Fix: queues the same per-day reconcile over a date range for one shift. | Attendance Fix |
| 2.22 | `measure_day` | @@avinashgroup_app/hr/shift_day.py::measure_day@@ | Late and early-exit minutes (full working days only) and overtime hours to the half hour (OT-eligible only) for one Attendance row. Used by the attendance reports and the Late Time rule (4.13). | Attendance `custom_*` deviation fields |

## 3. Overtime Sheet and settlement

| # | Function | File | What it does | Settings / data it reads |
|---|---|---|---|---|
| 3.1 | `OvertimeSheet.apply_rules` | @@avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.py::apply_rules@@ | Sheet validate: runs `evaluate` on every row, writes back work type, day type, entitlement, shift; lists all refused rows at once. | — |
| 3.2 | `evaluate` | @@avinashgroup_app/hr/overtime.py::evaluate@@ | Day type × the employee's two ticks → entitlement Overtime or Replacement Leave; refuses rows the policy does not allow. | Employee `custom_ot_eligibility`, `custom_compensatory_leave` |
| 3.3 | `get_day_type` | @@avinashgroup_app/hr/overtime.py::get_day_type@@ | Holiday, Weekly Off or Working Day from the employee's own holiday list. | Holiday List |
| 3.4 | `get_shift_window` | @@avinashgroup_app/hr/overtime.py::get_shift_window@@ | The shift rostered on a date (dated Shift Assignment, else Default Shift) with its start and end datetimes. | Shift Assignment, Employee `default_shift`, Shift Type |
| 3.5 | `get_holiday_work_rule` | @@avinashgroup_app/hr/overtime.py::get_holiday_work_rule@@ | The Employee's Overtime Eligible / Replacement Leave for Holiday Work ticks (either/or, enforced by `validate_employee_holiday_rule`). | Employee `custom_ot_eligibility`, `custom_compensatory_leave` |
| 3.6 | `on_sheet_submit` | @@avinashgroup_app/hr/overtime_settlement.py::on_sheet_submit@@ | Sheet submit: measures the never-measured rows if the work date is already past. | — |
| 3.7 | `measure_pending` | @@avinashgroup_app/hr/overtime_settlement.py::measure_pending@@ | Daily job: measures never-measured rows of submitted sheets from the last 62 days. | — |
| 3.8 | `measure` | @@avinashgroup_app/hr/overtime_settlement.py::measure@@ | The sheet's Measure button: re-measures every row (`measure_sheet`). | — |
| 3.9 | `measure_row` | @@avinashgroup_app/hr/overtime_settlement.py::measure_row@@ | Holiday work: hours worked; overtime: hours outside the shift; both rounded to the half hour. 0 hours with a note when there is no attendance, it is Absent, or there is one punch. | Attendance, Shift Type |
| 3.10 | `hours_outside_shift` | @@avinashgroup_app/hr/overtime.py::hours_outside_shift@@ | Hours of the in–out window that fall before shift start or after shift end. | — |
| 3.11 | `round_to_half_hour` | @@avinashgroup_app/hr/shift_day.py::round_to_half_hour@@ | Nearest half hour, halves rounding up. | — |

The measured hours stay on the sheet rows (`worked_hours`); payroll reads them in 4.16.

## 4. Prepare Payroll Inputs → Additional Salary

HR presses **Prepare Payroll Inputs** on the Payroll Entry. Each attendance-driven component becomes one submitted Additional Salary per employee, dated the month's last day.

| # | Function | File | What it does | Settings / data it reads |
|---|---|---|---|---|
| 4.1 | `Prepare Payroll Inputs` | @@avinashgroup_app/public/js/payroll_entry.js::=__("Prepare Payroll Inputs")@@ | The button; after a confirm it calls `trigger_for_payroll_entry`. | — |
| 4.2 | `trigger_for_payroll_entry` | @@avinashgroup_app/payroll/attendance_allowance.py::trigger_for_payroll_entry@@ | Runs `create_additional_salaries`, then `post_recoveries`, then `refresh_draft_slips`, and commits. | Payroll Entry |
| 4.3 | `create_additional_salaries` | @@avinashgroup_app/payroll/attendance_allowance.py::create_additional_salaries@@ | For each employee × attendance component: skip if not paid, price it, count it, write `qty × rate` as an Additional Salary under a savepoint. | Payroll Entry `start_date`, `end_date`, `employees` |
| 4.4 | `get_attendance_driven_components` | @@avinashgroup_app/payroll/attendance_allowance.py::get_attendance_driven_components@@ | Enabled Salary Components with `custom_is_attendance_driven`. | Salary Component |
| 4.5 | `get_employee_allowance_rows` | @@avinashgroup_app/payroll/allowance.py::get_employee_allowance_rows@@ | `{allowance: row}` from the Allowances table of the assignment in force; rows with a later From Date are left out. | Salary Structure Assignment → Assignment Allowance |
| 4.6 | `_gets` | @@avinashgroup_app/payroll/attendance_allowance.py::_gets@@ | An allowance is paid only with a row on the assignment; a non-allowance (late fine) only when the structure lists it. | Salary Component `custom_is_allowance`; Salary Structure rows |
| 4.7 | `_skip_for_eligibility` | @@avinashgroup_app/payroll/attendance_allowance.py::_skip_for_eligibility@@ | Skips OT-only components for staff not OT eligible, and late components for staff marked late-fine exempt. | Salary Component `custom_ot_eligible_only`; Employee `custom_ot_eligibility`, `custom_late_fine_exempt` |
| 4.8 | `_resolve_rate` | @@avinashgroup_app/payroll/attendance_allowance.py::_resolve_rate@@ | `Hourly Basic × Multiplier` components: hourly basic × multiplier; otherwise the Rate on the person's row; None if neither. | Salary Component `custom_rate_basis`, `custom_rate_multiplier` |
| 4.9 | `_hourly_basic` | @@avinashgroup_app/payroll/attendance_allowance.py::_hourly_basic@@ | Assignment `base` ÷ days per month ÷ hours per day. Days: the actual length of the BS month being priced (29–32) unless the component fixes it; hours: 8 when blank. | Salary Component `custom_rate_days_per_month`, `custom_rate_hours_per_day`; assignment `base` |
| 4.10 | `_attendance_period` | @@avinashgroup_app/payroll/attendance_allowance.py::_attendance_period@@ | The payroll's own dates, or the previous BS month when the component's Attendance Month is Previous Month. | Salary Component `custom_attendance_month` |
| 4.11 | `_qty_for_employee` | @@avinashgroup_app/payroll/attendance_allowance.py::_qty_for_employee@@ | Sums `evaluate_rule` over the period's submitted Attendance; `Flat per Period` gives 1 if any day matched. | Salary Component `custom_unit` |
| 4.12 | `_attendance_rows` | @@avinashgroup_app/payroll/attendance_allowance.py::_attendance_rows@@ | The employee's submitted Attendance rows in the period, with the deviation and holiday fields. | Attendance |
| 4.13 | `evaluate_rule` | @@avinashgroup_app/payroll/attendance_allowance.py::evaluate_rule@@ | One day's quantity by the component's condition: Present, Half Day, Worked on Holiday, Meal Entitlement, Authorised Overtime, Late Time, Early Entry / Late Stay / Late Arrival. | Salary Component `custom_condition_type`, `custom_unit`, `custom_pay_on_holiday`, `custom_half_day_counts`, `custom_time_offset_hours`; Attendance `custom_late_excused` |
| 4.14 | `_meals_for_day` | @@avinashgroup_app/payroll/attendance_allowance.py::_meals_for_day@@ | OT-eligible and on an Overtime Sheet that day: 2 on a holiday, else 1 each for coming early / staying late by the offset; capped at max per day. | Employee `custom_ot_eligibility`; Salary Component `custom_time_offset_hours`, `custom_max_per_day` |
| 4.15 | `_on_overtime_sheet` | @@avinashgroup_app/payroll/attendance_allowance.py::_on_overtime_sheet@@ | Whether a submitted Overtime Sheet names the employee on the date with the Overtime entitlement. | Overtime Sheet |
| 4.16 | `_authorised_overtime_hours` | @@avinashgroup_app/payroll/attendance_allowance.py::_authorised_overtime_hours@@ | Sum of `worked_hours` on submitted Overtime Sheet rows for the employee and date (the hours from 3.9). | Overtime Sheet Employee `worked_hours` |
| 4.17 | `_delete_existing_draft` | @@avinashgroup_app/payroll/attendance_allowance.py::_delete_existing_draft@@ | Cancels and deletes this calculator's earlier row for the same employee, component and date; hand-made rows are left. | Additional Salary `custom_source` |
| 4.18 | `_make_additional_salary` | @@avinashgroup_app/payroll/attendance_allowance.py::_make_additional_salary@@ | Inserts and submits the Additional Salary with qty and rate kept; earnings get `deduct_full_tax_on_selected_payroll_date`. | Salary Component `type` |
| 4.19 | `post_recoveries` | @@avinashgroup_app/payroll/advance_recovery.py::post_recoveries@@ | For each open Employee Advance: the smaller of the instalment and the balance, as a submitted `Salary Advance` deduction linked to the advance. | Employee Advance `custom_monthly_instalment`, `custom_recover_from`, `repay_unclaimed_amount_from_salary` |
| 4.20 | `clear_month` | @@avinashgroup_app/payroll/advance_recovery.py::clear_month@@ | Cancels the recoveries an earlier press posted into this month. | Additional Salary `custom_source` |
| 4.21 | `refresh_draft_slips` | @@avinashgroup_app/payroll/attendance_allowance.py::refresh_draft_slips@@ | Re-saves the entry's draft salary slips so they pick up what was just posted. | Salary Slip (draft) |

## 5. Payroll Entry

| # | Function | File | What it does | Settings / data it reads |
|---|---|---|---|---|
| 5.1 | `default_month` | @@avinashgroup_app/payroll/payroll_month.py::default_month@@ | The month a new entry opens on: after the company's last payroll, never past the running month. | Payroll Entry |
| 5.2 | `AvinashPayrollEntry.validate` | @@avinashgroup_app/payroll/payroll_entry.py::validate@@ | `fill_from_bs_month`, then HRMS's validate, then `warn_missing_attendance` on a new entry or changed month. | — |
| 5.3 | `fill_from_bs_month` | @@avinashgroup_app/payroll/payroll_month.py::fill_from_bs_month@@ | From Fiscal Year + BS month: start, end, posting date (month end), Monthly, currency, payable account, cost centre, and the employee list. | Company defaults; Nepal BS Period / BS calendar |
| 5.4 | `warn_missing_attendance` | @@avinashgroup_app/payroll/payroll_month.py::warn_missing_attendance@@ | Warns (does not stop) when employees have no submitted attendance in the month. | Payroll Settings `payroll_based_on`, `consider_unmarked_attendance_as` |
| 5.5 | `PayrollEntry.validate` | @@../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py::validate@@ | Sets the employee count and status. | — |
| 5.6 | `validate_payroll_entry` | @@avinashgroup_app/payroll/bs_period_guard.py::validate_payroll_entry@@ | Refuses an entry whose start/end is not the BS month of its posting date. | Nepal HRMS Settings `process_payroll_in_nepali_month` |
| 5.7 | `AvinashPayrollEntry.before_submit` | @@avinashgroup_app/payroll/payroll_entry.py::before_submit@@ | Warns about missing attendance again, then HRMS's before_submit. | — |
| 5.8 | `PayrollEntry.before_submit` | @@../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py::before_submit@@ | Refuses existing slips or a bad payable account; with Validate Attendance on, refuses unmarked attendance. | Payroll Entry `validate_attendance` |
| 5.9 | `PayrollEntry.on_submit` | @@../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py::on_submit@@ | Sets status and calls `create_salary_slips`. | — |
| 5.10 | `PayrollEntry.create_salary_slips` | @@../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py::create_salary_slips@@ | Builds the slip arguments (dates, posting date, entry); more than 30 employees are queued. | — |
| 5.11 | `create_salary_slips_for_employees` | @@../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py::create_salary_slips_for_employees@@ | Inserts one Salary Slip per employee who has none for the period; each insert runs stages 6–8. | — |

## 6. Salary Slip — HRMS core

`hrms/payroll/doctype/salary_slip/salary_slip.py`, class `SalarySlip`. `BSSalarySlip` (stage 7) subclasses it, so the methods it overrides run in its version.

| # | Function | File | What it does | Settings / data it reads |
|---|---|---|---|---|
| 6.1 | `SalarySlip.validate` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::validate@@ | Dates (`get_date_details`), then structure + working days on a new slip (or working days only), then `calculate_net_pay` and year-to-date totals. | — |
| 6.2 | `SalarySlip.get_emp_and_working_day_details` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::get_emp_and_working_day_details@@ | First build: clears rows, works out days, finds the structure, pulls its rows. | — |
| 6.3 | `SalarySlip.check_sal_struct` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::check_sal_struct@@ | The latest submitted assignment on an active structure dated on or before the period (end date included). | Salary Structure Assignment, Salary Structure |
| 6.4 | `SalarySlip.pull_sal_struct` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::pull_sal_struct@@ | Fills the slip from the structure through HRMS's `make_salary_slip`. | Salary Structure |
| 6.5 | `SalarySlip.get_working_days_details` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::get_working_days_details@@ | Total working days, LWP, absent days and payment days for the period. | Payroll Settings `payroll_based_on`, `include_holidays_in_total_working_days`, `consider_marked_attendance_on_holidays`, `daily_wages_fraction_for_half_day`, `consider_unmarked_attendance_as` |
| 6.6 | `SalarySlip.calculate_lwp_ppl_and_absent_days_based_on_attendance` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::calculate_lwp_ppl_and_absent_days_based_on_attendance@@ | LWP from leave-without-pay (and partial-pay) leave days and half days; Absent days counted separately. | Attendance, Leave Type `is_lwp`, `is_ppl` |
| 6.7 | `SalarySlip.get_half_absent_days` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::get_half_absent_days@@ | Count of Half Day rows with `half_day_status` Absent (the late rule in 2.16 produces these). | Attendance |
| 6.8 | `SalarySlip.get_unmarked_days` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::get_unmarked_days@@ | Days with no attendance; only deducted when unmarked counts as Absent. | Payroll Settings `consider_unmarked_attendance_as` |
| 6.9 | `SalarySlip.get_payment_days` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::get_payment_days@@ | Days between actual start and end (joining / relieving), less holidays unless holidays count. | Employee `date_of_joining`, `relieving_date` |
| 6.10 | `SalarySlip.calculate_net_pay` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::calculate_net_pay@@ | Earnings, gross, deductions (with tax), net pay, tax breakup. | — |
| 6.11 | `SalarySlip.calculate_component_amounts` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::calculate_component_amounts@@ | Structure rows, then Additional Salary rows; for deductions, then tax. | — |
| 6.12 | `SalarySlip.add_structure_components` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::add_structure_components@@ | Evaluates each structure row of the type and adds it (`add_structure_component`). | Salary Structure rows |
| 6.13 | `SalarySlip.eval_condition_and_formula` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::eval_condition_and_formula@@ | Row condition and formula evaluated against the slip, assignment and employee fields. | Assignment `base`, Employee fields |
| 6.14 | `SalarySlip.add_additional_salary_components` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::add_additional_salary_components@@ | Puts each submitted Additional Salary of the period on the slip. | Additional Salary |
| 6.15 | `get_additional_salaries` | @@../hrms/hrms/payroll/doctype/additional_salary/additional_salary.py::get_additional_salaries@@ | Submitted, enabled Additional Salary of the type: recurring ones covering the end date, one-offs dated in the period. | Additional Salary |
| 6.16 | `SalarySlip.update_component_row` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::update_component_row@@ | Finds or appends the row, sets default / additional amount, then prorates it by payment days. | Salary Component flags |
| 6.17 | `SalarySlip.get_amount_based_on_payment_days` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::get_amount_based_on_payment_days@@ | `amount × payment_days ÷ total_working_days` for components that depend on payment days; rounding if the component asks. | Salary Component `depends_on_payment_days`, `round_to_the_nearest_integer` |
| 6.18 | `SalarySlip.add_tax_components` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::add_tax_components@@ | Finds the tax component(s), loads the slab, computes the year's taxable earnings, adds the tax row. | Assignment `income_tax_slab` |
| 6.19 | `SalarySlip.compute_taxable_earnings_for_year` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::compute_taxable_earnings_for_year@@ | Previous + current + projected future taxable earnings, less exemptions. | Payroll Period, exemption declarations |
| 6.20 | `SalarySlip.calculate_variable_tax` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::calculate_variable_tax@@ | Year's slab tax less tax already paid, ÷ remaining months, plus full tax on one-off earnings. | Income Tax Slab |
| 6.21 | `SalarySlip.set_net_pay` | @@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::set_net_pay@@ | Total deduction, net pay, rounded total, amount in words. | — |

## 7. Salary Slip — BS override (rdp_common_app)

Registered by `rdp_common_app` as `override_doctype_class["Salary Slip"]`. Each method falls back to HRMS when `process_payroll_in_nepali_month` is off.

| # | Function | File | What it does | Settings / data it reads |
|---|---|---|---|---|
| 7.1 | `BSSalarySlip` | @@../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py::BSSalarySlip@@ | Subclass of HRMS `SalarySlip` used for every slip. | — |
| 7.2 | `BSSalarySlip.get_date_details` | @@../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py::get_date_details@@ | Start and end from the posting date's BS month: a Nepal BS Period record first, else `get_salary_period`. | Nepal HRMS Settings; Nepal BS Period |
| 7.3 | `get_salary_period` | @@../rdp_common_app/rdp_common_app/utils/bs_boundaries.py::get_salary_period@@ | The BS month containing a date, as AD start/end and its day count. | Nepali calendar |
| 7.4 | `BSSalarySlip.get_working_days_details` | @@../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py::get_working_days_details@@ | Runs HRMS's version, then sets `total_working_days` to the BS month's length (payment days unchanged). | — |
| 7.5 | `BSSalarySlip.get_amount_based_on_payment_days` | @@../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py::get_amount_based_on_payment_days@@ | HRMS's proration with the BS month length as the denominator. | — |
| 7.6 | `BSSalarySlip.compute_current_and_future_taxable_earnings` | @@../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py::compute_current_and_future_taxable_earnings@@ | Replaces `remaining_sub_periods` with the BS months left in the payroll period, then HRMS's version. | Payroll Period `end_date` |

## 8. Salary Slip — our validate hooks

Run after the controller's `validate` (stages 6–7), in the order `hooks.py` registers them.

| # | Function | File | What it does | Settings / data it reads |
|---|---|---|---|---|
| 8.1 | `add_employee_allowances` | @@avinashgroup_app/hooks.py::=payroll.salary_slip.add_employee_allowances@@ | Registration (first). | — |
| 8.2 | `add_employee_allowances` | @@avinashgroup_app/payroll/salary_slip.py::add_employee_allowances@@ | Draft slips: adds, updates or drops the Monthly and % of Initial Basic allowance rows, then reruns `calculate_net_pay`. | Assignment Allowance; Salary Component `custom_allowance_kind` |
| 8.3 | `fixed_allowance_amounts` | @@avinashgroup_app/payroll/allowance.py::fixed_allowance_amounts@@ | Full-month amount per fixed allowance: the Rate, or Rate % of the assignment's Initial Basic. | Assignment `custom_initial_basic` |
| 8.4 | `current_assignment` | @@avinashgroup_app/payroll/allowance.py::current_assignment@@ | The submitted assignment in force on the date (cached per request). | Salary Structure Assignment |
| 8.5 | `apply_tax_reliefs` | @@avinashgroup_app/hooks.py::=payroll.tax_relief.apply_tax_reliefs@@ | Registration (second). | — |
| 8.6 | `apply_tax_reliefs` | @@avinashgroup_app/payroll/tax_relief.py::apply_tax_reliefs@@ | When a retirement excess or women's rebate applies, recomputes the tax row from HRMS's figures and resets net pay; otherwise leaves the slip alone. | — |
| 8.7 | `retirement_excess` | @@avinashgroup_app/payroll/tax_relief.py::retirement_excess@@ | Retirement contributions for the year above the lower cap, put back into taxable income. | Employee Tax Exemption Category `custom_is_retirement_contribution`, `max_amount`, `custom_cap_percent_of_income` |
| 8.8 | `women_rebate_fraction` | @@avinashgroup_app/payroll/tax_relief.py::women_rebate_fraction@@ | The slab's rebate percent for a woman ticked Women's Tax Rebate, else 0. | Income Tax Slab `custom_women_rebate_percent`; Employee `gender`, `custom_womens_tax_rebate` |
| 8.9 | `apply_income_tax_override` | @@avinashgroup_app/hooks.py::=payroll.income_tax.apply_income_tax_override@@ | Registration (third). | — |
| 8.10 | `apply_income_tax_override` | @@avinashgroup_app/payroll/income_tax.py::apply_income_tax_override@@ | Stores the computed tax in `custom_income_tax_computed`; with Override ticked, sets the tax row to the typed amount and resets net pay. | Salary Slip `custom_override_income_tax`, `custom_income_tax_override` |
| 8.11 | `get_tax_row` | @@avinashgroup_app/payroll/income_tax.py::get_tax_row@@ | The deduction row with `variable_based_on_taxable_salary`. | — |
| 8.12 | `FY_8384_SLABS` | @@avinashgroup_app/payroll/income_tax.py::FY_8384_SLABS@@ | The 83/84 rate table. Not read by the slip: `hr/year_setup.py` uses it to create the Income Tax Slab record, which the slip reads (6.18). | — |
| 8.13 | `validate_salary_slip` | @@avinashgroup_app/hooks.py::=bs_period_guard.validate_salary_slip@@ | Registration (fourth). | — |
| 8.14 | `validate_salary_slip` | @@avinashgroup_app/payroll/bs_period_guard.py::validate_salary_slip@@ | Refuses a slip whose start date differs from its Payroll Entry's. | Payroll Entry `start_date` |
| 8.15 | `build_daily_breakdown` | @@avinashgroup_app/hooks.py::=daily_breakdown.build_daily_breakdown@@ | Registration (fifth). | — |
| 8.16 | `build_daily_breakdown` | @@avinashgroup_app/payroll/daily_breakdown.py::build_daily_breakdown@@ | Fills the Daily Breakdown table; logs and carries on if it fails. | — |
| 8.17 | `breakdown_rows` | @@avinashgroup_app/payroll/daily_breakdown.py::breakdown_rows@@ | Per day: paid weight × daily rate, attendance items spread by `evaluate_rule`, running balance; month-end rows and a Rounding / Adjustment row to reach net pay. | Attendance, Holiday List |
| 8.18 | `set_bs_dates` | @@avinashgroup_app/hooks.py::=avinashgroup_app.hr.bs_dates.set_bs_dates@@ | Registration (sixth, from a loop further down `hooks.py`). | — |
| 8.19 | `set_bs_dates` | @@avinashgroup_app/hr/bs_dates.py::set_bs_dates@@ | Writes the miti fields and `custom_bs_month` from the slip's dates; changes no amount. | — |

## 9. Journal on submit

| # | Function | File | What it does | Settings / data it reads |
|---|---|---|---|---|
| 9.1 | `PayrollEntry.submit_salary_slips` | @@../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py::submit_salary_slips@@ | The Submit Salary Slip button: the entry's draft slips, queued above 30. | — |
| 9.2 | `submit_salary_slips_for_employees` | @@../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py::submit_salary_slips_for_employees@@ | Submits each slip with net pay ≥ 0, then makes the accrual journal from the submitted ones. | — |
| 9.3 | `PayrollEntry.make_accrual_jv_entry` | @@../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py::make_accrual_jv_entry@@ | Earnings and deductions totals by account, advance deductions, payable line, then `make_journal_entry` (submitted). | Payroll Settings `process_payroll_accounting_entry_based_on_employee` |
| 9.4 | `AvinashPayrollEntry.get_salary_component_total` | @@avinashgroup_app/payroll/payroll_entry.py::get_salary_component_total@@ | HRMS's loop keyed by (component, cost centre, section); throws when an employee's department has no section but the component posts by section. | Payroll cost centres |
| 9.5 | `AvinashPayrollEntry.section_for` | @@avinashgroup_app/payroll/payroll_entry.py::section_for@@ | The employee's section, only if the component has S/D or F/P accounts for the company. | — |
| 9.6 | `get_section` | @@avinashgroup_app/payroll/allowance.py::get_section@@ | Employee → Department → `custom_payroll_section`. | Department `custom_payroll_section` |
| 9.7 | `AvinashPayrollEntry.get_account` | @@avinashgroup_app/payroll/payroll_entry.py::get_account@@ | Turns component keys into (account, cost centre) amounts using `section_account`, else HRMS's account. | — |
| 9.8 | `section_account` | @@avinashgroup_app/payroll/allowance.py::section_account@@ | The component's account for the section on the company row; blank S/D or F/P falls back to the row's own (O/O) account. | Salary Component Account `account`, `custom_account_marketing`, `custom_account_plant` |
| 9.9 | `PayrollEntry.make_journal_entry` | @@../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py::make_journal_entry@@ | Saves (and optionally submits) the Journal Entry and links it on the slips. | — |
| 9.10 | `default_jv_type` | @@avinashgroup_app/hooks.py::="avinashgroup_app.payroll.hr_journal.default_jv_type",@@ | Registered first in Journal Entry `before_insert`. | — |
| 9.11 | `default_jv_type` | @@avinashgroup_app/payroll/hr_journal.py::default_jv_type@@ | A journal referencing a Payroll Entry or Employee Advance gets a JV Type and, for a hand-numbered series, the next Document No. | JV Type; numbering series |
| 9.12 | `AvinashPayrollEntry.make_bank_entry` | @@avinashgroup_app/payroll/payroll_entry.py::make_bank_entry@@ | Refuses a missing or non-Bank/Cash Payment Account, then HRMS's bank entry. | Payroll Entry `payment_account` |
| 9.13 | `PayrollEntry.make_bank_entry` | @@../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py::make_bank_entry@@ | Bank Entry for the submitted slips' net pay against the payable account. | — |

## 10. Setup data the calculation reads

| # | Function | File | What it does | Settings / data it reads |
|---|---|---|---|---|
| 10.1 | `validate_salary_component` | @@avinashgroup_app/payroll/allowance.py::validate_salary_component@@ | Allowance kind sets the attendance condition; attendance-driven components get no payment-days proration and Remove if Zero; S/D and F/P accounts must be the row's company's. | Salary Component |
| 10.2 | `validate_salary_structure` | @@avinashgroup_app/payroll/allowance.py::validate_salary_structure@@ | Refuses allowances in Earnings / Deductions; blanks the amount and formula of attendance-driven rows (late fine tag); checks Allowance Rates. | Salary Structure |
| 10.3 | `guard_structure_rates` | @@avinashgroup_app/payroll/allowance.py::guard_structure_rates@@ | After submit, a listed rate changes only through a Salary Revision. | — |
| 10.4 | `validate_assignment_allowances` | @@avinashgroup_app/payroll/allowance.py::validate_assignment_allowances@@ | Allowances on an assignment: allowances only, once each; a blank rate takes the structure's; still 0 is refused. | Structure Allowance Rate |
| 10.5 | `get_rate_for_assignment` | @@avinashgroup_app/payroll/allowance.py::get_rate_for_assignment@@ | Form call: the structure's rate and unit for a picked allowance (0 for computed rates). | Structure Allowance Rate |
| 10.6 | `SalaryRevision.on_submit` | @@avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py::on_submit@@ | For each listed employee a new assignment and the arrears; then moves raised structure rates. | — |
| 10.7 | `SalaryRevision.assign_new_salary` | @@avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py::assign_new_salary@@ | New submitted assignment from the effective date: new base, planned allowances, Initial Basic, SSF Applicable, that year's tax slab. | Income Tax Slab |
| 10.8 | `SalaryRevision.pay_the_arrears` | @@avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py::pay_the_arrears@@ | Submits a `Salary Arrears` Additional Salary on the payout date, taxed in full that month. | — |
| 10.9 | `SalaryRevision.set_structure_rates` | @@avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py::set_structure_rates@@ | Raise Rate changes the structure's listed rate (cancel puts it back if unchanged since). | — |
| 10.10 | `tax_slab_for` | @@avinashgroup_app/payroll/year_rollover.py::tax_slab_for@@ | The submitted, enabled Income Tax Slab in force for a company on a date. | Income Tax Slab |
| 10.11 | `roll_salary_assignments` | @@avinashgroup_app/payroll/year_rollover.py::roll_salary_assignments@@ | New-year assignment for each active employee: same pay and allowances, the new year's slab; refuses without a slab from the year's first day. | Salary Structure Assignment |

## 11. Yearly payments: Dashain allowance and leave encashment

Both end as an Additional Salary that stage 6 adds to the slip, taxed in full in its month (`deduct_full_tax_on_selected_payroll_date`). Each is pressed once a year by HR and only writes drafts; HR submits after review.

| # | Function | File | What it does | Settings / data it reads |
|---|---|---|---|---|
| 11.1 | `dashain_allowance` | @@avinashgroup_app/public/js/payroll_entry.js::=function dashain_allowance(@@ | Payroll Entry → Nepal HRMS → **Dashain Allowance**: asks for the component and the cut-off date, calls `make_festival_adjustment`, shows the total and who was left out. | — |
| 11.2 | `make_festival_adjustment` | @@avinashgroup_app/payroll/festival_allowance.py::make_festival_adjustment@@ | Refuses another BS month than the component's Pay Month, or a second draft for the year; builds (or rebuilds) the entry's draft Payroll Adjustment from `compute_rows`. | Salary Component `custom_festival_pay_month`; Payroll Adjustment `source`, `payroll_entry` |
| 11.3 | `compute_rows` | @@avinashgroup_app/payroll/festival_allowance.py::compute_rows@@ | Per employee on the entry: leaves out joiners on/after the cut-off, leavers (unless included), short service, daily wage (unless included), no assignment, already paid; else one row with basic, service days, factor and amount. | Salary Component `custom_festival_*`; Employee `date_of_joining`, `relieving_date` |
| 11.4 | `service_factor` | @@avinashgroup_app/payroll/festival_allowance.py::service_factor@@ | Service days = cut-off − joining; year days = the year ending on the cut-off (365/366); 1 for a full year, else service ÷ year, clamped 0..1. | — |
| 11.5 | `monthly_basic` | @@avinashgroup_app/payroll/festival_allowance.py::monthly_basic@@ | The assignment `base` on the cut-off (a daily wage × the BS month's days). | Salary Structure Assignment `base`; Salary Structure `custom_daily_wage` |
| 11.6 | `festival_amount` | @@avinashgroup_app/payroll/festival_allowance.py::festival_amount@@ | basic × factor, never above basic; proration off pays a full month for any service. | Salary Component `custom_festival_prorate` |
| 11.7 | `PayrollAdjustment.validate_rows` | @@avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py::validate_rows@@ | Refuses a row above its `base_amount` (the 100 % cap survives hand edits). | Payroll Adjustment Row `base_amount` |
| 11.8 | `PayrollAdjustment.on_submit` | @@avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py::on_submit@@ | One submitted Additional Salary per row, full tax in the month; then re-saves the people's draft slips. | — |
| 11.9 | `encash_year_end` | @@avinashgroup_app/public/js/leave_encashment_list.js::=function encash_year_end(@@ | Leave Encashment list → **Encash Year-End Balances**: company + fiscal year, then the review table. | — |
| 11.10 | `leave_encashment.encash_year_end` | @@avinashgroup_app/payroll/leave_encashment.py::encash_year_end@@ | From the first day of the year's last BS month: active employees with an assignment → `encash_month` for that month, year-end occasion only. | Fiscal Year `year_end_date` |
| 11.11 | `encash_month` | @@avinashgroup_app/payroll/leave_encashment.py::encash_month@@ | Per due (employee, type, allocation): skips one already submitted, rebuilds a draft, inserts a Leave Encashment dated the allocation's end. | Leave Period; Leave Encashment |
| 11.12 | `due_encashments` | @@avinashgroup_app/payroll/leave_encashment.py::due_encashments@@ | Allocations of Allow Encashment types ending in the month (year end) or covering a relieving date in it (separation). | Leave Type `allow_encashment`, `custom_encash_at_year_end`, `custom_encash_at_separation`; Leave Allocation |
| 11.13 | `LeaveEncashment.get_leave_details_for_encashment` | @@../hrms/hrms/hr/doctype/leave_encashment/leave_encashment.py::get_leave_details_for_encashment@@ | HRMS: balance = allocated − carried + leaves taken; days capped by Non-Encashable / Maximum Encashable Leaves. | Leave Type `non_encashable_leaves`, `max_encashable_leaves` |
| 11.14 | `price_encashment` | @@avinashgroup_app/payroll/leave_encashment.py::price_encashment@@ | After HRMS's validate: refuses a second encashment of the allocation, a date that is neither year end nor relieving date, an occasion the type does not allow; amount = days × `per_day_rate`. | Leave Type `custom_encash_at_*` |
| 11.15 | `per_day_rate` | @@avinashgroup_app/payroll/leave_encashment.py::per_day_rate@@ | Assignment `base` ÷ Leave Type `custom_encashment_days_per_month` (blank = the BS month's days). | Salary Structure Assignment `base` |
| 11.16 | `LeaveEncashment.create_additional_salary` | @@../hrms/hrms/hr/doctype/leave_encashment/leave_encashment.py::create_additional_salary@@ | HRMS on submit: Additional Salary on the type's Earning Component, dated the encashment date. | Leave Type `earning_component` |
| 11.17 | `mark_additional_salary` | @@avinashgroup_app/payroll/leave_encashment.py::mark_additional_salary@@ | Additional Salary validate: an encashment's row is taxed in full in its month and tagged. | — |
| 11.18 | `link_additional_salary` | @@avinashgroup_app/payroll/leave_encashment.py::link_additional_salary@@ | Additional Salary on_submit: writes it back to the encashment so cancelling one cancels the other. | — |

## Settings that change the result

Values read from `avinas1` on 2026-10-12.

| Setting | Where | Value on avinas1 | Read by | Effect |
|---|---|---|---|---|
| `payroll_based_on` | Payroll Settings | Attendance | [`get_working_days_details`](@@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::get_working_days_details@@) | LWP and absent days come from Attendance, not Leave Applications |
| `include_holidays_in_total_working_days` | Payroll Settings | 1 | [`get_working_days_details`](@@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::get_working_days_details@@), [`get_payment_days`](@@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::get_payment_days@@) | Holidays are paid days and are not taken out of working or payment days |
| `consider_unmarked_attendance_as` | Payroll Settings | Present | [`get_working_days_details`](@@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::get_working_days_details@@), [`warn_missing_attendance`](@@avinashgroup_app/payroll/payroll_month.py::warn_missing_attendance@@) | A day with no attendance is paid; only marked Absent and half-absent days cut pay |
| `consider_marked_attendance_on_holidays` | Payroll Settings | 0 | [`calculate_lwp_ppl_and_absent_days_based_on_attendance`](@@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::calculate_lwp_ppl_and_absent_days_based_on_attendance@@) | Absent / Half Day rows on holidays are not counted |
| `daily_wages_fraction_for_half_day` | Payroll Settings | 0.5 | [`get_working_days_details`](@@../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py::get_working_days_details@@) | A half-absent day costs 0.5 day; a half day of LWP leave costs 0.5 |
| `process_payroll_accounting_entry_based_on_employee` | Payroll Settings | 0 | [`make_accrual_jv_entry`](@@../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py::make_accrual_jv_entry@@) | Payable side posted in one line, not per employee |
| `process_payroll_in_nepali_month` | Nepal HRMS Settings | 1 | [`get_date_details`](@@../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py::get_date_details@@), [`validate_payroll_entry`](@@avinashgroup_app/payroll/bs_period_guard.py::validate_payroll_entry@@) | Slips cover BS months; the BS guard is active |
| `enable_auto_attendance` | Shift Type (`NGI 9:00 AM to 5:00 PM`, `NGK 9:00 AM to 5:00 PM`) | 0 on both | [`process_auto_attendance_for_all_shifts`](@@../hrms/hrms/hr/doctype/shift_type/shift_type.py::process_auto_attendance_for_all_shifts@@), [`heal_unlinked_checkins`](@@avinashgroup_app/biometric/attendance_self_heal.py::heal_unlinked_checkins@@) | Off: neither HRMS auto attendance nor self-heal marks anything; attendance comes from Attendance Fix or by hand |
| `start_time` / `end_time` | Shift Type | 09:00–17:00 on both | [`compute_shift_deviations`](@@avinashgroup_app/biometric/attendance_sync.py::compute_shift_deviations@@) | Base of late / early minutes, OT outside shift, meals |
| `begin_check_in_before_shift_start_time` / `allow_check_out_after_shift_end_time` (minutes) | Shift Type | NGI 180 / 240; NGK 60 / 60 | [`fetch_shift`](@@../hrms/hrms/hr/doctype/employee_checkin/employee_checkin.py::fetch_shift@@), [`_shift_window_closed`](@@avinashgroup_app/biometric/attendance_self_heal.py::_shift_window_closed@@) | Punch window that ties a checkin to the shift; self-heal waits for the end buffer |
| `determine_check_in_and_check_out` / `working_hours_calculation_based_on` | Shift Type | Alternating entries; First Check-in and Last Check-out (both) | [`calculate_working_hours`](@@../hrms/hrms/hr/doctype/employee_checkin/employee_checkin.py::calculate_working_hours@@) | Hours = first punch to last punch |
| `working_hours_threshold_for_half_day` / `_for_absent` | Shift Type | 0 / 0 on both | [`get_attendance`](@@../hrms/hrms/hr/doctype/shift_type/shift_type.py::get_attendance@@) | Off: short hours never make a Half Day or Absent |
| `custom_half_day_if_late_by_hours` | Shift Type | 2.00 on both | [`enforce_late_arrival_half_day`](@@avinashgroup_app/biometric/attendance_override.py::enforce_late_arrival_half_day@@) | In after 11:00 → Half Day, half absent |
| `process_attendance_after` | Shift Type | NGI 2026-10-09; NGK 2026-06-29 | [`process_auto_attendance`](@@../hrms/hrms/hr/doctype/shift_type/shift_type.py::process_auto_attendance@@), [`heal_unlinked_checkins`](@@avinashgroup_app/biometric/attendance_self_heal.py::heal_unlinked_checkins@@) | Earliest day auto attendance and self-heal touch |
| `custom_rate_basis` | Salary Component | Hourly Basic × Multiplier: Overtime, Late Fine. Fixed Rate: the rest | [`_resolve_rate`](@@avinashgroup_app/payroll/attendance_allowance.py::_resolve_rate@@) | Computed from the person's basic instead of the assignment row's Rate |
| `custom_rate_multiplier` | Salary Component | Overtime 1.5; Late Fine 1 | [`_resolve_rate`](@@avinashgroup_app/payroll/attendance_allowance.py::_resolve_rate@@) | Multiplies the hourly basic |
| `custom_rate_days_per_month` / `custom_rate_hours_per_day` | Salary Component | Overtime and Late Fine blank: the BS month's actual days / 8 hours (decided 2026-10-12; the client's sheets used 30) | [`_hourly_basic`](@@avinashgroup_app/payroll/attendance_allowance.py::_hourly_basic@@) | Divisors of the hourly basic |
| `custom_pay_on_holiday` | Salary Component | Tea & Conveyance: Do Not Pay; others Pay | [`evaluate_rule`](@@avinashgroup_app/payroll/attendance_allowance.py::evaluate_rule@@) | No tea on a day worked on a holiday |
| `custom_half_day_counts` | Salary Component | Full Day on all | [`evaluate_rule`](@@avinashgroup_app/payroll/attendance_allowance.py::evaluate_rule@@) | A Half Day earns a full day of a Status = Present component |
| `custom_time_offset_hours` | Salary Component | Meal 1.5; others 0 | [`_meals_for_day`](@@avinashgroup_app/payroll/attendance_allowance.py::_meals_for_day@@), [`evaluate_rule`](@@avinashgroup_app/payroll/attendance_allowance.py::evaluate_rule@@) | Early / late minutes needed for a meal (or for Early Entry / Late Stay / Late Arrival components) |
| `custom_max_per_day` | Salary Component | Meal 2; others 0 (no cap) | [`_meals_for_day`](@@avinashgroup_app/payroll/attendance_allowance.py::_meals_for_day@@) | Cap on meals per day |
| `custom_ot_eligible_only` | Salary Component | Meal 1, Overtime 1; others 0 | [`_skip_for_eligibility`](@@avinashgroup_app/payroll/attendance_allowance.py::_skip_for_eligibility@@) | Paid only to employees with `custom_ot_eligibility` |
| `custom_is_festival_allowance`, `custom_festival_pay_month`, `custom_festival_min_service_days`, `custom_festival_prorate`, `custom_festival_include_daily_wage`, `custom_festival_include_leavers` | Salary Component | Dashain Allowance only: ✓, 06 - Ashwin, 0, 1, 0, 0 (2026-10-13) | [`compute_rows`](@@avinashgroup_app/payroll/festival_allowance.py::compute_rows@@) | Who gets the Dashain allowance, and on which month's entry |
| `allow_encashment`, `max_encashable_leaves`, `non_encashable_leaves`, `earning_component` | Leave Type | Casual, Sick: 1, 0, 0, Leave Encashment; others not encashable | [`due_encashments`](@@avinashgroup_app/payroll/leave_encashment.py::due_encashments@@) | Which balances are encashed, and how many days |
| `custom_encash_at_year_end`, `custom_encash_at_separation`, `custom_encashment_days_per_month` | Leave Type | Casual, Sick: 1, 1, blank (BS month's days) | [`price_encashment`](@@avinashgroup_app/payroll/leave_encashment.py::price_encashment@@), [`per_day_rate`](@@avinashgroup_app/payroll/leave_encashment.py::per_day_rate@@) | When encashment is allowed, and the per-day divisor |
| `custom_condition_type` / `custom_unit` | Salary Component | Tea & Conveyance: Status = Present, Per Day. Meal: Meal Entitlement. Overtime: Authorised Overtime, Per Hour. Late Fine: Late Time, Per Hour | [`evaluate_rule`](@@avinashgroup_app/payroll/attendance_allowance.py::evaluate_rule@@) | Which rule counts the quantity, and in what unit |

## Checking the links

Every link and CodeTour step on this page was checked by a script that opens the file and confirms the target line holds the named function or symbol. After editing any of these files, re-check by searching for `def <name>` in the file and updating the line number here and in `.tours/salary-calculation.tour`.
