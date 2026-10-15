# 04 · Overtime Sheet → measurement → replacement leave

Extra work — a festival holiday, a Saturday, or staying past the shift on a normal day — is paid only when the company *asked for it*. The **Overtime Sheet** records that request, and attendance supplies the hours. A plant (OT-eligible) worker's row turns into overtime hours and meals in payroll (stage [05](05-payroll-entry.md)). An officer or admin row becomes a day of **Replacement Leave**, through HRMS's Compensatory Leave Request.

```
 Overtime Sheet (draft) ──validate──► hr/overtime.evaluate()  day type × Employee ticks → entitlement
        │ submit (no approval rule on avinas1, so a plain submit)
        ├──► overtime_settlement.on_sheet_submit ─► measure_row() ─► row.worked_hours / attendance / settlement_note
        │       (+ daily job measure_pending, + "Measure from Attendance" button)
        └──► replacement_leave.on_sheet_submit ──► grant_row() ─► Compensatory Leave Request ─► Leave Allocation (Replacement Leave)
                (+ daily job grant_pending; on_cancel takes it back)

 Payroll (stage 05): Overtime component  = Σ row.worked_hours (Overtime rows) × hourly basic × 1.5
                     Meal component      = only on a day the person is on a submitted sheet with Overtime entitlement
```

**HRMS vs us.** Stock HRMS v15 has no overtime model at all; it has neither an overtime request nor overtime pay. The doctypes, rules, measuring and pay are all ours. The only HRMS piece used is **Compensatory Leave Request**, which turns a worked holiday into a leave allocation.

Policy source: the client minutes `docs/hr-decisions/00-policy-minutes-2026-09-15.txt` ([file](../hr-decisions/00-policy-minutes-2026-09-15.txt)), items 5.1 (the sheet decides eligibility), 2.2 (as corrected 2026-09-16) and 2.5 (holiday work: plant staff paid OT, officer/admin get replacement leave, never both). User-facing description: [docs/overtime-sheet.md](../overtime-sheet.md) and [user guide ch. 4](../user-guide/04-overtime-and-meals.md).

---

## 4.1 Doctypes: Overtime Sheet and Overtime Sheet Employee

