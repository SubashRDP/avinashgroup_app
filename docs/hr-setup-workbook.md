# HR & Payroll setup workbook

Point a session at this file: **"read `docs/hr-setup-workbook.md`"**.
Written 2026-08-27 for site `nepalgas`, HRMS **v15.49.2** (pinned).

Companion docs:
- `docs/leave-management.md` — what each leave field *means*
- `docs/hrms-attendance-handoff.md` — how the attendance pipeline works

---

## How to use this

Twenty steps in four parts. **Do them in order** — each depends on the one
before, and skipping ahead produces silent wrong answers rather than errors.

Every step has the same shape:

> **Where** the screen is · **What** to type · **Why** it matters · **Check**
> it worked before moving on

Repeat Parts A–C **per company**. Seven exist; NGI is the biggest and the one
to prove the process on.

| Company | Active staff |
|---|---|
| Nepal Gas Udhyog Pvt. Ltd. | 107 |
| Nepal Gas Udhyog (Narayani) Pvt. Ltd. | 77 |
| Nepal Gas Udhyog (Gandaki) Pvt. Ltd. | 55 |
| Nepal Gas Udhyog (Karnali) Pvt. Ltd. | 44 |
| Grihalaxmi Metal Industries Pvt. Ltd | 11 |
| Grishma Enterprises Pvt. Ltd. | 1 |
| Sambriddhi Gas Udhyog Pvt. Ltd. | 0 |

**The year everything hangs off:** Fiscal Year `83/84` = **2026-07-17 →
2027-07-16**. Type those AD dates wherever a date is asked for; the books are
BS but Frappe stores AD.

Running the checks: from `/home/sijan/frappe-15/sites`, use
`/home/sijan/frappe-15/env/bin/python`, or `bench --site nepalgas console`.

---

# Part A — Foundations

## Step 1 · Holiday List

**Where** `/app/holiday-list/new` — one per company.

| Field | Value |
|---|---|
| Holiday List Name | `NGI 83/84` |
| From Date | `2026-07-17` |
| To Date | `2027-07-16` |
| Weekly Off | `Saturday` |

Click **Get Weekly Off Dates** (fills all 52 Saturdays), then add each festival
as a row in the Holidays table — Dashain, Tihar, Chhath, and the rest.

**Why** Everything downstream reads this. Leave day-counts subtract holidays,
auto-attendance decides what is a working day, and payroll's payment-days
calculation uses it.

**Check** `total_holidays` should be roughly 52 + your festival count.

```sql
SELECT name, from_date, to_date, total_holidays FROM `tabHoliday List`;
```

> ⚠️ The dates must cover the **whole** leave year. A short list makes days
> outside it count as working days, silently.

---

## Step 2 · Company default holiday list

**Where** `/app/company/Nepal Gas Udhyog Pvt. Ltd.` → **Details** tab →
**Default Holiday List** → `NGI 83/84` → Save.

**Why** An employee with a blank `holiday_list` inherits the company's
(`erpnext/setup/doctype/employee/employee.py:276`). Setting it here covers all
107 without touching a single Employee record — and next year you re-point one
field instead of 107.

**Check** an employee with no list of their own resolves to the company's:

```python
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
get_holiday_list_for_employee("NGI-EMP-00006")   # -> 'NGI 83/84'
```

> The field is normally hidden by a Property Setter. It was deleted on
> 2026-08-27 to expose it; a `bench migrate` with `sync_on_migrate` may restore
> the hiding. If it vanishes, set the value from the console instead.

---

## Step 3 · Employee Grade, Department, Designation *(optional, do it if entitlements differ)*

**Where** `/app/employee-grade`, `/app/department`, `/app/designation`

**Why** All 299 employees currently have these **blank**. That is fine for one
policy covering everyone, and it is the *only* thing blocking per-grade
entitlements — the Leave Control Panel and Salary Structure Assignment both
filter on them.

**Skip this** if every employee gets the same leave and the same salary
structure. Come back to it the day they do not.

