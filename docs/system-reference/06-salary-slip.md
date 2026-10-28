# 06 · Salary Slip

How one Salary Slip is calculated, from the moment a Payroll Entry inserts it (or HR re-saves a draft) to the final `net_pay`. Three apps take part, and the order in which their code runs decides the result:

| App | What it owns on the slip | Edited from here? |
|---|---|---|
| `hrms` v15.49.2 | The `SalarySlip` controller: structure rows, Additional Salary rows, payment days, proration, income tax from the slab, net pay | Never |
| `rdp_common_app` | `BSSalarySlip`, the class override that puts the slip on a BS month | Never |
| `avinashgroup_app` (this repo) | Six `validate` doc_events: fixed allowances, tax reliefs, manual tax override, BS period guard, daily breakdown, BS dates | Yes |

Previous stage: [05-payroll-entry.md](05-payroll-entry.md) (the entry that creates slips and the Prepare Payroll Inputs button that posts tea, meal, overtime and late fine as Additional Salary). Next stage: [07-after-the-slip.md](07-after-the-slip.md). Every setting named here is also a row in [impact-matrix.md](impact-matrix.md); every hook is listed in [hooks-inventory.md](hooks-inventory.md). User-facing description: [../user-guide/06-salary-slip.md](../user-guide/06-salary-slip.md).

All DB values below were read from `avinas1` on 2026-10-12.

---

## 6.0 The order things run in

A slip save runs `Document.validate` → the controller's `validate()` → the doc_events registered for `validate`, doctype-specific handlers first, then the `"*"` handlers ([`doc_events.get`](../../../frappe/frappe/model/document.py#L1365)). Hooks from all apps are concatenated in **installed-app order**; on avinas1 that is `frappe, erpnext, avinashgroup_app, rdp_common_app, hrms` (`tabInstalled Application`). HRMS and rdp_common_app register **no** Salary Slip doc_events, so every Salary Slip `validate` handler is ours.

