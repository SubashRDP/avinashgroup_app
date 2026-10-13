# 05 · Payroll Entry and payroll inputs

A month's payroll is one **Payroll Entry** per company and BS month. HR picks the month and saves; the entry fills its dates, accounts and employee list. HR then presses **Prepare Payroll Inputs**, which turns the month's attendance into tea, meal, overtime and late-fine **Additional Salary** rows and posts advance instalments. **Submit** then creates one Salary Slip per employee (stage [06](06-salary-slip.md)). Submitting slips, the journal and the bank entry are stage [07](07-after-the-slip.md).

```
 HR picks Fiscal Year + BS month on the calendar (payroll_entry.js)
        │ save
        ▼
 AvinashPayrollEntry.validate ─► fill_from_bs_month  (dates, posting = month end, payable a/c, cost centre, employees)
                              ─► HRMS validate        (count, status)
                              ─► warn_missing_attendance (orange message only)
 doc_event validate          ─► bs_period_guard.validate_payroll_entry (start/end must be the posting date's BS month)
                              ─► bs_dates.set_bs_dates (miti fields)   ─► "*" hooks (numbering, approval, SMS)
        │ button "Nepal HRMS → Prepare Payroll Inputs"  (draft or submitted entry)
        ▼
 trigger_for_payroll_entry ─► create_additional_salaries  (attendance engine → submitted Additional Salary, tag "Nepal HRMS Attendance Allowance")
                           ─► post_recoveries             (Employee Advance instalments → "Salary Advance" deductions, tag "Advance Recovery")
                           ─► refresh_draft_slips         (re-save the entry's draft slips)
        │ submit
        ▼
 AvinashPayrollEntry.before_submit ─► warn_missing_attendance ─► HRMS before_submit (duplicates, payable account type, unmarked attendance if Validate Attendance)
 HRMS on_submit ─► create_salary_slips ─► create_salary_slips_for_employees (queued above 30 employees)  ─► stage 06
```

**HRMS vs us.** HRMS owns the Payroll Entry doctype, slip creation, the accrual journal and the bank entry. We add the following:

