# Employee groups: OT vs replacement leave

## The rule

From the client meeting of 2026-09-15, minute 2.2 **as corrected on 2026-09-16**
(the circulated minute says the opposite) and minute 2.5:

| Group | Worked a holiday or a Saturday |
|---|---|
| **Plant** | paid overtime + meals. **No** replacement leave |
| **Officer & Admin** | **replacement leave** (compensatory off). No overtime |

One switch decides both, and the same switch drives the OT sheet (5.1) and the
two tea & conveyance rates in the client's own salary sheet (plant 235/day,
office 40/day).

## Where it is kept

HR edits the two **Employee Group** documents. Membership sits in each group's
own table, and nothing on the Employee record points back — so payroll, leave and
our allowance engine cannot read it. They read the Employee field **OT Eligible**
(`custom_ot_eligibility`).

Saving a group therefore mirrors membership onto that field
(`avinashgroup_app/hr/employee_groups.py`, `on_update` hook): Plant → ticked,
Officer & Admin → unticked. An employee who ends up in both groups is left
unchanged and written to the Error Log, because the policy has no answer for that.

Editing the tick on an employee directly is not wrong, but the next save of
either group overwrites it. The groups are the place to change someone.

## State on nepalgas (2026-09-16)

| Group | Members |
|---|---|
| Plant | 206 |
| Officer & Admin | 89 |

Only 30 of 295 employees have a Designation, so the split is largely inferred:
plant-side designations went to Plant, office-side to Officer & Admin, NGI's
9 AM - 6 PM shift (82 people) to Officer & Admin, and everyone else defaulted to
Plant. **The client still has to confirm it**, especially for the six companies
other than NGI, which are 100% Plant by default.

## Still to build

Granting the leave. A step that reads Attendance where `custom_worked_on_holiday`
is set, keeps the employees whose OT Eligible is unticked, and files an approved
Compensatory Leave Request for each. It needs a Leave Type with **Is
Compensatory**, which arrives with the leave setup.