| # | Step | Code | Notes |
|---|---|---|---|
| 1 | `BSSalarySlip.validate` | [`validate`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py#L265) | Calls HRMS's `validate` and only logs afterwards |
| 2 | HRMS `SalarySlip.validate` | [`validate`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L152) | Dates, structure, working days, `calculate_net_pay`, YTD (6.1–6.4) |
| 3 | Audit fields | [`AuditEventMapper`](../../avinashgroup_app/hooks.py#L256) | `doc_events` starts as the audit mapper's dict, so its `validate` handler is first in the list (Salary Slip is in its doctype list) |
| 4 | `add_employee_allowances` | [`add_employee_allowances`](../../avinashgroup_app/hooks.py#L376) | 6.5 |
| 5 | `apply_tax_reliefs` | [`apply_tax_reliefs`](../../avinashgroup_app/hooks.py#L383) | 6.8 |
| 6 | `apply_income_tax_override` | [`apply_income_tax_override`](../../avinashgroup_app/hooks.py#L387) | 6.9 |
| 7 | `bs_period_guard.validate_salary_slip` | [`validate_salary_slip`](../../avinashgroup_app/hooks.py#L394) | 6.10 |
| 8 | `build_daily_breakdown` | [`build_daily_breakdown`](../../avinashgroup_app/hooks.py#L397) | 6.11. The hooks.py comment calls it "last of the slip's validate hooks"; it is not: step 9 is appended later in the file |
| 9 | `set_bs_dates` | [`set_bs_dates`](../../avinashgroup_app/hooks.py#L480) | 6.12, registered by a loop further down `hooks.py` |
| 10 | `"*"` validate | erpnext's [`service_level_agreement.apply`](../../../erpnext/erpnext/hooks.py#L329) etc., then our [`apply_engine_numbering`](../../avinashgroup_app/hooks.py#L443) and [`dynamic_approval.validate`](../../avinashgroup_app/hooks.py#L480) | No Dynamic Approval Setting exists for Salary Slip, so the approval hook exits; numbering is covered in [09-cross-cutting.md](09-cross-cutting.md) |

No Server Script, Client Script or Notification exists for Salary Slip on avinas1 (checked 2026-10-12), so nothing else changes amounts.

**Why the order matters.** Steps 5–6 read the tax row that step 2 (and step 4's re-run of `calculate_net_pay`) produced; step 8 reads the final `net_pay`, so anything that changes net pay must stay before it. If a new hook changes amounts, register it before `apply_tax_reliefs`, or the tax and the daily breakdown will be computed on stale figures.

**Why hooks, not a class.** `override_doctype_class` lets only one app win, and rdp_common_app already overrides Salary Slip ([`BSSalarySlip`](../../../rdp_common_app/rdp_common_app/hooks.py#L149)). The docstrings of `salary_slip.py` and `tax_relief.py` give this as the reason everything here is a `validate` hook.

---

## 6.1 HRMS core: what a slip does on its own

[`SalarySlip.validate`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L152) runs, in order:

| Step | HRMS method | What it does | Overridden by BS slip? |
|---|---|---|---|
| Withholding, status, active employee, dates, existing slip | `check_salary_withholding`, `validate_dates`, `check_existing` | Refuses a second slip for the same period | No |
| Period | [`get_date_details`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L333) | AD month from `start_date` / `posting_date` | **Yes** (6.2) |
| New slip: structure | [`get_emp_and_working_day_details`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L340) → [`check_sal_struct`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L385) → [`pull_sal_struct`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L427) | Latest submitted assignment on an active structure; copies its rows | No |
| Existing slip: days only | [`get_working_days_details`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L441) | Recomputes LWP, absent and payment days | **Partly** (6.2) |
| Assignment for formulas | [`set_salary_structure_assignment`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L798) | Assignment with `from_date <= actual_start_date` ([`actual_start_date`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L804)) — throws if none | No |
| Amounts | [`calculate_net_pay`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L822) | Earnings (structure rows + Additional Salary), `remaining_sub_periods`, gross, deductions (+ tax), loans, net pay, tax breakup | Proration and tax months (6.2) |
| YTD, MTD, leave balances | `compute_year_to_date` … `add_leave_balances` | Display figures | No |

Inside `calculate_net_pay`:

1. [`calculate_component_amounts`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1144)`("earnings")` → [`add_structure_components`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1164) (formula rows evaluated against [`get_data_for_eval`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1215)) and [`add_additional_salary_components`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1329) (every submitted Additional Salary whose `payroll_date` is in the period, from [`get_additional_salaries`](../../../hrms/hrms/payroll/doctype/additional_salary/additional_salary.py#L218)). Each row goes through [`update_component_row`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1445), which prorates it.
2. `remaining_sub_periods` from [`get_period_factor`](../../../hrms/hrms/payroll/doctype/payroll_period/payroll_period.py#L102) (AD months; replaced later, 6.2).
3. `gross_pay` = [`get_component_totals`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1911)`("earnings", depends_on_payment_days=1)` — note it **re-prorates every row from `default_amount`** rather than summing `amount` (this matters in Gotcha G1).
4. Deductions: structure rows (SSF, Late Fine tag), Additional Salary deductions (late fine, advance recovery), then [`add_tax_components`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1343) (6.7).
5. [`set_net_pay`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L856): `net_pay = gross_pay − total_deduction − total_loan_repayment`, `rounded_total = rounded(net_pay)`, amount in words from `rounded_total` (Payroll Settings `disable_rounded_total` = 0 on avinas1).

**Data visible to formulas** ([`get_data_for_eval`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1215)): the assignment's fields, then the slip's, then the Employee's (later ones win on a name clash), then every component abbreviation (`B`, `SSFA`, …) at its **prorated** `amount`. `custom_ssf_applicable` exists only on Salary Structure Assignment (no Employee field of that name on avinas1), so the structure's SSF formula and the slab's SST condition read the assignment's tick.

---

## 6.2 The BS override (`BSSalarySlip`, rdp_common_app)

**What.** A subclass of HRMS `SalarySlip` ([`BSSalarySlip`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py#L47)) that replaces AD month boundaries with Bikram Sambat ones. Every method falls back to HRMS when [`is_bs_payroll_enabled`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/doctype/nepal_hrms_settings/nepal_hrms_settings.py#L31) is false.

**Why.** The books, the salary sheet and HR all run on BS months (Shrawan–Ashadh fiscal year); an AD-month slip would never match the sheet (module docstring).

**Config on avinas1.** Nepal HRMS Settings: `process_payroll_in_nepali_month = 1`, `restrict_to_nepal_companies = 1`. `tabNepal BS Period`: **0 rows**, so every period comes from the calendar.

| Method | What changes | Downstream effect |
|---|---|---|
| [`get_date_details`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py#L60) | `start_date` / `end_date` = the BS month that contains **`posting_date`**: a Nepal BS Period record ([`get_user_defined_period`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/doctype/nepal_bs_period/nepal_bs_period.py#L109)) first, else [`get_salary_period`](../../../rdp_common_app/rdp_common_app/utils/bs_boundaries.py#L162) | The period is recomputed on **every** save from the posting date. A Bhadra entry posted on 2 Ashwin silently produces Ashwin slips; that is why `bs_period_guard` exists (6.10, [05-payroll-entry.md](05-payroll-entry.md)) |
| [`get_working_days_details`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py#L122) | Runs HRMS's version, then sets `total_working_days` = length of the BS month of `start_date` ([`get_total_working_days_in_bs_month`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py#L111)) | Payment days are **not** touched. With holidays included (avinas1) HRMS already counts every calendar day, so the override only matters when a Nepal BS Period differs from the calendar month |
| [`get_amount_based_on_payment_days`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py#L191) | Temporarily sets `total_working_days` to the BS month length and calls HRMS's [`get_amount_based_on_payment_days`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1795) | Proration = `default_amount × payment_days ÷ BS month days` (29–32) |
| [`compute_current_and_future_taxable_earnings`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py#L225) | `remaining_sub_periods` = BS months from the slip's start to the Payroll Period end, inclusive ([`get_bs_months_between`](../../../rdp_common_app/rdp_common_app/utils/bs_boundaries.py#L187)) | Shrawan = 12, Bhadra = 11 … Ashadh = 1. Every projected and per-month tax figure uses it, and so does our `apply_tax_reliefs` |

**Gotchas.**
- `get_total_working_days_in_bs_month` uses the BS month of `start_date`, not the length of the slip's period. A Nepal BS Period that starts or ends off the calendar month would prorate with the calendar month's length (unverified in practice: no BS Period rows exist).
- `calculate_net_pay` resets `remaining_sub_periods` to the AD value each time it runs, and the override re-patches it inside the tax computation. Code that reads `remaining_sub_periods` between those two points sees the AD figure. Our hooks run after both, so they see the BS figure.

---

## 6.3 Payment days and total working days

**What.** `payment_days` is the number of days paid in full; every row whose component has *Depends on Payment Days* is multiplied by `payment_days ÷ total_working_days`.

**Where.** [`get_working_days_details`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L441), [`get_payment_days`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L617), [`calculate_lwp_ppl_and_absent_days_based_on_attendance`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L724), [`get_half_absent_days`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L544), [`get_unmarked_days`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L529). Payroll Settings were set by `patches/setup_payroll_based_on_attendance.py` (see [01b-pay-masters.md](01b-pay-masters.md)).

The formula, with avinas1's Payroll Settings:

```
total_working_days = days in the BS month (29–32)                     (BS override)
payment_days       = days between max(start, joining) and min(end, relieving), inclusive
                     − LWP days (On Leave with an is_lwp Leave Type; half of a Half Day LWP)
                     − Absent days (status Absent)
                     − 0.5 × Half Day rows whose half_day_status = Absent
                     (− unmarked days, only if unmarked counts as Absent: it does not here)
```

| Payroll Setting | avinas1 | Effect on the slip |
|---|---|---|
| `payroll_based_on` | Attendance | LWP and absent days come from Attendance rows, not Leave Applications |
| `include_holidays_in_total_working_days` | 1 | Holidays are paid days; neither total nor payment days drop them |
| `consider_marked_attendance_on_holidays` | 0 | An Absent / Half Day row on a holiday costs nothing |
| `consider_unmarked_attendance_as` | Present | **A day with no Attendance at all is paid.** Only rows actually marked Absent or half-absent cut pay. With auto attendance off on avinas1 ([02-checkin-to-attendance.md](02-checkin-to-attendance.md)), a month nobody marked pays everyone 100% |
| `daily_wages_fraction_for_half_day` | 0.5 | A late half day (`half_day_status` Absent, from [03-shift-measurement.md](03-shift-measurement.md)) costs 0.5 day |
| `disable_rounded_total` | 0 | `rounded_total` is filled and printed |
| `email_salary_slip_to_employee` / `email_template` | 1 / `Salary Slip (BS)` | See [07-after-the-slip.md](07-after-the-slip.md) |
| `process_payroll_accounting_entry_based_on_employee` | 0 | One payable line per journal ([07](07-after-the-slip.md)) |

**Which components are prorated** (Salary Component `depends_on_payment_days`, avinas1): Basic, all Monthly allowances (Dearness, Other, Fixed, Fuel, Gas, Education, Maintenance, Transport), House Rent Allowance, Load/Unload. **Not prorated:** Leave Encashment and Dashain Allowance (one-off amounts already worked out; since 2026-10-13), SSF Addition and SSF (they are a share of the already-prorated Basic, so prorating again would cut twice — [../payroll-ngi.md](../payroll-ngi.md)), Income Tax, Late Fine, and every attendance-driven earning (Tea, Meal, Overtime: already counted per day; `validate_salary_component` forces this, see [01b-pay-masters.md](01b-pay-masters.md)).

**Impacts downstream.** Gross pay, SSF (31% of prorated Basic), taxable income for the month, the daily breakdown's fixed-pay rate, the salary sheet's "Deduction" column ([07](07-after-the-slip.md)).

---

## 6.4 Structure rows: Basic, SSF Addition, SSF, Late Fine tag, Income Tax

**What.** Four submitted structures exist, one per payroll company, each with the same five rows. GLMI, GEPL and SGU have no structure and no assignment (they do not run payroll yet).

| Structure (avinas1) | Earnings | Deductions |
|---|---|---|
| `NGI Staff 83/84`, `NGN Staff 83/84`, `NGG Staff 83/84`, `NGK Staff 83/84` | Basic = `base` (prorated); SSF Addition = `B * 0.20 if custom_ssf_applicable else 0` | SSF = `B * 0.31 if custom_ssf_applicable else 0`; Late Fine (no formula, a tag); Income Tax (no formula, `variable_based_on_taxable_salary`) |

**Why.** The SSF Act: the employer contributes 20% of basic and the employee 11%; the whole 31% is deposited. The employer's 20% is paid to the employee as an earning (SSF Addition) and the 31% taken back as one deduction, so the net effect on the employee is −11% and SSF Payable receives the full 31% ([../user-guide/09-accounts-setup.md](../user-guide/09-accounts-setup.md) §9.3; [`SSF_EMPLOYER`](../../avinashgroup_app/avinash_group_app/report/salary_tax_and_ssf_deposit/salary_tax_and_ssf_deposit.py#L46) in the deposit report). The Late Fine row only says "this structure charges late fines"; the amount comes from Additional Salary ([05-payroll-entry.md](05-payroll-entry.md)).

**Where the 20/31 lives:** in the structure rows' `formula` (data, not code). `B` is the **prorated** Basic, so SSF follows absences automatically. `custom_ssf_applicable` is the assignment's tick (6.1).

**Tax flags on the components (avinas1):**

| Component | Type | `is_tax_applicable` | `exempted_from_income_tax` | Effect |
|---|---|---|---|---|
| Basic, SSF Addition, every allowance, Tea, Meal, Overtime, Salary Arrears, Dashain Bonus | Earning | 1 | — | Taxable |
| SSF | Deduction | — | **1** | Leaves taxable income (subject to the retirement cap, 6.8) |
| Professional Tax | Deduction | — | 1 | Exempt (not used on avinas1) |
| Late Fine | Deduction | 0 | **0** | Reduces net pay but **not** taxable income: tax is charged on pay before the fine |
| Salary Advance | Deduction | 0 | 0 | Recovery only; no tax effect |
| Income Tax | Deduction | 1 | 0 | `variable_based_on_taxable_salary` = 1, `round_to_the_nearest_integer` = 1 |

HRMS copies the exemption flag onto each structure row when the row is written; changing a component flag later does nothing to an existing structure until its rows are re-synced ([../payroll-ngi.md](../payroll-ngi.md) "Income tax and SST").

---

## 6.5 Fixed allowances from the assignment (`add_employee_allowances`)

**What.** Puts the employee's **Monthly** and **% of Initial Basic** allowances on the slip as ordinary (non-additional) earning rows, adds/updates/drops them to match the assignment, then reruns HRMS's `calculate_net_pay`.

**Where.** [`add_employee_allowances`](../../avinashgroup_app/payroll/salary_slip.py#L33); amounts from [`fixed_allowance_amounts`](../../avinashgroup_app/payroll/allowance.py#L332), rows from [`get_employee_allowance_rows`](../../avinashgroup_app/payroll/allowance.py#L285), assignment from [`current_assignment`](../../avinashgroup_app/payroll/allowance.py#L270); kinds in [`FIXED_KINDS`](../../avinashgroup_app/payroll/allowance.py#L73).

**Why** (module docstring, [../allowances.md](../allowances.md)):
- Every person has their own mix (27 combinations across 195 people, October 2026), so allowances are rows on the person's Salary Structure Assignment, not structure formulas. No row → not paid.
- **Not** monthly Additional Salary, because HRMS treats Additional Salary as a one-off and would not project it over the rest of the year, under-taxing. Rows without `additional_salary` are projected like structure rows and prorated by payment days.
- A hook, not a class: rdp_common_app owns the Salary Slip class.

**Triggered by.** Salary Slip `validate`, draft slips with a structure only (`docstatus != 0` → returns).

**Reads.** Salary Structure Assignment (`custom_initial_basic`, child `custom_allowances` → Assignment Allowance `allowance`, `rate`, `effective_from`); Salary Component `custom_allowance_kind`.
**Writes.** Slip `earnings` rows (`default_amount` = full month, `amount` = prorated), then every total via `calculate_net_pay`.

| Kind | Full-month amount | Example (avinas1) |
|---|---|---|
| Monthly | the row's `rate` | Dearness 7,380; Gas 1,690; Education 2,780 |
| % of Initial Basic | `custom_initial_basic × rate ÷ 100` | HRA 25% × 17,165.50 = 4,291.38 |

**Impacts downstream.** Gross, taxable income (projected × remaining months), SSF is unaffected (reads `B` only), the journal's expense lines, the salary sheet's allowance columns.

**Gotchas.**
- **G1 — stale row amounts when payment days change on a re-save. Fixed 2026-10-12.** The early exit `if have == wanted: return` compared full-month `default_amount`s, so a re-save after payment days changed left these rows at the old proration while `gross_pay` was re-prorated (reproduced: 2 absences, Dearness stayed 13,635 instead of 12,755.32). The hook now rebuilds the rows on every save; test `TestAllowanceProration` in payroll/test_payroll_checks.py.
- `current_assignment` picks the latest submitted assignment with `from_date <= end_date`, while HRMS's `set_salary_structure_assignment` uses `from_date <= actual_start_date`. An assignment starting mid-month is used for allowances but not for Basic. Salary Revision always starts on the 1st of a BS month, so this should not occur in normal use.
- `current_assignment` filters by employee only, not company or structure.
- A structure's *Preview Salary Slip* does not run `validate`, so it shows no allowances ([../user-guide/06-salary-slip.md](../user-guide/06-salary-slip.md) §6.5).

---

## 6.6 Attendance-driven rows (Additional Salary)

Tea & Conveyance, Meal, Overtime (earnings) and Late Fine, Salary Advance recovery (deductions) arrive as submitted **Additional Salary** created by *Prepare Payroll Inputs* ([05-payroll-entry.md](05-payroll-entry.md)); arrears by Salary Revision ([08-changes-over-time.md](08-changes-over-time.md)). HRMS picks them up in `add_additional_salary_components`. On the slip they have `default_amount = 0`, `additional_amount = amount`, and are not prorated.

Tax treatment: [`_make_additional_salary`](../../avinashgroup_app/payroll/attendance_allowance.py#L829) sets [`deduct_full_tax_on_selected_payroll_date`](../../avinashgroup_app/payroll/attendance_allowance.py#L850) = 1 on earnings. HRMS therefore does **not** spread their tax over the remaining months: the extra tax they cause is charged in full in the month they are paid (`full_tax_on_additional_earnings`, 6.7). Salary Arrears (Salary Revision) is flagged the same way.

On avinas1 there are 10 Additional Salary rows, all from Prepare Payroll Inputs, all dated 2026-08-16 (NGI Shrawan, 4 employees). **The Bhadra runs at NGI and NGN carry none**: no tea, meal, overtime or late fine was paid in Bhadra (see the worked example's notes).

---

## 6.7 Income tax: what HRMS computes

**Where.** [`add_tax_components`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1343) → [`get_income_tax_slabs`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1592) (the slab named on the **assignment**; refused if disabled or effective after the Payroll Period start) → [`compute_taxable_earnings_for_year`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L873) → [`calculate_variable_tax`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1550) → [`calculate_tax_by_tax_slab`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L2199).

```
taxable this month (payment days)  = Σ taxable earnings (prorated) − Σ exempt deductions (SSF)        [get_taxable_earnings]
future structured                  = same, full month, × (remaining_sub_periods − 1)                  [BS months left]
total_taxable_earnings             = previous slips' taxable (this Payroll Period)
                                     + this month + future + this month's additional earnings
                                     + other income − total_exemption_amount (declaration / proof)
year's tax (structured)            = slab(total_taxable_earnings − additional-with-full-tax)
this month                         = (year's tax − tax already deducted this period) ÷ remaining_sub_periods
                                     + [slab(total incl. full-tax additions) − year's tax]
```

[`get_taxable_earnings`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1699) and [`get_total_exemption_amount`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1869) hold the rules. The row is rounded to the rupee (`round_to_the_nearest_integer` on Income Tax). The tax breakup fields (`annual_taxable_amount`, `current_month_income_tax`, `future_income_tax_deductions`, `total_income_tax`) are filled by [`compute_income_tax_breakup`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L949) from the **unrounded** figure, so they differ from the row by paisa.

**The slab and SST.** One `Income Tax Slab` per company, `Nepal 83/84 - <abbr>`, effective 2026-07-17, `allow_tax_exemption` = 1, no standard exemption, `tax_relief_limit` 0, `custom_women_rebate_percent` = 10:

| From | To | % | Condition |
|---|---|---|---|
| 0 | 10,00,000 | 1 | `not custom_ssf_applicable` |
| 10,00,001 | 15,00,000 | 10 | |
| 15,00,001 | 25,00,000 | 20 | |
| 25,00,001 | 40,00,000 | 27 | |
| 40,00,001 | — | 29 | |

The first band is the 1% Social Security Tax, waived for SSF contributors; HRMS skips a band whose condition is false, so one Income Tax component yields either the SST or the progressive tax (`payroll/income_tax.py` module docstring, [../payroll-ngi.md](../payroll-ngi.md)). The seed table is [`FY_8384_SLABS`](../../avinashgroup_app/payroll/income_tax.py#L31) in [`TAX_SLABS_BY_YEAR`](../../avinashgroup_app/payroll/income_tax.py#L45); the slip reads the **record**, created by [`ensure_income_tax_slab`](../../avinashgroup_app/hr/year_setup.py#L355). Changing `FY_8384_SLABS` changes nothing on a slip until a new slab record is built.

**Payroll Period.** One per company, `83/84 - <abbr>`, 2026-07-17 → 2027-07-16 (made by [`ensure_payroll_period`](../../avinashgroup_app/hr/year_setup.py#L335)). A slip outside any Payroll Period gets no tax and a message.

**Exemptions on avinas1.** Categories: *Insurance Premium* (max 70,000; sub-categories Life 40,000, Health 20,000, Private Building 10,000) and *Retirement Contribution* (max 5,00,000, `custom_is_retirement_contribution` = 1, `custom_cap_percent_of_income` = 33.333333; sub-categories "CIT paid directly", "Provident Fund paid directly"). Entered as documented in commit `4d6af9a` ([../user-guide/08-raises-advances-bonuses-year-end.md](../user-guide/08-raises-advances-bonuses-year-end.md)). **0** Employee Tax Exemption Declarations, **0** Proof Submissions and **0** Employee Other Income rows exist, so `total_exemption_amount` is 0 on every slip today. HRMS switches from declaration to proof in the Payroll Period's last month (`deduct_tax_for_unsubmitted_tax_exemption_proof`).

**Gotchas.**
- **Opening figures.** `previous_taxable_earnings` comes only from slips in the system, plus the assignment's `taxable_earnings_till_date` / `tax_deducted_till_date` (read only from an assignment starting inside the year). NGI's Shrawan 2083 run covers 4 people; for the other 83, and all 63 at NGN, Shrawan is in neither, so its income and tax are missing from the year's projection. Since 2026-10-12 the Payroll Entry warns "Tax history missing" and names them ([`tax_history_gaps`](../../avinashgroup_app/payroll/income_tax.py#L61)); the figures themselves are accounts' to enter.
- The SST band condition reads the assignment's `custom_ssf_applicable`; an employee whose SSF tick is wrong pays the wrong band for the whole year.

---

## 6.8 Retirement cap and women's rebate (`apply_tax_reliefs`)

**What.** Recomputes the tax row when either Nepal relief applies, using HRMS's own intermediate figures; leaves the slip untouched otherwise.

**Where.** [`apply_tax_reliefs`](../../avinashgroup_app/payroll/tax_relief.py#L77), [`retirement_excess`](../../avinashgroup_app/payroll/tax_relief.py#L131), [`retirement_cap`](../../avinashgroup_app/payroll/tax_relief.py#L66), [`retirement_categories`](../../avinashgroup_app/payroll/tax_relief.py#L57), [`declared_retirement`](../../avinashgroup_app/payroll/tax_relief.py#L170), [`women_rebate_fraction`](../../avinashgroup_app/payroll/tax_relief.py#L189); Employee guard [`validate_womens_tax_rebate`](../../avinashgroup_app/payroll/tax_relief.py#L202) (hooked at [`validate_womens_tax_rebate`](../../avinashgroup_app/hooks.py#L356)).

**Why** (module docstring):
1. *Retirement cap (Income Tax Act 2058 s.63).* Contributions to SSF/CIT/PF are deductible only up to the lower of a share of assessable income and a fixed yearly amount. HRMS exempts every rupee of an exempt deduction, so high earners were under-taxed. The excess over the cap is put back into taxable income.
2. *Women's rebate (Schedule 1, 1(10)).* A resident woman whose only income is employment gets a percentage off her tax. Gender alone cannot decide it, so HR ticks `custom_womens_tax_rebate` on the Employee (commit `5f54331`); the percentage is on the slab.
3. No figure lives in code: a blank field means the relief is off (user decision 2026-09-29).

**How.**
```
excess   = max(previous + current + future exempt deductions + declared retirement − cap, 0)
cap      = min(category max_amount, assessable × custom_cap_percent_of_income ÷ 100)
tax      = slab(total_taxable_without_full_tax + excess) × (1 − rebate)
month    = (tax − previous_total_paid_taxes) ÷ remaining_sub_periods  [+ full tax on additions, also × (1 − rebate)]
```
It writes the tax row (`amount`, `default_amount`), `custom_retirement_excess`, `custom_women_rebate`, the breakup fields, then `set_net_pay`.

**Config on avinas1.** Cap: 5,00,000 or 33.33% of assessable income. Rebate: 10% on all seven slabs. Employees ticked for the rebate: **0** (21 active women across NGI 17, NGG 3, NGN 1). Slips with a non-zero `custom_retirement_excess` or `custom_women_rebate`: **0**.

**Gotchas.**
- "Exempt deductions" are measured as *all* exempt deductions on the slip (`amount_exempted_from_income_tax`), not only retirement ones. Today SSF is the only exempt deduction in use; a future exempt non-retirement component (Professional Tax is flagged exempt) would be wrongly counted toward the cap.
- The recomputed row is **not** re-rounded to the rupee (it uses the field precision), unlike HRMS's own figure (unverified on a real slip: no slip has triggered it).
- Ticking the rebate on a man is refused at Employee save.

---

## 6.9 Manual income tax (`apply_income_tax_override`)

**What.** Stores the computed tax in `custom_income_tax_computed`; when `custom_override_income_tax` is ticked, replaces the tax row with `custom_income_tax_override` (zero allowed) and recomputes net pay. If the slip has no tax row, it appends one from the first deduction component with `variable_based_on_taxable_salary`.

**Where.** [`apply_income_tax_override`](../../avinashgroup_app/payroll/income_tax.py#L156), [`get_tax_row`](../../avinashgroup_app/payroll/income_tax.py#L148).

**Why.** The computed figure is a projection; accounts often knows better (previous employer's income, late declarations, auditor's figure) — module docstring, [../payroll-ngi.md](../payroll-ngi.md) "Changing it by hand".

**Fields.** Salary Slip `custom_override_income_tax` (Check), `custom_income_tax_override` (Currency), `custom_income_tax_computed` (read-only). None is *Allow on Submit*: the override must be set on the draft.

**Impacts downstream.** Total deduction, net pay, the journal's TDS-Remuneration credit, the deposit report's SST/remuneration split ([07](07-after-the-slip.md)), and next month's `previous_total_paid_taxes` (HRMS reads tax actually deducted, so next month's projection self-corrects).

**Config on avinas1.** 0 slips overridden.

**Gotcha.** It runs after `apply_tax_reliefs`, so the computed figure shown includes the reliefs and a typed figure always wins. The breakup fields (`current_month_income_tax` etc.) are **not** updated by the override; the payslip prints "Income tax set by accounts".

---

## 6.10 Slip and entry must agree on the month (`bs_period_guard.validate_salary_slip`)

**What.** Throws when a slip made by a Payroll Entry has a `start_date` different from the entry's.
**Where.** [`validate_salary_slip`](../../avinashgroup_app/payroll/bs_period_guard.py#L70); the entry-side twin [`validate_payroll_entry`](../../avinashgroup_app/payroll/bs_period_guard.py#L45) is covered in [05-payroll-entry.md](05-payroll-entry.md).
**Why.** The BS slip derives its period from the posting date (6.2). Paying Bhadra on 2 Ashwin used to produce Ashwin slips under a Bhadra entry, with Ashwin's attendance and allowances (module docstring).
**Gotcha.** It does not move dates; it only refuses. A slip with no Payroll Entry is not checked.

---

## 6.11 Daily Breakdown (`build_daily_breakdown`)

**What.** Fills `custom_daily_breakdown` (child doctype **Salary Slip Day**: `line_type` Day / Month End, `miti`, `date`, `weekday`, `attendance`, `paid_day`, `fixed_pay`, `earned`, `deducted`, `detail`, `day_total`, `balance`) with one row per day and month-end rows, ending exactly at `net_pay`.

**Where.** [`build_daily_breakdown`](../../avinashgroup_app/payroll/daily_breakdown.py#L64), [`breakdown_rows`](../../avinashgroup_app/payroll/daily_breakdown.py#L80), [`paid_weight`](../../avinashgroup_app/payroll/daily_breakdown.py#L219), [`spread_over_days`](../../avinashgroup_app/payroll/daily_breakdown.py#L162), [`attendance_additional_salaries`](../../avinashgroup_app/payroll/daily_breakdown.py#L207), [`fetch_holidays`](../../avinashgroup_app/payroll/daily_breakdown.py#L277). Created by `patches/setup_salary_slip_daily_breakdown.py`.

**Why.** Employees asked "why is my tea 2,115 and not 2,350?"; the slip only had monthly totals (module docstring, [../allowances.md](../allowances.md) "Daily breakdown on the salary slip").

**How it reconciles.**
- Fixed pay per day = (Σ non-additional, non-statistical earning `amount`s ÷ `payment_days`) × the day's weight: Absent 0, Half Day 0.5 (1 if the other half is paid leave), LWP 0, holiday and paid leave 1, unmarked 1 when Payroll Settings says Present.
- Each Additional Salary posted by Prepare Payroll Inputs (`custom_source` = [`SOURCE_TAG`](../../avinashgroup_app/payroll/attendance_allowance.py#L39)) is spread over the days by the same [`evaluate_rule`](../../avinashgroup_app/payroll/attendance_allowance.py#L297) that counted it; a line that counted another month (Attendance Month = Previous Month) or hand-made Additional Salary goes to month end.
- A difference under 1 rupee becomes a *Rounding* row; anything larger an *Adjustment: attendance differs from the slip's payment days* row.

**Triggered by.** Every validate except on cancelled slips; frozen at submit. Failures are logged (`Daily breakdown failed for …` in Error Log) and never block the save.

**Impacts.** Display only: printed on page 2 of the *Salary Slip BS* print format and in the emailed PDF. No amount reads it.

**Gotcha.** It re-reads attendance and evaluates the rules at save time; if attendance changed after the Additional Salary was posted, the per-day spread follows the new attendance while the amount stays the old one (it is scaled to the posted amount, so the total still matches).

---

## 6.12 BS dates on the slip (`set_bs_dates`)

**What.** Writes `custom_posting_miti`, `custom_start_miti`, `custom_end_miti` (YYYY-MM-DD BS) and `custom_bs_month` ("Bhadra 2083", from `end_date`).
**Where.** [`set_bs_dates`](../../avinashgroup_app/hr/bs_dates.py#L75), field map [`BS_DATE_FIELDS`](../../avinashgroup_app/hr/bs_dates.py#L29); fields made read-only on Salary Slip by `patches/setup_hr_bs_dates.py`.
**Why.** HR and staff speak BS; the BS payslip header and the email subject (`Salary Slip — {{ custom_bs_month }} · {{ company }}`) need it.
**Impacts.** Print format, email template, list-view filter on `custom_bs_month`. Changes no amount; conversion errors are logged, never raised.

---

## 6.13 Net pay and rounding

`net_pay = gross_pay − total_deduction − total_loan_repayment` (no loan app is installed; `total_loan_repayment` is 0). `rounded_total` = `net_pay` rounded to the rupee; the payslip prints `rounded_total`. The Bank Entry pays the sum of slip amounts, not `rounded_total` ([07](07-after-the-slip.md)). Each of our hooks that changes a deduction calls HRMS's `set_net_pay` itself (tax relief, override); `add_employee_allowances` calls the full `calculate_net_pay`. HRMS refuses to submit a slip with negative net pay ([`on_submit`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L207)).

---

## 6.14 Salary Slip custom fields (avinas1)

| Field | Type | Written by | Read by |
|---|---|---|---|
| `custom_income_tax_computed` | Currency, read-only | `apply_income_tax_override` | Payslip, accounts |
| `custom_override_income_tax` / `custom_income_tax_override` | Check / Currency | HR / accounts by hand | `apply_income_tax_override`, payslip note |
| `custom_retirement_excess` | Currency, read-only | `apply_tax_reliefs` | Payslip note |
| `custom_women_rebate` | Percent, read-only | `apply_tax_reliefs` | Payslip note |
| `custom_posting_miti`, `custom_start_miti`, `custom_end_miti`, `custom_bs_month` | Data, read-only | `set_bs_dates` | Payslip, email template, list filter |
| `custom_daily_breakdown` (Table → Salary Slip Day) | read-only | `build_daily_breakdown` | Payslip page 2 |
| `custom_created_by`, `custom_created_on`, `custom_modified_by` | Audit | audit_file_manager | [09-cross-cutting.md](09-cross-cutting.md) |

---

## 6.15 Worked example: NGI-SAL-83/84-00004 (Shrawan 2083)

A real submitted slip on avinas1, chosen because it exercises every kind of line. Employee NGI-EMP-00040, department *Plant/ Maintenance - NGI* → section **Plant (F/P)**, OT-eligible, not late-fine exempt. Payroll Entry NGI-PAYR-83/84-00001, posted 2026-08-16 (= 31 Shrawan 2083). Journal NGI-JE-83/84-00004.

**Inputs.**
- Assignment HR-SSA-26-10-00036 from 2026-07-17: `base` 19,838.181667, `custom_initial_basic` 17,165.50, `custom_ssf_applicable` 1, slab `Nepal 83/84 - NGI`, structure `NGI Staff 83/84`.
- Allowances table: Other 1,000; Education 2,780; Dearness 7,380; Gas 1,690; HRA 25 (%); Tea & Conveyance 235/day; Meal 75; Overtime 0 (computed rate).
- Attendance 17 Jul – 16 Aug 2026: 26 Present (1 of them on a holiday), 1 Absent, the rest unmarked (paid, unmarked = Present).

**Days.** Period 2026-07-17 → 2026-08-16 = Shrawan 2083, 31 days (BS override). `payment_days` = 31 − 1 Absent = **30**.

| Line | Rule | Calculation | Slip amount |
|---|---|---|---|
| Basic | structure `base`, prorated | 19,838.18 × 30 / 31 | 19,198.24 |
| SSF Addition | `B × 0.20`, not prorated | 19,198.24 × 0.20 | 3,839.65 |
| Other Allowance | Monthly, prorated (6.5) | 1,000 × 30/31 | 967.74 |
| Education Allowance | Monthly | 2,780 × 30/31 | 2,690.32 |
| Dearness Allowance | Monthly | 7,380 × 30/31 | 7,141.94 |
| Gas Allowance | Monthly | 1,690 × 30/31 | 1,635.48 |
| House Rent Allowance | 25% of Initial Basic | 17,165.50 × 25% = 4,291.38 × 30/31 | 4,152.95 |
| Meal | Additional Salary HR-ADS-26-10-00002 | 4 × 75 | 300.00 |
| Tea & Conveyance | HR-ADS-26-10-00003 | 25 days × 235 (the holiday day earns none: `custom_pay_on_holiday` Do Not Pay) | 5,875.00 |
| Overtime | HR-ADS-26-10-00004 | 12 h × 123.988 | 1,487.86 |
| **Gross** | | | **47,289.18** |
| SSF | `B × 0.31` | 19,198.24 × 0.31 | 5,951.45 |
| Late Fine | HR-ADS-26-10-00001 | 0.6667 h × 82.665 | 55.11 |
| Income Tax | slab | see below | 0.00 |
| **Total deduction** | | | **6,006.56** |
| **Net pay** / rounded | | 47,289.18 − 6,006.56 | **41,282.62** / 41,283 |

**Tax.** Annual taxable = this month's prorated non-additional taxable pay (39,626.32 − SSF 5,951.45 = 33,674.87) + additional earnings (7,662.86) + 11 future months at the full-month figure (40,947.20 − 5,951.45 = 34,995.75 × 11 = 3,84,953.25) = **4,26,290.98** (`annual_taxable_amount` on the slip). SSF member → the 1% band is skipped; 4,26,290.98 is below the 10% band → **0**. Remaining sub-periods: 12 (Shrawan).

**Daily breakdown.** 33 rows: 31 days at a fixed rate of 39,626.32 ÷ 30 = 1,320.88 per paid day, plus 235 tea on each present day, then *SSF −5,951.45* and *Rounding −0.08* at month end, ending at 41,282.62.

**Journal.** Its earnings went to `547103 - Salary Expenses - F/P - NGI` and its late fine was credited back to the same account (line 6 of NGI-JE-83/84-00004, 55.11) — see [07-after-the-slip.md](07-after-the-slip.md).

**Notes on this example.**
- The Overtime and Late Fine rates (123.988 = 1.5 × 82.659; 82.665) were priced with a **30-day** divisor, before commit `c82193b` (2026-10-12) switched the hourly basic to the BS month's actual days. Pressing Prepare Payroll Inputs again for Shrawan today would price overtime at 19,838.18 ÷ 31 ÷ 8 × 1.5 = 119.99/h (see [05-payroll-entry.md](05-payroll-entry.md)). The late fine's 82.665 does not exactly match either divisor (19,838.18 ÷ 240 = 82.659); unverified why.
- A Bhadra contrast: NGI-SAL-83/84-00038 (NGI-EMP-00002) has no Attendance rows at all in Bhadra, so payment days = 31 (unmarked = Present) and no tea is paid although the assignment lists Tea 40/day. Monthly taxable 1,08,205.10 × 11 remaining months = 11,90,256.10; 10% above 10,00,000 = 19,025.61 ÷ 11 = 1,729.60 → row 1,730 (rounded to the rupee). Its `income_tax_deducted_till_date` shows 1,729.60, the unrounded figure.

---

## 6.16 Known open issues (this stage)

| # | Issue | Status |
|---|---|---|
| G1 | Allowance row amounts went stale when a draft's payment days changed on re-save (6.5) | Fixed 2026-10-12 |
| G2 | No tax opening balances for months paid outside the system (6.7) | Unverified whether Shrawan was paid outside |
| G3 | Retirement cap counts every exempt deduction, not only retirement ones (6.8) | Latent; only SSF is exempt today |
| G4 | Women's rebate: 0 of 21 active women ticked | Data, HR to confirm per person |
| G5 | Bhadra 2083 slips (NGI 87, NGN 63) carry no tea / meal / OT / late fine: Prepare Payroll Inputs was not run or found no attendance | Confirm with HR; see [05-payroll-entry.md](05-payroll-entry.md) |
| G6 | [../payroll-ngi.md](../payroll-ngi.md) "The structure" still lists Dearness, Other, HRA, Gas, Education as structure formulas reading Employee fields (`custom_dearness_allowance`, `custom_hra_eligible`…) and says rates come from "Allowance Category". The live structures have only Basic / SSF Addition / SSF / Late Fine / Income Tax; allowances come from the assignment (`move_pay_to_salary_assignment`, `allowance_rate_list` patches) | Doc is stale |
