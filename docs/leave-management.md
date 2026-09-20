# Leave Management — how it works, field by field

Point a session at this file: **"read `docs/leave-management.md`"**.
Written 2026-08-27, against site `nepalgas`, HRMS **v15.49.2** (pinned — see
`docs/hrms-attendance-handoff.md` for why).

---

## The one thing to understand first

**Nobody has a leave balance stored anywhere.** There is no `balance` field on any
doctype. The balance is *derived* every time it is asked for, by adding up rows in
**Leave Ledger Entry**.

Everything else in this document exists to write rows into that ledger.

```
Leave Allocation  submitted  ──▶  ledger  +6
Leave Application submitted  ──▶  ledger  −2
Expiry (scheduler)           ──▶  ledger  −4
                                         ────
                              balance      0
```

Verified live on this site: Anil Shrestha's balance was `0.0` with a saved draft
allocation for 3 days, and `3.0` one second after it was submitted. The number on
the form grants nothing. **Submit is the moment days exist.**

---

## The chain

```
Leave Type            the RULES        Casual: paid, no carry forward, max 6
     │                                 ── one row for the whole company
     ▼
Leave Policy          the NUMBERS      Casual: 4 days/year
     │                                 ── one row per grade/band
     ▼
Leave Period          the YEAR         2026-07-17 → 2027-07-16
     │
     ▼
Leave Policy Assignment   employee + policy + period
     │  on submit, creates one allocation per leave type
     ▼
Leave Allocation      the GRANT        Anil, Casual, 3 days, this year
     │  on submit
     ▼
Leave Ledger Entry    the TRUTH        +3
     ▲
     │  on submit (−N)
Leave Application     the SPEND        Anil, 2 days off in Bhadra
```

Read it top-down as "policy becomes days". Read it bottom-up as "where did this
balance come from".

### Two shortcuts that skip layers

- **Casual-only setup**: skip Leave Policy and Leave Period entirely. Leave Control
  Panel with *Allocate Based On Leave Policy* **unticked** takes a leave type and a
  day count directly and creates allocations. This is the path in use on NGI.
- **Single employee**: create a Leave Allocation by hand. No policy, no assignment.

---

## Leave Type — the rules

One record per *kind* of leave. No employee, no dates, no per-person quantity.
It never grants anybody anything; it only constrains what allocations and
applications are allowed to do.

### Field reference

| Field | What it does | Where it bites |
|---|---|---|
| `max_leaves_allowed` | ceiling on days **granted** per leave period | Leave Policy refuses to save a bigger `annual_allocation`; Leave Allocation throws `OverAllocationError` when the period total exceeds it; earned-leave accrual stops at it. **0 = no limit** |
| `max_continuous_days_allowed` | ceiling on the length of **one unbroken absence** | Leave Application. Counts the whole adjacent chain, not just this application — Mon–Wed then Thu–Fri = 5, not 3+2. Draft applications count. **0 = no limit** |
| `applicable_after` | working days since joining before this leave can be used | Leave Application, on new joiners |
| `is_carry_forward` | unused days roll into next year instead of expiring | Leave Allocation `unused_leaves`. Without it, the scheduler writes a negative expiry entry at `to_date` |
| `maximum_carry_forwarded_leaves` | cap on how many days roll over | Leave Allocation |
| `expire_carry_forwarded_leaves_after_days` | carried days die this many days into the new year | scheduler |
| `is_lwp` | **unpaid** — payroll docks salary | Salary Slip. Cannot be allocated. Cannot be turned on while a live allocation exists |
| `is_ppl` + `fraction_of_daily_salary_per_leave` | partly paid; 0.5 = half a day's pay per day taken | Salary Slip. Mutually exclusive with `is_lwp`. Fraction must be 0–1 |
| `is_optional_leave` | festival leave the employee picks from the holiday list | Leave Application validates the date **is** an optional holiday in their list, and rejects anything else |
| `is_compensatory` | earned by working a holiday | not allocated by you — a **Compensatory Leave Request** creates/updates the allocation on submit. Mutually exclusive with `is_earned_leave` |
| `allow_negative` | balance may go below zero | Leave Application stops throwing on insufficient balance. Typical for sick leave |
| `allow_over_allocation` | allow granting more days than the allocation period is long | Leave Allocation: hard error becomes an orange warning. Only about **period length**, nothing to do with `max_leaves_allowed` |
| `include_holiday` | count holidays that fall inside the leave | Leave Application day count **and** Salary Slip. Off: Fri–Mon = 2 days. On: = 4 |
| `allow_encashment` | leftover days can be paid out as cash | unlocks Leave Encashment for this type |
| `earning_component` | Salary Component the payout books against | Leave Encashment throws without it |
| `max_encashable_leaves` | hard cap per encashment | Leave Encashment |
| `non_encashable_leaves` | days held back from the balance | Leave Encashment: balance 10, non-encashable 4 → 6 encashable |
| `is_earned_leave` | days **accrue** over the year instead of arriving upfront | balance starts at 0 and the daily scheduler tops it up. Requires a Leave Policy — without one there is no annual figure to divide, and the balance stays 0 forever with no error |
| `earned_leave_frequency` | Monthly / Quarterly / Half-Yearly / Yearly — the divisor (12/4/2/1) | scheduler |
| `rounding` | blank / 0.25 / 0.5 / 1.0 — tidies each instalment | scheduler. Rounds to **nearest**, so instalments may not sum to the annual figure; accrual then stops early at the cap |
| `allocate_on_day` | First Day / Last Day / Date of Joining — which day the instalment lands | scheduler |

