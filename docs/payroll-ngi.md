# NGI payroll — components, structure, and how it matches the sheet

Built from **NGI.xlsx → "Falgun salary"** (92 employees, gross 3,731,812.16, net
3,176,600.67). The sheet is the specification; ERPNext has to reproduce it.

## Where each number lives

| Sheet column | In ERPNext |
|---|---|
| Department, Cost Center, Designation | the Employee's own fields (imported — 265 of 295 had no designation) |
| Initial Basic | `Employee.custom_initial_basic` — HRA is 25% of **this**, not of Basic |
| Basic Salary | **base** on the Salary Structure Assignment |
| Dearness, Other Allowance | `custom_dearness_allowance`, `custom_other_allowance` — they differ per person and an assignment has nowhere to put them |
| HRA / Gas / Edu flags | three ticks on the Employee (48 of 92 each) |
| SSF applies? | a tick — 8 people are outside the scheme |
| Tea category OLD / NEW / NO | **Allowance Category** (`NGI OLD` 235/day, `NGI NEW` 40, `NGI NO` 0) |

## The structure — `NGI Staff 83/84`

| Component | Formula | Prorated |
|---|---|---|
| Basic | `base` | yes |
| Dearness Allowance | `custom_dearness_allowance` | yes |
| Other Allowance | `custom_other_allowance` | yes |
| House Rent Allowance | `custom_initial_basic * 0.25 if custom_hra_eligible else 0` | yes |
| Gas Allowance | `1690 if custom_gas_allowance else 0` | yes |
| Education Allowance | `2780 if custom_education_allowance else 0` | yes |
| SSF Addition | `B * 0.20 if custom_ssf_applicable else 0` | **no** |
| SSF (deduction) | `B * 0.31 if custom_ssf_applicable else 0` | **no** |

SSF and its employer half are **not** prorated: their formulas read Basic, which
is prorated already, and HRMS refuses the pair so the amount cannot be cut twice
for the same absence.

## Not in the structure, by design

Tea & Conveyance, Meal, Overtime and Late Fine are **attendance-driven**. The
allowance engine posts them as Additional Salary from attendance and the approved
Overtime Sheet, at rates that come from the employee's Allowance Category. SST,
income tax and advances are typed per month as Additional Salary — in Falgun only
2 people paid tax and 3 had advances.

## Parity with the sheet (2026-09-21)

Slips for Bhadra 2083 (31 days, all paid) reproduce the sheet **to the paisa** on
every structure component:

| | Sajjan Lama | Bikash Sharma | Bishwo Nath Poudel |
|---|---|---|---|
| Basic | 13,266.25 | 58,224.83 | 14,592.83 |
| HRA | 3,042.50 | 0 | 3,167.50 |
| SSF Addition | 2,653.25 | 11,644.97 | 2,918.57 |
| SSF | 4,112.54 | 18,049.70 | 4,523.78 |
| **Regular salary** | **30,812.00** | **126,254.80** | **32,528.90** |

## Company-wide parity (2026-09-21)

Slips built for all 87 assigned employees against the sheet's Regular Salary:

| | Result |
|---|---|
| Match to the paisa | **84 of 87** |
| Differ | 3, all of them rows the sheet types by hand |

The three: **Raju Maharjan** (the sheet pays 6/30 of the month), **Kishor Lal
Shrestha** (the sheet pays nothing), and **Shreechandra Bhatta**, the CEO row that
is typed throughout and contradicts itself (Basic 34,270.83, Net Basic 137,700).
Each is a data decision for HR, not a formula.

**Fuel Allowance** is paid to one employee (6,123) as a **recurring Additional
Salary**, not a structure row: it is one person's fixed monthly amount, and the
structure cannot be edited once assignments point at it. That took Abhishek
Khadka from 23,416.80 to the sheet's 29,539.80 exactly.

## First full run — Bhadra 2083 (2026-09-21)

Payroll Entry `NGI-PAYR-83/84-00001`, 87 employees, 87 slips saved.

| Component | Slips | Sheet (Falgun) |
|---|---|---|
| Basic | 1,518,037.57 | 1,518,037.54 |
| Dearness | 829,086.00 | 829,086.00 |
| Tea & Conveyance | 276,555 | 273,980 |
| SSF | 451,003.44 | 478,537.73 |
| **Gross** | **3,405,477.03** | 3,731,812.16 |

