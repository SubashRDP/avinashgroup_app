# 1. Overview, the Nepali calendar and the fiscal year

[Back to contents](README.md)

## 1.1 What the system does for you

| You used to… | Now the system… |
|---|---|
| Count attendance from the device printout | Receives punches from the biometric device and marks each day Present, Absent, Half Day or On Leave |
| Keep a list of who worked late or on a holiday | Keeps an **Overtime Sheet** for each date the company asked people to work extra |
| Type tea, meal, overtime and late fine into the Excel sheet | Works them out from attendance and Overtime Sheets when you press **Prepare Payroll Inputs** |
| Type the salary sheet by hand | Makes a **salary slip** per person and prints the same salary sheet layout (**Avinas Salary Statement**) |
| Ask accounts to post the salary voucher | Posts the salary journal itself, split into O/O, S/D and F/P accounts |

## 1.2 Who does what

| Person | Main work |
|---|---|
| **HR** | Employees, departments, shifts, leave, holiday lists, Overtime Sheets, salary assignments, the monthly Payroll Entry |
| **Accountant** | Accounts on salary components, the payable account, checking the payroll journal, bank payment, SSF and tax deposits |
| **Approvers** (managers) | Approve leave and Overtime Sheets, where an approval is set up for that company |

## 1.3 Companies that run payroll

| Company | Short name | Payroll |
|---|---|---|
| Nepal Gas Udhyog Pvt. Ltd. | NGI | Yes |
| Nepal Gas Udhyog (Narayani) Pvt. Ltd. | NGN | Yes |
| Nepal Gas Udhyog (Gandaki) Pvt. Ltd. | NGG | Yes |
| Nepal Gas Udhyog (Karnali) Pvt. Ltd. | NGK | Yes |
| Grihalaxmi Metal Industries Pvt. Ltd | GLMI | Not yet |
| Grishma Enterprises Pvt. Ltd. | GEPL | Not yet |
| Sambriddhi Gas Udhyog Pvt. Ltd. | SGU | Not yet |

## 1.4 BS and AD dates

The books run on the **Bikram Sambat (BS)** calendar. ERPNext stores every date in the English (AD) calendar, but the HR and payroll screens show the BS date beside it. A BS date is called **Miti** on the screens, for example "Start Date (BS)" or "Posting Date (BS)".

You will always choose the payroll **month** by its BS name (Bhadra, Ashwin…). The system works out the English dates for you. You do not need to convert dates for payroll.

## 1.5 The fiscal year

A fiscal year starts on **1 Shrawan** and ends on the last day of **Ashadh**. It is named by its two BS years, short form: **83/84** means Shrawan 2083 to Ashadh 2084.

The months, in fiscal-year order, with the English dates for **83/84** from the Nepali calendar:

| # | BS month | Nepali | English dates |
|---|---|---|---|
| 1 | Shrawan 2083 | साउन | 17 Jul – 16 Aug 2026 |
| 2 | Bhadra 2083 | भदौ | 17 Aug – 16 Sep 2026 |
| 3 | Ashwin 2083 | असोज | 17 Sep – 17 Oct 2026 |
| 4 | Kartik 2083 | कात्तिक | 18 Oct – 16 Nov 2026 |
| 5 | Mangsir 2083 | मंसिर | 17 Nov – 15 Dec 2026 |
| 6 | Poush 2083 | पुस | 16 Dec 2026 – 14 Jan 2027 |
| 7 | Magh 2083 | माघ | 15 Jan – 12 Feb 2027 |
| 8 | Falgun 2083 | फागुन | 13 Feb – 14 Mar 2027 |
| 9 | Chaitra 2083 | चैत | 15 Mar – 13 Apr 2027 |
| 10 | Baisakh 2084 | बैशाख | 14 Apr – 14 May 2027 |
| 11 | Jestha 2084 | जेठ | 15 May – 14 Jun 2027 |
| 12 | Ashadh 2084 | असार | 15 Jun – 16 Jul 2027 |

Note that **Baisakh, Jestha and Ashadh belong to the next BS year** (2084) but are still part of fiscal year 83/84.

## 1.6 Where a month's dates come from (Nepal BS Period)

Normally the system uses the Nepali calendar for each month's first and last day, as in the table above.

If the company ever needs a **different payroll cut-off** for a month (for example, the month should close two days early), HR can set it on the **Nepal BS Period** screen:

1. Open **Nepal BS Period** → **New**.
2. Type a **Period Name**, choose the **Company** (or leave it blank for all companies), and type the **BS Year**.
3. Save. All 12 months fill in with the normal calendar dates.
4. Change the **Start Date** or **End Date** of the month you need. Save.

From then on, the Payroll Entry, the salary slips, the Monthly Attendance BS report, the Avinas Salary Statement and the Salary Tax and SSF Deposit report all use your dates for that month. A company's own record wins over a record with no company.

As of 9 October 2026 no Nepal BS Period records exist, so every month follows the Nepali calendar.

> Change a month's dates **before** you run that month's payroll. Changing them after slips exist makes the slips and the entry disagree.

## 1.7 A new fiscal year must exist before the year starts

Document numbers depend on the fiscal year. If the **Fiscal Year** record for the new year (for example **84/85**, with all seven companies on it) does not exist when Shrawan starts, new documents cannot be numbered and the system shows an error. Ask the accountant or IT to create it in advance. See Chapter 8, "The new fiscal year".

## 1.8 The HR dashboard

Open the **HR** workspace. At the top you will see the HR dashboard for one BS month: head count, attendance, the **month close** steps for each company (attendance → overtime → payroll entry → slips → journal → paid), statutory deposits due, approvals waiting, and employees with missing data. Use it as your checklist.