| | |
|---|---|
| **What** | A submittable document, one per company and **work date**, listing who was asked in. Naming `OTS-.YYYY.-` (AD year, *not* the BS fiscal year). No times are typed on it; hours come from attendance. |
| **Why** | Policy 5.1: "a punch outside normal hours proves presence, not that the company asked". The module docstring ([`Overtime Sheet`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.py#L1)) says that backdated sheets are allowed on purpose, because extra work is often arranged by phone. The doctype replaced an earlier holiday-only "Holiday Duty Sheet", which patch `setup_overtime_sheet` deletes. |
| **Where** | Controller [`OvertimeSheet`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.py#L33); form script [`OVERTIME_PREVIEW`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.js#L4); JSON [`is_submittable`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.json#L8) |
| **Triggered by** | HR (roles HR Manager, HR User, System Manager) creating the sheet. |
| **Reads / Writes** | Writes its own rows. Reads Employee (incl. the Overtime Eligible / Replacement Leave ticks), Holiday List, Shift Assignment and Shift Type through `evaluate`. |
| **Impacts downstream** | Payroll pays Overtime and Meal **only** for rows on *submitted* sheets with entitlement `Overtime` (see 4.6). The attendance reports show an OT day only when a sheet authorises it (`get_overtime_days`). Replacement leave is credited from `Replacement Leave` rows. |
| **Config on avinas1** (2026-10-12) | 3 sheets, all NGI, all submitted, 3 rows, all entitlement `Overtime`, 14.0 measured hours in total (2026-07-21 … 07-25). No `Replacement Leave` row has ever been made. |
| **Gotchas** | No **Dynamic Approval Setting** exists for Overtime Sheet on avinas1: the only settings are for Leave Application and Purchase Order. Anyone with submit permission therefore authorises overtime directly. The docstring's "approval runs through Dynamic Approval" is only true once a setting is created (see [09-cross-cutting.md](09-cross-cutting.md)). Patch `setup_overtime_sheet` adds the audit field `custom_created_by` so that a rule *could* match. |

### Header fields

| Field | Type | Meaning |
|---|---|---|
| [`company`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.json#L39) | Link Company | Every row's employee must belong to it (`validate_rows`). |
| [`work_date`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.json#L48) | Date | The one day the sheet authorises. |
| [`day_summary`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.json#L57) | Data, read only | E.g. "Dashain / Weekly Off / Working Day", from `set_totals`. |
| [`reason`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.json#L75) | Small Text, required | Why the work was needed. |
| [`total_employees`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.json#L99), [`overtime_count`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.json#L109), [`replacement_leave_days`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.json#L116) | Int, read only | Totals. |
| [`total_worked_hours`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.json#L122) | Float, read only | The sum of measured hours, written by settlement with `db_set`. |

### Row fields (Overtime Sheet Employee)

| Field | Written by | Read by |
|---|---|---|
| [`employee`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet_employee/overtime_sheet_employee.json#L24) | HR | everything |
| [`work_type`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet_employee/overtime_sheet_employee.json#L42) (`Work on Holiday` / `Overtime`) | HR, or pre-filled from the day by `preview` | `evaluate`, `measure_row` |
| [`day_type`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet_employee/overtime_sheet_employee.json#L56) (Holiday / Weekly Off / Working Day) | `apply_rules` | replacement-leave reason text |
| [`entitlement`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet_employee/overtime_sheet_employee.json#L65) (`Overtime` / `Replacement Leave`) | `apply_rules`, never HR | settlement, replacement leave, **payroll** (`_on_overtime_sheet`, `_authorised_overtime_hours`), reports (`get_overtime_days`) |
| [`shift`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet_employee/overtime_sheet_employee.json#L93) | `apply_rules` (snapshot) | display only |
| [`worked_hours`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet_employee/overtime_sheet_employee.json#L86) | settlement (`db_set`). **Read only**: HR cannot type it | **payroll**: OT quantity |
| [`attendance`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet_employee/overtime_sheet_employee.json#L115) | settlement | `_is_unmeasured` |
| [`settlement_note`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet_employee/overtime_sheet_employee.json#L103) | settlement and replacement leave (both write it) | `_is_unmeasured` (the "already measured" marker) |
| [`compensatory_leave_request`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet_employee/overtime_sheet_employee.json#L109) | `grant_row` | `on_sheet_cancel`, `grant_pending` |

**Contradiction.** The `shift_day` docstring ([`put it through the`](../../avinashgroup_app/hr/shift_day.py#L29)) says a one-off agreement such as "after 5pm counts as 2 hours" should go "through the Overtime Sheet, where authorised hours can be typed over". In fact `worked_hours` is `read_only` and not allow-on-submit, so the desk cannot type over it. Only a script or a `db_set` can.

---

## 4.2 Validation on save: `OvertimeSheet.validate`

| Step | Function | What it does |
|---|---|---|
| 1 | [`validate_rows`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.py#L40) | Refuses an employee listed twice, or an employee of another company. |
| 2 | [`apply_rules`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.py#L55) | Runs `evaluate` on every row, writes back work type, day type, entitlement and shift, and reports **all** refused rows in one message. |
| 3 | [`validate_not_already_authorised`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.py#L77) | Nobody may be on two live (draft or submitted) sheets for the same date, because the work would be paid twice. |
| 4 | [`set_totals`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.py#L99) | Fills the counts and `day_summary`. |

The form evaluates each row live through [`preview`](../../avinashgroup_app/hr/overtime.py#L223) (called by [`preview_row`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.js#L59)). The script fills `work_type` only when HR has left it blank, and clears a stale entitlement when a row is refused.

---

## 4.3 The rules: `hr/overtime.py`

The module docstring ([`Overtime rules`](../../avinashgroup_app/hr/overtime.py#L1)) separates **policy** (the two ticks on the Employee), **authorisation** (Overtime Sheet) and **rules** (this module). "This module is the only place the rules live." It deliberately contains no attendance and no money.

### `evaluate(employee, work_date, work_type)`: day type × Employee ticks

[`evaluate`](../../avinashgroup_app/hr/overtime.py#L150)

| Work type | Day for *this* employee | Employee `custom_ot_eligibility` | Employee `custom_compensatory_leave` | Result |
|---|---|---|---|---|
| Work on Holiday | Holiday or Weekly Off | 1 | – | entitlement **Overtime** |
| Work on Holiday | Holiday or Weekly Off | 0 | 1 | entitlement **Replacement Leave** |
| Work on Holiday | Holiday or Weekly Off | 0 | 0 | refused: "has neither Overtime Eligible nor Replacement Leave … ticked" |
| Work on Holiday | Working Day | any | any | refused: "choose Overtime" |
| Overtime | Working Day | 1, and a shift exists | – | entitlement **Overtime** |
| Overtime | Working Day | 1, no shift | – | refused: "no shift … cannot be measured" |
| Overtime | Working Day | 0 | – | refused: "is not ticked Overtime Eligible, so cannot be given overtime on a working day" |
| Overtime | Holiday or Weekly Off | any | any | refused: "choose Work on Holiday" |

A blank work type defaults through [`default_work_type`](../../avinashgroup_app/hr/overtime.py#L145): a holiday or Saturday becomes holiday work, any other day overtime.

### Helpers

| Function | What | Reads | Note |
|---|---|---|---|
| [`get_day_type`](../../avinashgroup_app/hr/overtime.py#L60) | `Holiday`, `Weekly Off` or `Working Day` from the employee's **own** holiday list (`get_holiday_list_for_employee`: the Employee's list first, then the company default). | Holiday (`weekly_off`, `description`) | Resolved per employee because the lists differ: Teej is a holiday only on the "(Women)" lists. See [01-masters.md](01-masters.md). |
| [`get_shift_window`](../../avinashgroup_app/hr/overtime.py#L91) | `(shift_type, start_dt, end_dt)`: the latest active, submitted Shift Assignment covering the date, otherwise Employee `default_shift`. Handles overnight shifts. | Shift Assignment, Employee, Shift Type `start_time`/`end_time` | Also used by settlement and by the attendance hooks ([02](02-checkin-to-attendance.md)). |
| [`get_holiday_work_rule`](../../avinashgroup_app/hr/overtime.py#L121) | `(ot_eligible, compensatory_leave)` from the Employee's two ticks. | Employee `custom_ot_eligibility`, `custom_compensatory_leave` | Neither ticked → `evaluate` refuses holiday work: "a wrong default pays money or grants leave." |
| [`validate_employee_holiday_rule`](../../avinashgroup_app/hr/overtime.py#L136) | Employee `validate` hook: refuses both ticks at once. | – | Replaces the either/or check that lived on Employee Category. |
| [`hours_outside_shift`](../../avinashgroup_app/hr/overtime.py#L320) | Hours of `[in, out]` before the shift start or after its end. A window that does not overlap the shift counts in full. | – | The working-day OT measure, rounded to 2 decimals here (half-hour rounding is applied by the caller). |
| [`get_overtime_days`](../../avinashgroup_app/hr/overtime.py#L263) | `{(employee, date)}` with a submitted Overtime row over a period. | sheets | Used by the Monthly Attendance (BS) report and its summary. |
| [`get_authorised`](../../avinashgroup_app/hr/overtime.py#L236), [`was_authorised`](../../avinashgroup_app/hr/overtime.py#L309) | The "read API" the docstring names. | sheets | **Dead code**: nothing in the app calls either one. Payroll queries the sheet tables directly. |

### Config on avinas1 (2026-10-13)

Until 2026-10-13 the two answers came from the Employee Category (removed the same day, with the Overtime Sheet Employee `employee_category` column, by `drop_employee_category`) the person was linked to (`Operation`: overtime; `Officer & Admin`: replacement leave). Patch `holiday_work_rule_on_employee` ([`execute`](../../avinashgroup_app/patches/holiday_work_rule_on_employee.py#L27)) copied each member's answer onto the Employee ticks:

| Active employees | `custom_ot_eligibility` | `custom_compensatory_leave` |
|---|---|---|
| 2 (NGI, were `Operation`) | 1 | 0 |
| 2 (NGI, were `Officer & Admin`) | 0 | 1 |
| 261 (96 more at NGI, and every employee at NGG, NGK and NGN) | 0 | 0 |

A holiday-work Overtime Sheet row for any of the 261 is refused ("has neither … ticked"), and they get no Overtime or Meal in payroll. See [01-masters.md](01-masters.md).

---

## 4.4 Measuring hours: `hr/overtime_settlement.py`

| | |
|---|---|
| **What** | For each row with entitlement **Overtime** on a submitted sheet, reads that day's submitted Attendance and writes `worked_hours`, `attendance` and `settlement_note`, then the sheet's `total_worked_hours`. |
| **Why** | Docstring ([`Measure authorised overtime`](../../avinashgroup_app/hr/overtime_settlement.py#L1)): the sheet says the company asked; attendance says how long the work lasted. "Measuring used to be a button only, so overtime paid 0 for any sheet nobody thought to press it on." Commits 240ea3c (2026-09-21) and 297ebbd (2026-09-27). |
| **Triggered by** | (a) the hook on Overtime Sheet `on_submit` [`on_sheet_submit`](../../avinashgroup_app/hooks.py#L457), only when the work date is already past; (b) the daily job [`measure_pending`](../../avinashgroup_app/hooks.py#L539) in `daily_long`; (c) the **Measure from Attendance** button [`Measure from Attendance`](../../avinashgroup_app/avinash_group_app/doctype/overtime_sheet/overtime_sheet.js#L23), shown on a submitted sheet. |
| **Reads** | Attendance (`status`, `in_time`, `out_time`, `working_hours`), Shift Assignment and Shift Type through `get_shift_window`. |
| **Writes** | Overtime Sheet Employee `worked_hours`, `attendance`, `settlement_note`; Overtime Sheet `total_worked_hours`. All via `db_set(update_modified=False)` on a submitted doc, so there is no version history. |
| **Impacts downstream** | `worked_hours` is the **quantity of the Overtime component** in payroll (4.6). Re-measuring after Prepare Payroll Inputs changes nothing on the slip until Prepare Payroll Inputs is pressed again. |

### `measure_row`: the measuring rule

[`measure_row`](../../avinashgroup_app/hr/overtime_settlement.py#L80)

| Situation | Hours | `settlement_note` |
|---|---|---|
| Entitlement is not Overtime | 0 | "Earns replacement leave, not overtime" |
| No submitted Attendance | 0 | "No attendance — called in but did not come" |
| Attendance `Absent` | 0 | "Marked absent" |
| Missing in or out time (one punch) | 0 | "Only one punch — the hours cannot be measured" |
| **Work on Holiday** | `working_hours` (otherwise out − in), rounded to the half hour | "Hours worked on a holiday" |
| **Overtime**, no shift | 0 | "No shift on this date" |
| **Overtime** | `hours_outside_shift(in, out, shift_start, shift_end)`, rounded to the half hour | "Hours outside the {shift} shift" |

Rounding: [`round_to_half_hour`](../../avinashgroup_app/hr/shift_day.py#L42) rounds to the nearest half hour with halves rounding up (7:34 → 7.5, 7:53 → 8). It is the same function the attendance report uses, "so pay and the report never disagree" ([03-shift-measurement.md](03-shift-measurement.md)).

Note that a Half Day attendance still measures in full here: only `Absent` is zeroed.

### Three entry points

| Function | Scope | Overwrites HR's work? |
|---|---|---|
| [`measure`](../../avinashgroup_app/hr/overtime_settlement.py#L140) → [`measure_sheet`](../../avinashgroup_app/hr/overtime_settlement.py#L59) (button) | **every** row, Replacement Leave rows included | Yes. It re-measures and overwrites. On a Replacement Leave row it replaces the note "1 day of replacement leave granted" with "Earns replacement leave, not overtime"; the link to the Compensatory Leave Request is kept. |
| [`on_sheet_submit`](../../avinashgroup_app/hr/overtime_settlement.py#L203) → [`measure_unmeasured`](../../avinashgroup_app/hr/overtime_settlement.py#L185) | Overtime rows never measured | No |
| [`measure_pending`](../../avinashgroup_app/hr/overtime_settlement.py#L214) (daily) | submitted sheets with work date from today − [`LOOKBACK_DAYS`](../../avinashgroup_app/hr/overtime_settlement.py#L56) (62) to yesterday, unmeasured Overtime rows | No |

"Unmeasured" is decided by [`_is_unmeasured`](../../avinashgroup_app/hr/overtime_settlement.py#L175): no note, no hours and no attendance. Every measurement writes a note, so a row measured as zero is not redone.

**Gotcha (timing):** the daily job measures a row **once**. If attendance for a past date arrives after the job has run, the row is measured as 0 ("No attendance") and the next run skips it, because it now has a note. Re-measuring then needs the button. The 62-day retry window only helps for a sheet whose rows were never touched. The docstring's "for the sheets whose attendance arrived later" holds only when the sheet was submitted ahead of the day, or when the job had not yet seen the row.

**Dead code:** [`get_measured_hours`](../../avinashgroup_app/hr/overtime_settlement.py#L146) ("what payroll pays") is not called anywhere. Payroll reads the rows itself in `_authorised_overtime_hours`.

---

## 4.5 Replacement leave: `hr/replacement_leave.py`

| | |
|---|---|
| **What** | Turns each `Replacement Leave` row whose attendance shows the person worked into a submitted **Compensatory Leave Request** (HRMS). That request creates or tops up a **Leave Allocation** of type *Replacement Leave*. |
| **Why** | Docstring ([`Credit replacement leave`](../../avinashgroup_app/hr/replacement_leave.py#L1)): "Until now nothing turned that row into leave, so the day was promised on paper and never reached a balance." HRMS's own document is used for its audit trail and checks. Commit 297ebbd (2026-09-27). |
| **Triggered by** | [`on_sheet_submit`](../../avinashgroup_app/hooks.py#L457) (dates already past), the daily job [`grant_pending`](../../avinashgroup_app/hooks.py#L539) (`daily_long`, 62-day lookback), and [`on_sheet_cancel`](../../avinashgroup_app/hooks.py#L458). |
| **Reads** | Attendance `status` for the date. |
| **Writes** | Compensatory Leave Request (inserted and submitted with `ignore_permissions`), which through HRMS creates a Leave Allocation or Leave Ledger Entry. Row `compensatory_leave_request` and `settlement_note`. On failure, an Error Log. |
| **Impacts downstream** | The Replacement Leave balance shown in Leave Application and in the Yearly Leave Details (BS) report. Pay is not affected: the type has `allow_encashment` 0, and taking the day is ordinary paid leave. |

[`grant_row`](../../avinashgroup_app/hr/replacement_leave.py#L140):

| Attendance on the work date | Result |
|---|---|
| shown up ([`shown_up`](../../avinashgroup_app/hr/replacement_leave.py#L81): any Employee Checkin that day, or a submitted Attendance with `in_time`) | 1 full day (CLR `half_day` = 0), whatever the status — Half Day, late, few hours (user, 2026-10-15) |
| not shown up | nothing yet; the note says "waits: no punch" and the daily job retries |
| an older ½-day grant | [`grant_pending`](../../avinashgroup_app/hr/replacement_leave.py#L118) cancels it and grants 1 day |
| a corrected day ([`recheck_day`](../../avinashgroup_app/hr/replacement_leave.py#L194), from `punch_correction.remark_day`) | granted / topped up / taken back to match; a refused take-back keeps the grant, notes the row, warns, and is logged in the Attendance Correction Log |
| HRMS refuses (ValidationError) | rolled back to a savepoint; the note says "Replacement leave not granted: …"; Error Log |

HRMS's own checks then run inside the request: [`validate_holidays`](../../../hrms/hrms/hr/doctype/compensatory_leave_request/compensatory_leave_request.py#L60) (the date must be a holiday on the employee's list) and [`validate_attendance`](../../../hrms/hrms/hr/doctype/compensatory_leave_request/compensatory_leave_request.py#L36) — which our own grants skip (`ReplacementLeaveRequest`, `override_doctype_class`, when `flags.shown_up_on_holiday` is set), because it wants Present and gives a Half Day ½. Grants set `frappe.flags.audit_user`, so the Leave Allocation HRMS creates gets the `custom_created_on` the naming engine needs for its fiscal year — without it the nightly job's grants failed with "Date field … is required for Leave Allocation". Then [`on_submit`](../../../hrms/hrms/hr/doctype/compensatory_leave_request/compensatory_leave_request.py#L73) needs an **active Leave Period** covering the day after the work date, or it throws "No Leave Period Found".

[`on_sheet_cancel`](../../avinashgroup_app/hr/replacement_leave.py#L106) cancels each linked submitted request (HRMS then reverses the allocation) and clears the link.

Leave type: [`REPLACEMENT_LEAVE_TYPE`](../../avinashgroup_app/hr/replacement_leave.py#L55) = "Replacement Leave", created by patch `setup_leave_types` (`#2` re-run, [`Replacement Leave`](../../avinashgroup_app/patches/setup_leave_types.py#L68)).

### Config on avinas1 (2026-10-12)

| Item | Value |
|---|---|
| Leave Type *Replacement Leave* | `is_compensatory` 1, `include_holiday` 1, `allow_encashment` 0, `is_carry_forward` 0 |
| **Leave Period** records | **0** for every company |
| Replacement Leave rows ever | 0 |

**Open issue:** with no Leave Period on avinas1, every replacement-leave grant would fail with "No Leave Period Found". That would be logged on the row and in the Error Log, and retried daily for 62 days. `hr/year_setup.py` can create Leave Periods ([`Leave Period`](../../avinashgroup_app/hr/year_setup.py#L307)), but none exist on avinas1. See [08-changes-over-time.md](08-changes-over-time.md).

---

## 4.6 How the sheet reaches payroll

Two components in `payroll/attendance_allowance.py` read the sheet directly. Both require a **submitted** sheet and a row with entitlement **Overtime**. The full engine is in [05-payroll-entry.md](05-payroll-entry.md).

| Component (condition) | Function | Reads | Quantity |
|---|---|---|---|
| Overtime (`Authorised Overtime`, Per Hour) | [`_authorised_overtime_hours`](../../avinashgroup_app/payroll/attendance_allowance.py#L437) | `SUM(worked_hours)` for the employee and date | hours; rate = hourly basic × 1.5 |
| Meal (`Meal Entitlement`) | [`_meals_for_day`](../../avinashgroup_app/payroll/attendance_allowance.py#L356) via [`_on_overtime_sheet`](../../avinashgroup_app/payroll/attendance_allowance.py#L411) | *existence* of the row (not its hours) | holiday: by hours worked first IN to last OUT ([`holiday_hours_worked`](../../avinashgroup_app/hr/shift_day.py#L137), rounded to the half hour), [`HOLIDAY_MEAL_HOURS`](../../avinashgroup_app/payroll/attendance_allowance.py#L400) 8 h → 2, 6 h → 1; working day: 1 if `custom_early_entry` ≥ 1.5 h, plus 1 if `custom_late_exit` ≥ 1.5 h; capped at `custom_max_per_day` (2) |

Consequences:

* A holiday row earns two meals as soon as the sheet is submitted, even with 0 measured hours, provided that day's Attendance is Present or Half Day and the person is OT eligible. The meal code checks attendance status but not `worked_hours`.
* Overtime pay is evaluated per **attendance row**: `_qty_for_employee` loops over the month's submitted Attendance, and OT hours are only counted for dates that have one. A sheet date without an attendance row (which settlement measures as 0 in any case) contributes nothing.
* Meal uses the attendance deviation fields `custom_early_entry` / `custom_late_exit` (written by the Attendance hooks, [02](02-checkin-to-attendance.md)). Overtime hours use `in_time`/`out_time` against the shift window. Both measure against the same shift, but through different code paths.
* Cancelling a sheet does **not** remove Additional Salary that Prepare Payroll Inputs already posted. Press the button again: it now removes rows that are no longer due (fixed 2026-10-12, see [05 §5.6](05-payroll-entry.md#56-the-attendance-engine-payrollattendance_allowancepy)).

### Worked example (avinas1, NGI, Shrawan 2083)

| Sheet | Date | Employee | Work type / day | Attendance | `worked_hours` |
|---|---|---|---|---|---|
| OTS-2026-00001 | 2026-07-21 | NGI-EMP-00040 Ramhari Koirala | Overtime / Working Day | NGI-ATT-83/84-00004 | 3.5 |
| OTS-2026-00003 | 2026-07-25 | NGI-EMP-00040 | Work on Holiday / Weekly Off | NGI-ATT-83/84-00008 | 8.5 |
| OTS-2026-00002 | 2026-07-22 | NGI-EMP-00080 Rikesh Kumar Chaudhary | Overtime / Working Day | NGI-ATT-83/84-00032 | 2.0 |

Ramhari: 3.5 + 8.5 = **12 OT hours**. Meals: the Saturday gives 2; on 07-21 he was at least 1.5 h early and at least 1.5 h late, which gives 2; total **4 meals**. Both match Additional Salary HR-ADS-26-10-00004 (qty 12) and HR-ADS-26-10-00002 (qty 4 × 75). The pricing is worked in [05 §5.6](05-payroll-entry.md#worked-example-ngi-emp-00040-shrawan-2083).

---

## 4.7 Hooks and jobs (overtime only)

| Hook / job | Handler | Order note |
|---|---|---|
| Overtime Sheet `on_submit` | [`on_sheet_submit`](../../avinashgroup_app/hooks.py#L457) then [`on_sheet_submit`](../../avinashgroup_app/hooks.py#L457) | Independent: each handles its own entitlement. |
| Overtime Sheet `on_cancel` | [`on_sheet_cancel`](../../avinashgroup_app/hooks.py#L458) | Hours and Additional Salary are left as they are. |
| `daily_long` | `grant_pending`, `measure_pending` | Both use a 62-day lookback. |
| `*` validate / before_save / on_update | Dynamic Approval, Numbering engine, SMS | No-op for Overtime Sheet on avinas1 (no settings). See [hooks-inventory.md](hooks-inventory.md). |

## 4.8 What to check if overtime looks wrong

1. The employee is ticked **Overtime Eligible** (`custom_ot_eligibility`) on the Employee (4.3).
2. The sheet is **submitted**, not draft, and the row's entitlement is *Overtime*.
3. The row's `settlement_note`, and whether `worked_hours` were measured. If attendance came late, press **Measure from Attendance**.
4. A submitted Attendance with both in and out times exists for the date.
5. The employee's Salary Structure Assignment has an **Overtime** row in Allowances (Overtime is `custom_is_allowance` = 1: no row means not paid, [05 §5.6](05-payroll-entry.md)).
6. **Prepare Payroll Inputs** was pressed *after* steps 1–5.
