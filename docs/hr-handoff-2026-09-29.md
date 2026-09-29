# HR / Payroll session handoff — 2026-09-27 → 29

Session id: `72aeebaa-3a85-431c-a123-d47a843957e6` (transcript in `session/`).
Repo: `avinashgroup_app`, branch `develop` — **all code is pushed** (origin/develop `812a5cf`
contains the 10 HR commits `297ebbd … 08672a0`). Test site: `avinas1` on the laptop
(`/home/sijan/frappe-15`), migrated and matching the code.

## How to continue on another machine

1. `git pull origin develop` in apps/avinashgroup_app, then `bench --site <site> migrate`.
2. To resume THIS conversation in Claude Code: copy `session/72aeebaa-….jsonl` (and the
   folder of the same name) into `~/.claude/projects/<project-dir>/`, where
   `<project-dir>` is the app path with `/` replaced by `-`
   (laptop: `-home-sijan-frappe-15-apps-avinashgroup-app`;
   dell box: `-home-dell-frappe-v15-apps-avinashgroup-app`). Then run
   `claude --resume 72aeebaa-3a85-431c-a123-d47a843957e6` from that app folder.
3. Or start fresh: copy `claude-memory/*` into that project dir's `memory/` and tell the
   new session "read HANDOFF.md". Memory note `hr-gaps-build.md` is the resume point.

## What was built (all on develop)

| Area | What | Where |
|---|---|---|
| Backdated shifts | Shift Request / Assignment into past days re-marks attendance on the new shift (late minutes, half day, OT re-measured); refused into a paid month; worked day never flips to Absent — kept + flagged; days "detached" first because HRMS won't cancel an assignment that attendance names | `hr/shift_backdate.py` |
| Replacement leave | Overtime Sheet "Replacement Leave" rows → Compensatory Leave Request (leave type Replacement Leave) once attendance shows the day; daily job; cancel takes it back | `hr/replacement_leave.py` |
| Tax | Retirement cap (≤ lower of ⅓ income / 5,00,000) + women's rebate 10% (field on Income Tax Slab) as Salary Slip validate hook; insurance/CIT via HRMS exemption declaration; CIT component | `payroll/tax_relief.py`, `patches/setup_tax_exemptions.py` |
| Deposit report | "Salary Tax and SSF Deposit": SSF 31%, SST, remuneration tax per BS month + deadlines; HR roles only | `report/salary_tax_and_ssf_deposit/` |
| BS dates | `custom_*_miti` on Leave Application, Payroll Entry, Employee, Salary Slip (+ `custom_bs_month`); "Salary Slip BS" default print format + email template | `hr/bs_dates.py`, `templates/print_formats/salary_slip_bs.html` |
| Backdated holiday | Holiday Bulk Update on a past date: Worked on Holiday ticked, no-punch Absent removed, paid employees skipped + listed, OT sheets listed | `hr/holiday_backdate.py` |
| Women's list | ~~Employee save: Female → company's Women holiday list~~ **REMOVED 2026-09-29** on the user's instruction: `Employee.holiday_list` is set by whoever uploads/edits the employee, and the hook overrode that choice for women on every save. The Women holiday lists themselves stay — `year_setup` still creates them and Teej is entered with Holiday Bulk Update; only the automatic per-employee assignment is gone. Existing rows were left untouched (21 women on avinas1) | *(deleted)* |
| Dashain reminder | Dashboard finds any Dashain holiday name (Ghatasthapana/Fulpati/Ashtami…), EN or NE | `hr/hr_dashboard.py` |
| Punch windows | Check-in 3 h before / check-out 4 h after — **HR sets these on each Shift Type** (no constants); at 2 h, overtime check-outs were dropped and worked days became Absent | Shift Type fields; runbook §9 |
| Meal rule | Holiday hours for 1 / 2 meals (6/8) and max per day (2) are fields on the Meal Salary Component; Time Offset field now visible | `payroll/attendance_allowance.py`, `patches/setup_meal_rule_fields.py` |
| Late half day | >2 h late = Half Day + Half Day Status **Absent**, no leave type (was "Leave Without Pay"); pay identical (58 slips checked) | `biometric/attendance_override.py`, `patches/late_half_day_as_half_absent.py` |
| Site-only fields | Holiday List.custom_company, Attendance late/early fields, Shift Type cutoff now created by a patch | `patches/add_site_only_hr_fields.py` |

Handover doc in repo: `docs/payroll-handover.md` (§4 built, §8 open, §9 go-live runbook).

## Data changed on avinas1 (not in code)
- 2083 holiday lists for NGG / NGK / NGN from the HR PDFs (Baisakh rows skipped = FY 82/83); Teej only on Women lists.
- All 77 NGN staff on `NGN 9 AM - 5 PM` from 2026-07-17 (7–3 list still unknown).
- 127 worked days re-marked Absent → Present/Half Day after widening punch windows; Teej flags fixed.

## Decisions made by the user in this session
- Build audit items 3–7, skip 1 (holiday punches → attendance) and 2 (only approver creates Shift Requests).
- Shifts can be backdated → re-mark attendance.
- Keep TWO holiday lists per company (common + Women), women assigned automatically.
- Paid month + backdated holiday → warn/skip, don't refuse.
- No static numbers in code where the form has a field (punch windows, meal rule).
- Late half day is "paid but half" → HRMS half-absent, never "Leave Without Pay".
- Push only HR changes; do NOT merge `grid-wide-columns` or other old branches.

