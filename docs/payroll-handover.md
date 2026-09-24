# Payroll and HRMS — handover to the next session

Written 2026-09-24. Read this before touching payroll. It exists so the next
session starts from where this one ended instead of rediscovering it, and so it
does not repeat the mistakes listed in §6.

---

## 1. Resume here

**The build is finished and proven on the test site. It is not deployed, and it
cannot go live until the client fills in employee data that only they have.**

First action, unless the user says otherwise: nothing in the code. The blocking
item is data — see §8. If the user asks "what's left", answer from §8, not from
memory, and re-verify with the queries in §5 first; the counts move as HR fills
things in.

---

## 2. How to work here

Bench root on *this* machine is `/home/sijan/frappe-15` (the CLAUDE.md in the
repo describes the dell box, `/home/dell/frappe-v15` — different machine).

```bash
cd /home/sijan/frappe-15
bench --site avinas1 mariadb -e "SELECT ..."     # read anything
bench --site avinas1 console                      # for private helpers
```

Sites: **`avinas1` is the payroll test site** — everything below was built and
proven there. `nepalgas` is the default site in common_site_config and carries
an earlier copy of the same work. `ng-group` is the live site, reachable
read-only by a user-supplied API token, no SSH from here.

Gotchas that cost time before:

- A standalone script must run from `/home/sijan/frappe-15/sites` with
  `/home/sijan/frappe-15/env/bin/python`, or `frappe.connect()` fails on the log
  path. Never from the bench root.
- `bench execute` runs under RestrictedPython and rejects any name starting with
  `_`. Use `bench console` for a private helper.
- Redis is often down here: stub `frappe.enqueue`, `enqueue_doc`,
  `publish_realtime` and `publish_progress` before running a Payroll Entry in a
  script, then call `create_salary_slips_for_employees` directly — submitting the
  entry alone creates 0 slips when the queue is stubbed.
- The employee category field is `custom_employee_category`, not
  `employee_category`. Same for `custom_allowance_category`.

---

## 3. Code state

Everything is on **`origin/develop`** as of 2026-09-24 (tip `ddfa626`, a merge
someone else pushed that carries all of it). Working tree clean. Nothing is
waiting to be pushed.

| App | State |
|---|---|
| `avinashgroup_app` | All payroll/HR work merged to develop and pushed. |
| `rdp_common_app` | `090a069` — removed a `patches.txt` line that broke every `bench migrate`. Also `81dd7a2`, the BS salary-slip fix. |
| `hrms` | **Pinned to v15.49.2.** Do not bump it casually; the BS slip work was fixed against this version. |

**Live still needs `git pull`, `bench migrate`, and a restart.** Nothing has run
on ng-group.

---

## 4. What was built

| File | What it is |
|---|---|
| `hr/year_setup.py` | One call puts a whole fiscal year in place per company: holiday lists, shifts, categories, leave policies, cost centres, periods, slabs. Safe to re-run. Holds the FESTIVALS table. |
| `hr/shift_day.py` | The single measurement of a working day — per-day shift resolution, late minutes, OT to the nearest half hour, eligibility. Both reports and the OT settlement use it, which is why they cannot disagree. |
| `hr/leave_ceiling.py` | Refuses an allocation that would take the year past the policy's figure. Carry-forward excluded. |
| `hr/overtime*.py`, `shift_change.py`, `statutory_leave.py`, `holiday_lists.py` | Overtime Sheet, shift requests splitting standing assignments, maternity/paternity, holiday bulk update. |
| `payroll/attendance_allowance.py` | The engine: tea, meal, overtime, late fine, daily wage → Payroll Adjustment rows. Condition types, units, rate basis, the category→employee→component rate chain. |
| `payroll/income_tax.py` | FY 83/84 slabs + the per-slip override, hooked on Salary Slip validate. |
| `payroll/advance_recovery.py` | Instalments: min(instalment, outstanding), referenced back to the Employee Advance. |
| `payroll/onboarding.py` | Reads a company's own Excel salary sheet and builds components, structure, employee pay inputs and assignments. PROFILES per company; the 21-component catalogue lives here. |
| `payroll/hr_journal.py` | JV Type + Document No on HR journals, and the cost-centre → expense-account routing (547101 O/O, 547102 S/D, 547103 F/P). |
| Doctypes | Dashain Bonus, Salary Revision, Overtime Sheet, Payroll Adjustment, Allowance Category, Employee Category. |
| Reports | Monthly Attendance BS, Yearly Leave Details BS. |