---

# Part B — Attendance

## Step 4 · Shift Type

**Where** `/app/shift-type/new` — three shifts, all serving all seven companies.

| | Morning | Day | Evening |
|---|---|---|---|
| Start Time | 06:00 | 09:00 | **12:00** |
| End Time | 14:00 | 17:00 | 20:00 |

On **every** shift, set:

| Field | Value |
|---|---|
| Enable Auto Attendance | ✅ |
| Holiday List | `NGI 83/84` |
| Determine Check-in and Check-out | **Strictly based on Log Type in Employee Checkin** |
| Working Hours Threshold for Half Day | `4` |
| Working Hours Threshold for Absent | `2` |
| Enable Entry Grace Period | ✅, Late Entry Grace Period `15` |
| Enable Exit Grace Period | ✅, Early Exit Grace Period `15` |
| Process Attendance After | your go-live date |
| Last Sync of Checkin | leave blank until punches flow |

**Why** Without `enable_auto_attendance` no Attendance rows are ever created
from punches, and the whole pipeline is inert.

**Check**

```sql
SELECT name, start_time, end_time, enable_auto_attendance,
       determine_check_in_and_check_out, working_hours_threshold_for_half_day
FROM `tabShift Type`;
```

> ⚠️ **Evening starts at 12:00, not 00:00.** It was wrong once already, and a
> midnight start makes every evening punch read as impossibly late.
>
> ⚠️ **Leave "Late Entry Grace Period" cutoffs empty of wall-clock times.** That
> rule forces Half Day + Leave Without Pay, i.e. it docks pay.
>
> ⚠️ **No genuine night shift.** `get_day_checkins` slices on the calendar day,
> so a 20:00→04:00 shift splits across two days, both labelled IN, both zero
> hours. All three shifts above are daytime, so this is dormant — not fixed.

---

## Step 5 · Assign shifts to employees

**Where** either

- `/app/employee/<id>` → **Default Shift** — the employee's usual shift, or
- `/app/shift-assignment/new` — a dated assignment that overrides it

**Why** A punch from an employee with no shift is never picked up by
auto-attendance: the checkin has no `shift`, so the job does not select it.
There is a majority-vote fallback in the custom pipeline, but do not rely on it.

**Check** nobody active is left without one:

```sql
SELECT COUNT(*) FROM tabEmployee
WHERE status='Active' AND (default_shift IS NULL OR default_shift='');
```

---

## Step 6 · Biometric Device

**Where** `/app/biometric-device/new` — one row per physical device.

| Field | Value |
|---|---|
| Device Serial | the serial the K40 bridge sends |
| Company | the device's company |
| Enabled | ✅ |
| Duplicate Threshold Seconds | `60` |

**Why** `assert_known_device()` (`biometric/utils.py:14`) **rejects every punch**
from a serial that is not registered and enabled. Zero devices means zero
attendance, no matter what else is configured.

**Check** `SELECT device_serial, enabled FROM \`tabBiometric Device\`;`

---

## Step 7 · Employee device IDs

**Where** `/app/employee/<id>` → **Attendance Device ID**

**Why** The punch carries only a number. Without this mapping the bridge cannot
tell which Employee a punch belongs to.

**Do it in bulk**: Employee list → filter Company → select all → **Edit** →
`attendance_device_id`. Or a Data Import keyed on employee name.

**Check**

```sql
SELECT COUNT(*) missing FROM tabEmployee
WHERE status='Active' AND (attendance_device_id IS NULL OR attendance_device_id='');
```

Target: **0**.

---

## Step 8 · Restart the stopped scheduled jobs

**Where** `/app/scheduled-job-type` → filter `stopped = 1`

Three have been off since 2026-07-28:

| Job | Restart? |
|---|---|
| `attendance_self_heal.heal_unlinked_checkins` | **Yes.** While it is off the repair layer does not run at all — not "runs and skips" |
| `heartbeat.check_bridge_heartbeats` | **Yes.** Otherwise a dead bridge is silent |
| `CBMS.scheduler.retry_failed_cbms_syncs` | **Ask first.** It files bills to the IRD irreversibly, and it ignores `enable_from_date` |

