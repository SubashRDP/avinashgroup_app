"""Allowance Category: a group's rate for an attendance-driven allowance.

NGI's Falgun sheet pays tea & conveyance at 235 a day to one group of staff and
40 to another, decided by a category on the employee — plant and office each
contain both, so it is not a department rule. Typing the rate on all 92 employees
would make "235 becomes 250" a 51-row edit.

Adds `Employee.custom_allowance_category`; the rate itself lives on the category.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	frappe.reload_doc("avinash_group_app", "doctype", "allowance_category_rate")
	frappe.reload_doc("avinash_group_app", "doctype", "allowance_category")

	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "custom_allowance_category",
					"label": "Allowance Category",
					"fieldtype": "Link",
					"options": "Allowance Category",
					"insert_after": "custom_employee_category",
					"in_standard_filter": 1,
					"description": (
						"Decides this employee's rate for attendance-driven allowances "
						"(tea & conveyance, meals). Their own Attendance Allowances row "
						"still wins where one exists."
					),
				}
			]
		},
		update=True,
	)
