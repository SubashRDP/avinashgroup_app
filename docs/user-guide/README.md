# HR and Payroll — User Guide

For HR staff and the accountant of the Avinash Group (Nepal Gas Udhyog and sister companies).

This guide explains how to do your daily and monthly HR and payroll work in ERPNext. It uses plain words and short steps. It does not explain how the system is built.

**Where to work:** open the ERPNext desk in your browser (on the office server, `http://localhost:8001`) and log in with your own user.

**How to find a screen:** click the search bar at the top of the desk (it says "Search or type a command"), type the name of the screen, for example `Payroll Entry`, and press Enter. Every screen named in **bold** in this guide can be found this way.

Last checked against the system: 9 October 2026 (23 Ashwin 2083).

---

## Contents

| # | Chapter | Read it when |
|---|---|---|
| 1 | [Overview, the Nepali calendar and the fiscal year](01-overview-and-calendar.md) | You are new, or you want to know how BS months and dates work here |
| 2 | [Setting up an employee for payroll](02-employee-setup.md) | A new person joins, or someone's department, category, shift or pay changes |
| 3 | [Attendance, biometric devices, leave and holidays](03-attendance-leave-holidays.md) | Every day: punches, half days, lateness, leave, holiday lists |
| 4 | [Overtime Sheets and meals](04-overtime-and-meals.md) | Staff are asked to work late, early, on a Saturday or a holiday |
| 5 | [Running the monthly payroll, step by step](05-monthly-payroll.md) | At the end of every BS month |
| 6 | [The salary slip, the Daily Breakdown, printing and email](06-salary-slip.md) | You check a slip, or an employee asks "why is my pay this amount?" |
| 7 | [Reports](07-reports.md) | You need the salary sheet, the attendance sheet, or the tax and SSF deposit figures |
| 8 | [Raises, one-off payments, advances, bonuses and the new year](08-raises-advances-bonuses-year-end.md) | Pay changes, someone takes an advance, or the fiscal year ends |
| 9 | [Accounts setup for payroll (for the accountant)](09-accounts-setup.md) | Setting accounts on salary components, the payable account, reading the payroll journal |
| 10 | [Troubleshooting: error messages and what to do](10-troubleshooting.md) | The system shows a red message, or a number looks wrong |
| 11 | [Glossary](11-glossary.md) | You meet a word you do not know (O/O, SSF Addition, Miti…) |

---

## The month in one picture

```
Every day           Punches reach the system → Attendance is marked
                    HR fixes missing punches, approves leave
When extra work     HR makes an Overtime Sheet for that date and it is approved
is needed
End of BS month     1. Check attendance (Monthly Attendance BS report)
                    2. New Payroll Entry → Company → click the month → Save
                    3. Prepare Payroll Inputs   (tea, meal, overtime, late fine, advances)
                    4. Create Salary Slips → check a few slips
                    5. Submit Salary Slip       (journal is posted, slips are emailed)
                    6. Avinas Salary Statement → must show "Matches Journal"
                    7. Make Bank Entry           (pay the staff)
By the 15th / 25th  Deposit SSF (15th) and salary tax (25th) of the next BS month
of next month       — figures from Salary Tax and SSF Deposit
```

---

## Things that are not built yet

These appear in some older documents or in conversations, but they **do not work yet**. Do not look for them on the screen:

- **Dashain Bonus button** on the Payroll Entry. Not built. (An older "Dashain Bonus" screen was removed on purpose.) Until it is built, see Chapter 8 for the temporary way to pay it.
- **Leave Encashment button** on the Payroll Entry. Not built. See Chapter 8.
- **Automatic monthly shift rotation.** There is no automatic swap. HR moves people by hand (Chapter 3).
- **Payroll for GLMI, GEPL and SGU.** These three companies have no salary structure yet. Only NGI, NGN, NGG and NGK run payroll.
- **Daily-wage labour** is paid in cash, outside payroll.

## Older documents

Some older guides (the "payroll manual", "HR payroll handbook" and "payroll documentation" pages) describe an earlier setup: pay fields on the Employee, "Allowance Category" (OLD / NEW / NO tea groups), and a Dashain Bonus screen. **That setup is gone.** Where they disagree with this guide, this guide is correct.
