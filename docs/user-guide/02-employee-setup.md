# 2. Setting up an employee for payroll

[Back to contents](README.md)

An employee is paid correctly only when **all** of the items below are filled. Work through this chapter for every new joiner, and check it again whenever something about the person changes.

| # | What | Where | If it is missing |
|---|---|---|---|
| 1 | Department, with a Payroll Section | Employee → Department; Department → Payroll Section | Payroll submission stops with "Set Payroll Section on the Department…" |
| 2 | Employee Category | Employee Category Tool | Cannot be put on an Overtime Sheet; never paid overtime or meals |
| 3 | Shift | Employee → Default Shift, or a Shift Assignment | Lateness and overtime cannot be measured |
| 4 | Attendance Device ID | Employee → Attendance Device ID | Punches never reach this person; no attendance |
| 5 | Holiday List (women only) | Employee → Holiday List | Women do not get Teej / Women's Day off |
| 6 | Gender | Employee → Gender | Maternity / Paternity leave is refused |
| 7 | Salary Structure Assignment with pay and allowances | Salary Structure Assignment | Not in the payroll at all |
| 8 | Leave approver, Shift Request approver | Employee → Approvers section | Leave or shift requests cannot be approved |

**Pay is never typed on the Employee.** The Employee form holds personal and attendance details only. A person's pay lives on their **Salary Structure Assignment** (section 2.7). Someone who can edit employees does not see salaries unless they may also open assignments.

---

## 2.1 Department and Payroll Section (O/O, S/D, F/P)

Every salary cost is booked to one of three sections:

| Payroll Section on the Department | Short name on the salary sheet and accounts | Meaning |
|---|---|---|
| **Admin & Accounts** | **O/O** | Office: administration, accounts, IT, management |
| **Marketing** | **S/D** | Sales and Distribution: sales, marketing, drivers and vehicle helpers on delivery |
| **Plant** | **F/P** | Filling Plant: plant, filling, maintenance |

The section is set **once on the Department**, not on each person.

**To check or set a department's section:**
1. Open **Department** and open the department, for example "Sales/ Marketing - NGI".
2. Find **Payroll Section**. Choose Admin & Accounts, Marketing or Plant.
3. Save.

**To put an employee in a department:**
1. Open **Employee** and open the person.
2. In **Department**, choose the department **of the person's own company** (each company has its own departments, ending in -NGI, -NGN, -NGG, -NGK).
3. Save.

> **Important.** An employee with no Department, or whose Department has no Payroll Section, stops the payroll from being submitted for the whole company. On 9 October 2026 the active employees without a department were: NGG 49 (all), NGK 13, NGI 10, NGN 8. Fill these before the next payroll.

The salary sheet and the journal always use the **current** department of the employee. If you move someone to another department, the next payroll books them to the new section.

## 2.2 Employee Category — overtime or replacement leave

The category decides what a person gets for working on a holiday or a Saturday. There are two on the system:

| Category | Worked a holiday / Saturday | Worked extra on a normal day |
|---|---|---|
| **Operation** (staff below officer level) | Paid **overtime** + meals | Paid overtime + meals, if on an Overtime Sheet |
| **Officer & Admin** | One day of **Replacement Leave** (compensatory leave) | Nothing — not overtime-eligible |

The **OT Eligible** tick on the Employee is filled from the category. You cannot tick it by hand.

**To set categories for many people at once:**
1. Open **Employee Category Tool**.
2. In **Assign Category**, choose the category.
3. Narrow the list with Company, Branch, Department, Designation, or tick **Only Employees Without a Category**.
4. The list shows only people **not** already in that category. Tick the people.
5. Click **Assign Category** and confirm.

If one person cannot be saved (for example a required field is empty), they are listed and skipped. The others are still done.

**For one person:** open the Employee, set **Employee Category**, Save.

**Late Fine Exempt:** on the Employee, tick **Late Fine Exempt** for staff who are never fined for lateness (for example CEO, managers, company secretary). Their lateness is still shown in reports.

**Women's Tax Rebate:** shown only for a woman. Tick it when salary is her **only** income (no rent, business or investment income). Her income tax is then reduced by 10%, the figure on the company's Income Tax Slab. Leave it unticked if you do not know: unticked means no rebate. Ask her once a year, before Shrawan's payroll.

## 2.3 Shift

Lateness, early leaving and overtime are all measured against the person's shift for that day.

- **Default Shift** on the Employee: the person's usual shift.
- **Shift Assignment**: a dated shift that overrides the default. Most staff hold one open-ended assignment from the start of the fiscal year.

To change a shift later, see Chapter 3, section 3.7.

