# Allowances and pay: where everything lives

Code: `payroll/allowance.py`, `payroll/salary_slip.py`,
`payroll/attendance_allowance.py`, `payroll/payroll_entry.py`,
`payroll/onboarding.py`, Salary Revision. Patches: `setup_allowance_kinds`,
`move_pay_to_salary_assignment`, `allowance_rate_list`. Tests:
`payroll/test_allowance.py`.

Code map: [salary-code-map.md](salary-code-map.md) — every function from punch to journal, with links to the line.

## One picture (agreed with the user 2026-10-12)

| Screen | Holds | Example |
|---|---|---|
| **Salary Component** | What the allowance is and **how it is counted** (Is Allowance, Allowance Kind, the attendance rule), and per company the **three accounts** O/O, S/D, F/P. **No rate.** | Tea is paid per day present, not on holidays |
| **Salary Structure** | The formula lines (Basic, SSF Addition, SSF, Income Tax, Late Fine) and **Allowance Rates**: the usual rate of each allowance for the people on it. A template: it pays nobody an allowance by itself | NGI Staff 83/84: Tea 235, Meal 75, Gas 1,690, HRA 25 % |
| **Salary Structure Assignment** | A person's pay: Base (= Basic), Initial Basic, SSF Applicable and the **Allowances** they get, each with **their Rate**. Picking the structure on a draft replaces the table with the structure's Allowance Rates; HR removes what the person does not get. Picking an allowance fills the Rate from the structure; HR changes it for this person. **No row, not paid.** Payroll reads only this | Ram: Tea 40, Gas 1,690, Dearness 7,380 |
| **Salary Revision** | Every change in pay, from the 1st of a BS month: a raise in Basic / Dearness, and **Raise Rate / Add / Stop / Change Rate** for an allowance | Tea 235 → 260 from 1 Kartik for everyone on NGI Staff at 235 |
| **Department → Payroll Section** | Which of the three accounts a person's pay posts to | Sales/ Marketing → S/D |

Why the structure does not decide who gets what: in October 2026 the 195
assigned people had **27 different combinations** of allowances (some gas, some
rent, some neither). Who gets what is per person; the structure keeps the usual
rate and is the anchor for raising it.

**Pay is not on the Employee.**
- An employee can be created with no salary figure.
- Whoever maintains employees does not see pay unless they can open assignments.
- A change in pay is a new dated assignment, and the old one stays as the record.

## The Allowances table (Assignment Allowance)

| Column | Meaning |
|---|---|
| Allowance | a Salary Component marked Is Allowance (not Entered by Hand / Yearly) |
| Rate | what this person is paid, in the Unit. Filled from the structure's Allowance Rate when picked; a row saved at 0 is filled from it too; still 0 is refused |
| Unit | from the kind: per month, % of initial basic, per day present, per meal; "from basic × 1.5" for overtime, whose rate is never typed |
| From Date | blank = with the assignment |

One meaning per column: no "blank = company rate", no Active tick. To stop an
allowance, remove the row (by Salary Revision → Stop, for a submitted one).

**Adding a new allowance:**
1. A Salary Component with Is Allowance, its kind, and a company row (accounts).
2. Its usual rate in the Allowance Rates of the structures that have one.
3. Rows on the people who get it — or a Salary Revision with **Add**.

No new field and no new structure are needed.

## The kinds (how the allowance is counted)

| Kind | Examples | Reaches the slip |
|---|---|---|
| Monthly | Dearness, Other, Fixed, Fuel, Maintenance, Transport, Gas, Education | the assignment's rows; prorated by payment days; projected for income tax |
| % of Initial Basic | HRA | the same, Rate % × the assignment's Initial Basic |
| Per Day Present ⏱ | Tea & Conveyance | Prepare Payroll Inputs → Additional Salary (days × Rate) |
| Per Meal ⏱ | Meal | the same (see **Meal** below) |
| Per Overtime Hour ⏱ | Overtime | the same (Overtime Sheets × basic per hour × 1.5) |
| Entered by Hand | Load/Unload | Additional Salary typed by HR |
| Yearly | Dashain Allowance, Leave Encashment | Dashain: Payroll Entry → **Dashain Allowance** (draft Payroll Adjustment, basic × service factor ≤ basic). Leave: Leave Encashment list → **Encash Year-End Balances** (Ashadh) |

"Fixed per Person" and "Fixed Company Rate" were one kind with the rate kept in
two places; both are **Monthly** since 2026-10-12.

