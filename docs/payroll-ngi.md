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
