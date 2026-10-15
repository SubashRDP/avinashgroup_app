# 01 · Masters and setup (people, time, calendar)

The records every later stage reads before it computes anything: who the employee is, what group they are in, which days they have off, which shift they work, what leave they earn, and which BS month a date belongs to. The pay masters (Payroll Settings, Payroll Period, Income Tax Slab, exemption categories, Salary Components, Salary Structures, Salary Structure Assignments, accounts, and the patch appendix) are in [01b-pay-masters.md](01b-pay-masters.md).

Pipeline position: everything here feeds [02-checkin-to-attendance.md](02-checkin-to-attendance.md), [03-shift-measurement.md](03-shift-measurement.md), [04-overtime.md](04-overtime.md) and the payroll stages ([05](05-payroll-entry.md), [06](06-salary-slip.md)). For each field, [impact-matrix.md](impact-matrix.md) shows what changes if you change it. Every hook named here is listed in [hooks-inventory.md](hooks-inventory.md).

> All "Config on avinas1" values were read from the database on **2026-10-12** (read-only SELECTs).

## Snapshot: what avinas1 actually holds (2026-10-12)

Read this before trusting any "it works like this" below. Most of the machinery exists in code, but on avinas1 much of the data it runs on has not been entered yet.

| Master | State on avinas1 | Consequence |
|---|---|---|
| Employees | 265 Active (NGI 100, NGN 73, NGG 49, NGK 43), 4 Left. **GLMI, GEPL and SGU have no employees.** | Payroll runs only for the four gas companies. |
| `attendance_device_id` | **Blank on all 269 employees.** No Biometric Device records, **0 Employee Checkins**. | No punch could map to anyone. Attendance on avinas1 is hand-made or imported (105 submitted rows, all in Shrawan 2083: 2026-07-17 to 2026-08-16). |
| Overtime Eligible / Replacement Leave ticks | On the Employee since 2026-10-13 (copied from the old categories). **261 of 265 active employees have neither tick**; 2 are Overtime Eligible, 2 Replacement Leave. | Holiday-work Overtime Sheet rows are refused for the 261 ([`get_holiday_work_rule`](../../avinashgroup_app/hr/overtime.py#L121), read by `evaluate`). Meal and OT pay reach only the 2 OT-eligible people. The Employee Category doctype and its 2 records were removed the same day (`drop_employee_category`). |
| Shift Types | 2: `NGI 9:00 AM to 5:00 PM`, `NGK 9:00 AM to 5:00 PM`. No shift for NGN, NGG, GLMI, GEPL or SGU. None ticked *Takes Part in Rotation*. | Rotation has nothing to rotate. NGN/NGG staff have no shift to be measured against. |
| Shift Assignments | **0**. `default_shift` is set on 4 employees (NGI). | For 261 employees no shift resolves, so late, early and OT minutes cannot be computed (see [03](03-shift-measurement.md)). |
| Holiday Lists | 83/84: common + Women list for NGI, NGN, NGG, NGK (8 lists). 82/83: one list per company (7). **No 83/84 list for GLMI, GEPL or SGU**, and those three have no `default_holiday_list`. | The 21 women carry their Women list on `Employee.holiday_list`; everyone else inherits the company default. |
| Leave | Leave Types exist (plus a stray `Causal Leave`). **0 Leave Policies, 0 Leave Periods, 0 Leave Policy Assignments, 0 Leave Allocations.** | The BS accrual job runs daily and credits nothing. No one has a leave balance. |
| Fiscal Year | `83/84` = 2026-07-17 → 2027-07-16, with all 7 company rows. `82/83` has all 7 too. | Naming of HR documents dated in these years works. |
| Payroll Period | `83/84 - <ABBR>` for all 7 companies. | Created by `ensure_payroll_period` (see [year_setup](#10-year_setup-one-call-per-fiscal-year)). |
| Nepal BS Period | **No records.** Nepal HRMS Settings: `process_payroll_in_nepali_month = 1`, `restrict_to_nepal_companies = 1`. | Every BS month border comes from the plain Nepali calendar. |
| Payroll Cost Center | Blank on all 265 active employees. 80 have no Department. | See [Department](#3-department--payroll-section). Journal split by cost centre falls back to company defaults ([07](07-after-the-slip.md)). |
| Joining date = birth date | 71 active employees (an import copied one into the other, noted in `hr_dashboard.SETUP_GAPS`). | Service-year based figures are wrong for them. |

---

## 1. Employee

Stock ERPNext/HRMS owns the Employee doctype (ERPNext's `setup/doctype/employee`, with HRMS's fields added on top). We add custom fields and two validate hooks, and **do not override the class**.

### 1.1 HR/payroll custom fields on Employee (tabCustom Field, avinas1)

Fields that HRMS itself ships as Custom Fields (`grade`, `default_shift`, `leave_approver`, `payroll_cost_center`, `health_insurance_*`, `shift_request_approver`, …) are stock and not listed here. The fields our app (or the site) added:

| Field | Label / type | Created by | Written by | Read by |
|---|---|---|---|---|
| `custom_nepal_hrms_section` | Section "Nepal HRMS" | [`custom_nepal_hrms_section`](../../avinashgroup_app/patches/setup_attendance_allowance.py#L113) | n/a | Layout anchor for the next fields |
| `custom_ot_eligibility` | Check "Overtime Eligible", editable | [`custom_ot_eligibility`](../../avinashgroup_app/patches/setup_attendance_allowance.py#L120); `fetch_from` removed and relabelled by [`custom_ot_eligibility` in holiday_work_rule_on_employee](../../avinashgroup_app/patches/holiday_work_rule_on_employee.py#L32) | HR on the form or list Edit | [`get_holiday_work_rule`](../../avinashgroup_app/hr/overtime.py#L121), [`_skip_for_eligibility`](../../avinashgroup_app/payroll/attendance_allowance.py#L665), [`_meals_for_day`](../../avinashgroup_app/payroll/attendance_allowance.py#L381), [`overtime_eligibility`](../../avinashgroup_app/hr/shift_day.py#L42), Work On Holiday and Yearly Leave reports, HR dashboard setup gaps |
| `custom_compensatory_leave` | Check "Replacement Leave for Holiday Work" | [`custom_compensatory_leave`](../../avinashgroup_app/patches/holiday_work_rule_on_employee.py#L47) | HR on the form or list Edit | [`get_holiday_work_rule`](../../avinashgroup_app/hr/overtime.py#L121), HR dashboard setup gaps; either/or with the tick above by [`validate_employee_holiday_rule`](../../avinashgroup_app/hr/overtime.py#L136) |
| `custom_late_fine_exempt` | Check "Late Fine Exempt" | [`custom_late_fine_exempt`](../../avinashgroup_app/patches/setup_overtime_and_late_fine.py#L58) | HR | [`_skip_for_eligibility`](../../avinashgroup_app/payroll/attendance_allowance.py#L665) |
| `custom_womens_tax_rebate` | Check "Women's Tax Rebate", shown only when gender = Female | [`custom_womens_tax_rebate`](../../avinashgroup_app/patches/women_rebate_on_employee.py#L20) | HR | [`women_rebate_fraction`](../../avinashgroup_app/payroll/tax_relief.py#L182); guarded by [`validate_womens_tax_rebate`](../../avinashgroup_app/payroll/tax_relief.py#L195) |
| `custom_birth_miti`, `custom_joining_miti`, `custom_relieving_miti` | Data "… (BS)" | [`add_fields`](../../avinashgroup_app/patches/setup_hr_bs_dates.py#L38) from [`BS_DATE_FIELDS`](../../avinashgroup_app/hr/bs_dates.py#L29) | [`set_bs_dates`](../../avinashgroup_app/hr/bs_dates.py#L75) on every validate (AD wins) | Display; rdp's Nepali date picker (Bs Conversion record `Employee`) |
| `custom_pan` | Data "PAN" | **No patch or fixture: site-only data** | HR | [`custom_pan`](../../avinashgroup_app/avinash_group_app/report/salary_tax_and_ssf_deposit/salary_tax_and_ssf_deposit.py#L171) in the tax/SSF deposit report (falls back to stock `pan_number`), BS payslip print format |
| `custom_ssf_id_no` | Data "SSF ID No." | **No patch or fixture: site-only data** | HR | Same two readers |
| `custom_citizenship_*`, `custom_signature_image`, `custom_document_user`, `custom_employee_cost_center_manager`, `custom_abbr`, audit fields (`custom_created_by/on`, `custom_modified_by`) | n/a | Site / other features (document generator, audit, approvals) | n/a | Not part of the pay pipeline |

Fields that **used to** be on Employee and were moved: the per-person allowance fields (Dearness, Other, Fuel, Fixed, Maintenance; HRA/Gas/Education ticks), Initial Basic, SSF Applicable and the "Attendance Allowances" exceptions table. They now live on the Salary Structure Assignment. See [`Pay moves off the Employee onto the Salary Structure Assignment`](../../avinashgroup_app/patches/move_pay_to_salary_assignment.py#L1) and [01b-pay-masters.md](01b-pay-masters.md). If you meet an old doc or sheet saying "set the allowance on the Employee", that doc is out of date.

### 1.2 Overtime or replacement leave: two ticks on the Employee

| | |
|---|---|
| **What** | Two ticks on the Employee say whether working a holiday or Saturday earns **paid overtime and meals** (`custom_ot_eligibility`, "Overtime Eligible") or a **replacement-leave day** (`custom_compensatory_leave`, "Replacement Leave for Holiday Work"), never both. |
| **Why** | Client meeting 2026-09-15, minute 2.2 as corrected on 2026-09-16, and minute 2.5 (`docs/hr-decisions/00-policy-minutes-2026-09-15.txt`): staff below officer level get overtime, officer/admin staff get replacement leave. Until 2026-10-13 the rule lived on the **Employee Category** the person was linked to, with `custom_ot_eligibility` fetched read-only from it. HR asked for it on the Employee itself; `holiday_work_rule_on_employee` ([`execute`](../../avinashgroup_app/patches/holiday_work_rule_on_employee.py#L27)) removed the fetch, added the second tick and copied every member's answer from their category. |
| **Where** | Custom fields made by [`execute`](../../avinashgroup_app/patches/holiday_work_rule_on_employee.py#L27); either/or check [`validate_employee_holiday_rule`](../../avinashgroup_app/hr/overtime.py#L136) (Employee `validate` hook); read by [`get_holiday_work_rule`](../../avinashgroup_app/hr/overtime.py#L121). |
| **Triggered by** | HR saving an Employee (form or list bulk Edit). |
| **Reads / Writes** | Nothing writes the ticks except HR (and the one-off patch). |
| **Impacts downstream** | Overtime Sheet: [`evaluate`](../../avinashgroup_app/hr/overtime.py#L150) **refuses a holiday-work row for an employee with neither tick**, and a working-day overtime row for anyone not Overtime Eligible; it decides Overtime vs Replacement Leave ([04-overtime.md](04-overtime.md)). Payroll Inputs: components ticked *OT Eligible Only* (Meal, Overtime) skip anyone without `custom_ot_eligibility` ([`_skip_for_eligibility`](../../avinashgroup_app/payroll/attendance_allowance.py#L665)), and meals need it again ([`_meals_for_day`](../../avinashgroup_app/payroll/attendance_allowance.py#L381)). Replacement leave is granted only for rows whose entitlement `evaluate` set to Replacement Leave ([04-overtime.md](04-overtime.md)). Reports: Work On Holiday, Yearly Leave Details (holiday add-back only for non-OT staff). |
| **Config on avinas1** | After the patch (2026-10-13): 2 active employees Overtime Eligible, 2 Replacement Leave, 261 neither — exactly the old category membership (`Operation` → Overtime Eligible, `Officer & Admin` → Replacement Leave, none → neither). 0 mismatches. |
| **Gotchas** | (1) The answer is **current state, not dated**. It never was dated: the category link was not dated either, and each Overtime Sheet row keeps the entitlement worked out when it was saved, so past sheets are unaffected by a later change of tick. (2) Neither tick is a valid state the form allows; the HR dashboard counts it as a setup gap. (3) Ticks are edited through the ORM, so every change is in the Employee's Version history (the old `sync_employees` SQL push, which left none, is gone). |

**Employee Category and Employee Category Tool — removed 2026-10-13.** After the ticks above took over, the Employee Category doctype (with its 2 records, Operation and Officer & Admin), the Employee link `custom_employee_category`, the **Employee Category Tool** and the hidden `employee_category` column on Overtime Sheet Employee were deleted by `drop_employee_category` ([`execute`](../../avinashgroup_app/patches/drop_employee_category.py#L27)). The field definition goes first so the Employee form never holds a Link to a missing doctype; the old `tabEmployee.custom_employee_category` column is left in the database and nothing reads it. `setup_employee_category` ([`execute`](../../avinashgroup_app/patches/setup_employee_category.py#L11)) is now a no-op and `holiday_work_rule_on_employee` no longer creates the link, so a new site never gets them.

### 1.3 Late Fine Exempt

| | |
|---|---|
| **What** | A tick that stops the Late Fine (and any "Late Arrival After" component) from being charged. Late time is still recorded on attendance. |
| **Why** | NGI's salary sheet types the late rate as 0 for its managers (CEO, AGM, managers, assistant managers, company secretary). That is a decision about the person, so it lives on the Employee; see the comment in [`_skip_for_eligibility`](../../avinashgroup_app/payroll/attendance_allowance.py#L665). |
| **Triggered by** | Read during Prepare Payroll Inputs ([05-payroll-entry.md](05-payroll-entry.md)). |
| **Impacts downstream** | No Late Fine Additional Salary for the person, so no deduction on the slip. The Attendance rows and the Half Day rule are unaffected: being >2 h late still makes a half-absent day ([02](02-checkin-to-attendance.md)). |
| **Config on avinas1** | 0 employees ticked. |

### 1.4 Women's Tax Rebate

| | |
|---|---|
| **What** | HR ticks it for a woman whose **only** income is salary. Her tax is then reduced by the percentage on the company's Income Tax Slab (`custom_women_rebate_percent`). |
| **Why** | Income Tax Act Schedule 1, 1(10). Gender alone does not decide it (rent, business or investment income disqualifies her), and only HR knows that. Docstring of [`Who gets the women's rebate is on the Employee`](../../avinashgroup_app/patches/women_rebate_on_employee.py#L1); commit `5f54331` "Women's tax rebate: who qualifies is a tick on the Employee, the percent stays on the slab". |
| **Where** | Employee validate hook registered at [`validate_womens_tax_rebate`](../../avinashgroup_app/hooks.py#L356) refuses the tick on a non-female employee ([`validate_womens_tax_rebate`](../../avinashgroup_app/payroll/tax_relief.py#L195)); the slip reads it in [`women_rebate_fraction`](../../avinashgroup_app/payroll/tax_relief.py#L182). |
| **Impacts downstream** | Income-tax row of every slip for her ([06-salary-slip.md](06-salary-slip.md)). Unticked by default: no rebate until HR decides. Changing the gender to non-female with the tick on blocks the Employee save. |
| **Config on avinas1** | 0 ticked (21 active women). |

### 1.5 Attendance Device ID (company-scoped)

| | |
|---|---|
| **What** | `Employee.attendance_device_id` is the user number on the biometric device. Stock ERPNext makes it **unique site-wide**; we make it **unique within a company**. |
| **Why** | Each company runs its own device, and every device numbers its users from 1, so "7" legitimately exists in NGI and in NGK. Matching a punch is already company-scoped. Docstrings of [`execute` in company_scoped_attendance_device_id](../../avinashgroup_app/patches/company_scoped_attendance_device_id.py#L5) and [`validate_unique_device_id`](../../avinashgroup_app/biometric/employee.py#L13); commit `c3e8b19e` (2026-06-29). |
| **Where** | Patch drops the unique index and adds a plain one with a Property Setter `unique = 0` on [`attendance_device_id`](../../avinashgroup_app/patches/company_scoped_attendance_device_id.py#L22). The per-company check is registered at [`validate_unique_device_id`](../../avinashgroup_app/hooks.py#L353). The matcher is [`resolve_employee_for_punch`](../../avinashgroup_app/biometric/utils.py#L48): device company first, then the device's Allowed Employees list. |
| **Reads / Writes** | Reads Employee (`attendance_device_id`, `company`). Employee Checkin gets `custom_company` ([`custom_company`](../../avinashgroup_app/patches/add_company_to_employee_checkin.py#L18), `fetch_from employee.company`). |
| **Impacts downstream** | The only link from a punch to a person ([02](02-checkin-to-attendance.md)). A blank ID means no punches reach the person. A wrong ID means punches go to someone else's attendance and therefore their pay. |
| **Config on avinas1** | Blank for every employee, no Biometric Device, no checkins. |
| **Gotchas** | Stock HRMS's field-based API [`add_log_based_on_employee_field`](../../../hrms/hrms/hr/doctype/employee_checkin/employee_checkin.py#L131) still matches on the ID alone, without the company. It must not be used here; the patch docstring says nothing on this site calls it. |

### 1.6 BS dates on Employee

[`set_bs_dates`](../../avinashgroup_app/hr/bs_dates.py#L75) (Employee validate, registered with Leave Application, Payroll Entry and Salary Slip at [`set_bs_dates`](../../avinashgroup_app/hooks.py#L472)) writes `custom_birth_miti`, `custom_joining_miti` and `custom_relieving_miti` from the AD dates. **AD is authoritative**: a typed miti that disagrees is overwritten. Dates outside the converter's range (about 1913–2043 AD; avinas1 has 1900-01-01 placeholder birth dates) get a blank miti instead of an error ([`to_miti`](../../avinashgroup_app/hr/bs_dates.py#L53)). The hook never blocks a save; a failure is logged. Why: HR and staff speak BS (docstring of [`BS (miti) dates beside the AD dates`](../../avinashgroup_app/hr/bs_dates.py#L1)). On avinas1, 269 employees carry a joining miti. Nothing in pay reads these fields; they are for display and printing only.

### 1.7 Holiday list, default shift, department, payroll cost center

| Field (stock) | How we use it | Read by |
|---|---|---|
| `holiday_list` | **Blank for most people.** They inherit `Company.default_holiday_list`. Set only for women (their Women list), which is how the women-only holidays reach them. | HRMS's [`get_holiday_list_for_employee`](../../../erpnext/erpnext/setup/doctype/employee/employee.py#L269) (salary-slip working days, auto attendance absents); our [`resolve_holiday_lists`](../../avinashgroup_app/hr/utils.py#L308) (reports, daily breakdown); [`set_holiday_flag`](../../avinashgroup_app/payroll/attendance_allowance.py#L552); [`get_day_type`](../../avinashgroup_app/hr/overtime.py#L60); [`switch_to_current_year_lists`](../../avinashgroup_app/hr/holiday_year_switch.py#L30) |
| `default_shift` | The fallback when no Shift Assignment covers the date (HRMS precedence). | HRMS `fetch_shift`; [`get_shift_window`](../../avinashgroup_app/hr/overtime.py#L91); [`ShiftRoster`](../../avinashgroup_app/hr/shift_day.py#L60); [`resolve_employee_for_punch`](../../avinashgroup_app/biometric/utils.py#L48) returns it |
| `department` | Its `custom_payroll_section` decides which account each salary component posts to (see §3). | [`get_section`](../../avinashgroup_app/payroll/allowance.py#L162) |
| `payroll_cost_center` | Stock HRMS: the slip's and journal's cost centre. | HRMS Payroll Entry ([07](07-after-the-slip.md)) |
| `employment_type` | `Probation…` selects the Probation leave policy in `assign_leave_policies`. | [`assign_leave_policies`](../../avinashgroup_app/hr/year_setup.py#L398) |
| `gender` | Maternity/Paternity gate, Women's rebate gate. | [`validate_gender`](../../avinashgroup_app/hr/statutory_leave.py#L27), [`women_rebate_fraction`](../../avinashgroup_app/payroll/tax_relief.py#L182) |

**Gotcha, holiday-list resolution.** Any code that reads `Employee.holiday_list` directly sees a blank for ~244 people and concludes they have no holidays. [`resolve_holiday_lists`](../../avinashgroup_app/hr/utils.py#L308) exists for exactly this reason: it applies the company fallback for a whole roster in one query. New code must use it, or HRMS's `get_holiday_list_for_employee`.

### 1.8 Setup gaps the HR dashboard flags

[`SETUP_GAPS`](../../avinashgroup_app/hr/hr_dashboard.py#L506) counts active employees with: no Attendance Device ID ("No punch reaches this person"), no Default Shift ("Lateness cannot be measured"), neither Overtime Eligible nor Replacement Leave ticked ("Holiday work earns neither overtime nor leave"), no Payroll Cost Center, and joining date = birth date. It mirrors `docs/payroll-handover.md` §8. On avinas1 every one of these is non-zero (265 / 261 / 261 / 265 / 71). Note that "no Default Shift" overstates the problem on a site where Shift Assignments are used; on avinas1 there are none, so the count is accurate.

---

## 2. Employee Category: removed (see §1.2)

The doctype was deleted on 2026-10-13. [`require_standing_setup`](../../avinashgroup_app/hr/year_setup.py#L128) does not ask for categories.

---

## 3. Department → Payroll Section

| | |
|---|---|
| **What** | `Department.custom_payroll_section` (Select: *Admin & Accounts*, *Marketing*, *Plant*) says which of a Salary Component's three accounts that department's pay posts to: O/O (`account`), S/D (`custom_account_marketing`) or F/P (`custom_account_plant`). |
| **Why** | The client's books split salary expense by section: Office/Overhead, Selling/Distribution, Factory/Plant. One component has three ledgers. Docstring of `payroll/payroll_entry.py`; [`SECTION_ACCOUNT_FIELD`](../../avinashgroup_app/payroll/allowance.py#L94). |
| **Where** | Created by [`custom_payroll_section`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L211). Seeded once from the department's name by [`section_for_department`](../../avinashgroup_app/patches/setup_allowance_kinds.py#L267) ("plant" → Plant, "sales"/"marketing" → Marketing, else Admin & Accounts). Read via [`get_section`](../../avinashgroup_app/payroll/allowance.py#L162). |
| **Triggered by** | Payroll Entry's accrual journal ([07-after-the-slip.md](07-after-the-slip.md)). |
| **Impacts downstream** | The expense account of every earning and deduction line on the payroll journal. An employee whose department has **no** section, on a component that has S/D or F/P accounts, makes the journal **throw** (see `AvinashPayrollEntry.get_salary_component_total` in [07](07-after-the-slip.md)). Moving a department to another section moves all of its staff's future salary expense to that section's ledger. |
| **Config on avinas1** | Every department of all 7 companies has a section, so 0 active employees sit in a section-less department. HR has overridden the name heuristic in places: e.g. `Driver - NGK` and `Vehicle Helper - NGK` are Marketing, `Vehicle Helper - NGN` is Admin & Accounts. **80 active employees have no Department at all**, and `get_section` returns None for them. |
| **Gotchas** | Whether a blank department throws or falls back depends on the component's accounts; see [07](07-after-the-slip.md). Unverified for the 80 department-less employees, because no payroll journal has been posted on avinas1 yet. |

`Department.payroll_cost_center` is stock HRMS and blank on every department on avinas1.

---

## 4. Holiday Lists

### 4.1 Model: two lists per company per fiscal year

| | |
|---|---|
| **What** | Each company keeps, per fiscal year, a **common** list (`<ABBR> 83/84`, Saturdays + festivals, set as `Company.default_holiday_list`) and a **Women** list (`<ABBR> Women 83/84`, the same plus Teej and similar days, set on each woman's `Employee.holiday_list`). |
| **Why** | Policy 2.4: Teej is a holiday for women only. HRMS gives an employee exactly **one** holiday list, so the only way to give women an extra day is a second list. See [../holiday-lists.md](../holiday-lists.md), `docs/hr-decisions/02-holiday-list.txt`. |
| **Custom field** | `Holiday List.custom_company` (Link, reqd): [`custom_company`](../../avinashgroup_app/patches/add_site_only_hr_fields.py#L30). It was created on the desk first and only later put in a patch (audit 2026-09-27). Naming: `NAMING_CONFIG["Holiday List"]` → `<ABBR>-Holiday-#####`, which needs the company ([09-cross-cutting.md](09-cross-cutting.md)). |
| **Read by** | HRMS: slip working days ([06](06-salary-slip.md), `include_holidays_in_total_working_days = 1`, so holidays are paid days), auto attendance absent-marking ([02](02-checkin-to-attendance.md)). Ours: [`set_holiday_flag`](../../avinashgroup_app/payroll/attendance_allowance.py#L552) ticks `Attendance.custom_worked_on_holiday` when the date is **any** row of the employee's list (weekly offs included); [`get_day_type`](../../avinashgroup_app/hr/overtime.py#L60) (Holiday / Weekly Off / Working Day for the Overtime Sheet); Attendance Fix skips holidays; daily breakdown; BS attendance reports. |
| **Impacts downstream** | A missing festival on someone's list means: an attendance row on that day is a normal working day (no holiday tea/meal rules, no holiday OT, no replacement leave), and if they stayed home and auto attendance or Attendance Fix runs, an **Absent** that costs pay. A woman left on the common list loses Teej. |

**Config on avinas1 (83/84):**

| List | Rows | Of which not weekly-off |
|---|---|---|
| NGI 83/84 / NGI Women 83/84 | 68 / 69 | 16 / 17 |
| NGN 83/84 / NGN Women 83/84 | 68 / 69 | 16 / 17 |
| NGG 83/84 / NGG Women 83/84 | 63 / 64 | 11 / 12 |
| NGK 83/84 / NGK Women 83/84 | 63 / 64 | 11 / 12 |

NGG and NGK carry 5 fewer festival days than NGI and NGN. Whether that is a deliberate per-company difference or entry still pending is **unverified**; compare `hr_dashboard.py`'s note on Maha Ashtami at NGG/NGK. Women on own lists: NGI 17, NGG 3, NGN 1 (NGK has no women). GLMI, GEPL and SGU have only an 82/83 list, and no company default.

### 4.2 Holiday Bulk Update (doctype) → `holiday_lists.apply_holiday_change` → `holiday_backdate.follow_up`

| | |
|---|---|
| **What** | One form: a date, a name, "All Holiday Lists" or a picked set ([`all_holiday_lists`](../../avinashgroup_app/avinash_group_app/doctype/holiday_bulk_update/holiday_bulk_update.json#L46), [`holiday_lists`](../../avinashgroup_app/avinash_group_app/doctype/holiday_bulk_update/holiday_bulk_update.json#L53)). **Apply** adds the holiday to every chosen list whose date range covers it, then fixes attendance already marked for that date if it is in the past. |
| **Why** | Fourteen lists for 83/84. A holiday announced mid-year typed into thirteen of them shows up at payroll as one company's staff marked Absent on a day the rest had off. Docstrings of [`HolidayBulkUpdate`](../../avinashgroup_app/avinash_group_app/doctype/holiday_bulk_update/holiday_bulk_update.py#L32) and [`Add or remove one holiday across many Holiday Lists`](../../avinashgroup_app/hr/holiday_lists.py#L1); commit `5db8643` (2026-09-28) for the backdate follow-up. |
| **Where** | Button → [`apply`](../../avinashgroup_app/avinash_group_app/doctype/holiday_bulk_update/holiday_bulk_update.py#L42) → [`apply_holiday_change`](../../avinashgroup_app/hr/holiday_lists.py#L79) (skips lists out of range, or that already have the date) → [`follow_up`](../../avinashgroup_app/hr/holiday_backdate.py#L51). |
| **follow_up, for a past date** | For employees whose *effective* list (own, else company default: [`_employees_on`](../../avinashgroup_app/hr/holiday_backdate.py#L115)) now has the date: worked rows (Present / Half Day / WFH) get `custom_worked_on_holiday = 1`; an Absent with no punches and no leave is **cancelled and deleted** (it was never an absence); rows tied to a Leave Application are left alone (the sandwich rule already counts holidays inside leave). **Employees with a submitted Salary Slip covering the date are skipped and named.** Submitted Overtime Sheets for the date are only *listed*, not rewritten. |
| **Writes** | Holiday rows; `Attendance.custom_worked_on_holiday` (`db.set_value`, no modified bump); deletes Attendance; `last_applied_on`, `result` on the form. |
| **Impacts downstream** | Holiday tea/meal rules, holiday OT measurement, replacement leave, the Work On Holiday report, payment days. A paid month is never touched; HR must cancel and redo that slip by hand. |
| **Gotchas** | (1) The form **only adds**. [`apply_holiday_change`](../../avinashgroup_app/hr/holiday_lists.py#L79) also supports `"Remove Holiday"`, and [`get_removable_holidays`](../../avinashgroup_app/hr/holiday_lists.py#L43) / [`holiday_date_from_option`](../../avinashgroup_app/hr/holiday_lists.py#L74) build a removal picker, but **no caller in the app uses them**. This is dead code left from an earlier add/remove design; the module docstring still says "Add or remove". (2) Removing a holiday is done on the Holiday List itself, and nothing re-marks attendance for it; that is Attendance Fix's job ([02](02-checkin-to-attendance.md)). (3) Saturdays are generated with the Holiday List's own "Add to Holidays" button; the bulk tool never touches weekly-off rows. |

### 4.3 Year switch: `holiday_year_switch.switch_to_current_year_lists`

| | |
|---|---|
| **What** | Each day, any Company default or active Employee `holiday_list` that **no longer covers today** is repointed to the same kind of list (common or Women, detected by "Women" in the title) for the fiscal year that does. A missing target list is logged as an error ("Holiday lists missing for the new fiscal year"). |
| **Why** | HRMS v15.49 keeps one list per person, not one per year. On 1 Shrawan everyone would still point at last year's list, so no Saturday or festival would be a holiday, and attendance would mark those days Absent without saying why. The switch cannot happen early, because that would take away the rest of the old year's holidays. Docstring of [`On a fiscal year's first day`](../../avinashgroup_app/hr/holiday_year_switch.py#L1); commit `24b12af`. |
| **Where / Triggered by** | [`switch_to_current_year_lists`](../../avinashgroup_app/hr/holiday_year_switch.py#L30), scheduled `daily_long` at [`switch_to_current_year_lists`](../../avinashgroup_app/hooks.py#L563). Scheduled Job Type enabled on avinas1. |
| **Reads / Writes** | Fiscal Year spanning today; `Company.default_holiday_list`; `Employee.holiday_list` (`update_modified=False`); Holiday List titles `"<ABBR> [Women ]<FY>"` ([`_list_for`](../../avinashgroup_app/hr/holiday_year_switch.py#L87)). |
| **Impacts downstream** | Everything in §4.1 from the first day of the year. If the new year's lists are not built (`setup_year`) **before** 1 Shrawan, everyone has no holidays from that day. |
| **Gotchas** | (1) It matches lists **by title**, so a renamed list breaks the switch. (2) It acts only on Active employees; a Left employee keeps the old list. (3) Its docstring says it is scheduled `daily`; hooks.py registers it as `daily_long`. Same effect. (4) For GLMI, GEPL and SGU it does nothing today: their company default is blank, and the code treats a blank as "doesn't cover", then looks for `GLMI 83/84` and logs it missing. Unverified whether that error log is firing daily on avinas1. |

---

## 5. Shift Types

Stock HRMS owns Shift Type and its auto-attendance engine. We add three fields (plus `custom_naming_series` and the audit fields).

| Field | Created by | What / why | Read by |
|---|---|---|---|
| `custom_company` (Link, reqd) | [`custom_company`](../../avinashgroup_app/patches/add_company_to_shift_type.py#L20) | Naming `NAMING_CONFIG["Shift Type"]` (`SHIFT`) needs a company abbreviation. Without the field, **every Shift Type insert failed**, which is why the site could never create a shift and therefore never marked auto attendance (patch docstring). Also scopes rotation and `year_setup`. | Naming override; [`rotational_shifts`](../../avinashgroup_app/hr/shift_rotation.py#L87); [`require_standing_setup`](../../avinashgroup_app/hr/year_setup.py#L128) |
| `custom_half_day_if_late_by_hours` (Float, default 2) | [`custom_half_day_if_late_by_hours`](../../avinashgroup_app/patches/setup_late_half_day_rule.py#L25) | Policy 1.2: more than 2 h late is a half day, measured from **each shift's own start**, so it does not need re-typing when the hours change. 0 turns it off. | [`enforce_late_arrival_half_day`](../../avinashgroup_app/biometric/attendance_override.py#L55) ([02](02-checkin-to-attendance.md)) |
| `custom_in_rotation` (Check "Takes Part in Rotation") | [`ROTATION_FIELD`](../../avinashgroup_app/patches/setup_shift_rotation.py#L34) | Which shifts staff may be rotated between, month by month. HR's data, not code. The seed ticks NGI's 6–14 and 12–20 shifts ([`SEED_HOURS`](../../avinashgroup_app/patches/setup_shift_rotation.py#L26)). | [`rotational_shifts`](../../avinashgroup_app/hr/shift_rotation.py#L87), Shift Type form button |

**Removed 2026-10-13: Late Arrival Cutoff.** `custom_late_arrival_cutoff_time`, an absolute clock-time cutoff beside the hours rule, is gone, and so is its save guard `hr/shift_type_guard.py`. The desk Time control filled a blank cutoff with the clock time of the save; on the first test run that half-dayed **2,423 of 2,808 days**. patch `drop_late_arrival_cutoff` ([`execute`](../../avinashgroup_app/patches/drop_late_arrival_cutoff.py#L24)) deletes the Custom Field and leaves the column (and any stray values in it, e.g. on the demo server) unread. `custom_half_day_if_late_by_hours` is now the only lateness cutoff.

**Stock fields that matter downstream** (owned by HRMS, explained in [02](02-checkin-to-attendance.md)): `start_time`/`end_time`, `enable_auto_attendance`, `process_attendance_after`, `last_sync_of_checkin`, `begin_check_in_before_shift_start_time`, `allow_check_out_after_shift_end_time`, `determine_check_in_and_check_out`, `working_hours_calculation_based_on`, `working_hours_threshold_for_half_day/absent`, `late_entry_grace_period`, `early_exit_grace_period`.

**Config on avinas1:**

| Shift | Company | Hours | Auto attendance | Late → half day | Grace | Window before/after (min) | Process after | Rotation |
|---|---|---|---|---|---|---|---|---|
| NGI 9:00 AM to 5:00 PM | NGI | 09:00–17:00 | **0** | 2.00 h | 0 | 180 / 240 | 2026-10-09 | 0 |
| NGK 9:00 AM to 5:00 PM | NGK | 09:00–17:00 | **0** | 2.00 h | 0 | 60 / 60 | 2026-06-29 | 0 |

The rotation seed found nothing to tick, because avinas1 has no 6–14 or 12–20 shift. [../shift-rotation.md](../shift-rotation.md) describes a rotation that does not exist on this site yet.

---

## 6. Shift Assignment, Shift Request, rotation, roster

**Stock HRMS:** a Shift Assignment gives an employee a shift for a date range (open-ended if no end). A Shift Request, once approved and submitted, creates one. `fetch_shift` on a checkin resolves a shift as: dated assignment first, then `Employee.default_shift`. HRMS refuses overlapping active assignments.

**The group's model:** every employee holds **one open-ended assignment from the start of the fiscal year**, so attendance marked weeks later still finds the right shift. That model collides with HRMS's overlap rule, and the four modules below exist to work around it. Re-marking attendance after a shift change is covered in [02-checkin-to-attendance.md](02-checkin-to-attendance.md).

| Module | What it does | Triggered by | Why |
|---|---|---|---|
| [shift_change.py: `validate_request` and friends](../../avinashgroup_app/hr/shift_change.py#L41) | [`validate_request`](../../avinashgroup_app/hr/shift_change.py#L41) refuses a request for the shift the person already holds. [`make_room_for_request`](../../avinashgroup_app/hr/shift_change.py#L58) ends the standing assignment the day before, then resumes it the day after (an open request = permanent move, no resume). [`close_gap_after_cancel`](../../avinashgroup_app/hr/shift_change.py#L87) undoes that. | Shift Request validate / before_submit / on_cancel ([`validate_request`](../../avinashgroup_app/hooks.py#L443), [`make_room_for_request`](../../avinashgroup_app/hooks.py#L445), [`close_gap_after_cancel`](../../avinashgroup_app/hooks.py#L447)) | Without it no Shift Request can be approved: "already has an active Shift Assignment …". HRMS only compares a request with the Default Shift, which is empty here. |
| [shift_backdate.py: `guard_paid_period` and friends](../../avinashgroup_app/hr/shift_backdate.py#L81) | [`guard_paid_period`](../../avinashgroup_app/hr/shift_backdate.py#L81) **refuses** a change reaching into a period with a submitted Salary Slip. `prepare_*` detaches attendance and checkins from the old shift so HRMS lets the assignment be cancelled. [`rebuild_for_request`](../../avinashgroup_app/hr/shift_backdate.py#L141) / [`rebuild_for_assignment`](../../avinashgroup_app/hr/shift_backdate.py#L160) re-mark past days on the new shift (inline up to [`INLINE_REBUILD_DAYS`](../../avinashgroup_app/hr/shift_backdate.py#L70) = 45, longer on the `long` queue) and re-measure Overtime Sheets. | Shift Request / Shift Assignment validate, before_submit, before_cancel, on_submit, on_cancel (hooks.py lines 433–439, from [`guard_paid_period`](../../avinashgroup_app/hooks.py#L452) to [`rebuild_for_assignment`](../../avinashgroup_app/hooks.py#L456)) | "Ram worked 12–8 all last week, not 6–2": late fines, half-day cuts, tea, meals and OT all read the attendance, so a backdated change that is not followed through is a wrong salary. |
| [shift_rotation.py: `ROTATION_FIELD`](../../avinashgroup_app/hr/shift_rotation.py#L77) | Bulk move between shifts ticked `custom_in_rotation` in the same company: [`preview`](../../avinashgroup_app/hr/shift_rotation.py#L111) / [`rotate`](../../avinashgroup_app/hr/shift_rotation.py#L152) (open-ended from a date) and [`set_periods`](../../avinashgroup_app/hr/shift_rotation.py#L197) (bounded ranges from the roster page). Refuses non-rotational shifts server-side. | "Move Staff to This Shift" button in `public/js/shift_type.js`; Shift Roster page Apply. Nothing scheduled. | Stock tools refuse anyone who already holds a shift, which is everybody; Shift Schedule repeats by weekday, not by month. Developer request 2026-10-01. See [../shift-rotation.md](../shift-rotation.md). |
| [shift_roster.py: `roster`](../../avinashgroup_app/hr/shift_roster.py#L30) | Read-only page: one row per employee, one column per BS month, with each cell's shift spans. [`roster`](../../avinashgroup_app/hr/shift_roster.py#L30). Uses [`ShiftRoster`](../../avinashgroup_app/hr/shift_day.py#L60) (the same per-day resolver attendance and OT use). | Desk page `shift_roster` | One answer for "who was on which shift that day". |

**Config on avinas1:** 0 Shift Assignments, 0 Shift Requests in use, 4 employees with a Default Shift. None of the machinery above has data to act on yet.

---

## 7. Leave types, policies and BS accrual

### 7.1 Leave Types

| | |
|---|---|
| **What** | Casual, Sick (earned monthly, 0.25 rounding, credited on the BS month's **last day**, encashable, sandwich rule on), Maternity (98 continuous days max), Paternity (15), Replacement Leave (`is_compensatory`), Leave Without Pay (`is_lwp`). |
| **Why** | Client decisions 2026-09-15, refined 2026-09-17 (`docs/hr-decisions/00-policy-minutes-2026-09-15.txt`, `01-leave-type.txt`). Day counts are per company and belong in each Leave Policy, not the type. Sandwich rule: minute 3.5. "Home Leave" was renamed to Casual Leave. Source: [`LEAVE_TYPES`](../../avinashgroup_app/patches/setup_leave_types.py#L31). |
| **Triggered by** | Patch `setup_leave_types` (twice in patches.txt) and again by every `setup_year` ([`ensure_leave_types`](../../avinashgroup_app/hr/year_setup.py#L216)), which **overwrites** the behaviour flags on every run. |
| **Impacts downstream** | `is_lwp` → the slip's LWP days ([06](06-salary-slip.md)); a Leave Application on a date sets Attendance to On Leave ([02](02-checkin-to-attendance.md)); `include_holiday` → holidays inside a leave are charged as leave; Replacement Leave is credited by [`grant_row`](../../avinashgroup_app/hr/replacement_leave.py#L178) ([04](04-overtime.md)). |
| **Config on avinas1** | As above, plus **`Causal Leave`** (a typo duplicate: not earned, no rounding, no holiday rule). Unknown origin. Because `setup_year` re-asserts only the six named types, it will never fix or remove it. |

Late half days are **not** leave. Earlier versions put a Leave Without Pay type on a late Half Day. [`A late half day is "paid, but half"`](../../avinashgroup_app/patches/late_half_day_as_half_absent.py#L1) switched them to HRMS's Half Day + `half_day_status = Absent` with no leave type ("nobody took leave"), with the same pay effect. The short-lived "Late Half Day" type was removed.

### 7.2 Gender gate: `statutory_leave.validate_gender`

[`validate_gender`](../../avinashgroup_app/hr/statutory_leave.py#L27), registered for Leave Allocation and Leave Application at [`validate_gender`](../../avinashgroup_app/hooks.py#L495). Maternity only for Female, Paternity only for Male ([`GENDER_RESTRICTED_LEAVE`](../../avinashgroup_app/hr/statutory_leave.py#L21)). It deliberately enforces nothing else: the Labour Act day limits (98, of which 60 paid; 15) are guidance for HR.

### 7.3 Annual ceiling: `leave_ceiling.validate_within_policy`

[`validate_within_policy`](../../avinashgroup_app/hr/leave_ceiling.py#L36) (Leave Allocation validate, [`validate_within_policy`](../../avinashgroup_app/hooks.py#L499)). It refuses an allocation that would take the year's **new** leaves for that type past the `annual_allocation` on the employee's own submitted Leave Policy ([`policy_allocation`](../../avinashgroup_app/hr/leave_ceiling.py#L61)). Carry-forward does not count. Why: client rule 2026-09-22, "the month's credit may be any size, the year's total may not". It reads the person's own policy, so Karnali's 8 casual days are enforced as 8 (commit `61a4c5f`). No policy means no check.

### 7.4 BS earned-leave accrual: `hr/utils.allocate_earned_leaves_bs`

| | |
|---|---|
| **What** | It **replaces** HRMS's `allocate_earned_leaves`. Every day it checks whether today is a leave type's BS credit day (first or last day of the BS month) and, if so, credits one instalment to each live allocation through HRMS's own `update_previous_leave_allocation`. Only the calendar test changes; the instalment size, caps, pro-rating and ledger are HRMS's. |
| **Why** | Stock HRMS credits on AD month ends: (W1) every credit lands 14–17 days late, and (W2) the Ashad instalment **never** happens, because the leave year has already expired by 31 July, so everyone silently gets 11 of 12 instalments. Docstring of [`Monthly earned-leave accrual on Bikram Sambat months`](../../avinashgroup_app/hr/utils.py#L10). |
| **Where** | [`allocate_earned_leaves_bs`](../../avinashgroup_app/hr/utils.py#L81), [`_is_accrual_day`](../../avinashgroup_app/hr/utils.py#L199), [`_credit_instalment`](../../avinashgroup_app/hr/utils.py#L128); helper [`preview_accrual_dates`](../../avinashgroup_app/hr/utils.py#L266). Stock job stopped by [`STOCK_JOB_METHOD`](../../avinashgroup_app/patches/setup_bs_leave_accrual.py#L19). Stock function: [`allocate_earned_leaves`](../../../hrms/hrms/hr/utils.py#L341). |
| **Triggered by** | `daily_long` scheduler ([`allocate_earned_leaves_bs`](../../avinashgroup_app/hooks.py#L560)). |
| **Scope limits** | Monthly frequency with First Day / Last Day only. "Date of Joining" is excluded (BS day 31/32 does not exist in every month). Quarterly and other frequencies are refused, because the stock check reads inverted in 15.49.2. |
| **Config on avinas1** | Scheduled Job Types: `utils.allocate_earned_leaves` **stopped = 1**, `utils.allocate_earned_leaves_bs` stopped = 0. With 0 allocations on the site, it credits nothing. |
| **Gotcha** | If someone re-enables the stock job, every credit lands twice. |

### 7.5 Mid-year policy assignment: `BSLeavePolicyAssignment`

[`BSLeavePolicyAssignment`](../../avinashgroup_app/hr/leave_policy_assignment_bs.py#L44) (class override registered at [`BSLeavePolicyAssignment`](../../avinashgroup_app/hooks.py#L529)) overrides HRMS's [`get_leaves_for_passed_months`](../../../hrms/hrms/hr/doctype/leave_policy_assignment/leave_policy_assignment.py#L175). The back-fill for months already gone is counted in **BS** months ([`bs_months_backfill`](../../avinashgroup_app/hr/leave_policy_assignment_bs.py#L64)), matching what the BS job would have credited. Why: assigned on 24 Ashwin, HRMS counts 3 AD months where BS has completed 2, and the BS job then adds Ashwin, so the employee holds one month too many for the whole year (commit `24b12af`). Other configurations fall back to stock.

### 7.6 Replacement leave type

Credited per worked holiday as a Compensatory Leave Request by `hr/replacement_leave.py`, only for Overtime Sheet rows whose entitlement is Replacement Leave (the employee ticked **Replacement Leave for Holiday Work** when the row was saved) and only after attendance shows the day was worked (`on_sheet_submit` plus the daily [`grant_pending`](../../avinashgroup_app/hr/replacement_leave.py#L156)). Covered in [04-overtime.md](04-overtime.md).

---

## 8. Fiscal Year (BS)

| | |
|---|---|
| **What** | Stock ERPNext Fiscal Year, named in BS (`83/84`), running 1 Shrawan → end of Ashadh (mid-July → mid-July), with a company row for each of the 7 companies. |
| **Why it matters to HR** | (1) **Naming:** `NAMING_CONFIG` gives Attendance, Leave Application, Leave Allocation, Payroll Entry and Salary Slip `use_fiscal_year = True`. `naming_requirements_before_insert` (`custom_code/Override/naming_series.py`) looks up a Fiscal Year spanning `posting_date` / `attendance_date` / `custom_created_on` and **throws "No fiscal year found"** if none exists. Run from bench with no request, Leave Allocation has no `custom_created_on`, so `setup_year` sets `frappe.flags.audit_user` to avoid exactly that refusal ([`setup_year`](../../avinashgroup_app/hr/year_setup.py#L65)). (2) **Holiday year switch** picks the year spanning today. (3) **BS calendar** (`bs_calendar.bs_year_of`) reads `year_start_date` to know which BS year Baisakh–Ashadh belong to. (4) Payroll Period, Leave Period, holiday lists and the tax slab are all created per fiscal year by `setup_year`. |
| **Config on avinas1** | `83/84` 2026-07-17 → 2027-07-16; `82/83` 2025-07-17 → 2026-07-16; `81/82`, `80/81` also present. Both 82/83 and 83/84 carry all 7 companies. **`84/85` does not exist yet** (needed before 2027-07-17). |
| **Gotcha** | See [09-cross-cutting.md](09-cross-cutting.md) for the naming engine. A missing next-year Fiscal Year stops every attendance insert from 1 Shrawan. |

---

## 9. BS calendar: `hr/bs_calendar.py`, Nepal BS Period, Nepal HRMS Settings

| | |
|---|---|
| **What** | One answer to "which AD dates does BS month X cover", for Payroll Entry, the salary statement, the tax/SSF deposit report and the monthly attendance report. The order of lookup is: the company's **Nepal BS Period** row, then the global row, then the plain Nepali calendar. That is the same order the BS Salary Slip uses (`get_user_defined_period` in rdp_common_app), so **a payroll and its slips always cover the same days.** |
| **Why** | Screens used to work the month out differently: one report guessed "BS months start around the 16th", and a Payroll Entry took whatever posting date was typed. They could disagree, and a payroll posted on the wrong day silently became the next month's payroll. Docstring of [`Which English dates a BS month covers`](../../avinashgroup_app/hr/bs_calendar.py#L1); commits `df53710`, `714edfc` (2026-10-09). |
| **Where** | [`month_period`](../../avinashgroup_app/hr/bs_calendar.py#L88) (by month), [`month_of_date`](../../avinashgroup_app/hr/bs_calendar.py#L127) (by date, via rdp's [`get_user_defined_period`](../../../rdp_common_app/rdp_common_app/nepal_hrms_common/doctype/nepal_bs_period/nepal_bs_period.py#L109) or [`get_salary_period`](../../../rdp_common_app/rdp_common_app/utils/bs_boundaries.py#L162)), [`bs_year_of`](../../avinashgroup_app/hr/bs_calendar.py#L69), [`FISCAL_ORDER`](../../avinashgroup_app/hr/bs_calendar.py#L41) (Shrawan first), [`get_default_month`](../../avinashgroup_app/hr/bs_calendar.py#L165) (last finished month, a whitelisted call from report filters). Low-level conversion: rdp's [`ad_to_bs`](../../../rdp_common_app/rdp_common_app/utils/bs_boundaries.py#L50), [`get_bs_month_range`](../../../rdp_common_app/rdp_common_app/utils/bs_boundaries.py#L145). |
| **Nepal BS Period** (rdp_common_app) | A fiscal year's 12 months, company-specific or global, each with a start and end date that HR **can move**. Fields: `company`, `bs_year`, and a `months` table (`bs_year`, `bs_month`, `start_date`, `end_date`). |
| **Nepal HRMS Settings** (rdp_common_app, Single) | `process_payroll_in_nepali_month` switches on the BS Salary Slip class and our BS period guard ([05](05-payroll-entry.md), [06](06-salary-slip.md)); `year_setup.ensure_nepali_payroll` forces it to 1. `restrict_to_nepal_companies`. |
| **Impacts downstream** | Payroll Entry start/end/posting date ([05](05-payroll-entry.md)); slip period and `total_working_days` = BS month length ([06](06-salary-slip.md)); hourly basic for OT and late fine = base ÷ the BS month's actual days ([05](05-payroll-entry.md)); leave accrual day (§7.4); report month filters. **Moving a border** in Nepal BS Period moves all of these together, but only for payrolls created afterwards. |
| **Config on avinas1** | **No Nepal BS Period records**, so every month comes from the Nepali calendar. Settings: `process_payroll_in_nepali_month = 1`, `restrict_to_nepal_companies = 1`. |
| **Gotcha** | `nepal_hrms` (the separate app under `apps/`) is **not installed** on avinas1. Nepal HRMS Settings and Nepal BS Period come from `rdp_common_app/nepal_hrms_common`. |

---

## 10. `year_setup`: one call per fiscal year

| | |
|---|---|
| **What** | [`setup_year`](../../avinashgroup_app/hr/year_setup.py#L65)`(fiscal_year)` puts a year in place for every company, and is safe to re-run (creates only what is missing). Per company: common + Women holiday lists (Saturdays only, [`ensure_holiday_list`](../../avinashgroup_app/hr/year_setup.py#L235)); company defaults — holiday list, Salary Payable, Staff Advance, found by account **name** ([`ensure_company_defaults`](../../avinashgroup_app/hr/year_setup.py#L268)); Leave Period ([`ensure_leave_period`](../../avinashgroup_app/hr/year_setup.py#L299)); Payroll Period `"<FY> - <ABBR>"` ([`ensure_payroll_period`](../../avinashgroup_app/hr/year_setup.py#L335)); Income Tax Slab `"Nepal <FY> - <ABBR>"` from [`TAX_SLABS_BY_YEAR`](../../avinashgroup_app/payroll/income_tax.py#L45) unless one is already entered ([`ensure_income_tax_slab`](../../avinashgroup_app/hr/year_setup.py#L355)); salary rollover ([`roll_salary_assignments`](../../avinashgroup_app/payroll/year_rollover.py#L50), see [08](08-changes-over-time.md)); Leave Policy Assignment per active employee, Probation vs Regular by `employment_type` ([`assign_leave_policies`](../../avinashgroup_app/hr/year_setup.py#L398)). Group-wide: leave types re-asserted, Nepal HRMS Settings BS on. |
| **Why** | "A year cannot start until a holiday list, a leave period, a payroll period, an income tax slab and a leave policy assignment exist for every company. Miss one and the failure comes much later" (module docstring). Commits `3ab584f`, `adc2b61`, `24b12af`. |
| **What it refuses to invent** | [`require_standing_setup`](../../avinashgroup_app/hr/year_setup.py#L128) collects every missing item and refuses: per company, no Shift Type, or no submitted Leave Policy titled `<ABBR> Regular <FY>` and `<ABBR> Probation <FY>`. [`require_tax_table`](../../avinashgroup_app/hr/year_setup.py#L167): no slab rates for the year. The code used to hold guessed shifts, entitlements and festival dates, and "a wrong shift or entitlement is worse than a missing one". |
| **What it deliberately does not do** | Put festivals on the lists (HR enters them with Holiday Bulk Update; it prints a warning per new list). Build a first salary structure (that is `onboarding`). Change pay (Salary Revision). Switch people to the new lists (`holiday_year_switch`, on the day). |
| **Triggered by** | Manual: `bench --site avinas1 execute avinashgroup_app.hr.year_setup.setup_year --kwargs "{'fiscal_year': '83/84'}"`. Test script: `scripts/check_year_rollover.py`. |
| **Config on avinas1** | Payroll Periods for all 7 and 8 holiday lists for 83/84 exist, but there are **no Leave Periods, Leave Policies or Leave Policy Assignments**, and GLMI/GEPL/SGU have no Shift Type. Today `require_standing_setup` would refuse 83/84 for all 7 companies (no policies anywhere). So the 83/84 objects on avinas1 were made by an earlier version or partly by hand (**unverified**). |
| **Gotchas** | (1) The holiday-list and payroll-period checks look things up by title or start date, so a list renamed by hand gets a second list created next to it. (2) `ensure_company_defaults` fills only blank fields; it never corrects a wrong account. (3) [`ensure_leave_types`](../../avinashgroup_app/hr/year_setup.py#L216) resets leave-type flags HR may have changed on the desk. (4) For 84/85 the tax table must be added first, or the run refuses: "Last year's rates are never copied". |

---

## 11. `onboarding`: putting a company's payroll on the system from its Excel sheet

| | |
|---|---|
| **What** | It reads a company's monthly salary workbook and builds that company's payroll: components, a salary structure with its Allowance Rates ([`setup_company`](../../avinashgroup_app/payroll/onboarding.py#L224)); matches sheet rows to Employees by code or name ([`EmployeeMatcher`](../../avinashgroup_app/payroll/onboarding.py#L516)); sets the employee's Department from the sheet ([`set_department`](../../avinashgroup_app/payroll/onboarding.py#L360)); and submits a Salary Structure Assignment from the fiscal year's start with base, Initial Basic, SSF Applicable and the person's Allowances rows ([`import_sheet`](../../avinashgroup_app/payroll/onboarding.py#L327), [`assign`](../../avinashgroup_app/payroll/onboarding.py#L473)). [`check_against_sheet`](../../avinashgroup_app/payroll/onboarding.py#L579) compares computed slips with the sheet's totals. [`map_component_accounts`](../../avinashgroup_app/payroll/onboarding.py#L663) proposes O/O, S/D and F/P accounts. Entry: [`onboard`](../../avinashgroup_app/payroll/onboarding.py#L172). |
| **Why** | Every company already runs payroll in Excel, and the sheet is the only record of who gets which allowance, at what rate, and who is in SSF. Onboarding means reading the sheet, not retyping it. There are two pay models: **Initial-basic** (NGI, NGN: HRA as a % of a separate Initial Basic, flat gas/education, tea old/new rates) and **Grade-scale** (NGG, NGK: government scale, SSF on the scale, no HRA/gas/education). Per-company rates are in [`PROFILES`](../../avinashgroup_app/payroll/onboarding.py#L56) (e.g. NGN pays HRA at 27%, NGI at 25%). Commit `448d685` (2026-09-21). |
| **Triggered by** | Manual `bench execute avinashgroup_app.payroll.onboarding.onboard --kwargs "{'key': 'NGN', 'path': '…xlsx'}"`. Safe to re-run. |
| **Writes** | Salary Component (+ account rows), Salary Structure, Salary Structure Assignment, `Employee.department`, payable account. |
| **Impacts downstream** | Everything pay-related ([01b](01b-pay-masters.md), [06](06-salary-slip.md)). |
| **Gotchas** | [`FISCAL_YEAR`](../../avinashgroup_app/payroll/onboarding.py#L51) is hard-coded `"83/84"`, and column letters per company (`cols`) are fixed to the Falgun 2082 sheet layout. A different month's sheet with moved columns imports wrong figures silently unless `check_against_sheet` is run. Sheets: see memory reference `~/Downloads/salary detial for samita jee/{NGI,NGN,NGG,NGK}.xlsx`. GLMI, GEPL and SGU have no profile. |

---

## 12. Stock vs ours: summary

| Area | Stock HRMS / ERPNext does | We add / change |
|---|---|---|
| Employee | Fields, unique `attendance_device_id`, `get_holiday_list_for_employee` fallback | Overtime Eligible / Replacement Leave ticks, Late Fine Exempt, Women's Rebate tick, per-company device-ID uniqueness, BS mitis, PAN/SSF fields (site-only) |
| Holiday List | One list per employee, weekly-off generator | Per-company/per-FY common + Women lists, `custom_company`, bulk add + attendance follow-up, daily year switch |
| Shift Type | Auto attendance, thresholds, grace | `custom_company` (naming), late-hours half-day rule, cutoff guard, rotation flag |
| Shift Assignment / Request | Overlap refusal | Make-room/resume, backdate rebuild + paid-period lock, bulk rotation, roster page |
| Leave | Earned leave on AD months; passed-months back-fill on AD | BS accrual job (stock job stopped), BS back-fill override, annual ceiling, gender gate, leave-type definitions |
| Fiscal year / calendar | AD fiscal year rows | BS names; Nepal BS Period + BS calendar module; fiscal-year-based naming that throws without a year |
| Year start | n/a | `setup_year`, `holiday_year_switch`, `year_rollover` |

## Open issues found while writing this page

- avinas1 has no device IDs, checkins, shift assignments, leave policies, allocations, or overtime / replacement-leave ticks for 98% of staff. The pipeline in [02](02-checkin-to-attendance.md)–[05](05-payroll-entry.md) cannot run end to end on this data. Verify against the live client site before relying on any count here.
- `custom_pan` and `custom_ssf_id_no` exist only as site data. A fresh site would lose PAN and SSF number on the payslip and the deposit report. Same situation `add_site_only_hr_fields` fixed for other fields.
- `Causal Leave` (typo) Leave Type on avinas1.
- `Remove Holiday` path in `hr/holiday_lists.py` is dead code.
- 84/85 Fiscal Year not created; next rollover deadline is 2027-07-17.
