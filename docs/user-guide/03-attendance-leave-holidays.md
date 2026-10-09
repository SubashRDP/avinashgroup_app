# 3. Attendance, biometric devices, leave and holidays

[Back to contents](README.md)

Pay follows attendance. A day marked **Absent** is not paid; a **Half Day** with no paid leave costs half a day's pay. So attendance must be right before payroll is run.

---

## 3.1 How a punch becomes attendance

```
Employee punches the biometric device
        ↓   (the device bridge on site sends punches to ERPNext)
Employee Checkin   — one row per punch
        ↓
Attendance         — one row per person per day: Present / Absent / Half Day / On Leave
        ↓
Salary slip        — payment days, tea, meals, overtime, late fine
```

Things the system does by itself:
- The **last punch of the day is always treated as the check-out** (OUT), and the punches in between alternate IN / OUT.
- **Every hour**, a repair job links punches that arrived late and refreshes the day's hours.
- **Around midday** each day, an attendance summary email with an Excel file is sent per company to the people set up to receive it.
- If a device bridge stops sending, an alert is raised.

What HR must have in place:
- Each device registered on **Biometric Device** with its serial number, company and **Enabled** ticked. A device that is not registered is refused, and none of its punches are saved. (On 9 October 2026 no devices are registered on this site.)
- Each employee's **Attendance Device ID** (Chapter 2).
- Each employee's **shift** (Chapter 2).

## 3.2 What each status means for pay

| Status | Paid | Notes |
|---|---|---|
| Present | Full day | Earns tea (on a working day) |
| Work From Home | Full day | |
| Half Day | Half day, unless the other half is paid leave | Still earns a **full** day of tea |
| On Leave (paid leave type) | Full day | |
| On Leave (Leave Without Pay) | Not paid | |
| Absent | Not paid | |
| Holiday (no attendance) | Full day | Holidays are paid |
| No attendance on a working day | **Paid as Present** at present | Payroll Settings → "Consider unmarked attendance as" is **Present** on this site |

## 3.3 The attendance rules from the policy

