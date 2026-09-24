# payroll/ — salary, allowances, tax

| File | What it owns | Entry point |
|---|---|---|
| `attendance_allowance.py` | Tea, meal, overtime, late fine, daily wage → Payroll Adjustment rows | Payroll Entry flow |
| `income_tax.py` | Nepal salary tax: `TAX_SLABS_BY_YEAR` (one table per fiscal year) and the per-slip override | `doc_events` → Salary Slip validate |
| `year_rollover.py` | New salary assignments from a fiscal year's first day on the new year's tax slab — HRMS reads the slab from the assignment | called by `hr.year_setup.setup_year` |
| `bs_period_guard.py` | Refuses a Payroll Entry posted outside the BS month it pays, and a slip whose month differs from its entry's | `doc_events` → validate |
| `advance_recovery.py` | Employee advance instalments on the slip | Payroll Entry flow |
| `hr_journal.py` | JV Type / Document No and cost-centre routing on payroll journals | `doc_events` |
| `onboarding.py` | A company's own salary sheet → components, structure, first assignments | `bench execute` |

The BS salary slip itself (`BSSalarySlip`) lives in `rdp_common_app`, which this
app does not edit. Handover and traps: `docs/payroll-handover.md`.