### Combinations HRMS refuses

- `is_lwp` + `is_ppl` — "can either be without pay or partial pay"
- `is_compensatory` + `is_earned_leave` — one is request-driven, the other scheduler-driven
- turning on `is_lwp` while a live allocation exists for that type

### Earned leave, explained once

Leave paid like salary — a slice per month rather than the year upfront.

```
12 days/year, Monthly, Last Day

Shrawan 31  +1   balance 1
Bhadra 31   +1   balance 2
Ashwin 30   +1   balance 3      ← a 5-day request here is REJECTED
   ...
Ashar 31    +1   balance 12
```

The point is that nobody spends leave they have not yet worked for. The `+1` is
**credited** monthly; it does not limit how many days can be taken at once — five
accumulated days can all be taken together. Use `max_continuous_days_allowed` for
that.

⚠️ The frequency check in 15.49.2 (`hrms/hr/utils.py:526-531`) reads inverted for
Quarterly/Half-Yearly/Yearly — it fires when the month count is **not** a multiple
of 3/6/12. **Use Monthly.**

⚠️ `allocate_on_day = Date of Joining` silently skips months for anyone who joined
on the 31st. Prefer **Last Day**.

---

## Leave Policy — the numbers

A saved list of day counts, so you type the number once instead of 107 times.

```
Leave Policy "NGI Staff 83/84"
   Casual   4 days
   Sick    12 days
```

**Why it is separate from Leave Type:** different people get different amounts of
the *same* type. Leave Type has one `max_leaves_allowed` field and cannot hold both
"Staff: 18" and "Manager: 30". One policy per grade does.

**Leave Type is the speed limit; Leave Policy is the speed you drive.** Type says
"never more than 6", policy says "staff get 4". A policy row above the type's cap
is rejected on save.

> Recommendation: set `max_leaves_allowed = 0` and let the policy be the single
> place a number lives. Two fields both holding "6" for different reasons is the
> main source of confusion here.

`annual_allocation` is also the figure earned-leave accrual divides. No policy,
no accrual.

---

## Leave Period — the year

A date range, per company. `2026-07-17 → 2027-07-16` for FY 83/84.

Its impact is quieter than it looks: `max_leaves_allowed` is enforced **per leave
period**, so with no Leave Period covering the dates, that cumulative check finds
nothing and only the current allocation is validated.

---

## Leave Policy Assignment — the factory

Employee + policy + period. On **submit** it reads the policy table and creates one
Leave Allocation per leave type.

| Field | Impact |
|---|---|
| `assignment_based_on` | *Leave Period* — everyone shares the period's dates. *Joining Date* — each employee's year starts on their own anniversary |
| `effective_from` / `effective_to` | filled from the period or the joining date |
| `carry_forward` | silently forced to 0 for any leave type whose `is_carry_forward` is off |
| `leaves_allocated` | guard flag — resubmitting throws "Leave already have been assigned" |

It pro-rates mid-year joiners automatically.

---

## Leave Allocation — the grant

The record that gives days to **one** employee. This is where "who, how many, for
what period" finally lives.

| Field | Impact |
|---|---|
| `employee` + `leave_type` | who and which kind |
| `from_date` / `to_date` | the window the days are usable in. **`to_date` is the expiry date** — leftover days are cancelled by a negative ledger entry that day, unless the type carries forward |
| `new_leaves_allocated` | fresh days granted now |
| `unused_leaves` | days carried in from the previous allocation |
| `total_leaves_allocated` | the two added — **this is the grant**, and it is mandatory unless the type is earned or compensatory |
| `carry_forward` | pull in the previous allocation's leftovers. Throws "cannot be carry-forwarded" if the type disallows it *and* a previous allocation exists |
| `carry_forwarded_leaves_count` | how many actually came in, after `maximum_carry_forwarded_leaves` clamping |
| `total_leaves_encashed` | written by Leave Encashment |
| `expired` | set by the scheduler at `to_date` |

