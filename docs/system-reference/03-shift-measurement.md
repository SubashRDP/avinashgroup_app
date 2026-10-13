# 03 · Shift measurement: late, early, half day

Once an Attendance row exists ([02-checkin-to-attendance.md](02-checkin-to-attendance.md)), every money-relevant number about the *time* of the day — late minutes, early-leaving minutes, overtime hours, half day — is measured **against the shift the person was rostered on that date**. This page documents the measuring code, who consumes it, and the attendance reports built on it.

Next: [04-overtime.md](04-overtime.md) (how authorised OT hours are measured and paid), [05-payroll-entry.md](05-payroll-entry.md) (where Late Time becomes a Late Fine Additional Salary). Settings table for the components: [salary-code-map.md](../salary-code-map.md#settings-that-change-the-result).

Values from avinas1 dated **2026-10-12**.

---

## The three layers

| Layer | Code | Stored? | Who reads it |
|---|---|---|---|
| 1. Which shift on which date | [`get_shift_window`](../../avinashgroup_app/hr/overtime.py#L91) (one day) and [`ShiftRoster`](../../avinashgroup_app/hr/shift_day.py#L65) (a period) | Shift written to `Attendance.shift` | Attendance hooks, OT settlement, reports, Shift Roster page |
| 2. Raw deviations in seconds | [`compute_shift_deviations`](../../avinashgroup_app/biometric/attendance_sync.py#L135) | **Yes**: `custom_late_entry`, `custom_early_entry`, `custom_early_exit`, `custom_late_exit` on Attendance | layer 3, meals, Early Entry / Late Stay / Late Arrival components |
| 3. Which deviations count on which day | [`measure_day`](../../avinashgroup_app/hr/shift_day.py#L111) | No — computed on read | Late Fine (via `evaluate_rule` "Late Time"), attendance reports, slip daily breakdown |

The **>2 h late = Half Day** rule is not here: it is an Attendance validate hook that changes the status ([02 §5](02-checkin-to-attendance.md#5-attendance-validate-hrms-first-then-our-four-hooks)). Layer 3 then *reads* the Half Day status and stops charging late minutes for it.

---

## 1. Which shift: `get_shift_window` and `ShiftRoster`

| | |
|---|---|
| **What** | `get_shift_window(employee, date)` → `(shift_type, start_dt, end_dt)`: the latest-starting **submitted, Active Shift Assignment** covering the date, else the Employee's **Default Shift**; end moves to the next day if ≤ start (overnight). `(None, None, None)` if unrostered. `ShiftRoster(employees, start, end).shift_on(employee, day)` answers the same question for a whole period with one query ([`shift_on`](../../avinashgroup_app/hr/shift_day.py#L101)). |
| **Why** | `ShiftRoster` docstring: shift changes split an assignment in two (`hr/shift_change.py`), so one month can hold two shifts; resolving once per employee "shows whichever assignment happened to sort last for the whole month". Same precedence as HRMS. |
| **Triggered by** | `set_shift_deviation_fields` fills a blank `Attendance.shift` from `get_shift_window` ([`get_shift_window(doc.employee`](../../avinashgroup_app/biometric/attendance_override.py#L38)); OT settlement; Monthly Attendance BS ([`ShiftRoster(employees`](../../avinashgroup_app/avinash_group_app/report/monthly_attendance_bs/monthly_attendance_bs.py#L100)); the Shift Roster page ([`roster`](../../avinashgroup_app/hr/shift_roster.py#L30)); shift rotation. |
| **Config on avinas1** | 0 Shift Assignments; 4 employees have `default_shift` (all `NGI 9:00 AM to 5:00 PM`); both Shift Types run 09:00–17:00, `custom_in_rotation = 0`. Everyone else has **no shift** → no deviations, no late rule, no late fine, no meals. |
| **Gotcha** | HRMS's own auto attendance resolves the shift from the checkin time (`fetch_shift`, with the check-in window), ours from the date. They agree for day shifts; they could differ for a punch far outside the window (unverified). |

## 2. Raw deviations: `compute_shift_deviations`

| | |
|---|---|
| **What** | Shift start/end as datetimes on the attendance date (end + 1 day if overnight). `in_time` after start → `custom_late_entry`; before → `custom_early_entry`. `out_time` before end → `custom_early_exit`; after → `custom_late_exit`. Only one of each pair is non-zero. Seconds, rounded to the nearest minute ([`_round_to_minute`](../../avinashgroup_app/biometric/attendance_sync.py#L127): ≥ 30 s up). **No grace period.** |
| **Triggered by** | Every Attendance validate ([`set_shift_deviation_fields`](../../avinashgroup_app/biometric/attendance_override.py#L8)), and [`refresh_attendance_values`](../../avinashgroup_app/biometric/attendance_sync.py#L169) when a late punch moves in/out on an existing row. |
| **Reads** | Shift Type `start_time`, `end_time`; Attendance `in_time`, `out_time`, `attendance_date`, `shift`. |
| **Writes** | The four `custom_*` Duration fields (seconds). |
| **Gotcha** | A row with no `in_time` (keyed status only) gets all four = 0. A row with only `in_time` gets entry deviations only. Shift Type time changes do **not** re-compute existing rows until they are re-validated or refreshed. |

Stock HRMS has its own `late_entry` / `early_exit` **checkboxes**, set only when the Shift Type's `enable_late_entry_marking` / `enable_early_exit_marking` are on (with grace periods). Both are **off** on avinas1, so those flags are always 0. Our code ignores them — except the HR Dashboard (see §5).

## 3. Which deviations count: `measure_day`

```
measure_day(att, is_holiday=False, ot_eligible=False) -> {late_minutes, early_exit_minutes, ot_hours}
```

| Rule | Code | Why (module docstring of `hr/shift_day.py`, from the Chaitra 2082 attendance cards) |
|---|---|---|
| Only **worked** statuses count: Present, Work From Home, Half Day ([`WORKED_STATUSES`](../../avinashgroup_app/hr/shift_day.py#L39)). Absent / On Leave → all zero. | line 119 | Nothing to measure on a day not worked. |
| **Late minutes** = `custom_late_entry` / 60; **early-exit minutes** = `custom_early_exit` / 60 — only on a **non-holiday, non-Half-Day** row. | lines 124–126 | "A holiday has no start time to be late for, and a half day is already its own penalty." 09:08 on a 9 AM shift is 8 minutes — no grace. |
| Holiday = `is_holiday` argument **or** the row's `custom_worked_on_holiday`. | line 122 | — |
| **OT hours** only when `ot_eligible` is passed True. Working day: (`custom_early_entry` + `custom_late_exit`) / 3600. Holiday: `working_hours`, or in→out punched hours when hours are 0 ([`_punched_hours`](../../avinashgroup_app/hr/shift_day.py#L137)). Rounded by [`round_to_half_hour`](../../avinashgroup_app/hr/shift_day.py#L42) (nearest half hour, halves up: 7:53 → 8, 7:34 → 7.5). | lines 128–133 | "on a working day, the hours before the shift starts and after it ends; on a holiday, every hour worked … Only for staff whose category is overtime-eligible." |

**What `ot_eligible` means depends on the caller.** The reports pass "a submitted Overtime Sheet authorises Overtime for this person on this date" ([`get_overtime_days`](../../avinashgroup_app/hr/overtime.py#L263), policy 5.1) — not the employee's category or the Employee's `custom_ot_eligibility` tick. `evaluate_rule`'s Late Time call passes nothing, so `ot_hours` is always 0 there (it only needs the minutes).

**Dead code**: [`overtime_eligibility`](../../avinashgroup_app/hr/shift_day.py#L47) (eligibility from the Employee's Overtime Eligible tick, `custom_ot_eligibility`) is defined here and called nowhere in the app.

### Late Excused

`custom_late_excused` on the Attendance ([02 §5](02-checkin-to-attendance.md#5-attendance-validate-hrms-first-then-our-four-hooks)) does **not** change `measure_day` — reports keep showing the minutes. It is checked by the consumers: `evaluate_rule` [`"Late Time"`](../../avinashgroup_app/payroll/attendance_allowance.py#L271) returns 0 (no fine) and the half-day hook restores Present. Patch `setup_late_excuse` ([`custom_late_excused`](../../avinashgroup_app/patches/setup_late_excuse.py#L27)): "The lateness stays recorded … but the fine is not charged."

### How day kinds are treated (summary)

| Day | Late / early minutes | OT hours (`measure_day`) | Late Fine | Pay effect of status |
|---|---|---|---|---|
| Working day, Present | counted | early entry + late exit (if authorised) | (late + early) min ÷ 60 h × hourly basic × 1 | full day |
| Working day, in > start + 2 h | — (became Half Day) | early entry + late exit | **0** (no double penalty) | half-absent: −0.5 day |
| Half Day from leave (half-day Leave Application, or working on leave) | 0 | as above | 0 | leave half per leave type |
| Holiday worked (`custom_worked_on_holiday`) | 0 | all hours worked | 0 | holiday paid anyway; OT/meals if authorised |
| Absent / On Leave | 0 | 0 | 0 | per status / leave type |
| Excused | shown in reports | unchanged | **0** | Present if lateness was the only cause |
| No attendance | — | — | — | paid (unmarked = Present), earns no attendance components |

### Late Fine end to end (worked example)

`Late Fine` on avinas1: `custom_condition_type = Late Time`, `custom_unit = Per Hour`, `custom_rate_basis = Hourly Basic × Multiplier`, `custom_rate_multiplier = 1` (other attendance components: Daily Wage, Meal, Overtime 1.5×, Tea & Conveyance). For `NGI-ATT-83/84-00017` (NGI-EMP-00040, 2026-08-04, in 09:40): `custom_late_entry` = 2400 s → `measure_day` 40 late minutes → [`_per_unit`](../../avinashgroup_app/payroll/attendance_allowance.py#L433) Per Hour → 0.667 h → summed over the month by Prepare Payroll Inputs → `qty × (assignment base ÷ BS-month days ÷ 8 × 1)` as a Late Fine Additional Salary. Exempt staff (`custom_late_fine_exempt`) are skipped in [`_skip_for_eligibility`](../../avinashgroup_app/payroll/attendance_allowance.py#L517). Pricing details: [05-payroll-entry.md](05-payroll-entry.md).

### The other time-based conditions (not `measure_day`)

`Early Entry Before`, `Late Stay After`, `Late Arrival After` in `evaluate_rule` ([`"Late Arrival After"`](../../avinashgroup_app/payroll/attendance_allowance.py#L282)) read the raw seconds against `custom_time_offset_hours` directly. `Late Arrival After` skips excused and Half Day rows; **none of the three skips holidays** (unlike `measure_day`). No component on avinas1 uses them. Meals ([`_meals_for_day`](../../avinashgroup_app/payroll/attendance_allowance.py#L304)) also use raw `custom_early_entry` / `custom_late_exit` ≥ 1.5 h on authorised OT days — see [04-overtime.md](04-overtime.md).

---

## 4. Report OT vs paid OT — two measurements

Paid overtime does **not** come from `measure_day`. It comes from the Overtime Sheet row's `worked_hours`, measured by [`measure_row`](../../avinashgroup_app/hr/overtime_settlement.py#L70) with [`hours_outside_shift`](../../avinashgroup_app/hr/overtime.py#L296) (in/out window minus overlap with the shift), rounded to the half hour, and HR may type over it ([04-overtime.md](04-overtime.md)). The comment there says "pay and the report must never disagree", and for an ordinary day (in before start, out after end) the two agree. They can differ when:

| Case | `measure_day` (reports) | `measure_row` (pay) |
|---|---|---|
| In after the shift **ended** (called back in the evening) | counts only `custom_late_exit` | counts the whole window |
| Out before the shift **started** | counts only `custom_early_entry` | counts the whole window |
| Holiday decided differently | report's holiday map / `custom_worked_on_holiday` | Overtime Sheet row's work type |
| Shift on the row ≠ rostered shift | row's own shift (deviation fields) | `get_shift_window` (roster) |
| HR typed the hours on the sheet | not reflected | typed value paid |

So the "O.T." column in Monthly Attendance BS is an indicator; the paid figure is the Overtime Sheet's `worked_hours`. (Edge cases from reading the code; not exercised on data — avinas1 has no checkins.)

---

## 5. Consumers and the attendance reports

| Consumer | Uses | Link |
|---|---|---|
| Late Fine (payroll) | `measure_day` via `evaluate_rule` "Late Time" | [`measure_day(row`](../../avinashgroup_app/payroll/attendance_allowance.py#L278) |
| Salary Slip **Daily Breakdown** | `evaluate_rule` per day to spread attendance components; [`paid_weight`](../../avinashgroup_app/payroll/daily_breakdown.py#L210) for the day's pay fraction | [`evaluate_rule(`](../../avinashgroup_app/payroll/daily_breakdown.py#L170) — see [06-salary-slip.md](06-salary-slip.md) |
| Monthly Attendance BS — Detail | `ShiftRoster`, `measure_day` | below |
| Monthly Attendance BS — Summary | `measure_day` | below |
| Work On Holiday BS | `custom_worked_on_holiday` only | below |
| Yearly Leave Details BS | `custom_worked_on_holiday` only | below |
| HR Dashboard | **HRMS `late_entry` flag**, not our fields | [`sum(late_entry)`](../../avinashgroup_app/hr/hr_dashboard.py#L194) in [`_attendance`](../../avinashgroup_app/hr/hr_dashboard.py#L191) |
| Shift Roster page | `ShiftRoster` | [`ShiftRoster(employees`](../../avinashgroup_app/hr/shift_roster.py#L53) |

**HR Dashboard gotcha**: its "late" count sums HRMS's `late_entry` checkbox, which is never set on avinas1 (late-entry marking off), so it always shows **0 late** while the attendance report shows real late minutes. Monthly Attendance BS had the same bug and was fixed (comment at [`measure_day(att`](../../avinashgroup_app/avinash_group_app/report/monthly_attendance_bs/monthly_attendance_bs.py#L545): "This used to need HRMS's `late_entry` flag, which nothing on this site sets — so Late read 0 for everyone").

### Monthly Attendance BS (Script Report, ref doctype Attendance, total row on)

| | |
|---|---|
| **What** | One report, two views (filter **View**). **Detail**: one row per employee per day of a BS month. **Summary**: one row per employee, mirroring the Nepal Gas paper attendance sheet. The former separate "Monthly Attendance Summary BS" report was merged in (patches `merge_attendance_summary_report`, `remove_merged_attendance_summary_report`; only a stale `__pycache__` folder remains under `report/monthly_attendance_summary_bs/`). |
| **Where** | [`execute`](../../avinashgroup_app/avinash_group_app/report/monthly_attendance_bs/monthly_attendance_bs.py#L59), row builder [`_build_row`](../../avinashgroup_app/avinash_group_app/report/monthly_attendance_bs/monthly_attendance_bs.py#L494); summary [`execute_summary`](../../avinashgroup_app/avinash_group_app/report/monthly_attendance_bs/summary.py#L103), [`_build_summary_row`](../../avinashgroup_app/avinash_group_app/report/monthly_attendance_bs/summary.py#L166), [`measure_day(`](../../avinashgroup_app/avinash_group_app/report/monthly_attendance_bs/summary.py#L204). |
| **Period** | Fiscal Year + BS Month (→ `hr/bs_calendar.py`, Nepal BS Period first), else From/To dates. |
| **Detail columns** | Date (BS), AD date, weekday, employee, **IN / OUT = first and last Employee Checkin of the day** (not `Attendance.in_time/out_time`; hand-keyed rows fall back to the row's times), Hours (`working_hours` as HH:MM), Status (holiday-aware: "Worked on Holiday (…)", "Holiday (…)", "Not Marked"), Shift (`ShiftRoster` for that date), Late (min), Before ofc. Time, O.T. (only on Overtime-Sheet days), Leave, Work In Holiday, **one column per attendance-driven Salary Component** computed with the payroll's own `evaluate_rule`, Remarks, Holidays. |
| **Summary columns** | Code, name, department, Meal, Tea & Conveyance, Tihar, O.T. (hrs), Late Time (min) = late + early, Present Days = Present + WFH + 0.5 × Half Day, Worked on Holiday, Leave current / previous / up-to-month (from Leave Applications). |
| **Why** | Replace the hand-kept monthly attendance cards; columns from the Chaitra 2082 sheet. Reads from the **replica** (`read_from_replica`), so a just-saved row may lag (see [09-cross-cutting.md](09-cross-cutting.md)). |
| **Gotcha** | OUT − IN need not equal Hours (docstring): punches outside the shift window are left out of HRMS's attendance but shown here. |

### Work On Holiday BS (Script Report, ref doctype Attendance)

| | |
|---|---|
| **What** | One row per employee for a BS fiscal year, a count per BS month (Shrawan → Ashad) of Attendance rows with `custom_worked_on_holiday = 1`, plus total; filter OT Eligibility All / Yes / No on Employee `custom_ot_eligibility`. |
| **Where** | [`execute`](../../avinashgroup_app/avinash_group_app/report/work_on_holiday_bs/work_on_holiday_bs.py#L17), [`_count_worked_on_holiday`](../../avinashgroup_app/avinash_group_app/report/work_on_holiday_bs/work_on_holiday_bs.py#L116). |
| **Gotcha** | Counts every row with the flag and `docstatus != 2` — **status is not checked and drafts are included**. `set_holiday_flag` ticks the flag whatever the status, so an **Absent** marked on a holiday counts as a day of holiday work. Compare Monthly Attendance BS, which requires Present / Half Day. |

### Yearly Leave Details BS (Script Report, ref doctype Leave Application)

| | |
|---|---|
| **What** | Per employee per BS fiscal year: approved leave days per BS month, Total Leave Days, Total Yearly Leave (sum of `new_leaves_allocated` of submitted allocations), Total Worked on Holiday, **Leave Remaining = min(allocated, allocated − taken + worked-on-holiday)**. Mirrors the Excel "Yearly Leave Details F/Y 2082/083". |
| **Where** | [`execute`](../../avinashgroup_app/avinash_group_app/report/yearly_leave_details_bs/yearly_leave_details_bs.py#L36), [`_count_worked_on_holiday`](../../avinashgroup_app/avinash_group_app/report/yearly_leave_details_bs/yearly_leave_details_bs.py#L237). |
| **Why** | Comment at [`worked_holiday`](../../avinashgroup_app/avinash_group_app/report/yearly_leave_details_bs/yearly_leave_details_bs.py#L70): only non-OT staff earn leave back for holiday work; OT-eligible staff are paid instead. |
| **Gotchas** | Same status-blind count as Work On Holiday (Absent-on-holiday rows add leave back). OT eligibility here is the Employee tick `custom_ot_eligibility`, the same tick the Overtime Sheet reads to decide Overtime vs Replacement Leave ([`get_holiday_work_rule`](../../avinashgroup_app/hr/overtime.py#L121)) — one source of truth since 2026-10-13. The add-back counts every non-OT-eligible employee, including those with neither tick, as before. The add-back is the report's own arithmetic; whether it double-counts the Compensatory Leave allocation that replacement leave credits ([04-overtime.md](04-overtime.md)) is unverified. |

---

## Change-impact summary

| If you change… | …this moves |
|---|---|
| Shift Type `start_time` / `end_time` | Deviation seconds on newly validated rows → late minutes, Late Fine, meals, report OT; settlement OT for sheets measured afterwards. |
| Shift Assignment / Default Shift for a past date | The row's shift via [shift_backdate](02-checkin-to-attendance.md#7-backdated-shift-changes-re-mark-attendance) rebuild; refused into paid periods. |
| `WORKED_STATUSES` / `measure_day` rules | Late Fine on every future Prepare Payroll Inputs, the Daily Breakdown, both views of Monthly Attendance BS. |
| `round_to_half_hour` | Report OT **and** paid OT (settlement uses the same function). |
| `custom_late_excused` on a row | Late Fine 0 for that day; Half Day → Present if lateness was the only cause. Requires cancel + amend on a submitted row, then re-run Prepare Payroll Inputs. |
| Employee holiday list | Whether minutes count (holidays never charge late) and which hours count as holiday OT. |
