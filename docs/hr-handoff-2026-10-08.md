# HR / Payroll handoff — 2026-10-08: allowances, accounts by section, pay on the assignment

Branch `feature/allowances`, merged into `develop`. Built and checked on `avinas1`
(dell box, `/home/dell/frappe-v15`). Reference sheets: the Falgun 2082 salary
sheets `NGI.xlsx`, `NGN.xlsx`, `NGG.xlsx`, `NGK.xlsx` (dell box:
`~/Downloads/salary detial for samita jee/`). **Copy them to the server.**
Design and day-to-day use: [allowances.md](allowances.md).

---

## 1. What changed, in one table

| Before | Now |
|---|---|
| Each allowance had its own Employee field (DA, Other, Fuel, Fixed, Maintenance, HRA/Gas/Edu ticks), read by a structure formula; a new allowance = new field + new structure | **Pay lives on the Salary Structure Assignment**: Base (Basic), *Pay Details* (Initial Basic, SSF Applicable) and an **Allowances** table (Allowance · Amount · Active · From Date). A new allowance = a Salary Component + rows |
| Employee showed salary figures to anyone editing employees | Employee holds **no pay**. Only OT Eligible and Late Fine Exempt, which are attendance rules |
| One account per component per company; all pay posted to O/O | Each component's Accounts row per company has **Admin & Accounts (O/O)**, **Marketing (S/D)**, **Plant (F/P)** and a **Default Rate**. The journal posts each person to their **Department → Payroll Section** |
| Allowance Category (OLD / NEW / NO tea groups) | Removed. Tea is a tag in the structure (everyone on it); NEW staff have a tea row at 40; staff on no tea have an inactive row |
| Nothing marked which components are allowances | Salary Component → **Is Allowance** + **Allowance Kind** (8 kinds, see allowances.md) |
| Rule fields (meal hours, etc.) only on the component | Same place, plus **Attendance Month** (same / previous) and **Only OT-Eligible Staff** |
| Structures had every allowance row | Structures hold **Basic, SSF Addition, SSF, Income Tax**, and tags for Tea / Meal / Overtime / Late Fine. A structure **refuses** fixed, yearly or hand-entered allowances |
| Prepare Payroll Inputs posted after slips existed → drafts showed no tea | It now **refreshes the entry's draft slips** |
| Daily Wage component, Grade Amount, Arrear | **Disabled.** Daily-wage labour is paid in cash; grade is part of Basic; back pay is Salary Arrears |

Salary Revision (raises) carries every allowance onto the new assignment, with the new DA. Cancelling it brings the old assignment, old DA included, back in force.

## 2. Deploying on the server: step by step

Replace `<site>` with the server's site. Run from the bench root.

### 2.1 Before you touch anything
```bash
bench --site <site> backup --with-files
bench --site <site> mariadb -e "SELECT COUNT(*) slips FROM \`tabSalary Slip\` WHERE docstatus=1; SELECT name, docstatus FROM \`tabSalary Structure\`; SELECT COUNT(*) FROM \`tabSalary Structure Assignment\` WHERE docstatus=1;"
```
Write the numbers down. **If the site already has submitted salary slips or
structures, read 2.4 before 2.3.**

### 2.2 Code
```bash
cd apps/avinashgroup_app && git pull upstream develop && cd ../..
bench --site <site> migrate
```
Two patches run, in order. Each prints a one-line summary; keep the output.

| Patch | What it does |
|---|---|
| `setup_allowance_kinds` | Adds the allowance and account fields, plus Department → Payroll Section. Seeds sections by department name and **prints each one: check them**. Marks known components as allowances. Turns Allowance Category rates into rows. Tags everyone with what the old engine paid without a tag. Disables Daily Wage |
| `move_pay_to_salary_assignment` | Copies each employee's old pay fields onto their **latest submitted assignment**. Reads gas/edu/HRA rates from old structure formulas onto the components. Removes the old Employee fields **unless** a structure still reads them, or an employee with no assignment still holds a value. It prints which fields it kept |

Then press **Ctrl+Shift+R** in the browser (forms are cached there).

### 2.3 Settings (all were wrong on avinas1 and demo)
| Where | Set | Why |
|---|---|---|
| Nepal HRMS Settings | **Process payroll in Nepali month** ✔ | slips follow BS months. Off on demo |
| Company (all seven) | **Country = Nepal** | with "restrict to Nepal companies" on, BS payroll stays off for a company marked India (NGI, NGG, NGN were) |
| Payroll Settings | **Include holidays in total working days** ✔ | holidays are paid. Off, a full month paid 26/31 |
| Department list | **Payroll Section** on every department | check the printed seeding. Driver / Vehicle Helper → **Marketing** (sales) |
| Departments that employees point to but don't exist | create them | on avinas1, 5 NGK ones were missing (Account, Driver, Plant, Sales and Marketing, Vehicle Helper); assignments fail without them |

