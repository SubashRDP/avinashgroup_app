# HRMS / Attendance — session handoff

Point a new session at this file: **"read `docs/hrms-attendance-handoff.md`"**.
Written 2026-08-26. Branch `fix-roster-getlist`, 12 commits, **none pushed**.

---

## Environment (read this first — it is not what CLAUDE.md describes)

CLAUDE.md documents the *dell* box (`/home/dell/frappe-v15`, site `avinas1`).
**This machine is different:**

| | |
|---|---|
| Bench root | `/home/sijan/frappe-15` |
| Working site | **`nepalgas`** (also the `default_site`) |
| bench CLI | `/home/sijan/.local/bin/bench` |
| Framework python | `/home/sijan/frappe-15/env/bin/python` |
| Standalone scripts | run from `/home/sijan/frappe-15/sites`, never the bench root |

```bash
cd /home/sijan/frappe-15/sites && /home/sijan/frappe-15/env/bin/python - <<'PY'
import frappe
frappe.init(site='nepalgas', sites_path='/home/sijan/frappe-15/sites')
frappe.connect(); frappe.set_user("Administrator")
PY
```

**HRMS is pinned to v15.49.2** (detached HEAD) to match live. It was on 15.59.0.
Do not "upgrade" it back without asking. Three consequences that are true of
production right now:

- `attendance.py:194` has a typo — `self.haf_day_status = "Absent"`. Half Day with
  no leave record silently never sets `half_day_status`.
- `process_auto_attendance` runs **synchronously**, no error handling. A big batch
  times out and the exception vanishes.
- `mark_absent_for_half_day_dates` has no date ceiling; dates past the last sync
  can be flipped to Absent.

---

## The pipeline, in one picture

The bridge **pulls** from devices and **pushes** to the server. The server never
dials out. `hooks.py:11` registers an `iclock` ADMS page renderer, but **it is not
the live path** — it is an unused open door.

```
ZKTeco / Hikvision / HTMS  ──▶  K40 Bridge (Windows, on site)
                                     │ HTTPS + API key
        POST biometric.api.receive_attendance
                                     ▼
              assert_known_device()          utils.py:14   ← serial must exist + be enabled
                                     ▼
              process_attendance_records()   utils.py:48   ← group by (person, day), de-dup
                                     ▼
                          Employee Checkin                 ← last punch of the day forced to OUT
                                     ▼
              sync_day()                     attendance_sync.py:225
                                     ▼
                              Attendance                   ← the row payroll trusts
                                     ▼
              self-heal (hourly)             attendance_self_heal.py
```

### The iron rule
`sync_day()` may refresh a day's **numbers**. It may never create a row and never
change a **status**. Look at `refresh_attendance_values` — it unpacks HRMS's
`get_attendance()` into `_status, working_hours, ...` and **throws the status
away**. Decisions live only in `reconcile_employee_day()`, shared by Attendance
Fix and the self-heal job.

---

## What was built this session (12 commits)

| Commit | What |
|---|---|
| `3dd6816` | Roster 500 fix — `get_newargs` on the `frappe.client.get_list` override. Broke every frappe-ui client, incl. the HR mobile app |
| `f8b4817` | Cross-company punches (`allowed_employees` child table + optional per-row Device User ID); dropped 7 pull-model fields |
| `470a014` | De-dup window minutes → **seconds** (`duplicate_threshold_seconds`, Int, 60) + migration patch |
| `b45a357` | Midday attendance digest — one email per company, 3-sheet xlsx |
| `3f7b65a` | Digest follows the working calendar |
| `818b72b` | …but never skips a day's **data** — 3-day rolling window, all calendar days |
| `7e3ceb9` | **Repair from Check-ins** button on Attendance + the precision-convergence fix |
| `e5f46e7` | Attendance Fix: repair a whole shift **or** a named employee list |
| `6e100f8` | Monthly Attendance BS + Summary BS merged into one report, two views |
| `d56ef0f` | Charts, status chips, readable zeros |
| `013085c` | Both views agree on empty data; legibility pass |
| `a16797d` | Period resolver never throws — resolves and says what it assumed |

### Config applied to the site (not in git)
Three Shift Types switched on: `enable_auto_attendance=1`,
`determine_check_in_and_check_out="Strictly based on Log Type in Employee Checkin"`,
half-day `<4h`, absent `<2h`, late/early marking on with 15-min grace,
`auto_update_last_sync=1`. **Evening Shift start corrected 00:00 → 12:00.**
Late-arrival cutoffs **cleared** — they held wall-clock creation times, and that
rule forces Half Day + Leave Without Pay, so they would have docked pay.

Shifts are Morning 6–2, Day 9–5, Evening 12–8, and **three serve all seven
companies** — `custom_company` on Shift Type exists only to satisfy the naming
override; nothing validates it against the employee's company.

---

## Open blockers — nothing flows until these exist

| | Count | Note |
|---|---|---|
| Biometric Device | **0** | `assert_known_device()` rejects every punch without one |
| Employees with `attendance_device_id` | **0 of 299** | the punch carries only a number |
| Companies with `default_holiday_list` | **0 of 7** | the shift's list covers for it, badly |
| Employees with `default_shift` | 4 of 299 | majority-vote fallback covers it |
| **Scheduled jobs stopped since 2026-07-28** | **3** | see below |

