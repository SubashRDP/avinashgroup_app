"""Overtime and the late fine are priced on the BS month's actual days, not a flat 30.

The hourly wage was basic ÷ 30 ÷ 8, as on the client's Excel sheets, while the
slip prorates Basic by the BS month's real length (29–32). On 2026-10-12 the
user decided the hourly wage follows the real month too
(payroll/attendance_allowance.py `_hourly_basic`).

"Rate: Days per Month" now means: blank = the month's actual days; a number
fixes it. setup_ot_rate_fields seeded 30 on every component priced off basic,
so that seed is cleared here. A value other than 30 was typed by someone on
purpose and is left alone.
"""

import frappe


def execute():
	cleared = frappe.get_all(
		"Salary Component",
		filters={"custom_rate_basis": "Hourly Basic × Multiplier", "custom_rate_days_per_month": 30},
		pluck="name",
	)
	for name in cleared:
		frappe.db.set_value("Salary Component", name, "custom_rate_days_per_month", 0, update_modified=False)

	field = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": "custom_rate_days_per_month"})
	if field:
		frappe.db.set_value(
			"Custom Field",
			field,
			"description",
			"Days a month's basic is spread over for the hourly wage. Blank: the actual days of the BS month "
			"(29–32), the same as the slip prorates Basic. Type 30 to use a flat 30-day month.",
		)
	frappe.clear_cache(doctype="Salary Component")
	print(f"rate_on_actual_month_days: cleared the 30-day seed on {', '.join(cleared) or 'no component'}")
