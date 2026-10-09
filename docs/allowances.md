# Allowances and pay: where everything lives

Code: `payroll/allowance.py`, `payroll/salary_slip.py`,
`payroll/attendance_allowance.py`, `payroll/payroll_entry.py`,
`payroll/onboarding.py`. Patches: `setup_allowance_kinds`,
`move_pay_to_salary_assignment`. Tests: `payroll/test_allowance.py`.

## One picture

| What | Where |
|---|---|
| The allowance and its **kind** | **Salary Component** → Is Allowance, Allowance Kind |
| The attendance rule (tea not on holidays; meal Time Offset 1.5 h, max 2) | the same Salary Component → Attendance-Driven Rule |
| **Rate per company** (tea 235 NGI / 265 NGN, meal 75, gas 1,690, edu 2,780, HRA 25 %) | Salary Component → Accounts row for the company → **Default Rate** |
| **Three accounts per company** | the same row: **Admin & Accounts (O/O)**, **Marketing (S/D)**, **Plant (F/P)** |
| What everyone on a structure shares | **Salary Structure**: Basic, SSF Addition, SSF, Income Tax, and tags for Tea, Meal, Overtime, Late Fine |
| **A person's pay** | **Salary Structure Assignment**: Base (= Basic), **Initial Basic**, **SSF Applicable**, and the **Allowances** table |
| Which account a person's pay posts to | **Department → Payroll Section** |

**Pay is not on the Employee.**
- An employee can be created with no salary figure.
- Whoever maintains employees does not see pay unless they can open assignments.
- A change in pay is a new dated assignment, and the old one stays as the record. Salary Revision works this way: a raise carries every allowance over, with the new dearness amount.

## The Allowances table (Assignment Allowance)

| Column | Meaning |
|---|---|
| Allowance | a Salary Component marked Is Allowance |
| Amount | **Fixed per Person**: this person's monthly figure (DA 7,380). **Company Rate / % / tea, meal**: blank = the company's rate; a figure = their own (NEW staff tea 40) |
| Active | untick to stop it (staff on no tea) |
| From Date | blank = with the assignment |
| Kind | shown from the component |

**Adding a new allowance:**
1. Create a Salary Component with Is Allowance, its kind, and a company row (accounts + rate).
2. Add rows on the assignments of the people who get it.

No new field and no new structure are needed.

## The eight kinds

| Kind | Examples | Reaches the slip |
|---|---|---|
| Fixed per Person | Dearness, Other, Fixed, Fuel, Maintenance, Transport | the assignment's rows; prorated by payment days; projected for income tax |
| Fixed Company Rate | Gas, Education, Mobile | the same |
| % of Initial Basic | HRA | the same, % × the assignment's Initial Basic |
| Per Day Present ⏱ | Tea & Conveyance | Prepare Payroll Inputs → Additional Salary |
| Per Meal ⏱ | Meal | the same (see **Meal** below) |
| Per Hour (Overtime) ⏱ | Overtime | the same (Overtime Sheets) |
| Entered by Hand | Load/Unload | Additional Salary typed by HR |
| Yearly | Dashain Bonus, Leave Encashment | their own Payroll Entry buttons (not built yet) |

**Who gets an attendance allowance (⏱):** the structure's tag row (tea for everyone on NGI/NGN Staff), or a row on the person's assignment. A row on the assignment always wins: its own rate, or Active unticked.

A structure refuses fixed allowances (they would be paid twice) and Yearly or hand-entered ones (they would be paid every month).

## Meal

A meal is part of **overtime the company asked for** (rule of 2026-10-09):

| Check, per attendance day | Meals |
|---|---|
| Employee not **OT Eligible** | 0 |
| Not on a **submitted Overtime Sheet** for that date with entitlement **Overtime** (stayed late on their own, replacement-leave staff) | 0 |
| Working day: punched in **≥ 1.5 h before** the shift start | +1 |
| Working day: punched out **≥ 1.5 h after** the shift end | +1 |
| **Holiday** worked on the Overtime Sheet | 2 |
| Any day | max **2** |

The month's meals × the rate (the person's own on their assignment, else the
company's: NGI 75, NGN 75, NGG 100) become the "Meal" line, posted by Prepare
Payroll Inputs. Settings on the Meal component: Time Offset (1.5), Max Meals per
Day (2), Only OT-Eligible Staff ✔. Code: `_meals_for_day` in
`payroll/attendance_allowance.py`.

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
- Unpaid absence: allowances are currently prorated like Basic. Confirm, or make them full.
- Dashain Bonus and Leave Encashment buttons.
- `docs/payroll-manual.html`, `docs/hr-payroll-handbook.html` and `docs/payroll-documentation.html` still describe the old setup.
