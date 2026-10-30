# Payroll demo walkthrough: DEMO Ram Test, Ashwin 2083

A test employee on **demo-nggroup.raindropinc.com**, NGI, run through one full month so the whole flow can be shown live. Open each record in the order below. Every name is a real record on that site.

Ashwin 2083 = 2026-09-17 to 2026-10-17. Holidays: the five Saturdays and Ghatasthapana (10-11). **25 working days.**

## 1. The person

| Open | Record | What to show |
|---|---|---|
| Employee | `NGI-EMP-00112` DEMO Ram Test | Plant department (posts to F/P accounts), shift 9:00–17:00, holiday list NGI-Holiday-00002, **OT Eligible** ticked. No pay on the employee. |
| Salary Structure Assignment | `HR-SSA-26-10-00015` | Basic **30,000**, Initial Basic **20,000**, SSF ticked. Allowances: HRA 25%, Gas 1,690, Education 2,780, Tea 235/day, Meal 75. |
| Employee Tax Exemption Declaration | `HR-TAX-DEC-2026-00001` | Life 50,000 declared, cut to its 40,000 limit; Health 20,000. Exempt **60,000**. |
| Employee Advance | `NGI-EADV-83/84-00001` | 10,000 advance, **2,000 a month** from Ashwin. Paid by `NGI-JE-83/84-00616`. |

## 2. The month's attendance

HR → Attendance, filter Employee = NGI-EMP-00112. All other working days are 9:00–17:00.