The gap is entirely explained: **OT (198,871) and meals (52,275) are not built
yet**, and the sheet's three hand-typed rows account for the remaining 77,764.

Two things this run taught:

* **Attendance allowances must be submitted.** The engine creates Additional
  Salary as drafts; a draft is invisible to the slip, so tea only appeared after
  submitting the 80 drafts and rebuilding.
* **Meal cannot be "one per present day."** Configured that way it paid 132,525
  against the sheet's 52,275. It is now its own condition, **Meal Entitlement**:
  one meal for arriving 1.5 h early, one for staying 1.5 h late, never more than
  two in a day; on a holiday one at 6 hours worked and two at 8. Every case in
  the policy is covered by a check (1.4 h early earns nothing, 1.5 h earns one,
  early + late earns two, holiday 5/6/8/11 h earns 0/1/2/2, absent earns nothing,
  a half day still earns).

Both fixes went into the engine, so the run needs no manual step: allowances are
created submitted and appear on the slips, and a re-run cancels and replaces what
it made last time while leaving anything HR typed alone.

## Pay follows attendance (2026-09-21)

Payroll Settings was on **Leave**, so slips only lost pay for an approved leave
application and attendance was never read. The 2-hours-late half day and plain
absences therefore cost nothing: on a 9 AM - 6 PM shift, walking in at 11:30 every
day was paid in full.

Switched to **Attendance** (patch `setup_payroll_based_on_attendance`). For Bhadra
that took gross from 3,408,027.03 to **2,821,371.93** and payment days from "31
for everyone" to a spread of 16.5 to 31. One employee with 22 half days and 2
absences is now paid 18 days of 31 — and still earns the full 40 a day of tea for
every day he turned up.

Approved leave is unaffected: HRMS marks those days On Leave, not Absent.

The trade: attendance is now the source of truth for pay, so a missing punch is a
pay cut until it is repaired. That is what the hourly self-heal job and Attendance
Fix exist for.

## Known gaps

* 5 of the 92 have no Basic in the sheet, so they have no assignment.
* Cost centres did not import — `Office`, `Sales & Distribution` and `Filling
  Plant` do not exist as Cost Center records.
* The sheet's own row 5 (the Group CEO) is typed by hand and internally
  inconsistent (Basic 34,270.83, Net Basic 137,700).
* NGG, NGN, NGK still need their own structures: NGN pays HRA at 27% and tea at
  265, NGG and NGK run PF-style columns and keep whole groups (vehicle helpers,
  daily labour) on separate sheets.

## The month's one-off amounts — Payroll Adjustment

SST, income tax, an advance being recovered, a festival bonus: each is one
person's amount for one month, and ERPNext keeps them as Additional Salary, one
document each. Fine for two people; miserable for twenty, which is why the sheet
types them as columns.

**Payroll Adjustment** is that column: company, payroll date (inside the BS month
being paid), and a row per employee and component. Submitting creates and submits
each Additional Salary; cancelling takes them all back, so a month is undone in
one place. Attendance-driven components are kept out of the picker — the
allowance engine already posts those.

Verified on nepalgas with NGI's Falgun one-offs replayed into Bhadra: income tax
7,500 and 46,701, advance 6,500, extra SSF 5,000 twice. They reached the slips
(Bikash Sharma: Income Tax 7,500 and Salary Advance 6,500 as deductions) and
cancelling the adjustment left no live rows behind.

Still undecided, and the client's call: who pays the 1% SST, whether income tax
stays typed or is computed from the FY 83/84 slab, whether advances should instead
be tracked as Employee Advance with a balance, and what the Dashain bonus is based
on.

## Income tax and SST (2026-09-21)

Nothing taxed anyone before this date. The site had no Payroll Period, no Income
Tax Slab and no component flagged `variable_based_on_taxable_salary`, so every
slip deducted SSF and stopped.

**SST is not a second deduction.** It is the first band of the tax table — the
1% social security tax — and Nepal waives it for anyone contributing to the
Social Security Fund. That is exactly what the Falgun sheet shows: 1% of gross
on the four NGI staff outside the fund, zero on the 83 inside it. So the slab's
first row carries the condition `not custom_ssf_applicable`; HRMS skips a slab
row whose condition is false, and the employee's own fields are in scope there.

The table is the Finance Act 2083 one, effective Shrawan 1, 2083. One schedule
for everybody now — the separate couple column is gone:

