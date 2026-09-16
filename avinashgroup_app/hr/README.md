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

`apply_holiday_change()` adds or removes one date across the lists chosen by
company and `scope` ("both" / "women" / "common"). The desk entry point is the
**Holiday Bulk Update** doctype
(`avinash_group_app/doctype/holiday_bulk_update/`): fill its Holidays table, set
each row's `Applies To` (All Lists / Common Only / Women Only), choose the
companies — all of them, or just the two or three that change — press Apply.

It writes Holiday List rows only. Attendance already marked on that date is not
re-marked — use Attendance Fix for that.
