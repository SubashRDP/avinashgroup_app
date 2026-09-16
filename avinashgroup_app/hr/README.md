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
| Attendance Fix, Biometric Device, Employee Attendance Allowance (doctypes) | `avinash_group_app/doctype/` | Frappe binds a doctype to its **module**, recorded in `tabDocType.module`. Moving the folder needs a new Module Def plus a DB patch |
| Monthly Attendance BS, Yearly Leave Details BS, Work On Holiday BS, Avinas Salary Statement | `avinash_group_app/report/` | same rule, via `tabReport.module` |
| One-off HR migrations | `patches/` | `patches.txt` addresses them by dotted path and `tabPatch Log` records what ran. A rename re-runs the patch on every site |
| Leave/Attendance numbering rules | `custom_code/Override/naming_series.py` | a cross-cutting engine serving 30+ doctypes; HR doctypes are rows in its config table, not its subject |
| Leave Application approval | `custom_code/dynamic_approval.py` | the workflow engine is generic; Leave Application is one of its consumers |
| Fiscal-year filters on HR list views | `custom_code/fiscal_year_filter.py` | same — generic, HR doctypes are entries |

## What `hr/` owns

| File | What it owns | Entry point |
|---|---|---|
| `utils.py` | HR overrides — currently: monthly earned-leave accrual on **Bikram Sambat** months | `scheduler_events` → `daily_long` (not yet wired — see its docstring) |

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

It writes Holiday List rows only. Attendance already marked on that date is not
re-marked — use Attendance Fix for that.

## employee_groups.py — who gets OT, who gets replacement leave

Two Employee Groups carry the 2026-09-15 policy split (2.2 corrected 2026-09-16,
and 2.5):

| Group | Holiday / Saturday worked |
|---|---|
| `Plant` | paid OT + meals, no replacement leave |
| `Officer & Admin` | replacement leave, no OT |

Membership lives inside the Employee Group document, where payroll, leave and our
allowance engine cannot see it — they read `Employee.custom_ot_eligibility`. The
`on_update` hook on Employee Group mirrors membership onto that field (Plant → 1,
Officer & Admin → 0); `sync_all()` does the same as a backfill. An employee in
both groups is left untouched and logged.

Granting the replacement leave itself is a separate step that reads the same
field, so leave is never granted as a side effect of saving a group.
