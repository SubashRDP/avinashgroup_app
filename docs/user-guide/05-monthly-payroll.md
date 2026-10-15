# 5. Running the monthly payroll, step by step

[Back to contents](README.md)

Run one Payroll Entry **per company per BS month**, after the month has ended.

## 5.1 Before you start (checklist)

Do these first. Each one changes the pay, and some cannot be fixed easily after slips are submitted.

| ✓ | Check | Where |
|---|---|---|
| ☐ | Attendance for the whole month is complete and corrected | **Monthly Attendance BS** report (Chapter 7), Attendance Fix (Chapter 3) |
| ☐ | Approved leave is submitted | Leave Application |
| ☐ | Every Overtime Sheet for the month is submitted and measured | Overtime Sheet list, filter by Date |
| ☐ | New joiners have a submitted Salary Structure Assignment | Chapter 2 |
| ☐ | Raises effective this month are submitted | **Salary Revision** (Chapter 8) |
| ☐ | One-off amounts for the month (load/unload, extra tax, deductions) are submitted | **Payroll Adjustment** (Chapter 8) |
| ☐ | New advances to recover have their monthly instalment set | **Employee Advance** (Chapter 8) |
| ☐ | Every employee has a Department with a Payroll Section | Chapter 2 |

## 5.2 Step 1 — Create the Payroll Entry and choose the month

1. Open **Payroll Entry** → **New**.
2. Choose the **Company**.
3. The **month calendar** appears on the form. It shows the fiscal year's 12 BS months, Shrawan to Ashadh. Each month shows:
   - its name in English and Nepali, and the BS year;
   - its English dates (for example "17 Aug – 16 Sep");
   - a badge: **Paid** (a submitted Payroll Entry exists for it), **Draft** (a draft entry exists), or **Running** (the month we are in now);
   - links to any Payroll Entry already made for it.

   A new entry starts on the **last finished month**. Use **‹** and **›** at the top to see the previous or next fiscal year. Greyed-out months have not started yet and cannot be chosen.
4. **Click the month you are paying.** It is outlined.
   - If the month already has a payroll entry, the system asks: "**Bhadra 2083 already has payroll entry NGI-PAYR-83/84-00002. Make another one for it?**" Click **No** unless you really need a second run (for example someone was left out). Paying a month twice by accident pays everyone twice.
5. Click **Save**.

You do not type anything else. The system fills:
- **Start Date** and **End Date** — the month's first and last day (and their BS dates);
- **Posting Date** — the month's last day;
- **Payroll Frequency** — Monthly;
- **Currency**, **Payroll Payable Account** and **Cost Center** — from the company;
- the **Employees** table — everyone of the company with a salary assignment for that month.

The English date fields are locked, so the payroll cannot slip into another month.

**Check the number of employees** in the Employees table. If someone is missing, see Chapter 10, "Someone is missing from the payroll".

To pay only part of the company, set **Branch**, **Department** or **Designation** before saving, or click **Get Employees** after changing them.

## 5.3 Step 2 — Yearly payments and payroll inputs (no button)

Nothing is pressed for tea, meals, overtime, late fines or advance instalments. **Create Salary Slips** works them out from attendance and Overtime Sheets and posts them first, so every slip is made with them; **Submit Salary Slip** works them out again just before submitting, so an attendance fix made in between is paid.

In the **Yearly Payments** section of the Payroll Entry (first tab), before **Create Salary Slips**:

- **Pay Dashain Allowance** — tick it in the Dashain month, pick the **Festival Component** and the **Count Service To (Cut-off)** date (Chapter 8.4).
- **Settle Leave (encash or recover)** — tick it in Ashadh, or in a month someone leaves: leave left is paid, leave taken beyond what was earned is deducted (Chapter 8.5).

Both are paid in the same run as everything else. The read-only **Payroll Inputs Log** on the form records every run: when, by whom, the tea / meal / overtime and late-fine totals, advance instalments, the Dashain adjustment and the encashment total, for example "**2026-10-15 12:26 Slips created by hr@…: 212 attendance lines: tea / meal / overtime 1,04,960.00, late fines 5,375.40; 3 advance instalments; Dashain PADJ-2026-00001: 96 people, total 18,40,000.00**". **Dashain Payroll Adjustment** links the adjustment that paid the allowance.

What it works out, per person, for the month:

| Line | Counted from | Rate |
|---|---|---|
| **Tea & Conveyance** | Every day the person came, **holidays and Saturdays included** (Pay on Holiday = Pay on the Tea component). A Half Day counts as a full day | The Rate on the person's Tea row (usually NGI 235, NGN 265 per day) |
| **Meal** | Chapter 4, section 4.6 | The Rate on the person's Meal row |
| **Overtime** | Measured hours on submitted Overtime Sheets | Basic ÷ days in the BS month ÷ 8 × 1.5 per hour |
| **Late Fine** (deduction) | Minutes late in + minutes left early, on working days worked in full. Not on a Half Day (already a penalty), not on a day marked **Late Excused**, never for **Late Fine Exempt** staff | Per minute: Basic ÷ days in the BS month ÷ 8 ÷ 60. One minute late is charged |
| **Salary Advance** (deduction) | Each open Employee Advance set to be recovered from salary | The smaller of the monthly instalment and what is still owed |

