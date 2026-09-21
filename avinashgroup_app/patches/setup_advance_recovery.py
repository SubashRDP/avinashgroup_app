"""Advances recovered from salary in monthly instalments, against a balance.

Adds the two things HRMS's Employee Advance lacks — how much to take back each
month, and from which month — and makes salary recovery the default, since
that is how every advance on the client's sheet is repaid.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
	create_custom_fields(
		{
			"Employee Advance": [
				{
					"fieldname": "custom_recovery_section",
					"label": "Recovery from Salary",
					"fieldtype": "Section Break",
					"insert_after": "repay_unclaimed_amount_from_salary",
					"depends_on": "repay_unclaimed_amount_from_salary",
				},
				{
					"fieldname": "custom_monthly_instalment",
					"label": "Monthly Instalment",
					"fieldtype": "Currency",
					"insert_after": "custom_recovery_section",
					"description": "Taken from each month's salary until nothing is outstanding. Blank takes the whole balance in one month.",
				},
				{
					"fieldname": "custom_recovery_cb",
					"fieldtype": "Column Break",
					"insert_after": "custom_monthly_instalment",
				},
				{
					"fieldname": "custom_recover_from",
					"label": "Recover From",
					"fieldtype": "Date",
					"insert_after": "custom_recovery_cb",
					"description": "A date in the first BS month to deduct in. Blank starts with the next payroll run.",
				},
			]
		},
		ignore_validate=True,
	)
	make_property_setter(
		"Employee Advance", "repay_unclaimed_amount_from_salary", "default", "1", "Text",
		validate_fields_for_doctype=False,
	)
	frappe.db.set_value("Salary Component", "Salary Advance", {"type": "Deduction", "custom_is_attendance_driven": 0})
