"""Daily-wage labour: paid for the days actually worked, at the day's rate.

NGK's labour sheet pays 754 a day for the days in the month someone worked, and
overtime at that day's rate / 8 * 1.5, with 1% withheld. A monthly structure
cannot say that — its basic is prorated by payment days, which include the
holidays in between — so the day's wage is the assignment's base on a structure
flagged Daily Wage, and a `Daily Wage` component counts the present days through
the attendance engine, as tea already does. Overtime reads the flag and divides
by 8 instead of 30 * 8. The 1% is the tax slab's first band, as for everyone
outside the SSF.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

COMPONENT = "Daily Wage"


def execute():
	create_custom_fields(
		{
			"Salary Structure": [
				{
					"fieldname": "custom_daily_wage",
					"label": "Daily Wage",
					"fieldtype": "Check",
					"insert_after": "payroll_frequency",
					"description": "The assignment's base is one day's pay, paid for each day present",
				}
			]
		},
		ignore_validate=True,
	)

	name = frappe.db.get_value(
		"Custom Field", {"dt": "Salary Component", "fieldname": "custom_rate_basis"}, "name"
	)
	if name:
		options = (frappe.db.get_value("Custom Field", name, "options") or "").split("\n")
		if "Daily Wage" not in options:
			options.append("Daily Wage")
		frappe.db.set_value("Custom Field", name, "options", "\n".join(options))

	if not frappe.db.exists("Salary Component", COMPONENT):
		frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": COMPONENT,
				"salary_component_abbr": "DW",
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
			"custom_is_attendance_driven": 1,
			"custom_condition_type": "Status = Present",
			"custom_unit": "Per Day",
			"custom_half_day_counts": "Half Day",
			"custom_rate_basis": "Daily Wage",
			"custom_default_rate": 0,
			"custom_summary_group": "Daily Wage",
		},
	)
	frappe.clear_cache(doctype="Salary Component")
