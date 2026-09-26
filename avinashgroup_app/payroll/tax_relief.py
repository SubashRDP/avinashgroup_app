"""Nepal salary-tax reliefs that HRMS cannot express on its own.

The slab (payroll/income_tax.py) and HRMS's own exemption machinery already
cover the simple cases:

  * SSF is a deduction component marked `exempted_from_income_tax`, so it
    leaves taxable income before the slab is applied.
  * Insurance premiums and CIT paid outside payroll are HRMS's standard Employee
    Tax Exemption Declaration, against the categories seeded by
    patches/setup_tax_exemptions.py (each capped at its own maximum).
  * CIT deducted through payroll is the `CIT` deduction component, also exempt.

Two rules of the Income Tax Act 2058 have no HRMS equivalent, and live here:

  1. Retirement cap (s.63). Contributions to an approved retirement fund (SSF,
     CIT, PF) are deductible only up to the LOWER of one third of assessable
     income or Rs 5,00,000 a year. HRMS exempts every such rupee with no cap,
     so a high earner's tax came out low. The excess over the cap is put back
     into taxable income.
  2. Women's rebate (Schedule 1, 1(10)). A resident woman whose income is only
     from employment gets a rebate on her tax. The percentage is a field on the
     Income Tax Slab (`custom_women_rebate_percent`, 10 for FY 83/84) so a
     Finance Act change is a data edit.

How: HRMS computes the month's tax in the Salary Slip controller's validate and
leaves every intermediate figure (total taxable earnings, tax already paid,
remaining months) on the document. This hook runs straight after, recomputes the
year's tax from those same figures with the two reliefs applied, and spreads it
over the remaining months exactly as HRMS does. A slip neither rule touches is
left byte-for-byte as HRMS made it.

It runs BEFORE `income_tax.apply_income_tax_override`, so a hand-typed figure
still wins and `custom_income_tax_computed` shows the figure with reliefs.

Why a hook and not a Salary Slip class: rdp_common_app already overrides the
Salary Slip class (BS months) and is installed after this app, so a second
override here would be silently ignored.

The amounts come from third-party summaries of the Finance Act 2083 and are
awaiting the accountant's confirmation (docs/payroll-handover.md §8).
"""

from math import ceil

import frappe
from frappe.utils import flt

from hrms.payroll.doctype.salary_slip.salary_slip import calculate_tax_by_tax_slab

from avinashgroup_app.payroll.income_tax import get_tax_row

# Income Tax Act 2058 s.63(1): retirement contributions deductible up to the
# lower of one third of assessable income or this amount a year.
RETIREMENT_CAP_AMOUNT = 500_000
RETIREMENT_CAP_FRACTION = 1 / 3

# Employee Tax Exemption Category that holds retirement contributions made
# outside payroll (CIT paid directly). Seeded by patches/setup_tax_exemptions.py.
RETIREMENT_EXEMPTION_CATEGORY = "Retirement Contribution"


def apply_tax_reliefs(doc, method=None):
	"""Recompute the slip's income tax with the retirement cap and women's rebate. Hook: validate."""
	row = get_tax_row(doc)
	slab = getattr(doc, "tax_slab", None)
	if not row or not slab or not hasattr(doc, "total_taxable_earnings_without_full_tax_addl_components"):
		return  # HRMS computed no tax on this slip; nothing to adjust

	excess = retirement_excess(doc)
	rebate = women_rebate_fraction(doc, slab)
	if not excess and not rebate:
		return

	eval_locals, __ = doc.get_data_for_eval()
	remaining = flt(doc.remaining_sub_periods) or 1

	structured, __ = calculate_tax_by_tax_slab(
		doc.total_taxable_earnings_without_full_tax_addl_components + excess,
		slab,
		doc.whitelisted_globals,
		eval_locals,
	)
	structured *= 1 - rebate
	current = (structured - flt(doc.previous_total_paid_taxes)) / remaining

	full_tax_on_additional = 0.0
	if flt(doc.get("current_additional_earnings_with_full_tax")):
		with_additional, __ = calculate_tax_by_tax_slab(
			doc.total_taxable_earnings + excess, slab, doc.whitelisted_globals, eval_locals
		)
		full_tax_on_additional = with_additional * (1 - rebate) - structured

	amount = flt(max(current + full_tax_on_additional, 0), row.precision("amount"))
	row.amount = amount
	row.default_amount = amount
	doc.custom_retirement_excess = excess
	doc.custom_women_rebate = flt(rebate * 100)

	# Keep the slip's tax breakup section in step with the new figure.
	if doc.get("annual_taxable_amount") is not None:
		doc.annual_taxable_amount = flt(doc.annual_taxable_amount) + excess
	doc.income_tax_deducted_till_date = flt(doc.previous_total_paid_taxes) + amount
	doc.current_month_income_tax = amount
	doc.future_income_tax_deductions = structured + full_tax_on_additional - doc.income_tax_deducted_till_date
	doc.total_income_tax = doc.income_tax_deducted_till_date + doc.future_income_tax_deductions
	doc.set_net_pay()


def retirement_excess(doc):
	"""Rupees of retirement contribution this year above the s.63 cap (0 when within it)."""
	# Exempt deductions HRMS already took out of taxable income: past slips,
	# this slip, and this slip's figure projected over the months still to come.
	previous = flt(doc.get("previous_taxable_earnings_before_exemption")) - flt(
		doc.get("previous_taxable_earnings")
	)
	now = doc.get("current_taxable_earnings_for_payment_days")
	full_month = doc.get("current_taxable_earnings")
	current = flt(now.amount_exempted_from_income_tax) if now else 0
	future = (
		flt(full_month.amount_exempted_from_income_tax) * (ceil(flt(doc.remaining_sub_periods)) - 1)
		if full_month
		else 0
	)
	declared = declared_retirement(doc)
	contributions = previous + current + future + declared
	if not contributions:
		return 0.0

	# Assessable income is taxable income with every exemption added back.
	assessable = (
		flt(doc.total_taxable_earnings)
		+ flt(doc.get("total_exemption_amount"))
		+ previous
		+ current
		+ future
	)
	cap = min(assessable * RETIREMENT_CAP_FRACTION, RETIREMENT_CAP_AMOUNT)
	return max(contributions - cap, 0.0)


def declared_retirement(doc):
	"""CIT / PF paid outside payroll, from the employee's exemption declaration for the period."""
	period = getattr(doc, "payroll_period", None)
	if not period:
		return 0.0
	# Same source HRMS reads: the proof in the year's last month, the declaration before it.
	if doc.get("deduct_tax_for_unsubmitted_tax_exemption_proof"):
		parent, child = "Employee Tax Exemption Proof Submission", "Employee Tax Exemption Proof Submission Detail"
	else:
		parent, child = "Employee Tax Exemption Declaration", "Employee Tax Exemption Declaration Category"
	rows = frappe.db.sql(
		f"""select sum(c.amount) from `tab{child}` c join `tab{parent}` p on p.name = c.parent
		where p.employee = %s and p.payroll_period = %s and p.docstatus = 1
		  and c.exemption_category = %s""",
		(doc.employee, period.name, RETIREMENT_EXEMPTION_CATEGORY),
	)
	return flt(rows[0][0]) if rows else 0.0


def women_rebate_fraction(doc, slab):
	"""0.1 for a woman on a slab with a 10% rebate; 0 otherwise."""
	percent = flt(slab.get("custom_women_rebate_percent"))
	if not percent:
		return 0.0
	if frappe.db.get_value("Employee", doc.employee, "gender") != "Female":
		return 0.0
	return percent / 100
