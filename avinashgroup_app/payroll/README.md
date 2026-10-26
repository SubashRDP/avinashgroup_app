# payroll/ — salary, allowances, tax

Code map: [docs/salary-code-map.md](../../docs/salary-code-map.md) — every function from punch to journal, in run order, with a CodeTour (`.tours/salary-calculation.tour`).

| File | What it owns | Entry point |
|---|---|---|
| `allowance.py` | Allowances on Salary Component (Is Allowance, kind; per company O/O·S/D·F/P accounts, no rate); the structure's Allowance Rates (usual rates, changed only by Salary Revision once submitted); a person's pay on the Salary Structure Assignment (Initial Basic, SSF Applicable, Allowances with their Rate). See `docs/allowances.md` | `doc_events` → Salary Component / Salary Structure / Salary Structure Assignment validate, Salary Structure before_update_after_submit; `get_rate_for_assignment` (form) |
| `attendance_allowance.py` | Tea, meal, overtime, late fine, daily wage → submitted Additional Salary rows (tagged `custom_source`), for employees with a row on their assignment, at its Rate (overtime and late fine from basic); then refreshes the entry's draft slips | Payroll Entry → Prepare Payroll Inputs |
| `festival_allowance.py` | Dashain allowance: one month's basic × service factor (full year by the cut-off = 100 %, else days ÷ days in the year; never above basic) → a Payroll Adjustment, paid on a Dashain Allowance payout entry's own slips; rules on the Salary Component's Festival Allowance section | Payroll Entry with Payout = Dashain Allowance (`_pay_dashain`); `make_festival_adjustment` |
| `leave_encashment.py` | HRMS Leave Encashment priced at the person's basic ÷ days per month, allowed only at year end / separation per Leave Type; its Additional Salary linked back and paid on a Leave Encashment payout entry's own slips; leave recovery stays on the salary slip | Payroll Entry → Nepal HRMS → Leave Encashment (`encash_for_payroll_entry`); `doc_events` → Leave Encashment validate / on_submit / on_cancel, Additional Salary validate / on_submit |
| `special_payout.py` | Dashain allowance and leave encashment paid on their own slip (Payroll Entry / Salary Slip / Additional Salary `custom_payout_type`): payout rows kept off the monthly slip (`disabled`), the payout slip cut to the payout and the tax it adds to the year; `REGULAR_SLIPS` for "is this month paid?" checks | `doc_events` → Salary Slip before_validate / validate (first), Additional Salary validate; Payroll Entry overrides in `payroll_entry.py` |
| `salary_slip.py` | Fixed allowances from the assignment's rows onto the slip (prorated; projected for tax) | `doc_events` → Salary Slip validate, before the tax hooks |
| `daily_breakdown.py` | The slip's Daily Breakdown table: each day's attendance, fixed share, tea / meal / OT / late fine, running balance to net pay | `doc_events` → Salary Slip validate, last |
| `payroll_month.py` | A Payroll Entry from Fiscal Year + Month (BS): fills dates, posting date (month end), frequency, currency, payable account, cost centre, employees | `AvinashPayrollEntry.validate`; form: `public/js/payroll_entry.js` |
| `payroll_entry.py` | Accrual journal posts each section's pay to its own account; payout entries (Dashain, encashment) post only their payout, and duplicate checks / Get Employees compare a slip only with its own kind | `override_doctype_class` → Payroll Entry |
| `tax_relief.py` | Retirement cap (SSF + CIT + PF ≤ lower of ⅓ income or 5,00,000) and the women's rebate (`Income Tax Slab.custom_women_rebate_percent`); insurance / CIT declarations use HRMS's own Employee Tax Exemption Declaration (categories seeded by `patches/setup_tax_exemptions`) | `doc_events` → Salary Slip validate, before the override |
| `income_tax.py` | Nepal salary tax: `TAX_SLABS_BY_YEAR` (one table per fiscal year) and the per-slip override | `doc_events` → Salary Slip validate |
| `year_rollover.py` | New salary assignments from a fiscal year's first day on the new year's tax slab — HRMS reads the slab from the assignment | called by `hr.year_setup.setup_year` |
| `bs_period_guard.py` | Refuses a Payroll Entry posted outside the BS month it pays, and a slip whose month differs from its entry's | `doc_events` → validate |
| `advance_recovery.py` | Employee advance instalments on the slip | Payroll Entry flow |
| `hr_journal.py` | JV Type / Document No on payroll journals | `doc_events` |
| `onboarding.py` | A company's own salary sheet → components, structure, first assignments | `bench execute` |

Report: **Salary Tax and SSF Deposit** (`avinash_group_app/report/salary_tax_and_ssf_deposit/`) — one BS month's SSF (31%), SST and remuneration tax to deposit, with deadlines.
Print format: **Salary Slip BS** (`templates/print_formats/salary_slip_bs.html`) — the default Salary Slip format, so it is also what HRMS emails.

The BS salary slip itself (`BSSalarySlip`) lives in `rdp_common_app`, which this
app does not edit. Handover and traps: `docs/payroll-handover.md`.
