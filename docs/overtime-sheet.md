# Overtime Sheet

One form for every kind of extra work the company asks for — a festival holiday, a
Saturday, or staying beyond the shift on a normal day.

## Design

```
POLICY          Employee Category     who is OT-eligible / gets replacement leave   (data, HR edits)
AUTHORISATION   Overtime Sheet        the company's approved request for a date      (document, Dynamic Approval)
RULES           hr/overtime.py        work type × day × category → entitlement       (service, one place)
READ API        get_authorised(date)  the one question settlement asks               (submitted sheets only)
SETTLEMENT      next step             attendance match → Additional Salary / Compensatory Leave Request
```

Each layer changes without the others: a new group is a Category record, a new
approver is a Dynamic Approval Setting, a policy change is one function.

## Policy

Client meeting 2026-09-15 — 5.1 (the sheet decides eligibility), 2.2 as corrected
on 2026-09-16, and 2.5:

| Work Type | Allowed when, for that person | Plant (Overtime Eligible) | Officer & Admin (Replacement Leave) |
|---|---|---|---|
| **Work on Holiday** | Holiday or Saturday | **Overtime** | **Replacement Leave** |
| **Overtime** | Working day | **Overtime** (hours outside the shift) | refused — not OT-eligible |

## Using it

1. **Overtime Sheet → New**: Company, Date (past dates fine), Department (optional),
   why the extra work was needed.
2. Add the employees who were asked in. **No times** — each row fills itself:
   **Work Type** (pre-chosen from the person's day; change it if needed), **Day**
   (Holiday / Weekly Off / Working Day from their own holiday list), **Earns**,
   **Category**, **Shift**.
3. Save. Every row the policy refuses is listed in one message.
4. Approve through Dynamic Approval. Only a **submitted** sheet authorises anything.

A sheet can mix day types: on Teej a woman is on Work on Holiday and a man on
Overtime, and each row is judged on its own.

## Hours come from attendance

The sheet authorises; it never measures. At settlement the punches give the hours:

- **Work on Holiday:** the hours worked that day.
- **Overtime:** the hours outside the rostered shift —
  `hr/overtime.py: hours_outside_shift(in, out, shift_start, shift_end)`.
  On a 6 AM – 2 PM shift: in 06:00 / out 18:00 → 4 h; in 05:00 / out 14:00 → 1 h;
  in 06:05 / out 13:50 → 0 h.

The shift is the dated Shift Assignment for that date, else the Default Shift.

## What it refuses

- a work type that does not fit the person's day (Work on Holiday on their working
  day, Overtime on their holiday) — the message says which to choose;
- an employee with no Employee Category (a default would pay money or grant leave
  wrongly);
- Officer & Admin with Overtime on a working day;
- Overtime for someone with no shift that day (it could not be measured);
- an employee of another company, listed twice, or already on another live sheet
  for the same date.

## Approval

Configure in the desk — the chain is the company's decision:
**Dynamic Approval Setting** → Document Type *Overtime Sheet*, Company, criteria
(e.g. `custom_created_by`), approvers → **Setup Workflow**.
`custom_created_by` exists because the doctype is in the audit list; it is filled
from desk requests, not scripts.

## Code

| Piece | Where |
|---|---|
| Rules + read API | `avinashgroup_app/hr/overtime.py` — `evaluate()`, `preview()`, `get_authorised()`, `was_authorised()`, `hours_outside_shift()` |
| Form | `avinash_group_app/doctype/overtime_sheet`, `overtime_sheet_employee` |
| Install | patch `setup_overtime_sheet` (also removes the earlier Holiday Duty Sheet) |

## Settlement — measuring the hours

`avinashgroup_app/hr/overtime_settlement.py`. The sheet says the work was asked
for; attendance says how long it lasted. **Measure from Attendance** on an
approved sheet (or `measure_sheet(name)`) reads the punches for that date and
writes each row's **Worked Hours**, the Attendance it came from, and a note:

| Row | Hours |
|---|---|
| Work on Holiday | every hour worked that day |
| Overtime | only the hours outside the rostered shift |
| Earns Replacement Leave | 0 — nothing to measure |
| No attendance | 0, "called in but did not come" |
| One punch only | 0, the hours cannot be measured |

Re-measuring is safe; it rewrites the same fields from the same source. Verified
on nepalgas: a holiday worked came out at 8.1 h, and staying to 14:15 on a
6 AM - 2 PM shift at 0.25 h.

`get_measured_hours(from, to, company)` is what payroll reads: hours both
**authorised and worked**, per employee, for a period.

## Next

Paying it: hours × `basic ÷ 30 ÷ 8 × 1.5` as an Additional Salary, and the
replacement-leave side for Officer & Admin. Punched but never authorised stays
unpaid by design — fix it with a backdated sheet.