**Check** `SELECT method, stopped, last_execution FROM \`tabScheduled Job Type\`;`

> The scheduler on this box runs irregularly — jobs can show `stopped=0` and
> still not have run for days. Check `last_execution`, not just the flag.

---

# Part C — Leave

Full field-by-field reference: `docs/leave-management.md`.

## Step 9 · Leave Type

**Where** `/app/leave-type/new` — one per kind of leave.

A starting set. **Confirm the day counts against Avinash Group's actual HR
policy** — these are the Labour Act 2074 shape, not your policy.

| Leave Type | is_lwp | is_carry_forward | max_leaves_allowed | Notes |
|---|---|---|---|---|
| Home / Annual | 0 | 1 | 0 | the accruing one; see Step 12 |
| Sick | 0 | 0 | 0 | consider `allow_negative` |
| Casual | 0 | 0 | 0 | consider `max_continuous_days_allowed = 3` |
| Mourning (Kriya) | 0 | 0 | 0 | |
| **Leave Without Pay** | **1** | 0 | 0 | **required — see below** |

**Why the LWP type is not optional:** the attendance half-day rule resolves to
Half Day + Leave Without Pay. With no LWP Leave Type there is nothing for it to
resolve to.

**Set `max_leaves_allowed = 0` on all of them** and let the Leave Policy carry
the number. Two fields both holding "6" for different reasons is the single
biggest source of confusion in this module.

**Check** `SELECT name, is_lwp, is_carry_forward, max_leaves_allowed FROM \`tabLeave Type\`;`

---

## Step 10 · Leave Period

**Where** `/app/leave-period/new` — one per company.

| Field | Value |
|---|---|
| From Date | `2026-07-17` |
| To Date | `2027-07-16` |
| Company | Nepal Gas Udhyog Pvt. Ltd. |
| Is Active | ✅ |

**Why** `max_leaves_allowed` is enforced *per leave period*. With no period
covering the dates, that cumulative check finds nothing.

> ⚠️ **This is where it went wrong last time.** The dates were left at their
> defaults (`2026-05-12 → 2027-06-09`), and every allocation generated from the
> policy inherited them — expiring everyone's leave 37 days early. **Type the
> fiscal-year dates.**

**Check** they match the Fiscal Year exactly:

```sql
SELECT lp.name, lp.from_date, lp.to_date, fy.year_start_date, fy.year_end_date
FROM `tabLeave Period` lp, `tabFiscal Year` fy WHERE fy.name='83/84';
```

---

## Step 11 · Leave Policy

**Where** `/app/leave-policy/new` — one per entitlement band.

Add a row per leave type with its **annual allocation in days**:

```
Leave Policy: NGI Staff 83/84
   Home / Annual   18
   Sick            12
   Casual           6
   Mourning        13
```

Leave Without Pay gets **no row** — it cannot be allocated.

**Why** This is the only place the day counts live. It is also the figure
earned-leave accrual divides by 12.

**Check** `SELECT parent, leave_type, annual_allocation FROM \`tabLeave Policy Detail\`;`

---

## Step 12 · Earned leave *(only if Home/Annual should accrue monthly)*

Set on the **Home / Annual** Leave Type:

| Field | Value |
|---|---|
| Is Earned Leave | ✅ |
| Earned Leave Frequency | **Monthly** |
| Allocate on Day | **Last Day** |
| Rounding | blank (exact) or `0.5` |

**Why** Staff earn leave by working rather than receiving a year of it on day
one — which also stops a mid-year leaver taking a full year's entitlement.

