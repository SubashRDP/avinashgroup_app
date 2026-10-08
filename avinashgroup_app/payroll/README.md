# payroll/ — salary, allowances, tax

| File | What it owns | Entry point |
|---|---|---|
| `allowance.py` | Allowances on Salary Component: Is Allowance + Allowance Kind; per company the Admin & Accounts (O/O), Marketing (S/D) and Plant (F/P) accounts and a Default Rate on its Accounts rows; who is tagged (structure row, or the employee's own row). See `docs/allowances.md` | `doc_events` → Salary Component / Salary Structure / Employee validate; read by the two below |
| `attendance_allowance.py` | Tea, meal, overtime, late fine, daily wage → submitted Additional Salary rows (tagged `custom_source`), for tagged employees at their own or the company's rate; then refreshes the entry's draft slips | Payroll Entry → Prepare Payroll Inputs |
| `payroll_entry.py` | Accrual journal posts each section's pay to its own account | `override_doctype_class` → Payroll Entry |
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
