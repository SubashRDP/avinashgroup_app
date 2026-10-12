"""Who gets the women's rebate is on the Employee; how much is on the slab.

Income Tax Act Schedule 1, 1(10): a resident woman whose ONLY income is salary
gets a rebate on her tax. Gender alone does not decide it — a woman with rent,
business or investment income does not qualify, and only HR knows that. So the
Employee carries a tick, unticked by default (no rebate until HR says so), and
the Income Tax Slab keeps the percentage the Finance Act sets for the year.
payroll/tax_relief.py gives the rebate only when both are there.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "custom_womens_tax_rebate",
					"label": "Women's Tax Rebate",
					"fieldtype": "Check",
					"insert_after": "custom_late_fine_exempt",
					"depends_on": "eval:doc.gender=='Female'",
					"description": (
						"Tick only if salary is her only income (no rent, business or investment income). "
						"Her tax is then reduced by the Women's Rebate (%) on the company's Income Tax Slab."
					),
				}
			],
			"Income Tax Slab": [
				{
					"fieldname": "custom_women_rebate_percent",
					"label": "Women's Rebate (%)",
					"fieldtype": "Percent",
					"insert_after": "standard_tax_exemption_amount",
					"allow_on_submit": 1,
					"description": (
						"Rebate on the tax of a woman whose only income is salary (Income Tax Act Schedule 1). "
						"Applies only to employees ticked Women's Tax Rebate. Blank: no rebate."
					),
				}
			],
		},
		update=True,
	)
	frappe.clear_cache(doctype="Employee")
	frappe.clear_cache(doctype="Income Tax Slab")