Who gets tea and meal: anyone with a row for it on their salary assignment; no row, none. Overtime: anyone **OT eligible** who is on a submitted Overtime Sheet — no row on the assignment is needed. Late fine: everyone, except staff ticked **Late Fine Exempt** on the Employee — no line in the structure is needed, and the component's Unit and Rate Basis do not change it. Meals and overtime are only for OT-eligible staff.

**Running again is safe.** Each run replaces the month's tea, meal, overtime and late-fine lines and removes what is no longer due; amounts HR typed by hand are never touched. A Dashain allowance or encashment already paid is not paid twice. Submitted slips are never changed: cancel the slip first if it really must change.

If the log says "**… skipped (Error Log)**", some records could not be made. Ask IT to look at the Error Log; the usual causes are in Chapter 10.

## 5.4 Step 3 — Create Salary Slips

1. Click **Create Salary Slips** (the blue button).
2. This **submits the Payroll Entry** and makes one **draft** salary slip per employee. For many employees it runs in the background: the status shows **Queued**. Wait a minute and reload the page.
3. When done, the Payroll Entry shows the **Submit Salary Slip** button.

If the status becomes **Failed**, a message at the top says "Salary Slip creation failed. You can resolve the issue and retry creation." Click the word **issue** to see the error, fix it (Chapter 10), then click **Create Salary Slips** again.

If the entry refuses to submit with "**Cannot submit. Attendance is not marked for some employees.**", the entry has **Validate Attendance** ticked and some people have days with no attendance. Fix the attendance, or untick Validate Attendance if that is acceptable.

## 5.5 Step 4 — Check the slips

Before submitting, check. Submitted slips are emailed to staff and posted to the books.

1. Run **Avinas Salary Statement** (Chapter 7) for the company and month with **Slips = 0 - Draft**. It shows the whole month as the old Excel salary sheet. Compare the totals with last month (**Last Month Net** column) and look for anything unusual.
2. Open a few slips (from the Payroll Entry's **Connections**, or the **Salary Slip** list filtered by Payroll Entry). Check:
   - **Payment Days** against the person's attendance;
   - tea, meal and overtime lines;
   - **Income Tax**. To change the tax for one person, tick **Override Income Tax** and type **Income Tax (manual)**. Zero is allowed and means "no tax this month". **Computed Income Tax** keeps what the system worked out, for comparison;
   - the **Daily Breakdown** table at the bottom (Chapter 6).
3. If something is wrong:
   - **attendance or overtime wrong** → fix it; **Submit Salary Slip** works the month out again before submitting;
   - **pay or allowance wrong** → fix the person's Salary Structure Assignment (a new one if pay changed), then open the slip and **Save** it again;
   - **one-off amount missing** → add a Payroll Adjustment, then re-save the slip.

## 5.6 Step 5 — Submit the slips

1. On the Payroll Entry, click **Submit Salary Slip** and confirm.
2. The system submits every slip and posts the **payroll journal** (Journal Entry). Each person's pay is booked to their section's expense account: O/O, S/D or F/P (Chapter 9).
3. Each employee receives their slip by email, as a PDF in the "Salary Slip BS" layout, if they have an email address on their Employee record.

If submission stops with an error, nothing is half-posted. The usual messages are:
- "**Set Payroll Section on the Department of these employees…**" — the listed employees need a Department with a Payroll Section (Chapter 2);
- "**Please set account in Salary Component …**" — the accountant must add the company's account on that component (Chapter 9);
- "**Account type cannot be set for payroll payable account …**" — the accountant must clear Account Type on the payable account (Chapter 9).

Fix the cause and click **Submit Salary Slip** again.

## 5.7 Step 6 — Check against the journal

Run **Avinas Salary Statement** again with **Slips = 1 - Submitted**. The summary at the top must show a green **Matches Journal** card. If it shows red cards, read Chapter 7, section 7.1, "What a red card means", and tell the accountant.

## 5.8 Step 7 — Pay the staff

The accountant clicks **Make Bank Entry** on the Payroll Entry, chooses the bank account and posts the payment. Withheld salaries, if any, are released later with **Release Withheld Salaries**.

## 5.9 Step 8 — Deposit SSF and tax

Run **Salary Tax and SSF Deposit** (Chapter 7) for the month. It gives the SSF amount to deposit by the **15th** of the next BS month and the SST and remuneration tax to deposit with IRD by the **25th**.

## 5.10 Undoing a payroll

If a submitted payroll is wrong, cancel **in this order**, newest first:
1. the bank payment entry,
2. the payroll journal entry,
3. the salary slips,
4. the Payroll Entry.

Then fix the cause and run the month again. Tell the accountant before cancelling anything that is already posted.

## 5.11 Running a second payroll for the same month

Sometimes a person was left out (assignment made late). Make a new Payroll Entry for the same month, answer **Yes** to "Make another one for it?", keep only the missing people in the Employees table, and continue as normal. The system will not make a second slip for someone already paid that month ("Salary Slip of employee … already created for this period").
