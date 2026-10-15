# 8. Raises, one-off payments, advances, bonuses and the new year

[Back to contents](README.md)

## 8.1 Pay changes — Salary Revision

A change in pay is never an edit of the old pay. It is a **new, dated** salary assignment. **Salary Revision** makes these for many people at once: a raise in Basic or Dearness, and any change to an allowance.

**Rules**
- The **Effective From** date must be the **first day of a BS month**. A slip is paid at one rate for the whole month, so a change in the middle of a month is not possible. If you type another day, the system tells you which date to use.
- If the change is agreed late (for example it runs from Shrawan but was decided in Mangsir), the months already paid at the old pay are paid as **arrears** in one later month. Submitted slips are never changed.
- Each person listed gets **one** new assignment carrying everything the revision changes for them.

**Allowance Changes**

| Change | Who it reaches | What it does |
|---|---|---|
| **Raise Rate** | Everyone on the chosen **Salary Structure** whose rate is the structure's usual rate | Their rate becomes the **New Rate**, and so does the structure's Allowance Rate. People on a rate of their own (for example new staff's tea at 40) are **not** raised; Get Employees names them |
| **Add** | Every listed employee who does not have it | Gives the allowance at the **New Rate**, or, if blank, their structure's usual rate |
| **Stop** | Every listed employee who has it | Takes the allowance off |
| **Change Rate** | Every listed employee who has it | Sets their rate to the **New Rate** |

Overtime cannot be raised here: it is worked out from each person's Basic, so raise the Basic.

**Steps**
1. Open **Salary Revision** → **New**.
2. Choose the **Company**.
3. **Effective From**: the first day of the BS month the new pay starts. The **BS Month** fills itself.
4. **Reason**: for example "Annual increment 2083" or "Tea rate 2083".
5. For a raise in Basic: **Hike % for Everyone** (you can change each person after).
6. For allowances: add rows to **Allowance Changes** (table above).
7. If the change starts in a month already paid: tick **Pay Arrears** and set **Arrears Paid In** to a date **inside** the BS month in which the arrears should be paid.
8. Click **Get Employees**. With a Hike %, everyone with a salary is listed. Without one, only the people an allowance change reaches. Each row shows **Current Basic**, **New Basic**, **Current / New Dearness**, **Allowance Changes** (for example "Tea & Conveyance 235 → 260", "+ Gas Allowance 1690") and **Arrears**.
9. Change any row: a different **Hike %** or **New Basic** (each updates the other), a new **New DA**, or remove people. For Add / Stop / Change Rate you can also add people by hand.
10. **Save**. The Allowance Changes column and the Arrears are worked out on save. Check the totals (**Monthly Increase**, **Arrears**), then **Submit**.

**What happens on submit**
- Each person gets a new Salary Structure Assignment from the effective date, with the new Basic, the new Dearness Allowance, the allowance changes, and **all their other allowances, Initial Basic and SSF Applicable carried over**.
- A **Raise Rate** also changes the structure's Allowance Rate, so people assigned later get the new rate.
- If Pay Arrears is ticked, each person gets a **Salary Arrears** earning in the chosen month. Monthly pay (Basic, Dearness, Gas, HRA…) is owed by the days each past month actually paid, so a month with unpaid leave owes less. Tea and meal are owed by the days or meals each past month counted. The arrears are taxed in the month they are paid.

**Undo:** cancel the Salary Revision. The new assignments and the arrears are cancelled, a raised structure rate goes back, and the old pay is in force again.

| Message | Fix |
|---|---|
| "A salary revision must start on the first day of a BS month…" | Use the date the message suggests |
| "Row …: … has no salary structure assigned, so there is nothing to revise" | Give the person a Salary Structure Assignment first (Chapter 2) |
| "Row …: … already has a salary assigned from …" | Someone already has an assignment from that date. Remove the row, or cancel that assignment |
| "Row …: the new basic must be more than zero" | Type the New Basic |
| "Row …: … is listed twice" / "Row …: … belongs to …" | Remove the duplicate row / the person from another company |
| "Allowance Changes row …: … lists no rate for …, so nobody is on it" | The structure has no usual rate for that allowance. Use **Change Rate** for the people concerned |
| "Add …: … lists no rate for it; type the New Rate" | Type the rate the listed people should get |
| "… is worked out from each person's basic; raise the basic instead" | Overtime cannot be raised by rate |

## 8.2 One-off amounts in a month — Payroll Adjustment

Use **Payroll Adjustment** for amounts that are for one month only: load/unload allowance, an extra deduction, a correction. (The Dashain allowance also arrives here, as a draft made by a button: section 8.4.)

1. Open **Payroll Adjustment** → **New**.
2. Choose the **Company**.
3. **Payroll Date**: any date **inside** the BS month being paid. The **BS Month** fills itself.
4. **Reason**.
5. In **Adjustments**, one row per person and component: **Employee**, **Component**, **Amount**, **Note**.
6. Save and **Submit**.

Each row becomes an **Additional Salary** that the month's slip picks up. **Cancelling** the Payroll Adjustment takes them all back.

- Tea, meal, overtime and late fine **cannot** be chosen here; the payroll run pays those.
- One-off earnings are taxed in the month they are paid.
- Submitting (or cancelling) it updates the listed people's draft salary slips for that month by itself.

| Message | Fix |
|---|---|
| "Row …: … already has a … row — put the whole amount on one line" | Combine the two rows |
| "Row …: amount must be more than zero" | Type a positive amount. For a deduction, choose a deduction component |
| "Row …: … belongs to …" | The person is in another company |

## 8.3 Advances recovered from salary — Employee Advance

An advance is a loan. Record it **once**, when the money is given, with the monthly instalment. Payroll then takes the instalment every month until it is paid back.

1. Open **Employee Advance** → **New**.
2. Choose the **Employee**, type the **Purpose** and **Advance Amount**.
3. **Advance Account**: the company's staff advance account (148003 - Staff Advance). It must be of type **Receivable** — see the note below.
4. Tick **Repay Unclaimed Amount from Salary**.
5. In **Recovery from Salary**: type the **Monthly Instalment**, and **Recover From** (the first date recovery may start; leave blank to start with the next payroll).
6. Save and **Submit**. Then pay the money (the accountant uses the **Payment** button on the advance).

Each month, the payroll run deducts the smaller of the instalment and what is still owed, as **Salary Advance**. When the balance reaches zero, the advance becomes **Returned**. If **Monthly Instalment** is blank, the whole balance is taken in one month.

> **Accountant, please check:** the system refuses an advance whose account is not **Receivable** ("Employee advance account … should be of type Receivable"). On 9 October 2026 the 148003 Staff Advance account is typed **Payable** at NGN, NGG, NGK and GLMI, and has no type at NGI, GEPL and SGU.

## 8.4 Dashain allowance (Dashain bonus)

**The rule** (decided by the company, 13 October 2026):

- The base is **one month's basic salary**, nothing else: no allowance, overtime or grade added, no SSF, tax or advance taken off. It is the **Base** on the person's Salary Structure Assignment on the cut-off date (the figure the Basic line pays).
- Someone who has worked **one full year or more** by the cut-off date gets **100 %** of it.
- Someone with less than a year gets **days of service ÷ days in the year × basic**. Days of service = cut-off date − joining date. Days in the year = 365 (366 when the year before the cut-off has 29 February).
- Nobody ever gets more than one month's basic.
- Someone who joins on or after the cut-off date gets nothing.

Example (cut-off Ghatasthapana, 11 October 2026): Ram joined 11 April 2026, basic 30,000. Days of service 183, factor 183 ÷ 365 = 0.5014, Dashain allowance **15,041.10**. Sita joined in 2019: **30,000**.

The allowance is taxable. It is taxed in full in the month it is paid (one month's tax on it, not spread over the year).

### Where the settings are

**Salary Component → Dashain Allowance → Festival Allowance** section (HR Manager can change these; IT is not needed):

| Setting | Now | Meaning |
|---|---|---|
| Festival Allowance | ✓ | This component is paid by the Dashain Allowance button |
| Pay Month | 06 - Ashwin | The button works only on that month's Payroll Entry. Blank = any month |
| Minimum Service Days | 0 | Fewer days of service than this → nothing |
| Prorate for Under a Year | ✓ | Off = anyone who joined before the cut-off gets a full month |
| Include Daily-Wage Staff | ✗ | Daily-wage labour is paid in cash, outside payroll |
| Include Staff Leaving Before the Cut-off | ✗ | On = they are paid, counting service to their relieving date |

The rule itself (basic, 100 % cap) is not a setting.

### Paying it

1. Make the **Payroll Entry** for the pay month (Ashwin) as usual and press **Get Employees**.
2. In **Yearly Payments**, tick **Pay Dashain Allowance**, pick the **Festival Component** (Dashain Allowance) and set **Count Service To (Cut-off)**: Ghatasthapana, or the payment date. Blank = the month's last day. Save.
3. Press **Create Salary Slips**. The allowance is worked out and submitted as a **Payroll Adjustment** before the slips are made, so each slip carries it. The entry's **Dashain Payroll Adjustment** links it, and the **Payroll Inputs Log** shows how many people and the total.
4. Open the Payroll Adjustment to check: each row shows **Basic**, **Service Days** and **Factor**; the **Note** says "Full year" or "183 of 365 days".

Nobody is paid twice: someone already paid this year is left out of a later run. To undo, cancel the slips, then **Cancel** the Payroll Adjustment.

| Message | Fix |
|---|---|
| "Dashain Allowance is paid in 06 - Ashwin …; this entry is for …" | Use the Ashwin Payroll Entry, or change **Pay Month** on the component |
| "Draft … already holds Dashain Allowance for this year" | A draft from another entry exists. Delete that draft, or submit it |
| "The Payroll Entry has no employees yet" | Press **Get Employees** and save first |
| "Row …: … is more than …'s basic …; it is capped at 100 %" | Type an amount up to the Basic |

The component **Dashain Bonus** also exists. It is not a festival allowance; pick **Dashain Allowance**.

## 8.5 Leave encashment at year end

**The rule** (decided by the company, 13 October 2026; policy minute 3.7): in the last month of the fiscal year (**Ashadh**), the leave each person has **left** on every **encashable** leave type is worked out and paid on the **Ashadh salary slip**. Nothing is carried into the new year.

- **Days encashed** = the balance on the year's last day, less **Non-Encashable Leaves**, capped at **Maximum Encashable Leaves** (both on the Leave Type; 0 = no limit).
- **Rate per day** = monthly basic (Base on the salary assignment) ÷ **Encashment Days per Month** on the Leave Type. Blank = the number of days in the BS month (Ashadh: 31 or 32), the same as overtime uses.
- **Amount** = days × rate per day. Taxable, taxed in full in Ashadh.

### Where the settings are

**Leave Type → Encashment** section, for each type:

| Setting | Casual Leave | Sick Leave | Others |
|---|---|---|---|
| Allow Encashment | ✓ | ✓ | ✗ (Maternity, Paternity, Replacement, Leave Without Pay are never encashed) |
| Earning Component | Leave Encashment | Leave Encashment | |
| Maximum Encashable Leaves | 0 (whole balance) | 0 (whole balance) | |
| Non-Encashable Leaves | 0 | 0 | |
| Encash at Year End | ✓ | ✓ | |
| Encash at Separation | ✓ | ✓ | |
| Encashment Days per Month | blank (BS month's days) | blank | |

Untick **Allow Encashment** and that type is left out completely.

### Paying it (once a year, in Ashadh)

Leave encashment is paid by the payroll that pays it, the same as the Dashain allowance.

1. Wait until the last day of Ashadh has been credited (the monthly leave credit runs on the month's last day).
2. Open the **Ashadh Payroll Entry**, press **Get Employees**, tick **Pay Leave Encashment** in **Yearly Payments**, and save.
3. Press **Create Salary Slips** (on or after the first day of the payroll month). Each person's remaining balance on every encashable type is encashed and submitted, dated the year's last day, before the slips are made, so the Ashadh slip carries it.
4. The **Payroll Inputs Log** shows how many people, the total, and how many were left out (no salary assignment, no balance, already encashed). The encashments are in the **Leave Encashment** list; each shows **Balance**, **Days Encashed**, **Monthly Basic**, **Days per Month**, **Rate per Day** and **Amount**.

A later run never touches a submitted encashment, and the system refuses a second encashment of the same allocation, even typed by hand. To undo one, cancel the slip, then **Cancel** the encashment: its payment is cancelled with it.

### Someone leaving during the year

1. Set the **Relieving Date** on the Employee. Keep the status **Active** until the encashment is submitted (the system refuses an encashment for an employee who has Left).
2. In the Payroll Entry of the month they leave, tick **Pay Leave Encashment**. Everyone whose relieving date falls in the month is encashed at Separation, dated that day, at the same rate as above, when the slips are made.
3. It is paid on that month's slip (the last one).

A single leaver can also be done by hand: **Leave Encashment → New**, Employee, Leave Type, **Encashment Date = the relieving date**; the days and amount fill themselves.

| Message | Fix |
|---|---|
| "Leave is encashed at year end … or at separation …" | The date must be the allocation's last day, or the relieving date |
| "… is not encashed at year end / separation (Leave Type setting)" | Tick **Encash at Year End** / **Encash at Separation** on the Leave Type, if that is the policy |
| "… already encashes this allocation" | It has been paid. Cancel the old one first if it was wrong |
| "No Leave Period for … covers …" | IT runs the year setup, which makes the leave period |
| "Leave encashment for this month opens on …" | Wait for the payroll month to start |

## 8.6 Tax: insurance, CIT and manual tax

The limits below are the Finance Act 2083 figures for FY 2083/84, from the IRD's "Tax rate for natural persons" sheet. They were entered on avinas1 on 12 October 2026. They are records, not code: when a Finance Act changes a limit, edit the record.

| Exemption Category | Sub Category | Limit a year |
|---|---|---|
| **Insurance Premium** | Life Insurance | premium or 40,000, whichever is lower |
| | Health Insurance (Nepali insurer) | premium or 20,000, lower |
| | Private Building Insurance (own building) | premium or 10,000, lower |
| **Retirement Contribution** | CIT paid directly · Provident Fund paid directly | SSF + CIT + PF together: 5,00,000 or ⅓ of assessable income, lower |

The Insurance Premium category's own limit is 70,000, the three limits added together, so it never cuts anything. HRMS only needs it to be at least each sub-limit.

- **Insurance premiums, and CIT or PF paid outside payroll:** record them on **Employee Tax Exemption Declaration** for the person and the year (Payroll Period `83/84 - <company>`), one row per sub category with the premium actually paid. The system applies each limit itself, so a 55,000 life premium counts as 40,000. The tax on the slips that follow is reduced. In Ashadh, the **Proof Submission** (with the receipts) replaces the declaration. If a receipt is lower or missing, the tax saved earlier is taken back in that month.
- **CIT deducted through payroll:** needs a **CIT** deduction component, and on 12 October 2026 **none exists yet**. Ask IT to create it (a Deduction, ticked **Exempted from Income Tax**, with each company's account) before the first CIT deduction. Then give the person a recurring Additional Salary for it.
- **Months paid before go-live:** enter them on the person's Salary Structure Assignment as **Taxable Earnings Till Date** and **Tax Deducted Till Date** (Chapter 2.7). On 12 October 2026 Shrawan 2083 is missing for almost everyone: the Payroll Entry warns "**Tax history missing**" until it is entered.
- **Retirement contribution cap:** SSF + CIT + PF are tax-free only up to the limit above. The system adds back anything over it, and the slip shows that amount in **Retirement Contribution Over Cap (year)**. On SSF alone, this happens only above about 1,34,000 Basic a month. It is reached sooner when someone also pays CIT.
- **Women's rebate:** 10% off the tax of a woman whose **only** income is salary. Two places:
  - **who** gets it: tick **Women's Tax Rebate** on her Employee (Chapter 2). Unticked means no rebate.
  - **how much**: **Women's Rebate (%)** on the company's **Income Tax Slab**. It is 10 on all seven 83/84 slabs, set on 12 October 2026. Enter it again on each new year's slab.

  The slip shows **Women's Rebate Applied (%)**. On 12 October 2026 no one is ticked yet.
- **Not handled by payroll:** donations (the person claims them on their own tax return), children's tuition fees (25% or 25,000), remote-area deduction, disability, and the medical tax credit.
- **Changing one person's tax for one month:** on the draft slip, tick **Override Income Tax** and type **Income Tax (manual)** (Chapter 5).

## 8.7 The new fiscal year (every year, before 1 Shrawan)

The year's setup is mostly done in one step by IT, but it needs information that only HR and accounts have. Prepare these **by Ashadh**:

| # | What | Who | Deadline |
|---|---|---|---|
| 1 | **Fiscal Year** record for the new year (for example 84/85) with **all seven companies** | Accountant / IT | Before 1 Shrawan. Without it no document can be numbered in the new year. (On 9 October 2026, 84/85 does not exist yet.) |
| 2 | **Income tax rates** for the new year, from the Finance Act (budget speech, 15 Jestha): an **Income Tax Slab** per company, effective 1 Shrawan | Accountant | Jestha–Ashadh. The year setup refuses to run without it; last year's rates are never copied |
| 3 | Leave Policies for the new year per company ("Regular" and "Probation"), submitted | HR | Ashadh |
| 4 | Shift Types, and each employee's Overtime Eligible / Replacement Leave tick, still correct | HR | Ashadh |
| 5 | IT runs the **year setup**: holiday lists (all Saturdays), leave period, payroll period, new salary assignments on the new tax slab, leave policy assignments | IT | Ashadh |
| 6 | **Festivals** added to the new holiday lists with **Holiday Bulk Update**; Teej and Women's Day on the Women lists only | HR | Right after step 5, before the first festival |
| 7 | **Leave encashment** for the closing year: Ashadh Payroll Entry → **Nepal HRMS → Leave Encashment**, check, submit | HR | In Ashadh, before the Ashadh payroll (see 8.5) |
| 8 | On 1 Shrawan the companies and the women move to the new holiday lists | Automatic | Nothing to do. If a list was missing, IT sees it in the Error Log |

> **Check after step 5.** The year setup gives everyone a new salary assignment from 1 Shrawan so that the new tax rates apply. It copies the Basic, **Initial Basic**, **SSF Applicable** and the whole **Allowances** table from the old assignment. Open two or three of the new assignments and compare them with the old ones before the first payroll of the new year.