> ⚠️ **Stock HRMS accrues on Gregorian months** and would credit on 31 August
> rather than the last day of Shrawan — every credit 14–17 days late, and the
> **twelfth credit never happens at all** (the allocation has already expired
> when the job looks), so everyone silently gets 11 of 12 days a year.
>
> The BS replacement is written: `avinashgroup_app/hr/utils.py`. To switch over,
> stop `hrms.hr.utils.allocate_earned_leaves` and register
> `avinashgroup_app.hr.utils.allocate_earned_leaves_bs` under
> `scheduler_events` → `daily_long`. Running both double-credits.
>
> Preview a year's real credit dates before committing:
> ```python
> from avinashgroup_app.hr.utils import preview_accrual_dates
> preview_accrual_dates("2026-07-17", "2027-07-16")
> ```
>
> ⚠️ Use **Monthly** only. Quarterly/Half-Yearly/Yearly share a frequency check
> that reads inverted in 15.49.2.

---

## Step 13 · Allocate leave to everyone

**Where** `/app/leave-control-panel`

**Policy path** — several leave types, entitlements from the policy:

| Field | Value |
|---|---|
| Company | Nepal Gas Udhyog Pvt. Ltd. |
| Allocate Based On Leave Policy | ✅ |
| Leave Policy | NGI Staff 83/84 |
| Dates Based On | **Leave Period** |
| Leave Period | your Step 10 record |

**Direct path** — one leave type, same days for everyone, skips Steps 10–11:

| Field | Value |
|---|---|
| Allocate Based On Leave Policy | ❌ untick |
| Leave Type / New Leaves Allocated | e.g. Casual / 6 |
| Dates Based On | **Custom Range** |
| From / To | `2026-07-17` / `2027-07-16` |

Preview the employee list, confirm the count, then **Allocate Leaves**.

**Why** It creates every allocation in one action and **skips anyone who
already has one** for that period, so it is safe to re-run after new hires.

**Check** every active employee has a balance, and the dates are right:

```sql
SELECT from_date, to_date, leave_type, new_leaves_allocated, COUNT(*)
FROM `tabLeave Allocation` WHERE docstatus=1
GROUP BY from_date, to_date, leave_type, new_leaves_allocated;
```

Every row must read `2026-07-17 / 2027-07-16`. If not, cancel and redo Step 10.

---

## Step 14 · Prove one balance end to end

Pick one employee and walk the whole chain:

```python
from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on
get_leave_balance_on("NGI-EMP-00006", "Casual", "2026-08-27")
```

Then file a one-day Leave Application for them, approve it through the
**Leave Application Approval Workflow**, and confirm the balance drops by one
and a `-1` row appears in Leave Ledger Entry.

**Why** This is the only check that proves allocation, workflow, ledger and
balance all agree. Do it before rolling out to 295 people.

---

# Part D — Payroll

Everything below is **greenfield** — the site has none of it. `BSSalarySlip`
(rdp_common_app) and the attendance-allowance engine
(`payroll/attendance_allowance.py`) are built but unusable until these exist.

## Step 15 · Payroll Settings

**Where** `/app/payroll-settings`

Decide and record:

- **Payroll based on** — `Attendance` or `Leave`. Attendance is what this
  pipeline feeds
- **Consider unmarked attendance as** — Present or Absent. This one silently
  changes everybody's pay; pick deliberately
- Email salary slips to employees — off until the numbers are trusted

---

## Step 16 · Payroll Period

**Where** `/app/payroll-period/new` — per company.

| Field | Value |
|---|---|
| Start Date | `2026-07-17` |
| End Date | `2027-07-16` |
| Company | Nepal Gas Udhyog Pvt. Ltd. |

**Why** Income tax is computed across the payroll period. No period, no tax
calculation.

---

## Step 17 · Income Tax Slab

**Where** `/app/income-tax-slab/new`

| Field | Value |
|---|---|
| Effective from | `2026-07-17` |
| Company / Currency | NGI / NPR |
| Taxable Salary Slabs | the FY 2083/84 bands |

**Get the bands and the SSF treatment from your accountant or the IRD
publication for 2083/84 — do not copy last year's, and do not take them from
this document.** Rates, thresholds, the married/unmarried split and the SSF
1%/10%/20% treatment all change between years.

