# Payroll work, 12 October 2026 (complete record)

Everything decided, built, fixed, found and left open in the 12 October 2026 session on HRMS for avinashgroup_app (site **avinas1**). Read it top to bottom to check each item. Every change listed here is committed on `develop` and pushed to `upstream`.

**Where to look for more:**

| What | Where |
|---|---|
| How the whole system works, check-in to bank: what, why, where, impact | [docs/system-reference/README.md](system-reference/README.md) |
| Code map: every function on the salary path, with file:line links | [docs/salary-code-map.md](salary-code-map.md) (and the CodeTour `.tours/salary-calculation.tour`) |
| The HR user guide | [docs/user-guide/README.md](user-guide/README.md) |
| Allowance design | [docs/allowances.md](allowances.md) |
| Calculation diagram (SSF, tax, OT, late fine) | https://claude.ai/artifact/MwKMh42nED93MCGxndagd7 |

---

## Contents

1. [Commits in this session](#1-commits-in-this-session)
2. [Allowances: rate on the structure, person's rate on the assignment](#2-allowances-rate-on-the-structure-persons-rate-on-the-assignment)
3. [Overtime and late fine: actual days of the BS month, not 30](#3-overtime-and-late-fine-actual-days-of-the-bs-month-not-30)
4. [Labour Act: is ÷30 required? No](#4-labour-act-is-30-required-no)
5. [Tax reliefs, FY 2083/84](#5-tax-reliefs-fy-208384)
6. [Women's tax rebate on the Employee](#6-womens-tax-rebate-on-the-employee)
7. [The HR audit (agent acting as client HR)](#7-the-hr-audit-agent-acting-as-client-hr)
8. [The system reference (agent-written documentation)](#8-the-system-reference-agent-written-documentation)
9. [Six fixes from the audit](#9-six-fixes-from-the-audit)
10. [Data changed on avinas1](#10-data-changed-on-avinas1)
11. [A mistake, and its cleanup](#11-a-mistake-and-its-cleanup)
12. [Tests](#12-tests)
13. [Still open](#13-still-open)
14. [How to check each item yourself](#14-how-to-check-each-item-yourself)

---

## 1. Commits in this session

Oldest first. All are on `develop` and pushed to `upstream`.

| Commit | What |
|---|---|
| `975437c` + merge `6f0473d` | Allowance rates: the structure lists the usual rate, the assignment holds the person's (section 2) |
| `859bec0` | Salary code map and CodeTour |
| `c82193b` | Overtime and late fine use the BS month's actual days, not 30 (section 3) |
| `4d6af9a` | Guide: FY 83/84 tax exemption limits (section 5) |
| `5f54331` | Women's tax rebate: a tick on the Employee (section 6) |
| `57ab2d3` | Six fixes from the HR audit (section 9) |
| `80e6ced` | System reference docs, plus link tools (section 8) |
| *(this file)* | This record |

---

## 2. Allowances: rate on the structure, person's rate on the assignment

### The rule, agreed in the session

| Record | Holds | Does not hold |
|---|---|---|
| **Salary Component** (e.g. Tea & Conveyance) | The **rule**: kind (how it is counted), accounts, unit | Any rate |
| **Salary Structure** → **Allowance Rates** table | The **usual rate** for people on that structure | Who gets what |
| **Salary Structure Assignment** → **Allowances** table | **What this person gets and at what rate**. No row means not paid | — |

- **One meaning per field.** A rate of 0 means 0. The old "blank = company rate" and "unticked = not paid" are gone.
- **The structure does not decide who gets what.** People have 27 different combinations of allowances; some have gas and some don't, some have rent and some don't. The structure only pre-fills the rate when an allowance is picked on an assignment. It is also the anchor for bulk raises.
- **Kinds** (how an allowance is counted): Monthly, % of Initial Basic, Per Day Present (tea), Per Meal, Per Overtime Hour, Entered by Hand, Yearly.

### Changing an allowance: Salary Revision

All allowance changes go through **Salary Revision** → **Allowance Changes** table:

| Change | Does |
|---|---|
| **Raise Rate** | New usual rate on the structure. Only people **at the default rate** move. Anyone on a personal rate is left alone and listed |
| **Add** | Gives the allowance to people |
| **Stop** | Takes it away |
| **Change Rate** | Sets one person's rate |

Arrears: monthly allowances by payment days; tea and meal by the attendance quantity already paid.

### Guards

- A structure's rate cannot be edited after submit except through a Salary Revision (`guard_structure_rates`).
- An allowance cannot be put in a structure's Earnings/Deductions; it belongs in the Allowance Rates table.
- An assignment row with rate 0 is filled from the structure, or refused with "type X's rate for this person, or remove the row".

### Migration (patch `allowance_rate_list`)

Every one of the 195 employees' pay inputs was compared before and after: identical (total 2,422,537.33; 704 attendance rates). Falgun parity was unchanged by the migration.

**Code:** `payroll/allowance.py`, `payroll/attendance_allowance.py`, `payroll/salary_slip.py`, `payroll/onboarding.py`, `payroll/year_rollover.py`, doctype `salary_revision`, new child doctypes Structure Allowance Rate and Salary Revision Allowance, `public/js/salary_structure.js`, `public/js/salary_structure_assignment.js`, patch `patches/allowance_rate_list.py`.

---

## 3. Overtime and late fine: actual days of the BS month, not 30

**Decision (yours):** "DONT KEEP 30 KEEP ACTUAL DAYS".

> **OT per hour = Basic ÷ days in that BS month ÷ 8 × 1.5**
> **Late fine per hour = Basic ÷ days in that BS month ÷ 8**

- The days are those of the month whose attendance is being priced, the same length the slip uses to cut Basic for an absent day.
- The component setting **Rate: Days per Month** stays. Blank means actual days; a number (e.g. 30) fixes it. It was cleared on Overtime by patch `rate_on_actual_month_days`.
- Example (Basic 13,369.67, Bhadra, 31 days): late fine 55.71 → **53.91** an hour; OT 83.56 → **80.86** an hour. A 30-day month is unchanged.
- **Effect:** in 29-, 31- and 32-day months, OT and late fine differ slightly from the old Excel sheets. This is intended.

**Late fine rules as built** (for checking):
- It counts late minutes plus early-exit minutes, only on full working days.
- It is not charged on a Half Day, a holiday, a day marked Late Excused, or for staff ticked Late Fine Exempt.
- There is no grace period, and more than 2 hours late makes the day a Half Day.
- Open questions are in section 13.

**Code:** `payroll/attendance_allowance.py` → `_hourly_basic`, `_resolve_rate`; test `test_hourly_wage_uses_the_months_actual_days`.

---

## 4. Labour Act: is ÷30 required? No

Old code comments said "÷30 is the Labour Act hourly wage". I checked the official texts:

| Source | Says |
|---|---|
| Labour Act 2074 s.28 | 8 hours a day, 48 a week (our **8**) |
| Labour Act 2074 s.30 | Overtime at most **4 h a day, 24 h a week** |
| Labour Act 2074 s.31(1) | Overtime paid at **1.5 × basic remuneration** (our **× 1.5**) |
| Act and Labour Rules 2075, whole text | **No divisor at all.** Nothing says 30, 26 or days in the month |

So ÷30 was only the Excel habit. Actual days is legal, and it is the company's choice. No field in the live system still claims otherwise.

Sources: [Labour Act 2074, Labour Court PDF](https://labourcourt.gov.np/assets/uploads/ea43b3437b12a2cb4a51a4cd154c428c.pdf) · [Labour Rules 2075, amended to Shrawan 2080](https://www.moljpa.gov.np/public/uploads/9e22ac3d-55cf-4f2c-833f-8cb8c7c2349f.pdf)

---

## 5. Tax reliefs, FY 2083/84

### Official figures (read from the IRD's own PDFs)

Source: IRD "Tax rate for natural persons FY 2083/84" and the revised Finance Act 2083 handbook (26 Asoj 2083), [ird.gov.np](https://ird.gov.np/category/taxrateincentives/).

**Slabs:** 1% up to 10 lakh (waived for SSF contributors) · 10% 10–15 L · 20% 15–25 L · 27% 25–40 L · 29% above 40 L. There is one schedule for everyone. Our `Nepal 83/84 - <ABBR>` slabs **match**.

| # | Relief | Rule | Changed in 2083? | In the system |
|---|---|---|---|---|
| 1 | Retirement contribution (SSF + CIT + PF together) | Up to **5,00,000 or ⅓ of assessable income**, whichever is lower | No | ✅ **On** (category Retirement Contribution) |
| 2 | Life insurance | Premium or **40,000**, lower | No | ✅ **On** |
| 3 | Health insurance (Nepali insurer) | Premium or **20,000**, lower | No | ✅ **On** |
| 4 | Private building insurance (own building) | Premium or **10,000**, lower | **Yes, 5,000 → 10,000** | ✅ **On** |
| 5 | Children's tuition fee | 25% of the fee or 25,000, lower | **New** | ❌ Not built (HRMS can't apply the 25%) |
| 6 | Donation to tax-exempt bodies | Up to 3,00,000 (and the 5% limit) | **Yes, 1 L → 3 L** | ❌ Left out: the person claims it on their own return |
| 7 | Women's rebate | **10% off the tax** of a woman whose only income is salary | No | ✅ **On** (section 6) |
| 8 | Remote area | क 50,000 · ख 40,000 · ग 30,000 · घ 20,000 · ङ 10,000 | No | ❌ Not built; only if a site qualifies |
| 9 | Person with disability | Tax-free limit +50% | No | ❌ Not built; only if someone qualifies |
| 10 | Medical tax credit | 15% of the bill or 750, lower | No | ❌ Not worth it |
| 11 | Pension, foreign allowance | — | — | Not relevant to our staff |

### What was entered on avinas1 (data, not code; HR can edit)

| Exemption Category | Sub Category | Limit |
|---|---|---|
| **Retirement Contribution** (ticked "Retirement Contribution (s.63 cap)", cap 33.333333% of income) | CIT paid directly · Provident Fund paid directly | Category max **5,00,000** |
| **Insurance Premium** | Life 40,000 · Health 20,000 · Private Building 10,000 | Category max **70,000** = the three added together, so it never cuts anything. HRMS refuses a category limit below any sub-limit |

### Proof (rolled-back tests)

- Insurance declared at 55k / 12k / 15k was counted as **40k / 12k / 10k**: annual taxable income fell from 11,90,256 to 11,28,256.
- CIT of 4,00,000 paid outside payroll, on top of SSF: **1,35,612** over the cap was added back.
- **Nobody's tax changes today.** SSF alone reaches the 5-lakh cap only above about **1,34,000 Basic a month**; the highest Basic is 58,225.

**How HR uses it:** make an **Employee Tax Exemption Declaration** per person per year with the premium actually paid; the system applies the limits. In Ashadh the **Proof Submission** replaces it. If a receipt is lower or missing, the tax saved earlier is taken back in that month.

---

## 6. Women's tax rebate on the Employee

**Decision (yours):** "women rebate should be in employee doctype".

| Where | What |
|---|---|
| **Employee → Women's Tax Rebate** (new tick, shown only for Female) | **Who** gets it. HR ticks it when salary is her **only** income. Unticked means no rebate |
| **Income Tax Slab → Women's Rebate (%)** | **How much**, per year from the Finance Act. It is **10** on all seven 83/84 slabs |

Guards:
- Saving an Employee ticked but not Female is refused.
- Even if a tick reaches the database another way, the slip gives nothing unless the person is Female.
- The slip shows **Women's Rebate Applied (%)**.

**Today: 0 of 21 women are ticked.** HR must ask each one. Asha Goyal has two Employee records (NGI-EMP-00008 and NGG-EMP-00045); tick both if she has no other income.

**Code:** `payroll/tax_relief.py` → `women_rebate_fraction`, `validate_womens_tax_rebate`; patch `women_rebate_on_employee`; hook on Employee validate.

---

## 7. The HR audit (agent acting as client HR)

An agent played the client's HR manager, told to be brutal and back every claim with evidence. It was read-only.

**Verdict:** HR could not run next month's payroll alone yet.
- **Fixed pay is right.** It matches the Excel to within Rs 1 for 143 of 164 at NGI/NGN and 40 of 49 at NGG/NGK.
- **What's broken is mostly setup data.**

### Blockers

| # | What | Kind |
|---|---|---|
| B1 | No attendance arrives: 0 devices, 0 check-ins, 261 of 265 with no shift, no attendance after 16 Aug. Everyone is paid in full; tea, meal, OT and fine come out 0 | Setup |
| B2 | Only 2 of 265 are OT Eligible; 261 have no Employee Category (Falgun paid OT to 77) | Setup |
| B3 | Pressing Prepare Payroll Inputs again left stale amounts | **Code: fixed** (section 9) |
| B4 | NGG and NGK cannot submit slips: no salary component accounts | Setup |
| B5 | NGN fails as soon as tea or meal is paid: accounts missing | Setup |
| B6 | No leave can be granted: no leave policy, period or allocation | Setup |
| B7 | Tax ignores months paid before go-live (Bikash Sharma 1,730/month instead of about 2,487) | **Code warns now** (section 9); the figures are accounts' |
| B8 | Managers would be fined for lateness: nobody is ticked Late Fine Exempt | Setup |
| B9 | 70 active staff have no Salary Structure Assignment (e.g. Tirtha Khadka, NGK); Abhishek Khadka is missing Fuel 6,123 | Setup |
| B10 | Advances not carried over (22 people, Rs 69,290 in Falgun); Staff Advance account is the wrong type at NGN/NGG/NGK | Setup |

### Serious gaps

- **Half Day by hand:** paid in full unless "Status for Other Half = Absent". This is now documented (section 9).
- **Dashain is now:** there is no clean way to pay before the month closes. Leave encashment is not built.
- **No CIT component exists** (now documented).
- **People data:** 43 staff have no bank account, nobody has an email, 45 have no PAN, 80 have no SSF ID.
- **Bhadra was called a test month, but its journals are submitted** (NGI 26.7 L, NGN 14.9 L). If Bhadra was really paid from Excel, the books count it twice. **Your decision.**
- **Holiday lists for 83/84** are missing Shivaratri, Ram Nawami, New Year 2084 and Labour Day.

### Excel (Falgun 2082) vs system

| Person | Difference | Reason |
|---|---|---|
| NGI0002 Bikash Sharma | Tax 7,500 vs 1,730 | Tax history missing (B7) |
| NGI0008 Asha Goyal | Tea 4,700 vs 0 | No attendance |
| NGI0037 Abhishek Khadka | 29,539.80 vs 23,416.80 | Fuel row missing |
| NGI0001 CEO | 257,040 vs 132,925 | Suspected anomaly in the Excel sheet itself |
| NGN0002 Mahesh Madai (non-SSF) | Excel pays SSF Addition 3,370 in cash | **Your decision:** does a non-SSF person get the 20%? |
| NGG Shanta Kumar Chaudhary | Basic 12,843.50 vs 12,530.67 | Assignment probably copied from another person |
| NGK Tirtha Bahadur Khadka | Not in payroll | No assignment |

**Fine as is:** proration for joiners and leavers, absent days cut, SSF 20%/31%, SST for non-SSF staff, the journal split by section, the Salary Statement and Tax/SSF deposit reports, Payroll Settings.

---

## 8. The system reference (agent-written documentation)

`docs/system-reference/` has 13 files and about 3,500 lines. For every piece it gives what it does, why, where (file:line), what triggers it, what it reads and writes, what it affects, its config on avinas1, and known gotchas.

| File | Covers |
|---|---|
| README.md | Pipeline diagram, "trace a rupee" table, index |
| 01-masters.md, 01b-pay-masters.md | Employee fields, holidays, shifts, leave, BS calendar; Payroll Settings, slab, exemptions, components, structures, assignments, 48 patches |
| 02 … 09 | Check-in → attendance, shift measurement, overtime, Payroll Entry, Salary Slip (worked example NGI-SAL-83/84-00004 to net 41,282.62), after the slip, changes over time, cross-cutting |
| impact-matrix.md | About 110 fields and settings: value, writer, reader, what moves if changed |
| hooks-inventory.md | Every HR/payroll hook, in execution order |

All 1,475 links are verified. After any code change, run:

```bash
python3 docs/tools/reanchor_reference_links.py   # re-point moved line numbers
python3 docs/tools/check_reference_links.py      # must say failures: 0
python3 docs/tools/build_code_map.py             # regenerates salary-code-map.md + CodeTour
```

**Its main findings** (beyond the audit):

| Finding | Status |
|---|---|
| **The scheduler is off on avinas1** (last job 2026-07-17). Nightly OT measuring, replacement-leave grants, BS leave accrual and the holiday-year switch have never run | ✅ confirmed; **your decision** |
| **The read replica is off** (`read_from_replica: 0`); its runbook was deleted in 601b374c. CLAUDE.md still says 1 | ✅ confirmed |
| Allowance rows going stale on a re-saved slip | **Fixed** (section 9) |
| Stale rows on a re-press of Prepare Payroll Inputs | **Fixed** |
| No **84/85 Fiscal Year**: numbering of Attendance, slips and Payroll Entries fails from 2027-07-17 | Open |
| New-year slab dropped the women's rebate | **Fixed** |
| Replacement leave can't be granted (no Leave Period) | Open (setup) |
| No approval workflow active: Overtime Sheets submit with no approver | Open |
| Permission gap on Prepare Payroll Inputs and the holiday-flag rebuild | **Fixed** |
| Guide disagreeing with code | **Fixed** (section 9) |
| Dead code: `custom_daily_wage`, `get_authorised` / `was_authorised`, `get_measured_hours`, `overtime_eligibility`, the "Remove Holiday" path, and two doctype leftovers | Open, harmless |
| Two pay-shaping Payroll Settings and `custom_pan` / `custom_ssf_id_no` exist only as site data, with no patch | Open |

---

## 9. Six fixes from the audit

Commit `57ab2d3`.

| # | Problem | Fix | Proof |
|---|---|---|---|
| 1 | **Prepare Payroll Inputs pressed again left old amounts.** When a correction brought tea, meal, OT or a fine to zero, the loop skipped the person before deleting last press's record, so it stayed paid | The old record is now deleted **first**, for every person and component; a new one is made only if something is due. The message adds "… earlier records removed: nothing is due for them now." A month whose slips are submitted is still refused (correct) | Tea 160 paid → person marked absent → pressed again → **removed** |
| 2 | **A re-saved draft slip kept old allowance amounts.** After payment days changed, Dearness etc. stayed at last save's proration while gross moved | The hook rebuilds the allowance rows on every save | 2 absences: Dearness **13,635 → 12,755.32** (29/31), rows match gross |
| 3 | **Tax ignored months paid before go-live** | Payroll Entry now warns **"Tax history missing"** and names everyone whose earlier months of the year have no slip and no opening. Openings go on the Salary Structure Assignment: **Taxable Earnings Till Date** (taxable pay after SSF) and **Tax Deducted Till Date**, both editable after submit | Finds **83 of 87 at NGI, 63 of 63 at NGN** (Shrawan missing). An opening clears the person; the first month of the year raises nothing |
| 4 | **Anyone logged in could press Prepare Payroll Inputs; the holiday-flag rebuild had no check** | The button needs read on the Payroll Entry and create on Additional Salary, and is hidden from anyone without it. `recompute_holiday_flags` needs write on Attendance | A Guest call is refused |
| 5 | **The new year's tax slab had no women's rebate** | `WOMEN_REBATE_BY_YEAR` in `payroll/income_tax.py` sits beside the rates; the year setup writes it and refuses a year with rates but no rebate | Test slab came out at 10% |
| 6 | **Guide disagreed with code** | Corrected in chapters 2, 3, 5, 7, 8 and 10 (list below) | — |

The guide corrections:
- **Joiner:** the assignment starts on the **joining date**.
- **Half Day by hand:** set **Status for Other Half = Absent**, or it is paid in full.
- **Late Excused:** a submitted Attendance must be **Cancel → Amend** to tick it.
- **Attendance Fix skips holidays:** use **Repair from Check-ins** on those days. A holiday **added** for a past date is handled by Holiday Bulk Update.
- **Teej / women's list:** the fix steps are corrected.
- **No CIT component exists yet:** ask IT.
- **Opening tax figures:** how to enter them.
- **Tax/SSF report's month filter:** it reads like "05 - Bhadra".
- **Troubleshooting:** rows added for "Tax history missing" and the permission message.

**Code:** `payroll/attendance_allowance.py` (`create_additional_salaries`, new `_priced`, `_delete_existing_draft` returns a count, `trigger_for_payroll_entry`, `recompute_holiday_flags`), `payroll/salary_slip.py` (`add_employee_allowances`), `payroll/income_tax.py` (`tax_history_gaps`, `warn_missing_tax_history`, `WOMEN_REBATE_BY_YEAR`), `payroll/payroll_entry.py`, `hr/year_setup.py`, `public/js/payroll_entry.js`, `scripts/check_year_rollover.py`.

---

## 10. Data changed on avinas1

| When | Change |
|---|---|
| migrate | Patches `allowance_rate_list`, `rate_on_actual_month_days`, `women_rebate_on_employee` |
| 12 Oct | Exemption categories Retirement Contribution and Insurance Premium, plus 5 sub-categories (section 5) |
| 12 Oct | `custom_women_rebate_percent = 10` on all seven `Nepal 83/84 - <ABBR>` slabs |
| 12 Oct | Removed 9 test Attendance rows, 3 Deleted Document rows and 28 test Error Log rows (section 11) |

No Employee, assignment, slip, journal or payroll entry was changed by hand.

---

## 11. A mistake, and its cleanup

The allowance engine (`create_additional_salaries`) calls `frappe.db.commit()` itself. My "rolled back" test scripts therefore **saved** 9 test Attendance rows (Absent, 22–26 Sept 2026) for NGI-EMP-00080, NGI-EMP-00001 and NGI-EMP-00002.

- They were found and deleted, along with the audit's test Error Logs. A recheck shows nothing left behind.
- The test now stubs `frappe.db.commit` so it cannot leak again.
- **For anyone writing tests:** a script that calls the engine must stub `frappe.db.commit`.

---

## 12. Tests

43 tests, all passing:
- `payroll/test_allowance.py`: 25
- `payroll/test_payroll_checks.py`: 13, including the new re-press, permission, proration, tax-history and new-year-slab tests
- `payroll/test_tax_relief.py`: 5 (women's rebate, insurance caps)

`bench run-tests` fails on this bench while building test records, so run the suites directly:

```bash
cd /home/dell/frappe-v15/sites
cat > /tmp/run.py <<'EOF'
import sys, unittest, frappe
frappe.init(site="avinas1", sites_path="."); frappe.connect(); frappe.flags.in_test = True
s = unittest.TestSuite()
for n in sys.argv[1:]: s.addTests(unittest.defaultTestLoader.loadTestsFromName(n))
ok = unittest.TextTestRunner(verbosity=2).run(s).wasSuccessful()
frappe.db.rollback(); sys.exit(not ok)
EOF
../env/bin/python /tmp/run.py avinashgroup_app.payroll.test_payroll_checks avinashgroup_app.payroll.test_allowance avinashgroup_app.payroll.test_tax_relief
```

---

## 13. Still open

### Your decisions

| # | Question |
|---|---|
| D1 | **Turn the scheduler on** for avinas1? Without it, OT measuring, replacement leave, leave accrual and the holiday-year switch never run |
| D2 | **Was Bhadra paid from Excel?** If yes, its submitted journals (NGI 26.7 L, NGN 14.9 L) double-count it |
| D3 | Does a **non-SSF person get the 20% in cash**? Excel pays it to Mahesh Madai; the system doesn't |
| D4 | Should the **late fine have a cap**? It has none today |
| D5 | Should **leaving early** be fined like coming late? It is today |
| D6 | Should the Overtime Sheet **warn above the legal 4 h a day / 24 h a week**? |

### Accountant

- Sign off the tax figures in section 5.
- Supply **Shrawan 2083** taxable pay and tax per person (83 at NGI, 63 at NGN) for the opening fields.

### HR data entry (setup checklist)

- [ ] Shift (Default Shift or Shift Assignment) for 261 staff; Shift Types for SGU, GLMI, GEPL, NGN, NGG
- [ ] Employee Category for 261 staff; OT Eligible for operation staff
- [ ] Attendance Device ID for 265 staff; devices registered
- [ ] Salary Structure Assignment for 70 staff; Fuel row for Abhishek Khadka
- [ ] Salary component accounts for NGG, NGK, and NGN Tea/Meal/OT/Late Fine/Advance
- [ ] Department (payroll section) for 80 staff
- [ ] Leave Policies, Leave Period and allocations
- [ ] Late Fine Exempt for managers; Women's Tax Rebate for qualifying women
- [ ] PAN (45), SSF ID (80), bank account (43), email (all)
- [ ] Open advance balances from Excel; Staff Advance account type at NGN/NGG/NGK
- [ ] Missing festivals on the 83/84 holiday lists; women onto the Women lists
- [ ] Tax Exemption Declarations for anyone with insurance or CIT outside payroll
- [ ] A CIT deduction component, if anyone pays CIT through payroll
- [ ] The 84/85 Fiscal Year (all seven companies) before 2027-07-17

### Not built yet

- Leave encashment at year end (needed by Ashadh)
- A way to pay the Dashain allowance before the month closes
- A setup-checklist report that lists the gaps above per employee (offered, not started)
- Tax reliefs for tuition, remote area and disability, only if someone qualifies
- The six-stage check of real figures, attendance to journal: **waiting on your choice** between the Kartik/Chaitra 2082 workbooks and a test month
- Why Falgun parity dropped after 8 October (NGI 83 → 71, NGN 61 → 26): not investigated

---

## 14. How to check each item yourself

| Item | Check |
|---|---|
| Allowance rates | Open a Salary Structure: **Allowance Rates** table. Open an assignment: pick an allowance, and the rate fills from the structure |
| Salary Revision | New Salary Revision → Allowance Changes → Raise Rate on Tea. Only people at the default rate are listed |
| OT / late fine divisor | Salary Component **Overtime**: "Rate: Days per Month" is blank |
| Exemption limits | Employee Tax Exemption Category / Sub Category lists |
| Women's rebate | Employee form of a woman: the tick shows. On a man it doesn't, and saving it ticked is refused. Each Income Tax Slab shows 10 |
| Tax history warning | Open (or create) a draft Payroll Entry for NGI Ashwin: an orange "Tax history missing" message names 83 people |
| Re-press fix | On a draft month: Prepare Payroll Inputs → mark someone absent → press again → the message says "earlier records removed" |
| Button permission | Log in as a user without Additional Salary create: the button is hidden |
| Reference docs | `python3 docs/tools/check_reference_links.py` → failures: 0 |
| Tests | Section 12 |