**Punches:** every attended day has an IN and an OUT **Employee Checkin** at the times below (48 punches, device ID `DEMO-112`, each linked to its day's Attendance). Absent days and holidays not worked have none. To show the chain punch → attendance → pay, open **Monthly Attendance BS** (NGI · 83/84 · 06 - Ashwin · employee NGI-EMP-00112): First IN / Last OUT come from these punches, then Status, Late, O.T. and Late Excused per day.

| Date | In – Out | Result |
|---|---|---|
| 09-22 | 9:20 – 17:00 | Late 20 min (fined) |
| 09-24 | 9:00 – 19:00 | 2 h overtime, on OT sheet |
| 09-29, 09-30 | — | **Absent** |
| 10-01 | 9:40 – 17:00 | Late 40 min (fined) |
| 10-03 (Saturday) | 9:00 – 17:30 | **Holiday worked** 8.5 h, on OT sheet: overtime + 2 meals |
| 10-06 | 11:30 – 17:00 | Over 2 h late, so the system made it a **Half Day** (not fined; the half day is the cost) |
| 10-08 | 9:00 – 19:30 | 2.5 h overtime, on OT sheet |
| 10-13 | 10:00 – 17:00 | Late 1 h, **Late Excused** ("bus strike"): not fined |
| 10-14 | 9:30 – 17:00 | Late 30 min (fined) |

Overtime Sheets (submitted; hours measured from the attendance on submit): `OTS-2026-00012` (09-24, 2 h), `OTS-2026-00015` (10-03, Work on Holiday, 8.5 h), `OTS-2026-00014` (10-08, 2.5 h). `OTS-2026-00013` is a cancelled first try; ignore it.

## 3. The run

| Open | Record | What to show |
|---|---|---|
| Payroll Entry | `NGI-PAYR-83/84-00035` | Company + **83/84 / 06 - Ashwin** filled the dates. Only the demo employee. Scroll to the **Payroll Inputs Log**: inputs were posted on Create Slips and again on Submit. |
| Salary Slip | `NGI-SAL-83/84-00029` | The slip below. Open the **Daily Breakdown** for the day-by-day tea, meals, OT and fines. |
| Journal Entry | `NGI-JE-83/84-00617` | The salary journal, expense on the **F/P** accounts because the department is Plant. |
| Journal Entry | `NGI-JE-83/84-00618` | The **bank entry, left as a draft**: submit it live as the last step. |

## 4. How every number on the slip is calculated

Slip `NGI-SAL-83/84-00029`. Each figure below can be checked on the slip or in its **Daily Breakdown** table.

### 4.1 Days

| Figure | Working | Value |
|---|---|---|
| Days in Ashwin 2083 | 2026-09-17 to 2026-10-17 | 31 |
| Holidays | 5 Saturdays (09-19, 09-26, 10-03, 10-10, 10-17) + Ghatasthapana (10-11) | 6 |
| **Working days** | 31 − 6 (demo Payroll Settings leave holidays out of working days) | **25** |
| Absent | 09-29, 09-30 | 2 |
| Half day | 10-06: came in at 11:30, more than 2 h after 9:00, so the system turned the day into a Half Day | 0.5 lost |
| **Payment days** | 25 − 2 − 0.5 | **22.5** |

**Proration factor** for every line that depends on payment days: 22.5 ÷ 25 = **0.9**.

### 4.2 Fixed pay (from the assignment, cut by 0.9)

| Line | Full month | Working | On the slip |
|---|---:|---|---:|
| Basic | 30,000 | 30,000 × 0.9 | **27,000.00** |
| House Rent Allowance | 5,000 | 25% of initial basic 20,000 = 5,000; × 0.9 | **4,500.00** |
| Education | 2,780 | 2,780 × 0.9 | **2,502.00** |
| GAS Allowance | 1,690 | 1,690 × 0.9 | **1,521.00** |

### 4.3 SSF

| Line | Working | On the slip |
|---|---|---:|
| SSF Addition (earning, company's 20%) | 20% × Basic on the slip 27,000 | **5,400.00** |
| SSF (deduction, 31% = 20% company + 11% employee) | 31% × 27,000 | **8,370.00** |

The employee's own cost is 8,370 − 5,400 = **2,970** (11% of 27,000). On this demo site SSF follows the cut basic; the design is SSF on the full 30,000 (6,000 / 9,300). See "Things to know".

### 4.4 The hourly rate (used by overtime and the late fine)

**Hourly basic = Basic ÷ days in the BS month ÷ 8 = 30,000 ÷ 31 ÷ 8 = 120.97**

- It uses the full basic (30,000) and the calendar days of the month (31), not the working days.
- Overtime hour = 120.97 × 1.5 = **181.45**
- Late minute = 120.97 ÷ 60 = **2.016**

### 4.5 Overtime: only on days an approved OT sheet names him

| Date | Sheet | Punches | Hours counted | Amount |
|---|---|---|---:|---:|
| 09-24 (working day) | OTS-2026-00012 | 9:00–19:00, shift ends 17:00 | 2.0 | 362.90 |
| 10-03 (Saturday holiday) | OTS-2026-00015 | 9:00–17:30, a holiday so every hour counts | 8.5 | 1,542.34 |
| 10-08 (working day) | OTS-2026-00014 | 9:00–19:30 | 2.5 | 453.63 |
| **Total** | | | **13.0** | **2,358.87** |

13 h × 181.45 = 2,358.87. The hours are measured to the second from the punches and never rounded. Without a submitted OT sheet, staying late pays nothing.

### 4.6 Late fine: every minute late on a full working day, no grace

| Date | In | Late | Fine (minutes × 2.016) |
|---|---|---:|---:|
| 09-22 | 9:20 | 20 min | 40.32 |
| 10-01 | 9:40 | 40 min | 80.64 |
| 10-14 | 9:30 | 30 min | 60.48 |
| 10-06 | 11:30 | 150 min | not fined: the day is already a half day |
| 10-13 | 10:00 | 60 min | not fined: **Late Excused** by HR |
| **Total** | | **90 min = 1.5 h** | **181.45** |

1.5 h × 120.97 = 181.45. The per-day figures add up to 181.44, and the total is rounded once.

### 4.7 Tea: rate × days present

| Count | Days |
|---|---:|
| Working days present (25 − 2 absent; the half day counts) | 23 |
| Holiday worked (10-03; tea is paid on a worked holiday) | 1 |
| **Days** | **24** |

24 × 235 = **5,640.00**. Not cut by payment days: it is already counted by days.

### 4.8 Meals: only for OT-eligible staff, only on an OT-sheet day

| Date | Rule | Meals |
|---|---|---:|
| 10-03 holiday | worked 8.5 h: 8 h or more earns 2 (6 h earns 1) | 2 |
| 09-24, 10-08 working days | 1 meal for each 1.5 h early or late. **On demo the Meal "Time Offset" is 0, so working days earn none** | 0 |

2 × 75 = **150.00**.

### 4.9 Advance

Advance 10,000, instalment 2,000, recovery from Ashwin. This month: min(2,000, 10,000 outstanding) = **2,000.00**. 8,000 is left for the coming months. Net pay can never go below 0: the recovery is cut first if it would.

### 4.10 Gross, deductions, net

| | Lines | Amount |
|---|---|---:|
| **Gross** | 27,000 + 5,400 + 4,500 + 2,502 + 1,521 + 2,358.87 + 150 + 5,640 | **49,071.87** |
| **Deductions** | 8,370 SSF + 181.45 late fine + 2,000 advance + 0 tax | **10,551.45** |
| **Net pay** | 49,071.87 − 10,551.45 | **38,520.42** |

### 4.11 Income tax: why it is 0

Each month the system projects the whole year (Shrawan to Ashadh) and taxes the year.

| Step | Working | Value |
|---|---|---:|
| This month's taxable pay | gross 49,071.87 − SSF 8,370 | 40,701.87 |
| Coming 9 months (Kartik to Ashadh) at full pay | (45,470 fixed − 9,300 SSF) × 9 | about 3,25,530 |
| Less insurance (declaration) | life 40,000 (50,000 cut to the limit) + health 20,000 | −60,000 |
| **Yearly taxable income (the slip's figure)** | | **3,08,961.87** |
| Slab | under 10,00,000 = the 1% band, waived for an SSF member | **0** |

- Tea, meals and overtime (8,148.87) are taxed in full in this month only, not projected forward.
- The SSF deducted is not taxed. The retirement cap is 5,00,000; this year's SSF is about 1,12,000, so nothing is added back.
- If he were **not** in SSF, the 1% band would apply: about 3,090 for the year.

The slip's own figure is 3,08,961.87; the rows above show how it is built and are rounded.

### 4.12 Where it goes in the books (journal `NGI-JE-83/84-00617`)

Plant department, so every expense line posts to the **F/P** accounts.

| Account | Debit | Credit |
|---|---:|---:|
| 547103 Salary Expenses – F/P | 27,000.00 | |
| 547106 House Rent Allowance – F/P | 4,500.00 | |
| 547112 Other Allowance – F/P (tea 5,640 + education 2,502 + gas 1,521) | 9,663.00 | |
| 547115 Overtime Expenses – F/P | 2,358.87 | |
| 547132 Meal Allowance – F/P | 150.00 | |
| 347302 SSF Payable (SSF Addition, **demo mapping error**) | 5,400.00 | |
| 347305 CIT Payable (SSF, **demo mapping error**: should be SSF Payable) | | 8,370.00 |
| 545200 Tax, Fines & Penalties (late fine) | | 181.45 |
| 148003 Staff Advance (instalment) | | 2,000.00 |
| 347301 Salary Payable (net pay) | | 38,520.42 |
| **Total** | **49,071.87** | **49,071.87** |

The bank entry `NGI-JE-83/84-00618` then debits Salary Payable 38,520.42 and credits the bank.

## Things to know before presenting

- **This demo site is not set up exactly like the live design:**
  - **SSF is cut for absences here.** SSF and SSF Addition are worked out on the prorated basic (27,000, not 30,000), because the demo components depend on payment days. The design is SSF on the full basic. The deck's slide 5 shows the design.
  - **Basic is prorated over working days.** Here it is 22.5 of 25 working days, because Payroll Settings excludes holidays. The deck says days in the BS month. Check which one avinas1 uses before quoting either.
  - **Wrong SSF accounts.** The journal posts SSF to **347305 CIT Payable**, and SSF Addition as a debit to 347302 SSF Payable. This is a known demo account mapping error; the accountant should fix it.
  - **No meals on working days.** Meal has Time Offset 0, so the overtime days earn none. Only the worked holiday earns meals.
- **The Daily Breakdown ends with a large "Adjustment" line (−10,912.81) on this slip.** The breakdown pays the 6 holidays and the absent days at the working-day rate, while the slip leaves holidays out (25 working days). The slip's figures are the right ones. Don't scroll to the bottom of the breakdown in front of the client, or explain it.
- **Bug fixed today.** Submit Salary Slips failed for anyone with an advance ("Cannot link cancelled document"): re-posting the inputs cancelled the old instalment while the draft slip still linked it. Fixed in `avinashgroup_app/payroll/advance_recovery.py` `clear_month`.
- **To show a late excuse live:** in Monthly Attendance BS (NGI, 83/84, Ashwin, employee NGI-EMP-00112) 10-13 shows **✓ Excused** with its reason on hover. Click **Excuse ✎** on 10-14, or open its attendance and tick Late Excused, type a reason, click Update. Its slip is already submitted, so the system refuses it with "Already Paid": that refusal is itself worth showing. To show the fine going away, use a day in a month whose slip is still a draft, or explain it.

## Removing the demo afterwards

Cancel in reverse order: delete the 48 Employee Checkins (filter employee NGI-EMP-00112) → bank entry (if submitted) → `NGI-JE-83/84-00617` → slip `NGI-SAL-83/84-00029` → `NGI-PAYR-83/84-00035` → the Additional Salaries → OT sheets → attendance → advance journal `NGI-JE-83/84-00616` → advance → declaration → assignment. Then delete the employee. The full list of records is in the scratchpad file `created.txt` from this session.