Add allowable deductions (SSF, CIT, insurance) as **Salary Components** with
`variable_based_on_taxable_salary` or explicit exemption rows.

---

## Step 18 · Salary Component

**Where** `/app/salary-component/new`

Earnings: Basic, Grade/Allowance, Dashain Bonus, Overtime, Leave Encashment.
Deductions: SSF Employee, CIT, Advance Recovery, Income Tax.

For **attendance-driven** components (overtime, holiday allowance) tick
`custom_is_attendance_driven` and set `custom_summary_group` — that is what the
allowance engine and the Monthly Attendance BS grid read.

For encashment, the Leave Type's `earning_component` must point at a component
here, or Leave Encashment throws.

---

## Step 19 · Salary Structure + Assignment

**Where** `/app/salary-structure/new`, then **Assign Salary Structure**

On the structure set `leave_encashment_amount_per_day` — Leave Encashment
multiplies by it and produces 0 without it.

**Why the assignment matters:** it carries the employee's **base**. Nothing —
not a salary slip, not an encashment — works without one. This is what today's
`No Salary Structure assigned to Employee` error is.

**Check**

```sql
SELECT COUNT(*) FROM `tabSalary Structure Assignment` WHERE docstatus=1;
```

Target: one per active employee.

---

## Step 20 · First payroll run

1. `/app/payroll-entry/new` — company, posting date, payroll period
2. **Get Employees** → confirm the count
3. **Create Salary Slips** → they land as drafts
4. **Open three slips and check them by hand** — payment days against the
   attendance grid, LWP deductions, tax
5. Submit only when those three are right

**Check** against `Avinas Salary Statement`, which compares the current BS month
to the previous one — the report is already built and has been waiting on this.

---

# Order of operations, at a glance

```
A  1 Holiday List ──▶ 2 Company default ──▶ 3 Grades (optional)
                              │
B  4 Shift Type ──▶ 5 Shift assignment ──▶ 6 Biometric Device
                              │            7 Device IDs ──▶ 8 Restart jobs
                              │                                   │
                              │                          punches → Attendance
                              ▼                                   │
C  9 Leave Type ──▶ 10 Leave Period ──▶ 11 Leave Policy           │
                              │          12 Earned leave (opt)    │
                              ▼                                   │
                    13 Allocate ──▶ 14 Prove one balance          │
                                                                  ▼
D 15 Payroll Settings ─▶ 16 Payroll Period ─▶ 17 Tax Slab ─▶ 18 Components
                                     │
                    19 Structure + Assignment ──▶ 20 First payroll run
```

---

# The seven things that bite

1. **Saving is not granting.** A draft Leave Allocation showing 12 days gives a
   balance of zero. Only submit writes the ledger.
2. **`to_date` is an expiry date.** Whatever you type is the day leftover days
   are cancelled. An arbitrary end date silently shortens the entitlement.
3. **Leave Period dates are inherited by every allocation.** Get Step 10 right
   or redo Step 13.
4. **Carry-forward clamping is silent.** 10 new + 8 carried against a cap of 12
   becomes 12, and the other 6 evaporate with no message.
5. **The leave workflow only guards *spending*.** Allocation, expiry, encashment
   and compensatory requests all move the ledger without touching it.
6. **Attendance can dock pay with no Leave Application at all.** Auto-attendance
   marks Half Day → LWP directly on the Attendance row, and payroll reads
   attendance.
7. **Report scripts are cached per session.** After any report JS change,
   hard-refresh (Ctrl+Shift+R) or you are testing the old build.

# Bulk operations on this machine

Redis queue is configured on `:11000` but only `:6379` is running, so any script
doing many `delete_doc` / `insert` calls stalls retrying the queue. Stub it:

```python
frappe.enqueue = lambda *a, **k: None
frappe.enqueue_doc = lambda *a, **k: None
frappe.publish_realtime = lambda *a, **k: None
```

and run it under `nohup` rather than inline — these runs outlast a two-minute
tool timeout.
