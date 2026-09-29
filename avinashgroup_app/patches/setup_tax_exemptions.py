"""Fields for the Nepal tax reliefs in payroll/tax_relief.py — fields only, no figures.

No amount, percentage or record is seeded here. Every figure is HR's to enter on
the form, confirmed with the accountant, because a number put in by code looks
deliberate and is only found wrong in somebody's pay. A blank field means the
relief is off, never "use the Act's number".

  Income Tax Slab.custom_women_rebate_percent
      The women's rebate (Schedule 1, 1(10)). Allowed on submit, so a Finance
      Act change is a data edit. Blank: no rebate.
  Employee Tax Exemption Category.custom_is_retirement_contribution /
  custom_cap_percent_of_income
      Tick the category that holds retirement contributions (CIT / PF paid
      directly) and give it the s.63 cap: its Max Amount and a % of assessable
      income, the lower of which applies to SSF + CIT + PF together. Blank
      both: no cap.
  Salary Slip.custom_retirement_excess / custom_women_rebate
      Read-only, beside Computed Income Tax, so accounts can see why a slip's
      tax differs from the bare slab.

The exemption categories, sub-categories and the CIT deduction component are
ordinary HRMS records, created in the desk like any other.

Until 2026-09-29 this patch also seeded the Finance Act 2083 figures (10%,
65,000 / 40,000 / 20,000 / 5,000, 5,00,000) and the CIT component. The user
removed them: no data comes as default. Sites that already ran it keep what it
wrote; patches/tax_relief_fields_without_defaults.py adds the new fields there.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	add_fields()


def add_fields():
	create_custom_fields(
		{
			"Income Tax Slab": [
				{
					"fieldname": "custom_women_rebate_percent",
					"label": "Women's Rebate (%)",
					"fieldtype": "Percent",
					"insert_after": "standard_tax_exemption_amount",
					"allow_on_submit": 1,
					"description": "Rebate on the tax of a female employee (Income Tax Act Schedule 1). Blank: no rebate.",
				}
			],
			"Employee Tax Exemption Category": [
				{
					"fieldname": "custom_is_retirement_contribution",
					"label": "Retirement Contribution (s.63 cap)",
					"fieldtype": "Check",
					"insert_after": "max_amount",
					"description": "SSF, CIT and PF together are capped at the lower of this category's Max Amount "
					"and the % of assessable income below",
				},
				{
					"fieldname": "custom_cap_percent_of_income",
					"label": "Cap: % of Assessable Income",
					"fieldtype": "Percent",
					"insert_after": "custom_is_retirement_contribution",
					"depends_on": "custom_is_retirement_contribution",
					"description": "Blank: only the Max Amount caps. Both blank: no cap.",
				},
			],
			"Salary Slip": [
				{
					"fieldname": "custom_retirement_excess",
					"label": "Retirement Contribution Over Cap (year)",
					"fieldtype": "Currency",
					"insert_after": "custom_income_tax_computed",
					"read_only": 1,
					"description": "SSF + CIT + PF above the retirement cap, added back to taxable income.",
				},
				{
					"fieldname": "custom_women_rebate",
					"label": "Women's Rebate Applied (%)",
					"fieldtype": "Percent",
					"insert_after": "custom_retirement_excess",
					"read_only": 1,
				},
			],
		},
		update=True,
	)
	for dt in ("Income Tax Slab", "Employee Tax Exemption Category", "Salary Slip"):
		frappe.clear_cache(doctype=dt)
