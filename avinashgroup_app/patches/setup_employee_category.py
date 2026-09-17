"""Employee Category: the field on Employee, and OT eligibility following it.

`custom_ot_eligibility` was a free checkbox set per person. It now fetches from
the employee's category, so the category is the one place the rule is decided.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	frappe.reload_doc("avinash_group_app", "doctype", "employee_category")

	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "custom_employee_category",
					"label": "Employee Category",
					"fieldtype": "Link",
					"options": "Employee Category",
					"insert_after": "custom_nepal_hrms_section",
					"in_standard_filter": 1,
					"description": "Decides overtime vs replacement leave for holiday work",
				}
			]
		},
		update=True,
	)

	name = frappe.db.get_value(
		"Custom Field", {"dt": "Employee", "fieldname": "custom_ot_eligibility"}, "name"
	)
	if name:
		frappe.db.set_value(
			"Custom Field",
			name,
			{
				"fetch_from": "custom_employee_category.ot_eligible",
				"fetch_if_empty": 0,
				"read_only": 1,
				"insert_after": "custom_employee_category",
				"description": "Set by the Employee Category",
			},
		)
	frappe.clear_cache(doctype="Employee")
