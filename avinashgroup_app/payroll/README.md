# payroll/ — salary, allowances, tax

| File | What it owns | Entry point |
|---|---|---|
| `company_allowance.py` | Company Allowance helpers: per company × allowance the rule, default rate, who gets it and three section accounts (O/O, S/D, F/P); validates the Employee's Allowances table. See `docs/company-allowance.md` | read by the three below; `doc_events` → Employee validate |
| `attendance_allowance.py` | Tea, meal, overtime, late fine, daily wage → submitted Additional Salary rows (tagged `custom_source`), by the employee's company's Company Allowance | Payroll Entry flow |
| `salary_slip.py` | Fixed Monthly / % of Initial Basic allowances as slip rows (projected for tax) | `doc_events` → Salary Slip validate, before the tax hooks |
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
