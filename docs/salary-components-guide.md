# Salary Components: how to make them

For HR and accounts staff. This guide explains every field on the Salary Component form, what each Allowance Kind does, and how to set up every component we use. It ends with a checklist.

- Written on 2026-10-29 from the code (`avinashgroup_app/payroll/allowance.py`, `attendance_allowance.py`, `salary_slip.py`, `onboarding.py`, the HRMS Salary Component doctype) and from the data on the demo site (demo-nggroup.raindropinc.com).
- For the monthly run, tax, raises, Dashain and leave, see [payroll-user-guide.md](payroll-user-guide.md). For the code behind each rule, see [payroll-complete-reference.md](payroll-complete-reference.md).
- Numbers use Nepali grouping: 1,22,200 is one lakh twenty-two thousand two hundred.
- **Not available yet** marks something that is not built. **Known issue** marks a trap that is not fixed yet.

The running example used throughout: an NGI staff member in **Ashwin 2083** (31 days). Base 30,000. Initial Basic 24,000. SSF member. 1 day absent and 1 half day, so **29.5 payment days**. This is the same example as in the user guide.

---

## Contents

1. [What a component is: the three layers](#1-what-a-component-is-the-three-layers)
2. [Every field on the Salary Component form](#2-every-field-on-the-salary-component-form)
3. [The Allowance Kinds](#3-the-allowance-kinds)
4. [Recipes for every real component](#4-recipes-for-every-real-component)
5. [Making a new allowance, end to end](#5-making-a-new-allowance-end-to-end)
6. [Accounts: per company and per section](#6-accounts-per-company-and-per-section)
7. [Changing or retiring a component safely](#7-changing-or-retiring-a-component-safely)
8. [Common mistakes and error messages](#8-common-mistakes-and-error-messages)
9. [One-page checklist](#9-one-page-checklist)

---

## 1. What a component is: the three layers

A **Salary Component** is one line on a salary slip: Basic, Gas Allowance, SSF, Income Tax, and so on.

Each allowance lives in three places. Each place has one job.

| Layer | Screen | What it holds | What it does **not** hold |
|---|---|---|---|
| 1. The rule | **Salary Component** | What it is, how it is counted (Allowance Kind), the tax and proration ticks, and the accounts for each company and section | Any rate |
| 2. The usual rate | **Salary Structure** | The formula rows (Basic, SSF Addition, SSF, Income Tax) and the **Allowance Rates** table: the usual rate of each allowance | Anyone's pay. Payroll never reads Allowance Rates |
| 3. The person's rate | **Salary Structure Assignment** | The **Allowances** table: which allowances this person gets, and at what rate | — |

```
 SALARY COMPONENT  (the rule)
 ┌─────────────────────────────────────────────┐
 │ Gas Allowance                               │
 │ Type: Earning   Is Allowance: yes           │
 │ Allowance Kind: Monthly                     │
 │ Depends on Payment Days: yes  Taxed: yes    │
 │ Accounts: one row per company               │
 │   NGI  O/O 547110   S/D 547111   F/P 547112 │
 └──────────────────────┬──────────────────────┘
                        │ listed in
                        ▼
 SALARY STRUCTURE  "NGI Staff 83/84"  (the usual rate)
 ┌─────────────────────────────────────────────┐
 │ Earnings:   Basic = base                    │
 │             SSF Addition = B * 0.20 ...     │
 │ Deductions: SSF = B * 0.31 ...  Income Tax  │
 │ Allowance Rates:  Gas Allowance  1,690      │  ← fills the form only
 └──────────────────────┬──────────────────────┘
                        │ copied when HR picks the structure
                        ▼
 SALARY STRUCTURE ASSIGNMENT  (the person's rate)
 ┌─────────────────────────────────────────────┐
 │ Employee: NGI-EMP-00032   Base 30,000       │
 │ Allowances:  Gas Allowance  1,690           │  ← payroll reads THIS
 └──────────────────────┬──────────────────────┘
                        ▼
 SALARY SLIP:  Gas Allowance 1,690 × 29.5 ÷ 31 = 1,608.23
```

Three rules to remember:

1. **No row on the assignment means not paid.** The structure's rate list pays nobody.
2. **An allowance is never a row in the structure's Earnings or Deductions.** The save refuses it.
3. **A rate change is a new assignment** from the 1st of a BS month, made by a Salary Revision. The old assignment stays as the record of what was paid.

What is **not** an allowance: Basic, SSF Addition, SSF, Income Tax, Late Fine, Salary Advance, Leave Recovery, Salary Arrears. These are formula rows on the structure, or amounts the system posts by itself.

---

## 2. Every field on the Salary Component form

**Desk → HR → Salary Component**. The fields below are in the order the form shows them. "Ours" means a custom field of this app.

The custom fields of this app (Is Allowance, Allowance Kind and everything that hangs off them) sit on the **first tab, Overview**: after the standard ticks (after **Disabled**) and before the **Accounts** table. The Allowance section is open, not collapsed. This layout comes from the patch `move_allowance_fields_to_overview_tab` and shows after `bench migrate`. Until a site is migrated, these fields are still at the bottom of the Condition & Formula tab.

### 2.1 Overview tab: standard ticks

| # | Label | What it does | What to set | If set wrong |
|---|---|---|---|---|
| 1 | **Name** | The component's name. It is also the document's ID | A clear name. Some names are fixed by the code: **Income Tax**, **Salary Advance**, **Leave Recovery**, **Salary Arrears**, **Dearness Allowance** (see 7.3) | Renaming a fixed name breaks that feature |
| 2 | **Abbr** | Short code used in formulas (`B` for Basic). Must be unique. Left blank, HRMS makes one from the first letters. If taken, HRMS adds `_1` | Short and unique. Basic **must** be `B`, because the SSF formulas read `B` | A different Basic abbr makes SSF Addition and SSF 0, or throws on the slip |
| 3 | **Type** | Earning or Deduction. Decides which side of the slip | See the recipes | A deduction typed as Earning is **paid** instead of taken. The save refuses the wrong Type for Overtime and Late Fine only |
| 4 | **Description** | Free text | Optional | — |
| 5 | **Component Type** | Shown for deductions. An Indian HRMS list (Provident Fund, Professional Tax) | Leave blank | Nothing in our payroll reads it |
| 6 | **Depends on Payment Days** | Cuts the amount for unpaid days: amount × payment days ÷ days in the BS month. New components start with it **on** | **On** for Basic, Monthly and % of Initial Basic allowances. **Off** for everything else | On for SSF Addition or SSF: cut twice. On for an Entered by Hand or arrears line: a typed amount is cut for absences. Attendance kinds are forced off on save |
| 7 | **Is Tax Applicable** | Shown for earnings. The earning counts as taxable income | **On** for every earning | Off: the earning escapes income tax |
| 8 | **Deduct Full Tax on Selected Payroll Date** | Shown for taxed earnings. HRMS copies it onto a hand-made Additional Salary, so the whole tax on that amount is taken in its own month | **On** for Entered by Hand allowances. Leave off for the rest: our own buttons (Prepare Payroll Inputs, Payroll Adjustment, Leave Encashment) set it on every Additional Salary they make | Off on Load/Unload typed by hand: the tax on it is spread over the remaining months, so the month is under-taxed |
| 9 | **Variable Based On Taxable Salary** | Shown for deductions. Makes this the income tax line, worked out from the slab | **On for Income Tax only** | On anywhere else: a second tax line |
| 10 | **Is Income Tax Component** | Shown for deductions. Puts it in HRMS's Income Tax Deductions report | On for Income Tax | Report only |
| 11 | **Exempted from Income Tax** | Shown for deductions. The deduction lowers taxable income. Every exempt deduction is also counted as a retirement contribution under the s.63 cap | **On for SSF** (and a CIT line, if one is ever made). Off for every other deduction | On for Late Fine or Overtime: the save refuses it. On for Salary Advance or Leave Recovery: tax comes out too low |
| 12 | **Round to the Nearest Integer** | Rounds the slip line to whole rupees | **On for Income Tax** and Salary Arrears (the system makes them so). Off for the rest unless the accountant asks | Off/on only changes paisa |
| 13 | **Statistical Component** | The amount is worked out but not paid or deducted. Hides the Accounts table | **Off** | On: the line is never paid |
| 14 | **Do Not Include in Total** | The line shows on the slip but is left out of gross or total deductions | **Off** | On: shown but not paid |
| 15 | **Do Not Include in Accounting Entries** | Shown only when 14 is on. Leaves it out of the journal | Off | — |
| 16 | **Remove if Zero Valued** | Hides the line when it is 0. HRMS default is on | **On** (the save forces it on for attendance components) | Off: a 0.00 line prints on every slip |
| 17 | **Disabled** | The component cannot be picked on new structures or assignments, and attendance components stop being counted | See section 7. **It does not stop a Monthly allowance already on an assignment** | Disabled too early: see 7.2 |

### 2.2 Overview tab: Allowance section (ours)

| # | Label | What it does | What to set | If set wrong |
|---|---|---|---|---|
| 18 | **Is Allowance** | The person gets it from the Allowances table on their assignment. It cannot be put in a structure's Earnings | On for every allowance (recipes). Off for Basic, SSF, tax, fines, recoveries, arrears | On for Basic: Basic can no longer be a structure row. On for a **Deduction**: see 8.1, it is paid as an earning |
| 19 | **Allowance Kind** | How it is counted. Required when Is Allowance is on. Options: **Monthly**, **% of Initial Basic**, **Per Day Present**, **Per Meal**, **Per Overtime Hour**, **Entered by Hand**, **Yearly** | Section 3 | Blank: "Choose the Allowance Kind". Wrong kind: wrong money (section 3) |

Choosing a kind sets other fields on save:

| Kind | Is Attendance Driven | Condition Type | Unit | Depends on Payment Days | Remove if Zero Valued |
|---|---|---|---|---|---|
| Monthly, % of Initial Basic | forced off | — | — | as you set it (should be on) | as you set it |
| Per Day Present | forced on | Status = Present | as you set it | forced off | forced on |
| Per Meal | forced on | Meal Entitlement | ignored | forced off | forced on |
| Per Overtime Hour | forced on | Authorised Overtime | Per Hour | forced off | forced on |
| Entered by Hand, Yearly | forced off | — | — | as you set it (should be off) | as you set it |

### 2.3 Overview tab: Festival Allowance section (ours)

Shown only when Allowance Kind = **Yearly**. Used only for Dashain. Full rules in user guide section 11.

| # | Label | What it does | What to set |
|---|---|---|---|
| 20 | **Festival Allowance** | Makes this the component the Payroll Entry's Dashain button pays: one month's basic × service factor | On for **Dashain Allowance** only |
| 21 | **Pay Month** | The BS month whose Payroll Entry pays it. Blank = any month | 06 - Ashwin |
| 22 | **Minimum Service Days** | Under this many days from joining to the cut-off, nothing is paid. 0 = none | 0 |
| 23 | **Prorate for Under a Year** | On: under a year's service pays service days ÷ days in the year. Off: any service pays a full month | On |
| 24 | **Include Daily-Wage Staff** | A day's wage × the month's days counts as their month | Off (daily labour is paid outside payroll) |
| 25 | **Include Staff Leaving Before the Cut-off** | Pays leavers up to their relieving date | Off |

If wrong: two components ticked Festival Allowance both show up as Dashain choices; Pay Month wrong stops the Dashain button in the right month.

### 2.4 Overview tab: Attendance-Driven Rule section (ours)

These fields matter only for components counted from attendance: Tea, Meal, Overtime and the Late Fine. For an allowance, the Allowance Kind sets the first two. For the Late Fine (not an allowance) you set them by hand.

| # | Label | Shown when | What it does | What to set |
|---|---|---|---|---|
| 26 | **Is Attendance Driven** | always | Priced from attendance by **Prepare Payroll Inputs**, posted as Additional Salary | Leave to the kind. Tick by hand only on the Late Fine |
| 27 | **Condition Type** | Is Attendance Driven | The daily rule. Status = Present (tea), Meal Entitlement (meal), Authorised Overtime (OT), Late Time (late fine). Also listed: Status = Half Day, Worked on Holiday, Early Entry Before, Late Stay After, Late Arrival After (older rules, not used by our components) | Leave to the kind. Late Fine: **Late Time** |
| 28 | **Threshold Hours** | Condition = Working Hours >= Threshold | **Not available yet.** No code reads it, and the "Working Hours >= Threshold" rule pays 0 | Do not use |
| 29 | **Time Offset (Hours)** | Meal, Early Entry, Late Stay, Late Arrival | Meal: hours called in early, or kept late, on an authorised overtime day that earn one meal each | Meal: **1.5**. Blank or 0 means no working-day meal is ever earned |
| 30 | **Unit** | attendance, but not OT, Late Time or Meal | Per Day = 1 for each day that matches. Per Hour = the hours worked that day. Flat per Period = 1 for the whole month if any day matched | Tea: **Per Day** |
| 31 | **Attendance Month** | attendance | Same as Salary, or Previous Month (count last BS month's attendance) | **Same as Salary** |
| 32 | **Only OT-Eligible Staff** | attendance, but not OT or Late Time | Pays only people ticked Overtime Eligible on the Employee | Meal: **on**. Tea: off. (Overtime is always OT-eligible only; the late fine never is) |
| 33 | **Rate Basis** | attendance, but not OT or Late Time | Fixed Rate = the Rate on the assignment row. Hourly Basic × Multiplier = the person's basic ÷ days ÷ hours × Multiplier | **Fixed Rate** for tea and meal |
| 34 | **Multiplier** | Late Time, or Rate Basis = Hourly Basic × Multiplier | The multiple of the hourly basic | Late Fine: **1**. Hidden for Overtime: OT is always 1.5 |
| 35 | **Rate: Days per Month** | OT, Late Time, or Hourly Basic | Days a month's basic is spread over. Blank = the real BS month (29 to 32) | **Blank** (30 brings back the old Excel rule; management decision) |
| 36 | **Rate: Hours per Day** | same | Hours in a working day. Blank = 8 | **Blank** or 8 |
| 37 | **A Half Day Counts As** | Status = Present | What a Half Day earns: Full Day, Half Day (0.5) or Not At All | Tea: **Full Day** |
| 38 | **Pay on Holiday** | Status = Present or Half Day | Whether a worked holiday earns it. Blank = Pay | Tea: **Pay** (company rule since 15 October 2026) |

### 2.5 Overview tab: Accounts

| # | Label | What it does | What to set | If set wrong |
|---|---|---|---|---|
| 39 | **Accounts** table | One row per company: Company, **Admin & Accounts (O/O)**, **Marketing (S/D)** (ours), **Plant (F/P)** (ours) | One row for every company that pays it. Section 6 | No row for a company: that company's journal stops with "Please set account in Salary Component …" |

### 2.6 Condition & Formula tab: stock fields

| # | Label | What it does | What to set | If set wrong |
|---|---|---|---|---|
| 40 | **Condition** | A Python test. HRMS copies it into a structure row when the component is added to a structure | **Leave blank.** Write conditions on the structure row instead | A condition here is copied into new structure rows without anyone noticing |
| 41 | **Amount** | A fixed amount, copied into a new structure row | Leave blank | Same as above |
| 42 | **Amount based on formula** | Uses Formula instead of Amount | Leave off on the component | — |
| 43 | **Formula** | Copied into a new structure row | **Leave blank.** The formulas live on the structure (section 4) | — |

The form also has **Update Salary Structures → Sync Condition / Sync Formula** buttons. They overwrite the rows of every structure that uses the component, even submitted ones. **Do not use them.** Change a structure through a new structure or a Salary Revision.

For an allowance these four fields do nothing at all: an allowance is never a structure row.

### 2.7 Help and the Flexible Benefits tab

| # | Label | What to set |
|---|---|---|
| 44 | **Help** | HRMS formula help. Read only |
| 45 | **Is Flexible Benefit** | **Off.** We do not use flexible benefits. On, the line is taxed as a benefit claim, not as pay, and the Condition & Formula fields hide |
| 46 | **Max Benefit Amount (Yearly)**, **Pay Against Benefit Claim**, **Only Tax Impact**, **Create Separate Payment Entry Against Benefit Claim** | Shown only with Is Flexible Benefit. Leave blank |
| 47 | **Max Meals per Day** (ours) | Meal only: the cap on meals in one day. 0 = no cap. Set **2** |
| 48 | **Summary Group** (ours) | Attendance components only. Components with the same label share one column in the Monthly Attendance Summary BS report. Tea, Meal, Overtime, Late Fine |
| 49 | **Created On**, **Created By** (ours) | Filled by the system |

> **Known issue: Max Meals per Day and Summary Group sit on the Flexible Benefits tab.** Their place on the form points at fields that no longer exist, so Frappe puts them at the end of the form. They still work. Look for them on the last tab.

---

## 3. The Allowance Kinds

These are the seven kinds in the code (`ALLOWANCE_KINDS` in `allowance.py`).

| Kind | Rate goes on | Unit | Paid by | Prorated | Tax |
|---|---|---|---|---|---|
| **Monthly** | Assignment row | per month | The slip itself, from the assignment | Yes (with Depends on Payment Days) | Projected over the year like Basic |
| **% of Initial Basic** | Assignment row (a %) | % of initial basic | The slip itself | Yes | Projected over the year |
| **Per Day Present** | Assignment row | per day present | Prepare Payroll Inputs → Additional Salary | No (forced off) | In full in the month paid |
| **Per Meal** | Assignment row | per meal | Prepare Payroll Inputs → Additional Salary | No | In full in the month paid |
| **Per Overtime Hour** | Nowhere (from basic) | from basic × 1.5 | Prepare Payroll Inputs → Additional Salary | No | In full in the month paid |
| **Entered by Hand** | Payroll Adjustment row | — | Payroll Adjustment → Additional Salary | Only if Depends on Payment Days is on, so keep it **off** | In full in the month paid |
| **Yearly** | Nowhere (worked out) | — | Its own button (Dashain, Leave Encashment) on a payout slip | No | Special payout method (user guide 7.10) |

"In full in the month paid" means the extra tax this amount adds to the year is taken in that month, not spread.

### 3.1 Monthly

- **Use for:** a fixed amount each month. Dearness, Other, Fixed, Fuel, Maintenance, Transport, Gas, Education.
- **Required:** Type Earning. Is Allowance on. Kind Monthly. Depends on Payment Days **on**. Is Tax Applicable on. Accounts for every paying company.
- **Rate:** the assignment row's **Rate**, in rupees a month. The structure's Allowance Rates holds the usual rate (it can be 0 for a per-person amount like Dearness).
- **Calculation:** Rate × payment days ÷ days in the BS month.
- **Example:** Gas 1,690 × 29.5 ÷ 31 = **1,608.23**.
- A row with a later **From Date** is not paid until that date. A row removed from the assignment leaves the draft slip on its next save.

### 3.2 % of Initial Basic

- **Use for:** House Rent Allowance (NGI 25 %, NGN 27 %).
- **Required:** as Monthly, Kind % of Initial Basic.
- **Rate:** the assignment row's **Rate** is a **percent**: type 25, not 0.25 and not 6,000. The base is the assignment's **Initial Basic** field (Pay Details), not Base.
- **Calculation:** Initial Basic × Rate ÷ 100 × payment days ÷ days in the BS month.
- **Example:** 24,000 × 25 % = 6,000; × 29.5 ÷ 31 = **5,709.68**.
- Initial Basic blank or 0 on the assignment: HRA is 0, with no message.

### 3.3 Per Day Present

- **Use for:** Tea & Conveyance, or any amount earned by turning up.
- **Required:** Type Earning. Is Allowance on. Kind Per Day Present. Is Tax Applicable on. Unit Per Day. A Half Day Counts As. Pay on Holiday. Accounts.
- **Rate:** the assignment row's **Rate**, in rupees a day (NGI 235 for older staff, 40 for newer; NGN 265).
- **Calculation:** days counted × Rate. A day counts when the attendance is Present (or Work From Home, or any status other than Absent, On Leave, Half Day). A Half Day counts as set in **A Half Day Counts As**. A worked holiday counts unless **Pay on Holiday** = Do Not Pay. Absent and On Leave never count.
- **Example:** 26 days × 235 = **6,110.00**.
- Only people with a row for it on their assignment are paid.

### 3.4 Per Meal

- **Use for:** Meal only.
- **Required:** Type Earning. Is Allowance on. Kind Per Meal. Time Offset (Hours) 1.5. Max Meals per Day 2. Only OT-Eligible Staff on. Accounts.
- **Rate:** the assignment row's **Rate**, in rupees a meal (NGI and NGN 75, NGG 100).
- **Calculation:** a meal is earned only on a day a submitted **Overtime Sheet** names the person with Earns = Overtime, and only for people ticked Overtime Eligible who have a Meal row.
  - Working day: +1 if they punched in 1.5 h or more before the shift, +1 if they punched out 1.5 h or more after it.
  - Holiday on the sheet: 8 h or more first IN to last OUT → 2; 6 h to under 8 h → 1; under 6 h → 0.
  - Never more than Max Meals per Day.
- **Example:** one working day called in 1.5 h early and kept 2 h late (2 meals), one holiday worked 7 h (1 meal): 3 × 75 = **225.00**.

### 3.5 Per Overtime Hour

- **Use for:** Overtime only. Make **one** such component, never two.
- **Required:** Type **Earning** (the save refuses Deduction). Is Allowance on. Kind Per Overtime Hour. Is Tax Applicable on. Exempted from Income Tax off. Accounts.
- **Rate:** none to type. Hourly basic = Base ÷ days in the BS month ÷ 8, × 1.5. The 1.5 is fixed in the code. A Rate typed on a row is set back to 0 on save.
- **Calculation:** hours on submitted Overtime Sheets (Earns = Overtime) × hourly basic × 1.5. Paid to everyone ticked Overtime Eligible; no assignment row is needed.
- **Example:** 30,000 ÷ 31 ÷ 8 = 120.9677; × 1.5 = 181.4516 an hour; × 4.5 h = **816.53**. In a 30-day month: 187.50 an hour.

### 3.6 Entered by Hand

- **Use for:** an amount that changes each month and is typed by HR. Load/Unload Allowance.
- **Required:** Type Earning. Is Allowance on. Kind Entered by Hand. Is Tax Applicable on. **Depends on Payment Days off.** Deduct Full Tax on Selected Payroll Date on. Accounts.
- **Rate:** none. It cannot be on an assignment or in Allowance Rates (the save refuses it).
- **Calculation:** the amount typed on a **Payroll Adjustment** row (user guide section 9).
- **Example:** 3,500 typed → **3,500.00** on the slip, taxed in full that month.

### 3.7 Yearly

- **Use for:** Dashain Allowance and Leave Encashment. Each has its own button and its own payout slip.
- **Required:** Type Earning. Is Allowance on. Kind Yearly. Is Tax Applicable on. Depends on Payment Days off. Dashain also needs the Festival Allowance section (2.3). Leave Encashment is named as **Earning Component** on each encashable Leave Type.
- **Rate:** none. Not on assignments or Allowance Rates.
- **Calculation:** Dashain = one month's Base × service factor. Leave Encashment = days × Base ÷ days in the month.
- **Example:** Dashain, full year: **30,000.00**. Joined 280 days before the cut-off: 30,000 × 280 ÷ 365 = **23,013.70**. Encashment: 6.5 days × 937.50 = **6,093.75**.
- A Yearly component without the Festival tick and not on a Leave Type has no button. **Not available yet:** any other kind of yearly payment; use Entered by Hand on a Payroll Adjustment instead.

---

## 4. Recipes for every real component

How to read a recipe: set each field as shown. "—" means the field is hidden or not used; leave it as it is. Everything not listed stays at its default: Statistical Component off, Do Not Include in Total off, Is Flexible Benefit off, Disabled off, Condition and Formula blank on the component.

Account numbers are the NGI chart. Every company has the same numbers with its own suffix (`- NGG`, `- GEPL`). The accountant confirms the mapping. Section 6 explains the three columns.

Names: use the names below. Some sites carry older spellings (on the demo site: "GAS Allowance", "Education", "Tea & Convience", "Dashain Alllowance", "late comers deduction"). The name does not change the money, except for the fixed names in 7.3.

### 4.1 Basic

| Field | Value |
|---|---|
| Name / Abbr | Basic / **B** |
| Type | Earning |
| Depends on Payment Days | On |
| Is Tax Applicable | On |
| Is Allowance | Off |
| Accounts | 547101 Salary Expenses: O/O 547101, S/D 547102, F/P 547103 |

- **Structure:** Earnings row. Formula `base`. Amount based on formula on. Depends on Payment Days on.
- **Assignment:** **Base** = the monthly basic. No Allowances row.
- Example: 30,000 × 29.5 ÷ 31 = 28,548.39.

### 4.2 SSF Addition

| Field | Value |
|---|---|
| Name / Abbr | SSF Addition / SSFA |
| Type | Earning |
| Depends on Payment Days | **Off** |
| Is Tax Applicable | On |
| Is Allowance | Off |
| Accounts | Salary expense 547101 / 547102 / 547103 (the employer's share is a salary cost) |

- **Structure:** Earnings row. Formula `B * 0.20 if custom_ssf_applicable else 0`. Amount based on formula on. Depends on Payment Days **off** (B is already cut).
- **Assignment:** tick **SSF Applicable** (Pay Details).
- Example: 28,548.39 × 20 % = 5,709.68.

### 4.3 SSF

| Field | Value |
|---|---|
| Name / Abbr | SSF / SSF |
| Type | Deduction |
| Depends on Payment Days | **Off** |
| Exempted from Income Tax | **On** |
| Is Allowance | Off |
| Accounts | 347302 SSF Payable, in all three columns (or O/O only) |

- **Structure:** Deductions row. Formula `B * 0.31 if custom_ssf_applicable else 0`. Amount based on formula on. Depends on Payment Days off.
- **Assignment:** SSF Applicable.
- Example: 28,548.39 × 31 % = 8,850.00.

### 4.4 House Rent Allowance (HRA)

| Field | Value |
|---|---|
| Name / Abbr | House Rent Allowance / HRA |
| Type | Earning |
| Depends on Payment Days | On |
| Is Tax Applicable | On |
| Is Allowance / Kind | On / **% of Initial Basic** |
| Accounts | 547104 / 547105 / 547106 House Rent Allowance |

- **Structure:** no Earnings row. **Allowance Rates:** House Rent Allowance, Rate **25** (NGI) or 27 (NGN).
- **Assignment:** Allowances row House Rent Allowance, Rate 25. Fill **Initial Basic** on the assignment.
- Example: 5,709.68 (3.2).

### 4.5 Dearness Allowance

| Field | Value |
|---|---|
| Name / Abbr | Dearness Allowance / DA. **Keep this exact name** (Salary Revision reads it) |
| Type | Earning |
| Depends on Payment Days | On |
| Is Tax Applicable | On |
| Is Allowance / Kind | On / Monthly |
| Accounts | 547107 / 547108 / 547109 (demo NGI), or salary expense 547101-3 |

- **Structure:** Allowance Rates row Dearness Allowance, Rate 0 (it differs per person).
- **Assignment:** Allowances row Dearness Allowance, Rate = this person's amount (for example 2,000). A row left at 0 is refused.
- Example: 2,000 × 29.5 ÷ 31 = 1,903.23.

### 4.6 Gas Allowance

| Field | Value |
|---|---|
| Name / Abbr | Gas Allowance / GAS |
| Type / Depends on Payment Days / Is Tax Applicable | Earning / On / On |
| Is Allowance / Kind | On / Monthly |
| Accounts | 547110 / 547111 / 547112 Other Allowance (demo NGI) |

- **Structure:** Allowance Rates: Gas Allowance 1,690 (NGI), 1,690.27 (NGN).
- **Assignment:** a Gas row only for people who get it.
- Example: 1,608.23.

### 4.7 Education Allowance

As Gas. Name Education Allowance, Abbr EDU. Allowance Rates: 2,780 (NGI), 1,250 (NGN). Accounts 547110-2 Other Allowance.

Example: 2,780 × 29.5 ÷ 31 = 2,645.48.

### 4.8 Fuel Allowance (and Other, Fixed, Maintenance, Transport)

As Gas, with Allowance Rates Rate 0 (per person). Abbr: Fuel FUEL, Other OA, Fixed FA, Maintenance MNT.

| Component | Accounts (demo NGI) |
|---|---|
| Fuel Allowance | 547136 / 547137 / 547138 Fuel Allowance |
| Other Allowance | 547110 / 547111 / 547112 Other Allowance |
| Fixed, Maintenance, Transport | 547107-9 Fixed Allowance, or as the accountant decides |

### 4.9 Tea & Conveyance

| Field | Value |
|---|---|
| Name / Abbr | Tea & Conveyance / TEA |
| Type | Earning |
| Is Tax Applicable | On |
| Is Allowance / Kind | On / **Per Day Present** |
| Depends on Payment Days | (forced off) |
| Remove if Zero Valued | (forced on) |
| Is Attendance Driven / Condition Type | (set by the kind: on / Status = Present) |
| Unit | Per Day |
| Attendance Month | Same as Salary |
| Only OT-Eligible Staff | Off |
| Rate Basis | Fixed Rate |
| A Half Day Counts As | Full Day |
| Pay on Holiday | **Pay** |
| Summary Group | Tea |
| Is Flexible Benefit | **Off** |
| Accounts | 547110 / 547111 / 547112 Other Allowance (demo NGI), or salary expense |

- **Structure:** Allowance Rates: Tea & Conveyance 235 (NGI), 265 (NGN).
- **Assignment:** Tea row at the person's daily rate: 235, or 40 for newer NGI staff. **Per day, not per month.**
- Example: 6,110.00.

> **Known issue:** the onboarding script still creates Tea with Pay on Holiday = **Do Not Pay**. After onboarding a company, set it to **Pay**.

### 4.10 Meal

| Field | Value |
|---|---|
| Name / Abbr | Meal / MEAL |
| Type / Is Tax Applicable | Earning / On |
| Is Allowance / Kind | On / **Per Meal** |
| Condition Type | (set: Meal Entitlement) |
| Time Offset (Hours) | **1.5** |
| Only OT-Eligible Staff | **On** |
| Attendance Month | Same as Salary |
| Max Meals per Day (last tab) | **2** |
| Summary Group | Meal |
| Accounts | 547130 / 547131 / 547132 Meal Allowance |

- **Structure:** Allowance Rates: Meal 75 (NGI, NGN) or 100 (NGG).
- **Assignment:** a Meal row at the rate for each OT-eligible person. No row, no meal.
- Example: 3 meals × 75 = 225.00.

### 4.11 Overtime

| Field | Value |
|---|---|
| Name / Abbr | Overtime / OT |
| Type | **Earning** |
| Is Tax Applicable | On |
| Exempted from Income Tax | — (must stay off) |
| Is Allowance / Kind | On / **Per Overtime Hour** |
| Condition Type / Unit | (set: Authorised Overtime / Per Hour) |
| Attendance Month | Same as Salary |
| Rate: Days per Month | Blank |
| Rate: Hours per Day | Blank (8) |
| Summary Group | Overtime |
| Accounts | 547113 / 547114 / 547115 Overtime Expenses |

- **Structure:** Allowance Rates: Overtime, Rate 0 (shown as "from basic × 1.5").
- **Assignment:** no row is needed. A row may be left at 0 for the record; it is never priced. Tick **Overtime Eligible** on the Employee.
- Example: 816.53.

### 4.12 Late Fine

| Field | Value |
|---|---|
| Name / Abbr | Late Fine / LF |
| Type | **Deduction** |
| Exempted from Income Tax | **Off** (the save refuses it) |
| Is Allowance | **Off** |
| Is Attendance Driven | **On** (tick by hand) |
| Condition Type | **Late Time** |
| Multiplier | 1 |
| Rate: Days per Month / Hours per Day | Blank / Blank |
| Attendance Month | Same as Salary |
| Summary Group | Late Fine |
| Accounts | 547101 / 547102 / 547103 Salary Expenses (the fine lowers the salary cost). Demo NGI uses 545200 Tax, Fines & Penalties. Accountant decides |

- **Structure:** no row needed. Everyone not ticked **Late Fine Exempt** on the Employee is fined. An old Late Fine row is allowed; its formula is cleared on save.
- **Assignment:** nothing.
- Rate: Base ÷ BS month days ÷ 8 ÷ 60 a minute. Example: 37 minutes → **74.60**.
- Make only one Late Time component. Two would fine twice.

### 4.13 Advance Recovery (Salary Advance)

| Field | Value |
|---|---|
| Name / Abbr | **Salary Advance** (fixed name) / ADV |
| Type | Deduction |
| Depends on Payment Days | Off |
| Exempted from Income Tax | Off |
| Is Allowance | Off |
| Accounts | 148003 Staff Advance in **O/O only**. Leave S/D and F/P blank |

- **Structure:** no row.
- **Assignment:** nothing. The amount comes from the **Monthly Instalment** on each Employee Advance (user guide section 10).

### 4.14 Leave Recovery

| Field | Value |
|---|---|
| Name / Abbr | **Leave Recovery** (fixed name) / LR |
| Type | Deduction |
| Depends on Payment Days | Off |
| Exempted from Income Tax | Off |
| Remove if Zero Valued | On |
| Is Allowance | Off |
| Accounts | Same as Leave Encashment: 547101 / 547102 / 547103 |

- **Structure / assignment:** nothing. Posted at a settlement when **Settle Leave** is ticked (user guide 12.4).

### 4.15 Salary Arrears

| Field | Value |
|---|---|
| Name / Abbr | **Salary Arrears** (fixed name) / ARR |
| Type | Earning |
| Depends on Payment Days | **Off** |
| Is Tax Applicable | On |
| Round to the Nearest Integer | On |
| Is Allowance | Off |
| Accounts | 547101 / 547102 / 547103 |

- The first Salary Revision with arrears creates it **without accounts**. Add an Accounts row for every company straight away, or the journal stops.
- **Structure / assignment:** nothing. Worked out by the Salary Revision (user guide section 8).

### 4.16 Dashain Allowance

| Field | Value |
|---|---|
| Name / Abbr | Dashain Allowance / DA_1 or DSN (any free abbr; DA is Dearness) |
| Type | Earning |
| Depends on Payment Days | **Off** |
| Is Tax Applicable | On |
| Is Allowance / Kind | On / **Yearly** |
| Festival Allowance | **On** |
| Pay Month | 06 - Ashwin |
| Minimum Service Days | 0 |
| Prorate for Under a Year | On |
| Include Daily-Wage Staff | Off |
| Include Staff Leaving Before the Cut-off | Off |
| Accounts | 547145 / 547146 / 547147 Dashain Expenses |

- **Structure / assignment:** nothing. Paid by the Payroll Entry's Dashain button (user guide section 11).
- **Dashain Bonus** is an old component. Do not use it. Disable it once no open document uses it (7.2).

### 4.17 Leave Encashment

| Field | Value |
|---|---|
| Name / Abbr | Leave Encashment / LE |
| Type | Earning |
| Depends on Payment Days | **Off** |
| Is Tax Applicable | On |
| Is Allowance / Kind | On / **Yearly** |
| Accounts | 547101 / 547102 / 547103 (copied from Basic by the setup) |

- **Leave Type:** name it as **Earning Component** on each encashable Leave Type.
- **Structure / assignment:** nothing.

### 4.18 Load/Unload Allowance

| Field | Value |
|---|---|
| Name / Abbr | Load/Unload Allowance / LU |
| Type | Earning |
| Depends on Payment Days | **Off** |
| Is Tax Applicable | On |
| Deduct Full Tax on Selected Payroll Date | On |
| Is Allowance / Kind | On / **Entered by Hand** |
| Accounts | Salary expense 547101-3, or as the accountant decides |

- Paid only on a Payroll Adjustment row.

> **Known issue:** the onboarding script (`ensure_components`) creates Load/Unload with Depends on Payment Days **on**, and sets it back to on each time it runs. With it on, a typed 3,500 is cut for absences (3,500 × 29.5 ÷ 31 = 3,330.65). Check it is off after any onboarding.

### 4.19 Income Tax

| Field | Value |
|---|---|
| Name / Abbr | **Income Tax** (fixed name) / TAX or IT |
| Type | Deduction |
| Depends on Payment Days | Off |
| Variable Based On Taxable Salary | **On** |
| Is Income Tax Component | On |
| Round to the Nearest Integer | On |
| Exempted from Income Tax | — |
| Is Allowance | Off |
| Condition / Formula / Amount | Blank (hidden) |
| Accounts | 348102 TDS-Remuneration Income Tax (proposed). Demo NGI uses 348108 TDS-SST. Accountant decides |

- **Structure:** a Deductions row with no formula, in every structure.
- **Assignment:** **Income Tax Slab** (for example `Nepal 83/84 - NGI`).

### 4.20 CIT

**Not available yet.** No CIT component exists and no screen works out a CIT amount. The tax code is ready for one: a deduction ticked **Exempted from Income Tax** lowers taxable income and counts towards the retirement cap.

If CIT through payroll is agreed, IT should set it up and test it first. The likely recipe: Name CIT, Type Deduction, Depends on Payment Days off, Exempted from Income Tax on, **Is Allowance off** (an allowance deduction is paid as an earning, see 8.1), account 347305 CIT Payable, the amount from a recurring Additional Salary. Until then, CIT paid outside payroll goes on the Tax Exemption Declaration (user guide 7.3).

---

## 5. Making a new allowance, end to end

Example: a new **Mobile Allowance**, 500 a month, for some NGI and NGN staff.

### 5.1 The component

1. **Desk → HR → Salary Component → New**.
2. **Name**: Mobile Allowance. **Abbr**: MOB (check no other component uses it).
3. **Type**: Earning.
4. **Depends on Payment Days**: on (Monthly or % of Initial Basic). Off for Entered by Hand or Yearly.
5. **Is Tax Applicable**: on. Leave every other standard tick off, except Remove if Zero Valued (on).
6. Below **Disabled**, on the same Overview tab: tick **Is Allowance**. Choose **Allowance Kind**: Monthly.
7. For an attendance kind only: fill the Attendance-Driven Rule fields just below, from the matching recipe (Tea or Meal).
8. Do not open the Condition & Formula tab. Leave Condition and Formula blank.
9. Do not save yet. Scroll down to the Accounts table, still on Overview.

### 5.2 The accounts, for every company

1. In **Accounts**, click **Add Row**.
2. Pick the **Company** first. The account lists then show only that company's ledger accounts (expense accounts, for an earning).
3. **Admin & Accounts (O/O)**: for example `547110 - Other Allowance - O/O - NGI`.
4. **Marketing (S/D)**: `547111 - Other Allowance - S/D - NGI`.
5. **Plant (F/P)**: `547112 - Other Allowance - F/P - NGI`.
6. Repeat for every company that pays it. On avinas1 that is up to seven: NGI, NGG, NGK, NGN, GLMI, GEPL, SGU. Add a row even for a company that pays it to only one person.
7. **Save**. Fix any message (section 8).

### 5.3 The structure's Allowance Rates

1. Open the company's structure, for example **NGI Staff 83/84**.
2. In **Allowance Rates**, **Add Row**: Allowance = Mobile Allowance, Rate = 500. The Unit fills itself ("per month").
3. A submitted structure can take a new row: **Update**. (Changing an existing rate is refused; that needs a Salary Revision.)
4. Repeat on the NGN structure. Use Rate 0 if the amount differs for each person.

This step is optional. It only fills forms. Without it, HR types the rate on each assignment.

### 5.4 The assignments

For a few people, or a pay change from a date: make a **Salary Revision** with an Allowance Changes row **Add**, Allowance = Mobile Allowance, New Rate blank (the structure's rate) or 500. It makes a new assignment for each listed person from the 1st of a BS month. See user guide section 8.

For a new joiner: on their new **Salary Structure Assignment**, pick the structure (the table fills), keep the Mobile row, check the Rate, remove what they do not get, **Submit**.

Do not edit a submitted assignment. Do not add the allowance to the structure's Earnings.

### 5.5 The test slip

1. Make a Payroll Entry for one company and the month (user guide section 5), or open one person's draft Salary Slip for the month.
2. For an attendance kind, press **Prepare Payroll Inputs** first.
3. Check the slip shows **Mobile Allowance** = 500 × payment days ÷ month days. Example: 500 × 29.5 ÷ 31 = 483.87.
4. Check someone **without** a row has no Mobile line.
5. Check the income tax moved.
6. Submit one test slip on a test site and check the journal: Dr the right O/O, S/D or F/P account for the person's department.

---

## 6. Accounts: per company and per section

### 6.1 How the table works

Each Accounts row is **one company**. It has three account columns:

| Column (label on the form) | Section | Used for people whose Department's Payroll Section is |
|---|---|---|
| **Admin & Accounts (O/O)** | O/O | Admin & Accounts, or no section |
| **Marketing (S/D)** | S/D | Marketing |
| **Plant (F/P)** | F/P | Plant |

When a slip is submitted, the journal debits (earning) or credits (deduction) the column that matches the person's section. The section comes from Employee → Department → **Payroll Section**.

The chart numbers the three accounts apart: 547130 Meal Allowance - O/O, 547131 - S/D, 547132 - F/P. Every company has the same numbers with its own suffix.

Which account type to choose:

| Component | Account type |
|---|---|
| Every earning | Expense (the form offers only expense accounts for an earning) |
| SSF, Income Tax, CIT | Liability (payable) |
| Salary Advance | Asset (Staff Advance), O/O only |
| Late Fine, Leave Recovery | The salary expense account (lowers the cost) |

### 6.2 What happens if something is blank

| What is blank | Result |
|---|---|
| **No row** for the company | The save warns only if a row has no account. The month's journal stops: "Please set account in Salary Component …". Nobody in that company can be paid until the accountant adds the row |
| Row with **O/O blank** | Save warns "Accounts not set for Salary Component …". The journal stops the same way |
| **S/D or F/P blank**, O/O filled | That section's cost posts to O/O. No message. The split is lost |
| S/D or F/P filled, but a person's Department has **no Payroll Section** | The run stops: "Payroll cannot run yet" (… Department … has no Payroll Section), or "Set Payroll Section on the Department of these employees …" |

### 6.3 What the save checks

- Every account must belong to the row's company: "Accounts row 2: … is not an account of …".
- No group accounts: "Accounts row 2: … is a group account; pick a ledger account".
- On the form, picking an account before the Company: "Select the Company on row 2 first".

### 6.4 Filling every company at once

IT has a script, `map_component_accounts(company)` in `payroll/onboarding.py`. For one company it fills every blank row:

- every earning → 547101 Salary Expenses (O/O), with the S/D and F/P twins found by name;
- SSF → 347302 SSF Payable; Income Tax → 348102 TDS-Remuneration; Salary Advance → 148003 Staff Advance; Late Fine → 547101.

It never overwrites a row that already has an account, and skips an account the company's chart does not have. It is not a desk button; ask IT, and only after the accountant agrees the mapping. It does not know the per-allowance accounts (547104 HRA, 547130 Meal and so on), so set those by hand if the accountant wants them.

---

## 7. Changing or retiring a component safely

### 7.1 Changing a setting

| Change | Safe? | What to do |
|---|---|---|
| Accounts (add a company, change an account) | Yes | Edit and save. Applies to slips submitted after that |
| Pay on Holiday, A Half Day Counts As, Time Offset, Max Meals, Rate: Days/Hours | Yes, with management approval | Applies the next time **Prepare Payroll Inputs** runs. Submitted slips keep the old amount |
| Allowance Kind | **No** | Moving between Monthly and an attendance kind changes how every assignment row is read. Make a new component instead (7.2) |
| Type | **No** | Make a new component |
| Abbr | **No** | Structure formulas use it |
| Is Tax Applicable, Exempted from Income Tax, Depends on Payment Days on a **formula** component (Basic, SSF) | Ask IT | Each structure row keeps its own copy of these ticks, taken when the row was added. Changing the component does not change existing structure rows |
| Condition / Formula on the component | Do not | And do not press **Sync Condition / Sync Formula** |
| A usual rate | Not here | Salary Revision → **Raise Rate** |

### 7.2 Retiring a component

Disabling alone is **not enough** for a Monthly or % of Initial Basic allowance. The slip pays every row on a submitted assignment whether the component is disabled or not.

Steps:

1. Stop paying it: a **Salary Revision** with **Stop** for everyone who has it, from the 1st of a BS month. This makes new assignments without the row.
2. Remove its row from each structure's **Allowance Rates** (allowed on a submitted structure).
3. Wait until the last month that paid it is submitted.
4. Tick **Disabled** on the component. Save.

What Disabled does: the component is no longer offered on structures and assignments, and an attendance component (Tea, Meal, Overtime, Late Fine) stops being counted by Prepare Payroll Inputs at once. A Festival Allowance component stops being offered for Dashain.

Never delete a component that a submitted slip has used. Disable it.

### 7.3 Renaming

Frappe lets you rename a component (**⋯ → Rename**), and updates the links in structures, assignments and slips.

Do **not** rename these. The code finds them by name:

| Name | Used by |
|---|---|
| Income Tax | the tax engine and the tax override |
| Salary Advance | advance recovery |
| Leave Recovery | leave recovery |
| Salary Arrears | Salary Revision arrears (a renamed one is made again, without accounts) |
| Dearness Allowance | Salary Revision's dearness column |

Other names are safe to rename. Fixing a spelling such as "Tea & Convience" is fine. Rename outside the payroll days, and tell the accountant: reports grouped by component name change.

---

## 8. Common mistakes and error messages

### 8.1 Mistakes with no message

| Mistake | What happens | Fix |
|---|---|---|
| A **Deduction** ticked Is Allowance with kind Monthly or % of Initial Basic | The slip adds it to **earnings**: paid, not deducted | Untick Is Allowance. Deductions are never allowances |
| HRA Rate typed as rupees (demo has 3,929.04) | 24,000 × 3,929.04 % = 9,42,969.60 a month | Type the percent: 25 |
| Tea Rate typed as the month's total (demo has 4,700) | 26 days × 4,700 = 1,22,200 | Type the daily rate: 235 |
| Meal **Time Offset** 0 or blank (demo) | No working-day meal is ever earned | 1.5 |
| Meal **Max Meals per Day** 0 (demo) | No cap | 2 (on the last tab) |
| **Is Flexible Benefit** on Tea (demo) | Taxed as a benefit claim, not as pay | Untick |
| SSF Addition **Depends on Payment Days** on (demo) | A new structure row would cut it twice | Untick on the component, and check each structure row |
| Entered by Hand or arrears **Depends on Payment Days** on | A typed amount is cut for absences | Untick |
| SSF account = 347305 CIT Payable (demo NGI) | SSF posted to the CIT liability | 347302 SSF Payable |
| SSF Addition account = 347302 SSF Payable (demo NGI) | An earning debited to a liability | Salary expense 547101-3 |
| A second Per Overtime Hour component | Every OT hour is paid twice | One Overtime component only |
| A second Late Time component | Every late minute is fined twice | One only |
| A row on the assignment with a later **From Date** | Not paid until then | Clear it, or wait |
| Monthly allowance disabled but still on assignments | Still paid | Stop it with a Salary Revision first (7.2) |
| Salary Arrears made by a revision, no accounts added | Journal stops | Add the rows |
| Basic's Abbr is not `B` | SSF Addition and SSF formulas fail | Abbr B |

### 8.2 Messages from the save (allowance.py)

| Message | Where | Cause | Fix |
|---|---|---|---|
| Accounts row {n}: {account} is not an account of {company} | Salary Component | An account from another company | Pick the account with the row company's suffix |
| Accounts row {n}: {account} is a group account; pick a ledger account | Salary Component | A group (parent) account | Pick the ledger under it |
| Choose the Allowance Kind | Salary Component | Is Allowance on, kind blank | Choose a kind, or untick Is Allowance |
| {component} is paid for Authorised Overtime, so its Type must be Earning, not Deduction. As Deduction it would go on the wrong side of the slip. (title **Wrong Type**) | Salary Component | Overtime made as a Deduction | Type = Earning |
| {component} is paid for Late Time, so its Type must be Deduction, not Earning. … (title **Wrong Type**) | Salary Component | Late Fine made as an Earning | Type = Deduction |
| {component} is paid for {condition}, so it cannot be Exempted from Income Tax. Untick it. (title **Not Tax-Exempt**) | Salary Component | Exempt ticked on Overtime or Late Fine | Untick Exempted from Income Tax |
| Earnings row {n}: {component} is an allowance. List its rate under Allowance Rates; each person gets it from the Allowances on their salary assignment. | Salary Structure | An allowance put in Earnings or Deductions | Delete the row. Add it to Allowance Rates |
| Allowance Rates: {component} is listed twice | Salary Structure | Two rows for one allowance | Delete one |
| Allowance Rates row {n}: {component} is not an allowance | Salary Structure | Is Allowance is off on that component | Pick an allowance, or tick Is Allowance on the component |
| Allowance Rates row {n}: {component} is a {Entered by Hand / Yearly} allowance and is paid when entered | Salary Structure | Load/Unload, Dashain or Encashment in the rate list | Delete the row |
| Allowance Rates row {n}: {component}'s rate cannot be negative | Salary Structure | A minus rate | Type a positive rate |
| Allowance Rates row {n}: to change {component} from {old} to {new}, make a Salary Revision (Raise Rate). It moves the people paid {old} on this structure to the new rate too. (title **Use a Salary Revision**) | Submitted Salary Structure | Editing an existing rate | Put the old rate back. Make a Salary Revision, Raise Rate |
| Allowances: {component} is listed twice | Assignment | Two rows for one allowance | Delete one |
| Allowances row {n}: {component} is not an allowance | Assignment | — | Delete the row |
| Allowances row {n}: {component} is a {kind} allowance and is paid when entered | Assignment | Load/Unload, Dashain or Encashment on an assignment | Delete the row |
| Allowances row {n}: {component}'s rate cannot be negative | Assignment | A minus rate | Fix the rate |
| Allowances row {n}: type {component}'s rate for this person, or remove the row if they do not get it | Assignment | Rate 0, and the structure lists no rate | Type the rate, or delete the row |

### 8.3 Other messages you may see

| Message | Cause | Fix |
|---|---|---|
| Select the Company on row {n} first | Picked an account before the Company | Pick the Company |
| Accounts not set for Salary Component {name} (orange warning) | A row without an O/O account | Fill it, or remove the row |
| Pick the Salary Structure first: it holds the usual rates | Allowance picked before the structure | Pick the structure |
| Please set account in Salary Component {name} | No Accounts row for this company | Add the row (6.2) |
| Set Payroll Section on the Department of these employees, so their pay posts to the right account: … | S/D or F/P filled, Department without a section | Set the Department's Payroll Section |
| Cannot work out the hourly wage for {employee}: no month length given | Overtime or late fine priced without a month | Ask IT |

For every other payroll message see user guide section 17.

---

## 9. One-page checklist

**Before you start**

- [ ] Is it really new? Search the Salary Component list, including disabled ones.
- [ ] Is it an allowance (a person-by-person amount) or a formula line (Basic, SSF, tax)?
- [ ] Which kind? Fixed a month → Monthly. % of initial basic → % of Initial Basic. Per day present → Per Day Present. Typed each month → Entered by Hand. Meal and Overtime already exist.

**The component**

- [ ] Name clear. Abbr short and unique. Basic is `B`.
- [ ] Type right: Earning pays, Deduction takes.
- [ ] Depends on Payment Days: on for Basic, Monthly, % of Initial Basic. Off for everything else.
- [ ] Is Tax Applicable on for every earning.
- [ ] Exempted from Income Tax only on SSF.
- [ ] Variable Based On Taxable Salary only on Income Tax.
- [ ] Statistical, Do Not Include in Total, Is Flexible Benefit: off.
- [ ] Condition and Formula on the component: blank.
- [ ] Is Allowance on for allowances, and **only for earnings**. Allowance Kind chosen.
- [ ] Attendance kind: the Attendance-Driven Rule fields match the recipe (Tea: Pay on Holiday = Pay, Full Day. Meal: 1.5 h, 2 meals, OT-eligible only).
- [ ] Accounts: one row per paying company, all three columns, that company's ledger accounts.
- [ ] Saved with no message.

**The structure**

- [ ] Allowances are in **Allowance Rates**, never in Earnings or Deductions.
- [ ] Formula rows: Basic `base`; SSF Addition `B * 0.20 if custom_ssf_applicable else 0`; SSF `B * 0.31 if custom_ssf_applicable else 0`; Income Tax blank. Only Basic has Depends on Payment Days.
- [ ] A rate change goes through a Salary Revision.

**The assignment**

- [ ] One row per allowance this person gets. No row means not paid.
- [ ] Rate in the right unit: per month, %, per day, per meal. Overtime 0.
- [ ] Initial Basic filled if they get HRA.
- [ ] Submitted.

**The test**

- [ ] One draft slip: the new line shows with the right amount.
- [ ] Someone without the row has no line.
- [ ] Tax moved as expected.
- [ ] Journal on a test site hits the right section's account.

**Retiring**

- [ ] Salary Revision **Stop** first, then remove from Allowance Rates, then Disabled. Never delete a used component.
