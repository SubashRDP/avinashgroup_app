"""Install Dashain Bonus, and make the component behave like a festival bonus.

The bonus is taxable income paid on top of the month, and it is not prorated by
attendance — a person who was absent three days still gets their full festival
allowance, so `depends_on_payment_days` stays off.
"""

import frappe

COMPONENT = "Dashain Bonus"


def execute():
	frappe.reload_doc("avinash_group_app", "doctype", "dashain_bonus_employee")
	frappe.reload_doc("avinash_group_app", "doctype", "dashain_bonus")

	if not frappe.db.exists("Salary Component", COMPONENT):
		frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": COMPONENT,
				"salary_component_abbr": "DB",
				"type": "Earning",
			}
		).insert(ignore_permissions=True)

	frappe.db.set_value(
		"Salary Component",
		COMPONENT,
		{
			"type": "Earning",
			"is_tax_applicable": 1,
			"depends_on_payment_days": 0,
			"amount_based_on_formula": 0,
			"formula": "",
			"amount": 0,
			"round_to_the_nearest_integer": 1,
			"disabled": 0,
		},
	)
