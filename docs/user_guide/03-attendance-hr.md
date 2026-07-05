# Attendance & HR — User Guide

For HR Managers and HR Users. Covers how fingerprint punches become
attendance, how to fix gaps, allowances, and the HR reports.

## 1. How attendance works (the happy path)

1. An employee punches on the fingerprint device (ZKTeco K40, Hikvision, or an
   HTMS-connected controller).
2. The **K40 Bridge** (a small Windows program at each site) — or the device
   itself, if it pushes directly — sends the punches to ERPNext.
3. Each punch becomes an **Employee Checkin**. Punches alternate IN → OUT → IN
   for the day, sorted by time. Re-sent punches are ignored (no duplicates),
   and a punch that arrives late slots into the right place automatically.
4. The Shift Type's auto-attendance job turns the day's checkins into a
   submitted **Attendance** record.
5. On the Attendance, the system automatically fills:
   - **Late entry / early exit minutes** (compared to the shift times),
   - **Half Day** if the first punch is after the shift's late-arrival cutoff
     (with leave type "Leave Without Pay"),
   - **Worked on Holiday** if the date is in the employee's holiday list.

On the Attendance form you can see the day's **Checkin Log** (IN in green,
OUT in orange) right below the status.

### Employee setup that must be right

- Every employee needs their **Attendance Device ID** set to the user ID they
  have *on the device* (for HTMS: the Emp No, with leading zeros exactly as
  stored).
- The same device ID may be reused **across companies** but must be unique
  **within** a company — the form blocks duplicates.
- The employee's Company must match the device's Company (a punch on Company
  A's device only matches Company A's employees).

## 2. Fixing attendance (Attendance Fix)

When a bridge PC was off, a device was offline, or attendance is otherwise
wrong for a period, use **Attendance Fix**:

1. New Attendance Fix → choose the **Shift Type** and the **From/To dates**.
   Optionally narrow to one **Employee**, one **Company**, or specific
   **Devices**.
2. **Submit.** The job runs in the background; the form shows a live progress
   bar and refreshes itself.
3. When it finishes you get counters (attendance created/updated, checkins
   relinked, stale Absent rows deleted) and a day-by-day log.

What it does per employee/day: creates attendance from checkins where missing;
replaces a wrong "Absent" with the real attendance when checkins exist; links
orphan checkins to existing attendance; marks Absent where there are no
checkins (skipping holidays); and never touches days that already look right.

> Tip: when a bridge comes back online after an outage, the recovery email you
> receive tells you the date range to run Attendance Fix for.

## 3. Devices, syncing and alerts

- Each physical device is a **Biometric Device** record: name, serial number
  (must match the real hardware serial), Company, and enabled flag. Punches
  from unknown or disabled serials are rejected.
- **Force Bridge Sync**: on the Biometric Device form, this button asks the
  bridge to sync that device now; the result appears within a minute or two.
- **Alerts**: add emails to the device's *Alert Recipients* table and set the
  threshold (default 120 minutes). If the bridge stops reporting for longer
  than the threshold, those people get one "down" email, and one "recovered"
  email when it returns.
- The bridge itself is installed from `K40BridgeSetup.exe` on a Windows PC on
  the device's network — see the install runbook (`k40_bridge/SETUP.md`) or
  ask your administrator.

## 4. Attendance allowances (payroll)

Allowances that depend on attendance (meal allowance, tea/conveyance, holiday
work, overtime-style rules) are computed from Attendance records:

- Each allowance is a **Salary Component** marked *attendance driven*, with a
  condition (Present / Half Day / Worked on Holiday / Late Stay After / Early
  Entry Before / Late Arrival After / Working Hours threshold), a unit (per
  day / per hour / flat per period), and a default rate.
- Per-employee overrides live on the Employee form in the **Attendance
  Allowances** table (set a different rate, or untick *Eligible* to exclude
  the employee). Overtime-type rules also require the employee's **OT
  Eligibility** checkbox.
- On a **Payroll Entry**, click **Calculate Attendance Allowances** (under the
  Nepal HRMS menu). This creates/updates draft **Additional Salary** records —
  one per employee per component — and reports what was created or skipped.
  You can run it again safely; it replaces its own previous drafts.

## 5. HR reports (all in Nepali BS months)

| Report | Use it for |
|--------|-----------|
| **Monthly Attendance BS** | the day-by-day register for a BS month: in/out times, hours, late minutes, status, holiday work, and a column per attendance allowance |
| **Monthly Attendance Summary BS** | one line per employee for the month — present days, OT hours, late time, meal/tea groups, leave this month / last month / year-to-date. Mirrors the physical muster sheet |
| **Work On Holiday BS** | who worked on holidays, month by month across the fiscal year |
| **Yearly Leave Details BS** | leave taken per BS month, total allocation, and remaining balance per employee |
| **Avinas Salary Statement** | the salary sheet for a BS month: all earnings and deductions in columns, grouped by designation with sub-totals, plus last month's net for comparison |

Pick the fiscal year / BS month in the filters; you can also switch to an AD
date range where offered.