**More than 2 hours late = Half Day.** If the first punch is more than 2 hours after the shift starts (the shift's **Half Day If Late By (Hours)**), the day becomes a Half Day, half absent. Example: on a 9 AM shift, in at 10:59 stays Present; in at 11:01 becomes Half Day. There is no grace period.

**Coming to work while on approved leave = Half Day.** If a person has approved leave for a day but also punched in, the day becomes a Half Day: half leave, half present.

**Late minutes.** The Attendance form has a **Shift Deviation** section: Late Entry, Early Entry, Early Exit, Late Exit. These are measured against that day's shift and are what the late fine and meals use.

**Excusing lateness for one day.** For a real reason (traffic jam, funeral):
1. Open the person's **Attendance** for that day.
2. Tick **Late Excused** and type the **Reason for Excusing**.
3. Save.

The lateness stays recorded in reports but is no longer fined. If lateness was the only reason the day became a Half Day, the day goes back to Present.

**Worked on Holiday** is ticked automatically when someone has attendance on a day that is a holiday on their own holiday list.

## 3.4 Fixing attendance

### One person, one day: Repair from Check-ins
1. Open the **Attendance** row (or create it if it is missing, from the Attendance list).
2. Click **Repair from Check-ins**.
3. The system rebuilds the day from the punches and shows **Before** and **After**. If it says "Already correct — nothing to change", the punches support the current status.

The Attendance form also shows a **Checkin Log** with each punch of the day.

### Many people or many days: Attendance Fix
1. Open **Attendance Fix** → **New**.
2. Choose the **Company** and the **Shift Type**.
3. **Repair Scope:** "All Employees in Shift", or "Selected Employees" and list them in **Employees** (the **Add Everyone on This Shift** button fills the list; remove the ones you do not want).
4. Set **From Date** and **To Date**. Optionally limit to some **Devices**.
5. Save and **Submit**. The repair runs in the background. **Status**, **Progress %** and **Current Step** show how far it is. At the end you see how many rows were created, updated or removed, and a **Per-Day Log**.

Use Attendance Fix after: a device was offline, device IDs were filled late, a shift was changed, or a holiday was added or removed for a past date.

### A punch is genuinely missing
If the person forgot to punch, the device cannot know. Create or edit the **Attendance** for that day by hand with the right status, after checking with the person's manager.

## 3.5 Leave

### Leave types on the system

| Leave type | How the days arrive | Notes |
|---|---|---|
| **Casual Leave** | Credited automatically at the end of every BS month | Encashable at year end |
| **Sick Leave** | Credited automatically at the end of every BS month | Encashable at year end |
| **Maternity Leave** | Allocated by HR | Female employees only |
| **Paternity Leave** | Allocated by HR | Male employees only |
| **Replacement Leave** | Granted automatically for holiday work by Officer & Admin staff (Chapter 4) | |
| **Leave Without Pay** | Not allocated | Unpaid |

> There is also a leave type spelled **"Causal Leave"** on the system. It is a spelling mistake and is not set up correctly. Do not use it. Use **Casual Leave**.

Policy (client meeting, September 2026): 33 days a year in total — Casual 21 + Sick 12 (Karnali: Casual 8 + Sick 12). Staff on probation get 1 day a month. **Holidays that fall between two leave days count as leave** ("sandwich" rule). Leave left at the end of the fiscal year is **encashed**, not carried forward.

### Monthly credit
Leave is credited on the **last day of each BS month** (not the English month end), from the person's Leave Policy. A person who joins mid-month gets a share for that BS month.

HR may give a different amount in a month (three days one month, four the next), but **the year's total cannot pass the policy**. If it would, you see "**… is allowed N days of … this year, and this would make M.**"

> **Saving is not granting.** A Leave Allocation that is only saved (draft) gives zero days. It must be **Submitted**.

### Applying for leave
1. Open **Leave Application** → **New**.
2. Choose the **Employee**, **Leave Type**, **From Date** and **To Date**. Tick **Half Day** and choose the half-day date if needed.
3. Check **Leave Balance** shown on the form.
4. Save. Where an approval chain is set up for the company (NGI has one for Leave Application), the application goes to the approver. Once approved, it is submitted.

The day then shows **On Leave** in attendance and is paid (unless the type is Leave Without Pay).

### Checking a balance
Open **Leave Application** for the person: the balance is shown. For a whole year, use the **Yearly Leave Details BS** report (Chapter 7).

## 3.6 Holidays

Each company has two holiday lists per fiscal year: the common list (everyone) and the Women list (common + Teej + International Women's Day). See Chapter 2.

### Adding a holiday to many lists at once: Holiday Bulk Update
Use this when the government announces a new holiday, so that no list is forgotten.

1. Open **Holiday Bulk Update** → **New**.
2. Type the **Holiday Date** and the **Holiday** name (for example "Haritalika Teej").
3. Leave **All Holiday Lists** ticked to add it to every list. Or untick it and choose the lists in **Holiday Lists**:
   - a women-only day → choose the Women lists;
   - a holiday for one company → choose that company's two lists.
4. Save, then click **Apply**. The **Result** shows, list by list, what was added and what was skipped (skipped = the date is outside that list's year, or is already there).

**If the date is already past**, the system also tidies attendance for that day: "Worked on Holiday" is ticked for everyone who came, Absent rows with no punches are removed, and anyone whose salary for that month is already paid is skipped and named. Approved Overtime Sheets for that date are listed for you to check.

### Removing a holiday
The bulk screen only adds. To remove a holiday, open the **Holiday List** itself and delete the row. Then run **Attendance Fix** for that date so the day is marked again as a working day.

### Rules to remember
- **Do not** set a Holiday List on a Shift Type. It overrides every employee's own list.
- On **1 Shrawan** the system moves the companies and the women to the new year's lists by itself. The new year's lists must exist by then (Chapter 8).

## 3.7 Changing shifts

| Situation | Use |
|---|---|
| One person needs another shift for a few days | **Shift Request** with a To Date |
| One person moves to another shift permanently | **Shift Request** with **To Date blank** |
| Many people rotate between two shifts every month | **Move Staff to This Shift** on the Shift Type, or the **Shift Roster** page |

### Shift Request (one person)
1. Open **Shift Request** → **New**. Choose the employee, the new **Shift Type**, **From Date**, and **To Date** (blank = permanent).
2. Save; the approver approves and submits.
3. The old shift ends the day before and starts again after the To Date. Cancelling the request puts the old shift back.

The employee must have a **Shift Request Approver**, or approval fails with "Only Approvers can Approve this Request."

### Monthly rotation: Move Staff to This Shift
Only shifts ticked **Takes Part in Rotation** can be used. (On 9 October 2026 no shift on this site is ticked.)
1. Open the **Shift Type** people are moving **onto**.
2. Click **Move Staff to This Shift**.
3. Check the **From Date** (it suggests the first day of the next BS month; you may pick a BS date in **From Date (BS)**).
4. Tick who moves (the header box ticks everyone) and click **Move**.
5. The result lists who moved and, by name with the reason, who did not.

To undo a mistake: open the shift they came from, same From Date, tick them, Move.

### Shift Roster page
Open **Shift Roster**. One row per employee, one column per BS month. Choose a shift from the palette and click cells to "paint" months; drag down a column for many people; right-click a cell to alternate month by month. Nothing is saved until you click **Apply**.

### Changing a shift for past days
Allowed. The days already worked are re-marked on the new shift, and Overtime Sheet hours are measured again. It is **refused** if the person's salary for those days is already submitted: "**… has already been paid for … Cancel the salary slip first, or start the change after …**".
