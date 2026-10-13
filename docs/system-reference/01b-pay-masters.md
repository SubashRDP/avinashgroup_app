# 01b · Masters and setup (pay)

The pay-side setup every slip reads: settings, the payroll period and tax table, exemption categories, salary components, structures, assignments, and the department → account mapping. The people-side masters (Employee fields, Employee Category, holiday lists, shift types, leave types, Fiscal Year) are in [01-masters.md](01-masters.md). What happens to these records month by month is in [05-payroll-entry.md](05-payroll-entry.md), [06-salary-slip.md](06-salary-slip.md) and [07-after-the-slip.md](07-after-the-slip.md); how they change over time is in [08-changes-over-time.md](08-changes-over-time.md). Every field below is also a row in [impact-matrix.md](impact-matrix.md).

All values are from `avinas1`, read on **2026-10-12**.

## The model in one paragraph

HRMS calculates a slip from a **Salary Structure** (formula rows) applied to a **Salary Structure Assignment** (the person's `base`), plus submitted **Additional Salary** documents, then taxes it with the **Income Tax Slab** named on the assignment, projected over the **Payroll Period**. This app keeps that engine and adds three things around it (allowance.py docstring ([`Allowances`](../../avinashgroup_app/payroll/allowance.py#L1)), [docs/allowances.md](../allowances.md)):

1. **Salary Component** says what an allowance *is* and how it is counted (`custom_allowance_kind`) and which three accounts it posts to (O/O, S/D, F/P). It holds no rate.
2. **Salary Structure → Allowance Rates** lists the *usual* rate of each allowance for that structure (tea 235/day, gas 1,690/month, HRA 25 %). It decides nobody's pay; it is the starting Allowances table when a structure is picked on a draft assignment, fills a row's rate when an allowance is picked, and is what a Salary Revision raises.
3. **Salary Structure Assignment → Allowances** lists the allowances *this person* gets and at what rate. **No row = not paid.** Payroll reads only this table.

The structure's own Earnings/Deductions keep only formula lines (Basic, SSF Addition, SSF, Income Tax) and the Late Fine tag.

| Stock HRMS / ERPNext | What this app adds or overrides |
|---|---|
| Payroll Settings, Payroll Period, Income Tax Slab, exemption categories, components, structures, assignments | Custom fields on all of them (below); validate hooks on Component / Structure / Assignment; BS-month engine via `rdp_common_app` |
| Allowances as structure formula rows, paid to everyone on the structure | Allowances as **assignment rows**; [`validate_salary_structure`](../../avinashgroup_app/payroll/allowance.py#L419) refuses an allowance in Earnings |
| One GL account per component per company | Three accounts per company row (O/O, S/D, F/P) chosen by the employee's Department section, see [07-after-the-slip.md](07-after-the-slip.md) |
| Tax slab rows with optional Python condition | SST (1 %) waived for SSF members by a row condition; women's rebate and retirement cap added on top (see [06-salary-slip.md](06-salary-slip.md)) |

---

## 1. Payroll Settings (HRMS single doctype)

**What.** Global switches HRMS's Salary Slip reads to count working days, payment days and the accrual journal shape.
**Where.** HRMS schema [`payroll_based_on`](../../../hrms/hrms/payroll/doctype/payroll_settings/payroll_settings.json#L36). Read by HRMS's `get_working_days_details` / `get_payment_days` (see [06-salary-slip.md](06-salary-slip.md)) and by our `warn_missing_attendance` ([`consider_unmarked_attendance_as`](../../avinashgroup_app/payroll/payroll_month.py#L108)) and `build_daily_breakdown` ([`consider_unmarked_attendance_as`](../../avinashgroup_app/payroll/daily_breakdown.py#L219)).

| Field | HRMS default | avinas1 | Set by | Effect / why |
|---|---|---|---|---|
| [`payroll_based_on`](../../../hrms/hrms/payroll/doctype/payroll_settings/payroll_settings.json#L36) | Leave | **Attendance** | patch `setup_payroll_based_on_attendance` ([`execute`](../../avinashgroup_app/patches/setup_payroll_based_on_attendance.py#L23)) | With "Leave" only an approved Leave Application cut pay, so the "> 2 h late = half day" rule (policy 1.2) and "absent is absent" cost nothing. Patch docstring: one nepalgas employee with 22 half days and 2 absences was paid 31/31 days; with Attendance he is paid 18. |
| [`daily_wages_fraction_for_half_day`](../../../hrms/hrms/payroll/doctype/payroll_settings/payroll_settings.json#L63) | 0.5 | 0.5 | same patch (pins it) | A half-absent day costs half a day. |
| [`include_holidays_in_total_working_days`](../../../hrms/hrms/payroll/doctype/payroll_settings/payroll_settings.json#L49) | **0** | **1** | **Desk only — no patch or fixture sets it** | Holidays are paid days. The BS slip then replaces total working days with the BS month length anyway ([`get_working_days_details`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py#L122)). A fresh site would get 0. |
| [`consider_unmarked_attendance_as`](../../../hrms/hrms/payroll/doctype/payroll_settings/payroll_settings.json#L92) | (blank) | **Present** | Desk only | A day with no Attendance is paid. Only marked Absent / half-absent days cut pay. Our `warn_missing_attendance` ([`consider_unmarked_attendance_as`](../../avinashgroup_app/payroll/payroll_month.py#L108)) treats a blank as "Absent". |
| [`consider_marked_attendance_on_holidays`](../../../hrms/hrms/payroll/doctype/payroll_settings/payroll_settings.json#L150) | 0 | 0 | default | An Absent row on a holiday is not deducted. |
| [`process_payroll_accounting_entry_based_on_employee`](../../../hrms/hrms/payroll/doctype/payroll_settings/payroll_settings.json#L106) | 0 | 0 | default | The payable side of the accrual journal is one line, not per employee. |
| [`email_template`](../../../hrms/hrms/payroll/doctype/payroll_settings/payroll_settings.json#L171) | – | `Salary Slip (BS)` | patch `setup_hr_bs_dates` ([`execute`](../../avinashgroup_app/patches/setup_hr_bs_dates.py#L31)) (only if blank) | BS payslip mail; `email_salary_slip_to_employee` = 1, `show_leave_balances_in_salary_slip` = 0, `disable_rounded_total` = 0. |

**Impacts downstream.** Changing `payroll_based_on` back to Leave silently makes the late-half-day rule and absences free. Changing `consider_unmarked_attendance_as` to Absent makes every day without an Attendance row unpaid; with auto attendance off on avinas1 (see [02-checkin-to-attendance.md](02-checkin-to-attendance.md)) that would cut most of a month.

**Gotcha.** Two of the five values that shape pay (`include_holidays…`, `consider_unmarked…`) exist only as site data. Rebuilding a site from patches gives different payment days.

## 2. Nepal HRMS Settings (rdp_common_app single doctype)

**What.** The switch for the BS-month payroll engine — the `BSSalarySlip` class override registered by `rdp_common_app` ([`BSSalarySlip`](../../../rdp_common_app/rdp_common_app/hooks.py#L149) in its hooks). `nepal_hrms` (in `apps/`) is **not installed on avinas1**; the settings doctype used here is `rdp_common_app/nepal_hrms_common`.

| Field | avinas1 | Read by | Effect |
|---|---|---|---|
| [`process_payroll_in_nepali_month`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/doctype/nepal_hrms_settings/nepal_hrms_settings.json#L23) | 1 | [`is_bs_payroll_enabled`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/doctype/nepal_hrms_settings/nepal_hrms_settings.py#L31) → every `BSSalarySlip` method ([`get_date_details`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py#L60), [`get_amount_based_on_payment_days`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py#L191), [`compute_current_and_future_taxable_earnings`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/payroll/salary_slip_bs.py#L225)); our [`validate_payroll_entry`](../../avinashgroup_app/payroll/bs_period_guard.py#L45) | Slips cover one BS month; proration denominator = BS month length; tax spread over remaining BS months. Off = stock AD-month HRMS. |
| [`restrict_to_nepal_companies`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/doctype/nepal_hrms_settings/nepal_hrms_settings.json#L30) | 1 | same | Only companies whose `country` is Nepal use the BS engine. All seven are Nepal. |

**Set by.** [`ensure_nepali_payroll`](../../avinashgroup_app/hr/year_setup.py#L201) (called by `setup_year`) turns it on if off. **Nepal BS Period** records: 0 on avinas1, so `get_date_details` always falls back to the calendar computation (see [06-salary-slip.md](06-salary-slip.md)).

## 3. Payroll Period

**What.** HRMS's tax year: the window the annual tax projection is spread over ([`get_payroll_period`](../../../hrms/hrms/payroll/doctype/payroll_period/payroll_period.py#L86)). Without one, HRMS computes no income tax at all.
**Why.** `setup_income_tax` ([`execute`](../../avinashgroup_app/patches/setup_income_tax.py#L27)) docstring: "Nothing about tax computes until three records exist — a Payroll Period, an Income Tax Slab, and a deduction component flagged `variable_based_on_taxable_salary`… which is why every slip so far has deducted only SSF."
**Created by.** [`ensure_payroll_period`](../../avinashgroup_app/hr/year_setup.py#L335) in `setup_year` (named `<FY> - <ABBR>`, dates = the Fiscal Year's), earlier by the patch's own [`ensure_payroll_period`](../../avinashgroup_app/patches/setup_income_tax.py#L115).

| Name | Company | Start | End |
|---|---|---|---|
| 83/84 - NGI / NGG / NGK / NGN / GLMI / GEPL / SGU | each of the 7 | 2026-07-17 (1 Shrawan 2083) | 2027-07-16 |

**Impacts.** The BS slip computes the remaining months from the period's end date. Tax Exemption Declarations and Proofs are filed against it. A missing period for a new year = no tax deducted, silently.

## 4. Income Tax Slab

**What.** The Finance Act tax table. HRMS reads it from the **assignment's** `income_tax_slab` ([`get_income_tax_slabs`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1592)), not from the date, which is why every new year needs new assignments ([`roll_salary_assignments`](../../avinashgroup_app/payroll/year_rollover.py#L50), [08-changes-over-time.md](08-changes-over-time.md)).

**Rows on avinas1** (identical on all seven `Nepal 83/84 - <ABBR>` slabs, submitted, effective 2026-07-17, `allow_tax_exemption` 1, standard exemption 0, `custom_women_rebate_percent` **10**):

| # | From | To | % | Condition |
|---|---|---|---|---|
| 1 | 0 | 10,00,000 | 1 | `not custom_ssf_applicable` |
| 2 | 10,00,001 | 15,00,000 | 10 | |
| 3 | 15,00,001 | 25,00,000 | 20 | |
| 4 | 25,00,001 | 40,00,000 | 27 | |
| 5 | 40,00,001 | (no ceiling) | 29 | |

**Why the condition on row 1.** The first band is the 1 % Social Security Tax (the "SST" column on the client's sheet), waived for SSF contributors (income_tax.py docstring ([`Income tax`](../../avinashgroup_app/payroll/income_tax.py#L1))): Falgun 2082 shows SST on exactly the four NGI staff without SSF. So SST is not a component; HRMS skips a slab row whose condition is false ([`calculate_tax_by_tax_slab`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L2199), [`eval_tax_slab_condition`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L2240)), and the assignment's fields — including `custom_ssf_applicable` — are in the eval scope because [`get_data_for_eval`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1215) merges [`_salary_structure_assignment`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1223) into it. The patch disables any old `SST` component.

**Where the rows come from.**
- [`FY_8384_SLABS`](../../avinashgroup_app/payroll/income_tax.py#L31) and [`TAX_SLABS_BY_YEAR`](../../avinashgroup_app/payroll/income_tax.py#L45) — the seed table, keyed by fiscal year.
- [`ensure_income_tax_slab`](../../avinashgroup_app/hr/year_setup.py#L355): builds and submits `Nepal <FY> - <ABBR>` from that table unless a submitted slab effective on the year's first day already exists (a desk-entered slab wins).
- [`require_tax_table`](../../avinashgroup_app/hr/year_setup.py#L167): refuses `setup_year` when the year is neither in the table nor entered by hand. "Last year's rates are never copied."
- [`tax_slab_for`](../../avinashgroup_app/payroll/year_rollover.py#L35): which slab a new assignment points at.

**Custom field** `custom_women_rebate_percent` (Percent, allowed on submit) — created by `setup_tax_exemptions` ([`custom_women_rebate_percent`](../../avinashgroup_app/patches/setup_tax_exemptions.py#L43)), its default removed by `tax_relief_fields_without_defaults` ([`execute`](../../avinashgroup_app/patches/tax_relief_fields_without_defaults.py#L19)), re-asserted by `women_rebate_on_employee` ([`custom_women_rebate_percent`](../../avinashgroup_app/patches/women_rebate_on_employee.py#L33)). Read only by [`women_rebate_fraction`](../../avinashgroup_app/payroll/tax_relief.py#L182), and only for a Female employee with `custom_womens_tax_rebate` ticked (validated by [`validate_womens_tax_rebate`](../../avinashgroup_app/payroll/tax_relief.py#L195), hooked at [`validate_womens_tax_rebate`](../../avinashgroup_app/hooks.py#L349)). On avinas1 nobody is ticked yet, so the 10 % has no effect today ([user guide 8.6](../user-guide/08-raises-advances-bonuses-year-end.md)).

**Gotchas.**
- `ensure_income_tax_slab` writes `custom_women_rebate_percent` from [`WOMEN_REBATE_BY_YEAR`](../../avinashgroup_app/payroll/income_tax.py#L54) (added 2026-10-12), and `require_tax_table` refuses a year whose rates are entered without it.
- `TAX_SLABS_BY_YEAR` has only `83/84`. Before Shrawan 2084, either add `84/85` or submit the slabs by hand, or `setup_year('84/85')` refuses to run.
- HRMS's [`validate_income_tax_slab`](../../../hrms/hrms/payroll/doctype/salary_structure_assignment/salary_structure_assignment.py#L73) makes the slab mandatory on an assignment whose structure has a tax component — every structure here has one.

## 5. Employee Tax Exemption Categories and Sub-categories

**What.** Stock HRMS: declared exemptions (insurance, CIT, PF) reduce taxable income via Employee Tax Exemption Declaration / Proof Submission. This app adds the **s.63 retirement cap** (SSF + CIT + PF together capped at the lower of an amount and a % of assessable income), which HRMS cannot express.
**Why.** `setup_tax_exemptions` ([`execute`](../../avinashgroup_app/patches/setup_tax_exemptions.py#L34)) docstring: fields only, no figures — "a number put in by code looks deliberate and is only found wrong in somebody's pay". Until 2026-09-29 the patch seeded Finance Act figures and the cap lived in code; the user removed them.

| Category | Max amount | `custom_is_retirement_contribution` | `custom_cap_percent_of_income` | Sub-categories (max) |
|---|---|---|---|---|
| Insurance Premium | 70,000 | 0 | 0 | Life Insurance 40,000 · Health Insurance 20,000 · Private Building Insurance 10,000 |
| Retirement Contribution | 5,00,000 | **1** | **33.333333** | CIT paid directly 5,00,000 · Provident Fund paid directly 5,00,000 |

Insurance's 70,000 is the three sub-limits added, so it never binds ([user guide 8.6](../user-guide/08-raises-advances-bonuses-year-end.md), commit `4d6af9a`).

**Read by.** [`retirement_categories`](../../avinashgroup_app/payroll/tax_relief.py#L57) → [`retirement_cap`](../../avinashgroup_app/payroll/tax_relief.py#L66) (lower of `max_amount` and % of assessable income) → [`retirement_excess`](../../avinashgroup_app/payroll/tax_relief.py#L124) (adds the excess back to taxable income) inside [`apply_tax_reliefs`](../../avinashgroup_app/payroll/tax_relief.py#L77). Declared CIT/PF: [`declared_retirement`](../../avinashgroup_app/payroll/tax_relief.py#L163). Detail in [06-salary-slip.md](06-salary-slip.md).

**Config on avinas1.** 0 Employee Tax Exemption Declarations, 0 Proof Submissions. So only the SSF deduction itself (component flagged `exempted_from_income_tax`) reduces taxable income today.

**Gotchas.** The cap is 33.333333 %, not exactly ⅓ (a rupee or so at high incomes). Untick the category's `custom_is_retirement_contribution` and the cap silently disappears — no error.

## 6. Salary Components

### 6.1 The components on avinas1

`al` = `custom_is_allowance`, `att` = `custom_is_attendance_driven`. Flags are HRMS's own fields.

| Component | Abbr | Type | Allowance kind | att | HRMS flags | Group |
|---|---|---|---|---|---|---|
| Basic | B | Earning | – | 0 | taxable, payment-days | |
| SSF Addition | SSFA | Earning | – | 0 | taxable | |
| Dearness Allowance | DA | Earning | Monthly | 0 | taxable, payment-days | |
| Other Allowance | OA | Earning | Monthly | 0 | taxable, payment-days | |
| Fixed Allowance | FA | Earning | Monthly | 0 | taxable, payment-days | |
| Fuel Allowance | FUEL | Earning | Monthly | 0 | taxable, payment-days | |
| Maintenance Allowance | MNT | Earning | Monthly | 0 | taxable, payment-days | |
| Gas Allowance | GAS | Earning | Monthly | 0 | taxable, payment-days | |
| Education Allowance | EDU | Earning | Monthly | 0 | taxable, payment-days | |
| Transport Allowance | TA | Earning | Monthly | 0 | taxable, payment-days | |
| House Rent Allowance | HRA | Earning | % of Initial Basic | 0 | taxable, payment-days | |
| Tea & Conveyance | TEA | Earning | Per Day Present | 1 | taxable | Tea |
| Meal | MEAL | Earning | Per Meal | 1 | taxable | Meal |
| Overtime | OT | Earning | Per Overtime Hour | 1 | taxable | (blank) |
| Load/Unload Allowance | LU | Earning | Entered by Hand | 0 | taxable, **payment-days** | |
| Dashain Allowance | DSA | Earning | Yearly | 0 | taxable; **Festival Allowance** ✓ (pay month Ashwin) | |
| Dashain Bonus | DB | Earning | Yearly | 0 | taxable, round; not used by the Dashain button | |
| Leave Encashment | LE | Earning | Yearly | 0 | taxable (payment-days off since 2026-10-13) | |
| Salary Arrears | ARR | Earning | – | 0 | taxable, round | |
| Arrear · Grade Amount · Daily Wage | A · GR · DW | Earning | – | (DW 1) | **disabled** | |
| SSF | SSF | Deduction | – | 0 | exempt-from-tax | |
| Income Tax | IT | Deduction | – | 0 | tax-slab (`variable_based_on_taxable_salary`), is-income-tax-component, round | |
| Late Fine | LF | Deduction | – | 1 | – | Late Fine |
| Salary Advance | ADV | Deduction | – | 0 | – | |
| Professional Tax · Provident Fund | PT · PF | Deduction | – | 0 | (HRMS-shipped, unused by any structure) | |

Every component has `remove_if_zero_valued` = 1. All earnings are `is_tax_applicable` = 1, forced by [`set_component_flags`](../../avinashgroup_app/patches/setup_income_tax.py#L87), which also set Income Tax's flags and SSF's `exempted_from_income_tax`.

### 6.2 Our custom fields on Salary Component

| Field | Options / type | Created by | Read by | Meaning |
|---|---|---|---|---|
| `custom_is_allowance` | Check | `setup_allowance_kinds` ([`custom_is_allowance`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L141)) | [`validate_salary_structure`](../../avinashgroup_app/payroll/allowance.py#L419), [`_check_allowance_row`](../../avinashgroup_app/payroll/allowance.py#L393), [`_gets`](../../avinashgroup_app/payroll/attendance_allowance.py#L608), JS filters | Paid from the assignment's Allowances; refused in structure Earnings |
| `custom_allowance_kind` | Monthly · % of Initial Basic · Per Day Present · Per Meal · Per Overtime Hour · Entered by Hand · Yearly ([`ALLOWANCE_KINDS`](../../avinashgroup_app/payroll/allowance.py#L62)) | `setup_allowance_kinds` ([`custom_allowance_kind`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L148)), renamed by [`rename_kinds`](../../avinashgroup_app/patches/allowance_rate_list.py#L132) | [`validate_salary_component`](../../avinashgroup_app/payroll/allowance.py#L357), [`fixed_allowance_amounts`](../../avinashgroup_app/payroll/allowance.py#L321), [`add_employee_allowances`](../../avinashgroup_app/payroll/salary_slip.py#L33), [`unit_for`](../../avinashgroup_app/payroll/allowance.py#L180) | How it is counted: [`FIXED_KINDS`](../../avinashgroup_app/payroll/allowance.py#L72) go on the slip directly; [`ATTENDANCE_KIND_CONDITION`](../../avinashgroup_app/payroll/allowance.py#L74) kinds go through Prepare Payroll Inputs; [`NOT_ON_ASSIGNMENT`](../../avinashgroup_app/payroll/allowance.py#L80) kinds only via Additional Salary |
| `custom_is_attendance_driven` | Check | `setup_attendance_allowance` ([`custom_is_attendance_driven`](../../avinashgroup_app/patches/setup_attendance_allowance.py#L16)) | [`get_attendance_driven_components`](../../avinashgroup_app/payroll/attendance_allowance.py#L568), [`validate_salary_structure`](../../avinashgroup_app/payroll/allowance.py#L419) | Priced by the attendance engine ([05-payroll-entry.md](05-payroll-entry.md)) |
| `custom_condition_type` | Status = Present · Status = Half Day · Worked on Holiday · Meal Entitlement · Early Entry Before · Late Stay After · Late Arrival After · Authorised Overtime · Late Time | `setup_attendance_allowance` ([`custom_condition_type`](../../avinashgroup_app/patches/setup_attendance_allowance.py#L27)), options extended by [`add_conditions`](../../avinashgroup_app/patches/setup_overtime_and_late_fine.py#L88) | [`evaluate_rule`](../../avinashgroup_app/payroll/attendance_allowance.py#L250), [`_skip_for_eligibility`](../../avinashgroup_app/payroll/attendance_allowance.py#L544) | Which daily rule counts the quantity |
| `custom_unit` | Per Day · Per Hour · Flat per Period | `setup_attendance_allowance` ([`custom_unit`](../../avinashgroup_app/patches/setup_attendance_allowance.py#L63)) | [`_qty_for_employee`](../../avinashgroup_app/payroll/attendance_allowance.py#L232), [`evaluate_rule`](../../avinashgroup_app/payroll/attendance_allowance.py#L250), daily breakdown | Unit of the quantity |
| `custom_time_offset_hours` | Float | `setup_attendance_allowance` ([`custom_time_offset_hours`](../../avinashgroup_app/patches/setup_attendance_allowance.py#L49)) | `evaluate_rule` ([`custom_time_offset_hours`](../../avinashgroup_app/payroll/attendance_allowance.py#L317)), [`_meals_for_day`](../../avinashgroup_app/payroll/attendance_allowance.py#L331) | Early/late hours needed (meal 1.5) |
| `custom_summary_group` | Data | `setup_attendance_allowance` ([`custom_summary_group`](../../avinashgroup_app/patches/setup_attendance_allowance.py#L83)) | [`custom_summary_group`](../../avinashgroup_app/avinash_group_app/report/monthly_attendance_bs/summary.py#L63) (Monthly Attendance BS summary view only) | Column grouping in the report; no pay effect |
| `custom_half_day_counts` | Full Day · Half Day · Not At All | `setup_half_day_allowance_rule` ([`custom_half_day_counts`](../../avinashgroup_app/patches/setup_half_day_allowance_rule.py#L21)) | `evaluate_rule` ([`custom_half_day_counts`](../../avinashgroup_app/payroll/attendance_allowance.py#L273)) | Client 2026-09-21: "if a person comes then they are eligible" — tea for a half day is full |
| `custom_pay_on_holiday` | Pay · Do Not Pay | `setup_pay_on_holiday_field` ([`custom_pay_on_holiday`](../../avinashgroup_app/patches/setup_pay_on_holiday_field.py#L28)) | `evaluate_rule` ([`custom_pay_on_holiday`](../../avinashgroup_app/payroll/attendance_allowance.py#L262)) | The sheet never paid tea on a worked holiday |
| `custom_max_per_day` | Int | `setup_meal_rule_fields` ([`custom_max_per_day`](../../avinashgroup_app/patches/setup_meal_rule_fields.py#L44)) | `_meals_for_day` ([`custom_max_per_day`](../../avinashgroup_app/payroll/attendance_allowance.py#L364)) | Meal cap (policy 1.3/2.3: never more than 2) |
| `custom_rate_basis` | Fixed Rate · Hourly Basic × Multiplier ([`COMPUTED_RATE_BASIS`](../../avinashgroup_app/payroll/allowance.py#L90)) | `setup_overtime_and_late_fine` ([`custom_rate_basis`](../../avinashgroup_app/patches/setup_overtime_and_late_fine.py#L37)) | [`_resolve_rate`](../../avinashgroup_app/payroll/attendance_allowance.py#L620), [`rate_is_computed`](../../avinashgroup_app/payroll/allowance.py#L175) | OT and late fine follow the person's basic, so a raise moves them |
| `custom_rate_multiplier` | Float | `setup_overtime_and_late_fine` ([`custom_rate_multiplier`](../../avinashgroup_app/patches/setup_overtime_and_late_fine.py#L47)) | [`_resolve_rate`](../../avinashgroup_app/payroll/attendance_allowance.py#L620) | OT 1.5, fine 1 |
| `custom_rate_days_per_month` | Float (blank = BS month's actual days) | `setup_ot_rate_fields` ([`custom_rate_days_per_month`](../../avinashgroup_app/patches/setup_ot_rate_fields.py#L29)), seed cleared by `rate_on_actual_month_days` ([`execute`](../../avinashgroup_app/patches/rate_on_actual_month_days.py#L17)) | `_hourly_basic` ([`custom_rate_days_per_month`](../../avinashgroup_app/payroll/attendance_allowance.py#L453)) | User decision 2026-10-12: hourly wage on the real month (29–32), not the sheet's 30 |
| `custom_rate_hours_per_day` | Float (blank = 8) | `setup_ot_rate_fields` ([`custom_rate_hours_per_day`](../../avinashgroup_app/patches/setup_ot_rate_fields.py#L37)) | `_hourly_basic` ([`custom_rate_hours_per_day`](../../avinashgroup_app/payroll/attendance_allowance.py#L456)) | Labour Act 8-hour day |
| `custom_attendance_month` | Same as Salary · Previous Month | `setup_allowance_kinds` ([`custom_attendance_month`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L165)) | [`_attendance_period`](../../avinashgroup_app/payroll/attendance_allowance.py#L557) | For a component whose attendance closes a month behind |
| `custom_ot_eligible_only` | Check | `setup_allowance_kinds` ([`custom_ot_eligible_only`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L175)) | [`_skip_for_eligibility`](../../avinashgroup_app/payroll/attendance_allowance.py#L544) | Policy 2.2: OT money and meals only for OT-eligible staff |

### 6.3 Rule settings of the attendance-driven components (avinas1)

| Component | Condition | Unit | Rate basis | Mult. | Days/month | Hours/day | Pay on holiday | Half day counts | Offset h | Max/day | OT-only | Month |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tea & Conveyance | Status = Present | Per Day | Fixed Rate | – | – | – | **Do Not Pay** | Full Day | 0 | 0 | 0 | Same |
| Meal | Meal Entitlement | Per Day | Fixed Rate | – | – | – | Pay | Full Day | **1.5** | **2** | **1** | Same |
| Overtime | Authorised Overtime | Per Hour | Hourly Basic × Multiplier | **1.5** | blank (= BS month days) | **8** | Pay | Full Day | 0 | 0 | **1** | Same |
| Late Fine | Late Time | Per Hour | Hourly Basic × Multiplier | **1** | blank | blank (= 8) | Pay | Full Day | 0 | 0 | 0 | Same |
| Daily Wage (disabled) | Status = Present | Per Day | Fixed Rate | 0 | – | – | Pay | Half Day | 0 | 0 | 0 | Same |

The non-attendance allowances also carry `custom_unit` = Per Day and `custom_rate_multiplier` = 1 — field defaults, never read for them.

### 6.4 `validate_salary_component` (hook)

- **What.** [`validate_salary_component`](../../avinashgroup_app/payroll/allowance.py#L357): (1) an S/D or F/P account on an Accounts row must belong to that row's company; (2) an allowance must have a kind; an attendance kind (Per Day Present / Per Meal / Per Overtime Hour) **forces** `custom_is_attendance_driven` = 1 and the matching `custom_condition_type` (Per Overtime Hour also forces `custom_unit` = Per Hour); any other kind forces attendance-driven off; a non-allowance has its kind cleared; (3) every attendance-driven component gets `depends_on_payment_days` = 0 and `remove_if_zero_valued` = 1.
- **Why.** "Counted on the days worked, so not cut again for absences; and paid only through Additional Salary, so a 0 must not print on the slip."
- **Triggered by.** [`validate_salary_component`](../../avinashgroup_app/hooks.py#L472) (Salary Component validate).
- **Impacts.** Changing an allowance's kind from Monthly to Per Day Present moves it from the slip hook to Prepare Payroll Inputs and switches off proration. You cannot hand-set a Per Meal allowance to a non-meal condition: save resets it.

### 6.5 Accounts per company: O/O · S/D · F/P

- **What.** Stock HRMS: Salary Component Account (`company`, `account`). We add `custom_account_marketing` (S/D) and `custom_account_plant` (F/P) (`setup_allowance_kinds` ([`custom_account_marketing`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L185)), [`custom_account_plant`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L193)); the stock `account` is the O/O (Admin & Accounts) one. The mapping is [`SECTION_ACCOUNT_FIELD`](../../avinashgroup_app/payroll/allowance.py#L93).
- **Why.** The chart keeps every staff cost three ways — 547101 O/O office, 547102 S/D sales & distribution, 547103 F/P filling plant — the way NGI's Falgun sheet charges departments (allowance.py docstring ([`Allowances`](../../avinashgroup_app/payroll/allowance.py#L1)), [user guide ch. 9](../user-guide/09-accounts-setup.md)).
- **Read by.** [`get_account_row`](../../avinashgroup_app/payroll/allowance.py#L112), [`section_account`](../../avinashgroup_app/payroll/allowance.py#L129) (blank S/D or F/P falls back to O/O), [`has_section_accounts`](../../avinashgroup_app/payroll/allowance.py#L138); used by our Payroll Entry override [`section_for`](../../avinashgroup_app/payroll/payroll_entry.py#L124) / [`get_account`](../../avinashgroup_app/payroll/payroll_entry.py#L133) when the accrual journal is built ([07-after-the-slip.md](07-after-the-slip.md)). [`sibling_account`](../../avinashgroup_app/payroll/allowance.py#L143) finds the S/D / F/P twin of an O/O account by name.
- **Set up by.** [`map_component_accounts`](../../avinashgroup_app/payroll/onboarding.py#L663) using [`PROPOSED_ACCOUNTS`](../../avinashgroup_app/payroll/onboarding.py#L652) — every earning and the Late Fine to 547101/2/3 Salary Expenses; SSF → 347302 SSF Payable; Income Tax → 348102 TDS-Remuneration; Salary Advance → 148003 Staff Advance.

**Config on avinas1.**

| Company | Component accounts |
|---|---|
| NGI | All 22 active pay components mapped; earnings + Late Fine with all three section accounts; SSF / Income Tax / Salary Advance O/O only |
| NGN | 10 components, **O/O only** (no S/D, F/P); Meal and Tea rows have **no account** |
| NGG | Only a Meal row, with **no account** |
| NGK, GLMI, GEPL, SGU | none |

**Gotchas.**
- **NGG (27 assigned staff) and NGK (18) cannot post a payroll journal today**: HRMS throws "set account in Salary Component" for every unmapped component. NGN's Tea and Meal likewise. No NGG/NGK slips exist yet; the first run will hit it.
- The Late Fine (a deduction) posts to the **salary expense** account, reducing salary cost — deliberate ("No fines-income account exists").
- `insert_after` of `custom_max_per_day` points at `custom_holiday_hours_two_meals`, a field `meal_on_authorised_overtime` ([`execute`](../../avinashgroup_app/patches/meal_on_authorised_overtime.py#L17)) removed; harmless (the field renders at the section end).

## 7. Department → payroll section

- **What.** `Department.custom_payroll_section` (Admin & Accounts · Marketing · Plant), created by `setup_allowance_kinds` ([`custom_payroll_section`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L211)) and seeded by name ([`section_for_department`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L267): "Plant…" → Plant, "Sales…/Marketing…" → Marketing, rest → Admin & Accounts).
- **Read by.** [`get_section`](../../avinashgroup_app/payroll/allowance.py#L161) (Employee → Department → section, cached per request) → [`get_salary_component_total`](../../avinashgroup_app/payroll/payroll_entry.py#L76), which **throws** listing employees with no section whenever a component has S/D or F/P accounts.
- **Config on avinas1** (salaried staff with a submitted assignment): NGI 87 / 0 without section, NGN 63 / 0, NGK 18 / 0, **NGG 27 / 27 without section** (NGG has no section accounts yet, so it does not throw on this today; it will once accounts are mapped).
- **Impacts.** Moving an employee to another Department moves next month's cost to another account. Blanking a department's section stops the whole company's journal.

## 8. Salary Structures

**What.** One per paying company, built from the company's Falgun 2082 sheet by [`setup_company`](../../avinashgroup_app/payroll/onboarding.py#L224) / [`structure_rows`](../../avinashgroup_app/payroll/onboarding.py#L187) / [`structure_rates`](../../avinashgroup_app/payroll/onboarding.py#L213). All submitted, active, Monthly, NPR, `payment_account` = the company's 347301 Salary Payable.

| Structure | Company |
|---|---|
| NGI Staff 83/84 | Nepal Gas Udhyog |
| NGN Staff 83/84 | Narayani |
| NGG Staff 83/84 | Gandaki |
| NGK Staff 83/84 | Karnali |

GLMI, GEPL and SGU have no structure and no active employees.

**Earnings / Deductions (identical in all four):**

| Table | Component | Formula | Payment days |
|---|---|---|---|
| Earnings | Basic (B) | `base` | yes |
| Earnings | SSF Addition (SSFA) | `B * 0.20 if custom_ssf_applicable else 0` | no |
| Deductions | SSF | `B * 0.31 if custom_ssf_applicable else 0` | no |
| Deductions | Late Fine (LF) | (blank — a tag) | no |
| Deductions | Income Tax (IT) | (slab) | no |

**Why SSF is 20 % / 31 %.** The Social Security Fund takes 31 % of basic: 20 % paid by the employer (shown as the SSF Addition earning) and 11 % by the employee, all deducted as one SSF line ([payroll-ngi.md](../payroll-ngi.md), `setup_payroll_employee_fields` ([`execute`](../../avinashgroup_app/patches/setup_payroll_employee_fields.py#L22)) docstring). SSF reads `B`, which is already prorated, so the SSF rows are not payment-days rows ([`structure_rows`](../../avinashgroup_app/payroll/onboarding.py#L187) docstring). `custom_ssf_applicable` comes from the assignment (HRMS puts assignment fields in formula scope).

**Allowance Rates** (`custom_allowance_rates`, child **Structure Allowance Rate**: [`allowance`](../../avinashgroup_app/avinash_group_app/doctype/structure_allowance_rate/structure_allowance_rate.json#L14), [`rate`](../../avinashgroup_app/avinash_group_app/doctype/structure_allowance_rate/structure_allowance_rate.json#L24), [`unit`](../../avinashgroup_app/avinash_group_app/doctype/structure_allowance_rate/structure_allowance_rate.json#L33)) — added by `allowance_rate_list` ([`execute`](../../avinashgroup_app/patches/allowance_rate_list.py#L50)):

| Structure | Rates listed |
|---|---|
| NGI | Meal 75/meal · Tea & Conveyance 235/day · Overtime (from basic × 1.5) · Dearness 0 · Education 2,780/mo · Gas 1,690/mo · HRA 25 % of initial basic · Other 0 |
| NGN | Tea 265/day · Meal 75 · Overtime · Dearness 0 · Education 1,250 · Gas 1,690.27 · HRA 27 % · Other 0 |
| NGG | Overtime · Meal 100 · Dearness 0 · Fixed 0 · Other 0 |
| NGK | Overtime · Dearness 0 · Fixed 0 · Fuel 0 · Maintenance 0 · Other 0 |

A rate of 0 means "per person, no usual rate" (dearness, other, fixed…). Overtime is listed only so it can be picked; its rate is always computed.

**Hooks.**
- [`validate_salary_structure`](../../avinashgroup_app/payroll/allowance.py#L419) (hook [`validate_salary_structure`](../../avinashgroup_app/hooks.py#L482)): refuses an allowance in Earnings/Deductions ("would be paid to everyone on the structure, whatever their assignment says"); blanks amount/formula/condition of attendance-driven rows (the Late Fine tag); checks each Allowance Rates row via [`_check_listed_once`](../../avinashgroup_app/payroll/allowance.py#L411) and [`_check_allowance_row`](../../avinashgroup_app/payroll/allowance.py#L393) (an allowance, not Entered by Hand / Yearly, rate ≥ 0, computed-rate rows forced to 0, unit filled).
- [`guard_structure_rates`](../../avinashgroup_app/payroll/allowance.py#L448) (hook [`guard_structure_rates`](../../avinashgroup_app/hooks.py#L483), `before_update_after_submit`): on a submitted structure, adding/removing a rate row is allowed, **changing a listed rate is refused** unless `frappe.flags.in_salary_revision` — "a later raise would then find nobody at the structure's rate". See Salary Revision in [08-changes-over-time.md](08-changes-over-time.md).
- Form script [`salary_structure.js`](../../avinashgroup_app/hooks.py#L110) → [`custom_allowance_rates`](../../avinashgroup_app/public/js/salary_structure.js#L7): the picker offers enabled allowances that are not Entered by Hand / Yearly.

**Impacts downstream.**
- The Late Fine row is how a non-allowance attendance component is "given" to a person: [`_gets`](../../avinashgroup_app/payroll/attendance_allowance.py#L608) pays the late fine only if the structure lists it ([`structure_components`](../../avinashgroup_app/payroll/allowance.py#L296)). Remove that row and nobody on the structure is fined.
- Editing a structure formula changes every slip on it; HRMS keeps the structure editable only via amend.
- Structure Allowance Rates feed only the form ([`get_structure_allowances`](../../avinashgroup_app/payroll/allowance.py#L219), [`get_rate_for_assignment`](../../avinashgroup_app/payroll/allowance.py#L209)), [`validate_assignment_allowances`](../../avinashgroup_app/payroll/allowance.py#L474) (blank row rate) and Salary Revision. **Payroll never reads them.**

**Gotchas.**
- `Salary Structure.custom_daily_wage` (created by `setup_daily_wage` ([`custom_daily_wage`](../../avinashgroup_app/patches/setup_daily_wage.py#L24))) is **read by no code**. Daily-wage labour is paid in cash outside payroll (decided 2026-10-08, [`_hourly_basic`](../../avinashgroup_app/payroll/attendance_allowance.py#L440) docstring); [`retire_daily_wage`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L306) disabled the component and dropped the "Daily Wage" rate basis. The checkbox is dead; [payroll-ngi.md](../payroll-ngi.md) still lists Daily Wage as a paid component.
- [`COMPONENTS`](../../avinashgroup_app/payroll/onboarding.py#L124) gives Income Tax abbr `TAX`; the site has `IT` (made earlier by `setup_income_tax`). `ensure_components` only creates missing components, so no conflict — but a fresh site onboarded before `setup_income_tax` would get `TAX`.

## 9. Salary Structure Assignment (the person's pay)

**What.** Stock HRMS: employee, structure, `from_date`, `base`, `variable`, `income_tax_slab`, payroll payable account, cost centres. We add (`move_pay_to_salary_assignment` ([`execute`](../../avinashgroup_app/patches/move_pay_to_salary_assignment.py#L62))):

| Field | Created at | Meaning | Read by |
|---|---|---|---|
| `base` (stock) | – | Monthly basic | Structure formula `base`; [`_hourly_basic`](../../avinashgroup_app/payroll/attendance_allowance.py#L440) (OT, late fine) |
| `custom_initial_basic` | [`custom_initial_basic`](../../avinashgroup_app/patches/move_pay_to_salary_assignment.py#L86) | The sheet's separate "initial basic" HRA is a % of; cannot be derived from base | [`fixed_allowance_amounts`](../../avinashgroup_app/payroll/allowance.py#L321) |
| `custom_ssf_applicable` | [`custom_ssf_applicable`](../../avinashgroup_app/patches/move_pay_to_salary_assignment.py#L98) | In the SSF scheme | SSF/SSFA formulas; slab row 1 condition (SST waiver) |
| `custom_allowances` (table **Assignment Allowance**) | [`custom_allowances`](../../avinashgroup_app/patches/move_pay_to_salary_assignment.py#L112) | Which allowances, at what rate | [`get_employee_allowance_rows`](../../avinashgroup_app/payroll/allowance.py#L274), [`allowance_rate`](../../avinashgroup_app/payroll/allowance.py#L341) |
| `income_tax_slab` (stock) | – | The year's slab | HRMS tax ([`get_income_tax_slabs`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1592)) |

**Assignment Allowance** child fields: [`allowance`](../../avinashgroup_app/avinash_group_app/doctype/assignment_allowance/assignment_allowance.json#L15), [`rate`](../../avinashgroup_app/avinash_group_app/doctype/assignment_allowance/assignment_allowance.json#L24), [`unit`](../../avinashgroup_app/avinash_group_app/doctype/assignment_allowance/assignment_allowance.json#L32), [`effective_from`](../../avinashgroup_app/avinash_group_app/doctype/assignment_allowance/assignment_allowance.json#L41) (a row with a later date is not in force yet).

**Why on the assignment, not the Employee.** `move_pay_to_salary_assignment` ([`execute`](../../avinashgroup_app/patches/move_pay_to_salary_assignment.py#L62)) docstring: each allowance used to be its own Employee field read by a structure formula, so a new allowance meant a new field and a new structure, and "anyone who could edit an employee saw their pay". Now a person's pay is one dated record; a change is a new assignment from the first of a BS month (Salary Revision) and the old one stays as the record of what was paid.

**How each row is used.**
- Monthly / % of Initial Basic → [`fixed_allowance_amounts`](../../avinashgroup_app/payroll/allowance.py#L321) (HRA = `custom_initial_basic × rate / 100`) → [`add_employee_allowances`](../../avinashgroup_app/payroll/salary_slip.py#L33) on the slip, prorated by payment days ([06-salary-slip.md](06-salary-slip.md)).
- Per Day Present / Per Meal → rate × attendance count; Per Overtime Hour → rate computed from `base`, the row only says "gets OT" ([05-payroll-entry.md](05-payroll-entry.md)).
- Which assignment: [`current_assignment`](../../avinashgroup_app/payroll/allowance.py#L259) = latest submitted with `from_date` ≤ the date (the slip passes its **end date**).

**Hooks.**
- [`validate_assignment_allowances`](../../avinashgroup_app/payroll/allowance.py#L474) (hook [`validate_assignment_allowances`](../../avinashgroup_app/hooks.py#L484)): allowances only, each once, not Entered by Hand / Yearly; a blank rate takes the structure's ([`structure_rate`](../../avinashgroup_app/payroll/allowance.py#L195)); still 0 → refused ("no row means not paid"); computed-rate rows skip the check.
- Form script [`salary_structure_assignment.js`](../../avinashgroup_app/hooks.py#L110): picking an allowance calls [`get_rate_for_assignment`](../../avinashgroup_app/payroll/allowance.py#L209) and fills rate and unit; warns if no structure picked yet.
- Same script, on a draft (docstatus 0): picking or changing `salary_structure` calls [`get_structure_allowances`](../../avinashgroup_app/payroll/allowance.py#L219) and fills `custom_allowances` with one row per structure Allowance Rate (structure order, usual rate, 0 for computed; disabled and Entered by Hand / Yearly skipped). An empty table is filled at once; rows already there are replaced only after a `frappe.confirm`, and not at all when they already equal the structure's list. An alert names the rows left at 0 for HR to type or remove. Form only: no server hook fills an empty table, because Salary Revision ("Stop"), onboarding imports and scripts legitimately save assignments whose table is empty or partial (no row = not paid).
- HRMS's own [`validate_income_tax_slab`](../../../hrms/hrms/payroll/doctype/salary_structure_assignment/salary_structure_assignment.py#L73).

**Created by.** [`assign`](../../avinashgroup_app/payroll/onboarding.py#L473) via [`import_sheet`](../../avinashgroup_app/payroll/onboarding.py#L327) (onboarding, from the BS year's first day), Salary Revision (new dated assignment), [`roll_salary_assignments`](../../avinashgroup_app/payroll/year_rollover.py#L50) (new year), or by hand.

**Config on avinas1.**

| Company | Submitted | SSF applicable | With initial basic | Structure / slab |
|---|---|---|---|---|
| NGI | 87 | 83 | 87 | NGI Staff 83/84 / Nepal 83/84 - NGI |
| NGN | 63 | 53 | 63 | NGN / NGN |
| NGG | 27 | 27 | 0 | NGG / NGG |
| NGK | 18 (+1 cancelled) | 15 | 0 | NGK / NGK |

All from 2026-07-17. 195 people have an assignment; **70 active employees have none** (NGG 22, NGK 25, NGN 10, NGI 13) and so get no slip. Allowance rows in force: Overtime 195, Dearness 179, Meal 177, Tea 119 (rates 40–265), Other 88, Gas 77, HRA 74, Education 74, Fixed 37, Fuel 4, Maintenance 3. No row uses `effective_from`.

**Gotchas.**
- A mid-month change: the slip reads the assignment in force on its **end date** for allowances, while HRMS picks the structure assignment by its own rule ([06-salary-slip.md](06-salary-slip.md)). The house rule is to date revisions on the 1st of a BS month.
- `current_assignment` filters only `employee`, `docstatus`, `from_date` — not company or structure. An employee transferred between companies is read from whichever assignment is latest.

## 10. Payroll Adjustment

- **What.** [`PayrollAdjustment`](../../avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py#L28): one document per company and month, a row per employee × component; [`on_submit`](../../avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py#L81) creates and submits one Additional Salary per row with [`overwrite_salary_structure_amount`](../../avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py#L92) 0 and full tax in that month; [`on_cancel`](../../avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py#L111) cancels them.
- **Why.** NGI's Falgun sheet types one-off amounts (load/unload, bonus, SST, advance) as columns beside everyone's name; one Additional Salary each is "miserable for twenty". Installed by `setup_payroll_adjustment` ([`execute`](../../avinashgroup_app/patches/setup_payroll_adjustment.py#L6)).
- **Still read.** Linked from the HR dashboard ([`Payroll Adjustment`](../../avinashgroup_app/hr/hr_dashboard.py#L688)); onboarding names it as the place Load/Unload is paid. **0 documents on avinas1.**
- **Dashain.** The Payroll Entry's Dashain Allowance button writes a draft of it (`source`, `payroll_entry`, `cutoff_date`; rows carry `base_amount`, `service_days`, `year_days`, `prorate_factor`), and validate refuses a row above its `base_amount`. See [08-changes-over-time.md §5](08-changes-over-time.md#5-festival-allowance-dashain).
- **Gotcha (code reading, unverified on a real slip).** Load/Unload has `depends_on_payment_days` = 1 (Leave Encashment had it too, until 2026-10-13). An Additional Salary that does not overwrite has `default_amount` 0, so HRMS's [`get_amount_based_on_payment_days`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1795) (and the BS override) prorates it by payment days: someone with absences would receive less than the typed amount. Untick payment days on Load/Unload if that is not intended.

## 11. Removed or dead masters

| Item | Status | Evidence |
|---|---|---|
| Company Allowance, Company Allowance Item | **Deleted.** Never released; only `__pycache__` left in the repo; doctypes and tables dropped | [`remove_company_allowance`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L440) |
| Employee Attendance Allowance (Employee "Allowance Exceptions" table) | **Deleted.** Rows moved to Assignment Allowance; no DocType on avinas1; only `__pycache__` in repo | `move_pay_to_salary_assignment` ([`execute`](../../avinashgroup_app/patches/move_pay_to_salary_assignment.py#L62)) |
| Allowance Category (+ `Employee.custom_allowance_category`) | **Deleted**; patch kept as no-op | [`move_categories`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L363), [`remove_categories`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L388) |
| `Salary Component Account.custom_default_rate` | **Deleted** (rates moved to the structure) | [`remove_default_rate_field`](../../avinashgroup_app/patches/allowance_rate_list.py#L283) |
| Employee pay fields (`custom_dearness_allowance`, HRA/Gas/Education ticks, initial basic, SSF applicable…) | **Deleted** from Employee on avinas1 (only `custom_ssf_id_no` remains) | [`remove_old`](../../avinashgroup_app/patches/move_pay_to_salary_assignment.py#L255) |
| `Salary Structure.custom_daily_wage`, component Daily Wage | Field exists, **no reader**; component disabled | §8 gotcha |
| Components Arrear, Grade Amount | Disabled; Salary Arrears (ARR) is the live arrears line | DB |
| Professional Tax, Provident Fund | HRMS-shipped, on no structure | DB |

**Doc-vs-code contradictions.** [payroll-ngi.md](../payroll-ngi.md) still describes Employee fields `custom_dearness_allowance` etc. and an "Allowance Exceptions" table (its 2026-10-08 banner points at allowances.md but the banner itself names the superseded Exceptions table), and lists Daily Wage as paid. [allowances.md](../allowances.md) is current.

---

## Appendix: HR / payroll patches, in `patches.txt` order

Section `[pre_model_sync]` runs before doctype sync; the rest are `[post_model_sync]`. "Live?" = whether what it created is still read by code today.

| Patch | What it creates / changes | Why | Live? |
|---|---|---|---|
| `skip_broken_hrms_advance_ledger_patch` [`execute`](../../avinashgroup_app/patches/skip_broken_hrms_advance_ledger_patch.py#L23) | Runs HRMS's `update_advance_payment_ledger_amount` fix with qualified columns, then marks the HRMS patch done | The HRMS patch aborts every migrate here (ambiguous `amount` column, MariaDB 1052) | Yes (migrate safety) |
| `setup_attendance_allowance` [`execute`](../../avinashgroup_app/patches/setup_attendance_allowance.py#L5) | Attendance-Driven Rule section on Salary Component (`custom_is_attendance_driven`, condition, offset, unit, default rate, summary group); `Attendance.custom_worked_on_holiday`; `Employee.custom_ot_eligibility`; Employee allowance table; `Additional Salary.custom_source` | First version of the attendance engine (no docstring; from the biometric/nepal_hrms consolidation commit `8d9a6a82`) | Partly — default rate and the Employee table were removed later |
| `leave_application_dynamic_approval` [`execute`](../../avinashgroup_app/patches/leave_application_dynamic_approval.py#L20) | Hides `leave_approver`, drops its mandatory rule | Leave goes through Dynamic Approval ([09-cross-cutting.md](09-cross-cutting.md)) | Yes |
| `add_company_to_employee_checkin` [`execute`](../../avinashgroup_app/patches/add_company_to_employee_checkin.py#L5) | `Employee Checkin.custom_company`, backfilled | Company-scoped device IDs (commit `d96f265d`) | Yes |
| `company_scoped_attendance_device_id` [`execute`](../../avinashgroup_app/patches/company_scoped_attendance_device_id.py#L5) | Swaps the unique index on `attendance_device_id` for a plain one | Same device user ID may exist in two companies | Yes |
| `add_company_to_shift_type` [`execute`](../../avinashgroup_app/patches/add_company_to_shift_type.py#L5) | `Shift Type.custom_company` | Per-company shifts | Yes |
| `add_site_only_hr_fields` [`execute`](../../avinashgroup_app/patches/add_site_only_hr_fields.py#L25) | Creates HR fields that existed only as desk data (Holiday List company, Attendance deviation fields …) | 2026-09-27 audit: code depended on fields no patch made | Yes |
| `convert_duplicate_threshold_to_seconds` [`execute`](../../avinashgroup_app/patches/convert_duplicate_threshold_to_seconds.py#L21) | Biometric Device dedup window minutes → seconds (×60) | Unit change would otherwise shrink the window 60× | Yes (one-off) |
| `merge_attendance_summary_report` [`execute`](../../avinashgroup_app/patches/merge_attendance_summary_report.py#L17) | Deletes the standalone Monthly Attendance Summary BS report | Merged into Monthly Attendance BS's View filter; it never worked from the desk | One-off |
| `setup_employee_category` [`execute`](../../avinashgroup_app/patches/setup_employee_category.py#L11) | `Employee.custom_employee_category`; OT eligibility fetched from it | The category was then the one place the OT rule was decided (superseded by `holiday_work_rule_on_employee`) | Yes ([01-masters.md](01-masters.md)) |
| `holiday_work_rule_on_employee` [`execute`](../../avinashgroup_app/patches/holiday_work_rule_on_employee.py#L26) | `custom_ot_eligibility` made an ordinary tick ("Overtime Eligible", no fetch); new `custom_compensatory_leave`; each employee's answer copied from their category | HR asked for overtime vs replacement leave on the Employee itself (2026-10-13) | Yes ([01-masters.md](01-masters.md) §1.2) |
| `setup_overtime_sheet` [`execute`](../../avinashgroup_app/patches/setup_overtime_sheet.py#L17) | Installs Overtime Sheet with audit fields; removes Holiday Duty Sheet | Dynamic Approval criteria key on `custom_created_by` | Yes ([04-overtime.md](04-overtime.md)) |
| `setup_leave_types` (×2) [`execute`](../../avinashgroup_app/patches/setup_leave_types.py#L84) | Casual, Sick, Maternity, Paternity, LWP, Replacement Leave | Client decisions 2026-09-15/17 | Yes |
| `setup_bs_leave_accrual` [`execute`](../../avinashgroup_app/patches/setup_bs_leave_accrual.py#L22) | Stops HRMS's earned-leave Scheduled Job | Our BS job replaces it; both would credit twice | Yes |
| `setup_late_half_day_rule` [`execute`](../../avinashgroup_app/patches/setup_late_half_day_rule.py#L20) | `Shift Type.custom_half_day_if_late_by_hours` (2); clears accidental cutoffs | Policy 1.2 as hours from shift start, not a clock time | Yes ([02](02-checkin-to-attendance.md)) |
| `setup_allowance_category` [`execute`](../../avinashgroup_app/patches/setup_allowance_category.py#L17) | (now a no-op) | Superseded 2026-10-08 by allowance kinds | No |
| `setup_payroll_employee_fields` [`execute`](../../avinashgroup_app/patches/setup_payroll_employee_fields.py#L22) | Employee initial basic, HRA/Gas/Education ticks, SSF applicable | NGI sheet's per-person inputs | **No** — moved to the assignment, fields removed |
| `setup_half_day_allowance_rule` [`execute`](../../avinashgroup_app/patches/setup_half_day_allowance_rule.py#L16) | `custom_half_day_counts` | Client 2026-09-21: a half day still earns tea | Yes |
| `setup_meal_entitlement_rule` [`execute`](../../avinashgroup_app/patches/setup_meal_entitlement_rule.py#L30) | `Meal Entitlement` condition; Meal points at it | One-meal-per-present-day paid 132,525 vs the client's 52,275 | Yes (rule since changed) |
| `setup_payroll_based_on_attendance` [`execute`](../../avinashgroup_app/patches/setup_payroll_based_on_attendance.py#L23) | Payroll Settings `payroll_based_on` = Attendance, half-day fraction 0.5 | §1 | Yes |
| `setup_payroll_adjustment` [`execute`](../../avinashgroup_app/patches/setup_payroll_adjustment.py#L6) | Installs Payroll Adjustment | §10 | Yes, unused |
| `setup_income_tax` [`execute`](../../avinashgroup_app/patches/setup_income_tax.py#L27) | Payroll Periods, 83/84 slabs, Income Tax component flags, slip override fields, tax row on structures, slab on assignments | §3, §4 | Yes |
| `setup_tax_exemptions` [`execute`](../../avinashgroup_app/patches/setup_tax_exemptions.py#L34) | `custom_women_rebate_percent`, retirement-cap fields, slip `custom_retirement_excess` / `custom_women_rebate` | §5; no figures seeded | Yes |
| `setup_salary_revision` [`execute`](../../avinashgroup_app/patches/setup_salary_revision.py#L10) | Installs Salary Revision | Dated raise with arrears ([08](08-changes-over-time.md)) | Yes |
| `setup_overtime_and_late_fine` [`execute`](../../avinashgroup_app/patches/setup_overtime_and_late_fine.py#L32) | `custom_rate_basis`, `custom_rate_multiplier`, `Employee.custom_late_fine_exempt`, Late Time / Authorised Overtime conditions | Sheet prices both off the person's basic (basic/30/8 ×1.5; fine per minute) | Yes |
| `setup_advance_recovery` [`execute`](../../avinashgroup_app/patches/setup_advance_recovery.py#L13) | Employee Advance monthly instalment and start month; salary recovery default | Advances repaid from salary ([08](08-changes-over-time.md)) | Yes |
| `setup_daily_wage` [`execute`](../../avinashgroup_app/patches/setup_daily_wage.py#L19) | `Salary Structure.custom_daily_wage`, Daily Wage component | NGK labour paid per day | **No** — retired 2026-10-08, field unread |
| `remove_merged_attendance_summary_report` [`execute`](../../avinashgroup_app/patches/remove_merged_attendance_summary_report.py#L13) | Deletes the leftover Report record | It raised ModuleNotFoundError | One-off |
| `setup_pay_input_fields` [`execute`](../../avinashgroup_app/patches/setup_pay_input_fields.py#L16) | Employee dearness/other/fuel/fixed/maintenance fields | Made by ad-hoc script on the working site | **No** — removed by `move_pay_to_salary_assignment` |
| `setup_hr_bs_dates` [`execute`](../../avinashgroup_app/patches/setup_hr_bs_dates.py#L31) | `custom_*_miti` fields, `Salary Slip.custom_bs_month`, Bs Conversion records, "Salary Slip BS" default print, email template | BS dates on HR forms ([09](09-cross-cutting.md)) | Yes |
| `setup_meal_rule_fields` [`execute`](../../avinashgroup_app/patches/setup_meal_rule_fields.py#L23) | Holiday hours for 1/2 meals, `custom_max_per_day` | Meal numbers out of code | Partly — holiday-hours fields removed |
| `late_half_day_as_half_absent` [`execute`](../../avinashgroup_app/patches/late_half_day_as_half_absent.py#L22) | Late half days: LWP leave type → Half Day + half-day status Absent | "Nobody took leave"; pay identical | Yes (data) |
| `setup_ot_rate_fields` [`execute`](../../avinashgroup_app/patches/setup_ot_rate_fields.py#L24) | `custom_rate_days_per_month` (seed 30), `custom_rate_hours_per_day` (seed 8) | Labour Act divisors out of code | Yes (30-day seed later cleared) |
| `setup_pay_on_holiday_field` [`execute`](../../avinashgroup_app/patches/setup_pay_on_holiday_field.py#L23) | `custom_pay_on_holiday` | Sheet never paid tea on a worked holiday | Yes |
| `setup_late_excuse` [`execute`](../../avinashgroup_app/patches/setup_late_excuse.py#L22) | `Attendance.custom_late_excused` + reason | HR can waive one day's lateness | Yes |
| `remove_dashain_bonus` [`execute`](../../avinashgroup_app/patches/remove_dashain_bonus.py#L20) | Removes Dashain Bonus doctypes (keeps the component) | User decision 2026-09-29 | One-off |
| `tax_relief_fields_without_defaults` [`execute`](../../avinashgroup_app/patches/tax_relief_fields_without_defaults.py#L19) | Retirement cap fields; rebate field default removed | No figures as defaults | Yes |
| `setup_shift_rotation` [`execute`](../../avinashgroup_app/patches/setup_shift_rotation.py#L29) | `Shift Type` "Takes Part in Rotation"; seeds NGI 6–2 and 12–8 | Monthly rotation ([01](01-masters.md)) | Yes |
| `remove_working_hours_threshold` [`execute`](../../avinashgroup_app/patches/remove_working_hours_threshold.py#L18) | Drops the "Working Hours >= Threshold" condition | Never implemented; paid nothing | One-off |
| `setup_allowance_kinds` [`execute`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L105) | Allowance kind fields, S/D/F/P accounts, Department section, seeds; retires Daily Wage; drops Company Allowance | §6, §7 | Yes |
| `move_pay_to_salary_assignment` [`execute`](../../avinashgroup_app/patches/move_pay_to_salary_assignment.py#L62) | Initial basic, SSF applicable, Allowances table on the assignment; old Employee fields removed | §9 | Yes |
| `meal_on_authorised_overtime` [`execute`](../../avinashgroup_app/patches/meal_on_authorised_overtime.py#L17) | Meal OT-eligible only; holiday-hours fields removed | Meal rule of 2026-10-09 ([04-overtime.md](04-overtime.md)) | Yes |
| `setup_salary_slip_daily_breakdown` [`execute`](../../avinashgroup_app/patches/setup_salary_slip_daily_breakdown.py#L12) | Salary Slip Daily Breakdown table (Salary Slip Day) | [06](06-salary-slip.md) | Yes |
| `setup_payroll_entry_bs_month` [`execute`](../../avinashgroup_app/patches/setup_payroll_entry_bs_month.py#L13) | Payroll Entry BS month fields, backfilled | Entries chosen by FY + BS month ([05](05-payroll-entry.md)) | Yes |
| `clear_payroll_payable_account_type` [`execute`](../../avinashgroup_app/patches/clear_payroll_payable_account_type.py#L13) | Clears Account Type on each company's default payroll payable | HRMS refuses a typed payable account | Yes (GEPL, SGU 347301 still typed "Liability" — they have no default payroll payable set, so the patch skipped them) |
| `setup_additional_salary_quantity` [`execute`](../../avinashgroup_app/patches/setup_additional_salary_quantity.py#L19) | `Additional Salary.custom_quantity`, `custom_rate`, backfilled | Salary statement needs OT hours, meals, late hours | Yes |
| `allowance_rate_list` [`execute`](../../avinashgroup_app/patches/allowance_rate_list.py#L50) | Structure Allowance Rates; rates onto assignment rows; drops Default Rate and structure tag rows | §8 | Yes |
| `rate_on_actual_month_days` [`execute`](../../avinashgroup_app/patches/rate_on_actual_month_days.py#L17) | Clears the 30-day seed | User decision 2026-10-12 | Yes |
| `women_rebate_on_employee` [`execute`](../../avinashgroup_app/patches/women_rebate_on_employee.py#L15) | `Employee.custom_womens_tax_rebate` | Rebate only for a woman whose only income is salary (commit `5f54331`) | Yes |