### The stopped jobs — decision needed
`heal_unlinked_checkins` (hourly_long), `check_bridge_heartbeats` (hourly) and
`retry_failed_cbms_syncs` (*/5) are all `stopped=1`, last run 2026-07-28.
**Self-heal being off means the repair layer does not run at all** — not "runs and
skips". Not restarted: CBMS retry reports bills to the IRD irreversibly, so it is
the user's call. Restarting only the two attendance ones was offered.

---

## Gotchas found the hard way

- **`process_attendance_records` commits internally.** A test that ends in
  `frappe.db.rollback()` will *not* clean up. Delete explicitly and commit.
- **`Attendance.working_hours` is `decimal(21,1)`** on 15.49.2 — the DB rounds
  8.32 → 8.3. Comparing unrounded computed against rounded stored made every
  repair look like a change and never converge. Fixed by rounding to the field
  precision before compare *and* write.
- **`get_day_checkins` slices on the calendar day.** A genuine night shift
  (20:00→04:00) splits across two days, both labelled IN, both zero hours.
  Inert today — all three shifts are daytime. **Landmine.**
- **Frappe never drops columns.** Removed doctype fields leave their data behind;
  a renamed field needs a patch or the old value is silently reinterpreted.
- **Frappe Float columns are `NOT NULL`.** `SET col = NULL` throws; use 0.
- **Every `Hourly` / `Hourly Long` job fires at `0 * * * *`.** The digest runs at
  **13:10**, not 13:00, so it does not race the self-heal job it reports on.
- **Report scripts are cached per session.** After changing report JS, hard-refresh
  (Ctrl+Shift+R) or the new formatter never loads.

---

## Reports

Five custom HR/payroll reports, all Bikram Sambat native. `Monthly Attendance BS`
now carries a **View** filter (Detail = per day, Summary = per employee); the
standalone `Monthly Attendance Summary BS` is deleted — it had **never** worked
from the desk (its JS set `bs_year`, its Python required `fiscal_year`).

Others: `Work On Holiday BS`, `Yearly Leave Details BS`, `Avinas Salary Statement`.

---

## What is next

**Payroll is a bigger gap than attendance was.** Built but unusable:
`BSSalarySlip` (rdp_common_app) and the attendance-allowance engine
(`payroll/attendance_allowance.py`). Missing entirely:

- Payroll Period — **0**
- Income Tax Slab — **0** (FY 2083/84 Nepali bands + SSF rules go here)
- Salary Structure — **0**
- Salary Structure Assignment — **0**

Salary Component exists (7).

## Build log
Live page, updated as work lands:
<https://claude.ai/code/artifact/b3a815c3-4649-4942-b5f7-fdf7080edb2d>

---

## An employee asking for a different shift (2026-09-20)

Everyone holds one **open-ended Shift Assignment** from the start of the fiscal
year — that is what keeps attendance right when it is marked weeks later. It also
means a stock **Shift Request** can never be approved: ERPNext refuses a second
assignment overlapping the first, and all three shifts here overlap each other.

    NGI-EMP-00029 already has an active Shift Assignment HR-SHA-26-09-00108
    for some/all of these dates.

`avinashgroup_app/hr/shift_change.py` makes room for it, on `before_submit`:

    before      6 AM - 2 PM  Shrawan 1 ─────────────────────────▶ open
    approved    6 AM - 2 PM  Shrawan 1 ──▶ Oct 4
                12 PM - 8 PM              Oct 5 ─ Oct 7
                6 AM - 2 PM                        Oct 8 ──────▶ open
    cancelled   6 AM - 2 PM  Shrawan 1 ─────────────────────────▶ open

Cancelling the request joins the standing assignment back together.

**Temporary or permanent** is decided by the request's To Date:

| Request | Result |
|---|---|
| From 05 Oct, To 07 Oct | the new shift covers those three days and the old one resumes on the 8th |
| From 01 Oct, **To blank** | the old shift ends 30 Sep and the new one runs on — the permanent move |

Cancelling either one puts the old shift back the way it was.

A request for the shift the employee is already on is refused: HRMS only compares
against the Default Shift, which is empty for all 295 here, so "9-6 instead of
9-6" would otherwise split the assignment into three pointless pieces.

**The employee must have a Shift Request Approver** on their Employee record, or
HRMS refuses the approval with "Only Approvers can Approve this Request."

HR can still do the same thing directly in the **Roster** (`/hr/roster`), which
splits and rejoins assignments the same way.

---

## Two attendance rules from the policy meeting (2026-09-20)

**More than 2 hours late is a half day** (policy 1.2, no grace period).
`Shift Type → Half Day If Late By (Hours)`, default **2**, counted from that
shift's own start. On 6 AM - 2 PM: in at 07:59 stays Present, in at 08:01 becomes
a Half Day with Leave Without Pay against it, whatever the hours add up to. 0
turns the rule off for a shift.

This replaces having to type an absolute cutoff per shift. The old
`custom_late_arrival_cutoff_time` still applies where it is set and the earlier
of the two wins, but two shifts here had been saved with a stray 11:24:33 — on
12 PM - 8 PM that would have made **every** attendance a half day, since the
shift starts at 12:00. The patch clears cutoffs that can only be accidents (one
before its own shift start, or one carrying seconds).

**Coming to the office while on leave is a half day** (policy 3.4). HRMS forces
the status to On Leave from the approved leave application; if there is also a
punch, the day becomes a Half Day with `half_day_status = Present`, keeping the
leave type so payroll still deducts the leave half. No punch, and it stays a full
day of leave.

Both live in `biometric/attendance_override.py` and run on Attendance validate,
after HRMS's own checks.
