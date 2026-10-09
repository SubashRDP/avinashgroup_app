# 6. The salary slip, the Daily Breakdown, printing and email

[Back to contents](README.md)

## 6.1 What is on a salary slip

Open **Salary Slip** and open one slip. The main parts:

| Part | What it shows |
|---|---|
| Top | Employee, company, **Salary Month (BS)** (for example "Bhadra 2083"), **Start Date (BS)** and **End Date (BS)** with the English dates beside them, **Posting Date (BS)** |
| **Working Days** / **Payment Days** | Days in the month, and the days paid. Holidays are paid and count as payment days. An Absent day, an unpaid leave day, or half of a Half Day is taken off |
| **Earnings** | Basic, SSF Addition, the fixed allowances from the person's assignment (Dearness, HRA, Gas, Education…), and the lines from Prepare Payroll Inputs (Tea & Conveyance, Meal, Overtime) and from Payroll Adjustments |
| **Deductions** | SSF (31% of Basic), Income Tax, Late Fine, Salary Advance, and any one-off deductions |
| **Income Tax** section | **Computed Income Tax** (what the slab worked out), **Override Income Tax** and **Income Tax (manual)** (to type your own figure), **Women's Rebate Applied (%)**, **Retirement Contribution Over Cap (year)** |
| **Net Pay** | What the employee receives |
| **Daily Breakdown** | Day by day, how the month adds up to the net pay (below) |

Fixed allowances and Basic are **reduced for unpaid days** in the same proportion (payment days ÷ working days). SSF Addition and SSF are worked out from the reduced Basic.

## 6.2 The Daily Breakdown

Every slip has a **Daily Breakdown** table. It answers the employee's question "why is my pay this amount?" without anyone redoing the sums.

It has **one row per day** of the BS month, then **month-end rows**, and the last **Balance** is exactly the **Net Pay**.

| Column | Day row | Month-end row |
|---|---|---|
| **Line** | Day | Month End |
| **Miti**, **Date**, **Day** | "03 Shrawan", the English date, "Sun" | — |
| **Attendance** | "Present 07:20–18:45", "Absent", "Half Day 11:05–17:00", "Leave: Casual Leave", "Holiday: Dashain", "Not marked", "Not yet joined" | The name of the line: SSF, Income Tax, Salary Advance, Salary Arrears, Rounding… |
| **Paid Day** | How much of the day is paid: 1, ½ or 0 | — |
| **Fixed Pay** | The slip's daily rate (fixed earnings ÷ payment days) × Paid Day | — |
| **Earned** | Tea, meal, overtime earned that day | One-off earnings |
| **Deducted** | Late fine for that day | SSF, tax, advances, other deductions |
| **Detail** | For example "Tea & Conveyance 235 · Meal 2 × 75 = 150 · Overtime 1.5 h = 412.50 · Late Fine 30 min −60" | — |
| **Day Total** | That day's net | That line's net |
| **Balance** | Running total | The last one = **Net Pay** |

The table is rebuilt every time the slip is saved, and frozen when the slip is submitted.

### Rounding and Adjustment rows
- A **Rounding** row of a few paisa may appear at the end. This is normal.
- A row "**Adjustment: attendance differs from the slip's payment days**" means attendance was changed **after** the slip was made, so the days no longer match the slip's Payment Days. Open the slip and **Save** it again (while it is still a draft). The Adjustment row should disappear. If the slip is already submitted, the difference is shown honestly instead of being hidden; correct it next month or by cancelling and remaking the slip.

## 6.3 Printing a salary slip

1. Open the slip.
2. Click the **Print** icon (printer) at the top.
3. The print format **Salary Slip BS** is chosen by default. It prints:
   - **Page 1:** the payslip in Bikram Sambat — company, BS month and dates, employee details (PAN, SSF No.), earnings and deductions side by side, net pay in figures and words, and signature lines;
   - **Page 2:** the **Daily Breakdown** (दैनिक विवरण), one line per day.
4. Click **PDF** to download, or **Print**.

To print many slips: open the **Salary Slip** list, filter by Payroll Entry, tick the slips, then **Actions** → **Print**, and choose **Salary Slip BS**.

## 6.4 Emailing salary slips

Slips are **emailed automatically** when they are submitted (Payroll Settings → "Email Salary Slip to Employee" is on). The email:
- uses the email template **Salary Slip (BS)**, subject like "Salary Slip — Bhadra 2083 · Nepal Gas Udhyog Pvt. Ltd.";
- attaches the slip as a PDF in the **Salary Slip BS** layout, so the Daily Breakdown page goes too;
- goes to the employee's email on their Employee record. An employee with no email gets nothing.

**To send one slip again:** open the submitted slip → click the **⋯** menu or the envelope icon → **Email** → check the address, tick **Attach Document Print** with **Salary Slip BS**, and send.

## 6.5 Preview Salary Slip on an assignment shows less

On a Salary Structure or Salary Structure Assignment, the **Preview Salary Slip** button shows only the structure lines (Basic, SSF…). It does **not** show the person's allowances or the tea, meal and overtime. This is normal. Only a real salary slip, made from a Payroll Entry, shows everything.
