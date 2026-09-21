"""Meals are earned by the extra hours, not by turning up.

Configured as "one per present day" the Meal component paid 132,525 for Bhadra
against the client's Falgun figure of 52,275 — because every person present every
day collected a meal.

Policy 1.3 and 2.3 (client meeting 2026-09-15): one meal for coming 1.5 hours
early, one for staying 1.5 hours late, never more than two in a day; on a holiday
one meal at 6 hours worked and two at 8.

Adds the `Meal Entitlement` condition to Salary Component and points the Meal
component at it.
"""

import frappe

CONDITIONS = (
	"",
	"Working Hours >= Threshold",
	"Status = Present",
	"Status = Half Day",
	"Worked on Holiday",
	"Meal Entitlement",
	"Early Entry Before",
	"Late Stay After",
	"Late Arrival After",
)
MEAL_OFFSET_HOURS = 1.5


def execute():
	name = frappe.db.get_value(
		"Custom Field", {"dt": "Salary Component", "fieldname": "custom_condition_type"}, "name"
	)
	if name:
		frappe.db.set_value("Custom Field", name, "options", "\\n".join(CONDITIONS))
		frappe.clear_cache(doctype="Salary Component")

	if frappe.db.exists("Salary Component", "Meal"):
		frappe.db.set_value(
			"Salary Component",
			"Meal",
			{
				"custom_is_attendance_driven": 1,
				"custom_condition_type": "Meal Entitlement",
				"custom_unit": "Per Day",          # the quantity is meals, not days
				"custom_time_offset_hours": MEAL_OFFSET_HOURS,
			},
		)