| Annual taxable income | Rate |
|---|---|
| up to 10,00,000 | 1% (skipped for SSF members) |
| 10,00,001 – 15,00,000 | 10% |
| 15,00,001 – 25,00,000 | 20% |
| 25,00,001 – 40,00,000 | 27% |
| above 40,00,000 | 29% |

Taxable income is earnings less the SSF contribution. The exemption is copied
onto each salary structure row the day that row is written and read from the
row, not the component, at slip time — so ticking `Exempted from Income Tax` on
the SSF component does nothing to a structure built earlier. The patch syncs the
existing rows; without it Bhatta's projection stood at 1,400,000 instead of
1,337,799.

Next year's Finance Act is a data edit: a new Income Tax Slab with a later
`effective_from`, and the assignments pointed at it.

### Changing it by hand

The computed figure is a projection of a year that has not finished — it assumes
the remaining months look like this one. Accounts often knows better. Every slip
carries:

- **Computed Income Tax** — what the slab worked out, kept for comparison
- **Override Income Tax** + **Income Tax (manual)** — tick and type, and that is
  deducted instead. Zero is a valid override, meaning "nothing this month".

Bhadra 2083 on nepalgas: 87 slips, 6 taxed — the two above ten lakh, and the
four at 1%.

## Dashain bonus

The festival allowance is compulsory under the Labour Act: one month's pay for a
full year served, that fraction of a month for anyone who joined part-way
through. `Dashain Bonus` holds the year's decision for one company.

- **Bonus Given This Year** — untick and the year is recorded with its reason,
  which is the honest answer when a company skips it.
- **One Month Means** — Basic, Basic + Dearness Allowance, or last slip's gross.
- **Get Employees** counts each person's months of service to the payout date,
  caps them at twelve, and prorates. The months are shown on the row so the
  arithmetic can be checked; every amount stays editable.
- Submitting writes one submitted Additional Salary per line, dated in the
  payout month, so the bonus rides that month's slip and is taxed with it.
  Cancelling takes them all back.
- Staff with no salary structure assigned are left out rather than listed at
  zero, and named in a message.

NGI at Bhadra end: 87 of 107 staff, 15,18,037.57 on basic, 23,47,123.57 on basic
with the dearness allowance.

## Mid-year pay rises — Salary Revision

A salary is a dated fact. Never edit someone's basic in place: assign the
structure again from the date the new pay starts, and the old assignment stays
as the record of what was paid before, so old slips keep reconciling with old
journal entries. `Salary Revision` does that for a company at a time — one hike
percent for everyone, any row typed over as a percent or an amount, one new
Salary Structure Assignment per person on submit.

Two things to know:

- **A slip is paid at one rate for its whole month.** An effective date in the
  middle of a BS month cannot half-pay that month — it takes effect the month
  after. Put the effective date on the first day of a BS month.
- **Increments are agreed late.** When the rise runs from Shrawan but the
  meeting was in Mangsir, the months already paid at the old rate are arrears:
  tick **Pay Arrears** and name the month they ride on, and the difference goes
  out as a `Salary Arrears` earning. Submitted slips are never edited.

The dearness allowance is the one part of NGI's pay that is not dated — the
structure reads it off the Employee — so the old value is written onto the row
before it is overwritten. That makes the revision document its history, and lets
a cancel put it back.

## Attendance reports measure against the day's shift (2026-09-21)

Monthly Attendance BS (Detail and Summary), Yearly Leave Details BS and Work On
Holiday BS now reproduce the Chaitra 2082 attendance workbook's rules. One module,
`hr/shift_day.py`, decides what counts, and overtime pay uses the same code, so
the report and the slip cannot disagree about a day.

| Column | Rule |
|---|---|
| Shift | The shift rostered on **that date** — a mid-month shift change shows on the day it happened |
| Late | Minutes after that shift starts, on a working day worked in full. No grace: 09:08 on the 9 AM shift is 8 |
| Before ofc. Time | Minutes before the shift ends, same days |
| Late Time (summary) | Late + Before ofc. Time, as the sheet's card adds them |
| O.T. | Hours outside the shift; every hour on a holiday; nearest half hour (7:53 → 8, 7:34 → 7.5); OT-eligible staff only |
| Leave Remaining | `min(Entitled, Entitled − Taken + Holidays Worked)` — holiday work credited back only for staff **not** paid OT |

Before this, Late read **0 for everyone** (it waited for an HRMS flag nothing sets),
O.T. was every minute anyone stayed late, and "before office" counted on absent days.