**Draft grants nothing.** `docstatus 0` means zero ledger entries and a balance of 0.

### A worked example from this site

`NGI-HR-LAL-83/84-00001` — the full lifecycle in one record:

```
18 Jul 17:13  submitted        ledger  +6   2026-07-18 → 2026-07-31
31 Jul        period ended     (6 days unused)
05 Aug 00:00  scheduler ran    ledger  −6   dated 2026-07-31, is_expired=1
              balance today = 0
```

Note the expiry entry was *created* on 5 Aug but *dated* 31 Jul. A late-running
scheduler does not corrupt the dates.

---

## Leave Application — the spend

| Field | Impact |
|---|---|
| `from_date` / `to_date` | the absence |
| `total_leave_days` | computed — holidays and weekly offs dropped unless the type has `include_holiday`; half days count 0.5 |
| `half_day` + `half_day_date` | which day is the half |
| `leave_balance` | shown for information, read from the ledger |
| `status` | Open / Approved / Rejected — **superseded by the workflow on this site** |
| `salary_slip` | set once payroll consumes it |

On submit it writes `leaves = total_leave_days * -1`. An application spanning two
allocation periods splits into two negative rows rather than one.

**On `nepalgas`, approval runs through the custom `Leave Application Approval
Workflow`, not the stock `leave_approver` field.**

---

## Leave Ledger Entry — the truth

Read-only in practice; every other doctype writes into it.

| Column | Meaning |
|---|---|
| `leaves` | signed. **+** from allocations, **−** from applications, expiry, encashment |
| `transaction_type` / `transaction_name` | which document wrote it |
| `from_date` / `to_date` | the period the entry applies to |
| `is_carry_forward` | this row is carried-in days |
| `is_expired` | this row is the year-end cancellation |

Cancel the source document and the entry reverses. That is the whole audit trail —
when someone asks "why is my balance 3", this table answers it.

---

## Setting up a new leave year

### Full path (multiple leave types, entitlements differ by grade)

1. **Leave Types** — one per kind of leave. Set the flags from the table above.
2. **Leave Period** — the leave year, per company. Match the Fiscal Year dates.
3. **Leave Policy** — one per grade, listing type → days.
4. **Leave Control Panel** — filter by company, tick *Allocate Based On Leave
   Policy*, pick the policy, Allocate. Creates assignments → allocations.

### Short path (one leave type, same for everyone) — what NGI uses

Skip steps 2 and 3 entirely. `/app/leave-control-panel`:

| Field | Value |
|---|---|
| Company | Nepal Gas Udhyog Pvt. Ltd. |
| **Allocate Based On Leave Policy** | **untick** ← this is what skips the policy layer |
| Leave Type | Casual |
| New Leaves Allocated (In Days) | 4 (or 6 — see open question below) |
| Dates Based On | Custom Range |
| From Date / To Date | 2026-07-17 / 2027-07-16 |
| Carry Forward | untick (Casual has `is_carry_forward = 0`) |

It previews the employee list before acting, and **skips anyone who already has an
allocation for that period** — so it is safe to re-run after new hires join.

---

## Site state — `nepalgas`, 2026-08-27

| | |
|---|---|
| Active employees | 295 across 6 companies (NGI 107, NGN 77, NGG 55, NGK 44, GLMI 11, GEPL 1) |
| Leave Types | 2 — `Casual` (cap 6), `Sick` (cap 0, created 08-27, unused) |
| Leave Policy | 1 — `HR-LPOL-2026-00001`, Casual = 4 |
| Leave Period | 1 — `HR-LPR-2026-00001`, **dates wrong** (2026-05-12 → 2027-06-09 vs FY 2026-07-17 → 2027-07-16) |
| Leave Allocations | 2 — one expired test, one live (Anil Shrestha, Casual, 3 days) |
| Leave Applications | 0 |
| Employees with a balance | **1 of 295** |

### Scheduler

`allocate_earned_leaves`, `generate_leave_encashment` and
`process_expired_allocation` are all **`stopped=0`** (unlike the three attendance
jobs), but last executed **2026-08-21** — the scheduler on this box runs
irregularly.

---

## Open items

