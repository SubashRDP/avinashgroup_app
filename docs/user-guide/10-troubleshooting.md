# 10. Troubleshooting: error messages and what to do

[Back to contents](README.md)

How to use this chapter: find the message you see (use your browser's **Ctrl+F** and type a few words of it). In the messages below, "…" stands for a name, date or number that changes each time.

If the fix says "tell IT", copy the full message (or take a screenshot) and send it with the document number.

**First thing to try when a screen looks wrong or a new button is missing:** press **Ctrl+Shift+R** to reload the page fully. The browser keeps old copies of forms and reports.

---

## 10.1 Problems with no error message

### Someone is missing from the payroll
The Payroll Entry fills only people who have, for that month:
1. **Status Active** (or a Relieving Date inside the month), and a **Date of Joining** on or before the month's end;
2. a **submitted Salary Structure Assignment** with **From Date** on or before the month's end;
3. the **same Payroll Payable Account** on that assignment as on the Payroll Entry. A blank or different payable account leaves the person out **silently**;
4. the same **company**, and the same Branch / Department / Designation if you filtered by them.

Fix the cause, then on the draft Payroll Entry click **Get Employees**. If the entry is already submitted, make a second Payroll Entry for the same month with only the missing person (Chapter 5, section 5.11).

### The draft slips have no tea, meal or overtime
**Prepare Payroll Inputs** was not pressed, or was pressed before the attendance or Overtime Sheets were finished. Press it again on the Payroll Entry. It updates the draft slips.

### Overtime is 0 (or less than expected) for someone
Check in this order:
1. Is the person in an overtime category (**Operation**)? Officer & Admin get replacement leave instead.
2. Is there a **submitted** Overtime Sheet for that date with the person on it and **Earns = Overtime**?
3. Open the sheet: what do **Worked Hours** and **Note** say? "No attendance", "Marked absent", "Only one punch" all give 0. Fix the attendance, then click **Measure from Attendance**.
4. On a working day only the hours **outside** the shift count. Check the person's shift for that day.
5. Press **Prepare Payroll Inputs** again.

Punches without a sheet are never paid. Make the sheet for that date (past dates are fine) and get it approved.

### Meals are 0 for someone
Meals need **all** of: OT-eligible category, a submitted Overtime Sheet for that day with Earns = Overtime, and on a working day a punch at least **1.5 hours** before the shift start or after the shift end. On a holiday on the sheet, 2 meals. See Chapter 4, section 4.6.

### Tea is less than the days present
Tea is not paid on **holidays and Saturdays**, even if the person worked. A Half Day earns a full day of tea. Check also that the person has no inactive Tea & Conveyance row (or a lower rate) on their assignment.

### Everyone is paid for fewer days than the month has (for example 26 of 31)
Payroll Settings → **Include holidays in total working days** has been turned off. It must be **on** (holidays are paid). Tell IT or the HR manager.

### Many days suddenly became Half Day
Usually a **Late Arrival Cutoff (forces Half Day)** time was saved on a Shift Type by mistake. Open the Shift Type, clear that field, save, then run **Attendance Fix** for the affected dates.

### A long overtime day is marked Absent
The Shift Type's **Allow check-out after shift end time** is too short (it should be 240 minutes), so the late check-out was ignored. Correct it, then run **Attendance Fix**.

### Someone worked on a Saturday or holiday but has no attendance
Automatic attendance may skip holidays. Open **Attendance** for that day and use **Repair from Check-ins**, or run **Attendance Fix** for that date.

### A woman did not get Teej off
Her **Holiday List** on the Employee is not her company's **Women** list. Set it, then run **Attendance Fix** for that date. Also make sure no Shift Type has a Holiday List set (it would override hers).

### A slip shows an "Adjustment: attendance differs from the slip's payment days" row
Attendance was changed after the slip was made. Open the draft slip and **Save** it again. See Chapter 6.

### Preview Salary Slip shows no allowances
Normal. Preview only shows the structure. A real slip shows everything (Chapter 6).

### The salary sheet shows people under "No Section"
Their Department has no Payroll Section, or they have no Department. See Chapter 2.

### The salary sheet shows a red card instead of "Matches Journal"
See Chapter 7, section 7.1 "What a red card means". A card such as **"Education Allowance: S/D column holds the O/O account 547101"** names the setting to fix: the accountant opens that Salary Component, finds the company's Accounts row and corrects that column (Chapter 9).

### A new Payroll Entry opens on a month I did not expect
It opens on the month after the company's last payroll (so a paid month is not offered again), but never later than the month running today. Click another month on the calendar if needed.

### A list view shows an error or "unknown column", but the form opens fine
The list views read from a copy of the database that may be behind. Tell IT ("the read replica may be stuck").

### The month I want is greyed out on the Payroll Entry calendar
That month has not started yet. You can only pay a month that has started (usually the one that just ended).

### Leave balance shows 0 although days were allocated
The Leave Allocation is still a **draft**. Open it and **Submit** it.

---

## 10.2 Payroll Entry and salary slip messages

| Message | What it means | What to do |
|---|---|---|
| **Set Payroll Section on the Department of these employees, so their pay posts to the right account: …** | The listed employees have no Department, or their Department has no Payroll Section | Set the Department on each Employee and the Payroll Section on each Department (Chapter 2). Then click **Submit Salary Slip** again |
| **Please set account in Salary Component …** | That component has no Accounts row for this company | Accountant adds the row (Chapter 9). Then retry |
| **Account type cannot be set for payroll payable account …, please remove and try again** | The salary payable account has an Account Type | Accountant opens the account, clears **Account Type**, saves (Chapter 9) |
| **Set Default Payroll Payable Account on Company …, or choose one on this entry.** | The company has no default salary payable account | Accountant sets it on the Company (Chapter 9), or choose the account on the entry |
| **No employees found for the mentioned criteria: Company … Currency … Payroll Payable Account …** | Nobody matches: no submitted assignments for that month, or their payable account differs | Check the assignments (section 10.1, "Someone is missing") |
| **Posting date is in another BS month** — "This entry pays … but is posted on …, which is in …. Every salary slip takes its month from the posting date…" | The posting date was changed to a date outside the month being paid | Choose the month again on the calendar (it resets the posting date to the month's last day), or set the posting date to the date the message suggests |
| **Slip and payroll entry disagree on the month** — "Salary slip covers … but its payroll entry … pays …. Fix the entry's posting date." | A slip's month differs from its Payroll Entry | Tell IT. Usually the entry's dates were changed after slips were made: cancel and remake the slips |
| **Attendance missing** — "… of … employees have no submitted attendance between … and …. Their unmarked days count as Present, and they get no tea, meal, overtime or late fine." | An orange warning on Save or Submit: the month has no attendance for these people | If attendance is still to come, stop: mark it, run **Prepare Payroll Inputs**, then submit. If paying a full month without attendance is intended, carry on |
| **Choose the Payment Account and press Update to save it, then make the bank entry.** | **Make Bank Entry** was pressed before the Payment Account was saved on the submitted entry | Choose the bank account, press **Update**, then **Make Bank Entry** |
| **Payment Account … is a … account. Salary is paid from a Bank or Cash account.** | The Payment Account is not a bank or cash account (for example a stock account) | Choose the bank or cash account the salary is paid from, press **Update**, try again |
| **Cannot submit. Attendance is not marked for some employees.** | The entry has **Validate Attendance** ticked and some days have no attendance | Complete the attendance, or untick Validate Attendance |
| **Salary Slip of employee … already created for this period** | The person already has a slip for this month | Do not pay them twice. Remove them from this entry, or cancel the other slip if it was wrong |
| **No active or default Salary Structure found for employee … for the given dates** | The person has no submitted Salary Structure Assignment for the month | Create and submit one (Chapter 2) |
| **Salary Slip creation failed. You can resolve the issue and retry creation.** (on the entry) | One or more slips could not be made | Click **issue** to read the reason, fix it, click **Create Salary Slips** again |
| "… skipped — see Error Log" (after Prepare Payroll Inputs) | Some tea / meal / overtime / fine records could not be made | Tell IT; they will read the Error Log entries titled "Nepal HRMS Attendance Allowance: …" |
| **Cannot calculate allowances for a cancelled Payroll Entry.** | You pressed Prepare Payroll Inputs on a cancelled entry | Use the live entry for that month |
| **No income tax Salary Component is set up, so it cannot be overridden.** | Override Income Tax was ticked on a slip with no Income Tax line | Untick it, or tell IT to check the salary structure |
| **Please set Payroll based on in Payroll settings** | Payroll Settings are incomplete | Tell IT (it must be "Attendance") |
| **Employee advance account … should be of type Receivable.** | The staff advance account has the wrong type | Accountant sets Account Type = Receivable (Chapter 9) |
| **… is not in any active Fiscal Year** | The new fiscal year has not been created | Accountant / IT creates the Fiscal Year with all seven companies (Chapter 8) |

## 10.3 Salary component, structure and assignment messages

| Message | What to do |
|---|---|
| **Accounts row …: … is not an account of …** | The S/D or F/P account belongs to another company. Choose that company's own account |
| **Choose the Allowance Kind** | You ticked Is Allowance. Choose the Allowance Kind |
| **Row …: … is a … allowance: give it on the employee's Allowances table** | You put a fixed allowance (Dearness, Gas, HRA…) in a Salary Structure. Remove it from the structure; give it on each person's assignment |
| **Row …: … is a … allowance: it is paid when entered, not every month** | You put a Yearly or Entered-by-Hand allowance in a structure. Remove it; pay it with a Payroll Adjustment |
| **Allowance … is listed twice** | Remove the duplicate row on the assignment |
| **Row …: … is not an allowance** | Only components ticked **Is Allowance** can go in the Allowances table |
| **Row …: … is a … allowance and is paid when entered** | Load/Unload, Dashain Bonus, Leave Encashment cannot be on the assignment. Use a Payroll Adjustment |
| **Row …: type …'s monthly amount** | A Fixed per Person allowance (Dearness, Other, Fixed…) needs this person's Amount. Type it, or untick Active |

## 10.4 Salary Revision and Payroll Adjustment messages

| Message | What to do |
|---|---|
| **A salary revision must start on the first day of a BS month. … use … or the first of the next month.** | Use the date suggested |
| **Row …: … has no salary structure assigned, so there is nothing to revise** | Create the person's first assignment instead |
| **Row …: … already has a salary assigned from …** | Remove the row or cancel that assignment |
| **Row …: the new basic must be more than zero** | Type the New Basic |
| **Row …: … is listed twice** | Remove the duplicate |
| **Row …: … belongs to …** | The person is in another company; remove the row |
| **Row …: … already has a … row — put the whole amount on one line** (Payroll Adjustment) | Combine the two rows into one |
| **Row …: amount must be more than zero** (Payroll Adjustment) | Type a positive amount |

## 10.5 Overtime Sheet messages

| Message | What to do |
|---|---|
| **Rows the policy does not allow** (list) | Read each line; the fixes are in Chapter 4, section 4.3 |
| **… has no Employee Category — set it with the Employee Category Tool first** | Set the category (Chapter 2) |
| **…: … is a working day for them — choose Overtime, not Work on Holiday** | Change Work Type to Overtime |
| **…: … is … for them — choose Work on Holiday, not Overtime** | Change Work Type to Work on Holiday |
| **… (…) is not eligible for overtime on a working day** | Officer & Admin cannot get working-day overtime; remove the row |
| **… has no shift on …, so overtime beyond it cannot be measured** | Give the person a shift |
| **…: category … earns nothing for holiday work** | The category has neither box ticked; HR manager fixes the Employee Category |
| **Row …: … belongs to …, not …** | Use the person's own company's sheet |
| **Row …: … is listed twice** | Remove the duplicate |
| **Authorised Twice** — "Already on another Overtime Sheet for this date: …" | Use the existing sheet, or cancel it first |
| **… is not approved yet, so there is nothing to settle** | Submit/approve the sheet before Measure from Attendance |
| **A category gets either overtime or replacement leave for holiday work, not both** (Employee Category) | Tick only one of the two boxes |

## 10.6 Attendance, device and holiday messages

| Message | What to do |
|---|---|
| **Attendance Device ID … is already used by … (…) in company …. It must be unique within a company…** | Check the device enrolment; give each person their own number |
| **Device serial … is not registered or is disabled.** (seen by IT in the bridge log) | Register the device on **Biometric Device** with that serial and tick Enabled |
| **From Date must be on or before To Date.** (Attendance Fix) | Correct the dates |
| **Add at least one employee, or set Repair Scope to All Employees in Shift.** | Add employees, or change the scope |
| **Row …: … is listed more than once.** (Attendance Fix) | Remove the duplicate |
| **To Date cannot be before From Date** (Monthly Attendance BS) | Correct the filter dates |
| **Holiday Date is required** / **Holiday name is required when adding** | Fill both on Holiday Bulk Update |

## 10.7 Leave messages

| Message | What to do |
|---|---|
| **Over the year's leave** — "… is allowed N days of … this year, and this would make M." | The allocation would pass the yearly limit in the person's Leave Policy. Reduce the days |
| **Not Eligible** — "… is only for employees whose gender is …. … is recorded as …." | Maternity is for women, Paternity for men. Check the Gender on the Employee |

## 10.8 Shift messages

| Message | What to do |
|---|---|
| **… is already on … for these dates** (Shift Request) | The person already has that shift; nothing to request |
| **Only Approvers can Approve this Request.** | Set the **Shift Request Approver** on the Employee, and approve as that user |
| **… already has an active Shift Assignment … for some/all of these dates.** | Do not create a second Shift Assignment by hand. Use a **Shift Request**, **Move Staff to This Shift**, or the **Shift Roster** (Chapter 3) |
| **Payroll Already Submitted** — "… has already been paid for … to … on …. Changing the shift for those days would change attendance under a paid salary…" | Start the change after the paid month, or cancel that salary slip first (with the accountant) |
| **Set the Company on this Shift Type first — staff rotate within one company.** | Fill Company on the Shift Type |
| **Tick at least one employee to move.** / **Enter the date the new shift starts.** | Tick people / fill the From Date |
| **… is on … on …, which does not take part in rotation. Only staff on … rotate; for a one-off change use a Shift Request.** | That person is on a fixed shift. Use a Shift Request |
| **… does not take part in rotation, so nobody can be rotated onto it…** | Tick **Takes Part in Rotation** on that Shift Type, or use a Shift Request |
| **… is a shift of …. Staff of … can only rotate between its own shifts.** | Choose a shift of the person's own company |
| **… is already on … on ….** | The person is already on that shift from that date |
| **… has a dated shift change on or after … (…). Cancel it first, or start the rotation after it ends.** | Cancel the later change first, or choose a later From Date |
| **Shift rotation is not set up on this site yet. Run bench migrate.** | Tell IT |
