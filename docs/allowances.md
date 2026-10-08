# Allowances: kinds, three accounts, and who gets them

Code: `payroll/allowance.py`, `payroll/attendance_allowance.py`,
`payroll/payroll_entry.py`, patch `setup_allowance_kinds`. Tests:
`payroll/test_allowance.py`. Replaces Allowance Category (and the short-lived
Company Allowance doctype, never released).

## The idea in one table

| What | Where HR sets it |
|---|---|
| That a pay line is an allowance, and its **kind** | Salary Component → **Is Allowance**, **Allowance Kind** |
| The attendance rule (tea not on holidays, meal 1.5 h / 6 h / 8 h / max 2) | Salary Component → Attendance-Driven Rule (one rule for all companies) |
| **Three accounts** per company | Salary Component → Accounts table: **Admin & Accounts (O/O)**, **Marketing (S/D)**, **Plant (F/P)** |
| **Rate** per company (tea 235 at NGI, 265 at NGN) | the same Accounts row → **Default Rate** |
| **Who gets it** | the employee's **Salary Structure**: a row for the allowance tags everyone on that structure |
| Exceptions (NEW staff tea at 40; staff on no tea) | Employee → **Allowance Exceptions**: own rate, or Eligible unticked |
| Which account an employee's pay posts to | Department → **Payroll Section** (Admin & Accounts / Marketing / Plant) |

## The eight kinds (from the four companies' Falgun 2082 sheets)

| Kind | Examples | Paid | Counted over | How it reaches the slip |
|---|---|---|---|---|
| Fixed per Person | Dearness, Other, Fixed, Fuel, Maintenance, Transport | monthly | the BS month | structure row reading the employee's amount; HRMS prorates by payment days |
| Fixed Company Rate | Gas (NGI 1,690), Education (NGI 2,780), Mobile | monthly | the BS month | structure row with the amount |
| % of Initial Basic | HRA (NGI 25%, NGN 27%) | monthly | the BS month | structure row formula |
| Per Day Present ⏱ | Tea & Conveyance | monthly | attendance in the BS month | **Prepare Payroll Inputs** → Additional Salary |
| Per Meal ⏱ | Meal | monthly | attendance in the BS month | Prepare Payroll Inputs |
| Per Hour (Overtime) ⏱ | Overtime (E.OT, H.OT, M.OT) | monthly | Overtime Sheets in the BS month | Prepare Payroll Inputs |
| Entered by Hand | Load/Unload | months with work | that month | Additional Salary typed by HR |
| Yearly | Dashain Bonus, Leave Encashment | once a year | fiscal year | their own buttons (not built yet) |

An attendance kind (⏱) sets the component itself: Is Attendance Driven, the
matching condition, Depends on Payment Days **off** (the count already leaves
out absences) and Remove if Zero Valued (its structure row is only a tag).
**Attendance Month** can be set to Previous Month if attendance ever closes a
month behind; the default is the salary's own month, as the Falgun sheet does.
**Only OT-Eligible Staff** limits overtime (and meals, if HR wants) to employees
with OT Eligible ticked.

## Tags in the structure

An attendance allowance's row in a Salary Structure is a tag only: saving the
structure blanks its amount and formula, and the slip shows nothing for it until
Prepare Payroll Inputs posts the month's figure. A Yearly or Entered-by-Hand
allowance is refused in a structure (it would be paid every month).

Tagged = in the employee's structure, or a ticked row in their Allowance
Exceptions (older sites tag that way). An unticked row always wins.

## A month's run

1. Attendance submitted.
2. Payroll Entry → **Prepare Payroll Inputs** (best before Submit). Tagged
   employees' tea, meals, overtime and fines become submitted Additional
   Salary, at their own rate or the company's Default Rate. If the entry was
   already submitted, its draft slips are recalculated so they show it.
3. Submit the Payroll Entry (HRMS makes the slips), review, **Submit Salary
   Slips**.
4. The accrual journal posts each employee's amounts to their section's
   account. A blank S/D or F/P account falls back to the O/O one. An employee
   whose Department has no Payroll Section stops the run with their names.

## Setup gaps found on 2026-10-08 (must fix before a real run)

- **Process payroll in Nepali month** (Nepal HRMS Settings) is OFF on avinas1
  and on demo. Slips are then cut on AD months (17–31 July), and anything dated
  at the BS month end misses them.
- **Company country is "India"** for NGI, NGG and NGN on avinas1. With
  "Restrict to Nepal companies" on, BS payroll stays off even when enabled.
  (Demo has Nepal.)
- **Include holidays in total working days** is off in Payroll Settings, but the
  BS slip divides by the BS month's days (31). Saturdays are then unpaid: a
  full month showed 26 / 31 payment days (Basic 25,161 instead of 30,000).
- avinas1: Income Tax has no account, and 347301 Salary Payable is typed
  Liability (HRMS refuses an account type on the payable account). Demo
  differs.

## Migration (`patches/setup_allowance_kinds.py`)

- Fields as above; the existing account column is relabelled Admin & Accounts (O/O).
- Departments seeded by name: Plant… → Plant, Sales…/Marketing… → Marketing,
  the rest Admin & Accounts. On avinas1: 3 Plant, 12 Marketing, 64 Admin &
  Accounts. **Check "Marketing & Admin - NGG"** (set to Marketing).
- Every Accounts row gets the S/D and F/P siblings of its account where the
  chart has them, and the component's old default rate as the company's.
- Known components are marked by name or condition (avinas1: 8). Overtime-type
  conditions become Only OT-Eligible Staff.
- Allowance Category rates become exception rows; the category doctypes go.
- Whatever the old engine paid untagged (overtime, late fine, and tea or meal
  where no category decided it) is tagged on every active employee
  of the company, so nobody stops being paid. Existing rows are kept.

## Not in payroll

- **Daily-wage labour** (NGK's Wages tab, 754 a day; NGN's and NGG's helpers) is
  paid in cash day to day, outside payroll (decided 2026-10-08). The Daily Wage
  component is disabled and onboarding no longer imports the Wages tab.
- **Grade Amount** and **Arrear** are disabled: grade is part of Basic at NGG and
  NGK; back pay is **Salary Arrears**, posted by Salary Revision.

## Not done yet

- Dashain Bonus and Leave Encashment buttons on the Payroll Entry.
- NGI pilot: accounts for tea (O/O, S/D, F/P), structure with tags, parity run
  against the Falgun sheet; then NGN, NGG, NGK.
- `docs/payroll-manual.html`, `docs/hr-payroll-handbook.html` and
  `docs/payroll-documentation.html` still describe Allowance Category.
