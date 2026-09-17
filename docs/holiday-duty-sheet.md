# Holiday Duty Sheet — the company's call-in for holiday work

## Why

Policy 5.1 (client meeting 2026-09-15): holiday overtime is tracked on a per-day
sheet, and **that sheet decides eligibility**. A punch on a holiday proves someone
was on site; it does not prove the company asked them to be. Only work the company
called for earns:

| Employee Category | Called in and worked a holiday |
|---|---|
| Plant | paid overtime + meals |
| Officer & Admin | replacement leave |

(see `docs/employee-category.md`)

## The procedure

1. **Company calls staff in.** Whoever arranges it raises a **Holiday Duty Sheet**:
   company, date, optional department, why, and the employees with planned From/To.
2. **Approval** through Dynamic Approval — the sheet counts once it is submitted.
3. **On the day** staff punch as usual.
4. **After the day**, attendance is matched against approved sheets (next step to
   build): on the sheet and punched → counts; punched but not on a sheet → flagged
   for admin; on the sheet but no punch → flagged.

**Backdated sheets are allowed.** Duty is often arranged by phone and written up
afterwards, and someone who came in without being listed is put right by adding
them to a sheet — never by guessing from punches.

## What the sheet refuses

- a date that is not a holiday **for that employee** — checked against each
  person's own holiday list, so Teej counts for women on a (Women) list and is a
  normal working day for men;
- an employee from another company;
- the same employee twice on one sheet, or on two live sheets for the same date
  (they would be compensated twice);
- To before From. Planned Hours is worked out from the times.

## Approval — Dynamic Approval

The doctype is ready for it; the approval chain is the company's call, so it is
configured in the desk, not in code:

1. **Dynamic Approval Setting** → New: Document Type = *Holiday Duty Sheet*,
   Company, the approver table and level field names, match criteria (e.g.
   `custom_created_by` = the plant manager) and fixed approvers per section.
2. **Setup Workflow** on that setting.

`custom_created_by` exists on this doctype because it was added to the audit list
(`utils/audit_file_manager.py`); it is filled from desk requests, not from scripts.

## Code

| Piece | Where |
|---|---|
| Doctypes | `avinash_group_app/doctype/holiday_duty_sheet`, `holiday_duty_sheet_employee` |
| Read side for later steps | `hr/holiday_duty.py` — `get_called_employees(date, company)`, `was_called(employee, date)`, `get_holiday_for_employee(employee, date)` |
| Install | patch `setup_holiday_duty_sheet` (doctypes + audit fields) |

Only **submitted** sheets count in `get_called_employees`; a draft or a sheet still
pending approval is a request, not a call-in.