Settings on each **Shift Type** that HR should check:

| Field | Setting | Why |
|---|---|---|
| Begin check-in before shift start time | **180** minutes | An early arrival for overtime must still be counted |
| Allow check-out after shift end time | **240** minutes | A late check-out for overtime must still be counted. At 120, a long overtime day is marked Absent |
| Half Day If Late By (Hours) | **2** | More than 2 hours late = half day (policy) |
| Late Arrival Cutoff (forces Half Day) | **leave blank** | Older rule; a wrong time here turns many days into half days |
| Holiday List | **leave blank** | If filled, it replaces every employee's own holiday list (women would lose Teej) |
| Takes Part in Rotation | tick only for shifts that rotate monthly | See Chapter 3 |

## 2.4 Attendance Device ID

This is the number the person is enrolled under on the biometric device.

1. Open the Employee.
2. Type the number in **Attendance Device ID**. Save.

The same number cannot be used by two people of the **same company**. If you try, you see "Attendance Device ID … is already used by …". Check the device enrolment.

To fill many at once: Employee list → filter by Company → tick the rows → **Edit** → choose Attendance Device ID. Or ask IT for a Data Import.

## 2.5 Holiday List

Each company has two holiday lists per fiscal year:

| List | Who | Where it is set |
|---|---|---|
| `NGI 83/84` (and NGN, NGG, NGK) | Everyone | Company → Default Holiday List (nothing to do on the Employee) |
| `NGI Women 83/84` (and others) | Female employees | Employee → **Holiday List** |

For a woman, set **Holiday List** to her company's Women list. For a man, leave it blank.

## 2.6 Other employee fields used by HR and payroll

| Field | Used for |
|---|---|
| **Gender** | Maternity leave (female only) and Paternity leave (male only) |
| **Date of Joining**, **Relieving Date** | Who is included in a month's payroll |
| **PAN**, **SSF ID No.** | Printed on the salary slip and the Salary Tax and SSF Deposit report |
| **Leave Approver**, **Shift Request Approver** | Who may approve this person's requests. Without a Shift Request Approver, a shift request cannot be approved |
| **Preferred / Company Email** | Where the salary slip email is sent |

## 2.7 The Salary Structure Assignment — the person's pay

A person's pay is a **dated** record: the **Salary Structure Assignment**. It holds:

| Field | What to type |
|---|---|
| **Employee** | The person |
| **Salary Structure** | The company's structure, for example **NGI Staff 83/84** |
| **From Date** | The first day of the BS month the pay starts (for a joiner: the joining month's first day) |
| **Base** | The person's monthly **Basic** salary |
| **Income Tax Slab** | The company's slab for the year, for example **Nepal 83/84 - NGI** |
| **Payroll Payable Account** | The company's salary payable account, for example **347301 - Salary Payable - NGI**. Do not leave it empty: an assignment without it is silently left out of the payroll |
| **Initial Basic** (Pay Details) | The person's initial basic. House Rent Allowance is a percentage of this, not of Basic |
| **SSF Applicable** (Pay Details) | Tick if the person contributes to the Social Security Fund. Untick for the few who do not; they pay 1% social security tax (SST) instead |
| **Allowances** table | One row per allowance the person gets — see below |

**To create one:**
1. Open **Salary Structure Assignment** → **New**.
2. Fill the fields above.
3. Add the allowance rows.
4. Save, check, then **Submit**. Only a submitted assignment is used.

A pay change is **never** an edit of the old assignment. It is a new assignment from a new date (use **Salary Revision**, Chapter 8). The old one stays as the record of what was paid before.

### What the salary structure holds

A structure is a **template**. It pays nobody an allowance by itself.

**Earnings and Deductions**: what HRMS works out by formula for everyone on it.

| Line | How it is worked out |
|---|---|
| Basic | The assignment's Base, reduced for unpaid days |
| SSF Addition | 20% of Basic, if SSF Applicable (the employer's share, added to gross) |
| SSF (deduction) | 31% of Basic, if SSF Applicable (20% employer + 11% employee) |
| Income Tax | From the Income Tax Slab |
| Late Fine (deduction) | From attendance (Chapter 5) |

An allowance cannot be put in Earnings: "**… is an allowance. List its rate under Allowance Rates…**".

**Allowance Rates**: the **usual rate** of each allowance for people on this structure.

| Allowance | Rate | Unit |
|---|---|---|
| Tea & Conveyance | 235 | per day present |
| Meal | 75 | per meal |
| Gas Allowance | 1,690 | per month |
| House Rent Allowance | 25 | % of initial basic |
| Dearness Allowance | 0 | per month — differs for every person |
| Overtime | 0 | from basic × 1.50 — worked out, never typed |

When you pick an allowance on someone's assignment, its Rate is filled in from this list. That is all the list does for pay. It is also what a **Salary Revision** raises (Chapter 8).

On a submitted structure you can add or remove an allowance in this list, but you cannot change an existing rate here: "**Use a Salary Revision**". The revision raises the people at that rate too.

### The Allowances table: what this person gets

| Column | Meaning |
|---|---|
| **Allowance** | The allowance (only allowances can be chosen) |
| **Rate** | What **this person** is paid, in the unit shown. Filled in from the structure's rate when you pick the allowance; change it for this person |
| **Unit** | Shown automatically: per month, per day present, per meal, % of initial basic, or "from basic" |
| **From Date** | Leave blank to start with the assignment. Type a later date if the allowance starts later |

**No row means the allowance is not paid.** Payroll reads only this table.

**Examples (NGI):**
- Dearness Allowance, Rate 7,380 → 7,380 a month. The structure has no usual dearness, so type it.
- Gas Allowance → Rate fills in 1,690 → 1,690 a month.
- House Rent Allowance → Rate fills in 25 → 25% × this person's Initial Basic.
- Tea & Conveyance → Rate fills in 235; change it to 40 for a newer staff member.
- No Tea row → no tea for this person.

A row left at 0 is filled from the structure when you save. If the structure has no rate for it either, the save stops: "**type …'s rate for this person, or remove the row if they do not get it**".

### The allowance kinds

Each allowance has a **kind**, set on its Salary Component. The kind decides how it is counted:

| Kind | Examples | How it reaches the slip |
|---|---|---|
| Monthly | Dearness, Other, Fixed, Fuel, Maintenance, Transport, Gas, Education | The row's Rate every month, reduced for unpaid days |
| % of Initial Basic | House Rent Allowance | Rate % × Initial Basic, reduced for unpaid days |
| Per Day Present | Tea & Conveyance | Days counted from attendance × Rate, by **Prepare Payroll Inputs** |
| Per Meal | Meal | Meals counted from attendance and Overtime Sheets × Rate, by **Prepare Payroll Inputs** |
| Per Overtime Hour | Overtime | Hours from approved Overtime Sheets × the person's basic per hour × 1.5, by **Prepare Payroll Inputs** |
| Entered by Hand | Load/Unload Allowance | Typed each month on a **Payroll Adjustment** (Chapter 8) |
| Yearly | Dashain Bonus, Dashain Allowance, Leave Encashment | Their own buttons — **not built yet** (Chapter 8) |

"Entered by Hand" and "Yearly" allowances cannot be put on an Allowances table or a structure's Allowance Rates.

### Usual rates (as of 12 October 2026)

On each company's salary structure, under **Allowance Rates**:

| Allowance | NGI | NGN | NGG | NGK |
|---|---|---|---|---|
| Tea & Conveyance (per day) | 235 | 265 | — | — |
| Meal (per meal) | 75 | 75 | 100 | — |
| Gas Allowance (per month) | 1,690 | 1,690.27 | — | — |
| Education Allowance (per month) | 2,780 | 1,250 | — | — |
| House Rent Allowance (% of Initial Basic) | 25% | 27% | — | — |

"—" means the structure lists no usual rate. Always check the structure for the current figure.

### Adding a new kind of allowance

1. Open **Salary Component** → **New**. Type the name, Type = Earning.
2. Tick **Is Allowance** and choose the **Allowance Kind**.
3. In **Accounts**, add a row for each company that pays it: Company and the three accounts (Admin & Accounts, Marketing (S/D), Plant (F/P)).
4. Save.
5. If there is a usual rate, add it to the **Allowance Rates** of each structure that has one.
6. Give it to people: a row on each person's assignment, or a **Salary Revision** with **Add** for many at once (Chapter 8).

No new field and no new structure is needed.

## 2.8 Checklist for a new joiner

1. Create the **Employee**: company, name, gender, date of joining, department, designation, PAN, SSF ID No., email.
2. Set the **Employee Category** and, if needed, **Late Fine Exempt**.
3. Set the **Default Shift** (or a Shift Assignment from the joining date).
4. Type the **Attendance Device ID** after enrolling the person on the device.
5. For a woman, set the **Holiday List** to the company's Women list.
6. Set **Leave Approver** and **Shift Request Approver**.
7. Create and submit the **Salary Structure Assignment** with Base, Initial Basic, SSF Applicable, Payroll Payable Account and allowances.
8. Leave is credited automatically at the end of each BS month (Chapter 3).