**Data finding:** 63 of 80 NGI staff had the opposite OT category from the
workbook's Work On Holiday tab — nearly a clean inversion. Fixed on nepalgas from
the client's sheet; **check the same on ng-group before the first live run.**

## What the monthly run pays, and how

Press **Prepare Payroll Inputs** on the Payroll Entry. It posts, per person:

| Line | Counted by | Priced at |
|---|---|---|
| Tea & Conveyance | days present (a half day earns the full day) | Allowance Category rate (OLD/NEW/NO) |
| Meal | 1.5 h early / 1.5 h late, max 2; holiday 6 h → 1, 8 h → 2 | Allowance Category rate |
| Overtime | hours on a submitted **Overtime Sheet**, backed by punches (policy 5.1) | Basic ÷ 30 ÷ 8 × 1.5 |
| Late Fine | Late Time minutes; not on a half day; not for **Late Fine Exempt** staff | Basic ÷ 30 ÷ 8 per hour |
| Daily Wage | days present, half day = half | the day's rate (assignment base) |
| Salary Advance | min(instalment, outstanding) per open Employee Advance | — |

Every earning is taxed **in the month it is paid** (without this a labourer's
7,068.75 month drew 6 of tax instead of 70.69).

**Advances** are a balance now: record the Employee Advance when the cash is
handed over (monthly instalment, start month), pay it with Make Bank Entry, and
each run takes the instalment; the advance moves to *Returned* when cleared.
HRMS requires the staff advance account to be **Receivable** — NGI's 148003 was
changed on nepalgas only; four companies have it typed *Payable*. Accountant's call.

## The other companies — onboarding from their own sheets

`payroll/onboarding.py`: `onboard(key, path)` builds the company's structure and
imports its sheet (NGN, NGG, NGK; NGI's profile is there to replay).

| Company | Model | Parity (full month vs sheet, per component) |
|---|---|---|
| NGN | initial-basic (HRA 27%, gas 1,690.27, edu 1,250, tea 265/40) | 66/66 |
| NGG | grade scale (basic + increments + grade) | 27/28 — the one is a mid-month joiner |
| NGK | grade scale + maintenance; labour at 754/day | 19/19 staff, 6 labourers |

Not on the site, so not imported: NGN — Dipak Chaudhary; NGK — Arun Kumar Tharu,
Pal Bahadur Lohar (joined Magh/Falgun), labourer Kis Mohan Tharu. Five NGN rows
have no basic on the sheet and were left unassigned. NGG's vehicle-helper sheet
has broken `#REF!` formulas and was not used. GLMI, GEPL and SGU sent no sheet.

## Posting to the books — needs the accountant

Salary slips submit, but the payroll journal needs every component mapped to a
GL account, and **none are**. `onboarding.map_component_accounts(company)` applies
a proposal from the existing chart (same codes on every company):

| Line | Account |
|---|---|
| All earnings | 547101 Salary Expenses - O/O |
| SSF | 347302 SSF Payable |
| Income Tax | 348102 TDS-Remuneration |
| Salary Advance | 148003 Staff Advance |
| Late Fine | 547101 (reduces salary cost; no fines-income account exists) |

Proven in a rolled-back transaction: 87 NGI slips submitted and the journal
balanced, crediting Salary Payable with exactly the net pay (24,24,689.55).

**Open:** the chart splits salary expense three ways (O/O office, S/D sales &
distribution, F/P filling plant) but has no matching cost centres, and a
component maps to one account. Either create those cost centres per company and
set each employee's payroll cost centre, or accept one expense account.

Journals HRMS writes itself get a JV Type, and for the hand-numbered Journal
Entry / Cash Entry series the next number in that series (marked manual, so the
duplicate check still applies) — `payroll/hr_journal.py`.

## Month-end, in order

1. Attendance is complete for the BS month (reports: Monthly Attendance BS).
2. Overtime Sheets for the month are submitted and measured.
3. One-offs on **Payroll Adjustment**; bonus on **Dashain Bonus**; rises on **Salary Revision**.
4. New **Payroll Entry** — the posting date picks the BS month's dates. Get
   Employees and **Save only**: submitting the entry creates the slips at once.
5. **Prepare Payroll Inputs** while the entry is still a draft.
6. **Create Salary Slips** (this submits the entry and makes the slips).
7. Check tax on the slips; tick *Override Income Tax* where accounts knows better.
8. Submit Salary Slip (needs the GL mapping above).
