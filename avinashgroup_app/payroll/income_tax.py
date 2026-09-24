"""Income tax on the salary slip: computed from the slab, overridable by hand.

Nepal charges salary tax on a single annual table (Finance Act 2083 merged the
old single/couple schedules into one), and the first band is the 1% *social
security tax* — the "SST" column on the client's sheet. That 1% is waived for
anyone contributing to the Social Security Fund, which is why Falgun 2082 shows
SST on exactly the four NGI staff who have no SSF deduction, and zero on the 83
who do.

So SST is not a second component. It is the first row of the slab, carrying the
condition `not custom_ssf_applicable`; HRMS skips a slab row whose condition is
false, and the employee's own fields are in scope there. One `Income Tax`
component with `variable_based_on_taxable_salary` then produces either the 1%
SST or the full progressive tax, whichever the person is liable for.

The computed figure is a projection — it assumes the rest of the year looks like
this month. Accounts routinely knows better (a mid-year joiner's previous
employer income, a declaration filed late, a figure agreed with the auditor), so
every slip carries an override: tick `Override Income Tax`, type the amount, and
that is what is deducted. The computed number is kept beside it so the two can
always be compared.
"""

import frappe
from frappe import _
from frappe.utils import flt

#: The tax table itself, as amounts and percentages — the whole point of keeping
#: it in an Income Tax Slab record is that next year's Finance Act is a data
#: edit, not a code change. This is only the seed for the first year.
FY_8384_SLABS = (
	# from, to (0 = no ceiling), percent, condition
	(0, 1_000_000, 1, "not custom_ssf_applicable"),
	(1_000_001, 1_500_000, 10, ""),
	(1_500_001, 2_500_000, 20, ""),
	(2_500_001, 4_000_000, 27, ""),
	(4_000_001, 0, 29, ""),
)

#: The tables by fiscal year, as the Finance Act sets them. `year_setup` builds a
#: year's Income Tax Slab from here, and refuses a year that is missing rather
#: than copy the last one — reused rates are the failure nobody notices. Add
#: "84/85" once the Finance Act 2084 is published (budget speech, 15 Jestha), or
#: create the 84/85 slab in the desk by hand; either is enough.
TAX_SLABS_BY_YEAR = {
	"83/84": FY_8384_SLABS,
}

TAX_COMPONENT = "Income Tax"


def get_tax_row(doc):
	"""The deduction row that holds the slab-computed tax, if the slip has one."""
	for row in doc.get("deductions") or []:
		if row.variable_based_on_taxable_salary:
			return row
	return None


def apply_income_tax_override(doc, method=None):
	"""Record what the slab computed, then honour a hand-typed figure over it.

	Runs after the controller's own validate, so the tax row already holds the
	computed amount. Rewriting it here means re-running the totals — the row
	feeds `total_deduction`, `net_pay` and the amount in words.
	"""
	row = get_tax_row(doc)
	if row:
		doc.custom_income_tax_computed = flt(row.amount)
	elif not doc.get("custom_override_income_tax"):
		return

	if not doc.get("custom_override_income_tax"):
		return

	amount = flt(doc.get("custom_income_tax_override"))

	if not row:
		if not amount:
			return
		component = frappe.db.get_value(
			"Salary Component",
			{"variable_based_on_taxable_salary": 1, "type": "Deduction"},
			["name", "salary_component_abbr"],
			as_dict=True,
		)
		if not component:
			frappe.throw(_("No income tax Salary Component is set up, so it cannot be overridden."))
		row = doc.append(
			"deductions",
			{
				"salary_component": component.name,
				"abbr": component.salary_component_abbr,
				"variable_based_on_taxable_salary": 1,
				"depends_on_payment_days": 0,
				"statistical_component": 0,
			},
		)

	row.amount = amount
	row.default_amount = amount
	row.additional_amount = 0
	doc.set_net_pay()
