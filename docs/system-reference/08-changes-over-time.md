# 08 · Changes over time

How pay changes after the first month: raises and allowance changes (Salary Revision), the new fiscal year (rollover), one-off amounts (Payroll Adjustment, hand-made Additional Salary), festival allowance, advances, undoing a month (cancel / amend), and leave encashment.

The single rule behind every section of this page: **a salary is a dated fact, never an edit.** Pay lives on a Salary Structure Assignment (see [01b-pay-masters.md](01b-pay-masters.md)); a change makes a *new* assignment from a date, and a past month that was already paid is corrected with a *new* amount in a later month, never by editing a submitted slip. ([module notes, `A pay rise`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L1) say why: HRMS picks one assignment per slip, so a slip is paid at one rate for its whole month.)

Values marked "avinas1" were read from the database on 2026-10-12.

## Contents

1. [Salary Revision (raises and allowance changes)](#1-salary-revision)
2. [Year rollover (new fiscal year)](#2-year-rollover)
3. [One-off amounts: Payroll Adjustment](#3-payroll-adjustment)
4. [Additional Salary entered by hand, and how the engine leaves it alone](#4-additional-salary-by-hand)
5. [Festival allowance (Dashain)](#5-festival-allowance-dashain)
6. [Advances recovered from salary](#6-advances-recovered-from-salary)
7. [Cancelling and amending: slip, payroll entry, backdated changes](#7-cancelling-and-amending)
8. [Joiners, leavers, final settlement, leave encashment](#8-joiners-leavers-final-settlement-leave-encashment)
9. [What exists on avinas1 today](#9-what-exists-on-avinas1-today)

---

## 1. Salary Revision

| | |
|---|---|
| **What** | A submittable document (`SREV-.YYYY.-`) that, for a list of employees of one company, creates a new submitted Salary Structure Assignment from an effective date (new Basic, new Dearness Allowance, allowance changes, everything else carried over), optionally pays arrears for months already paid, and moves a structure's listed allowance rate. |
| **Why** | Increments are agreed late (the rise runs from Shrawan, the meeting is in Mangsir). Editing a submitted assignment or slip would break last year's slips vs. journals. Arrears are a one-off amount in the month they are paid. Source: [module notes, `A pay rise`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L1); commits `8777a6b` "A pay rise is a dated fact, not an edit" (2026-09-21), `77b9500` (2026-10-08, pay moved to the assignment), `975437c` (2026-10-12, allowance rate list). User view: [user-guide 8.1](../user-guide/08-raises-advances-bonuses-year-end.md). |
| **Stock HRMS** | Has no raise document. HRMS only offers a new Salary Structure Assignment by hand; it has no arrears logic. Everything below is ours. |
| **Where** | Controller [`SalaryRevision`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L65); form [`"Salary Revision"` form script](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.js#L6); child tables `Salary Revision Row` (employees) and `Salary Revision Allowance` (allowance changes); install patch [`execute`](../../avinashgroup_app/patches/setup_salary_revision.py#L10) (creates the `Salary Arrears` component). |
| **Triggered by** | HR: New → Get Employees → Save → Submit. Cancel undoes. |
| **Permissions** | HR Manager and System Manager only (create/submit/cancel). HR User cannot see it. |

### 1.1 Fields that drive it

| Field | Meaning | Read by |
|---|---|---|
| `company`, `effective_date` | Whose pay, from when. Effective date **must be day 1 of a BS month** | [`validate_effective_date`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L228) |
| `bs_month` | Display only, set from the effective date | [`set_bs_month`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L246) |
| `default_increment_percent` | "Hike % for everyone"; with it Get Employees lists everyone with a salary | [`get_employees`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L423) |
| `pay_arrears`, `arrears_payout_date` | Pay the months already paid; the payout date is mandatory when ticked (`mandatory_depends_on`) and picks the BS month the arrears land in | [`pay_the_arrears`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L397) |
| `employees[]` (Salary Revision Row) | `current_base`, `new_base`, `increment_percent`, `current_/new_dearness_allowance`, `arrears_months`, `arrears_amount`, `allowance_summary`; after submit `salary_structure_assignment`, `arrears_additional_salary` | whole controller |
| `allowance_changes[]` (Salary Revision Allowance) | `change` (Raise Rate / Add / Stop / Change Rate), `allowance`, `salary_structure` (Raise only), `old_rate`, `new_rate`, `unit` | [`validate_allowance_changes`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L75), [`plan_allowances`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L129) |

### 1.2 The four allowance changes

| Change | Reaches | Effect | Refused when |
|---|---|---|---|
| **Raise Rate** | People on the named structure whose rate equals the structure's listed rate | Their row's rate → New Rate; the structure's Allowance Rates row too ([`set_structure_rates`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L326)). People on their own rate are named, not raised | structure not of this company; structure lists no rate; new = old; the allowance is computed from basic ([`rate_is_computed`](../../avinashgroup_app/payroll/allowance.py#L182)) |
| **Add** | Listed people without the allowance | New row at New Rate, else the structure's rate ([`structure_rate`](../../avinashgroup_app/payroll/allowance.py#L207)) | no rate anywhere and the rate is not computed |
| **Stop** | Listed people who have it | Row removed (`new_rate` forced to 0) | — |
| **Change Rate** | Listed people who have it | Row rate → New Rate | computed-rate allowance (Overtime, Late Fine) |

Only allowances paid from the assignment can be changed: kinds `Entered by Hand` and `Yearly` are refused ([`NOT_ON_ASSIGNMENT`](../../avinashgroup_app/payroll/allowance.py#L81); the form filters them out too, [`NOT_ON_ASSIGNMENT`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.js#L4)).

### 1.3 Validate (every save)

[`validate`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L66) runs, in order:

1. `set_bs_month`.
2. `validate_effective_date` — not day 1 of a BS month → refused, with the date to use. Uses `rdp_common_app.utils.bs_boundaries` (`ad_to_bs`, `bs_to_ad`).
3. `validate_allowance_changes` — table rules above; sets `unit`, freezes `old_rate` from the structure while draft.
4. [`validate_rows`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L176) — per employee: listed once, belongs to the company, has an assignment in force on the effective date ([`current_assignment`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L499)), new basic > 0 (blank = unchanged), dearness taken from the allowance change if there is one, `allowance_summary`, `arrears_months` ([`months_already_paid`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L510)), `arrears_amount`; refuses a person who already has a submitted assignment from exactly that date.
5. [`set_totals`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L290) — `employee_count`, `total_increase` (sum of [`monthly_increase`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L256)), `total_arrears`.

### 1.4 Arrears: how the number is made

[`arrears`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L270) = two parts:

| Part | Formula | Code |
|---|---|---|
| Monthly pay (Basic, Dearness, other `Monthly` and `% of Initial Basic` allowances) | Σ over submitted slips with `start_date ≥ effective_date`: `monthly_increase × payment_days ÷ total_working_days` | [`arrears_for`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L518), [`_monthly_allowances`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L486) |
| Attendance allowances with a fixed rate (Tea & Conveyance, Meal) | `(new rate − old rate) × quantity the engine counts again for those months` | [`attendance_qty_paid`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L535) → [`_qty_for_employee`](../../avinashgroup_app/payroll/attendance_allowance.py#L273), [`_attendance_period`](../../avinashgroup_app/payroll/attendance_allowance.py#L684), [`_skip_for_eligibility`](../../avinashgroup_app/payroll/attendance_allowance.py#L665) |

The arrears are paid as one **Additional Salary** of component `Salary Arrears` ([`ARREARS_COMPONENT`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L60), created by [`ensure_arrears_component`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L560): Earning, taxable, not prorated, rounded) dated `arrears_payout_date`, `deduct_full_tax_on_selected_payroll_date = 1`, `overwrite_salary_structure_amount = 0`. No `custom_source` tag, so Prepare Payroll Inputs never touches it (section 4).

### 1.5 Submit and cancel

| Step | Code | Writes |
|---|---|---|
| For each row: new assignment | [`assign_new_salary`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L350) | New submitted **Salary Structure Assignment** from `effective_date`: same structure, `base = new_base`, same `variable`, currency, payable account, `custom_initial_basic`, `custom_ssf_applicable`; **income tax slab = the slab in force on the effective date** ([`tax_slab_for`](../../avinashgroup_app/payroll/year_rollover.py#L35)), else the old one; `custom_allowances` = planned rows; Dearness row set by [`set_dearness`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L384). Row field `salary_structure_assignment` |
| For each row: arrears | [`pay_the_arrears`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L397) | Submitted **Additional Salary** `Salary Arrears`; row field `arrears_additional_salary` |
| Raise Rate → structure | [`set_structure_rates`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L326) | Saves the submitted **Salary Structure**'s `custom_allowance_rates` row with `frappe.flags.in_salary_revision` set, the only way past [`guard_structure_rates`](../../avinashgroup_app/payroll/allowance.py#L494) (hook [`guard_structure_rates`](../../avinashgroup_app/hooks.py#L489)) |
| Cancel | [`on_cancel`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L307) | Cancels the arrears Additional Salary and the new assignments; puts a raised structure rate back only if it still equals what this revision set |

### 1.6 Impacts downstream

- Every slip from the effective month picks the new assignment ([`check_sal_struct`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L385) takes the latest assignment on or before the slip's period) → new `base` → Basic, SSF Addition and SSF (structure formulas `base`, `B * 0.20`, `B * 0.31`), `% of Initial Basic` allowances, the hourly basic behind Overtime and Late Fine ([06-salary-slip.md](06-salary-slip.md), [05-payroll-entry.md](05-payroll-entry.md)).
- The assignment's Allowances table drives both the fixed allowances on the slip and who gets attendance allowances (Prepare Payroll Inputs).
- The slab on the new assignment decides the tax on every later slip.
- The arrears Additional Salary is taxed in full in its payout month.

### 1.7 Gotchas / open issues

- **Overtime and Late Fine have no arrears.** They are priced from the hourly basic, and `arrears` skips computed-rate components ([`rate_is_computed`](../../avinashgroup_app/avinash_group_app/doctype/salary_revision/salary_revision.py#L283)). A backdated basic raise pays no OT difference for months already paid.
- **No SSF on arrears.** SSF and SSF Addition are structure formulas on the slip's `B`; `Salary Arrears` is a separate earning, so the basic difference in arrears carries no 20 % / 31 %. Whether the SSF Fund expects contributions on arrears is a client/legal question (unverified).
- **Attendance arrears are counted again from today's attendance**, not read from the paid slips. If attendance was corrected after a month was paid, the tea/meal arrears follow the corrected attendance.
- `months_already_paid` counts any submitted slip with `start_date ≥ effective_date`; a revision effective in the future has 0 arrears even if ticked.
- One assignment per person per date: a second revision from the same date for the same person is refused — combine them, or cancel the first.
- `validate_effective_date` only blocks mid-month dates; it does not stop an effective date earlier than the person's current assignment (that case becomes a new assignment in the past; HRMS then uses it for slips not yet made). Unverified edge case.
- avinas1: **no Salary Revision has been made yet** (0 rows on 2026-10-12).

---

## 2. Year rollover

| | |
|---|---|
| **What** | On the new fiscal year's first day, every active employee gets a new submitted assignment with the same pay and the **new year's Income Tax Slab**. |
| **Why** | HRMS reads the slab from the assignment ([`get_income_tax_slabs`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1592)) and only checks that it started on or before the payroll period. Without a rollover, all 84/85 slips would silently be taxed at 83/84 rates. Source: [module notes, `Carrying everyone's pay`](../../avinashgroup_app/payroll/year_rollover.py#L1); commits `24b12af` (2026-09-24) and `6a37bc5` (2026-10-09, "year rollover keeps a person's whole pay" — before it the new assignments lost HRA, SSF and every allowance). Doc: [payroll-handover.md §9 "Year rollover"](../payroll-handover.md), [user-guide 8.7](../user-guide/08-raises-advances-bonuses-year-end.md). |
| **Stock HRMS** | Nothing. Ours entirely. |
| **Where** | [`roll_salary_assignments`](../../avinashgroup_app/payroll/year_rollover.py#L50), [`tax_slab_for`](../../avinashgroup_app/payroll/year_rollover.py#L35); called from [`setup_year`](../../avinashgroup_app/hr/year_setup.py#L65) at [`roll_salary_assignments`](../../avinashgroup_app/hr/year_setup.py#L115). |
| **Triggered by** | IT, once a year, by hand: `bench --site avinas1 execute avinashgroup_app.hr.year_setup.setup_year --kwargs "{'fiscal_year': '84/85'}"`. Not scheduled. |
| **Reads** | Income Tax Slab (company, `effective_from`, submitted, not disabled); Employee (Active); latest assignment before the year: structure, base, variable, currency, payable account, `custom_initial_basic`, `custom_ssf_applicable`, Assignment Allowance rows. |
| **Writes** | One new submitted Salary Structure Assignment per active employee, `from_date` = year start, `income_tax_slab` = the new slab. Allowance rows copied with **blank From Date**. |

### 2.1 The pay-related parts of `setup_year`

`setup_year` builds everything a year needs (holiday lists, leave period, leave policies: see [01-masters.md](01-masters.md)). The pay parts, in order:

| Step | Function | Effect on pay |
|---|---|---|
| Tax table must exist | [`require_tax_table`](../../avinashgroup_app/hr/year_setup.py#L167) | Refuses the whole run unless every company has a submitted slab for the year, or the year is in [`TAX_SLABS_BY_YEAR`](../../avinashgroup_app/payroll/income_tax.py#L45) |
| BS payroll on | [`ensure_nepali_payroll`](../../avinashgroup_app/hr/year_setup.py#L201) | Ticks Nepal HRMS Settings `process_payroll_in_nepali_month` |
| Payroll Period | [`ensure_payroll_period`](../../avinashgroup_app/hr/year_setup.py#L335) | `<FY> - <ABBR>`, year start to end. HRMS's tax projection needs it |
| Income Tax Slab | [`ensure_income_tax_slab`](../../avinashgroup_app/hr/year_setup.py#L355) | Keeps an existing submitted slab, else builds `Nepal <FY> - <ABBR>` from `TAX_SLABS_BY_YEAR`, `allow_tax_exemption = 1` |
| Roll pay | `roll_salary_assignments` | As above |

### 2.2 Impacts and gotchas

- **Women's rebate is carried (fixed 2026-10-12).** `ensure_income_tax_slab` sets `custom_women_rebate_percent` from `WOMEN_REBATE_BY_YEAR` in payroll/income_tax.py, and `require_tax_table` refuses a year that has rates but no rebate figure. See [06-salary-slip.md](06-salary-slip.md).
- **People already on a new-year assignment are skipped** (an early revision or a joiner), so they keep whatever slab their own assignment names.
- Allowance rows lose any future From Date — the row starts with the new assignment.
- Only `Active` employees roll. Someone on leave-without-pay status "Inactive" (unverified whether HR uses it) would be left on the old slab.
- `setup_year` must run **before** 1 Shrawan, but the holiday-list switch must run **on** 1 Shrawan; that part is the daily job [`switch_to_current_year_lists`](../../avinashgroup_app/hr/holiday_year_switch.py#L30), which does not run while the scheduler is off (see [09-cross-cutting.md](09-cross-cutting.md#5-scheduler-jobs)).
- Doc vs. DB: [payroll-handover.md](../payroll-handover.md) says "84/85 exists on avinas1 since 2026-09-24" and the module notes say "All 205 assignments". On 2026-10-12 avinas1 has **no 84/85 Fiscal Year** (latest is 83/84; the 84/85 run was inside a rolled-back test) and **195** submitted assignments, all `from_date` 2026-07-17. The user guide (8.7) is the accurate one.
- Rolled-back proof script: [`Rolled-back check` (scripts/check_year_rollover.py)](../../avinashgroup_app/scripts/check_year_rollover.py#L1) — it hard-codes `sites_path="/home/sijan/frappe-15/sites"`, so it does not run on this bench without editing the path.

### 2.3 Config on avinas1 (2026-10-12)

| Item | Value |
|---|---|
| Fiscal Years | 83/84 (latest), 82/83, 81/82 |
| Payroll Periods | `83/84 - <ABBR>` × 7, 2026-07-17 → 2027-07-16 |
| Income Tax Slabs | `Nepal 83/84 - <ABBR>` × 7, effective 2026-07-17, submitted, `custom_women_rebate_percent = 10` on all |
| Salary Structure Assignments | 195 submitted, all from 2026-07-17 |

---

## 3. Payroll Adjustment

| | |
|---|---|
| **What** | One submittable document per company and month (`PADJ-.YYYY.-`), one row per employee × component × amount. Submit creates and submits one Additional Salary per row; cancel cancels them. |
| **Why** | NGI's salary sheet types one-offs (SST, load/unload, a correction, a festival payment) as columns. One Additional Salary per person is "fine for two people and miserable for twenty". Nothing is calculated: the amount is the decision. Source: [module notes, `The month's one-off amounts`](../../avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py#L1); commit `2fc4972` (2026-09-21). User view: [user-guide 8.2](../user-guide/08-raises-advances-bonuses-year-end.md). |
| **Stock HRMS** | Additional Salary one at a time, or Bulk Salary Structure Assignment (not for one-offs). Ours is the bulk screen. |
| **Where** | [`PayrollAdjustment`](../../avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py#L28): [`validate`](../../avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py#L29), [`on_submit`](../../avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py#L81), [`on_cancel`](../../avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py#L111); form [`set_query`](../../avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.js#L9); install patch [`execute`](../../avinashgroup_app/patches/setup_payroll_adjustment.py#L6). |
| **Permissions** | HR Manager, System Manager. |
| **Reads / Writes** | Reads Employee `company`, Salary Component `type`. Writes Additional Salary (`payroll_date` = the document's date, `overwrite_salary_structure_amount = 0`, `deduct_full_tax_on_selected_payroll_date = 1` for earnings, `notes`), row field `additional_salary`; header `bs_month`, `total_earnings`, `total_deductions`. |
| **Impacts** | The month's slips pick the rows up through HRMS `add_additional_salary_components` ([06-salary-slip.md](06-salary-slip.md)). Submit and cancel re-save the listed people's draft slips covering `payroll_date` ([`refresh_slips_covering`](../../avinashgroup_app/payroll/attendance_allowance.py#L125)). |

Gotchas:

- **Attendance-driven components are blocked only in the form** (`custom_is_attendance_driven: 0` filter in JS). The server accepts them; a row for Tea or Overtime created by import or API would sit beside the engine's row and pay twice.
- A component with **Depends on Payment Days** is prorated by HRMS even when it arrives as an Additional Salary ([`get_amount_based_on_payment_days`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L1795) prorates `additional_amount`). `Leave Encashment` had `depends_on_payment_days = 1` until 2026-10-13 ([`execute` in patch setup_leave_encashment](../../avinashgroup_app/patches/setup_leave_encashment.py#L26) set it to 0); `Salary Arrears`, `Dashain Bonus`, `Dashain Allowance` are 0 too. Load/Unload still prorates.
- Deductions are entered as positive amounts on a Deduction component (amount ≤ 0 is refused).
- avinas1: **0 Payroll Adjustments** on 2026-10-12.

---

## 4. Additional Salary by hand

Three writers of Additional Salary exist, told apart by `custom_source` (Data, read-only, added by [`custom_source` in patch setup_attendance_allowance](../../avinashgroup_app/patches/setup_attendance_allowance.py#L150)):

| Writer | `custom_source` | Replaced on re-run? |
|---|---|---|
| Prepare Payroll Inputs, attendance engine | `Nepal HRMS Attendance Allowance` ([`SOURCE_TAG`](../../avinashgroup_app/payroll/attendance_allowance.py#L38)) | Yes: [`_delete_existing_draft`](../../avinashgroup_app/payroll/attendance_allowance.py#L790) cancels and deletes the earlier row for the same employee + component + `payroll_date` with this tag |
| Prepare Payroll Inputs, advance instalments | `Advance Recovery` ([`SOURCE_TAG`](../../avinashgroup_app/payroll/advance_recovery.py#L31)) | Yes: [`clear_month`](../../avinashgroup_app/payroll/advance_recovery.py#L150) cancels (does not delete) the month's earlier rows |
| HR by hand, Payroll Adjustment, Salary Revision arrears | blank | Never touched by any job |

**Overwrite safety.** The engine's rows are `overwrite_salary_structure_amount = 0`, so HRMS **adds** them to anything else on the same component ([`_make_additional_salary`](../../avinashgroup_app/payroll/attendance_allowance.py#L827)). HRMS's own default for a hand-made Additional Salary is `overwrite_salary_structure_amount = 1` (hrms JSON default), which replaces the structure amount of that component, and [`validate_duplicate_additional_salary`](../../../hrms/hrms/payroll/doctype/additional_salary/additional_salary.py#L120) allows only one overwriting row per component and date.

Practical consequences:

| HR types by hand… | Result |
|---|---|
| A one-off on a component nobody else posts (e.g. a bonus) | Paid as typed; taxed in its month only if HR ticks *Deduct Full Tax on Selected Payroll Date* (Payroll Adjustment ticks it for you) |
| An extra Overtime / Tea / Meal / Late Fine amount for the month | Added on top of the engine's row (both stand; the engine never deletes it). Use with care |
| A Basic / SSF line with *Overwrite* left on | Replaces the structure's formula amount for that month |

`custom_quantity` / `custom_rate` (from [`execute` in patch setup_additional_salary_quantity](../../avinashgroup_app/patches/setup_additional_salary_quantity.py#L19)) are filled only by the engine and read by the Avinas Salary Statement report; hand rows show blank quantity there.

avinas1 on 2026-10-12: 10 submitted Additional Salary rows, all from the attendance engine (Tea & Conveyance 4, Overtime 2, Meal 2, Late Fine 2); none by hand.

---

## 5. Festival allowance (Dashain)

| | |
|---|---|
| **What** | A **Dashain Allowance** button on the Payroll Entry (Nepal HRMS group) writes a **draft Payroll Adjustment** for the entry's company and month, one row per employee: one month's basic × service factor. HR reviews and submits; submit creates the Additional Salary (section 3). |
| **Rule** (user, 2026-10-13) | Basic = the Salary Structure Assignment `base` in force on the cut-off date (what the structures' `Basic` row pays, formula `base`); nothing added or deducted. Service days = cut-off − `date_of_joining`; year days = cut-off − the same date a year earlier (365/366). Factor = 1 if joined on or before that date, else service ÷ year days, clamped 0..1. Amount = basic × factor ≤ basic. Joined on/after the cut-off → not listed. [`service_factor`](../../avinashgroup_app/payroll/festival_allowance.py#L75), [`festival_amount`](../../avinashgroup_app/payroll/festival_allowance.py#L95), [`monthly_basic`](../../avinashgroup_app/payroll/festival_allowance.py#L103) |
| **Why** | The festival allowance had no way in except hand-typed amounts; the 2026-09-29 decision against a document of its own is kept by writing onto the existing Payroll Adjustment. Source: [module notes, `Dashain (festival) allowance`](../../avinashgroup_app/payroll/festival_allowance.py#L1). User view: [user-guide 8.4](../user-guide/08-raises-advances-bonuses-year-end.md). |
| **Settings (data)** | On the Salary Component, section *Festival Allowance* ([`execute` in patch setup_festival_allowance](../../avinashgroup_app/patches/setup_festival_allowance.py#L44)): `custom_is_festival_allowance`, `custom_festival_pay_month` (BS month option, the button refuses another month), `custom_festival_min_service_days`, `custom_festival_prorate`, `custom_festival_include_daily_wage`, `custom_festival_include_leavers` (counted to the relieving date when on). avinas1: only `Dashain Allowance` is ticked — Ashwin, 0, ✓, ✗, ✗. `Dashain Bonus` exists but is not ticked. |
| **Where** | [`make_festival_adjustment`](../../avinashgroup_app/payroll/festival_allowance.py#L235) (whitelisted; the button), [`compute_rows`](../../avinashgroup_app/payroll/festival_allowance.py#L122) (pure), [`paid_already`](../../avinashgroup_app/payroll/festival_allowance.py#L195), [`get_defaults`](../../avinashgroup_app/payroll/festival_allowance.py#L223); run by [`_pay_dashain`](../../avinashgroup_app/payroll/payroll_entry.py#L96) when the entry has Pay Dashain Allowance ticked (a form button until 2026-10-15). Payroll Adjustment fields `payroll_entry`, `source` (`Festival Allowance: <component>`), `cutoff_date`; row fields `date_of_joining`, `base_amount`, `service_days`, `year_days`, `prorate_factor`. |
| **Idempotency** | Draft for this entry + source → rebuilt in place (deleted if nobody is due). Another draft for the same company/source/payroll period → refused. A submitted Additional Salary on the component within the payroll period → that person is left out ("already paid"). [`PayrollAdjustment.validate_rows`](../../avinashgroup_app/avinash_group_app/doctype/payroll_adjustment/payroll_adjustment.py#L34) refuses `amount > base_amount` (the 100 % cap holds after hand edits). |
| **Tax** | Payroll Adjustment sets `deduct_full_tax_on_selected_payroll_date = 1`, so HRMS taxes it as `full_tax_on_additional_earnings` = slab(year with it) − slab(year without) in the paying month; the structured monthly tax is unchanged. Test: NGI's best-paid assignment (basic 58,224.83), Ashwin slip tax 1,730 → 7,552, i.e. 5,822.48 = 10 % marginal ([`test_dashain_is_taxed_once_in_its_month`](../../avinashgroup_app/payroll/test_festival_allowance.py#L221)). |
| **Reminder** | The HR dashboard warns 45 days before the first Dashain holiday on the company's list ([`DASHAIN_WARN_DAYS`](../../avinashgroup_app/hr/hr_dashboard.py#L66), [`_dashain_deadline`](../../avinashgroup_app/hr/hr_dashboard.py#L419)). |
| **Kind `Yearly`** | Refused on an assignment's Allowances and in Salary Revision ([`NOT_ON_ASSIGNMENT`](../../avinashgroup_app/payroll/allowance.py#L81)), so it can never become a monthly line by mistake. |
| **History** | The `Dashain Bonus` doctype (commit `40c37160`, 2026-09-21) was removed on 2026-09-29 by [`execute`](../../avinashgroup_app/patches/remove_dashain_bonus.py#L20). |

Boundary: only people on the Payroll Entry. Someone who left in an earlier month is not on it; settle them in Full and Final.

On avinas1 (dry run, rolled back, 2026-10-13): NGI Ashwin entry, cut-off 2026-10-11 → 87 rows, all full year, total 15,18,037.57.

---

## 6. Advances recovered from salary

| | |
|---|---|
| **What** | An Employee Advance with *Repay Unclaimed Amount from Salary* is recovered month by month: Prepare Payroll Inputs posts min(instalment, outstanding) as a submitted `Salary Advance` deduction referencing the advance. |
| **Why** | An advance is a loan; typed month by month on the sheet, a forgotten month is lost. HRMS already keeps the balance (an Additional Salary referencing an Employee Advance updates its `return_amount`) but has no instalment. Source: [module notes, `Advances recovered from salary`](../../avinashgroup_app/payroll/advance_recovery.py#L1); patch [`execute`](../../avinashgroup_app/patches/setup_advance_recovery.py#L13); commit `dca27f4` (2026-09-21). User view: [user-guide 8.3](../user-guide/08-raises-advances-bonuses-year-end.md). |
| **Stock HRMS** | Employee Advance, its payment, and [`update_return_amount_in_employee_advance`](../../../hrms/hrms/payroll/doctype/additional_salary/additional_salary.py#L183) on Additional Salary submit/cancel. We add the two fields and the posting. |
| **Custom fields** | Employee Advance `custom_monthly_instalment` (blank = whole balance at once), `custom_recover_from` (first date recovery may start); property setter: `repay_unclaimed_amount_from_salary` defaults to 1. Component `Salary Advance` forced to Deduction, not attendance-driven. |
| **Where** | [`post_recoveries`](../../avinashgroup_app/payroll/advance_recovery.py#L67) (called by [`trigger_for_payroll_entry`](../../avinashgroup_app/payroll/attendance_allowance.py#L78)), [`open_advances`](../../avinashgroup_app/payroll/advance_recovery.py#L39), [`clear_month`](../../avinashgroup_app/payroll/advance_recovery.py#L150). |
| **Reads** | Employee Advance: submitted, recover-from-salary, `paid_amount > 0`, status not Claimed/Returned/Cancelled, oldest first; `paid_amount − claimed_amount − return_amount` = outstanding. |
| **Writes** | Additional Salary (`Salary Advance`, Deduction, `payroll_date` = payroll end date, `ref_doctype/ref_docname` = the advance, `custom_source = Advance Recovery`). HRMS then updates the advance's `return_amount` and status. |
| **Impacts** | Deduction on the slip; the accrual journal credits the advance account for that component's line ([07-after-the-slip.md](07-after-the-slip.md)). |

Gotchas:

- The advance account must be of type **Receivable** or HRMS refuses the advance. [user-guide 8.3](../user-guide/08-raises-advances-bonuses-year-end.md) records that on 2026-10-09 the 148003 Staff Advance account was Payable at NGN, NGG, NGK, GLMI and untyped at NGI, GEPL, SGU.
- `clear_month` has **no savepoint**: pressing Prepare Payroll Inputs after the month's slips are submitted tries to cancel a recovery a submitted slip already used. Frappe normally refuses to cancel a document linked from a submitted one, which would abort the whole button (unverified; the allowance part has per-row savepoints, this part does not).
- Advances are not employee loans in the Lending app: no Loan doctype is installed on avinas1. The `Loan Summary` report in this app is a **company borrowings** report (Short/Long Term Borrowings accounts), not staff loans.
- avinas1: **0 Employee Advances** on 2026-10-12.

---

## 7. Cancelling and amending

### 7.1 What HRMS does on its own

| Action | Stock behaviour | Code |
|---|---|---|
| Cancel a **Payroll Entry** | Cancels **and deletes** every linked slip, cancels every submitted Journal Entry that references the entry (accrual **and** bank entry), resets the flags. Above 50 slips it is queued | [`on_cancel`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L107), [`delete_linked_salary_slips`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L135), [`cancel_linked_journal_entries`](../../../hrms/hrms/payroll/doctype/payroll_entry/payroll_entry.py#L144) |
| Cancel a **Salary Slip** | Status, loan repayment cancel, realtime update. The journal is not touched (it belongs to the entry) | [`on_cancel`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L249) |
| Cancel an **Additional Salary** | Hands an advance recovery back to the advance balance | [`on_cancel`](../../../hrms/hrms/payroll/doctype/additional_salary/additional_salary.py#L22) |
| Amend a slip | Standard Frappe amend (`-1` suffix). Our naming keeps the suffix (`get_amendment_suffix` in `naming_series.py`) | — |

Recommended order (from [payroll-handover.md §9](../payroll-handover.md)): bank entry → journal → slips → payroll entry; then fix the inputs, press Prepare Payroll Inputs again (it replaces its own rows), submit again.

What survives a cancelled Payroll Entry: the month's **Additional Salary rows** (engine, advance, adjustment, arrears) stay submitted. A new Payroll Entry for the same month picks them up again; Prepare Payroll Inputs replaces only its own.

### 7.2 Our guards against changing a paid month

| Guard | Hook | Stops |
|---|---|---|
| [`guard_paid_period`](../../avinashgroup_app/hr/shift_backdate.py#L81) | Shift Request `validate` ([`guard_paid_period`](../../avinashgroup_app/hooks.py#L452)), Shift Assignment `validate` ([`guard_paid_period`](../../avinashgroup_app/hooks.py#L452)), and again from the cancel preparers | A backdated shift change reaching a day covered by a submitted slip: "Cancel the salary slip first" ([02-checkin-to-attendance.md](02-checkin-to-attendance.md)) |
| [`follow_up`](../../avinashgroup_app/hr/holiday_backdate.py#L51) (from [`apply`](../../avinashgroup_app/avinash_group_app/doctype/holiday_bulk_update/holiday_bulk_update.py#L42)) | Holiday Bulk Update | Does **not** refuse: adds the holiday, re-marks attendance only for people without a submitted slip covering the date, and lists the paid ones for HR to decide |
| [`validate_salary_slip`](../../avinashgroup_app/payroll/bs_period_guard.py#L70) | Salary Slip `validate` | An amended/re-made slip whose start date differs from its Payroll Entry's ([05-payroll-entry.md](05-payroll-entry.md)) |
| Salary Revision | design | Never edits a paid slip; pays arrears instead |

**Not guarded** (a paid month can still be changed underneath the money): editing or re-marking Attendance by hand or via Attendance Fix, submitting/cancelling an Overtime Sheet, a Leave Application for a paid date, and a later run of the payroll inputs on a submitted Payroll Entry ([`submit_salary_slips`](../../avinashgroup_app/payroll/payroll_entry.py#L270) runs them again). For the last one the engine's per-row savepoint catches a failed cancel and lists the row as skipped ([`savepoint`](../../avinashgroup_app/payroll/attendance_allowance.py#L187)); the expected failure reason (Frappe's linked-document check) is unverified.

---

## 8. Joiners, leavers, final settlement, leave encashment

| Case | How it works | Ours or stock |
|---|---|---|
| **New company onboarding** | [`onboard`](../../avinashgroup_app/payroll/onboarding.py#L172) reads a company's Excel salary sheet, builds components and the structure ([`setup_company`](../../avinashgroup_app/payroll/onboarding.py#L224)), matches people and [`assign`](../../avinashgroup_app/payroll/onboarding.py#L473)s the structure from the fiscal year start; [`check_against_sheet`](../../avinashgroup_app/payroll/onboarding.py#L579) compares a dry-run slip with the sheet. Details: [01b-pay-masters.md](01b-pay-masters.md) | Ours, run by IT |
| **A single new hire** | Employee (Overtime Eligible or Replacement Leave tick, device ID, holiday list…) + one Salary Structure Assignment by hand with Basic, Initial Basic, SSF Applicable, Allowances and the current slab ([user-guide ch. 2](../user-guide/02-employee-setup.md)). The first slip is prorated from `date_of_joining` by HRMS payment days | Stock + our assignment fields |
| **Leaver** | Set `relieving_date` / status Left. HRMS prorates the last slip to the relieving date and refuses a slip for a period after it ([`validate_dates`](../../../hrms/hrms/payroll/doctype/salary_slip/salary_slip.py#L283)) | Stock |
| **Full and Final Statement, Gratuity** | Stock HRMS doctypes exist; none used (0 records each on avinas1); nothing of ours | Stock, unused |
| **Leave encashment** | HRMS `Leave Encashment`, extended. Rule (policy 3.7, user 2026-10-13): in the FY's last month (Ashadh) the remaining balance of every `allow_encashment` type is encashed on the Ashadh slip; carry forward off. Days = HRMS balance − `non_encashable_leaves`, capped at `max_encashable_leaves`. Rate = assignment `base` ÷ Leave Type `custom_encashment_days_per_month` (blank = the BS month's days). See [section 8a](#8a-leave-encashment) | Stock document + ours |

### 8a. Leave encashment

| | |
|---|---|
| **Entry point** | The Payroll Entry that pays it, beside the Dashain allowance: tick **Pay Leave Encashment** ([`_pay_leave_encashment`](../../avinashgroup_app/payroll/payroll_entry.py#L113), submits what [`encash_month`](../../avinashgroup_app/payroll/leave_encashment.py#L262) makes while the slips are made; until 2026-10-15 a button) → [`encash_for_payroll_entry`](../../avinashgroup_app/payroll/leave_encashment.py#L228)(payroll_entry): refused before the payroll month's first day; for the entry's employees, [`encash_month`](../../avinashgroup_app/payroll/leave_encashment.py#L262) drafts one Leave Encashment per (employee, encashable type, allocation) due in the month — Year End when the allocation ends in it (Ashadh), dated its `to_date`; Separation when the relieving date falls in it, dated that day — and returns occasion / balance / days / rate / amount for review. HR submits from the Leave Encashment list. (Until 2026-10-14 this was an **Encash Year-End Balances** button on the Leave Encashment list, by company and fiscal year, year end only.) |
| **Pricing and gate** | doc_event Leave Encashment `validate` → [`price_encashment`](../../avinashgroup_app/payroll/leave_encashment.py#L110), after HRMS's own: refuses a second submitted encashment of the same allocation (HRMS's balance does not subtract one); occasion = Year End (date = allocation `to_date`) or Separation (date = Employee `relieving_date`), else refused; the Leave Type's `custom_encash_at_year_end` / `custom_encash_at_separation` must allow it; sets `custom_occasion`, `custom_monthly_basic`, `custom_days_per_month`, `custom_rate_per_day`, `encashment_amount`. Replaces HRMS's per-structure `leave_encashment_amount_per_day` (0 on every structure). |
| **Additional Salary** | HRMS's [`create_additional_salary`](../../../hrms/hrms/hr/doctype/leave_encashment/leave_encashment.py#L155) writes it; our Additional Salary `validate` → [`mark_additional_salary`](../../avinashgroup_app/payroll/leave_encashment.py#L152) sets `deduct_full_tax_on_selected_payroll_date = 1` and `custom_source = "Leave Encashment"`; `on_submit` → [`link_additional_salary`](../../avinashgroup_app/payroll/leave_encashment.py#L164) writes it back to the encashment (HRMS v15.49 never does, so its `on_cancel` would leave the payment standing). Leave Encashment `on_submit` / `on_cancel` → [`refresh_slip`](../../avinashgroup_app/payroll/leave_encashment.py#L173). |
| **Separation** | No button: HR makes a Leave Encashment on the stock form dated the relieving date while the employee is still Active (HRMS's `validate_active_employee`). |
| **Expiry** | Carry forward off. HRMS's `process_expired_allocation` expires only what the ledger still holds; an encashment submitted after expiry gets HRMS's reverse expiry entry, so days are neither carried nor counted twice. |
| **Settings (data)** | Leave Type: `allow_encashment`, `earning_component`, `max_encashable_leaves`, `non_encashable_leaves`, `custom_encash_at_year_end`, `custom_encash_at_separation`, `custom_encashment_days_per_month` ([`execute` in patch setup_leave_encashment](../../avinashgroup_app/patches/setup_leave_encashment.py#L26)). avinas1: Casual and Sick encashable, component `Leave Encashment`, no caps, both occasions, divisor blank. [`HR_OWNED` in patch setup_leave_types](../../avinashgroup_app/patches/setup_leave_types.py#L26) no longer resets `allow_encashment` on an existing type. |
| **Needs** | A Leave Period per company and year (Leave Encashment requires one; year_setup makes it) and submitted Leave Allocations. avinas1 on 2026-10-13: **0 of each**. |

Gotcha: [`FISCAL_YEAR`](../../avinashgroup_app/payroll/onboarding.py#L51) is hard-coded to `"83/84"`, so onboarding a company in a later year assigns from 83/84's first day unless the constant is changed.

---

## 9. What exists on avinas1 today

Read 2026-10-12.

| Item | Count / value |
|---|---|
| Salary Revision | 0 |
| Payroll Adjustment | 0 |
| Employee Advance | 0 |
| Additional Salary | 10 submitted, all `Nepal HRMS Attendance Allowance` |
| Payroll Entries | NGI Shrawan and Bhadra 83/84, NGN Bhadra 83/84 — all submitted |
| Salary Slips | 154, all submitted, none cancelled |
| Components for changes | `Salary Arrears` (enabled, not prorated), `Arrear` (old, **disabled**, prorated), `Dashain Bonus`, `Dashain Allowance`, `Leave Encashment`, `Salary Advance` |
| Leave Encashment / Full and Final Statement / Gratuity | 0 / 0 / 0 |
| Leave Allocation / Leave Period (needed by encashment) | 0 / 0 (2026-10-13) |

See [impact-matrix.md](impact-matrix.md) for every field above against what it moves, and [hooks-inventory.md](hooks-inventory.md) for the hook registrations.
