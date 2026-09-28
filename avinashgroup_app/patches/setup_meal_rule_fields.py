"""Meal rule settings on the Salary Component form instead of in code.

The meal rule (policy 1.3 / 2.3) had three numbers fixed in
payroll/attendance_allowance.py: a holiday earns 1 meal at 6 h worked and 2 at
8 h, and never more than 2 a day. HR could not change them without a developer.
They are now fields in the Attendance-Driven Rule section, shown when the
Condition Type is Meal Entitlement, and seeded here with those same values so
pay does not change.

Also shows Time Offset (Hours) for Meal Entitlement: the rule reads it (1.5 h
early / late earns a meal) but the field was hidden on the Meal form.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MEAL = 'doc.custom_condition_type=="Meal Entitlement"'

# Today's policy values, written once so nothing changes on migrate.
SEED = {"custom_holiday_hours_one_meal": 6, "custom_holiday_hours_two_meals": 8, "custom_max_per_day": 2}


def execute():
	create_custom_fields(
		{
			"Salary Component": [
				{
					"fieldname": "custom_holiday_hours_one_meal",
					"label": "Holiday: Hours for 1 Meal",
					"fieldtype": "Float",
					"insert_after": "custom_time_offset_hours",
					"depends_on": f"eval:{MEAL}",
					"description": "Worked at least this long on a holiday earns 1 meal. Blank: no holiday meal.",
				},
				{
					"fieldname": "custom_holiday_hours_two_meals",
					"label": "Holiday: Hours for 2 Meals",
					"fieldtype": "Float",
					"insert_after": "custom_holiday_hours_one_meal",
					"depends_on": f"eval:{MEAL}",
					"description": "Worked at least this long on a holiday earns 2 meals.",
				},
				{
					"fieldname": "custom_max_per_day",
					"label": "Max Meals per Day",
					"fieldtype": "Int",
					"insert_after": "custom_holiday_hours_two_meals",
					"depends_on": f"eval:{MEAL}",
					"description": "Cap on meals earned in one day. 0: no cap.",
				},
			]
		},
		update=True,
	)

	offset = "Salary Component-custom_time_offset_hours"
	if frappe.db.exists("Custom Field", offset):
		frappe.db.set_value(
			"Custom Field",
			offset,
			"depends_on",
			'eval:["Early Entry Before","Late Stay After","Late Arrival After","Meal Entitlement"].includes(doc.custom_condition_type)',
		)
	frappe.clear_cache(doctype="Salary Component")

	for name in frappe.get_all("Salary Component", filters={"custom_condition_type": "Meal Entitlement"}, pluck="name"):
		current = frappe.db.get_value("Salary Component", name, list(SEED), as_dict=True)
		values = {k: v for k, v in SEED.items() if not current.get(k)}
		if values:
			frappe.db.set_value("Salary Component", name, values, update_modified=False)