```sql
-- employees pointing to a department that does not exist
SELECT e.department, COUNT(*) FROM tabEmployee e LEFT JOIN tabDepartment d ON d.name=e.department
WHERE IFNULL(e.department,'')<>'' AND d.name IS NULL GROUP BY e.department;
```

### 2.4 If the server already has structures built the old way
Old structures have rows such as `custom_dearness_allowance` and `1690 if custom_gas_allowance`.
- **If no slip has been submitted from them:** cancel and delete those assignments and structures, then do 2.5. This is exactly what was done on avinas1.
- **If slips were submitted:** leave them. Create the new structures for the **next** month: run 2.5, and the assignments start on the fiscal year's first day, so set `FISCAL_YEAR` / dates as needed. Then cancel the old assignments from that date. The patch keeps the old Employee fields while an old structure reads them; once the old structures are inactive, re-run the patch to remove the fields:
  `bench --site <site> run-patch --force avinashgroup_app.patches.move_pay_to_salary_assignment`

### 2.5 Build structures and assignments from the sheets
```bash
bench --site <site> execute avinashgroup_app.payroll.onboarding.onboard --kwargs "{'key': 'NGI', 'path': '/path/NGI.xlsx'}"
bench --site <site> execute avinashgroup_app.payroll.onboarding.onboard --kwargs "{'key': 'NGN', 'path': '/path/NGN.xlsx'}"
bench --site <site> execute avinashgroup_app.payroll.onboarding.onboard --kwargs "{'key': 'NGG', 'path': '/path/NGG.xlsx'}"
bench --site <site> execute avinashgroup_app.payroll.onboarding.onboard --kwargs "{'key': 'NGK', 'path': '/path/NGK.xlsx'}"
```
Each one:
- creates **`<KEY> Staff 83/84`** (Basic, SSF Addition, tags; SSF, Late Fine, Income Tax);
- sets the company rates on the components (tea, meal, gas, edu, HRA %);
- creates each matched employee's **assignment** from 1 Shrawan 2083, with Initial Basic, SSF Applicable and Allowances rows.

It is safe to run again: an existing assignment is not touched.

Expected (avinas1): NGI 87 assignments, NGN 63, NGG 27, NGK 19.

### 2.6 Check against the sheets (read-only)
```bash
bench --site <site> execute avinashgroup_app.payroll.onboarding.check_against_sheet --kwargs "{'key': 'NGI', 'path': '/path/NGI.xlsx'}"
```
Prints how many slips equal the sheet's regular salary and SSF, and lists the rest. On avinas1:

| Company | Match | Differ (HR to check) |
|---|---|---|
| NGI | 83 | Shreechandra Bhatta (CEO, special pay), Kishor Lal Shrestha (0 on sheet), Raju Maharjan (part month), Abhishek Khadka |
| NGN | 61 | Mahesh Bahadur Madai, Shiva Kumar Kushwaha (0), Sudip Mahato (0) |
| NGG | 27 | — |
| NGK | 19 | — |

**If everyone differs with days 26/31, "Include holidays" is off (2.3).**

### 2.7 Accounts (with the accountant)
- No component has accounts per company yet. The proposal is in `payroll/onboarding.py` (`PROPOSED_ACCOUNTS`). Once the accountant agrees:
  `bench --site <site> execute avinashgroup_app.payroll.onboarding.map_component_accounts --kwargs "{'company': 'Nepal Gas Udhyog Pvt. Ltd.'}"`
  It fills the O/O account and its S/D and F/P siblings (e.g. 547101 / 547102 / 547103). Rows that already hold a company rate get their account added.
- **There is no tea account in the chart.** Create "Tea & Conveyance Allowance" O/O, S/D and F/P, then type them on Tea & Conveyance's Accounts rows.
- Meal: 547130 / 547131 / 547132 exist.
- avinas1 had **Income Tax without an account**, and **347301 Salary Payable with account type "Liability"**. HRMS refuses any account type on the payable account; clear it.

### 2.8 First payroll run
1. Attendance submitted for the BS month.
2. New Payroll Entry → choose **Company, Fiscal Year, Month (BS)** → Save. Dates, posting date, accounts and employees fill themselves; the English date fields are locked. (Added 2026-10-09: `patches/setup_payroll_entry_bs_month` adds the two fields; month borders from Nepal BS Period, else the calendar.)
3. **Nepal HRMS → Prepare Payroll Inputs** (tea, meal, overtime, late fine, advances). Best before Submit; afterwards it refreshes the draft slips.
4. Submit → slips are created → review a few against the sheet.
5. **Submit Salary Slips** → the accrual journal splits Basic and allowances by O/O / S/D / F/P.

A dry run on avinas1 (rolled back) posted Basic to 547101/2/3 and Mobile + Tea to 547110/1/2 by section, with Salary Payable credited the exact net.

