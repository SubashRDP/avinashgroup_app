---
name: clean-code
description: House conventions for writing code in avinashgroup_app — where a new file belongs, how to extend ERPNext/HRMS without patching it, what a module docstring must explain, and the review checklist before a commit. Use when adding a new module, override, scheduled job, report or doctype to this app, or when asked to clean up / refactor existing code here.
---

# Writing code in avinashgroup_app

This app extends ERPNext v15 and HRMS for seven Nepali gas companies. The rules
below are what keep it survivable across upgrades, seven companies, and the next
developer who opens it cold.

## 1. Never edit `apps/erpnext` or `apps/hrms`

**HRMS is pinned to v15.49.2 on a detached HEAD** to match live. Any edit there
vanishes on the next checkout, and nobody will know why the behaviour changed
back. ERPNext is the same story with fewer pins.

Extend from this app instead, in this order of preference:

| Need | Mechanism |
|---|---|
| React to a save/submit | `doc_events` in `hooks.py` |
| Replace a whitelisted API | `override_whitelisted_methods` |
| Replace a controller | `override_doctype_class` |
| Replace a scheduled job | stop the stock Scheduled Job Type, register your own under `scheduler_events` |
| Add a field | Custom Field fixture, never a core JSON edit |
| Change a field property | Property Setter — and know it can be wiped, see §6 |

If none of those fit, write your own function and call it from a hook. Do not
monkeypatch at import time; it breaks silently under workers.

## 2. Where a new file goes

Top-level packages under `avinashgroup_app/` are **by domain**, not by doctype:

```
biometric/     device punches → Employee Checkin → Attendance
hr/            leave, holidays, employee lifecycle
payroll/       salary, allowances
custom_code/   ERPNext-side overrides, grouped by doctype
  ├── SalesInvoice/  CBMS/  printing/  Override/  payment_entry/
scripts/       one-off and diagnostic scripts (read-only where possible)
patches/       migration patches, listed in patches.txt
avinash_group_app/
  ├── doctype/     custom doctypes
  ├── report/      script reports
  └── print_format/
```

Put the file where someone would *look* for it, not where it is convenient to
import from. If a domain package does not exist yet, create it with an
`__init__.py` and a `README.md` (see §5).

## 3. Every module opens with a docstring that explains *why*

Not what the code does — the code says that. The docstring says what was broken,
what this fixes, and what it deliberately does not do. `biometric/
attendance_self_heal.py` is the reference example: it enumerates the three stock
HRMS failure modes by name (F1/F2/F3) before a line of code.

Required elements:

- the problem, concretely, with the stock behaviour named
- the boundary — what this code refuses to do, and who owns that instead
- any landmine a future reader would otherwise step on

```python
"""One-line summary of what this module owns.

What is broken without it, described concretely enough that a reader who has
never seen the bug can recognise it in the wild.

Deliberately narrow: names what this does NOT do and which component owns
that decision instead.
"""
```

## 4. Function-level rules

- **Docstring on anything non-obvious**, saying what it raises and what it
  returns. Skip it on a three-line helper whose name already says it.
- **Named constants, with a comment on where the value came from.**
  `DEFAULT_DUPLICATE_THRESHOLD_SECONDS = 60  # matches the Biometric Device
  field default` — the comment is the point.
- **Never swallow an exception silently.** Either let it raise, or
  `frappe.log_error(title=..., message=...)` with the document name in the
  message. A bare `except: pass` is a bug report nobody will ever receive.
- **Fail loudly at the boundary, quietly in a mirror.** A validation hook should
  throw. A field-mirroring hook (BS date beside an AD date) should log and move
  on — it must never block a save it is only decorating.
- Type hints where they clarify (`serial: str -> str`), not everywhere.
- Imports grouped: stdlib, `frappe`, `frappe.utils`, `erpnext`/`hrms`, then this
  app. Absolute imports only.

## 5. Findability

The next developer arrives cold and greps. Help them:

- **A `README.md` in every domain package**, naming the entry points, the
  scheduled jobs it registers, and the doctypes it touches.
- **Name files after the domain concept**, not the pattern —
  `earned_leave_bs.py`, not `leave_utils.py` or `helpers.py`.
- **Docstring names the hook that calls it.** If a function only ever runs from
  `hooks.py`, say so; otherwise it reads as dead code.
- **Cross-reference the handoff doc.** Anything with operational consequence gets
  a line in `docs/` (see §7) and the module docstring points at it.

## 6. This codebase's specific landmines

- **`sync_on_migrate` wipes Customize Form.** Property Setters made in the desk
  can disappear on `bench migrate`. Anything that must persist belongs in a
  fixture or a patch.
- **Frappe never drops columns.** A removed field leaves its data behind; a
  renamed field needs a patch or the old value is silently reinterpreted.
- **Frappe Float columns are `NOT NULL`.** `SET col = NULL` throws; use 0.
- **Seven companies.** Company-scoped setup data is created for all seven, or
  for none. Never hardcode one abbreviation.
- **The books run on Bikram Sambat.** Fiscal years are `83/84`, starting mid-July.
  Anything month- or year-shaped needs `rdp_common_app.utils.bs_boundaries`
  (`get_bs_month_start/end`, `get_salary_period`), not `frappe.utils.get_last_day`.
- **`bench --site X execute` runs under RestrictedPython** and rejects any name
  starting with `_`. Use `bench console` or a standalone script from `sites/`.
- **Every `Hourly` job fires at `0 * * * *`.** Offset anything that must not race
  a job it depends on.

## 7. Documentation goes in `docs/`

Markdown, committed to the branch. Not artifacts, not scrollback.

- One file per subject — `docs/hrms-attendance-handoff.md`,
  `docs/leave-management.md`.
- A session that changes behaviour updates the relevant doc in the same commit.
- Doc structure that works here: environment → the pipeline in one picture →
  what was built → open blockers → gotchas found the hard way.

## 8. Before committing

- [ ] Nothing edited under `apps/erpnext` or `apps/hrms` — `git -C ../hrms status`
- [ ] Module docstring explains the *why* and the boundary
- [ ] No bare `except`; every swallowed error logs with a document name
- [ ] Constants named, with provenance comments
- [ ] Works for all seven companies, or is explicitly scoped and says so
- [ ] BS dates go through `bs_boundaries`, not `frappe.utils` month helpers
- [ ] New package has a `README.md`
- [ ] `docs/` updated if behaviour changed
- [ ] Commit as soon as it works — uncommitted work has been lost to hard resets
      between sessions on this repo