A structure refuses an allowance in Earnings / Deductions (it would be paid to
everyone on it, whatever their assignment says). Its Allowance Rates refuse
Yearly and hand-entered ones. A submitted structure's existing rate changes only
through a Salary Revision (`guard_structure_rates`): editing it in place would
leave the people at the old rate behind, and the next raise would find nobody at
the structure's rate.

## Salary Revision: allowance changes

| Change | Reaches | Does |
|---|---|---|
| Raise Rate | everyone on the chosen structure **at its listed rate** | their row → New Rate; the structure's rate → New Rate. Own rates (new staff's tea 40) untouched and named by Get Employees |
| Add | listed employees without it | a row at New Rate, or blank = their structure's rate |
| Stop | listed employees with it | removes the row |
| Change Rate | listed employees with it | their row → New Rate |

One new assignment per person carries all of it. Arrears for months already
paid: monthly kinds by each month's payment days / working days; tea and meal
by the days or meals each month counted (`attendance_qty_paid`, the engine's
own rule). Cancel restores the old assignments and the structure's rate (only if
it is still the revision's rate).

## Meal

A meal is part of **overtime the company asked for** (rule of 2026-10-09):

| Check, per attendance day | Meals |
|---|---|
| Employee not ticked **Overtime Eligible** | 0 |
| Not on a **submitted Overtime Sheet** for that date with entitlement **Overtime** (stayed late on their own, replacement-leave staff) | 0 |
| Working day: punched in **≥ 1.5 h before** the shift start | +1 |
| Working day: punched out **≥ 1.5 h after** the shift end | +1 |
| **Holiday** worked on the Overtime Sheet | 2 |
| Any day | max **2** |

The month's meals × the Rate on the person's Meal row (usually NGI 75, NGN 75,
NGG 100) become the "Meal" line, posted by Prepare Payroll Inputs. Settings on
the Meal component: Time Offset (1.5), Max Meals per Day (2), Only OT-Eligible
Staff ✔. Code: `_meals_for_day` in `payroll/attendance_allowance.py`.

## The 2026-10-12 migration (`allowance_rate_list`) on avinas1

| Step | Count |
|---|---|
| Kinds renamed (Fixed per Person / Fixed Company Rate → Monthly, Per Hour (Overtime) → Per Overtime Hour) | 9 |
| Old Amount copied to Rate | 343 |
| Structure Allowance Rates listed (from the components' old Default Rates and what people carry) | 27 |
| Rows added for what a structure tag paid (tea 89, meal 177, overtime 195) | 461 |
| Company rates written onto rows that relied on them (gas 77, education 74, HRA 74) | 225 |
| "Not paid" (Active unticked) rows removed | 31 |

Proven unchanged: every one of the 195 assigned people has the same monthly
allowance amounts (total 2,422,537.33) and the same tea / meal / overtime rate
(704 entries) before and after; the Falgun sheet check gives the same result
for the same people (NGI 71/79, NGN 26/43, NGG 27/27, NGK 18/18).

## Daily breakdown on the salary slip

Every slip carries a **Daily Breakdown** table (section on the Salary Slip, and a
second page on the "Salary Slip BS" print, so it is emailed too). One row per day
of the BS month, then month-end rows, ending at the net pay:

| Column | Day row | Month-end row |
|---|---|---|
| Miti, Day | 03 Shrawan, Sun | – |
| Attendance | "Present 07:20–18:45", "Absent", "Half Day", "Leave: Casual", "Holiday: …" | the line: SSF, Income Tax, Advance, Rounding |
| Fixed | the slip's daily rate (fixed earnings ÷ payment days) × that day's paid share (absent 0, half day ½, holiday 1) | – |
| Earned / Deducted | tea, meal, overtime / late fine that day | one-off earnings / SSF, tax, advances |
| Detail | "Tea & Conveyance 235 · Meal 2 × 75 = 150 · Overtime 1.5 h = 412.50 · Late Fine 30 min −60" | – |
| Balance | running | the last = **net pay** |

Built on every save (frozen at submit) by `payroll/daily_breakdown.py`, from the
same rules that posted the amounts, so it always adds up. If attendance changed
after the slip was made, the gap shows as an **Adjustment** line instead of
being hidden in the days; re-save the slip to bring them back in step.

## A month's run

1. Attendance submitted.
2. New Payroll Entry → **Company**, then click the month on the **month calendar** (a fiscal year's 12 BS months with their dates; paid / draft / running marked; asks before a second entry for a paid month) → Save. That is all HR types: the dates, the posting date (the month's last day), frequency, currency, payable account, cost centre and the employee list fill themselves (`payroll/payroll_month.py`). A new entry starts on the last finished month. Month borders come from **Nepal BS Period** when it has the month, else the Nepali calendar (`hr/bs_calendar.py`); the slips, the Monthly Attendance BS report and the deposit report read the same calendar.
3. **Prepare Payroll Inputs** (tea, meal, OT, late fine, advances). It refreshes the entry's draft slips.
4. Submit → slips → **Submit Salary Slips** → the journal posts each person to their section's account.

## The salary sheet (Avinas Salary Statement)

The client's Excel salary sheet, printed from the slips: Company, Fiscal Year +
BS Month (as on the Payroll Entry), optionally one Payroll Entry.

- **Columns, in the sheet's order:** Attendance, OT Hr., Meal Qty., Late Hr., Initial Basic, Basic Salary, OT Rate, Late Deduction Rate, Unpaid Leave, Deduction, Net Basic, SSF Addition, HRA … Edu, Total Allowance, Regular Salary, Tea, OT, Meal, Gross, SSF, Tax, Late Fine, advances, Total Deduction, Net Payable, Last Month Net. A component the sheet does not name gets its own column, so the columns always add up to the slip's gross and net.
- **Rows:** grouped O/O, S/D, F/P (Department → Payroll Section) with a subtotal each, then the sections' summary and the grand total, as on the sheet.
- **Quantities** (OT hours, meals, late hours, rates) come from Additional Salary → Quantity / Rate, written by Prepare Payroll Inputs.
- **Check against the books:** the summary compares each section's gross with the payroll journal's expense debits for that section, and net pay with the credit to the payable account. Green "Matches Journal", or a red card per difference. A difference means a component's section accounts are wrong (2026-10-09: NGN Education Allowance's S/D account pointed at O/O, 11,250 for Bhadra).

