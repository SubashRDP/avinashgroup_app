"""Meal follows authorised overtime: OT-eligible staff only, holiday = 2 meals.

The meal rule changed on 2026-10-09 (payroll/attendance_allowance.py
`_meals_for_day`): a meal is earned only on a day a submitted Overtime Sheet
calls the person in, 1.5 h early or late on a working day earns one each, and
a holiday worked earns two, never more than two a day. So:

  * the Meal component is marked Only OT-Eligible Staff;
  * Holiday: Hours for 1 / 2 Meals go — a holiday is two meals, whatever the
    hours;
  * Time Offset says what it now means.
"""

import frappe


def execute():
	if frappe.db.exists("Salary Component", "Meal"):
		frappe.db.set_value("Salary Component", "Meal", "custom_ot_eligible_only", 1, update_modified=False)

	for fieldname in ("custom_holiday_hours_one_meal", "custom_holiday_hours_two_meals"):
		name = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)

	name = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": "custom_time_offset_hours"})
	if name:
		frappe.db.set_value(
			"Custom Field",
			name,
			"description",
			"Meal: called this many hours early, or kept this many hours late, on an authorised "
			"overtime day earns one meal each. Early Entry / Late Stay / Late Arrival: the hours "
			"from shift start or end.",
		)
	frappe.clear_cache(doctype="Salary Component")
