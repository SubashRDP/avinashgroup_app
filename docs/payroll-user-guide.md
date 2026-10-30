# Payroll user guide

For HR and accounts staff who set up and run payroll on the desk. It covers the one-time setup, the monthly run, income tax, raises, advances, Dashain, leave encashment, leavers, the new year, and how to undo a run.

- Written on 2026-10-29 from [payroll-complete-reference.md](payroll-complete-reference.md), which was written from the code. Where this guide and the older chapters in [user-guide/](user-guide/README.md) disagree, this guide is right.
- For the code behind any rule, see the reference. This guide only says what to click and what to type.
- Numbers use Nepali grouping: 1,50,000 is one lakh fifty thousand.
- **Not available yet** marks something not built. **Known issue** marks a bug or a trap that is not fixed yet.

---

## Contents

1. [How payroll fits together](#1-how-payroll-fits-together)
2. [One-time setup, in order](#2-one-time-setup-in-order)
3. [Which component to use for what](#3-which-component-to-use-for-what)
4. [Setting up a person](#4-setting-up-a-person)
5. [The monthly run, step by step](#5-the-monthly-run-step-by-step)
6. [How each line on the slip is worked out](#6-how-each-line-on-the-slip-is-worked-out)
7. [Income tax and tax reductions](#7-income-tax-and-tax-reductions)
8. [Raises, revisions and arrears](#8-raises-revisions-and-arrears)
9. [One-off amounts: Payroll Adjustment](#9-one-off-amounts-payroll-adjustment)
10. [Advances](#10-advances)
11. [Dashain allowance](#11-dashain-allowance)
12. [Leave encashment and leave recovery](#12-leave-encashment-and-leave-recovery)
13. [Someone leaving](#13-someone-leaving)
14. [The new fiscal year](#14-the-new-fiscal-year)
15. [Cancelling or correcting a run](#15-cancelling-or-correcting-a-run)
16. [Company differences](#16-company-differences)
17. [Troubleshooting: messages](#17-troubleshooting-messages)
18. [Things that go wrong with no message](#18-things-that-go-wrong-with-no-message)
19. [Glossary](#19-glossary)

---

## 1. How payroll fits together

A person's pay is built from six records. Each one does one job.

| Record | What it holds | Who keeps it |
|---|---|---|
| **Salary Component** | One line of the slip: what it is, how it is counted, whether it is taxed, which accounts it posts to | Accountant and HR manager, once |
| **Salary Structure** | The formula lines everyone on it gets: Basic, SSF Addition, SSF, Income Tax. Also the **Allowance Rates** list of usual rates | HR manager, once a year |
| **Salary Structure Assignment** | One person's pay from a date: Base, Initial Basic, SSF Applicable, tax slab, and the **Allowances** table | HR, per person |
| **Employee** | Ticks that change pay: Overtime Eligible, Replacement Leave, Late Fine Exempt, Women's Tax Rebate. The Department | HR, per person |
| **Department** | The **Payroll Section**: Admin & Accounts (O/O), Marketing (S/D) or Plant (F/P) | HR, once per department |
| **Additional Salary** | Every amount that changes month to month: tea, meal, overtime, late fine, advance instalment, arrears, Dashain, encashment, one-offs | Made by the system. You do not type these |

The month runs like this:

1. Attendance and Overtime Sheets are complete.
2. HR makes a **Payroll Entry** for the company and BS month.
3. **Create Salary Slips**: the system works out tea, meals, overtime, late fines and advance instalments, then makes one draft slip per person.
4. HR checks the drafts.
5. **Submit Salary Slip**: the system works the month out again (so late attendance fixes count), submits the slips and posts the salary journal.
6. The accountant makes the **bank entry** and submits it.

Dashain and leave encashment are paid by a **second Payroll Entry** for the same month, with its own slips, journal and bank entry (sections 11 and 12).

> **There is no Prepare Payroll Inputs button any more.** Some older messages and documents still say "Run Prepare Payroll Inputs". Ignore that. Press **Submit Salary Slip**: it re-posts the month's inputs first.

---

## 2. One-time setup, in order

Do these in the order shown. Each step needs the ones before it.

| # | What | Who | Section |
|---|---|---|---|
| 1 | Company: default payroll payable account; salary, SSF, TDS and advance accounts in the chart | Accountant | 2.1 |
| 2 | Fiscal Year and Payroll Period | Accountant / IT | 2.2 |
| 3 | Income Tax Slab for each company | Accountant | 2.3 |
| 4 | Tax exemption categories (retirement, insurance) | Accountant | 2.4 |
| 5 | Payroll Section on each Department | HR | 2.5 |
| 6 | Salary Components, with accounts for each company | Accountant and HR manager | 2.6 |
| 7 | Salary Structure for each company | HR manager | 2.7 |
| 8 | Payroll Settings and Nepal HRMS Settings | IT / HR manager | 2.8 |
| 9 | Per person: Employee ticks and a Salary Structure Assignment | HR | 4 |

### 2.1 Company accounts

1. Go to **Desk → Accounting → Company** and open the company.
2. In **Default Payroll Payable Account**, choose **347301 - Salary Payable - <ABBR>**. Save.
3. Open that account (**Desk → Accounting → Chart of Accounts**, find 347301). **Account Type** must be **empty**. If it says Payable or anything else, clear it and save. Otherwise the run stops with "Account type cannot be set for payroll payable account".
4. Open **148003 - Staff Advance - <ABBR>**. Set **Account Type** to **Receivable**. Save. Without this, an Employee Advance is refused.
5. Check that these accounts exist for the company (they are leaf accounts, not groups):

| Use | Account (NGI numbers) |
|---|---|
| Salary expense, O/O | 547101 Salary Expenses - O/O |
| Salary expense, S/D | 547102 Salary Expenses - S/D |
| Salary expense, F/P | 547103 Salary Expenses - F/P |
| SSF (31 %) | 347302 SSF Payable |
| Income tax | 348102 11112 TDS-Remuneration Income Tax |
| Staff advance | 148003 Staff Advance |

The chart also has separate expense accounts for some allowances (547104-6 HRA, 547113-5 Overtime, 547130-2 Meal, 547145-7 Dashain and others). Use them if the accountant wants the split. Otherwise post every earning to 547101 / 547102 / 547103.

### 2.2 Fiscal Year and Payroll Period

**Fiscal Year** (needed for every document number, not only payroll):

1. **Desk → Accounting → Fiscal Year → New**.
2. **Year Name**: `83/84` (the short BS form).
3. **Year Start Date**: 1 Shrawan in AD (83/84: 2026-07-17). **Year End Date**: the last day of Ashadh (83/84: 2027-07-16).
4. In **Companies**, add a row for **all seven** companies.
5. Save.

Without it, every document dated in that year fails to number: "… is not in any active Fiscal Year".

**Payroll Period** (one per company):

1. **Desk → HR → Payroll Period → New**.
2. Name it `83/84 - NGI` (the year, a dash, the company abbreviation).
3. **Company**: the company. **Start Date** 2026-07-17, **End Date** 2027-07-16.
4. Save.

Without a payroll period the slip deducts no tax and shows "Start and end dates not in a valid Payroll Period".

IT's year setup (section 14) makes the payroll periods for you. Check they exist.

### 2.3 Income Tax Slab

One slab per company per year.

1. **Desk → HR → Income Tax Slab → New**.
2. **Name**: `Nepal 83/84 - NGI`.
3. **Effective from**: 1 Shrawan (2026-07-17). **Company**: the company. **Currency**: NPR.
4. Tick **Allow Tax Exemption**. Without it, SSF and insurance do not lower the tax.
5. **Standard Tax Exemption Amount**: 0.
6. **Women's Rebate (%)**: 10.
7. In **Taxable Salary Slabs**, type these rows (83/84 rates, Finance Act 2083):

| From Amount | To Amount | Percent Deduction | Condition |
|---|---|---|---|
| 0 | 10,00,000 | 1 | `not custom_ssf_applicable` |
| 10,00,001 | 15,00,000 | 10 | |
| 15,00,001 | 25,00,000 | 20 | |
| 25,00,001 | 40,00,000 | 27 | |
| 40,00,001 | 0 (no upper limit) | 29 | |

8. Save and **Submit**.

The condition on the first row is what waives the 1 % Social Security Tax for SSF members (section 7.2). Type it exactly.

The slab is read **from each person's Salary Structure Assignment**, not by date. A new year's slab only applies once people have new assignments on it (section 14).

### 2.4 Tax exemption categories

These hold the legal limits. They are records, so when the Finance Act changes a limit, edit the record.

**Who creates them.** The app does not. Its patch `setup_tax_exemptions` only adds the custom fields (the retirement-cap tick, the % cap, the women's rebate %). The category and sub-category records are made by hand in the desk. Sites set up before 2026-09-29 got them from an older version of that patch and still have them; a new site starts empty.

**Retirement contribution (the SSF / CIT / PF cap):**

1. **Desk → HR → Employee Tax Exemption Category**, open **Retirement Contribution** (or **New** with that name).
2. **Max Exemption Amount**: 5,00,000.
3. Tick **Retirement Contribution (s.63 cap)**.
4. **Cap: % of Assessable Income**: 33.333333.
5. Tick **Is Active**. Save.

If **Retirement Contribution (s.63 cap)** is unticked, no cap is applied at all and nothing warns you. Check it once a year.

Sub-categories under it (**Desk → HR → Employee Tax Exemption Sub Category**): **Citizen Investment Trust (CIT)** and **Provident Fund (paid directly)**, each with **Max Exemption Amount** 5,00,000.

**Insurance:**

| Sub Category | Tax Exemption Category | Max Exemption Amount (law, 83/84) |
|---|---|---|
| Life Insurance Premium | Insurance Premium | 40,000 |
| Health Insurance Premium | Insurance Premium | 20,000 |
| Building Insurance Premium | Insurance Premium | 10,000 |
| (category) Insurance Premium | | 70,000 |

> **Known issue: Building Insurance limit.** The law allows 10,000 a year. The system has been found holding **5,000** for Building Insurance Premium, and 65,000 for the Insurance Premium category. Fix it:
> 1. **Desk → HR → Employee Tax Exemption Sub Category**, open **Building Insurance Premium**. Set **Max Exemption Amount** to 10,000. Save.
> 2. **Desk → HR → Employee Tax Exemption Category**, open **Insurance Premium**. Set **Max Exemption Amount** to 70,000. Save.
> 3. Any declaration already submitted keeps the old limit. Cancel and amend it, then submit again, so its total is worked out with 10,000.

### 2.5 Department payroll section

Every salary cost goes to one of three sections. The section is set on the **Department**, not on the person.

1. **Desk → HR → Department**, open the department (for example "Sales/ Marketing - NGI").
2. **Payroll Section**: choose **Admin & Accounts** (O/O), **Marketing** (S/D) or **Plant** (F/P).
3. Save.

Every employee needs a Department of their own company, and that Department needs a Payroll Section. Otherwise the run stops for the whole company with "Payroll cannot run yet" or "Set Payroll Section on the Department of these employees".

### 2.6 Salary Components

**Desk → HR → Salary Component**. Open the component, or **New**.

For every field, every Allowance Kind and a filled-in recipe for each component, see [salary-components-guide.md](salary-components-guide.md).

#### Fields every component has

| Field | What it does | Set it to |
|---|---|---|
| **Type** | Earning or Deduction | See section 3 |
| **Depends on Payment Days** | Cuts the amount for unpaid days: amount × payment days ÷ days in the BS month | On for Basic and Monthly / % of Initial Basic allowances. Off for SSF Addition, SSF, tax, and everything priced from attendance (the system turns it off for those) |
| **Is Tax Applicable** | The earning is taxed | On for every earning |
| **Exempted from Income Tax** | The deduction lowers taxable income | On for SSF (and a CIT component, if one is made). **Never** on Overtime or Late Fine: the save refuses it |
| **Variable Based On Taxable Salary** | This is the income tax line | On for **Income Tax** only |
| **Round to the Nearest Integer** | Rounds the line | As the accountant prefers. Salary Arrears is made with it on |
| **Remove if Zero Valued** | Hides a 0 line | On for attendance lines (the system sets it) |

#### The Nepal HRMS fields

| Field | What it does |
|---|---|
| **Is Allowance** | Paid from each person's **Allowances** table on their assignment. An allowance cannot be put in a structure's Earnings |
| **Allowance Kind** | How it is counted. Monthly · % of Initial Basic · Per Day Present · Per Meal · Per Overtime Hour · Entered by Hand · Yearly |
| **Is Attendance Driven** | Priced from attendance when the slips are made. Ticked by the system for Per Day Present, Per Meal and Per Overtime Hour, and for the Late Fine |
| **Condition Type** | The daily rule: Status = Present (tea), Meal Entitlement (meal), Authorised Overtime (OT), Late Time (late fine). Set by the kind |
| **Pay on Holiday** | Tea on a holiday the person worked. **Pay** or **Do Not Pay**. Blank means Pay |
| **A Half Day Counts As** | Tea on a half day: Full Day, Half Day or Not At All |
| **Time Offset (Hours)** | Meal: how early or late counts (1.5) |
| **Max Meals per Day** | Meal: 2 |
| **Only OT-Eligible Staff** | Meal: only people ticked Overtime Eligible. Overtime is always OT-eligible only; the late fine ignores this tick |
| **Attendance Month** | Same as Salary, or Previous Month (count last month's attendance) |
| **Rate Basis** / **Multiplier** | Price from basic. The late fine is always priced from basic with Multiplier 1. Overtime is always 1.5; its Multiplier field is ignored |
| **Rate: Days per Month** | Blank = the real BS month length (29-32). Type 30 to use the old Excel rule |
| **Rate: Hours per Day** | Blank = 8 |
| **Festival Allowance** section | Dashain only (section 11) |

#### Accounts table

One row **per company that pays the component**:

| Column | What to choose |
|---|---|
| **Company** | The company. Pick it first: the account lists then show only that company's leaf accounts |
| **Account** | The **O/O** account. For a deduction, the liability or asset account |
| **Marketing (S/D)** | The S/D account of the same company |
| **Plant (F/P)** | The F/P account of the same company |

Rules:

- An account from another company, or a group account, is refused on save.
- A blank S/D or F/P posts that section's cost to the O/O account. Nothing fails, but the split is lost.
- If S/D or F/P is filled, every person paid this component must have a Payroll Section.
- A component with **no row** for the company stops the journal: "Please set account in Salary Component …".

#### How to configure each component

| Component | Type | Is Allowance / Kind | Depends on Payment Days | Tax | Other settings | Accounts |
|---|---|---|---|---|---|---|
| **Basic Salary** | Earning | No | On | Is Tax Applicable | In the structure, formula `base` | 547101 / 547102 / 547103 |
| **SSF Addition** | Earning | No | **Off** | Is Tax Applicable | Structure formula (2.7) | Salary expense (O/O, S/D, F/P) |
| **SSF** | Deduction | No | **Off** | **Exempted from Income Tax** | Structure formula (2.7) | 347302 SSF Payable |
| **Income Tax** | Deduction | No | Off | **Variable Based On Taxable Salary** | In every structure | 348102 TDS-Remuneration |
| **House Rent Allowance** | Earning | Yes, % of Initial Basic | On | Is Tax Applicable | | Salary expense or 547104-6 |
| **Dearness, Other, Fixed, Fuel, Maintenance, Transport, Gas, Education** | Earning | Yes, Monthly | On | Is Tax Applicable | | Salary expense or its own account |
| **Tea & Conveyance** | Earning | Yes, Per Day Present | (forced off) | Is Tax Applicable | Pay on Holiday = **Pay**; A Half Day Counts As = Full Day | Salary expense |
| **Meal** | Earning | Yes, Per Meal | (forced off) | Is Tax Applicable | Time Offset (Hours) 1.5; Max Meals per Day 2; Only OT-Eligible Staff on | Salary expense or 547130-2 |
| **Overtime** | Earning | Yes, Per Overtime Hour | (forced off) | Is Tax Applicable, **not** exempt | Rate: Days per Month blank; Rate: Hours per Day 8 | Salary expense or 547113-5 |
| **Late Fine** | Deduction | No; Is Attendance Driven, Condition Type = Late Time | (forced off) | **Not** exempt | Rate Basis = Hourly Basic × Multiplier, Multiplier 1 | Salary expense (the fine lowers the salary cost) |
| **Salary Advance** | Deduction | No | Off | Not exempt | | 148003 Staff Advance |
| **Leave Recovery** | Deduction | No | Off | Not exempt | | Salary expense |
| **Salary Arrears** | Earning | No | Off | Is Tax Applicable | Made by the first Salary Revision with arrears | Salary expense |
| **Load/Unload Allowance** | Earning | Yes, Entered by Hand | Off | Is Tax Applicable | Paid by Payroll Adjustment only | Salary expense |
| **Dashain Allowance** | Earning | Yes, Yearly | Off | Is Tax Applicable | **Festival Allowance** ticked; Pay Month 06 - Ashwin (section 11) | 547145-7 or salary expense |
| **Leave Encashment** | Earning | Yes, Yearly | Off | Is Tax Applicable | Named as **Earning Component** on each encashable Leave Type | Salary expense |

The save checks the kind: an allowance must have a kind; Overtime must be an Earning; Late Fine must be a Deduction; neither may be exempt.

> **Known issue: Tea on a new site.** The setup script for a new company still seeds Tea & Conveyance with Pay on Holiday = **Do Not Pay**. The company rule since 15 October 2026 is **Pay**. After onboarding a company, open Tea & Conveyance and check it says Pay.

> **Dashain Bonus** is an old component. Do not use it. Use the component ticked **Festival Allowance**.

> **Daily Wage** is disabled. Daily labour is paid in cash outside payroll.

**Adding a new allowance:**

1. **Desk → HR → Salary Component → New**. Type the name. **Type** = Earning.
2. Tick **Is Allowance**. Choose the **Allowance Kind**.
3. Tick **Is Tax Applicable**. For a Monthly or % of Initial Basic allowance, tick **Depends on Payment Days**.
4. In **Accounts**, add one row per company with all three accounts.
5. Save.
6. If it has a usual rate, add it to each structure's **Allowance Rates** (2.7).
7. Give it to people: a row on each assignment, or a Salary Revision with **Add** (section 8).

### 2.7 Salary Structure

One structure per company per year, for example **NGI Staff 83/84**.

1. **Desk → HR → Salary Structure → New**.
2. **Name**, **Company**, **Payroll Frequency** = Monthly, **Currency** = NPR.
3. **Earnings**:

| Component | Formula | Amount based on formula |
|---|---|---|
| Basic Salary | `base` | ✓ |
| SSF Addition | `B * 0.20 if custom_ssf_applicable else 0` | ✓ |

4. **Deductions**:

| Component | Formula | Amount based on formula |
|---|---|---|
| SSF | `B * 0.31 if custom_ssf_applicable else 0` | ✓ |
| Income Tax | (blank: comes from the slab) | |

   `B` is the abbreviation of Basic Salary. Basic is already cut for unpaid days, so SSF Addition and SSF must **not** have Depends on Payment Days ticked, or they are cut twice.

   A **Late Fine** row is no longer needed. Everyone not ticked Late Fine Exempt is fined.

5. **Allowance Rates**: the usual rate for people on this structure. One row per allowance: **Allowance**, **Rate**. The **Unit** fills itself.

| Allowance | NGI rate | Unit |
|---|---|---|
| Tea & Conveyance | 235 | per day present |
| Meal | 75 | per meal |
| Gas Allowance | 1,690 | per month |
| Education Allowance | 2,780 | per month |
| House Rent Allowance | 25 | % of initial basic |
| Dearness Allowance | 0 | per month (typed per person) |
| Overtime | 0 | from basic × 1.5 (never typed) |

6. **Daily Wage**: leave unticked (it only changes the Dashain base for a daily-wage structure).
7. Save and **Submit**.

What Allowance Rates do, and do not do:

- They fill the Allowances table on a **new assignment** when you pick the structure, and fill the Rate when you pick an allowance on a row.
- They fill a 0 Rate on an assignment row when you save.
- A Salary Revision **Raise Rate** changes them.
- **Payroll never reads them.** A person is paid only what is on their own assignment.
- On a submitted structure, an existing rate cannot be edited: "Use a Salary Revision". You can add or remove rows.
- An allowance put in Earnings or Deductions is refused: "… is an allowance. List its rate under Allowance Rates".

### 2.8 Settings

Check these once. IT normally sets them.

| Setting | Where | Value | Why |
|---|---|---|---|
| Payroll Based On | **Desk → HR → Payroll Settings** | Attendance | Payment days come from attendance |
| Consider Unmarked Attendance As | Payroll Settings | Present | A day with no attendance is paid. Change only with management approval |
| Email Salary Slip to Employee | Payroll Settings | On | Slips are emailed on submit |
| Process payroll in Nepali month | **Nepal HRMS Settings** | On | The month is the BS month (29-32 days) and holidays are paid. If it is off, everyone shows 26 of 31 working days |
| Auto Leave Encashment | HR Settings | Off | Encashment is paid by its own payout entry |
| Scheduler | System Settings → Enable Scheduler | On | Overtime is measured and leave is credited every night (section 18) |

---

## 3. Which component to use for what

| Component | Earning / Deduction | Kind | Where the rate is entered | Cut for unpaid days | Taxed | Example (Basic 30,000, Ashwin 2083 = 31 days, 29.5 payment days) |
|---|---|---|---|---|---|---|
| **Basic Salary** | Earning | Structure formula | **Base** on the assignment | Yes | Yes | 30,000 × 29.5 ÷ 31 = 28,548.39 |
| **SSF Addition** | Earning | Structure formula | **SSF Applicable** tick on the assignment | No (taken from the already-cut Basic) | Yes | 28,548.39 × 20 % = 5,709.68 |
| **SSF** | Deduction | Structure formula | **SSF Applicable** tick | No | Lowers taxable income (up to the cap) | 28,548.39 × 31 % = 8,850.00 |
| **House Rent Allowance** | Earning | % of Initial Basic | Assignment Allowances row: Rate 25 (NGI), 27 (NGN) | Yes | Yes | 24,000 × 25 % = 6,000 × 29.5 ÷ 31 = 5,709.68 |
| **Dearness Allowance** | Earning | Monthly | Assignment Allowances row, per person | Yes | Yes | 2,000 × 29.5 ÷ 31 = 1,903.23 |
| **Gas Allowance** | Earning | Monthly | Assignment row (usual 1,690) | Yes | Yes | 1,690 × 29.5 ÷ 31 = 1,608.23 |
| **Education Allowance** | Earning | Monthly | Assignment row (NGI 2,780, NGN 1,250) | Yes | Yes | 2,780 × 29.5 ÷ 31 = 2,645.48 |
| **Fuel, Other, Fixed, Maintenance, Transport** | Earning | Monthly | Assignment row, per person | Yes | Yes | as Dearness |
| **Tea & Conveyance** | Earning | Per Day Present | Assignment row (NGI 235 old staff, 40 new; NGN 265) | No (counts days present) | Yes, in full that month | 26 days × 235 = 6,110 |
| **Meal** | Earning | Per Meal | Assignment row (NGI/NGN 75, NGG 100) | No | Yes, in full that month | 1 meal × 75 = 75 |
| **Overtime** | Earning | Per Overtime Hour | Nowhere: Basic ÷ BS month days ÷ 8 × 1.5 | No | Yes, in full that month | 4.5 h × 181.4516 = 816.53 |
| **Late Fine** | Deduction | Attendance (Late Time) | Nowhere: Basic ÷ BS month days ÷ 8 ÷ 60 a minute | No | Does **not** lower taxable income | 37 min × 2.0161 = 74.60 |
| **Salary Advance** (advance recovery) | Deduction | Additional Salary | **Monthly Instalment** on the Employee Advance | No | No effect | 5,000 instalment |
| **Leave Recovery** | Deduction | Additional Salary | Worked out: days short × Basic ÷ month days | No | No effect | 3 days × 1,000 = 3,000 |
| **Salary Arrears** | Earning | Additional Salary | Worked out by **Salary Revision** | No | Yes, in full that month | 5,629 (section 8) |
| **Load/Unload Allowance** | Earning | Entered by Hand | **Payroll Adjustment** row | No | Yes, in full that month | 3,500 typed |
| **Dashain Allowance** | Earning | Yearly (Festival Allowance) | Worked out: one month's Base × service factor | No | Yes, on its own slip | 30,000 (full year), 23,013.70 (280 of 365 days) |
| **Leave Encashment** | Earning | Yearly | Worked out: days × Base ÷ month days | No | Yes, on its own slip | 6.5 days × 937.50 = 6,093.75 |
| **Income Tax** | Deduction | Slab | **Income Tax Slab** on the assignment | — | — | 0 for an SSF member under 10,00,000 a year |

"Taxed in full that month" means the whole extra tax the amount adds to the year is taken in the month it is paid, not spread over the remaining months.

**The whole slip for this example** (NGI, SSF member, 1 day absent, 1 half day, 26 days present, one Overtime Sheet with 4.5 hours, 37 minutes late):

| Line | Amount |
|---|---|
| Basic | 28,548.39 |
| SSF Addition | 5,709.68 |
| House Rent Allowance | 5,709.68 |
| Dearness Allowance | 1,903.23 |
| Gas Allowance | 1,608.23 |
| Tea & Conveyance | 6,110.00 |
| Overtime | 816.53 |
| Meal | 75.00 |
| **Gross** | **50,480.74** |
| SSF | 8,850.00 |
| Late Fine | 74.60 |
| Income Tax | 0.00 |
| **Net pay** | **41,556.14** |

---

## 4. Setting up a person

### 4.1 Employee ticks

**Desk → HR → Employee**, open the person.

| Field | Where | Set it to |
|---|---|---|
| **Department** | Main tab | A department of the person's own company that has a Payroll Section |
| **Date of Joining** / **Relieving Date** | Main / Exit tab | Real dates. They decide payment days, Dashain, advance recovery and encashment |
| **Gender** | Main tab | Needed for the Women's Tax Rebate |
| **Overtime Eligible** | **Nepal HRMS** section | Staff below officer level: overtime and meals are paid |
| **Replacement Leave for Holiday Work** | Nepal HRMS section | Officer and admin: a holiday worked earns a day of leave, not overtime. You cannot tick both |
| **Late Fine Exempt** | Nepal HRMS section | CEO, managers, company secretary. No late fine |
| **Women's Tax Rebate** | Nepal HRMS section (women only) | Tick when salary is her only income. Refused for a non-female employee |
| **PAN**, **SSF ID No.** | | Printed on the slip and the deposit report |
| **Default Shift** | Attendance tab | Needed to measure lateness and overtime |
| **Attendance Device ID** | Attendance tab | Needed for any attendance |

Pay is never typed on the Employee. It lives on the assignment.

### 4.2 Salary Structure Assignment

**Desk → HR → Salary Structure Assignment → New**.

| Field | What to type |
|---|---|
| **Employee** | The person |
| **Salary Structure** | The company's structure, for example NGI Staff 83/84. Picking it fills the Allowances table from the structure's Allowance Rates, and **replaces** any rows already there |
| **From Date** | The first day of the BS month the pay starts. For a joiner, the **joining date** |
| **Income Tax Slab** | `Nepal 83/84 - NGI` |
| **Payroll Payable Account** | 347301 - Salary Payable - <ABBR>. Never blank: a blank or different account leaves the person out of the payroll with no message |
| **Base** | The monthly Basic |
| **Initial Basic** (Pay Details) | The person's initial basic. HRA is a % of this, not of Basic (NGI, NGN) |
| **SSF Applicable** (Pay Details) | Tick if the person is in the SSF. Unticked people pay 1 % SST and get no SSF Addition |
| **Allowances** table | One row per allowance the person gets (below) |
| **Taxable Earnings Till Date** | Only for months of this tax year paid **outside** the system: their taxable pay after SSF (section 7.8) |
| **Tax Deducted Till Date** | The tax already deducted in those months |

**Allowances table:**

| Column | Meaning |
|---|---|
| **Allowance** | Only components ticked Is Allowance |
| **Rate** | What this person gets, in the unit shown. Filled from the structure; change it for this person |
| **Unit** | Shown by itself: per month, per day present, per meal, % of initial basic, from basic |
| **From Date** | Blank = from the assignment's From Date. A later date starts the allowance later |

Steps:

1. Fill the header fields.
2. Pick the **Salary Structure**. The Allowances table fills.
3. **Remove** every row the person does not get. **No row means not paid.**
4. Type the Rate where it is 0 (Dearness, Other, Fixed, Fuel: the message after filling lists them). Leave Overtime at 0.
5. Change the Tea rate to 40 for newer NGI staff, if that applies.
6. Save. Check. **Submit**. Only a submitted assignment is used.

Messages on save:

- "type …'s rate for this person, or remove the row if they do not get it": neither the row nor the structure has a rate.
- "… is a … allowance and is paid when entered": Load/Unload, Dashain and Leave Encashment cannot be on an assignment.
- "Allowance … is listed twice": remove one.

A pay change is never an edit of the old assignment. It is a new assignment from the 1st of a BS month (section 8).

The Allowances table is filled only on the form. An assignment made by a Salary Revision, an import or a script is not filled from the structure.

### 4.3 Checklist for a new joiner

1. Employee: company, name, gender, date of joining, Department, PAN, SSF ID No., email.
2. Tick Overtime Eligible **or** Replacement Leave for Holiday Work. Late Fine Exempt if needed. Women's Tax Rebate if it applies.
3. Default Shift and Attendance Device ID.
4. Salary Structure Assignment from the joining date: Base, Initial Basic, SSF Applicable, Income Tax Slab, Payroll Payable Account, Allowances. Submit.
5. If they worked elsewhere earlier in the same tax year, enter Taxable Earnings Till Date and Tax Deducted Till Date (section 7.8).
6. Life or health insurance? File a Tax Exemption Declaration (section 7.5).

---

## 5. The monthly run, step by step

Run one Payroll Entry per company per BS month, after the month ends.

### 5.1 Before you start

| Check | Where |
|---|---|
| Attendance for the whole month is complete and corrected | **Monthly Attendance BS** report; **Attendance Fix**; **Repair from Check-ins** on one day |
| Leave applications are submitted | Leave Application list |
| Late excuses are entered (Monthly Attendance BS → **Late Excused** column → **Excuse ✎**, or open the Attendance → tick **Late Excused**, type the reason → **Update**; no cancel needed) | Attendance |
| Every Overtime Sheet for the month is **submitted** and shows **Worked Hours** | Overtime Sheet list, filter by Date |
| New joiners have a submitted assignment | Salary Structure Assignment list |
| Raises effective this month are submitted | Salary Revision |
| One-off amounts are submitted | Payroll Adjustment |
| New advances have their **Monthly Instalment** | Employee Advance |
| Everyone has a Department with a Payroll Section | Employee list, filter Department is not set |
| Leavers have a Relieving Date | Employee |

### 5.2 Attendance

Pay follows attendance:

| Status | Paid | Tea |
|---|---|---|
| Present | Full day | Yes |
| Half Day | Half day (unless the other half is paid leave) | A full day (A Half Day Counts As = Full Day) |
| On Leave, paid leave type | Full day | No |
| On Leave, Leave Without Pay | No | No |
| Absent | No | No |
| Holiday with no attendance | Full day | No |
| Holiday worked | Full day | Yes, when Pay on Holiday = Pay |
| No attendance on a working day | Paid (Consider Unmarked Attendance As = Present) | No |

Payment days = days employed in the month − Leave Without Pay − absent days (a half day counts 0.5). Holidays are paid. The month has its real BS length, 29 to 32 days.

### 5.3 Overtime Sheet

Overtime and meals are paid only for extra work written on a **submitted** Overtime Sheet.

1. **Desk → HR → Overtime Sheet → New**.
2. **Company**, **Date** (past dates are fine), **Department** (optional), **Why Extra Work Was Needed**.
3. In **Employees**, add each person. Do not type times. **Work Type**, **Day**, **Earns** and **Shift** fill themselves.
4. Save. Problems are listed together under "Rows the policy does not allow". Fix or remove those rows.
5. **Submit** (or send for approval).

The hours are measured from the punches:

- On submit, for a date already past.
- Every night, for sheets whose attendance came later.
- When you press **Measure from Attendance** on the submitted sheet. Press it after fixing attendance.

Hours are exact to the second. They are not rounded: 7 h 54 m 38 s is 7.9106 hours. (Before 15 October 2026 they were rounded to the half hour. The older chapters that say so are out of date.)

On a working day only the time before and after the shift counts. On a holiday or weekly off, the whole time from first IN to last OUT counts.

> **Known issue: a sheet made before the work day.** A sheet submitted on or before its date is measured only by the nightly job. If the scheduler is off, it is never measured and pays 0. Open the sheet after the day and press **Measure from Attendance**.

To change a submitted sheet: **Cancel**, **Amend**, correct, **Submit**. Do it before the payroll. Cancelling a sheet after the run does not remove the overtime already posted until the month is run again.

### 5.4 Advances

Advances given this month are recorded on **Employee Advance** with a **Monthly Instalment** (section 10). The run takes the instalments by itself.

### 5.5 Create the Payroll Entry

1. **Desk → HR → Payroll Entry → New**.
2. **Company**.
3. The month calendar shows the fiscal year's twelve BS months. Click the month you are paying. Greyed months have not started yet.
4. If the month already has an entry, the system asks "… already has payroll entry …. Make another one for it?". Answer **No** unless you need a second run for people left out (5.12).
5. Leave **Payout** blank (blank = the monthly salary).
6. **Settle Leave**: tick it in Ashadh, or in a month someone leaves, so leave taken beyond what was earned is deducted (section 12.3).
7. Leave **Validate Attendance** unticked unless you want the entry refused when any day is unmarked.
8. To pay only part of the company, set Branch, Department or Designation and press **Get Employees**.
9. **Save**.

The system fills Start Date, End Date, Posting Date (the month's last day), Payroll Frequency, Currency, Payroll Payable Account, Cost Center and the Employees table. The date fields lock.

Check:

- The number of employees. If someone is missing, see section 18.
- Orange **Attendance missing**: some people have no attendance this month. Their unmarked days are paid as Present, and they get no tea, meal, overtime or fine. Stop and mark the attendance unless that is intended.
- Orange **Tax history missing**: some people have months of this tax year with no slip. Enter their openings (section 7.8), then save the entry again.

### 5.6 Create Salary Slips

1. Press **Create Salary Slips**.
2. The system first checks everyone. If anything is missing, it stops with **Payroll cannot run yet** and one line per person. Nothing has been posted. Fix each person, or remove them from the Employees table, and press again.
3. It posts tea, meals, overtime, late fines and advance instalments (and leave recovery, if Settle Leave is ticked), then makes one draft slip per person.
4. With more than 30 people it runs in the background: status **Queued**. Wait and reload.
5. The **Payroll Inputs Log** on the entry gets a line, for example "Slips created by hr@…: 212 attendance lines: tea / meal / overtime 1,04,960.00, late fines 5,375.40; 3 advance instalments".

If the status becomes **Failed**, click the word **issue** in the message to read why, fix it, and press **Create Salary Slips** again.

If the log says "… skipped (Error Log)", some lines could not be made. Ask IT to read the Error Log entries titled "Nepal HRMS Attendance Allowance: …".

### 5.7 Review the drafts

1. Run **Desk → HR → Avinas Salary Statement** for the company and month, **Slips = 0 - Draft**. Compare with **Last Month Net**.
2. Open a few slips (Payroll Entry → Connections, or the Salary Slip list filtered by Payroll Entry). Check:
   - **Payment Days** against attendance;
   - tea, meal and overtime;
   - **Income Tax**, **Computed Income Tax**, **Retirement Contribution Over Cap (year)** and **Women's Rebate Applied (%)**;
   - the **Daily Breakdown** table.
3. Fix what is wrong:

| Wrong | Fix |
|---|---|
| Attendance or overtime | Correct it. Submit Salary Slip works the month out again |
| Pay or an allowance | Correct the assignment (a new one if pay changed). Open the slip and **Save** |
| A one-off amount is missing | Add a Payroll Adjustment. It updates the drafts itself |
| One person's tax | On the draft slip, tick **Override Income Tax** and type **Income Tax (manual)** (section 7.9) |

### 5.8 Checks before submitting

Submitted slips are emailed to staff and posted to the books. Before you press Submit Salary Slip, confirm:

1. The head count matches last month, allowing for joiners and leavers.
2. No slip has negative net pay.
3. Payment days look right for people with absences.
4. New joiners and leavers have the right part-month.
5. SSF members show 0 tax below 10,00,000 a year; non-SSF people show 1 % SST.
6. Every component on the slips has an Accounts row for this company (section 16).
7. Every person has a Department with a Payroll Section.
8. Overtime Sheets show Worked Hours (not 0 with a note) for everyone you expect.

### 5.9 Submit the slips

1. On the Payroll Entry press **Submit Salary Slip** and confirm.
2. The system checks everyone again, re-posts the month's inputs from attendance **as it is now**, re-saves every draft, then caps recoveries: a slip that would go below zero has its leave recovery cut first, then its advance, down to a net of 0. The message **Collect Outside Payroll** names what was cut.
3. It submits the slips and posts the **salary journal** (submitted), each person's cost to their section's account.
4. Slips are emailed.

If it stops with an error, nothing is half-posted. Fix it and press again. "Could not submit some Salary Slips: …" means those slips stay draft and the rest went through.

### 5.10 The journal

One Journal Entry, submitted, with **JV Type** and **Document No** filled by itself:

| Side | Lines |
|---|---|
| Debit | Each earning to its section's expense account |
| Credit | SSF → SSF Payable; Income Tax → TDS; Late Fine → back to salary expense; Salary Advance → Staff Advance (per employee); net pay → Salary Payable |

Check it: run Avinas Salary Statement with **Slips = 1 - Submitted**. A green **Matches Journal** card means the sheet and the journal agree. A red card names the section and amount that differ, usually a wrong account on a component.

### 5.11 Bank entry

1. On the submitted Payroll Entry, choose the **Payment Account** (a Bank or Cash account).
2. Press **Update** to save it.
3. Press **Make Bank Entry**.
4. A **draft** Bank Entry (Cash Entry for a cash account) opens: Debit Salary Payable, Credit the bank.
5. The accountant checks it and **submits** it.

Then run **Salary Tax and SSF Deposit** for the month: SSF to the fund by the 15th of the next BS month; SST and remuneration tax to IRD by the 25th.

### 5.12 A second run for the same month

For someone left out (an assignment made late): new Payroll Entry, same month, answer **Yes** to "Make another one?", keep only the missing people, then run as normal. A person already paid that month is refused ("Salary Slip already exists for … for the given dates").

---

## 6. How each line on the slip is worked out

### 6.1 Basic, SSF Addition, SSF

- Basic = Base × payment days ÷ days in the BS month.
- SSF Addition = 20 % of that Basic. It is the employer's share, shown as an earning so it is in the gross and taxed.
- SSF = 31 % of that Basic (20 % employer + 11 % employee). All of it goes to SSF Payable.
- The person's take-home goes down by 11 % of Basic.
- Without SSF Applicable, both lines are 0.

**Not available yet:** whether a non-SSF person should get the 20 % in cash is still to be decided. Today nobody gets it without SSF.

### 6.2 Monthly and % of Initial Basic allowances

- Monthly: the row's Rate × payment days ÷ month days.
- % of Initial Basic: Initial Basic × Rate % × payment days ÷ month days.
- A row with a future **From Date** is not paid yet.
- A row removed from the assignment disappears from the draft on its next save.

### 6.3 Tea & Conveyance

- One unit for each day the person came: Present, Half Day (counts as a full day), and a holiday worked when Pay on Holiday = Pay.
- Nothing for Absent or On Leave.
- Amount = days × the Rate on the person's Tea row.
- No Tea row = no tea.

(The older chapters that say tea is not paid on holidays are out of date. Blank or Pay means it is paid.)

### 6.4 Meal

All of these must hold:

- the person is **Overtime Eligible**;
- a submitted Overtime Sheet names them that day with Earns = Overtime;
- the day is Present or Half Day;
- the person has a **Meal** row on their assignment (no row = no meal; there is no company fallback rate).

Then:

| Day | Meals |
|---|---|
| Working day, punched in 1.5 h or more before the shift | +1 |
| Working day, punched out 1.5 h or more after the shift | +1 |
| Holiday on the sheet, 8 h or more first IN to last OUT | 2 |
| Holiday on the sheet, 6 h to under 8 h | 1 |
| Holiday on the sheet, under 6 h | 0 |
| Any day | never more than 2 |

5.99 hours earns 0. 7 h 59 m earns 1. (The older chapters that say a holiday always earns 2 meals are out of date.)

### 6.5 Overtime

- Hours = the Worked Hours on submitted Overtime Sheets for the month, Earns = Overtime.
- Rate per hour = Base ÷ days in the BS month ÷ 8 × 1.5.
- Example: 30,000 ÷ 31 ÷ 8 = 120.9677; × 1.5 = 181.4516; × 4.5 h = **816.53**. In a 30-day month: 187.50 an hour.
- Needs **Overtime Eligible**. No Overtime row on the assignment is needed.
- The 1.5 is fixed. Rate: Days per Month (blank = real days) and Rate: Hours per Day (8) are on the Overtime component. Change them only with management approval.

**Not available yet:** a warning above 4 hours a day or 24 a week.

### 6.6 Late Fine

- Minutes late in + minutes left early, on working days.
- Not on a day marked **Late Excused**.
- Not for staff ticked **Late Fine Exempt**. Everyone else is fined; no structure row is needed.
- Rate per minute = Base ÷ BS month days ÷ 8 ÷ 60. One minute is charged.
- Example: 37 minutes × (30,000 ÷ 31 ÷ 8 ÷ 60 = 2.0161) = **74.60**.
- There is no cap. **Not available yet:** a cap on the late fine.
- The fine does not lower taxable income.

### 6.7 Running the inputs again

Each run (Create Salary Slips, Submit Salary Slip) replaces the month's tea, meal, overtime, late fine and advance lines and removes what is no longer due. Amounts you entered on a Payroll Adjustment are not touched. A person whose monthly slip is already submitted is left alone: the log says "N already paid, left as they are". To change them, cancel their slip first.

---

## 7. Income tax and tax reductions

### 7.1 How the month's tax is worked out

Every month the system does this for each person:

1. **Project the year.** Taxable pay already paid this year (submitted slips + openings) + this month + the same full month for each month left to Ashadh + one-off amounts this month.
2. **Take off what is exempt.** SSF (and CIT / PF), up to the retirement cap; insurance and other declared amounts.
3. **Apply the slab** to the year's figure. This is the year's tax.
4. **Take off women's rebate**, if ticked.
5. **Spread what is left.** (Year's tax − tax already deducted this year) ÷ months left, including this one.
6. **Add one-off tax in full.** The extra tax that tea, overtime, arrears and other one-offs add to the year is taken this month.

So a change (a raise, a declaration) changes the remaining months' tax, and the year corrects itself.

Months left are counted in BS months, both ends included: Ashwin → Ashadh is 10, Ashadh is 1.

### 7.2 The slab, and the 1 % SST waiver for SSF members

83/84 slabs:

| Yearly taxable income | Rate |
|---|---|
| First 10,00,000 | 1 % SST, **waived for SSF members** |
| 10,00,001 - 15,00,000 | 10 % |
| 15,00,001 - 25,00,000 | 20 % |
| 25,00,001 - 40,00,000 | 27 % |
| Above 40,00,000 | 29 % |

The first band is the Social Security Tax. The slab's condition `not custom_ssf_applicable` skips it for anyone whose assignment has **SSF Applicable** ticked.

**Worked numbers:**

| Person | Yearly taxable | Working | Year's tax |
|---|---|---|---|
| SSF member | 5,00,000 | first band skipped | **0** |
| Not in SSF | 5,00,000 | 5,00,000 × 1 % | **5,000** |
| SSF member | 12,00,000 | 0 + 2,00,000 × 10 % | **20,000** |
| Not in SSF | 12,00,000 | 10,000 + 2,00,000 × 10 % | **30,000** |
| SSF member | 19,54,000 | 0 + 5,00,000 × 10 % + 4,54,000 × 20 % = 50,000 + 90,800 | **1,40,800** |

The system's slab arithmetic adds 0.01 to the 1 % band (4,00,000 shows 4,000.01). It is harmless.

If **SSF Applicable** is wrong on someone's assignment, they are charged SST all year, or not charged when they should be. Check it for every joiner.

### 7.3 Retirement cap: SSF, CIT and PF

SSF, CIT and PF are tax-free only up to the **lower** of:

- 5,00,000 a year, and
- one third of the person's assessable income.

Anything over is added back to taxable income. The slip shows it in **Retirement Contribution Over Cap (year)**.

On SSF alone, the cap is reached only above about 1,34,000 Basic a month (31 % × 1,34,400 × 12 ≈ 5,00,000). It is reached sooner when someone also pays CIT or PF.

**Worked example.** Basic 1,50,000 a month, SSF member, full year in the system:

| Figure | Working | Value |
|---|---|---|
| SSF for the year | 46,500 × 12 | 5,58,000 |
| Assessable income | taxable + exemptions + SSF | 25,90,000 |
| One third of it | 25,90,000 ÷ 3 | 8,63,333 |
| Cap | lower of 5,00,000 and 8,63,333 | 5,00,000 |
| Over the cap | 5,58,000 − 5,00,000 | **58,000** |

The 58,000 is added to the year's taxable income. At the 20 % rate this costs about 11,600 more tax a year.

CIT or PF paid **outside** payroll is counted too: declare it on the Tax Exemption Declaration under **CIT paid directly** or **Provident Fund paid directly** (7.5).

**Not available yet:** a CIT deduction component. Nobody can have CIT deducted through payroll until IT makes one (a Deduction, ticked **Exempted from Income Tax**, with each company's account). It is then given as a recurring Additional Salary.

### 7.4 Insurance

| Insurance | Yearly limit (law) |
|---|---|
| Life insurance | the premium or 40,000, whichever is lower |
| Health insurance (Nepali insurer) | the premium or 20,000, lower |
| Private building insurance (own building) | the premium or 10,000, lower |

> **Known issue:** the system holds **5,000** for building insurance, not 10,000. Fix it as in section 2.4 before filing declarations.

The system applies the limits itself when the declaration is saved. A 50,000 life premium counts as 40,000.

**Worked example.** Life premium 50,000, health premium 25,000, building premium 8,000:

| Line | Declared | Counts as |
|---|---|---|
| Life Insurance Premium | 50,000 | 40,000 |
| Health Insurance Premium | 25,000 | 20,000 |
| Building Insurance Premium | 8,000 | 8,000 (under the 10,000 limit, once fixed) |
| **Total exemption** | | **68,000** |

For someone in the 20 % band, 68,000 off taxable income saves 13,600 tax a year. Filed in Ashwin with 10 months left, it lowers each remaining month by about 1,360.

### 7.5 Filing the declaration and the proof

**Declaration** (any time in the year; the earlier, the more evenly the saving is spread):

1. **Desk → HR → Employee Tax Exemption Declaration → New**.
2. **Employee**, **Company**, **Payroll Period** (`83/84 - NGI`), **Currency** NPR.
3. In **Declarations**, one row per item:
   - **Exemption Sub Category**: Life Insurance Premium, Health Insurance Premium, Building Insurance Premium, Citizen Investment Trust (CIT), or Provident Fund (paid directly).
   - **Exemption Category** fills itself.
   - **Maximum Exempted Amount** shows the limit.
   - **Declared Amount**: the premium actually paid for the year.
4. Save. **Total Exemption Amount** shows what counts after the limits.
5. **Submit**. Only a submitted declaration is used.
6. Draft slips of the month pick it up on their next save. Re-save them, or press Submit Salary Slip.

**Proof** (in Ashadh, the last month):

1. **Desk → HR → Employee Tax Exemption Proof Submission → New**.
2. **Employee**, **Payroll Period**, **Company**.
3. In **Tax Exemption Proofs**, one row per item: **Exemption Sub Category**, **Type of Proof** (for example "Premium receipt"), **Actual Amount**, **Attach Proof**.
4. Save and **Submit**.

In Ashadh the proof replaces the declaration. If the proof is lower, or missing, the tax saved earlier in the year is taken back in Ashadh. Collect receipts before the Ashadh payroll.

### 7.6 Women's 10 % rebate

A woman whose only income is salary gets 10 % off her tax.

- **Who:** tick **Women's Tax Rebate** on her Employee. Unticked means no rebate. Ask her once a year, before Shrawan.
- **How much:** **Women's Rebate (%)** on the company's Income Tax Slab (10). Type it again on each new year's slab.
- The slip shows **Women's Rebate Applied (%)**.

**Worked example.** Her year's tax before the rebate is 1,52,400. With the rebate: 1,52,400 × 0.9 = **1,37,160**. Saving: 15,240 a year.

### 7.7 Full worked example

**Sita**, NGI, SSF member, female, Women's Tax Rebate ticked. Slip for Ashwin 2083 (10 months left). Shrawan and Bhadra paid in the system on the same pay, 11,430 tax each.

Monthly pay: Basic 1,50,000; SSF Addition 30,000; HRA 30,000; Dearness 5,000. Earnings 2,15,000. SSF 46,500. This month also **Salary Arrears 10,000**. Declaration: 68,000 (7.4).

**Step 1: the year's taxable income**

| Figure | Working | Value |
|---|---|---|
| Already paid (Shrawan, Bhadra) | 2 × (2,15,000 − 46,500) | 3,37,000 |
| This month | 2,15,000 − 46,500 | 1,68,500 |
| Months still to come | 1,68,500 × 9 | 15,16,500 |
| Arrears (one-off) | | 10,000 |
| Declaration | | − 68,000 |
| **Total** | | **19,64,000** |
| Without the arrears | | 19,54,000 |

**Step 2: retirement cap.** SSF for the year 5,58,000; cap 5,00,000; **58,000** added back (7.3).

**Step 3: the year's tax, with the cap and rebate**

| Figure | Working | Value |
|---|---|---|
| Regular tax for the year | slab(19,54,000 + 58,000 = 20,12,000) = 1,52,400 × 0.9 | 1,37,160 |
| This month's share | (1,37,160 − 22,860 already paid) ÷ 10 | 11,430 |
| Tax on the arrears, in full | slab(20,22,000) = 1,54,400 × 0.9 = 1,38,960 − 1,37,160 | 1,800 |
| **Income Tax this month** | | **13,230** |

Net pay = 2,25,000 − 46,500 − 13,230 = **1,65,270**.

For comparison, with the declaration but without the cap and the rebate, the same month would be 13,794.

### 7.8 Tax openings for mid-year joiners and go-live months

The year's tax must include months paid **outside** the system: a previous employer, or Shrawan 2083 paid from Excel before go-live. Without them too little is deducted, and the Payroll Entry warns **Tax history missing**.

1. Open the person's **Salary Structure Assignment** (it can be edited after submit).
2. **Taxable Earnings Till Date**: the taxable pay of those months **after SSF**.
3. **Tax Deducted Till Date**: the tax already deducted in them.
4. Save. Save the Payroll Entry again to clear the warning.

These are counted only when the assignment's **From Date** is inside this tax year. For the go-live year that is true of every first assignment.

**Example.** Hari joins NGI on 1 Bhadra 2083. His last employer paid him for Shrawan: 70,000 taxable after SSF, 0 tax (SSF member). Enter 70,000 and 0. From Bhadra his projection is 70,000 + this month + 10 more months.

**Not available yet:** the Shrawan 2083 openings were still missing for almost everyone as of 12 October 2026. The accountant must supply them.

### 7.9 Manual override

To set one person's tax for one month by hand:

1. Open the **draft** slip.
2. Tick **Override Income Tax**.
3. Type **Income Tax (manual)**. 0 is allowed and means "no tax this month".
4. Save.

**Computed Income Tax** keeps what the system worked out, for comparison. The override is for this slip only. Next month's tax counts what was actually deducted, so the difference is caught up over the remaining months.

**Example.** Computed 13,230, override 12,000. Next month's projection sees 1,230 less tax paid and spreads it over the 9 months left (about 137 more each month).

"No income tax Salary Component is set up, so it cannot be overridden" means the structure has no Income Tax row. Tell IT.

### 7.10 Tax on Dashain and leave encashment

These are paid on their own slip. That slip deducts **the whole tax the payment adds to the year**, at the person's own rate, with the retirement cap and the women's rebate:

> payout tax = (year's tax with the payout − year's tax without it) × (1 − rebate)

**Example.** Sita (7.7), Dashain 1,50,000 in Ashwin. Year without it 20,12,000 (after the cap); with it 21,62,000.

- slab(21,62,000) − slab(20,12,000) = 1,82,400 − 1,52,400 = 30,000
- × 0.9 (rebate) = **27,000**
- The Dashain slip pays 1,50,000 − 27,000 = **1,23,000**.

The salary slip of the same month deducts the usual month's tax. From the next month the system counts both slips.

For an SSF member well below 10,00,000 a year, a Dashain payout that keeps the year under 10,00,000 is taxed 0.

> **Known issue: payout tax on submit.** The payout tax worked out on the draft can differ from the tax on submit when the payout straddles a slab boundary, because on submit the fixed allowances are left out of the projection. Compare the draft and the submitted figure for anyone near 10,00,000, 15,00,000 or 25,00,000.

### 7.11 Not handled by payroll

**Not available yet:** children's tuition (25 % or 25,000), remote-area deduction, disability relief and the medical tax credit. Donations are claimed by the person on their own return.

---

## 8. Raises, revisions and arrears

A pay change is a new, dated assignment. **Salary Revision** makes them for many people at once.

Rules:

- **Effective From** must be the **1st of a BS month**. The system tells you the right date if not.
- Months already paid at the old pay are paid as **arrears** in one later month. Submitted slips are never changed.

**Allowance Changes:**

| Change | Reaches | Does |
|---|---|---|
| **Raise Rate** | Everyone on the chosen structure at the usual rate | Their rate and the structure's Allowance Rate become the New Rate. People on their own rate are not raised; Get Employees names them |
| **Add** | Listed employees who do not have it | Gives it at the New Rate, or the structure's usual rate if blank |
| **Stop** | Listed employees who have it | Takes it off |
| **Change Rate** | Listed employees who have it | Sets their rate to the New Rate |

Overtime cannot be raised: raise the Basic.

**Steps:**

1. **Desk → HR → Salary Revision → New**.
2. **Company**.
3. **Effective From**: the 1st of the BS month. **BS Month** fills itself.
4. **Reason**, for example "Annual increment 2083".
5. For a Basic raise: **Hike % for Everyone** (change each person after if needed).
6. For allowances: rows in **Allowance Changes**.
7. If the change starts in a paid month: tick **Pay Arrears** and set **Arrears Paid In** to a date inside the BS month the arrears are paid.
8. **Get Employees**. Each row shows Current / New Basic, Current / New Dearness, the allowance changes and the arrears.
9. Adjust rows: **Hike %** or **New Basic**, **New DA**, or remove people.
10. **Save**. Check **Monthly Increase** and **Arrears**. **Submit**.

On submit, each person gets a new assignment from the effective date, carrying over everything else (other allowances, Initial Basic, SSF Applicable). Arrears become a **Salary Arrears** earning in the chosen month, taxed in full that month.

**How arrears are worked out:**

- Monthly pay (Basic, Dearness, HRA, Gas …): the monthly increase × payment days ÷ month days, for each paid month.
- Tea and meal: (new rate − old rate) × the days or meals each paid month counted.

**Example.** A raise from 1 Shrawan, agreed in Ashwin. +2,000 Basic and +500 Dearness = 2,500 a month. Shrawan paid 31 of 31 days, Bhadra 29.5 of 31.

| Part | Working | Amount |
|---|---|---|
| Shrawan | 2,500 × 31 ÷ 31 | 2,500.00 |
| Bhadra | 2,500 × 29.5 ÷ 31 | 2,379.03 |
| Tea 235 → 250 | 15 × (26 + 24 days) | 750.00 |
| **Arrears** | | **5,629.03**, shown as 5,629 |

> **Known issue: no SSF on arrears.** The arrears leave out SSF Addition and SSF. The 20 % and 31 % on the raise for the back months are never paid or deducted. Until fixed, the accountant must post the SSF difference by hand (a Payroll Adjustment row for SSF Addition and one for SSF).

**Undo:** cancel the Salary Revision. The new assignments and the arrears are cancelled, and a raised structure rate goes back.

| Message | Fix |
|---|---|
| A salary revision must start on the first day of a BS month … | Use the date the message gives |
| Row …: … has no salary structure assigned | Give the person an assignment first |
| Row …: … already has a salary assigned from … | Remove the row, or cancel that assignment |
| … is worked out from each person's basic; raise the basic instead | Overtime cannot be raised by rate |

---

## 9. One-off amounts: Payroll Adjustment

For an amount in one month only: Load/Unload, an extra deduction, a correction.

1. **Desk → HR → Payroll Adjustment → New**.
2. **Company**.
3. **Payroll Date**: any date inside the BS month being paid.
4. **Reason**.
5. **Adjustments**: one row per person and component: **Employee**, **Component**, **Amount**, **Note**.
6. Save and **Submit**.

Each row becomes an Additional Salary on that month's slip. Draft slips update themselves. Earnings are taxed in full that month. **Cancel** the adjustment to take all rows back.

- Tea, meal, overtime and late fine cannot be chosen here.
- Amount must be above zero. For a deduction, choose a deduction component.
- Put a person's whole amount for one component on one row.

---

## 10. Advances

### 10.1 Giving an advance

1. **Desk → HR → Employee Advance → New**.
2. **Employee**, **Purpose**, **Advance Amount**.
3. **Advance Account**: 148003 - Staff Advance - <ABBR> (must be Receivable, section 2.1).
4. Tick **Repay Unclaimed Amount from Salary**.
5. **Recovery from Salary**: **Monthly Instalment**, and **Recover From** (the first date recovery may start; blank = the next payroll).
6. Save and **Submit**. The accountant pays it with the **Payment** button.

### 10.2 How it is recovered

- Each month: the lower of the Monthly Instalment and what is still owed. A blank instalment takes the whole balance in one month.
- Owed = paid − claimed − already returned.
- **Leaver**: in the month of the Relieving Date, the **whole** balance, whatever the instalment.
- **Cap**: if the slip would go below zero, the recovery is cut to what the slip can pay. The rest stays owed and **Collect Outside Payroll** names it.

**Example.** Advance 50,000, 20,000 already returned, 30,000 owed, instalment 5,000. A normal month takes 5,000. If the person leaves this month, 30,000 is due; if their net before the advance is 12,000, the system takes 12,000, net pay is 0, and "collect 18,000 outside payroll" is shown. The advance still shows 18,000 owed.

The advance shows the instalment as returned as soon as the slips are **created**, not when they are submitted.

> **Known issue:** cancelling a Payroll Entry does not give the instalment back. The advance still shows it returned. Running the same month again replaces it. If you will not run the month again, ask IT to cancel that month's Additional Salary rows with Source "Advance Recovery" for the person.

---

## 11. Dashain allowance

### 11.1 The rule

- One month's **Base** on the person's assignment on the cut-off date. No allowances, no SSF, no deductions.
- A full year or more of service by the cut-off: 100 %.
- Under a year: service days ÷ days in the year (365 or 366) × Base.
- Never more than one month's Base.
- Nothing for someone who joins on or after the cut-off, has already been paid this year, or (unless the settings say so) left before the cut-off or is daily-wage.

**Example.** Base 30,000, cut-off 2026-10-17. Joined 2026-01-10: 280 ÷ 365 = 0.767123 × 30,000 = **23,013.70**. Joined on or before 2025-10-17: **30,000**.

### 11.2 Settings

**Desk → HR → Salary Component → Dashain Allowance**, **Festival Allowance** section:

| Setting | Value | Meaning |
|---|---|---|
| **Festival Allowance** | ✓ | Paid by a Dashain payout entry, never on the salary slip |
| **Pay Month** | 06 - Ashwin | Only an Ashwin payout entry may pay it |
| **Minimum Service Days** | 0 | Fewer days than this → nothing |
| **Prorate for Under a Year** | ✓ | Off = any service before the cut-off pays a full month |
| **Include Daily-Wage Staff** | ✗ | Daily wage is paid outside payroll |
| **Include Staff Leaving Before the Cut-off** | ✗ | On = leavers are paid, counting service to their relieving date |

### 11.3 Paying it

It is paid on its **own Payroll Entry and slips**, separate from the Ashwin salary. The older chapters that describe a Pay Dashain tick or button on the salary entry are out of date.

1. **Desk → HR → Payroll Entry → New**. Company. Click **Ashwin**. Answer **Yes** to "Make another one?".
2. **Payout**: **Dashain Allowance**.
3. **Festival Component**: Dashain Allowance.
4. **Count Service To (Cut-off)**: Ghatasthapana or the payment date. Blank = the month's last day.
5. Save. **Get Employees** lists the company.
6. **Create Salary Slips**. The system builds and **submits** a **Payroll Adjustment** (linked as **Dashain Payroll Adjustment**), one row per person with Basic, Service Days and Factor; the Note says "Full year" or "280 of 365 days". People with nothing due are taken off the entry; the log names them.
7. Check the slips: each has only the Dashain line and its tax (7.10).
8. **Submit Salary Slip**, then **Make Bank Entry**, as for salary.

The salary entry and the payout entry can be made in either order.

To pay one person by hand, add a row for the festival component on a Payroll Adjustment: it is still paid by the Dashain payout entry, not on the salary slip.

> **Known issue:** never untick **Disabled** on a Dashain or encashment Additional Salary. That puts it on the monthly slip as well, and the person is paid twice.

---

## 12. Leave encashment and leave recovery

### 12.1 The rule

At year end (Ashadh), the balance left on each encashable leave type is paid on its own slip. Nothing is carried forward.

- Days = balance on the year's last day − **Non-Encashable Leaves**, capped at **Maximum Encashable Leaves** (0 = no limit).
- Rate per day = Base ÷ **Encashment Days per Month** (blank = the BS month's days).
- Amount = days × rate.

**Example.** Ashadh 2084 has 32 days. Base 30,000 → 937.50 a day. 6.5 days → **6,093.75**.

### 12.2 Settings on each Leave Type

**Desk → HR → Leave Type**, **Encashment** section:

| Setting | Casual / Sick Leave | Others |
|---|---|---|
| Allow Encashment | ✓ | ✗ (Maternity, Paternity, Replacement, Leave Without Pay) |
| Earning Component | Leave Encashment | |
| Maximum Encashable Leaves | 0 | |
| Non-Encashable Leaves | 0 | |
| **Encash at Year End** | ✓ | |
| **Encash at Separation** | ✓ | |
| **Encashment Days per Month** | blank | |

### 12.3 Paying it (Ashadh)

1. Wait until Ashadh's last-day leave credit has run.
2. **Payroll Entry → New**, Company, click **Ashadh**, answer **Yes** to "Make another one?".
3. **Payout**: **Leave Encashment**. **Settle Leave** ticks itself. Save.
4. **Create Salary Slips** (on or after the first day of the month). Each person's balance is encashed and submitted as a **Leave Encashment**, dated the year's last day. People with nothing due are taken off; the log says why (no assignment, no balance, already encashed).
5. Check the encashments in the **Leave Encashment** list: Balance, Days Encashed, Monthly Basic, Days per Month, Rate per Day, Amount.
6. **Submit Salary Slip** and **Make Bank Entry**. The encashments turn **Paid**.

A second encashment of the same allocation is refused, even by hand.

### 12.4 Leave recovery

Leave can be taken before it is earned. If someone leaves, or the year ends, with a negative balance, the days short are deducted from the **salary** slip as **Leave Recovery**:

1. On that month's **salary** Payroll Entry (Payout blank), tick **Settle Leave** before Create Salary Slips.
2. Days short × Base ÷ month days is deducted.

**Example.** −3 days in Kartik 2083 (30 days), Base 30,000 → 1,000 a day → **3,000** deducted.

If the deduction is more than the slip can pay, it is cut first (before the advance), and Collect Outside Payroll names the rest.

---

## 13. Someone leaving

1. Set the **Relieving Date** on the Employee. Keep the status **Active** until all payouts are submitted: an encashment is refused for someone who has Left.
2. Run that month's **salary** entry with **Settle Leave** ticked. The person is paid to the relieving date. Their whole advance balance is recovered (cut to what the slip can pay). A negative leave balance is recovered.
3. If they have leave left, make a **Leave Encashment** payout entry for the month. Everyone relieved in the month is encashed at Separation, on their own slip.
4. If Dashain is due and **Include Staff Leaving Before the Cut-off** is ticked, they are included in the Dashain payout.
5. Collect anything named under **Collect Outside Payroll**.
6. After everything is submitted, set the status to **Left**.

A single leaver's encashment can also be made by hand: **Leave Encashment → New**, Employee, Leave Type, **Encashment Date** = the relieving date. Days and amount fill themselves. It is paid by that month's Leave Encashment payout entry.

> **Known issue: a leaver's tax.** The tax projection still counts months up to Ashadh, not to the relieving date. The last month's tax can be wrong. Check the leaver's tax with the accountant and use **Override Income Tax** if needed.

---

## 14. The new fiscal year

Do these before 1 Shrawan.

| # | What | Who | When |
|---|---|---|---|
| 1 | **Fiscal Year** for the new year (for example 84/85) with **all seven companies** (2.2) | Accountant / IT | Before 1 Shrawan. Without it nothing can be numbered |
| 2 | **Income Tax Slab** per company for the new year, effective 1 Shrawan, with **Women's Rebate (%)** and the SST condition (2.3) | Accountant | After the budget (15 Jestha), by Ashadh |
| 3 | Check the exemption limits against the new Finance Act (2.4) | Accountant | Same time |
| 4 | Leave policies for the new year, submitted | HR | Ashadh |
| 5 | Shift Types and each person's Overtime Eligible / Replacement Leave tick | HR | Ashadh |
| 6 | IT runs the **year setup**: holiday lists, leave period, **payroll period**, a **new salary assignment for everyone from 1 Shrawan on the new slab**, leave policy assignments | IT | Ashadh |
| 7 | Festivals added to the new holiday lists (Holiday Bulk Update); Teej and Women's Day on the Women lists only | HR | Right after step 6 |
| 8 | Leave encashment for the closing year (12.3) | HR | Ashadh |
| 9 | Declarations: new ones for the new year; proofs for the old year (7.5) | HR | Ashadh / Shrawan |
| 10 | Ask each woman about the Women's Tax Rebate | HR | Before Shrawan's payroll |

> **Not available yet:** the 84/85 tax rates are not built into the year setup. The accountant must enter the 84/85 slabs by hand (step 2), or IT must add them, before the setup runs. The setup refuses to run without them, and never copies last year's rates.

> **Check after step 6.** The new assignments copy Base, Initial Basic, SSF Applicable and the whole Allowances table. Open two or three and compare with the old ones. The new slab applies only through these new assignments: anyone without one is taxed at last year's rates with no warning.

---

## 15. Cancelling or correcting a run

### 15.1 Before submitting the slips

Nothing is posted to the books yet. Fix the cause and press **Submit Salary Slip**: it works the month out again. To remove one person, delete their draft slip and their row in Employees.

### 15.2 Undoing a submitted month

Cancel in this order:

1. The **bank entry**: cancel it if submitted, **delete** it if still draft. Cancelling the Payroll Entry does not remove a draft bank entry.
2. The **Payroll Entry**: **Cancel**. This cancels and deletes its slips and cancels the salary journal. With more than 50 slips it runs in the background.
3. For a **Dashain** payout: cancel the **Payroll Adjustment** linked as Dashain Payroll Adjustment. For an **encashment** payout: cancel each **Leave Encashment**. If you skip this, a new payout entry finds them "already paid" and pays nothing.
4. Fix the cause.
5. Make a new Payroll Entry for the month.

Left behind after a cancel, and what to do:

| Left behind | What to do |
|---|---|
| The month's tea, meal, overtime and late-fine lines | Nothing. The new run replaces them |
| Advance instalments, still showing returned | The new run replaces them. If not re-running, ask IT (section 10.2) |
| Leave Recovery lines | The new run replaces them |
| A draft bank entry | Delete it |
| The Payroll Inputs Log | Nothing; it is a record |

### 15.3 Correcting one person

1. Cancel that person's submitted slip. Their month counts as unpaid again.
2. Fix the cause (attendance, assignment, adjustment).
3. Make a new Payroll Entry for the month with only that person (5.12).
4. The accountant reverses and re-posts their part of the journal and bank payment.

### 15.4 Other cancels

- **Salary Revision**: cancels its arrears and new assignments, and puts raised structure rates back.
- **Overtime Sheet**: withdraws replacement leave only. Overtime already posted stays until the month is run again.
- **Payroll Adjustment**: cancels all its rows.

---

## 16. Company differences

| | NGI | NGN | NGG | NGK | GLMI / GEPL / SGU |
|---|---|---|---|---|---|
| Runs payroll | Yes | Yes | Yes | Yes | **Not yet** (no structure, no staff on payroll) |
| Pay model | Initial basic | Initial basic | Grade scale | Grade scale | — |
| HRA (% of Initial Basic) | 25 % | 27 % | — | — | — |
| Gas / Education (usual) | 1,690 / 2,780 | 1,690.27 / 1,250 | — | — | — |
| Tea, old / new staff | 235 / 40 | 265 / 40 | — | — | — |
| Meal | 75 | 75 | 100 | — | — |
| Per-person allowances | Dearness, Other, Fuel | same | Fixed, Dearness, Other, Fuel | Fixed, Dearness, Other, Fuel, Maintenance | — |
| Leave (policy) | 21 + 12 | 21 + 12 | 21 + 12 | **8 + 12** | — |
| Structure | NGI Staff 83/84 | NGN Staff 83/84 | NGG Staff 83/84 | NGK Staff 83/84 | none |

Account mapping on avinas1 (snapshot of 12 October 2026, not re-checked since):

| Company | State | Effect |
|---|---|---|
| NGI | All active components mapped, with O/O, S/D and F/P | Posts |
| NGN | 10 components, O/O only. **Tea & Conveyance and Meal have no account** | **Known issue:** the journal stops at "Please set account in Salary Component …" until the accountant adds them |
| NGG | Only a Meal row, without an account. 27 of 27 staff without a Payroll Section | **Known issue:** cannot post |
| NGK | None | **Known issue:** cannot post |
| GLMI, GEPL, SGU | None | Not running payroll |

The Income Tax Slabs are the same for all seven companies.

> **Known issue (copy sites):** on the demo copy, NGI's SSF is mapped to 347305 CIT Payable and SSF Addition to 347302 SSF Payable. That is wrong. Do not copy that mapping to a live site: SSF Addition is a salary expense and SSF goes to SSF Payable.

---

## 17. Troubleshooting: messages

Search this page (Ctrl+F) for a few words of the message. "…" stands for a name, date or number.

| Message | Cause | Fix |
|---|---|---|
| **Payroll cannot run yet** — "Nothing was posted. Fix these, or remove the people …" | Someone has no submitted assignment starting on or before the month start (or joining day), no Department, or a Department with no Payroll Section | Fix each person listed, or remove them from Employees. Nothing to clean up |
| Set Payroll Section on the Department of these employees … | The journal needs the section | Set Department on the Employee and Payroll Section on the Department. Press Submit Salary Slip again |
| Please set account in Salary Component … | No Accounts row for this company | Accountant adds the row (2.6) |
| Account type cannot be set for payroll payable account … | 347301 has an Account Type | Clear Account Type on the account |
| Set Default Payroll Payable Account on Company …, or choose one on this entry. | Company has no default | Set it on the Company (2.1) |
| No employees found … | No submitted assignments for the month, or a different payable account | Check assignments (section 18) |
| No active or default Salary Structure found for employee … | No submitted assignment | Make and submit one |
| Duplicate Entry: Salary Slip already exists for … for the given dates | Already paid a slip of the same kind this month | Remove them from the entry |
| Salary Slip of employee … already created for this period | Same; or a slip made by hand in a month with a payout slip | Remove them; make the slip from a Payroll Entry |
| Cannot submit. Attendance is not marked for some employees. | Validate Attendance is ticked | Complete attendance, or untick it |
| Posting date is in another BS month | Posting date moved out of the month | Click the month on the calendar again |
| Slip and payroll entry disagree on the month | Dates changed after slips were made | Tell IT. Usually cancel and remake the slips |
| Attendance missing (orange) | No attendance for some people | Mark attendance, unless paying without it is intended |
| Tax history missing (orange) | Earlier months of the year have no slip | Enter Taxable Earnings / Tax Deducted Till Date (7.8) |
| Salary Slip creation failed. You can resolve the issue and retry creation. | A slip could not be made | Click **issue**, fix, press Create Salary Slips |
| Could not submit some Salary Slips: … | Those slips have negative net pay or an error | Open them, fix, press Submit Salary Slip again |
| Net Pay cannot be less than 0 | Deductions exceed earnings (not a recovery the cap can cut) | Reduce the deduction, or check the slip |
| Collect Outside Payroll | A recovery was cut to what the slip could pay | Collect the named amount outside payroll |
| … skipped (Error Log) | An attendance line could not be made | Tell IT |
| Choose the Payment Account and press Update to save it, then make the bank entry. | Payment Account not saved | Choose it, **Update**, then Make Bank Entry |
| Payment Account … is a … account. Salary is paid from a Bank or Cash account. | Wrong account | Choose a Bank or Cash account |
| Run Prepare Payroll Inputs on its Payroll Entry before submitting | Old wording; the button is gone | Press **Submit Salary Slip**: it re-posts first |
| Income Tax Slab not set in Salary Structure Assignment … | Assignment has no slab | Set **Income Tax Slab** on the assignment |
| … must be effective on or before Payroll Period Start Date | Slab dated after 1 Shrawan | Fix the slab's Effective from |
| Start and end dates not in a valid Payroll Period | No payroll period | Create it (2.2) |
| No income tax Salary Component is set up, so it cannot be overridden. | Structure has no Income Tax row | Untick the override; tell IT |
| Women's Tax Rebate is only for female employees … | Tick on a non-female employee | Untick it, or correct Gender |
| … is not in any active Fiscal Year | New year missing | Create the Fiscal Year with all seven companies |
| Employee advance account … should be of type Receivable | 148003 not Receivable | Set Account Type = Receivable |
| Choose the Allowance Kind | Is Allowance ticked, no kind | Choose the kind |
| Accounts row …: … is not an account of … / … is a group account | Wrong company or group account | Choose a leaf account of that company |
| Wrong Type: … must be Earning / Deduction · Not Tax-Exempt | Overtime as deduction, fine as earning, or either exempt | Correct Type; untick Exempted from Income Tax |
| … is an allowance. List its rate under Allowance Rates … | Allowance in a structure's Earnings | Remove it; use Allowance Rates and assignments |
| Use a Salary Revision | Edited a rate on a submitted structure | Use Salary Revision → Raise Rate |
| Allowances row …: type …'s rate for this person, or remove the row … | No rate anywhere | Type the rate, or remove the row |
| … is a … allowance and is paid when entered | Yearly or Entered by Hand on an assignment | Remove it; use Payroll Adjustment or the payout entry |
| Nothing to pay — "Nobody on this entry has … to be paid between …" | Payout entry with nobody due | Read the log; delete the entry if correct |
| … is paid once, on its own payout; it cannot be recurring. | Dashain or encashment made recurring | Untick recurring |
| … is not a festival allowance (tick Festival Allowance …) | Wrong Festival Component | Pick the component ticked Festival Allowance |
| … is paid in 06 - Ashwin; this entry is for … | Wrong month | Use Ashwin, or change Pay Month |
| Draft … already holds … for this year | Another entry's Dashain draft exists | Delete or submit that draft |
| The Payroll Entry has no employees yet | Payout entry not filled | Get Employees, Save |
| Dashain not paid on the salary (orange) | Old Pay Dashain tick cleared | Make a Dashain payout entry |
| … already encashes this allocation | Already paid | Cancel the old one first if wrong |
| Leave is encashed at year end … or at separation … | Wrong encashment date | Use the allocation's last day or the relieving date |
| … is not encashed at year end / separation | Leave Type setting | Tick Encash at Year End / Separation if policy |
| No Leave Period for … covers … | Year setup not run | Tell IT |
| A salary revision must start on the first day of a BS month … | Wrong date | Use the date given |
| Row …: amount must be more than zero · … already has a … row · … belongs to … | Payroll Adjustment row errors | Fix the row |
| Rows the policy does not allow · Authorised Twice | Overtime Sheet row errors | Fix or remove the rows |
| Tick either Overtime Eligible or Replacement Leave …, not both | Both ticked | Untick one |

---

## 18. Things that go wrong with no message

| What you see | Why | Fix |
|---|---|---|
| Someone missing from the Payroll Entry | Not Active; joined after the month; no submitted assignment; **blank or different Payroll Payable Account on the assignment** | Fix, then Get Employees (draft) or a second entry (5.12) |
| Allowance not paid | No row on the assignment, or its From Date is in the future | Add or correct the row; re-save the slip |
| Meal not paid | No Meal row on the assignment; not OT Eligible; not on the sheet; under 1.5 h | See 6.4 |
| Overtime 0 | Not OT Eligible; sheet not submitted; sheet made before the day and not measured; Earns = Replacement Leave; no shift | Press **Measure from Attendance** on the sheet |
| Overtime and holiday meals 0 for everyone | Scheduler off, so sheets are never measured at night | Ask IT to turn the scheduler on; press Measure from Attendance on each sheet |
| Leave credit missing; encashment or recovery wrong | Scheduler off, so the month-end credit did not run | Ask IT |
| Everyone shows 26 of 31 working days | Nepal HRMS Settings "Process payroll in Nepali month" is off | Ask IT to turn it on |
| Pay for unmarked days | Consider Unmarked Attendance As = Present | Mark Absent days properly |
| SST charged all year to an SSF member (or not charged to a non-member) | SSF Applicable wrong on the assignment | Correct it; tax catches up over the remaining months |
| Last year's tax rates in the new year | Person has no new assignment on the new slab | New assignment from 1 Shrawan (section 14) |
| No retirement cap applied | Retirement Contribution (s.63 cap) unticked on the category | Tick it (2.4) |
| Building insurance capped at 5,000 | Wrong limit on the sub-category | Fix it (2.4) |
| A leaver's tax looks wrong | Projection runs to Ashadh, not the relieving date | Check with accounts; override |
| Payout tax differs between draft and submitted slip | Fixed allowances left out of the projection on submit | Check people near a slab boundary |
| Arrears without SSF | SSF not in the arrears | Post the SSF difference by hand (section 8) |
| Advance shows returned though no slip paid it | Returned when slips are created; cancel does not undo it | Re-run the month, or ask IT |
| Dashain or encashment pays nothing after cancelling its entry | The Payroll Adjustment / Leave Encashments are still submitted | Cancel them first (15.2) |
| Dashain paid twice | Disabled unticked on a payout Additional Salary | Never untick it |
| A slip made by hand is refused | A payout slip exists that month | Make it from a Payroll Entry |
| Daily Breakdown wrong but the slip saved | Breakdown errors go to the Error Log | Tell IT; pay is not affected |
| Leftover draft bank entry | Cancel removes only submitted journals | Delete it |
| Late fine lowers salary expense | By design: it is mapped to the salary expense account | Nothing |
| Large company: some slips miss the latest attendance lines | With more than 30 people, slips are made in the background; in rare cases a worker may start before the inputs are saved (not confirmed) | Re-save the drafts, or press Submit Salary Slip, which re-posts and re-saves |
| Submit Salary Slip slow or times out on a large company | Every draft is re-saved in the same request | Wait and reload; if it fails, press again |
| Old Ashwin entries end on 16 October | Made before the calendar fix; Ashwin 2083 now ends 17 October | Re-saving such a draft may fail "Posting date is in another BS month": click Ashwin on the calendar again |

---

## 19. Glossary

| Term | Meaning |
|---|---|
| **Additional Salary** | A one-month amount added to a slip. The system makes them for tea, meals, overtime, fines, advances, arrears, Dashain, encashment and Payroll Adjustment rows |
| **Allowance Kind** | How an allowance is counted: Monthly, % of Initial Basic, Per Day Present, Per Meal, Per Overtime Hour, Entered by Hand, Yearly |
| **Allowance Rates** | The usual rates on a Salary Structure. They fill forms; payroll does not read them |
| **Allowances table** | The rows on a person's assignment. The only place payroll reads allowances from |
| **Arrears** | The difference owed for months already paid at the old pay, after a backdated raise |
| **Assessable income** | Income before the retirement contribution, used for the one-third cap |
| **Base** | The monthly Basic on the assignment |
| **BS** | Bikram Sambat, the Nepali calendar. **Miti** is a BS date |
| **CIT** | Citizen Investment Trust. A retirement contribution inside the 5,00,000 cap |
| **Cut-off** | The date service is counted to for Dashain |
| **Declaration / Proof** | Employee Tax Exemption Declaration (during the year) and Proof Submission (in Ashadh, with receipts) |
| **Draft / Submitted** | A draft can change; a submitted document is final and posted |
| **F/P** | Filling Plant section (Plant) |
| **Festival Allowance** | The tick that makes a component the Dashain allowance |
| **Fiscal Year** | Shrawan to Ashadh, named like 83/84 |
| **Full tax** | The whole extra tax of a one-off amount, taken in its month |
| **Initial Basic** | The basic HRA is a percentage of (NGI, NGN) |
| **Late Excused** | A tick on one day's Attendance that removes that day's fine |
| **Leave Recovery** | A deduction for leave taken beyond what was earned |
| **O/O** | Office section (Admin & Accounts) |
| **Override Income Tax** | A tick on a draft slip to set the tax by hand |
| **Payment days** | Days paid in the month: days employed − unpaid leave − absences |
| **Payout entry** | A Payroll Entry with Payout = Dashain Allowance or Leave Encashment |
| **Payroll Adjustment** | A form to add one-off amounts to a month |
| **Payroll Entry** | The run for one company and one BS month |
| **Payroll Inputs Log** | The record on a Payroll Entry of each run's totals |
| **Payroll Period** | The tax year for one company, for example 83/84 - NGI |
| **Payroll Section** | O/O, S/D or F/P, set on the Department |
| **PF** | Provident Fund. A retirement contribution inside the cap |
| **Replacement Leave** | A day of leave for holiday work, instead of overtime |
| **Retirement cap** | SSF + CIT + PF are tax-free only up to the lower of 5,00,000 and one third of assessable income |
| **S/D** | Sales and Distribution section (Marketing) |
| **Salary Revision** | A form to raise pay for many people and pay arrears |
| **Salary Structure** | The template of formula lines and usual rates for a company |
| **Salary Structure Assignment** | One person's pay from a date |
| **Settle Leave** | A tick on the salary entry to deduct leave taken beyond what was earned |
| **Slab** | The Income Tax Slab: the tax bands for a year |
| **SSF** | Social Security Fund: 31 % of Basic (20 % employer, 11 % employee) |
| **SSF Addition** | The employer's 20 %, shown as an earning |
| **SST** | Social Security Tax: the 1 % first band, waived for SSF members |
| **Tax openings** | Taxable Earnings Till Date and Tax Deducted Till Date, for months paid outside the system |
| **Women's rebate** | 10 % off the tax of a woman whose only income is salary |
