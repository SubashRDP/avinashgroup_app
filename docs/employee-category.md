# Employee Category — overtime vs replacement leave

## The rule

From the client meeting of 2026-09-15, minute 2.2 **as corrected on 2026-09-16**
(the circulated minute says the opposite), and minute 2.5:

| Category | Worked a holiday or a Saturday |
|---|---|
| **Plant** — below officer level | paid overtime + meals. **No** replacement leave |
| **Officer & Admin** | **replacement leave** (compensatory off). No overtime |

Never both — the Employee Category form refuses a category with both ticked.

## How it is kept

| Piece | What it is |
|---|---|
| **Employee Category** (doctype) | one record per group, stating its rule: *Overtime Eligible*, *Replacement Leave for Holiday Work*, and who belongs |
| **Employee → Employee Category** (`custom_employee_category`) | the group a person is in. A field on the employee, so list views and reports can filter by it |
| **Employee → OT Eligible** (`custom_ot_eligibility`) | now read-only, fetched from the category. The allowance engine already reads this flag, so it needed no change |
| **Employee Category Tool** | bulk assignment, laid out like Shift Assignment Tool |

Changing a category's *Overtime Eligible* tick updates every employee already in
it at once (`EmployeeCategory.sync_employees`), because `fetch_from` alone only
refreshes an employee when that employee is next saved.

A third group later — a driver pool, say — is a new Employee Category record, not
a code change.

## Using the tool

1. **Employee Category Tool** → **Assign Category**: the category to put people in.
2. Narrow the list with Company, Branch, Department, Designation, Current
   Category, *Only Employees Without a Category*, or Advanced Filters on any
   Employee field.
3. The grid shows only employees **not already** in that category. Tick them,
   press **Assign Category**, confirm.

Each employee is saved normally, so the change shows in their history. One that
fails validation is listed and skipped; the rest still go through.

## Why not Employee Group

ERPNext's Employee Group keeps its members inside the group document, and nothing
on the Employee points back. In v15 only the telephony features read it; Payroll
Entry, Leave Control Panel and the assignment tools cannot filter by it. The first
cut used a hook to copy group membership onto the employee; this replaces it with
a field the employee actually carries.

## State on nepalgas (2026-09-17)

The split carried over from the Employee Groups: largely inferred, because only
30 of 295 employees have a Designation. Plant-side designations and every
uncategorisable employee went to Plant; office-side designations and NGI's
9 AM - 6 PM shift (plus Archana Bajracharya) to Officer & Admin.
**The client still has to confirm it.**

## Still to build

Granting the replacement leave: read Attendance where `custom_worked_on_holiday`
is set, keep employees whose category has *Replacement Leave for Holiday Work*,
and file an approved Compensatory Leave Request for each. Needs a Leave Type with
**Is Compensatory**, which arrives with the leave setup.
