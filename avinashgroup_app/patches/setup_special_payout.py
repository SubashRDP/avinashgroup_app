"""Payout on Payroll Entry, Salary Slip and Additional Salary: Dashain and encashment on their own slips.

The user (2026-10-26): the holiday bonus and leave encashment are paid
separately, with only that component, not bound to another month's salary.
A Payroll Entry's Payout says which payout it pays (blank: the month's
salary); its slips and the Additional Salary they pay carry the same value
(payroll/special_payout.py). The Yearly Payments fields follow it: the Dashain
fields belong to a Dashain Allowance payout, and Settle Leave now encashes only
on a Leave Encashment payout, while on the salary entry it recovers leave taken
beyond what was earned.

Fields only. Submitted slips and Additional Salary are left as they were: what
was paid on a monthly slip stays there.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

OPTIONS = "\nDashain Allowance\nLeave Encashment"
ON_DASHAIN = "eval:doc.custom_payout_type=='Dashain Allowance'"


def execute():
	create_custom_fields(
		{
			"Payroll Entry": [
				{
					"fieldname": "custom_payout_type",
					"label": "Payout",
					"fieldtype": "Select",
					"options": OPTIONS,
					"insert_after": "company",
					"in_list_view": 1,
					"in_standard_filter": 1,
					"description": "Blank: the month's salary. Dashain Allowance or Leave Encashment: pays only that, "
					"on slips of its own with the tax it causes, and its own journal and bank entry.",
				},
			],
			"Salary Slip": [
				{
					"fieldname": "custom_payout_type",
					"label": "Payout",
					"fieldtype": "Select",
					"options": OPTIONS,
					"insert_after": "status",
					"read_only": 1,
					"in_list_view": 1,
					"in_standard_filter": 1,
					"description": "Blank: the month's salary slip. Otherwise a payout slip, from its Payroll Entry.",
				},
			],
			"Additional Salary": [
				{
					"fieldname": "custom_payout_type",
					"label": "Payout",
					"fieldtype": "Select",
					"options": OPTIONS,
					"insert_after": "custom_source",
					"read_only": 1,
					"in_standard_filter": 1,
					"description": "Paid on its own payout slip, never on the monthly salary slip.",
				},
			],
		},
		update=True,
	)

	field_props = {
		"Payroll Entry-custom_pay_dashain": {
			"depends_on": ON_DASHAIN,
			"read_only": 1,
			"description": "Ticked on a Dashain Allowance payout. One month's basic, less for under a year's service.",
		},
		"Payroll Entry-custom_festival_component": {
			"depends_on": ON_DASHAIN,
			"mandatory_depends_on": ON_DASHAIN,
		},
		"Payroll Entry-custom_festival_cutoff": {"depends_on": ON_DASHAIN},
		"Payroll Entry-custom_pay_leave_encashment": {
			"label": "Settle Leave",
			"depends_on": "eval:doc.custom_payout_type!='Dashain Allowance'",
			"read_only_depends_on": "eval:doc.custom_payout_type=='Leave Encashment'",
			"description": "Year end (Ashadh) and anyone relieved this month. On the month's salary: leave taken "
			"beyond what was earned is deducted. On a Leave Encashment payout: leave left is paid.",
		},
		"Payroll Entry-custom_payroll_inputs_log": {
			"description": "What each run posted: tea, meals, overtime, late fines, advances, leave recovery; "
			"on a payout, the Dashain or the encashment.",
		},
	}
	for name, values in field_props.items():
		if frappe.db.exists("Custom Field", name):
			frappe.db.set_value("Custom Field", name, values)

	for doctype in ("Payroll Entry", "Salary Slip", "Additional Salary"):
		frappe.clear_cache(doctype=doctype)