## Onboarding from the Falgun 2082 sheets (2026-10-08, avinas1)

| Company | Structure | Assignments | Slip = sheet |
|---|---|---|---|
| NGI | NGI Staff 83/84 | 87 | 83 |
| NGN | NGN Staff 83/84 | 63 | 61 |
| NGG | NGG Staff 83/84 | 27 | 27 |
| NGK | NGK Staff 83/84 | 19 | 19 |

**Differ, for HR to check:**
- NGI: Shreechandra Bhatta (CEO, special pay), Kishor Lal Shrestha, Raju Maharjan, Abhishek Khadka.
- NGN: Mahesh Bahadur Madai, Shiva Kumar Kushwaha, Sudip Mahato.

**Not found as employees:**
- NGN: Shreeram Sah, Dinesh Chaudhary, Hari Sharan Mahato, Dipak Chaudhary
- NGG: Subash Chaudhary
- NGK: Arun Kumar Tharu, Pal Bahadur Lohar

**69 active employees have no assignment.** They are not on the sheets: placeholders such as "Staff Advance", cash labour, likely duplicates across companies, and new joiners. They need a Basic from HR.

## Settings this relies on (set on avinas1 on 2026-10-08)

- Nepal HRMS Settings → **Process payroll in Nepali month** ON. Every company's country must be **Nepal** (NGI, NGG and NGN were "India").
- Payroll Settings → **Include holidays in total working days** ON. Holidays are paid; with it off a full month paid 26/31.
- NGK departments created: Account, Plant, Sales and Marketing, Driver, Vehicle Helper. Driver and Vehicle Helper are in the Marketing (S/D) section.

## Not in payroll

- **Daily-wage labour** is paid in cash day to day. The Daily Wage component is disabled.
- **Grade Amount** and **Arrear** are disabled: grade is part of Basic (NGG, NGK), and back pay is Salary Arrears (Salary Revision).

## Still open

- Accounts: no tea account exists yet (O/O, S/D, F/P), and other components have no accounts per company.
- Falgun parity on avinas1 has dropped since 2026-10-08 (NGI 83 → 71 matching, NGN 61 → 26) — before the 2026-10-12 change, which leaves it exactly as it found it. Not yet investigated.
- Unpaid absence: allowances are currently prorated like Basic. Confirm, or make them full.
- `docs/payroll-manual.html`, `docs/hr-payroll-handbook.html` and `docs/payroll-documentation.html` still describe the old setup.
