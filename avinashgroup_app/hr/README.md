# HR in this app — where everything lives

**Start here** if you are looking for anything attendance-, leave-, holiday- or
payroll-shaped. HR code is spread across five locations, and that is deliberate:
Frappe pins doctypes, reports and patches to fixed paths, so the map below is
the map, not a mess waiting to be tidied.

## The routing table

| Looking for | It is here | Why not elsewhere |
|---|---|---|
| Device punches, bridge API, checkin de-dup, self-heal | `biometric/` | the K40 bridge posts into `biometric/api.py`; the path is part of the deployed contract |
| Leave accrual, holidays, employee lifecycle | **`hr/`** ← you are here | |
| Salary components, attendance allowance | `payroll/` | |
| Attendance Fix, Attendance Correction Log, Biometric Device, Employee Attendance Allowance (doctypes) | `avinash_group_app/doctype/` | Frappe binds a doctype to its **module**, recorded in `tabDocType.module`. Moving the folder needs a new Module Def plus a DB patch |
| Monthly Attendance BS, Yearly Leave Details BS, Work On Holiday BS, Avinas Salary Statement | `avinash_group_app/report/` | same rule, via `tabReport.module` |
| One-off HR migrations | `patches/` | `patches.txt` addresses them by dotted path and `tabPatch Log` records what ran. A rename re-runs the patch on every site |
| Leave/Attendance numbering rules | `custom_code/Override/naming_series.py` | a cross-cutting engine serving 30+ doctypes; HR doctypes are rows in its config table, not its subject |
| Leave Application approval | `custom_code/dynamic_approval.py` | the workflow engine is generic; Leave Application is one of its consumers |
| Fiscal-year filters on HR list views | `custom_code/fiscal_year_filter.py` | same — generic, HR doctypes are entries |

## What `hr/` owns