### 2.9 If something goes wrong
- Restore the backup from 2.1: `bench --site <site> restore <file>`.
- Or revert code: `git checkout <previous commit>` + `bench --site <site> migrate`. Note that the patches have already removed fields; their data is on the assignments.

## 3. Changed on avinas1 today (data, not code)

- **Companies:** NGI, NGG and NGN country India → **Nepal**.
- **Settings:** Process payroll in Nepali month **on**; Include holidays in total working days **on**; `read_from_replica` set to **0** in `sites/avinas1/site_config.json` (the replica on :3307 has been stuck since 2026-09-29 and needs `sudo` to re-seed: STOP SLAVE; RESET SLAVE ALL; `sudo bash setup_replica.sh`; then set it back to 1).
- **Created:** 5 NGK departments; 4 structures; 196 assignments.
- **Disabled:** Daily Wage, Grade Amount, Arrear.
- **Backups:** `sites/avinas1/private/backups/20261008_*`. The 12:11 one is from before any of this.

## 4. Open: decisions and data for HR / accounts

1. **Unpaid absence:** allowances are prorated like Basic (Depends on Payment Days). Confirm, or tell dev to make them full.
2. **69 active employees with no assignment** (not on the sheets):
   - placeholders to set Inactive: "Staff Advance" (NGI, NGG), "Dashain Advance" (NGN), "Rounding Staff's Balance" (NGK);
   - cash labour (NGK plant and vehicle helpers);
   - likely duplicates across companies, several marked "(A.W)": ask what that means;
   - new joiners and others who need Basic + allowances. Give them an assignment by hand, or a sheet in the same layout.
   - Some NGN joining dates (1960, 1962) look like birth dates.
3. **7 sheet names with no employee:** NGN Shreeram Sah, Dinesh Chaudhary, Hari Sharan Mahato, Dipak Chaudhary; NGG Subash Chaudhary; NGK Arun Kumar Tharu, Pal Bahadur Lohar.
4. ~~Meal for OT-eligible only~~ **Done 2026-10-09:** a meal is earned only on overtime the company authorised (submitted Overtime Sheet, entitlement Overtime), by OT-eligible staff. 1.5 h early or late on a working day = 1 meal each; a holiday = 2; max 2 a day. The holiday 6 h / 8 h fields are removed. Patch `meal_on_authorised_overtime`. See allowances.md → Meal.
5. **M.OT** on the attendance sheet: meaning unknown, treated as ordinary overtime.
6. **Not built yet:** Dashain Bonus button and Leave Encashment button on the Payroll Entry. Both are pressed by HR: Dashain before the Dashain holiday, leave at Ashadh.
7. **Docs** `payroll-manual.html`, `hr-payroll-handbook.html` and `payroll-documentation.html` still describe Allowance Category and the Employee pay fields.

## 5. Gotchas found the hard way

- **Only one app's `override_doctype_class` wins.** rdp_common_app's BS Salary Slip wins, so allowances reach the slip through a Salary Slip **validate hook** (`payroll/salary_slip.py`), not a class. Payroll Entry is overridden normally (`payroll/payroll_entry.py`).
- **Preview Salary Slip** (on a structure or an assignment) does not run validate, so it shows the structure lines only. A real draft slip shows the allowances.
- **HRMS creates the slips when the Payroll Entry is submitted.** Anything posted later reaches a draft slip only when it is re-saved, which is why Prepare Payroll Inputs now refreshes them.
- **HRMS commits on a payroll failure** (`log_payroll_failure`), even inside a test. For a dry run, patch `frappe.db.commit` for the whole script.
- **A structure formula sees the assignment's fields**, but the Employee's same-named field overrides them. That's why Initial Basic and SSF Applicable had to leave the Employee.
- **The list views read the replica.** A broken replica makes new columns "unknown" in lists while forms work.

## 6. Files

| File | Role |
|---|---|
| `payroll/allowance.py` | kinds, account rows / sections, assignment rows, hooks for Salary Component / Structure / Assignment |
| `payroll/salary_slip.py` | fixed allowances from the assignment onto the slip |
| `payroll/attendance_allowance.py` | tea / meal / OT / late fine → Additional Salary; refreshes draft slips |
| `payroll/payroll_entry.py` | journal by section |
| `payroll/onboarding.py` | sheets → structures, assignments, company rates; `check_against_sheet`; `map_component_accounts` |
| `avinash_group_app/doctype/assignment_allowance/` | the Allowances table on the assignment |
| `avinash_group_app/doctype/salary_revision/salary_revision.py` | raises carry the allowances; DA on the new assignment |
| `patches/setup_allowance_kinds.py`, `patches/move_pay_to_salary_assignment.py` | migration |
| `public/js/salary_structure_assignment.js`, `public/js/payroll_entry.js` | form scripts |
| `payroll/test_allowance.py` | 18 tests; with the attendance and shift suites, 53 pass on develop after the merge |

Tests: run with the runner in `docs/shift-rotation.md` ("Tests"), module
`avinashgroup_app.payroll.test_allowance`.