---

## 5. Verified state of avinas1 — with the query to re-check it

Run this first; the numbers move as HR fills data in.

```sql
select 'active employees' k, count(*) v from tabEmployee where status='Active'
union all select 'no device id', count(*) from tabEmployee where status='Active' and ifnull(attendance_device_id,'')=''
union all select 'no employee category', count(*) from tabEmployee where status='Active' and ifnull(custom_employee_category,'')=''
union all select 'no default shift', count(*) from tabEmployee where status='Active' and ifnull(default_shift,'')=''
union all select 'no cost centre', count(*) from tabEmployee where status='Active' and ifnull(payroll_cost_center,'')=''
union all select 'salary assignments 83/84', count(*) from `tabSalary Structure Assignment` where docstatus=1 and from_date='2026-07-17'
union all select 'assignments missing payable ac', count(*) from `tabSalary Structure Assignment` where docstatus=1 and ifnull(payroll_payable_account,'')=''
union all select 'leave allocations 83/84', count(*) from `tabLeave Allocation` where docstatus=1 and from_date>='2026-07-17'
union all select 'component-account rows', count(*) from `tabSalary Component Account`;
```

As at 2026-09-23: 292 active · **292 no device id** · 179 no category · 77 no
shift · 171 no cost centre · 205 assignments · 0 missing payable account · 584
allocations · 146 component-account rows.

Also in place: 14 holiday lists (52 Saturdays + 10 festivals, 11 on the women's,
no duplicates, no festival on a Saturday), 10 shift types, 7 payroll periods,
7 tax slabs, 5 salary structures, 7 allowance categories, 28 cost centres.

**Test data on avinas1 that is not real:** 10,816 checkins tagged
`device_id='TEST-DEVICE'`, ~5,811 attendance rows, 87 submitted Bhadra slips and
their journal. Clear these before the site is used for anything real, and filter
every delete — a blanket DELETE once cost 357k rows on another site.

---

## 6. Do not redo — and do not repeat

**Settled. Do not re-litigate:**

- Payslip parity is **proven** against the companies' own Falgun sheets:
  NGI 85/87 to the paisa (the 2 exceptions are hand-typed sheet rows — one
  inconsistent SSF, one part-month worker prorated by hand), NGN 66/66,
  NGK 19/19, NGG 27/28.
- The full chain ran end to end on avinas1 for Bhadra 2083: 87 slips, gross
  3,196,168.49, deductions 449,886.46, net 2,746,282.03, journal balanced with
  F/P 1,729,975.70, O/O 998,139.46, S/D 468,053.33, SSF Payable 415,278.61,
  TDS 5,926.29.
- Pay is a **dated fact**. A rise is a new Salary Structure Assignment from the
  first day of a BS month, never an edit. Decided, built, documented.
- Voucher numbering, the BS calendar helpers and the JV Type requirement are
  other people's settled decisions. Don't redesign them.

**Mistakes this session made. Don't repeat them:**

- I claimed "nothing checked that an allowance category belongs to the right
  company" and wrote a duplicate `hr/employee_tags.py`. The check already existed
  in `allowance_category.validate_employee_category`. **Grep before building a
  guard.**
- I documented that each Shift Type should point at a holiday list. It must stay
  **blank** — see §7. Caught only by reading the HRMS source.
- I reported ~45 unpushed commits from memory; it was 3, and now 0. **Check
  `git log origin/develop..develop`, don't recall it.**
- Build sources left in `/tmp` were wiped between sessions. Anything worth
  keeping goes in the repo or the scratchpad, and gets committed the same turn.

---

## 7. Product traps — each one is silent, not loud

| Trap | What happens | Source |
|---|---|---|
| **Shift Type → Holiday List** | The shift's list *overrides* the employee's. Filling it deletes Teej for all 22 women, who carry it on their own list alone. Ours are all blank; keep them blank. | `hrms/hr/doctype/shift_type/shift_type.py:333` |
| **Late Arrival Cutoff Time** | Self-filled with a clock time once and turned 2,423 of 2,808 days into Half Day. The rule now ignores a cutoff ≤ shift start and the field is cleared on create, but the root cause in Frappe was never pinned. A wave of half days is always this. | `biometric/attendance_override.py` |
| **Blank payroll payable account on an assignment** | HRMS drops the employee from the run. No error, just fewer slips. | — |
| **`depends_on_payment_days` on a structure row** | Refills from the component when the row is written. Set it on the component, not the row. Both SSF components must carry 0 or the amount prorates twice and HRMS refuses. | `payroll/onboarding.py` COMPONENTS |
| **Auto-attendance skips holidays** | 48 Saturday punches at NGI produced nothing; for Plant staff that is paid overtime lost. Build those days with the repair tool, or see the decision in §8. | `shift_type.py:336` |
| **Amending a salary structure** | Changes nothing until employees are reassigned — pay flows through the assignment. | — |
| **One-off earnings** | Need `deduct_full_tax_on_selected_payroll_date`, or the tax spreads over the year (6 instead of 70.69). | — |
| **HR journals** | Need `custom_p_type` (JV Type) and `custom_document_no` or they will not save. | `payroll/hr_journal.py` |

