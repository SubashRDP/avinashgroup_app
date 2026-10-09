"""Salary Slip gets its Daily Breakdown table (payroll/daily_breakdown.py).

One row per day of the slip's period — attendance, share of fixed pay, tea,
meals, overtime, late fine, running balance — then month-end rows, ending at
net pay. Filled on every save by the Salary Slip validate hook.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	frappe.reload_doc("avinash_group_app", "doctype", "salary_slip_day")
	create_custom_fields(
		{
			"Salary Slip": [
				{
					"fieldname": "custom_daily_breakdown_section",
					"label": "Daily Breakdown",
					"fieldtype": "Section Break",
					"insert_after": "base_total_in_words",
					"collapsible": 1,
				},
				{
					"fieldname": "custom_daily_breakdown",
					"label": "Daily Breakdown",
					"fieldtype": "Table",
					"options": "Salary Slip Day",
					"insert_after": "custom_daily_breakdown_section",
					"read_only": 1,
					"description": (
						"Each day of the month: attendance, that day's share of fixed pay, tea, meals, "
						"overtime and late fine, and the running balance; then SSF, tax and other "
						"monthly lines, ending at the net pay. Filled automatically on save."
					),
				},
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Salary Slip")
