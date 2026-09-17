# Overtime Sheet

One form for every kind of extra work the company asks for — a festival holiday, a
Saturday, or staying beyond the shift on a normal day.

## Design

```
POLICY          Employee Category     who is OT-eligible / gets replacement leave   (data, HR edits)
AUTHORISATION   Overtime Sheet        the company's approved request for a date      (document, Dynamic Approval)
RULES           hr/overtime.py        day type × category → entitlement; hours       (service, one place)
READ API        get_authorised(date)  the one question settlement asks               (submitted sheets only)
SETTLEMENT      next step             attendance match → Additional Salary / Compensatory Leave Request
```

Each layer changes without the others: a new group is a Category record, a new
approver is a Dynamic Approval Setting, a policy change is one function.

## Policy

Client meeting 2026-09-15 — 5.1 (the sheet decides eligibility), 2.2 as corrected
on 2026-09-16, and 2.5:

| Employee Category | Holiday / Saturday | Working day |
|---|---|---|
| **Plant** (Overtime Eligible) | **Overtime**, all hours worked | **Overtime**, hours outside the shift |
| **Officer & Admin** (Replacement Leave) | **Replacement Leave** | refused — not OT-eligible |

## Using it

1. **Overtime Sheet → New**: Company, Date (past dates fine), Department (optional),
   why the extra work was needed.
2. Add employees with **From / To**. Each row fills itself as you type:
   **Day** (Holiday / Weekly Off / Working Day, from that person's own holiday list),
   **Earns** (Overtime / Replacement Leave), **OT Hours**, plus Category and Shift.
3. Save. Every row the policy refuses is listed in one message.
4. Approve through Dynamic Approval. Only a **submitted** sheet authorises anything.

A sheet can mix day types: on Teej a woman is on a holiday and a man on a working
day, and each row is judged on its own.

## How hours are worked out

- **Holiday / Saturday:** To − From. Times are optional for Replacement Leave.
- **Working day:** the part of From–To outside the rostered shift — before it
  starts or after it ends. From 14:00 to 18:00 on a 6 AM – 2 PM shift is 4 h; 05:00
  to 07:00 is 1 h; 07:00 to 13:00 is refused as inside the shift.
- A window past midnight (20:00 → 02:00) counts as 6 h. A window under a minute is
  treated as no times given.
- The shift is the dated Shift Assignment for that date, else the Default Shift.

## What it refuses

- an employee with no Employee Category (a default would pay money or grant leave
  wrongly);
- Officer & Admin on a working day;
- a working-day row without From/To, with no shift, or entirely inside the shift;
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
| Rules + read API | `avinashgroup_app/hr/overtime.py` — `evaluate()`, `preview()`, `get_authorised()`, `was_authorised()` |
| Form | `avinash_group_app/doctype/overtime_sheet`, `overtime_sheet_employee` |
| Install | patch `setup_overtime_sheet` (also removes the earlier Holiday Duty Sheet) |

## Next

Settlement: match `get_authorised()` against attendance. Authorised and punched →
Additional Salary for overtime (Plant) or a Compensatory Leave Request (Officer &
Admin). Punched but not authorised → flagged; fixed by a backdated sheet.