| File | What it owns | Entry point |
|---|---|---|
| `hr_dashboard.py` | Data for the HR dashboard: one BS month of headcount, attendance, **month close** per paying company (attendance → overtime → payroll entry → slips → journal → paid), **statutory deposits due** (TDS by the 25th, SSF by the 15th of the next BS month, Dashain allowance before Fulpati), approvals waiting, missing employee data, decisions due (probation / contract / retirement), who is on leave this week, the next 30 days in BS dates; plus the HR menu filtered by permission. Read-only; pay figures need Salary Slip read. Shown in two places from one script, `public/js/hr_dashboard.js`: at the **top of the stock HR workspace** (`public/js/hr_workspace.js` places it above the workspace editor, so HRMS's own `hr.json` is never edited and "Edit → Save" cannot store it; it also hides HRMS's setup checklist on that page) and the full-width page `/app/hr-dashboard`. Click test: `scripts/hr_dashboard_clicktest.mjs`. | `get_dashboard`, `get_menu` (whitelisted) |
| `year_setup.py` | `setup_year(fiscal_year)`: a whole fiscal year for every company — holiday lists, shifts, leave period/policies, payroll period, tax slab, **pay rolled onto the new slab** (`payroll/year_rollover.py`), leave policy assignments. Refuses without the Fiscal Year or the year's tax rates; warns without festival dates. Runbook: `docs/payroll-complete-reference.md` §9 "Year rollover". | `bench execute` |
| `holiday_year_switch.py` | On a fiscal year's first day, repoints Company defaults and employees (the women's lists) from last year's holiday lists to this year's. HRMS keeps one list per person, so without it nobody has holidays after 31 Ashadh. | `scheduler_events` → `daily_long` |
| `leave_policy_assignment_bs.py` | Leave Policy Assignment override: a mid-year assignment back-fills earned leave in **BS** months (HRMS counts AD months and over-credits one). | `override_doctype_class` |
| `utils.py` | HR overrides — currently: monthly earned-leave accrual on **Bikram Sambat** months | `scheduler_events` → `daily_long` (the stock job is stopped by `patches/setup_bs_leave_accrual`) |
| `punch_correction.py` | HR sets one past day's First IN / Last OUT, and/or the shift of that day or up to 31 days (`_apply_shift`: `shift_rotation.make_room` + one stamped Shift Assignment covering exactly the days, `patches/setup_shift_correction_fields`), from the Monthly Attendance BS grid. Every correction, here or on the Employee Checkin form, writes an **Attendance Correction Log** entry (`log_correction`). Punches: punches moved or added (never deleted), stamped with the device's original time, who, when and why (`custom_time_edited` …, `patches/setup_punch_correction_fields`); the day's punches pinned to the rostered shift and its attendance rebuilt through `reconcile_employee_day`, Overtime Sheet rows re-measured. Refused under a submitted slip, on leave days, today. The report highlights stamped punches (`get_edited_days`). The same re-mark runs when a past day's punch is added, moved or deleted on the Employee Checkin form (`remark_from_form`, from `biometric/attendance_sync`'s hooks). | whitelisted `correct_day`, called by the report's edit dialog; `remark_from_form` / `can_detach` / `stamp_form_change` from the Employee Checkin hooks |
| `leave_from_report.py` | HR gives leave for chosen days from the Monthly Attendance BS grid: one approved, submitted Leave Application per run of consecutive days (HRMS's validate, balance, ledger and attendance marking; the Dynamic Approval workflow is not walked — HR is the approver), days with punches made Half Day with the leave kept (policy 3.4), each day logged as **Leave Given** in the Attendance Correction Log. Refused inside a submitted slip. | whitelisted `leave_types_for`, `preview`, `give_leave`, called by the report's **Give Leave** dialog; `get_leave_notes` for its highlight |
| `shift_backdate.py` | A Shift Request / Shift Assignment reaching into past days: those days' attendance is re-marked on the new shift, Overtime Sheet rows re-measured; refused when the days are already paid. Detaches the days first, because HRMS will not cancel an assignment while attendance names its shift. | `doc_events` → Shift Request / Shift Assignment |
| `shift_rotation.py` | Monthly rotation between the Shift Types ticked `Takes Part in Rotation` (NGI: 6 AM - 2 PM and 12 PM - 8 PM): moves a ticked list of employees onto the other shift from one date, open-ended; source and target must both be rotational and of the employee's company. HR-triggered, no scheduler. Past dates are re-marked through `shift_backdate`. Write-up: `docs/shift-rotation.md`. | whitelisted `preview` / `rotate`, called by **Move Staff to This Shift** on the Shift Type form (`public/js/shift_type.js`); whitelisted `set_periods` (bounded ranges, via `set_period`) for the Shift Roster page's Apply |
| `replacement_leave.py` | Overtime Sheet rows earning Replacement Leave (officer / admin holiday work) become a submitted Compensatory Leave Request once attendance shows the day was worked; cancelling the sheet takes the days back. | `doc_events` → Overtime Sheet on_submit / on_cancel; `daily_long` → `grant_pending` |
| `bs_calendar.py` | Which English dates a BS month covers: Nepal BS Period (company, then global), else the Nepali calendar; the slip's own rule. The one answer for the Payroll Entry, the BS period guard, Monthly Attendance BS and the deposit report. | imported; whitelisted `get_month` / `get_default_month` for forms and report filters |
| `bs_dates.py` | `custom_*_miti` BS dates beside the AD dates on Leave Application, Payroll Entry, Employee and Salary Slip, plus `Salary Slip.custom_bs_month`. Server side of rdp_common_app's Bs Conversion picker. | `doc_events` → validate |

## Why this package exists

Stock HRMS does its month arithmetic in Gregorian months. The books here run
Shrawan → Ashad, so anything that accrues, pro-rates or expires "per month"
lands on the wrong date — and in one case on no date at all. See
`utils.py` for the worked example, which costs every employee one
day of leave per year under stock behaviour.

Nothing here edits `apps/hrms`. HRMS is pinned to v15.49.2 on a detached HEAD to
match live, so edits there do not survive a checkout. Every override either
replaces a scheduled job or hangs off a hook in `hooks.py`.

## Related docs

- `docs/leave-management.md` — how leave works, field by field, plus the BS audit
- `docs/hrms-attendance-handoff.md` — the attendance pipeline and its open blockers
- `.claude/skills/clean-code/SKILL.md` — house conventions before you add a file here

## holiday_lists.py — bulk holiday maintenance

Seven companies keep two Holiday Lists each per fiscal year: `<ABBR> 83/84` (the
Company default, inherited by everyone) and `<ABBR> 83/84 (Women)` (the same days
plus Teej and International Women's Day, set on each female Employee).

`apply_holiday_change()` adds or removes one date across the Holiday Lists it is
given (all of them when none are named). The desk entry point is the **Holiday
Bulk Update** doctype (`avinash_group_app/doctype/holiday_bulk_update/`): the
holiday date and name sit on the document, and you either leave "All Holiday
Lists" ticked or pick the lists — the seven (Women) lists for a women-only day,
one company's two for a branch festival.

The desk screen only adds; `apply_holiday_change(action="Remove Holiday", ...)`
stays available for scripts and for whatever replaces the removal UI.

For a date already past, `holiday_backdate.follow_up()` then brings that day's
attendance in line: "Worked on Holiday" ticked for everyone who came, Absent rows
with no punches removed, employees whose month is already paid skipped and
named, approved Overtime Sheets for the date listed for HR to amend. Removing a
holiday (on the Holiday List itself) does not re-mark anything; use Attendance Fix.

## Who gets OT, who gets replacement leave — two ticks on the Employee

`Employee.custom_ot_eligibility` ("Overtime Eligible") and
`Employee.custom_compensatory_leave` ("Replacement Leave for Holiday Work"), set
per person; never both (`overtime.validate_employee_holiday_rule`, an Employee
validate hook). `overtime.get_holiday_work_rule` reads them. Until 2026-10-13 this
came from the Employee Category the person was linked to; patch
`holiday_work_rule_on_employee` copied each person's answer across. The
`Employee Category` doctype, the `custom_employee_category` link and the
`Employee Category Tool` were then removed (patch `drop_employee_category`).
History: `docs/payroll-complete-reference.md`.


## overtime.py — the overtime rules

The only place the policy for extra work lives: `evaluate(employee, date, from,
to)` turns a row into a day type, an entitlement (Overtime / Replacement Leave) and
hours; `get_authorised(date)` is what settlement reads (submitted Overtime Sheets
only). Full write-up: `docs/payroll-complete-reference.md`.
