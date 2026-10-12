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
from frappe.utils import date_diff, flt, getdate

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

#: The women's rebate (Schedule 1, 1(10)) by fiscal year, as the Finance Act sets
#: it: a percent off the tax of a woman whose only income is salary. Who gets it
#: is the Employee's Women's Tax Rebate tick (payroll/tax_relief.py). Goes onto
#: the year's Income Tax Slab with the rates; a year in TAX_SLABS_BY_YEAR must
#: be here too. 83/84: 10 (IRD, "Tax rate for natural persons FY 2083/84").
WOMEN_REBATE_BY_YEAR = {
	"83/84": 10,
}

TAX_COMPONENT = "Income Tax"


def tax_history_gaps(company: str, employees: list, start_date) -> list:
	"""Employees whose earlier months of this tax year have neither a slip nor an opening.

	HRMS taxes the year as: submitted slips so far + the opening on the Salary
	Structure Assignment + this month projected over the months left. A month
	before go-live (Shrawan 2083 was paid from Excel) is in none of those, so its
	pay drops out of the year and every slip under-deducts tax. Bikash Sharma:
	1,730 a month instead of about 2,487 (audit, 2026-10-12).

	The opening is `taxable_earnings_till_date` / `tax_deducted_till_date`, and
	HRMS reads it only from an assignment starting inside the year
	(SalarySlip.get_opening_for).
	"""
	period = frappe.db.get_value(
		"Payroll Period",
		{"company": company, "start_date": ("<=", start_date), "end_date": (">=", start_date)},
		["name", "start_date"],
		as_dict=True,
	)
	start_date = getdate(start_date)
	if not period or start_date <= getdate(period.start_date) or not employees:
		return []

	covered = dict(
		frappe.db.sql(
			"""select employee, sum(datediff(end_date, start_date) + 1) from `tabSalary Slip`
			where docstatus = 1 and employee in %(employees)s
			  and start_date >= %(year_start)s and end_date < %(start)s
			group by employee""",
			{"employees": tuple(employees), "year_start": period.start_date, "start": start_date},
		)
	)
	joined = dict(
		frappe.get_all(
			"Employee", filters={"name": ("in", employees)}, fields=["name", "date_of_joining"], as_list=True
		)
	)
	gaps = []
	for employee in employees:
		begin = max(getdate(period.start_date), getdate(joined.get(employee) or period.start_date))
		if begin >= start_date or flt(covered.get(employee)) >= date_diff(start_date, begin):
			continue
		assignment = frappe.db.get_value(
			"Salary Structure Assignment",
			{"employee": employee, "docstatus": 1, "from_date": ("<=", start_date)},
			["from_date", "taxable_earnings_till_date", "tax_deducted_till_date"],
			as_dict=True,
			order_by="from_date desc",
		)
		if (
			assignment
			and getdate(assignment.from_date) >= getdate(period.start_date)
			and (flt(assignment.taxable_earnings_till_date) or flt(assignment.tax_deducted_till_date))
		):
			continue
		gaps.append(employee)
	return gaps


def warn_missing_tax_history(doc):
	"""Tell HR, before the slips are made, whose tax would leave out earlier months.

	A warning, not a refusal, like the missing-attendance one: the figures are
	the accountant's to supply. Runs from AvinashPayrollEntry.validate and
	before_submit, on drafts.
	"""
	if doc.docstatus != 0 or not (doc.company and doc.start_date and doc.employees):
		return
	gaps = tax_history_gaps(doc.company, [e.employee for e in doc.employees], doc.start_date)
	if not gaps:
		return
	shown = ", ".join(gaps[:10]) + (_(" and {0} more").format(len(gaps) - 10) if len(gaps) > 10 else "")
	frappe.msgprint(
		_(
			"{0} employees have earlier months of this tax year with no salary slip: {1}. "
			"Their income tax leaves those months out, so too little is deducted. On each one's "
			"Salary Structure Assignment for this year, enter what was paid before: "
			"<b>Taxable Earnings Till Date</b> (taxable pay after SSF) and <b>Tax Deducted Till Date</b>. "
			"Both can be edited after submit."
		).format(len(gaps), shown),
		title=_("Tax history missing"),
		indicator="orange",
	)


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
