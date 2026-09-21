# Allowance Category — a group's rate, changed in one place

## Why

NGI's Falgun 2082 sheet pays **tea & conveyance per day worked**, at two different
rates, decided by a category on each employee:

| Category | Rate | People |
|---|---|---|
| **OLD** | 235/day | 51 |
| **NEW** | 40/day | 29 |
| **NO** | nothing | 4 |

It is **not** a department rule — Plant has 37 OLD and 11 NEW, the office has 8
OLD and 11 NEW. The sheet's formula reads the category off the Employee Record.

Typing 235 or 40 onto 92 employees would make one change ("235 becomes 250") a
51-row edit, and moving one person between groups a hunt for the right cell.

## How it works

| Piece | What it is |
|---|---|
| **Allowance Category** | one record per group, with a rate per salary component |
| **Employee → Allowance Category** | the group this person is in |
| the allowance engine | resolves a rate as: the employee's own **Attendance Allowances** row → **their category** → the component's default rate |

So:
- **move a person between groups** → change one field on their Employee record;
- **change what a group is paid** → change one number on the category;
- **one person paid differently from their group** → their own Attendance
  Allowances row still wins;
- a **category rate of 0** means the group is not paid that component at all (the
  sheet's NO), and it does not fall through to the default.

A category carries rates for several components at once, so meals or an OT
multiplier can join tea later without new code, and a new group is a record.

## State on nepalgas (2026-09-21)

Categories OLD / NEW / NO exist with the Falgun rates, on the salary component
**Tea & Conveyance** (attendance-driven, Per Day, Status = Present).

Set from the sheet on **84 of 107** NGI employees. The other 23: the 8 with no
attendance in Falgun (their tea was 0 either way, so the sheet cannot say which
group they are in — the client must) and 15 staff who are on the system but not
in that month's sheet.

Code: `payroll/attendance_allowance.py` (`_get_category_rates`, `_resolve_rate`),
doctypes `Allowance Category` and `Allowance Category Rate`, patch
`setup_allowance_category`.
