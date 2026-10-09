# 8. Raises, one-off payments, advances, bonuses and the new year

[Back to contents](README.md)

## 8.1 Pay raises — Salary Revision

A raise is never an edit of the old pay. It is a **new, dated** salary assignment. **Salary Revision** makes these for a whole company at once.

**Rules**
- The **Effective From** date must be the **first day of a BS month**. A slip is paid at one rate for the whole month, so a raise in the middle of a month is not possible. If you type another day, the system tells you which date to use.
- If the raise is agreed late (for example it runs from Shrawan but was decided in Mangsir), the months already paid at the old rate are paid as **arrears** in one later month. Submitted slips are never changed.

**Steps**
1. Open **Salary Revision** → **New**.
2. Choose the **Company**.
3. **Effective From**: the first day of the BS month the new pay starts. The **BS Month** fills itself.
4. **Reason**: for example "Annual increment 2083".
5. **Hike % for Everyone**: the percentage for all (you can change each person after).
6. If the raise starts in a month already paid: tick **Pay Arrears** and set **Arrears Paid In** to a date **inside** the BS month in which the arrears should be paid.
7. Click **Get Employees**. Everyone of the company with a salary is listed with **Current Basic**, **Hike %**, **New Basic**, **Current Dearness Allowance**, **New DA**, **Arrears Months** and **Arrears**.
8. Change any row: type a different **Hike %** or **New Basic** (each updates the other), a new **New DA**, or remove people who get no raise.
9. Check the totals (**Monthly Increase**, **Arrears**). Save, then **Submit**.

**What happens on submit**
- Each person gets a new Salary Structure Assignment from the effective date, with the new Basic, the new Dearness Allowance, and **all their other allowances, Initial Basic and SSF Applicable carried over**.
- If Pay Arrears is ticked, each person gets a **Salary Arrears** earning in the chosen month. Arrears follow the days actually paid in each past month, so a month with unpaid leave owes less. The arrears are taxed in the month they are paid.

**Undo:** cancel the Salary Revision. The new assignments and the arrears are cancelled, and the old pay (old Dearness Allowance included) is in force again.

| Message | Fix |
|---|---|
| "A salary revision must start on the first day of a BS month…" | Use the date the message suggests |
| "Row …: … has no salary structure assigned, so there is nothing to revise" | Give the person a Salary Structure Assignment first (Chapter 2) |
| "Row …: … already has a salary assigned from …" | Someone already has an assignment from that date. Remove the row, or cancel that assignment |
| "Row …: the new basic must be more than zero" | Type the New Basic |
| "Row …: … is listed twice" / "Row …: … belongs to …" | Remove the duplicate row / the person from another company |

## 8.2 One-off amounts in a month — Payroll Adjustment

Use **Payroll Adjustment** for amounts that are for one month only: load/unload allowance, an extra deduction, a correction, a festival payment.

1. Open **Payroll Adjustment** → **New**.
2. Choose the **Company**.
3. **Payroll Date**: any date **inside** the BS month being paid. The **BS Month** fills itself.
4. **Reason**.
5. In **Adjustments**, one row per person and component: **Employee**, **Component**, **Amount**, **Note**.
6. Save and **Submit**.

Each row becomes an **Additional Salary** that the month's slip picks up. **Cancelling** the Payroll Adjustment takes them all back.

- Tea, meal, overtime and late fine **cannot** be chosen here; Prepare Payroll Inputs pays those.
- One-off earnings are taxed in the month they are paid.
- Submit it **before** Create Salary Slips. If the slips already exist as drafts, open and save each affected slip, or press Prepare Payroll Inputs (which also refreshes draft slips).

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

Each month, **Prepare Payroll Inputs** deducts the smaller of the instalment and what is still owed, as **Salary Advance**. When the balance reaches zero, the advance becomes **Returned**. If **Monthly Instalment** is blank, the whole balance is taken in one month.

