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
| **OT Hr.**, **Meal Qty.**, **Late Hr.** | Overtime hours, meals and late hours that were paid or fined |
| **Initial Basic** | From the person's assignment |
| **Basic Salary** | Full-month Basic |
| **OT Rate/ Hr.**, **Late Deduction Rate** | The person's rates |
| **Unpaid Leave** | Days not paid |
| **Deduction** | What unpaid days took off Basic |
| **Net Basic** | Basic actually paid |
| **SSF Addition** | Employer's 20% |
| HRA, Dearness Allowance, Other Allowance, Fixed, Fuel, Maintenance, Gas, Edu (and any other allowance) | Fixed allowances paid |
| **Total Allowance** | Sum of the allowances |
| **Regular Salary** | Net Basic + SSF Addition + Total Allowance |
| **Tea Conveyance**, **OT**, **Meal** (and other earnings) | Attendance-based earnings |
| **Gross Salary** | The slip's gross pay |
| **SSF**, **Tax**, **Late Fine**, **Regular Advance**, **Dashain Advance** (and any other deduction) | Deductions |
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

**Detail view columns:** BS Date, Employee, AD Date, Day, Shift (the shift on **that** date), Department, **IN** and **OUT** (first and last punch of the day), **Hours**, **Status**, **Late (min)**, **Before ofc. Time** (minutes left before shift end), **O.T. (hrs)** (only on days an approved Overtime Sheet covers), **Leave**, **Work In Holiday**, one column per attendance allowance (Tea & Conveyance, Meal, Overtime, Late Fine — the same count payroll will use), **Remarks**, **Holidays**.

IN and OUT are the first and last punch of the day, even if a punch fell outside the shift's window. So "OUT minus IN" may differ from **Hours**, which is what pay uses.

Summary cards: BS Period, Total Days Worked, Worked on Office Day, Worked on Holiday, Leave Days, Late Time (min), O.T. (hrs). There are charts of hours worked and of statuses.

**Summary view columns:** S.N., Employee, Department, the allowance columns, **O.T. (hrs)**, **Late Time (min)** (late + left early), **Present Days**, **Worked on Holiday**, **Leave (Current)**, **Leave (Prev Month)**, **Leave (Upto Month)**.

Rules used: late minutes count from the shift start with no grace (09:08 on a 9 AM shift = 8 minutes), only on working days worked in full. Overtime is rounded to the nearest half hour and shown only for OT-eligible staff.

## 7.3 Salary Tax and SSF Deposit

**What it is for.** Each month accounts deposits money withheld from salary. This report gives the three amounts and their deadlines.

**Filters**

| Filter | What to choose |
|---|---|
| **Company** | The company |
| **BS Year** | The **calendar** BS year of the salary month — for example **2083** for Bhadra 2083, **2084** for Baisakh 2084. (Not the fiscal year "83/84".) |
| **Salary Month** | The month the salary is **for** (the report defaults to last month) |
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
