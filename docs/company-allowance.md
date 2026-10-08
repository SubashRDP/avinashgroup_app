# Company Allowance — each company's allowances, rates and accounts

Replaces `Allowance Category` (removed 2026-10-08).

## Why

Every company pays its own set of allowances (tea & conveyance and meal at NGI
and NGN, fuel and maintenance at NGK, gas, HRA, mobile recharge…), and the list
keeps growing. The chart keeps every staff cost three ways:

| Section | Accounts | NGI departments (Falgun 2082 sheet) |
|---|---|---|
| **Admin & Accounts** | O/O | General Management, Finance, Operations, Admin/HR, IT, Legal |
| **Marketing** | S/D | Sales/Marketing |
| **Plant** | F/P | Plant/Maintenance |

HRMS gives a Salary Component one account per company, so before this
everything posted to O/O, and only Salary Expenses was re-routed by a hard-coded
map.

## The pieces

| Where | What HR sets |
|---|---|
| **Company Allowance** (one record per company, named after it) | its **Allowances** table: one row per allowance with default rate, how it is calculated, the three accounts |
| **Employee → Allowances** table | **the tag**: only allowances listed here are paid to this person. Rate blank = company default; untick Eligible to stop one |
| **Department → Payroll Section** | Admin & Accounts / Marketing / Plant: decides the account |

Open the company's record (e.g. *Nepal Gas Udhyog Pvt. Ltd.*) to see and edit
all its allowances on one screen. The grid shows allowance, who gets it, rate,
attendance based, based on / calculation and the O/O account; a row's edit icon
opens the rest (meal hours, half day, holiday, S/D and F/P accounts).

### Allowance row fields (Company Allowance Item)

**No Salary Component screen needed.** HRMS still needs a Salary Component behind
every pay line (payslip row, Additional Salary, journal), but the row makes it:
type a new name in *Allowance* (existing ones are suggested) and save. The
component is created with the row's Type, an abbreviation from the initials,
Depends on Payment Days off for an attendance-based allowance and on for a
fixed one, and the company's Admin & Accounts account.

| Field | Meaning |
|---|---|
| Default Rate | per day / meal / hour (attendance based), per month (Fixed Monthly), or a % (% of Initial Basic) |
| Attendance Based | ticked → counted from attendance each month, posted by **Prepare Payroll Inputs** as Additional Salary |
| Based On | Status = Present (tea) · Meal Entitlement · Authorised Overtime · Worked on Holiday · Late Time … |
| Only OT-Eligible Staff | pays only employees with OT Eligible (policy 2.2: OT staff get OT + meals) |
| Rule fields | Half Day Counts, Pay on Holiday (tea); Time Offset 1.5 h, holiday hours 6 / 8, max 2 a day (meal); rate basis and multiplier (OT, late fine) |
| Calculation (not attendance based) | **Fixed Monthly** / **% of Initial Basic**: added to the salary slip from the employee's row · **From Salary Structure**: the structure computes it; the record only supplies accounts |
| Accounts | Admin & Accounts (O/O, required), Marketing (S/D), Plant (F/P). A blank S/D or F/P falls back to O/O |

The rule is per company, so NGN can use a different meal threshold from NGI.

### Example: NGI

| Allowance | Attendance | Based on / Calculation | Default | Accounts O/O · S/D · F/P |
|---|---|---|---|---|
| Tea & Conveyance | ✔ | Status = Present, half day = full, Do Not Pay on holiday | 235 | tea account ×3 (to be created by accounts) |
| Meal | ✔ | Meal Entitlement 1.5 h / 6 h / 8 h / max 2 | 75 | 547130 · 547131 · 547132 |
| Mobile Recharge | – | Fixed Monthly | e.g. 1,500 | … |
| HRA | – | % of Initial Basic | 25 | … |
| Basic | – | From Salary Structure | – | 547101 · 547102 · 547103 |

Nobody is paid an allowance unless tagged with it. Tea is for all staff (policy 1.4), so every employee is tagged with Tea: OLD staff with the rate blank (the company's 235). NEW staff on 40 a day: a Tea row with Rate 40. Staff on no tea: a Tea row with Eligible unticked.

## How a month runs

1. Attendance submitted.
2. Payroll Entry → **Prepare Payroll Inputs**: attendance-based allowances become submitted Additional Salary, at the employee's rate or the company default.
3. **Create Salary Slips**: Fixed Monthly and % of Initial Basic rows are added to each slip (`payroll/salary_slip.py`, a Salary Slip validate hook). They are prorated by payment days when the component has Depends on Payment Days, and HRMS projects them over the year for income tax: they are not Additional Salary.
4. **Submit**: the accrual journal posts each employee's amounts to their section's account (`payroll/payroll_entry.py`). An employee whose Department has no Payroll Section stops the run with their names.

## Checks the record makes

- Attendance-based: the Salary Component must NOT have Depends on Payment Days (the count already leaves out absences).
- Fixed Monthly / % of Initial Basic: an Earning, and not also in an active salary structure of the company (it would be paid twice).
- Accounts must be ledgers of the record's own company.
- A component is attendance based for every company or none (the attendance reports read it off the component).
- Saving writes the O/O account into the Salary Component's Accounts row for that company, so HRMS's own checks pass.
- Employee save: every row must be an allowance of the employee's company, listed once.

## Migration (`patches/setup_company_allowance.py`)

- Departments seeded by name: Plant… → Plant, Sales…/Marketing… → Marketing, the rest Admin & Accounts. On avinas1: 3 Plant, 12 Marketing, 64 Admin & Accounts. **Check "Marketing & Admin - NGG"** (set to Marketing).
- Every Salary Component with an account for a company → a row on that company's Company Allowance. The S/D and F/P accounts are the chart's siblings of the O/O one. Attendance components carry their rule across; the rest become From Salary Structure.
- Allowance Category rates → rows on each member's Allowances table (rate 0 → unticked); then the category doctypes and `Employee.custom_allowance_category` are removed.
- Whatever the old engine paid without a tag (overtime, late fine, daily wage; tea or meal where no category decided it, or where the component had a default rate) is tagged on every active employee of the company, so nobody stops being paid. An existing row is kept.
- The rule fields on Salary Component are hidden; Is Attendance Driven becomes read-only (set from Company Allowance).

## Not done yet

- Today's structure-formula allowances (DA, Other, Fuel, Gas, Edu, HRA) are still computed by the structure from Employee fields. Moving them onto employee rows needs a parity run against the Falgun sheets. New allowances use the new path.
- A structure **preview** does not show Fixed Monthly rows (it does not run validate).
- `docs/payroll-manual.html`, `docs/hr-payroll-handbook.html` and `docs/payroll-documentation.html` still describe Allowance Category.

## Tests

`payroll/test_company_allowance.py` (14 tests): who is paid, rates, OT-only, the
meal rule, slip rows with proration and tax projection, section accounts, and
the record's checks. Run with the runner in docs/shift-rotation.md ("Tests").