## Open items
| # | Item | Who |
|---|---|---|
| 1 | Browser walkthrough of the new screens (only script-tested) | dev |
| 2 | Deploy to ng-group / demo-nggroup: pull, migrate, restart; **recreate draft salary slips made before deploy** (late half-day switch would double-deduct) | dev |
| 3 | demo-nggroup shift types wrong: stray Late Arrival Cutoff 09:49, windows 60/60, half/absent thresholds 0/0, late marking + auto attendance off | dev (needs go-ahead to write) |
| 4 | ~~Ashwin 2083 = 31 days~~ **DONE 09-29**: the dell box was the stale server. `nepali-datetime` 1.0.8.4 → 1.0.8.5 in `frappe-v15/env`; now 31 days, Kartik 1 = 2026-10-18. Needs a `bench start` restart to reach the workers | dev |
| 5 | ~~`nepali_date_converter` anchors on two clocks~~ **DONE 09-29**: `rdp_common_app/utils/bs_boundaries.py` now reads today from a fixed NPT (UTC+5:45) offset via `bs_today()`, not `datetime.date.today()`. **Uncommitted** — that repo has someone else's WIP in the tree | dev: commit there |
| 6 | ~~OT pays 0 unless "Measure from Attendance" is pressed~~ **DONE 09-29**: measures on submit (for a past day) and in a `daily_long` job, over rows never measured only — `hr/overtime_settlement.py` | dev |
| 7 | ~~OT / late-fine constants 30 days / 8 h~~ **DONE 09-29**: `Rate: Days per Month` / `Rate: Hours per Day` on the Salary Component, seeded 30 / 8 — `patches/setup_ot_rate_fields.py` | dev |
| 8 | ~~Tea paid on worked holidays~~ **DONE 09-29**: `Pay on Holiday` (Pay / Do Not Pay) on the Salary Component, seeded `Pay` so nothing moves on migrate — `patches/setup_pay_on_holiday_field.py`. **HR still has to set Tea to `Do Not Pay`** to match the sheet | HR |
| 9 | ~~"Excuse late"~~ **DONE 09-29**: `Late Excused` + mandatory reason on Attendance; drops the fine and restores a late-demoted Half Day to Present, but never one short hours earned — `patches/setup_late_excuse.py` | dev |
| 10 | Shift Request approvers: only 2/292 have one | user: who approves per company |
| 11 | NGN 7–3 staff list | HR |
| 12 | NGK/GLMI/GEPL/SGU have no Allowance Category (no tea/meal) | HR: rates |
| 13 | 73 NGI days wrongly Absent under paid Bhadra slips (avinas1 test data) | decide |
| 14 | 51 NGG people unmarked on 28 Aug (Janai Purnima removed per official sheet) | HR |
| 15 | Scheduler still disabled on the **dell box** avinas1. Cleared to enable — checked 09-29 after migrating: stock `allocate_earned_leaves` is now `stopped=1` (no double credit), and every job would be a no-op on that site's data (0 checkins, no shift with auto attendance, 0 leave policy assignments, 0 CBMS bills/configs, no outgoing email account). `bench --site avinas1 enable-scheduler` — blocked for Claude by the auto-mode classifier, run it by hand | dev |
| 16 | Accountant: tax figures; does women's rebate also cut SST?; SST split method; TDS 25th / SSF 15th deadlines | accountant |
| 17 | Functional: 292/292 device IDs missing; bank a/c numbers corrupted to `1.01E+12`; categories/cost centres | functional team |
| 18 | API key for demo-nggroup was pasted in chat → regenerate it | user |
| 19 | ~~avinas1 on the dell box was never migrated~~ **DONE 09-29**: migrated (DB backed up `20260929_105437` first). Every HR patch applied, `duplicate_threshold_seconds` created, and `test_attendance_pipeline` went from 7 errors to 12/12 passing — those failures were the schema gap, nothing else | dev |
| 20 | **The dell box avinas1 is not the HR/payroll test site** — it holds 265 active employees and nothing else HR: 0 Attendance, 0 Employee Checkin, 0 Salary Slip, 0 Salary Structure Assignment, 0 Overtime Sheet, 0 Leave Allocation. The "58 slips checked" / "127 days re-marked" dataset is the laptop site (`/home/sijan/frappe-15`). Its only attendance-driven Salary Components are Daily Wage and Overtime — there is **no Tea, Meal or Late Fine component**, so the meal rule (#8 of the built table) and `Pay on Holiday` have nothing to sit on until those are created. Any real verification of pay has to run on the laptop site or a restore of it | dev |

## Gotchas learned
- Test scripts against a site: stub `frappe.db.commit` (reload_doc / DDL commit mid-test and leak data); keep `frappe.msgprint` raising when `raise_exception` is set.
- With `bench start` running, redis caches develop's hooks — scripts importing a worktree must bypass `app_hooks` cache.
- HRMS keeps a draft slip's saved `leave_without_pay`; re-validating an old slip is not a fresh computation.
- HRMS reads one holiday list per person; Shift Type Holiday List must stay blank (overrides the employee's, kills Teej).
- rdp_common_app installs after this app → its Salary Slip class override wins; extend slips via doc_events.
