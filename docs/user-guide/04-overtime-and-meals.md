# 4. Overtime Sheets and meals

[Back to contents](README.md)

## 4.1 The rule in one sentence

**Overtime and meals are paid only for extra work the company asked for, written on an approved Overtime Sheet.** The sheet says who was asked to work and on which date. The punches say how many hours they worked. Staying late on one's own, with no sheet, is not paid.

If someone did work extra but nobody made a sheet, make the sheet afterwards (past dates are allowed) and get it approved before payroll.

## 4.2 What each category earns

| Employee Category | Worked on a holiday or Saturday | Worked before / after the shift on a working day |
|---|---|---|
| **Operation** (OT-eligible) | Overtime for every hour worked + 2 meals | Overtime for the hours outside the shift + up to 2 meals |
| **Officer & Admin** | 1 day of **Replacement Leave** (½ day if the attendance is a Half Day) | Not allowed — the sheet refuses it |

A person never gets both overtime and replacement leave for the same day.

## 4.3 Making an Overtime Sheet

1. Open **Overtime Sheet** → **New**.
2. Fill in:
   - **Company**
   - **Date** — the day of the extra work. Past dates are fine.
   - **Department** (optional)
   - **Why Extra Work Was Needed**
3. In **Employees**, add each person who was asked to work. **Do not type any times.** Each row fills itself:
   - **Work Type** — "Work on Holiday" or "Overtime", chosen from the person's day. Change it only if it is wrong.
   - **Day** — Holiday, Weekly Off or Working Day, from the person's own holiday list.
   - **Earns** — Overtime or Replacement Leave, from the person's category.
   - **Category** and **Shift**.
4. Save. If any row breaks the policy, all the problems are listed together under "**Rows the policy does not allow**". Fix or remove those rows and save again.
5. Submit (or send for approval, if an approval chain is set up for Overtime Sheets in your company). **Only a submitted sheet counts.**

One sheet can mix people: on Teej, a woman can be on "Work on Holiday" and a man on "Overtime" on the same sheet.

### What the sheet refuses

| Message | Meaning and fix |
|---|---|
| "… has no Employee Category — set it with the Employee Category Tool first" | Set the person's category (Chapter 2) |
| "…: … is a working day for them — choose Overtime, not Work on Holiday" | The date is not a holiday for this person. Change Work Type to Overtime |
| "…: … is … for them — choose Work on Holiday, not Overtime" | The date is a holiday or Saturday for this person. Change Work Type to Work on Holiday |
| "… (…) is not eligible for overtime on a working day" | An Officer & Admin person cannot get overtime on a working day. Remove the row |
| "… has no shift on …, so overtime beyond it cannot be measured" | Give the person a shift (Chapter 2) |
| "…: category … earns nothing for holiday work" | The category has neither overtime nor replacement leave ticked. Ask the HR manager |
| "Row …: … belongs to …, not …" | The person is in another company. Use that company's sheet |
| "Row …: … is listed twice" | Remove the second row |
| "Already on another Overtime Sheet for this date: …" (Authorised Twice) | The person is already on another sheet for that date. Use that sheet |

## 4.4 How the hours are measured

After the sheet is submitted, the system reads each person's attendance for that date and writes **Worked Hours** and a **Note** on the row:

| Row | Hours |
|---|---|
| Work on Holiday | Every hour worked that day |
| Overtime | Only the hours before the shift starts and after it ends |
| Earns Replacement Leave | 0 — nothing to measure |
| No attendance | 0, note "No attendance — called in but did not come" |
| Marked absent | 0, note "Marked absent" |
| Only one punch | 0, note "Only one punch — the hours cannot be measured" |

Hours are rounded to the **nearest half hour** (7:53 → 8, 7:34 → 7.5).

Example on a 6 AM – 2 PM shift: in 06:00, out 18:00 → 4 h overtime. In 05:00, out 14:00 → 1 h. In 06:05, out 13:50 → 0 h.

**When it is measured:**
- On submit, for a date already past.
- Every night, for sheets whose attendance arrived later.
- Any time you click **Measure from Attendance** on the submitted sheet. Do this after you fix the attendance for that date. It is safe to press again.

You cannot type the hours by hand. To change them, correct the attendance, then click **Measure from Attendance**.

## 4.5 How overtime is paid

At payroll time, **Prepare Payroll Inputs** (Chapter 5) adds up each OT-eligible person's measured hours for the month and pays:

> **Overtime per hour = Basic ÷ 30 days ÷ 8 hours × 1.5**

Example: Basic 30,000 → 30,000 ÷ 30 ÷ 8 = 125 an hour × 1.5 = **187.50 per overtime hour**.

The 30, 8 and 1.5 are settings on the **Overtime** salary component ("Rate: Days per Month", "Rate: Hours per Day", "Multiplier"). Change them only with management approval.

## 4.6 Meals

A meal is part of overtime the company asked for. For each day, the meals are counted like this:

| Check | Meals |
|---|---|
| Employee is not **OT Eligible** (not in an overtime category) | 0 |
| Not on a **submitted Overtime Sheet** for that date with Earns = **Overtime** | 0 |
| Working day: punched in **1.5 hours or more before** the shift start | +1 |
| Working day: punched out **1.5 hours or more after** the shift end | +1 |
| Holiday or Saturday worked, on the Overtime Sheet | 2 |
| Any day | never more than **2** |

So 1.4 hours early earns nothing; 1.5 hours early earns one meal; early **and** late earns two.

**Meal rate:** the person's own rate on their assignment if they have one, else the company's (NGI 75, NGN 75, NGG 100 as of 9 October 2026).

The 1.5 hours and the maximum of 2 are settings on the **Meal** salary component (**Time Offset (Hours)** and **Max Meals per Day**).

## 4.7 Replacement leave for Officer & Admin

When an Officer & Admin person is on a submitted Overtime Sheet for a holiday:
- once their attendance for that day exists, the system creates and submits a **Compensatory Leave Request** for **Replacement Leave** by itself: 1 day, or ½ day if the attendance is a Half Day;
- the row shows the request in **Replacement Leave Granted** and a note "1 day of replacement leave granted";
- if attendance is not there yet, the note says "Replacement leave waits for attendance…", and the system tries again every night (for about two months);
- if it fails, the note says "Replacement leave not granted: …" with the reason.

Cancelling the Overtime Sheet takes the replacement leave back.

## 4.8 Changing a sheet

A submitted sheet cannot be edited. To change it: **Cancel**, then **Amend**, correct it, and submit again. Do this **before** the month's payroll. After payroll, a change needs the salary slip to be cancelled and made again.
