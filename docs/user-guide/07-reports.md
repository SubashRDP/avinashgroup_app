# 7. Reports

[Back to contents](README.md)

Open any report by typing its name in the search bar. Set the filters at the top; the report refreshes by itself. Every report can be exported (**⋯** menu → **Export**) or printed (**⋯** → **Print**).

| Report | Use it for | Main filters |
|---|---|---|
| [Avinas Salary Statement](#71-avinas-salary-statement--the-salary-sheet) | The monthly salary sheet, in the old Excel layout; checks the payroll journal | Company, Fiscal Year, BS Month |
| [Monthly Attendance BS](#72-monthly-attendance-bs--the-attendance-sheet) | Day-by-day attendance (Detail) or one line per person (Summary) | View, Company, Fiscal Year, BS Month |
| [Salary Tax and SSF Deposit](#73-salary-tax-and-ssf-deposit) | How much SSF, SST and salary tax to deposit, and by when | Company, BS Year, Salary Month |
| [Advance Tax TDS Details](#74-advance-tax-tds-details) | TDS (advance tax) deducted in a period, by TDS head, for the IRD return | Company, From Date, To Date |
| [Yearly Leave Details BS](#75-yearly-leave-details-bs) | Leave taken month by month for a fiscal year, and leave remaining | Fiscal Year, Company |
| [Work On Holiday BS](#76-work-on-holiday-bs) | How many holidays each person worked, month by month | Fiscal Year, OT Eligibility, Company |

> There is no separate "Monthly Attendance Summary BS" report any more. Use **Monthly Attendance BS** with **View = Summary**.

---

## 7.1 Avinas Salary Statement — the salary sheet

**What it is for.** It prints the company's salary sheet exactly in the layout of the old Excel sheet, from the salary slips. HR and accounts can lay it beside the old sheet and see the same figures. It also checks that the payroll journal in the books agrees with the slips.

**Filters**

| Filter | What to choose |
|---|---|
| **Company** | The company |
| **Fiscal Year** and **BS Month** | The month, as on the Payroll Entry (for example 83/84, 05 - Bhadra). If left empty, the last finished month is used |
| **Payroll Entry** | Optional. Choose one entry to see only its slips (useful when a month has two entries) |
| **Slips** | **1 - Submitted** (default) for the final sheet; **0 - Draft** to preview before submitting |

A line under the filters says which dates were used, for example "Bhadra 2083: 2026-08-17 to 2026-09-16 (Nepali calendar)".

**Columns, in the sheet's order**

| Column | Meaning |
|---|---|
| S. No., Employee, Employee Name, Section, Department, Designation | Who |
| **Attendance** | Days at work in the month (a half day = ½) |
| **OT Hr.**, **OT Time**, **Meal Qty.**, **Late Hr.** | Overtime hours (to 4 decimals, exact to the second) and the same as h:mm:ss, meals, and late hours that were paid or fined. OT Hr. × OT Rate = the OT column, to the paisa |
| **Initial Basic** | From the person's assignment |
| **Basic Salary** | Full-month Basic |
| **OT Rate/ Hr.**, **Late Deduction Rate** | The person's rates, to 4 decimals |
| **Unpaid Leave** | Days not paid |
| **Deduction** | What unpaid days took off Basic |
| **Net Basic** | Basic actually paid |
| **SSF Addition** | Employer's 20% |
| HRA, Dearness Allowance, Other Allowance, Fixed, Fuel, Maintenance, Gas, Edu (and any other allowance) | Fixed allowances paid |
| **Total Allowance** | Sum of the allowances |
| **Regular Salary** | Net Basic + SSF Addition + Total Allowance |
| **Tea Conveyance**, **OT**, **Meal** (and other earnings) | Attendance-based earnings. They are found by their Condition Type, so tea is here (not in Total Allowance) whatever the component is called, for example "Tea & Convience" |
| **Gross Salary** | The slip's gross pay |
| **SSF**, **Tax**, **Late Fine**, **Regular Advance**, **Dashain Advance** (and any other deduction) | Deductions. Late Fine is the Late Time component, whatever its name (for example "late comers deduction") |
| **Total Deduction**, **Net Payable** | From the slip |
| **Last Month Net** | Net pay in the previous month, to spot big changes |

A component the sheet does not name still gets its own column, so the columns always add up to Gross and Net.

**Rows.** People are grouped by section in this order: **O/O**, **S/D**, **F/P**, then "**No Section**" for anyone whose department has no Payroll Section. Each group ends with **Sub Total**. After the groups come the sections' subtotals again, together, and the **Grand Total**.

**Summary cards at the top**

| Card | Meaning |
|---|---|
| Employees, Gross Salary, Total Deduction, Net Payable | Totals for the month |
| Green **Matches Journal** (with the journal number) | The payroll journal agrees with the sheet: each section's gross equals the journal's expense for that section, and net pay equals the credit to the salary payable account. All good |
| Orange **Payroll Journal: Not posted** | Slips are submitted but no payroll journal was found. Check that **Submit Salary Slip** finished on the Payroll Entry |
| Orange **Payroll Journal: No payroll entry** | The slips were not made from a Payroll Entry |
| Red cards, for example "**S/D expense: journal 4,57,000.00**" with "**-11,250.00 vs sheet**", and a red **Journal** card | The journal does **not** agree with the sheet (see below) |
| Orange "**SSF Addition: not an expense**" | That earning is booked to an account that is not an expense (NGI: SSF Payable), so it can never appear in the journal's expense. It is left out of the gross comparison. If it should be a cost of each section, the accountant gives it expense accounts (Chapter 9) |
| Red "**Cancelled after posting: …**" | A slip of the Payroll Entry was cancelled after the journal was posted, so the journal still pays it. The red differences are usually exactly that slip. The accountant reverses it in the journal |

The journal check only runs when **Slips = 1 - Submitted**.

**What a red card means.** The amount shown is "journal minus sheet" for that section (or for net payable).
- If one section's journal is **lower** and another section's is **higher** by the same amount, an allowance's account for that section points to the wrong section's account. Example from Bhadra 2083 at NGN: Education Allowance's **Marketing (S/D)** account pointed to the O/O salary account, so 11,250 that belonged to S/D was booked to O/O. Fix: the accountant corrects the account on the **Salary Component → Accounts** row (Chapter 9), then the journal is corrected.
- A difference in **Net payable** means the payable account on the Payroll Entry is different, or the journal was edited by hand. Tell the accountant.
- People in "**No Section**" have no section, so their pay cannot be matched to a section's account. Set the Payroll Section on their Department (Chapter 2).

## 7.2 Monthly Attendance BS — the attendance sheet

**What it is for.** Checking attendance before payroll; answering "what happened on this day?".

**Filters**

| Filter | What to choose |
|---|---|
| **View** | **Detail** — one row per person per day. **Summary** — one row per person for the month |
| **Company** | The company |
| **Fiscal Year** and **BS Month** | The month (uses the same dates as payroll) |
| **From Date (AD)**, **To Date (AD)** | Only if you want a custom range instead of a BS month. A BS Month, if set, wins |
| **Shift**, **Department**, **Branch**, **Designation**, **Employee** | To narrow down |
| **Status** | Employee status, default Active |

If a filter is missing, the report picks a sensible period and says so at the top (for example "No BS Month was set, so the current month … is shown").

**Detail view columns:** BS Date, Employee, AD Date, Day, Shift (the shift on **that** date), Department, **First IN** and **Last OUT** (first and last punch of the day), **Hours Worked**, **Status**, **Late In (min)**, **Before ofc. Time (min)** (minutes left before shift end), **O.T. (hrs)** (only on days an approved Overtime Sheet covers), **On Leave**, **Worked on Holiday**, one column per attendance allowance (Tea & Conveyance, Meal, Overtime, Late Fine — the same count payroll will use), **Remarks**, **Holidays**.

**A red remark "Marked from 13:05 – 18:09, not the first and last punch: re-mark the day"** means the day's attendance was marked from other times than its punches. First IN / Last OUT show the real punches, but Status, Hours and Late come from the attendance, so the two disagree (for example a 05:59 First IN on a day marked Half Day "4 hours late"). Click **First IN** (✎) and save without changing the times to re-mark the day from its punches. A day inside a submitted salary slip cannot be re-marked until the slip is cancelled.

First IN and Last OUT are the first and last punch of the day, even if a punch fell outside the shift's window. So "OUT minus IN" may differ from **Hours Worked**, which is what pay uses.

**Correcting a day's First IN / Last OUT** (HR Manager, System Manager; past days only). Click the First IN or Last OUT cell of the day (a pencil ✎ shows it can be edited; a missing punch shows "— —"). Enter the right First IN and Last OUT and a reason, then **Save Correction**. The day's first punch is moved to the new IN and the last to the new OUT, or a missing one is added; the day's attendance is then re-marked from them (status, hours, late, early) and any approved Overtime Sheet for that day re-measured. The grid refreshes with the new figures. Saving times that are already right re-marks the attendance from them, which fixes a day whose attendance disagrees with its punches. A corrected cell stays **amber with "✎ edited"**; hover it to see what the device read, who changed it, when and why. Refused: today, a day inside a submitted salary slip (cancel the slip first), and times that would leave another punch of the day outside the new IN–OUT. **On a leave day** the punches are saved and the leave is kept: the day becomes **Half Day, other half Present** (came in while on leave, policy 3.4); its shift cannot be changed there. If a draft salary slip covers the day, **Submit Salary Slip** works the month out again and pays the corrected day. **Correcting a day's shift.** Click the **Shift** cell (or open the same dialog from First IN / Last OUT), pick the right shift and, for more than one day, **Same Shift Until** (up to 31 days), give a reason and save. The employee's Shift Assignment is cut around those days only (the dates before and after keep their shift) and one new assignment covers exactly them; each day is re-marked on the new shift. Punch times can be changed in the same save. A corrected Shift cell is **amber with "✎ changed"**; hover it for the old shift, who, when and why. Refused for another company's shift, overnight shifts, today, paid and leave days. Leave days inside a range keep their leave; only their shift is set.

**Giving leave from the report** (HR Manager, System Manager). For leave nobody applied for — a phoned-in sick day found as Absent at month end — click **Give Leave**. Pick the employee and leave type (only types they have an allocation for, with the balance, plus Leave Without Pay), From and To, and untick any days in between that are not leave. Tick **Half Day** and its date for a half day. The dialog shows the balance, how many days HRMS will deduct (holidays inside the days count only if the leave type includes holidays), and warnings before you save: a day already marked **Present** (HRMS refuses leave there), leave already given on a day (HRMS refuses the overlap), and days the person punched (they become **Half Day** with the leave kept, policy 3.4 — the balance still counts the full day). Give a reason and save. One approved **Leave Application** is filed per run of consecutive days, HR is recorded as the approver, and the approval workflow is not walked — giving it here is the approval. HRMS then marks the days On Leave and updates the balance and the leave ledger exactly as for any approved application. Future days are allowed; a day inside a submitted salary slip is refused. In the grid those days show **✎ given** on the status, with who, when and why on hover; each day is also in the Attendance Correction Log as **Leave Given**. To undo, cancel the Leave Application.

**Correction Log.** Every correction — punch edited, added or deleted, shift changed, from this report or from the Employee Checkin form — is written to **Attendance Correction Log** with employee, date, before → after, reason, who and when. Open it with the **Correction Log** button on the report (narrowed to the report's employee and dates) or the "View this day's log" link in the dialog. Nobody can edit an entry; only a System Manager can delete one.

Adding, moving or deleting a punch directly on the **Employee Checkin** form does the same for a past day: the day's attendance is re-marked straight away and the punch is highlighted as edited (reason "Edited / Added on Employee Checkin form"). One-off setup: `bench --site <site> migrate` (adds the correction fields to Employee Checkin and Shift Assignment, and the Attendance Correction Log).

**Worked on Holiday** counts days someone came in on a date in their holiday list, the same in the Detail and Summary views.

Summary cards for **one employee** read as that person's month: BS Period, Working Days in Month, Present Days (every day the person came = Working Days Present + Worked on Holiday), Working Days Present (working days only; a half day counts ½), Half Days,  Absent Days, Leave Days, Worked on Holiday (a holiday the person came in on; never a half day; its status reads "Worked on Holiday (name)"), Not Marked Days, Late Time (min), O.T. Hours, O.T. Amount. For **several employees** the same figures are sums over everybody, so each card says so ("Present Days — all 42 employees"), Employees and Present Days per Employee (avg) are added, and Working Days in Month is shown once (a range such as 25–26 when holiday lists differ). There are charts of hours worked and of statuses.

**Summary view columns:** S.N., Employee, Department, the allowance columns, **O.T. (hrs)**, **Late Time (min)** (late + left early), **Present Days** (every day came), **Working Days Present**, **Worked on Holiday**, **Leave (Current)**, **Leave (Prev Month)**, **Leave (Upto Month)**.

Rules used: late minutes count from the shift start with no grace (09:08 on a 9 AM shift = 8 minutes), only on working days worked in full. Overtime is exact to the second (never rounded) and shown only for OT-eligible staff.

## 7.3 Salary Tax and SSF Deposit

**What it is for.** Each month accounts deposits money withheld from salary. This report gives the three amounts and their deadlines.

**Filters**

| Filter | What to choose |
|---|---|
| **Company** | The company |
| **BS Year** | The **calendar** BS year of the salary month — for example **2083** for Bhadra 2083, **2084** for Baisakh 2084. (Not the fiscal year "83/84".) |
| **Salary Month** | The month the salary is **for**, picked from the list as number and name, for example **05 - Bhadra** (the report defaults to last month) |
| **Slips** | 1 - Submitted, or 0 - Draft to preview |

**Columns:** Employee, Name, PAN, SSF No., Gross Pay, **SSF Employer 20%**, **SSF Employee 11%**, **SSF Deposit 31%**, CIT, **SST (1%)**, **Remuneration Tax**, **Total Tax Withheld**, Salary Slip.

**Cards at the top:**
- **SSF to deposit · by (date)** — to the Social Security Fund, by the 15th of the next BS month;
- **SST to IRD · by (date)** and **Remuneration tax to IRD · by (date)** — to IRD, by the 25th of the next BS month;
- **CIT**.

SST is the 1% first band of income tax. It is paid only by staff **not** in SSF. The report splits each slip's income tax into its SST share and the rest. The deadlines and the split are still waiting for the accountant's final confirmation.

The report only shows figures. It does not post or deposit anything.

## 7.4 Advance Tax TDS Details

**What it is for.** The list of TDS (अग्रिम कर) deducted in a period, grouped by TDS head and account number, as needed for the IRD TDS return. It mainly covers suppliers (from purchase invoices), and also TDS posted through journal entries without a party — this is where **salary TDS from the payroll journal** appears, under the TDS-Remuneration head, with the name "**No Subledger**".

**Filters:** **Company**, **From Date**, **To Date** (you can pick in BS; the AD date is stored), **Fit Columns** (screen layout only).

**Columns:** क्र.सं. (S.No.), नाम (name), कारोबार रकम (turnover), खाता नं (account no.), अग्रिम कर रकम (TDS amount), पान नम्बर (PAN), रेट (rate).

For a salary journal row, "turnover" is the salary expense of that journal and "rate" is the TDS divided by it. For person-by-person salary tax, use **Salary Tax and SSF Deposit** instead.

The printed report has "Prepared By", "Checked By" and "Verified By" lines at the bottom.

## 7.5 Yearly Leave Details BS

**What it is for.** The yearly leave register, in the layout of the old "Yearly Leave Details" Excel sheet.

**Filters:** **Fiscal Year** (required), Company, Department, Branch, Employee, Employee Status.

**Columns:** S.No., Name Of Staff, Department, one column per BS month Shrawan → Ashadh (approved leave days taken in that month), **Total Leave Days**, **Total Yearly Leave** (days allocated for the year), **Total Worked on Holiday**, **Leave Remaining**, Remarks.

## 7.6 Work On Holiday BS

**What it is for.** How many holidays and Saturdays each person worked, month by month, for a fiscal year.

**Filters:** **Fiscal Year** (required), **OT Eligibility** (All / Yes / No — "No" shows the staff who earn replacement leave instead of overtime), Company, Department, Branch, Employee, Employee Status.

**Columns:** S.N., Name Of Staff, OT Eligibility, one column per BS month, Total.
