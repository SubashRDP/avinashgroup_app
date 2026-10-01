# Shift rotation

Some NGI staff change shift every month — a month on **6 AM - 2 PM**, the next on
**12 PM - 8 PM**, and back. Only those two shifts rotate. The 9 AM - 6 PM day
shift and every other company's shifts are fixed: nobody is rotated onto them or
off them.

HR does the rotation by hand, on screen, when it is due. Nothing runs on a
schedule and nothing alternates by itself (developer's decision, 2026-10-01).

Code: `avinashgroup_app/hr/shift_rotation.py` · desk:
`public/js/shift_type.js` · setup: `patches/setup_shift_rotation.py` · tests:
`hr/test_shift_rotation.py`.

## How HR uses it

1. Open the Shift Type people are moving **onto** (HR → Shift Type →
   `NGI 12 PM - 8 PM`).
2. Press **Move Staff to This Shift**.
3. The dialog shows the **From Date** — the first day of the next BS month, change
   it to any date — and everybody of that company who is on one of the *other*
   rotational shifts on that date.
4. Tick who moves (the header checkbox ticks everyone) and press **Move**.

Everybody ticked is on the new shift from that date, with no end date, until HR
moves them again. Next month, open the other shift and do the same.

    before          6 AM - 2 PM   Shrawan 1 ─────────────────────────▶ open
    1 Kartik        6 AM - 2 PM   Shrawan 1 ──▶ 30 Asoj
                    12 PM - 8 PM                1 Kartik ─────────────▶ open
    1 Mangsir       6 AM - 2 PM   Shrawan 1 ──▶ 30 Asoj
                    12 PM - 8 PM                1 Kartik ──▶ 30 Kartik
                    6 AM - 2 PM                              1 Mangsir ▶ open

The result lists who moved and, by name with the reason, who did not. One
person's refusal does not stop the others.

**Changing it afterwards**

| Wanted | Do |
|---|---|
| Somebody was moved by mistake | Open the shift they came from, same From Date, tick them, Move. The rotated assignment is cancelled and the earlier one runs on again, as if nothing happened. |
| The date was wrong | Undo as above, then move again from the right date. |
| One person, a few days only | A **Shift Request** with a To Date, as before (`hr/shift_change.py`). Rotation is not involved. |

## Which shifts rotate

A checkbox on the Shift Type: **Takes Part in Rotation** (`custom_in_rotation`).
The patch adds the field and ticks the two NGI shifts — found by company and
hours (06:00–14:00, 12:00–20:00), because they are `NGI 6 AM - 2 PM` on one site
and `6 AM - 2 PM` on another. HR can tick or untick any shift later; the button
appears only on ticked shifts.

The rule, enforced on the server (`rotate` → `_check_target`, `_move`), whatever
the dialog showed:

- the shift a person is **leaving** on that date must be ticked;
- the shift they are **joining** must be ticked;
- both must belong to the employee's own company.

Anything else is refused with a sentence naming the shift and the way out, e.g.
*"Ram (NGI-EMP-00029) is on NGI 9 AM - 6 PM on 18-10-2026, which does not take
part in rotation. Only staff on NGI 6 AM - 2 PM, NGI 12 PM - 8 PM rotate; for a
one-off change use a Shift Request."*

Also refused:

- a person with a **dated shift change still ahead** of the From Date (a Shift
  Request for next week, a move already booked for a later month). Cancel that
  first — whose dates win is HR's call, not the tool's;
- a From Date reaching into a **month already paid** (submitted Salary Slip) —
  the same guard a backdated Shift Assignment has.

## Why the stock screens could not do this

Everybody holds one open-ended Shift Assignment from the start of the fiscal
year. Measured on `nepalgas`, 2026-10-01:

| Stock route | What happens |
|---|---|
| Shift Assignment for next month | `MultipleShiftError`: "already has an active Shift Assignment … for some/all of these dates" |
| Shift Assignment Tool → Assign Shift | offers 1 of 107 active employees: it hides everyone who already has a shift |
| Shift Schedule | repeats by weekday every 1–4 weeks, not by month, and creates the same overlapping assignments |
| Shift Request, month 1 (no To Date) | works — `hr/shift_change.py` makes room |
| Shift Request, month 2, the way back | `OverlappingShiftRequestError`: month 1's request has no end, so every later request "overlaps" it. With a To Date instead, the way back is refused as "You can not request for your Default Shift" |
| Any of them, onto 9 AM - 6 PM | allowed — nothing knew which shifts rotate |

So rotation moves the Shift Assignments itself, the same way a permanent Shift
Request does: the standing one ends the day before, the new one starts.

## A From Date in the past

Allowed — "they have been on evenings since the 1st". The days already lived are
handled by `hr/shift_backdate.py`, exactly as for a backdated Shift Assignment:
attendance is re-marked on the new shift (11:58 → 20:03 is six hours late on
6 AM - 2 PM and on time on 12 PM - 8 PM), approved Overtime Sheet rows are
re-measured, and more than 45 days goes to the `long` queue.

## Deploy

`bench migrate` is required: the patch `setup_shift_rotation` creates the custom
field and ticks the two shifts. Until then the button does not appear and the
API answers "Shift rotation is not set up on this site yet".

After migrate, check HR → Shift Type: `Takes Part in Rotation` is ticked on
exactly the two NGI shifts.

## Tests

`bench run-tests` fails at bootstrap on the dev bench, so run the module with a
small runner, from anywhere:

```python
# run.py — ../env/bin/python run.py
import os, sys, unittest
os.chdir("/home/sijan/frappe-15/sites")          # site log paths are cwd-relative
import frappe
frappe.init(site="nepalgas", sites_path="."); frappe.connect()
frappe.flags.in_test = True
suite = unittest.defaultTestLoader.loadTestsFromName("avinashgroup_app.hr.test_shift_rotation")
ok = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
frappe.db.rollback(); frappe.destroy(); sys.exit(not ok)
```

The suite builds its own employees, Shift Types and assignments in one
transaction and rolls it back. It replaces `rotational_shifts` (the only reader
of the checkbox), so it also runs on a site that has not been migrated.

## Not built

- No automatic monthly swap and no scheduler job — by decision.
- Shift Request is not restricted: one person can still be moved onto a fixed
  shift by an approved request. That is the "plain case", left as it was.
- The move is not a document of its own. The record is the Shift Assignments
  (the undone one stays, cancelled).