---

## 8. Open items — none of these are yours to decide

**Client / HR data (blocking go-live).** Numbers as at 2026-09-23:

| Gap | Count | Consequence |
|---|---|---|
| Attendance Device ID | **292 of 292** | No punch reaches a person. Nothing works. |
| Employee Category | 179 | Never paid overtime |
| Payroll Cost Center | 171 | Journal can't split O/O · S/D · F/P |
| Allowance Category (NGI + NGN only) | 42 | No tea |
| Default Shift | 77 | Lateness unmeasurable |
| No salary assignment | 87 | Absent from every run — NGG 25, NGI 20, NGK 19, GLMI 11, NGN 11, GEPL 1 |

**Accountant sign-offs:** the 146 component→account rows are proposals; Staff
Advance is typed Payable on 6 companies and must be Receivable; the payroll
payable accounts whose Account Type was cleared need confirming; 547101 "O/O"
may want a readable name.

**Client decisions:**

- Tick `mark_auto_attendance_on_holidays` on the shifts? It makes holiday punches
  produce Present automatically (proven in `test_shift_type.py:356`) — but a
  Present row on a holiday also earns a day of tea, which the Excel sheet never
  paid. Per company, their call.
- Which NGN sales staff work 7–3 vs 9–5. Only the billing desk was identifiable:
  NGN-EMP-00013, NGN-EMP-00003, NGN-EMP-00004.
- Teej for 3 staff whose gender is "Other" or "Prefer not to say" (NGG, NGK, NGI
  one each) — they inherit the common list, so no Teej.
- GLMI, GEPL and SGU have no salary sheet, so no structure and no payroll.

---

## 9. Go-live runbook

1. Fill the §8 data gaps on the live site. Nothing else matters until this is done.
2. Get the accountant's sign-off on the account mapping and the Staff Advance type.
3. On ng-group: `git pull`, `bench migrate`, restart. (Watch memory — that box
   OOMs on over-provisioned gunicorn workers; 4 workers + `--max-requests 500`.)
4. **Verify the Employee Category data on live.** It was inverted for 63 of 80
   NGI staff on the first import and had to be rebuilt from the client's workbook.
5. Re-enable the scheduled jobs stopped since 2026-07-28 (attendance marking
   among them) — infra checks stay green because they filter `stopped=0`.
6. Run one company for one month in draft, compare against their Excel sheet
   before submitting anything.
7. Rollback if the first run is wrong: cancel in reverse order — bank entry,
   journal, slips, payroll entry.

---

## 10. Documentation

| File | For whom | State |
|---|---|---|
| `docs/payroll-documentation.html` | The client's staff and QA | **Current.** 36 articles: setup path in dependency order, daily operations, the monthly run, calculation reference, 52 test cases + 8 required refusals. Published at https://claude.ai/artifact/YJx4RGJC8TarifLWeJhKNd |
| `docs/payroll-handover.md` | The next session | This file. |
| `docs/hr-decisions/` | Everyone | Raw client minutes — 2026-09-15 policy meeting, leave and holiday answers. The authority when a policy question comes up. |
| `docs/payroll-ngi.md` | Ops | The NGI month-end runbook. Still useful. |
| `docs/hrms-attendance-handoff.md` | — | Superseded by this file and the site. |
| `docs/payroll-manual.html`, `hr-payroll-handbook.html`, `payroll-qa-plan.html` | — | Superseded by `payroll-documentation.html`. They overlap it; the user has not yet said to delete them. **Ask before deleting.** |

Policy decisions of record: 33 days leave a year, sandwich leave on, encashment
at FY end, Teej women-only, no optional holidays, per-company calendars
(2026-09-15); the leave year's total is a ceiling but the monthly shape is free,
Dashain 5 days and Tihar 3 (2026-09-22).
