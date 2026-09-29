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
| Women's list | Employee save: Female → company's Women holiday list (Teej); others taken off it | `hr/womens_holiday_list.py` |
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
| 4 | Ashwin 2083 = 31 days; a server (dell box or ng-group?) showed 30 → old `nepali-datetime` there; fix `pip install nepali-datetime==1.0.8.5` + restart | dev, ask which server |
| 5 | `nepali_date_converter` anchors on two clocks (NPT vs server) → off-by-one after a UTC-evening restart; fix is in rdp_common_app (needs user OK) | user decision |
| 6 | OT pays 0 unless "Measure from Attendance" is pressed on the Overtime Sheet — offered to automate | user decision |
| 7 | OT / late-fine rates still use constants 30 days / 8 h — offered to move to the form | user decision |
| 8 | Tea is paid on worked holidays (sheet never did) — offered a "pay on holidays" field | user decision |
| 9 | "Excuse late" option (HR waives a late day) — offered | user decision |
| 10 | Shift Request approvers: only 2/292 have one | user: who approves per company |
| 11 | NGN 7–3 staff list | HR |
| 12 | NGK/GLMI/GEPL/SGU have no Allowance Category (no tea/meal) | HR: rates |
| 13 | 73 NGI days wrongly Absent under paid Bhadra slips (avinas1 test data) | decide |
| 14 | 51 NGG people unmarked on 28 Aug (Janai Purnima removed per official sheet) | HR |
| 15 | Scheduler disabled on avinas1 — auto attendance / accrual / replacement-leave jobs not running there | dev |
| 16 | Accountant: tax figures; does women's rebate also cut SST?; SST split method; TDS 25th / SSF 15th deadlines | accountant |
| 17 | Functional: 292/292 device IDs missing; bank a/c numbers corrupted to `1.01E+12`; categories/cost centres | functional team |
| 18 | API key for demo-nggroup was pasted in chat → regenerate it | user |

## Gotchas learned
- Test scripts against a site: stub `frappe.db.commit` (reload_doc / DDL commit mid-test and leak data); keep `frappe.msgprint` raising when `raise_exception` is set.
- With `bench start` running, redis caches develop's hooks — scripts importing a worktree must bypass `app_hooks` cache.
- HRMS keeps a draft slip's saved `leave_without_pay`; re-validating an old slip is not a fresh computation.
- HRMS reads one holiday list per person; Shift Type Holiday List must stay blank (overrides the employee's, kills Teej).
- rdp_common_app installs after this app → its Salary Slip class override wins; extend slips via doc_events.
