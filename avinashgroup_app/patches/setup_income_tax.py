"""Turn income tax on: a payroll period, the FY 83/84 slab, and an override.

Nothing about tax computes until three records exist — a Payroll Period (the
window the annual projection is spread over), an Income Tax Slab (the bands),
and a deduction component flagged `variable_based_on_taxable_salary`. None of
them were on the site, which is why every slip so far has deducted only SSF.

The slab is the Finance Act 2083 table, effective Shrawan 1, 2083: one schedule
for everyone (the old single/couple split is gone), 1% to ten lakh and 29% at
the top. That first 1% band is the SST column on the client's sheet and carries
the SSF waiver as a row condition — see `payroll/income_tax.py`.

Taxable income is earnings less the SSF contribution, so the slab allows
exemption and the SSF deduction is marked exempt. Every cash earning is marked
taxable; a genuinely non-taxable reimbursement, if one is ever added, has to
untick `Is Tax Applicable` itself.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from avinashgroup_app.payroll.income_tax import FY_8384_SLABS, TAX_COMPONENT

FISCAL_YEAR = "83/84"


def execute():
	add_slip_fields()
	set_component_flags()
	slabs = {}
	for company in frappe.get_all("Company", pluck="name"):
		period = ensure_payroll_period(company)
		if not period:
			continue
		slabs[company] = ensure_tax_slab(company)

	attach_to_structures()
	sync_structure_rows()
	attach_to_assignments(slabs)


def add_slip_fields():
	create_custom_fields(
		{
			"Salary Slip": [
				{
					"fieldname": "custom_income_tax_section",
					"label": "Income Tax",
					"fieldtype": "Section Break",
					"insert_after": "total_loan_repayment",
					"collapsible": 1,
				},
				{
					"fieldname": "custom_income_tax_computed",
					"label": "Computed Income Tax",
					"fieldtype": "Currency",
					"insert_after": "custom_income_tax_section",
					"read_only": 1,
					"description": "What the slab works out for this month, before any override.",
				},
				{
					"fieldname": "custom_income_tax_cb",
					"fieldtype": "Column Break",
					"insert_after": "custom_income_tax_computed",
				},
				{
					"fieldname": "custom_override_income_tax",
					"label": "Override Income Tax",
					"fieldtype": "Check",
					"insert_after": "custom_income_tax_cb",
					"description": "Deduct the amount below instead of the computed one.",
				},
				{
					"fieldname": "custom_income_tax_override",
					"label": "Income Tax (manual)",
					"fieldtype": "Currency",
					"insert_after": "custom_override_income_tax",
					"depends_on": "custom_override_income_tax",
					"mandatory_depends_on": "eval:0",
				},
			]
		},
		ignore_validate=True,
	)


def set_component_flags():
	"""One component computes the tax; SSF reduces what it is computed on."""
	if frappe.db.exists("Salary Component", TAX_COMPONENT):
		frappe.db.set_value(
			"Salary Component",
			TAX_COMPONENT,
			{
				"type": "Deduction",
				"variable_based_on_taxable_salary": 1,
				"depends_on_payment_days": 0,
				"amount_based_on_formula": 0,
				"formula": "",
				"amount": 0,
				"round_to_the_nearest_integer": 1,
			},
		)

	if frappe.db.exists("Salary Component", "SSF"):
		frappe.db.set_value("Salary Component", "SSF", "exempted_from_income_tax", 1)

	# SST is the slab's first band, not a component of its own.
	if frappe.db.exists("Salary Component", "SST"):
		frappe.db.set_value("Salary Component", "SST", "disabled", 1)

	for name in frappe.get_all("Salary Component", filters={"type": "Earning"}, pluck="name"):
		frappe.db.set_value("Salary Component", name, "is_tax_applicable", 1)


def ensure_payroll_period(company):
	fy = frappe.db.get_value("Fiscal Year", FISCAL_YEAR, ["year_start_date", "year_end_date"], as_dict=True)
	if not fy:
		return None

	existing = frappe.db.get_value(
		"Payroll Period", {"company": company, "start_date": fy.year_start_date}, "name"
	)
	if existing:
		return existing

	abbr = frappe.db.get_value("Company", company, "abbr")
	doc = frappe.get_doc(
		{
			"doctype": "Payroll Period",
			"__newname": f"{FISCAL_YEAR} - {abbr}",
			"company": company,
			"start_date": fy.year_start_date,
			"end_date": fy.year_end_date,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_tax_slab(company):
	fy_start = frappe.db.get_value("Fiscal Year", FISCAL_YEAR, "year_start_date")
	existing = frappe.db.get_value(
		"Income Tax Slab", {"company": company, "effective_from": fy_start, "docstatus": 1}, "name"
	)
	if existing:
		return existing

	abbr = frappe.db.get_value("Company", company, "abbr")
	doc = frappe.get_doc(
		{
			"doctype": "Income Tax Slab",
			"__newname": f"Nepal {FISCAL_YEAR} - {abbr}",
			"company": company,
			"effective_from": fy_start,
			"currency": frappe.db.get_value("Company", company, "default_currency") or "NPR",
			"allow_tax_exemption": 1,
			"standard_tax_exemption_amount": 0,
			"slabs": [
				{
					"from_amount": from_amount,
					"to_amount": to_amount,
					"percent_deduction": percent,
					"condition": condition,
				}
				for from_amount, to_amount, percent, condition in FY_8384_SLABS
			],
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def attach_to_structures():
	"""Add the tax component to every structure that does not carry it.

	Salary Structure's component tables are not editable after submit, and the
	structures already have assignments hanging off them, so the row goes in the
	way the desk would have written it.
	"""
	component = frappe.db.get_value(
		"Salary Component", TAX_COMPONENT, ["name", "salary_component_abbr"], as_dict=True
	)
	if not component:
		return

	for structure in frappe.get_all("Salary Structure", filters={"docstatus": 1}, pluck="name"):
		if frappe.db.exists(
			"Salary Detail",
			{"parent": structure, "parentfield": "deductions", "salary_component": TAX_COMPONENT},
		):
			continue

		idx = (
			frappe.db.sql(
				"""select ifnull(max(idx), 0) from `tabSalary Detail`
				where parent = %s and parentfield = 'deductions'""",
				structure,
			)[0][0]
			or 0
		)
		row = frappe.get_doc(
			{
				"doctype": "Salary Detail",
				"parent": structure,
				"parenttype": "Salary Structure",
				"parentfield": "deductions",
				"idx": idx + 1,
				"docstatus": 1,
				"salary_component": component.name,
				"abbr": component.salary_component_abbr,
				"variable_based_on_taxable_salary": 1,
				"depends_on_payment_days": 0,
				"amount": 0,
			}
		)
		row.insert(ignore_permissions=True)
		frappe.clear_document_cache("Salary Structure", structure)


def sync_structure_rows():
	"""Copy the tax flags from each component onto the rows that already exist.

	A Salary Detail row keeps its own copy of `is_tax_applicable` and
	`exempted_from_income_tax`, taken from the component the day the row was
	added. The slip copies the row, not the component — so ticking
	`Exempted from Income Tax` on SSF today does nothing to a structure built
	yesterday, and taxable income silently stays too high.
	"""
	for component in frappe.get_all(
		"Salary Component",
		fields=["name", "is_tax_applicable", "exempted_from_income_tax", "variable_based_on_taxable_salary"],
	):
		frappe.db.sql(
			"""update `tabSalary Detail` sd
			join `tabSalary Structure` ss on ss.name = sd.parent
			set sd.is_tax_applicable = %(is_tax_applicable)s,
			    sd.exempted_from_income_tax = %(exempted_from_income_tax)s,
			    sd.variable_based_on_taxable_salary = %(variable_based_on_taxable_salary)s
			where sd.parenttype = 'Salary Structure' and sd.salary_component = %(name)s""",
			component,
		)
		frappe.clear_cache(doctype="Salary Structure")


def attach_to_assignments(slabs):
	"""Point every assignment at its company's slab — the slip reads it there."""
	for assignment in frappe.get_all(
		"Salary Structure Assignment",
		filters={"docstatus": 1, "income_tax_slab": ["in", (None, "")]},
		fields=["name", "company"],
	):
		slab = slabs.get(assignment.company)
		if slab:
			frappe.db.set_value(
				"Salary Structure Assignment", assignment.name, "income_tax_slab", slab, update_modified=False
			)
