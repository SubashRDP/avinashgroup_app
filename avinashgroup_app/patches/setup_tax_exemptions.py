"""Nepal tax exemptions: declaration categories, the CIT component, the women's rebate.

Pairs with payroll/tax_relief.py. What each piece is for:

  Employee Tax Exemption Category / Sub Category
      HRMS's standard declaration: the employee declares premiums paid for the
      payroll period, HRMS subtracts them from taxable income, each capped at
      its sub-category maximum. Income Tax Act 2058 s.12A / 12B / 12C:
        Insurance Premium       Life 40,000 · Health 20,000 · Building 5,000
        Retirement Contribution CIT / PF paid directly 5,00,000 (the s.63 cap
                                on SSF + CIT + PF together is applied in
                                tax_relief.py, since HRMS caps one category
                                at a time)
  CIT (Salary Component)
      A deduction exempt from income tax, for CIT taken through payroll. Pay it
      with a recurring Additional Salary per employee; no structure change.
  Income Tax Slab.custom_women_rebate_percent
      10 for FY 83/84. Allowed on submit, so next year's rate is a data edit.
  Salary Slip.custom_retirement_excess / custom_women_rebate
      Read-only, beside Computed Income Tax, so accounts can see why a slip's
      tax differs from the bare slab.

Every amount here is from third-party summaries of the Finance Act 2083 and is
pending the accountant's confirmation. All are data; change them in the desk.

Idempotent: existing records are updated, never duplicated.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

WOMEN_REBATE_PERCENT = 10  # Income Tax Act 2058, Schedule 1, 1(10)

EXEMPTIONS = {
	# category: (category max, {sub-category: max})
	"Insurance Premium": (
		65_000,
		{"Life Insurance Premium": 40_000, "Health Insurance Premium": 20_000, "Building Insurance Premium": 5_000},
	),
	"Retirement Contribution": (
		500_000,
		{"Citizen Investment Trust (CIT)": 500_000, "Provident Fund (paid directly)": 500_000},
	),
}

CIT_COMPONENT = "CIT"


def execute():
	add_fields()
	for category, (category_max, subs) in EXEMPTIONS.items():
		upsert("Employee Tax Exemption Category", category, {"max_amount": category_max, "is_active": 1})
		for sub, sub_max in subs.items():
			upsert(
				"Employee Tax Exemption Sub Category",
				sub,
				{"exemption_category": category, "max_amount": sub_max, "is_active": 1},
			)

	upsert(
		"Salary Component",
		CIT_COMPONENT,
		{
			"salary_component_abbr": "CIT",
			"type": "Deduction",
			"exempted_from_income_tax": 1,
			"depends_on_payment_days": 0,
			"description": "Citizen Investment Trust deducted through payroll. Exempt from income tax, "
			"within the retirement cap. Pay with a recurring Additional Salary.",
		},
		name_field="salary_component",
	)

	for slab in frappe.get_all("Income Tax Slab", filters={"docstatus": ("<", 2)}, pluck="name"):
		if not frappe.db.get_value("Income Tax Slab", slab, "custom_women_rebate_percent"):
			frappe.db.set_value("Income Tax Slab", slab, "custom_women_rebate_percent", WOMEN_REBATE_PERCENT)


def add_fields():
	create_custom_fields(
		{
			"Income Tax Slab": [
				{
					"fieldname": "custom_women_rebate_percent",
					"label": "Women's Rebate (%)",
					"fieldtype": "Percent",
					"insert_after": "standard_tax_exemption_amount",
					"default": str(WOMEN_REBATE_PERCENT),
					"allow_on_submit": 1,
					"description": "Rebate on the tax of a female employee (Income Tax Act Schedule 1). 0 turns it off.",
				}
			],
			"Salary Slip": [
				{
					"fieldname": "custom_retirement_excess",
					"label": "Retirement Contribution Over Cap (year)",
					"fieldtype": "Currency",
					"insert_after": "custom_income_tax_computed",
					"read_only": 1,
					"description": "SSF + CIT + PF above the lower of ⅓ of income or 5,00,000, added back to taxable income.",
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
	for dt in ("Income Tax Slab", "Salary Slip"):
		frappe.clear_cache(doctype=dt)


def upsert(doctype, name, values, name_field=None):
	"""Update `name` in place, or create it. Exemption categories are Prompt-named;
	Salary Component is named from `name_field`."""
	if frappe.db.exists(doctype, name):
		doc = frappe.get_doc(doctype, name)
	else:
		doc = frappe.new_doc(doctype)
		if name_field:
			doc.set(name_field, name)
		else:
			doc.set("__newname", name)
	doc.update(values)
	doc.flags.ignore_permissions = True
	doc.save()
