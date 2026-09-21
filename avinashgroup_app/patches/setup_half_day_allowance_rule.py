"""A half day still earns the full allowance, unless a component says otherwise.

"If a person comes then they are eligible" — the client's rule for tea and
conveyance (2026-09-21). The engine counted a half day as half a day, which
quietly paid 117.50 instead of 235 for turning up.

Whether that is right depends on the allowance, so it is a switch on the
component rather than a rule in code: Full Day (the default), Half Day, or Not
At All.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Salary Component": [
				{
					"fieldname": "custom_half_day_counts",
					"label": "A Half Day Counts As",
					"fieldtype": "Select",
					"options": "Full Day\nHalf Day\nNot At All",
					"default": "Full Day",
					"insert_after": "custom_unit",
					"depends_on": "custom_is_attendance_driven",
					"description": "For per-day allowances: what someone who worked half a day earns.",
				}
			]
		},
		update=True,
	)
	frappe.db.sql(
		"""update `tabSalary Component` set custom_half_day_counts = 'Full Day'
		where ifnull(custom_half_day_counts, '') = ''"""
	)