> **Accountant, please check:** the system refuses an advance whose account is not **Receivable** ("Employee advance account … should be of type Receivable"). On 9 October 2026 the 148003 Staff Advance account is typed **Payable** at NGN, NGG, NGK and GLMI, and has no type at NGI, GEPL and SGU.

## 8.4 Dashain bonus — not built yet

The Labour Act requires a festival allowance: one month's pay for a full year of service, a share of it for less.

- The planned **Dashain Bonus button on the Payroll Entry is not built yet.**
- The older "Dashain Bonus" screen was **removed on purpose** in September 2026.
- The **Dashain Bonus** and **Dashain Allowance** salary components still exist.

Until the button is built, the only way in the system is to work out each person's amount outside the system and enter it on a **Payroll Adjustment** (section 8.2) with the **Dashain Bonus** component, in the month it is paid (before Fulpati). Confirm with the HR manager and the accountant before doing this.

## 8.5 Leave encashment — not built yet

Leave left at the end of the fiscal year is to be **encashed**, not carried forward. The **Leave Encashment button on the Payroll Entry is not built yet.** Casual and Sick leave allocations expire at the end of Ashadh, so ask IT **before the end of Ashadh** how the year's encashment will be paid.

## 8.6 Tax: insurance, CIT and manual tax

- **Insurance premiums and CIT paid outside payroll:** record them on **Employee Tax Exemption Declaration** for the person and the year. The tax on the following slips is reduced.
- **CIT deducted through payroll:** a **CIT** deduction component (create a recurring Additional Salary for the person).
- **Women's rebate:** a percentage on the company's **Income Tax Slab** (field **Women's Rebate (%)**). On 9 October 2026 it is 0 on every slab.
- **Retirement contribution cap:** SSF + CIT + PF are tax-free only up to a limit. The system adds back anything over the cap; the slip shows it in **Retirement Contribution Over Cap (year)**.
- **Changing one person's tax for one month:** on the draft slip, tick **Override Income Tax** and type **Income Tax (manual)** (Chapter 5).

## 8.7 The new fiscal year (every year, before 1 Shrawan)

The year's setup is mostly done in one step by IT, but it needs information that only HR and accounts have. Prepare these **by Ashadh**:

| # | What | Who | Deadline |
|---|---|---|---|
| 1 | **Fiscal Year** record for the new year (for example 84/85) with **all seven companies** | Accountant / IT | Before 1 Shrawan. Without it no document can be numbered in the new year. (On 9 October 2026, 84/85 does not exist yet.) |
| 2 | **Income tax rates** for the new year, from the Finance Act (budget speech, 15 Jestha): an **Income Tax Slab** per company, effective 1 Shrawan | Accountant | Jestha–Ashadh. The year setup refuses to run without it; last year's rates are never copied |
| 3 | Leave Policies for the new year per company ("Regular" and "Probation"), submitted | HR | Ashadh |
| 4 | Shift Types and Employee Categories still correct | HR | Ashadh |
| 5 | IT runs the **year setup**: holiday lists (all Saturdays), leave period, payroll period, new salary assignments on the new tax slab, leave policy assignments | IT | Ashadh |
| 6 | **Festivals** added to the new holiday lists with **Holiday Bulk Update**; Teej and Women's Day on the Women lists only | HR | Right after step 5, before the first festival |
| 7 | **Leave encashment** for the closing year | HR + IT | Before 31 Ashadh (not built yet, see 8.5) |
| 8 | On 1 Shrawan the companies and the women move to the new holiday lists | Automatic | Nothing to do. If a list was missing, IT sees it in the Error Log |

> **Check after step 5.** The year setup gives everyone a new salary assignment from 1 Shrawan so that the new tax rates apply. It copies the Basic, **Initial Basic**, **SSF Applicable** and the whole **Allowances** table from the old assignment. Open two or three of the new assignments and compare them with the old ones before the first payroll of the new year.