| | Note |
|---|---|
| **Holiday lists** | **1 of 107** NGI employees has one; Company `default_holiday_list` is NULL. `NGI-Holiday-00002` (2026-07-17 → 2027-07-16, 80 holidays) exists and is not attached to anyone. **Fix before allocating** — without it a Fri→Mon leave costs 4 days instead of 2 |
| **Allocate the 106** | Leave Control Panel, short path above |
| **4 or 6 days?** | the policy says 4, the Leave Type cap says 6. They should agree with actual HR policy |
| **Leave Period dates** | wrong; harmless while using Custom Range, a trap the moment anyone uses the policy path |
| **No LWP type** | the attendance half-day rule forces Half Day + Leave Without Pay, and there is no Leave Without Pay type for it to resolve to |
| **No grades/departments** | all 107 NGI employees have blank grade, department, designation and employment type — so the Control Panel can only filter by Company. Fine for one policy; blocks per-grade entitlements |
| `prevent_self_leave_approval` | **0** — a manager can approve their own leave |
| Notification templates | `leave_approval_notification_template` and `leave_status_notification_template` are NULL while `send_leave_notification` is on |
| Leave Block List | 0 — this is where Dashain/Tihar peak-demand blackouts would go |

---

## Gotchas

- **Saving is not granting.** A draft allocation with "12" on it gives a balance of
  zero. Only `submit` writes the ledger.
- **`to_date` is an expiry date.** Whatever you type there is the day leftover days
  are cancelled. An arbitrary end date silently shortens the entitlement.
- **Carry-forward clamping is silent.** 10 new + 8 carried against a cap of 12
  becomes 12 with no message — the other 6 evaporate.
- **Leave Type alone cannot hold a balance.** It is one row shared by 295 people.
  This is why Leave Allocation exists, and why it feels redundant until employee
  number two.
- **`max_leaves_allowed` vs `allow_over_allocation`** measure different things: the
  first against the annual cap, the second against the **length of the allocation
  period**.
- **The workflow only guards spending.** Allocation, expiry, encashment and
  compensatory requests all move the ledger without ever touching
  `Leave Application Approval Workflow`.
- **Attendance can dock pay with no leave application at all.** Auto-attendance
  marks Half Day → Leave Without Pay directly on the Attendance row, and payroll
  reads attendance. The leave workflow never runs.

---

## Related

- `docs/hrms-attendance-handoff.md` — the attendance pipeline this feeds into
- Payroll is the bigger gap: 0 Payroll Periods, 0 Income Tax Slabs, 0 Salary
  Structures, 0 Salary Structure Assignments. Leave Encashment and LWP both need
  a Salary Structure before they do anything.

---

## Monthly credit runs on Bikram Sambat months (2026-09-20)

The leave year is Shrawan → Ashadh, so the credit does not follow Gregorian
month ends. `avinashgroup_app.hr.utils.allocate_earned_leaves_bs` is registered
as a `daily_long` scheduler event and credits on the BS month end; the patch
`setup_bs_leave_accrual` stops the stock `hrms.hr.utils.allocate_earned_leaves`
so nothing is credited twice.

Credit days for FY 83/84 (`preview_accrual_dates("2026-07-17", "2027-07-16")`):

| BS month end | AD date | | BS month end | AD date |
|---|---|---|---|---|
| Shrawan 31 | 2026-08-16 | | Magh 29 | 2027-02-12 |
| Bhadra 31 | 2026-09-16 | | Falgun 30 | 2027-03-14 |
| Ashwin 31 | 2026-10-17 | | Chaitra 30 | 2027-04-13 |
| Kartik 30 | 2026-11-16 | | Baisakh 31 | 2027-05-14 |
| Mangsir 29 | 2026-12-15 | | Jestha 31 | 2027-06-14 |
| Poush 30 | 2027-01-14 | | Ashadh 32 | 2027-07-16 |

Two things the stock job got wrong, and this one does not: every instalment
landed 14–17 days late, and the Ashadh instalment never ran at all (the leave
year is already expired by 31 July, so HRMS skipped it and everybody lost their
twelfth credit, every year).

### The instalment is capped, not refused

HRMS credits the whole instalment or nothing, so after admin advances leave with
the **Allocate Leaves** button the last month is dropped: 21 a year, 20 already
given, and the final 1.75 instalment is refused rather than paying the 1. This
job credits `min(instalment, what is left of the year)`, so the year lands
exactly on the policy figure. Verified on nepalgas: advanced to 20 of 21, the
Ashwin credit came out at 1.0.

Mid-month joiners are pro-rated against the **BS** month, not the Gregorian one.

### Checking a month before it lands

`allocate_earned_leaves_bs(dry_run=True)` returns what it would credit and
writes nothing:

    bench --site nepalgas console
    >>> frappe.flags.current_date = frappe.utils.getdate("2026-10-17")
    >>> rows = allocate_earned_leaves_bs(dry_run=True)

On 2026-09-20 that returned 590 rows: Casual 1.75 a month (NGK 0.75, being 8 a
year) and Sick 1.00, for all 295 staff.