* a **class override**, `AvinashPayrollEntry`, registered at [`AvinashPayrollEntry`](../../avinashgroup_app/hooks.py#L506);
* the **BS month** fields and calendar;
* one **doc_event** guard;
* the whole **attendance engine**. HRMS has no attendance-driven pay at all, only proration by payment days (stage [06](06-salary-slip.md)).

---

## 5.1 Choosing the month: `payroll/payroll_month.py` and `public/js/payroll_entry.js`

| | |
|---|---|
| **What** | The entry is made by choosing **Fiscal Year + Month (BS)**. Everything else (start, end, posting date, frequency, currency, payable account, cost centre, employees) is derived from them. |
| **Why** | Module docstring ([`Payroll Entry`](../../avinashgroup_app/payroll/payroll_month.py#L1)): "HR runs 'Bhadra's salary', not '17 August to 16 September'". Typing an AD posting date was the root of the Bhadra-paid-on-2-Ashwin mistake that `bs_period_guard` refuses. Commits df53710 and 714edfc (2026-10-09). |
| **Where** | [`fill_from_bs_month`](../../avinashgroup_app/payroll/payroll_month.py#L45), [`default_month`](../../avinashgroup_app/payroll/payroll_month.py#L121), [`month_calendar`](../../avinashgroup_app/payroll/payroll_month.py#L148); BS calendar [`month_period`](../../avinashgroup_app/hr/bs_calendar.py#L88), [`month_of_date`](../../avinashgroup_app/hr/bs_calendar.py#L127), [`get_month`](../../avinashgroup_app/hr/bs_calendar.py#L148) |
| **Triggered by** | `fill_from_bs_month` runs from [`validate`](../../avinashgroup_app/payroll/payroll_entry.py#L42) (drafts only). `default_month` runs from the form's `onload` on a new entry. `month_calendar` runs whenever the form draws the calendar. |
| **Reads** | Company `default_currency`, `default_payroll_payable_account`, `cost_center`; Nepal BS Period / Nepal BS Period Month (company first, then global), falling back to the Nepali calendar (`get_bs_month_range`); existing Payroll Entries. |
| **Writes** | Payroll Entry `start_date`, `end_date`, `posting_date` (= month end), `payroll_frequency` = Monthly, `currency`, `exchange_rate` = 1, `payroll_payable_account` and `cost_center` (only when blank), `employees` (HRMS `fill_employee_details`, when empty or when the month changed). |
| **Impacts downstream** | `posting_date` decides the slip's month (the BS slip derives its period from posting date, [06](06-salary-slip.md)); `start_date`/`end_date` bound the attendance engine and the Additional Salary `payroll_date`; the payable account is credited by the accrual journal ([07](07-after-the-slip.md)). |
| **Config on avinas1** (2026-10-12) | Nepal BS Period: **0 records**, so every month comes from the Nepali calendar. Payroll payable account: `347301 - Salary Payable - <abbr>` for NGI, NGG, NGK and NGN; **blank for GLMI, GEPL and SGU**, so `fill_from_bs_month` throws "Set Default Payroll Payable Account on Company…" for those three. |

### Fields added to Payroll Entry

| Field | Added by | Purpose |
|---|---|---|
| `custom_month_calendar` (HTML) | patch `setup_payroll_entry_bs_month` ([`custom_month_calendar`](../../avinashgroup_app/patches/setup_payroll_entry_bs_month.py#L18)) | The clickable month grid. |
| `custom_fiscal_year` (Link Fiscal Year) | same ([`custom_fiscal_year`](../../avinashgroup_app/patches/setup_payroll_entry_bs_month.py#L24)) | e.g. `83/84`; hidden on the form and set by the calendar; in list view and filters. |
| `custom_bs_month` (Select "04 - Shrawan" … "03 - Ashadh") | same ([`custom_bs_month`](../../avinashgroup_app/patches/setup_payroll_entry_bs_month.py#L34)) | The month being paid. The options are fiscal-ordered [`MONTH_OPTIONS`](../../avinashgroup_app/hr/bs_calendar.py#L42). |
| `custom_start_miti`, `custom_end_miti`, `custom_posting_miti` | `setup_hr_bs_dates`; filled by `hr/bs_dates.set_bs_dates` and by the form | BS dates for display ([09-cross-cutting.md](09-cross-cutting.md)). |

The patch also back-filled `custom_fiscal_year` / `custom_bs_month` on existing entries from their start date.

### `default_month`

[`default_month`](../../avinashgroup_app/payroll/payroll_month.py#L121) returns the month after the company's last non-cancelled Payroll Entry, but never later than the month now running. If the company has no payroll yet, it returns the last finished month ([`last_closed_month`](../../avinashgroup_app/hr/bs_calendar.py#L140)). Why: "the last finished month alone … opened a new entry on Bhadra after Bhadra had been paid" (October 2026 audit, commit 705e671; test [`test_month_after_the_last_payroll`](../../avinashgroup_app/payroll/test_payroll_checks.py#L39)).

### The form script (ours)

Registered at [`payroll_entry.js`](../../avinashgroup_app/hooks.py#L107).

| Function / handler | What |
|---|---|
| [`draw_month_calendar`](../../avinashgroup_app/public/js/payroll_entry.js#L90) / [`render_month_calendar`](../../avinashgroup_app/public/js/payroll_entry.js#L109) | Twelve tiles in fiscal order, with badges Paid / Draft / Running. Future months are locked. Picking a month that already has an entry asks for confirmation ("Make another one for it?"). |
| [`show_bs_month`](../../avinashgroup_app/public/js/payroll_entry.js#L16) | Calls `bs_calendar.get_month` and writes start, end, posting date and the mitis **directly on `frm.doc`**, "so HRMS's own start/end/posting handlers would [not] recompute the dates from the AD calendar". |
| [`lock_bs_dates`](../../avinashgroup_app/public/js/payroll_entry.js#L11) | Makes `posting_date`, `start_date`, `end_date` and `payroll_frequency` read-only once a month is picked. |
| [`fill_company_defaults`](../../avinashgroup_app/public/js/payroll_entry.js#L50) | Fills a blank payable account, cost centre and currency on the client. HRMS only does this when the company is *changed*, and the form would otherwise refuse Save before the server could fill them. |
| [`Prepare Payroll Inputs`](../../avinashgroup_app/public/js/payroll_entry.js#L248) | The button, in group **Nepal HRMS**, on any non-cancelled entry. It shows a confirm, then calls `trigger_for_payroll_entry` (5.5) and shows "{n} allowance and fine records, {m} advance instalments. {k} draft salary slips updated." |

### Coexisting script from rdp_common_app

rdp_common_app also registers a Payroll Entry form script ([`payroll_entry.js`](../../../rdp_common_app/rdp_common_app/hooks.py#L58)). Its [`set_bs_dates`](../../../rdp_common_app/rdp_common_app/public/js/payroll_entry.js#L6) sets start and end from `get_bs_period_for_date(posting_date)` 300–600 ms after `posting_date`, `payroll_frequency` or `company` changes. Frappe loads both scripts and both sets of handlers fire. In practice ours wins:

* posting date and frequency are locked once a month is picked, so rdp's two triggers cannot fire from the UI;
* on a `company` change both run, and both resolve to the same BS month;
* the server recomputes every date in `fill_from_bs_month` on save in any case.

rdp's script only matters on an entry with no Fiscal Year / BS month, i.e. an old-style entry.

---

## 5.2 The class override: `AvinashPayrollEntry` (payroll/payroll_entry.py)

[`AvinashPayrollEntry`](../../avinashgroup_app/payroll/payroll_entry.py#L41) subclasses HRMS [`PayrollEntry`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L35).

| Method | Ours / HRMS | What |
|---|---|---|
| [`validate`](../../avinashgroup_app/payroll/payroll_entry.py#L42) | ours, then `super()` | `fill_from_bs_month` → HRMS [`validate`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L45) (sets `number_of_employees`, status) → `warn_missing_attendance` on a new entry or a changed `start_date`. |
| [`before_submit`](../../avinashgroup_app/payroll/payroll_entry.py#L49) | ours, then `super()` | `warn_missing_attendance` again, then HRMS [`before_submit`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L58): [`validate_existing_salary_slips`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L68) (refuses if a slip already exists for an employee for the same dates), [`validate_payroll_payable_account`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L99) (the payable account must have **no** account type; patch `clear_payroll_payable_account_type` blanked it), and the unmarked-attendance refusal, which applies only when **Validate Attendance** is ticked ([`get_employees_with_unmarked_attendance`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L1109)). |
| HRMS [`on_submit`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L64) | HRMS | Status Submitted, then `create_salary_slips` (5.8). |
| [`make_bank_entry`](../../avinashgroup_app/payroll/payroll_entry.py#L55) | ours, then `super()` | Refuses a missing or non-Bank/Cash Payment Account. See [07](07-after-the-slip.md). |
| [`get_salary_component_total`](../../avinashgroup_app/payroll/payroll_entry.py#L76), [`section_for`](../../avinashgroup_app/payroll/payroll_entry.py#L124), [`get_account`](../../avinashgroup_app/payroll/payroll_entry.py#L133) | ours, replacing HRMS | Section accounts (O/O, S/D, F/P) on the accrual journal. See [07](07-after-the-slip.md). |

**Config on avinas1:** `validate_attendance` is 0 on all three entries, so HRMS never refuses for unmarked attendance. Our orange warning is the only signal.

### `warn_missing_attendance`

[`warn_missing_attendance`](../../avinashgroup_app/payroll/payroll_month.py#L77)

* **What:** "{n} of {m} employees have no submitted attendance between … Their unmarked days count as **Present**, and they get no tea, meal, overtime or late fine." It is a warning and blocks nothing.
* **Why:** both Bhadra 2083 payrolls (NGI-PAYR-83/84-00002 with 87 employees, NGN-PAYR-83/84-00001 with 63) ran with no attendance and paid everyone in full with no attendance pay, and nothing said so (docstring; commit 705e671; test [`test_warns_with_the_count`](../../avinashgroup_app/payroll/test_payroll_checks.py#L90)).
* **When:** only when Payroll Settings `payroll_based_on` = Attendance, which it is on avinas1.
* **Gotcha:** it checks for *any* attendance in the month per employee, not for complete attendance. One marked day silences it.

---

## 5.3 The BS period guard (Payroll Entry side)

[`validate_payroll_entry`](../../avinashgroup_app/payroll/bs_period_guard.py#L45), hooked at [`validate_payroll_entry`](../../avinashgroup_app/hooks.py#L369).

| | |
|---|---|
| **What** | Refuses an entry whose start and end are not exactly the BS month of its **posting date** ([`period_for`](../../avinashgroup_app/payroll/bs_period_guard.py#L35) → `month_of_date`). |
| **Why** | Module docstring ([`BS month`](../../avinashgroup_app/payroll/bs_period_guard.py#L1)): `BSSalarySlip.get_date_details` always recomputes a slip's dates from its posting date. "Pay Bhadra's salary on 2 Ashwin … and every slip silently becomes an Ashwin slip." Commit 24b12af (2026-09-24). |
| **Active when** | Nepal HRMS Settings `process_payroll_in_nepali_month` = 1 ([`is_bs_payroll_enabled`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/doctype/nepal_hrms_settings/nepal_hrms_settings.py#L31)). On avinas1 it is 1, and `restrict_to_nepal_companies` is 1. |
| **Runs after** | the class `validate`, so `fill_from_bs_month` has already set posting = month end. With the calendar the guard can therefore only fire on an entry without a BS month, or on one where the month borders disagree. |
| **Slip side** | `validate_salary_slip` (same file) refuses a slip whose start differs from its entry's. See [06](06-salary-slip.md). |
| **Gotcha** | `fill_from_bs_month` uses `month_period` (looked up **by month**), while the guard uses `month_of_date` (looked up **by date**). If a Nepal BS Period record has a moved border, the two can disagree and the guard refuses the entry the calendar just filled. With 0 BS Period records on avinas1 this cannot happen today (unverified edge). |

---

## 5.4 What the payroll guards cover (October 2026 audit)

[`guards added after`](../../avinashgroup_app/payroll/test_payroll_checks.py#L1) lists them. Tests run against avinas1's own data.

| Guard | Code | Test |
|---|---|---|
| Sheet import matches by name; the code is only a cross-check | `payroll/onboarding.EmployeeMatcher` ([08](08-changes-over-time.md)) | [`test_code_is_taken_only_with_the_name`](../../avinashgroup_app/payroll/test_payroll_checks.py#L24) |
| New entry opens on the month after the last payroll | `default_month` (5.1) | [`test_month_after_the_last_payroll`](../../avinashgroup_app/payroll/test_payroll_checks.py#L39), [`test_never_past_the_running_month`](../../avinashgroup_app/payroll/test_payroll_checks.py#L52) |
| Bank entry refuses an unsaved or non-bank Payment Account | `make_bank_entry` | [`test_no_payment_account`](../../avinashgroup_app/payroll/test_payroll_checks.py#L73), [`test_not_a_bank_account`](../../avinashgroup_app/payroll/test_payroll_checks.py#L79) |
| A month without attendance is announced | `warn_missing_attendance` | [`test_warns_with_the_count`](../../avinashgroup_app/payroll/test_payroll_checks.py#L90) |
| Salary sheet names an account set for two sections | Avinas Salary Statement report ([07](07-after-the-slip.md)) | [`test_account_in_two_sections_is_named`](../../avinashgroup_app/payroll/test_payroll_checks.py#L109) |

Other guards on the way to slips: the BS period guard (5.3); HRMS's duplicate-slip check and payable-account check (5.2); and the "Set Payroll Section on the Department" refusal when the journal is made ([07](07-after-the-slip.md)).

---

## 5.5 Prepare Payroll Inputs: `trigger_for_payroll_entry`

[`trigger_for_payroll_entry`](../../avinashgroup_app/payroll/attendance_allowance.py#L62) (whitelisted)

| Step | Function | Notes |
|---|---|---|
| 0 | refuse a cancelled entry | Works on a **draft** entry (once saved, so its `employees` exist) and on a **submitted** one. |
| 1 | [`create_additional_salaries`](../../avinashgroup_app/payroll/attendance_allowance.py#L109) | The attendance engine (5.6). Each employee × component pair is in its own savepoint. It **commits** at the end. |
| 2 | [`post_recoveries`](../../avinashgroup_app/payroll/advance_recovery.py#L61) | Advance instalments (5.7). There is **no savepoint per advance**: one failure raises, and the allowances from step 1 are already committed. |
| 3 | [`refresh_draft_slips`](../../avinashgroup_app/payroll/attendance_allowance.py#L92) | Re-saves every **draft** slip of this entry (`ignore_permissions`) so it pulls the new Additional Salary. Submitted slips are never touched. |
| 4 | `frappe.db.commit()` and return the counts | |

**Why one button:** the comment says "one button prepares everything the slips will read". The refresh exists because HRMS makes the slips at submit, and a press after that would otherwise reach a slip only on its next save ([`refresh_draft_slips`](../../avinashgroup_app/payroll/attendance_allowance.py#L92) docstring).

**When to press:** the user guide says before *Create Salary Slips* (submit), and again before submitting the slips if anything changed ([user guide 5.3](../user-guide/05-monthly-payroll.md)). Pressing after the slips are **submitted**: `_delete_existing_draft` tries to cancel Additional Salary that a submitted slip references. That is likely refused by Frappe's link check, so the record is *skipped* with an Error Log (unverified; not reproduced).

---

## 5.6 The attendance engine: `payroll/attendance_allowance.py`

The module docstring ([`Calculator`](../../avinashgroup_app/payroll/attendance_allowance.py#L1)) states the five steps. Below they are followed one function at a time.

### Which components

[`get_attendance_driven_components`](../../avinashgroup_app/payroll/attendance_allowance.py#L541): every Salary Component with `custom_is_attendance_driven` = 1 and `disabled` = 0.

Config on avinas1 (2026-10-12):

| Component | Type | Allowance? (`custom_is_allowance` / kind) | Condition | Unit | Rate basis | Mult. | Days/Month | Hrs/Day | Pay on holiday | Half day counts | Offset h | Max/day | OT-eligible only |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tea & Conveyance | Earning | 1 / Per Day Present | Status = Present | Per Day | Fixed Rate | – | – | – | **Do Not Pay** | Full Day | 0 | 0 | 0 |
| Meal | Earning | 1 / Per Meal | Meal Entitlement | Per Day* | Fixed Rate | – | – | – | Pay | Full Day | **1.5** | **2** | **1** |
| Overtime | Earning | 1 / Per Overtime Hour | Authorised Overtime | Per Hour | **Hourly Basic × Multiplier** | **1.5** | blank → BS month days | 8 | Pay | Full Day | 0 | 0 | **1** |
| Late Fine | Deduction | 0 | Late Time | Per Hour | **Hourly Basic × Multiplier** | **1** | blank → BS month days | blank → 8 | Pay | Full Day | 0 | 0 | 0 |
| Daily Wage | Earning | 0 | Status = Present | Per Day | Fixed Rate | – | – | – | Pay | Half Day | – | – | 0 — **disabled** |

\* Meal's unit is not used: `_meals_for_day` returns a meal count directly. All attendance-month settings are "Same as Salary". All have `depends_on_payment_days` = 0, which `validate_salary_component` forces ([01b-pay-masters.md](01b-pay-masters.md)).

**Daily Wage: doc vs code.** Patch `setup_daily_wage` ([`Daily-wage labour`](../../avinashgroup_app/patches/setup_daily_wage.py#L1)) says the day's wage is the assignment base on a structure flagged Daily Wage, and that "Overtime reads the flag and divides by 8 instead of 30 * 8". It also adds a `Daily Wage` option to Rate Basis. The code no longer does either: [`_hourly_basic`](../../avinashgroup_app/payroll/attendance_allowance.py#L413) says "Daily-wage labour is paid in cash day to day, outside payroll (decided 2026-10-08), so every assignment's base here is a monthly basic". `_resolve_rate` knows only `Hourly Basic × Multiplier`, and the component is disabled (commit fb3b934). The `custom_daily_wage` checkbox on Salary Structure and the `Daily Wage` rate-basis option remain as leftovers.

### Per employee × component

For each employee in the entry's `employees` table (falling back to [`_employees_in_payroll_entry`](../../avinashgroup_app/payroll/attendance_allowance.py#L613)):

| # | Function | Rule |
|---|---|---|
| a | [`get_employee_allowance_rows`](../../avinashgroup_app/payroll/allowance.py#L236) | `{allowance: row}` from the **Assignment Allowance** rows of the assignment in force on the period's **end date**. Rows with a later `effective_from` are left out. |
| b | [`_gets`](../../avinashgroup_app/payroll/attendance_allowance.py#L581) | An **allowance** (`custom_is_allowance`) is paid only if the person has a row for it on their assignment: no row, not paid, even when the rate is computed (Overtime). A **non-allowance** (Late Fine) is paid only when the person's Salary **Structure** lists it in Earnings or Deductions ([`structure_components`](../../avinashgroup_app/payroll/allowance.py#L258)). The structure row's amount and formula are blanked by `validate_salary_structure`, so the row works purely as a tag. |
| c | [`_skip_for_eligibility`](../../avinashgroup_app/payroll/attendance_allowance.py#L517) | Skip if the component is `custom_ot_eligible_only` and Employee `custom_ot_eligibility` = 0 (policy 2.2). Skip Late Time / Late Arrival components if Employee `custom_late_fine_exempt` (NGI's sheet types 0 for its managers). |
| d | [`_attendance_period`](../../avinashgroup_app/payroll/attendance_allowance.py#L530) | The entry's own dates, or the previous BS month when the component's `custom_attendance_month` = "Previous Month". |
| e | [`_resolve_rate`](../../avinashgroup_app/payroll/attendance_allowance.py#L593) | `Hourly Basic × Multiplier` gives `_hourly_basic × custom_rate_multiplier`, unrounded. Otherwise the **Rate on the person's assignment row**. If neither applies, the result is `None` and the component is skipped. |
| f | [`_hourly_basic`](../../avinashgroup_app/payroll/attendance_allowance.py#L413) | `assignment.base ÷ days ÷ hours`. Days = `custom_rate_days_per_month` if set, otherwise the **actual length of the attendance period** (29–32, `date_diff + 1`). Hours = `custom_rate_hours_per_day`, otherwise [`RATE_HOURS_PER_DAY`](../../avinashgroup_app/payroll/attendance_allowance.py#L400) (8). `base` comes from [`_assignment`](../../avinashgroup_app/payroll/attendance_allowance.py#L403): the latest submitted assignment with `from_date` ≤ the period end. |
| g | [`_qty_for_employee`](../../avinashgroup_app/payroll/attendance_allowance.py#L205) | Sums `evaluate_rule` over the period's **submitted** Attendance ([`_attendance_rows`](../../avinashgroup_app/payroll/attendance_allowance.py#L550)). `Flat per Period` gives 1 if any day matched. |
| h | `amount = flt(qty × rate, 2)` | Skipped when ≤ 0. |
| i | [`_delete_existing_draft`](../../avinashgroup_app/payroll/attendance_allowance.py#L621) | Cancels and deletes this calculator's earlier row for the same employee, component and `payroll_date` (tag `custom_source` = "Nepal HRMS Attendance Allowance"). Hand-made rows (other tags) are left alone. |
| j | [`_make_additional_salary`](../../avinashgroup_app/payroll/attendance_allowance.py#L649) | Inserts and **submits** an Additional Salary (5.6.2). |

Errors in steps i–j roll back to a savepoint whose name is made SQL-safe ([`_savepoint_name`](../../avinashgroup_app/payroll/attendance_allowance.py#L575); "Tea & Conveyance" once broke MariaDB, commit 886d643). The record is listed as *skipped*, with an Error Log titled "Nepal HRMS Attendance Allowance: {employee}/{component}".

### 5.6.1 `evaluate_rule`: one day's quantity

[`evaluate_rule`](../../avinashgroup_app/payroll/attendance_allowance.py#L223). "Present statuses" are the Attendance `status` options minus Absent, On Leave and Half Day ([`get_present_statuses`](../../avinashgroup_app/payroll/attendance_allowance.py#L39)), i.e. Present and Work From Home.

| Condition (`custom_condition_type`) | Day counts when | Quantity | Used by |
|---|---|---|---|
| *(holiday gate)* `Status = Present` / `Status = Half Day` | `custom_worked_on_holiday` = 1 and `custom_pay_on_holiday` = "Do Not Pay" | 0 | Tea & Conveyance: no tea on a holiday worked. |
| `Status = Present` | present status | 1 day (or `working_hours` if Per Hour) | Tea & Conveyance |
| | `Half Day` | `custom_half_day_counts`: Full Day → 1 (client policy 2026-09-21: "someone who comes gets the day"), Half Day → 0.5, Not At All → 0 | |
| `Status = Half Day` | status Half Day | 1 | none on avinas1 |
| `Worked on Holiday` | holiday flag and present or Half Day | 1 day / hours | none on avinas1 (Overtime used this before 2026-09-21) |
| `Meal Entitlement` | [`_meals_for_day`](../../avinashgroup_app/payroll/attendance_allowance.py#L304) | see [04 §4.6](04-overtime.md#46-how-the-sheet-reaches-payroll): OT eligible **and** on a submitted Overtime Sheet with Overtime entitlement that day; holiday = 2; working day = 1 per early or late ≥ offset; capped at max/day | Meal |
| `Authorised Overtime` | [`_authorised_overtime_hours`](../../avinashgroup_app/payroll/attendance_allowance.py#L371) | Σ `worked_hours` of submitted Overtime-entitlement rows for that date (already rounded to ½ h) | Overtime |
| `Late Time` | not `custom_late_excused`; [`measure_day`](../../avinashgroup_app/hr/shift_day.py#L112) | (late minutes + early-exit minutes) ÷ 60 hours. Counted only on a **full working day**: no holidays, no Half Day ([03](03-shift-measurement.md)) | Late Fine |
| `Early Entry Before` / `Late Stay After` / `Late Arrival After` | seconds from `custom_early_entry` / `custom_late_exit` / `custom_late_entry` ≥ the offset; Late Arrival is skipped if excused or Half Day (policy 1.2: no double charge) | day / hours | none on avinas1 |

Reads Attendance `status`, `working_hours`, `custom_worked_on_holiday`, `custom_late_entry`, `custom_early_entry`, `custom_early_exit`, `custom_late_exit`, `custom_late_excused`, `in_time` and `out_time`. All of these are written by the Attendance hooks in [02](02-checkin-to-attendance.md).

### 5.6.2 The Additional Salary it writes

| Field | Value | Why |
|---|---|---|
| `salary_component`, `type` | the component; type taken from it | |
| `amount` | qty × rate, 2 dp | |
| `payroll_date` | the entry's **end date** | Inside the slip's period, so HRMS [`get_additional_salaries`](../../../hrms/hrms/payroll/doctype/additional_salary/additional_salary.py#L218) picks it up ([06](06-salary-slip.md)). |
| `is_recurring` 0, `overwrite_salary_structure_amount` 0 | | |
| `deduct_full_tax_on_selected_payroll_date` | 1 for earnings, 0 for deductions | "a labourer's 7,068.75 month drew 6 of tax instead of the sheet's 1%, 70.69" (commit 913bde9). The one-off is taxed in the month it is paid. |
| `custom_source` | "Nepal HRMS Attendance Allowance" ([`SOURCE_TAG`](../../avinashgroup_app/payroll/attendance_allowance.py#L32)) | Identifies the calculator's own rows for replace-on-rerun. Field created by patch `setup_attendance_allowance` ([`custom_source`](../../avinashgroup_app/patches/setup_attendance_allowance.py#L150)). |
| `custom_quantity`, `custom_rate` | qty and rate | Read by the **Avinas Salary Statement** (OT hours, meals, late hours). Patch `setup_additional_salary_quantity` ([`custom_quantity`](../../avinashgroup_app/patches/setup_additional_salary_quantity.py#L24)) back-filled the old rows. |
| docstatus | **1 (submitted)** | "a draft Additional Salary is invisible to the salary slip, so the first full payroll run produced slips with no tea on them at all". |

HRMS checks on insert: [`validate_salary_structure`](../../../hrms/hrms/payroll/doctype/additional_salary/additional_salary.py#L38) refuses an employee without any Salary Structure Assignment. That refusal is caught and becomes a skipped row.

### 5.6.3 Gotchas in the engine

* **Stale rows on a re-press — Fixed 2026-10-12..** The last press's row is now deleted first for every employee and component ([`_delete_existing_draft`](../../avinashgroup_app/payroll/attendance_allowance.py#L621)), and only then is a new one made if anything is due ([`_priced`](../../avinashgroup_app/payroll/attendance_allowance.py#L191)). Removed rows come back as `cleared` and the button says "… earlier records removed". A month whose slips are submitted still cannot change: its rows are reported as skipped (LinkExistsError).
* **Only the entry's employee table is processed.** Someone removed from the entry keeps any rows posted earlier.
* **The assignment for allowance rows is the one in force on the end date.** The `base` for OT comes from `_assignment`, the latest submitted assignment with `from_date` ≤ end. A mid-month raise prices the whole month's OT at the new base, while the slip prorates nothing for it (Salary Revision handles arrears, [08](08-changes-over-time.md)).
* Late Fine depends on the person's **structure** listing it. A structure without a Late Fine row means no fine, for everyone on that structure.
* The rates stored before 2026-10-12 used ÷ 30 (see the worked example). Rows are recomputed only when the button is pressed again.

### Worked example: NGI-EMP-00040, Shrawan 2083

Ramhari Koirala, entry `NGI-PAYR-83/84-00001` (2026-07-17 → 2026-08-16, **31** days). Assignment `HR-SSA-26-10-00036`: base **19,838.18**, Initial Basic 17,165.50. Allowance rows: Tea & Conveyance 235, Meal 75, Overtime 0 (computed), plus fixed allowances.

| Component | Qty (from) | Rate stored (2026-10-09) | Amount stored | Rate **if pressed today** (BS-month days) | Amount today |
|---|---|---|---|---|---|
| Tea & Conveyance | 25 days present (holidays excluded) | 235 (assignment row) | 5,875.00 | 235 | 5,875.00 |
| Meal | 4 (2 on the Saturday sheet, 2 on 07-21) | 75 | 300.00 | 75 | 300.00 |
| Overtime | 12 h (3.5 + 8.5 from the sheets) | 123.988333 = 19,838.18 ÷ **30** ÷ 8 × 1.5 | 1,487.86 | 119.989 = 19,838.18 ÷ **31** ÷ 8 × 1.5 | 1,439.87 |
| Late Fine | 0.6667 h = 40 min | 82.665 | −55.11 | 79.993 = 19,838.18 ÷ 31 ÷ 8 | −53.33 |

These rows were posted on 2026-10-09, before commit c82193b ("hourly wage on the BS month's actual days, not 30", 2026-10-12) and patch `rate_on_actual_month_days`. The Shrawan slip `NGI-SAL-83/84-00004` is **submitted**, so these amounts stand. The stored late-fine rate 82.665 does not equal 19,838.18 ÷ 240 = 82.659: it implies a base of about 19,839.60 at the time (unverified; the assignment may have been edited since). Bhadra (NGI-PAYR-83/84-00002, NGN-PAYR-83/84-00001) has **no** attendance-driven Additional Salary at all: no inputs were prepared and there was no attendance.

Totals on avinas1 (2026-10-12): 10 Additional Salary rows, all from this calculator, all for Shrawan 2083 (4 Tea & Conveyance totalling 14,025; 2 Meal, 375; 2 Overtime, 1,644.49; 2 Late Fine, 139.17); 0 Advance Recovery rows; 0 Employee Advances.

---

## 5.7 Advance recovery: `payroll/advance_recovery.py`

| | |
|---|---|
| **What** | For each open **Employee Advance** of the entry's employees, posts a submitted `Salary Advance` **deduction** of min(instalment, outstanding) dated at the month end, linked to the advance (`ref_doctype`/`ref_docname`). |
| **Why** | Module docstring ([`Advances recovered`](../../avinashgroup_app/payroll/advance_recovery.py#L1)): typed month by month on the sheet, "a forgotten month is simply lost". HRMS keeps the balance ([`update_return_amount_in_employee_advance`](../../../hrms/hrms/payroll/doctype/additional_salary/additional_salary.py#L183) adds to `return_amount` on submit and takes it back on cancel) but has no instalment. Patch `setup_advance_recovery`; commit dca27f4. |
| **Where** | [`post_recoveries`](../../avinashgroup_app/payroll/advance_recovery.py#L61), [`open_advances`](../../avinashgroup_app/payroll/advance_recovery.py#L33), [`outstanding`](../../avinashgroup_app/payroll/advance_recovery.py#L28), [`clear_month`](../../avinashgroup_app/payroll/advance_recovery.py#L117) |
| **Triggered by** | Prepare Payroll Inputs (5.5). |
| **Reads** | Employee Advance where `docstatus` = 1, `repay_unclaimed_amount_from_salary` = 1, `paid_amount` > 0, status not Claimed/Returned/Cancelled; fields `custom_monthly_instalment` and `custom_recover_from`; oldest first. |
| **Writes** | Additional Salary (`Salary Advance`, Deduction, `custom_source` = "Advance Recovery", note "Instalment on … of … outstanding"); through HRMS, Employee Advance `return_amount` and status. |
| **Re-run** | [`clear_month`](../../avinashgroup_app/payroll/advance_recovery.py#L117) first **cancels** this month's earlier recoveries (which hands the amounts back to the balance), then re-reads `return_amount` and posts again. Cancelled rows are not deleted. |
| **Impacts downstream** | The deduction on the slip. On the accrual journal, HRMS posts advance deductions against the advance account, not the component account (`get_advance_deduction`; [07](07-after-the-slip.md)). |
| **Config on avinas1** | Employee Advance count **0**. The `repay_unclaimed_amount_from_salary` default is set to 1 by a property setter. |

Employee Advance custom fields (patch [`custom_monthly_instalment`](../../avinashgroup_app/patches/setup_advance_recovery.py#L25)):

| Field | Meaning |
|---|---|
| `custom_monthly_instalment` | Taken each month until nothing is outstanding. **Blank takes the whole balance in one month.** |
| `custom_recover_from` | A date in the first BS month to deduct in; blank starts with the next run. Compared with the entry's end date. |

**Gotcha:** `clear_month` only cancels submitted recoveries for the employees currently in the entry. Unlike the allowance engine, there is no per-row savepoint, so a single failure (for example an employee without an assignment) aborts the rest of the button after the allowances have already been committed.

---

## 5.8 Slip creation (HRMS)

| Step | Function | Notes |
|---|---|---|
| 1 | [`create_salary_slips`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L218) | Builds args: dates, **posting_date**, `payroll_entry`, currency, exchange rate. **More than 30 employees is enqueued** (status "Queued"); otherwise it runs inline. |
| 2 | [`create_salary_slips_for_employees`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L1447) | Skips employees who already have a non-cancelled slip for this entry and dates ([`get_existing_salary_slips`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L1511)). Inserts one Salary Slip each, which runs stages 6–8. On any exception it rolls back **everything** and logs to the entry's `error_message` ([`log_payroll_failure`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L1426)). |
| 3 | Salary Slip insert | `BSSalarySlip` recomputes start and end from `posting_date`, pulls the structure, prorates, then adds Additional Salary via [`add_additional_salary_components`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1329). Then our validate hooks. See [06-salary-slip.md](06-salary-slip.md). |

Employee list: HRMS [`fill_employee_details`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L179) fetches the employees of submitted Salary Structures matching company, currency and frequency ([`get_employee_list`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L1587)), filtered by the optional branch / department / designation, minus employees already payrolled for these dates (`remove_payrolled_employees`). `fill_from_bs_month` calls it when the list is empty or the month changed.

**Gotcha (all-or-nothing):** one failing slip, e.g. an employee whose Department has no Payroll Section when the slip's journal is made later, or a throw in a validate hook, rolls back the creation of every slip in the batch. The reason is in the entry's *Error Message* field, not in a popup.

---

## 5.9 Monthly checklist (developer view)

| Before | Check | Where it bites |
|---|---|---|
| Save | Company has a Default Payroll Payable Account with no account type | `fill_from_bs_month`, HRMS `validate_payroll_payable_account` |
| Prepare inputs | Attendance submitted for the month (the warning) | otherwise unmarked days count as Present, and no tea, OT or fine |
| Prepare inputs | Overtime Sheets submitted and measured ([04](04-overtime.md)) | Overtime and Meal |
| Prepare inputs | Each person's assignment has the allowance rows (Tea, Meal, Overtime) | `_gets` |
| Prepare inputs | Structure lists Late Fine; Employee Late Fine Exempt as intended | `_gets`, `_skip_for_eligibility` |
| Submit | No existing slips for the dates | HRMS `validate_existing_salary_slips` |
| After a correction | Press Prepare Payroll Inputs again; it removes what is no longer due | stale-row fix (5.6.3) |

See [impact-matrix.md](impact-matrix.md) for every field above and what moves when it changes, and [hooks-inventory.md](hooks-inventory.md) for the hook order.
