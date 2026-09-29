"""The Labour Act wage basis on the Salary Component form instead of in code.

Overtime and the late fine are priced off each person's own basic at the Act's
hourly wage — basic / 30 days / 8 hours — and those two divisors were constants
in payroll/attendance_allowance.py. HR could not restate the basis (a 26-day
month, a 7-hour shift) without a developer, and could not restate it for
overtime without also moving the late fine.

They are now fields in the rate section, shown when the Rate Basis is
`Hourly Basic × Multiplier`, and seeded with 30 and 8 so no rate changes on
migrate. A blank field still falls back to the Act's numbers in code rather
than dividing by zero.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

HOURLY = 'eval:doc.custom_rate_basis=="Hourly Basic × Multiplier"'

# Today's basis, written once so nothing changes on migrate.
SEED = {"custom_rate_days_per_month": 30, "custom_rate_hours_per_day": 8}


def execute():
	create_custom_fields(
		{
			"Salary Component": [
				{
					"fieldname": "custom_rate_days_per_month",
					"label": "Rate: Days per Month",
					"fieldtype": "Float",
					"insert_after": "custom_rate_multiplier",
					"depends_on": HOURLY,
					"description": "Days a month's basic is spread over. Blank: 30, the Labour Act's.",
				},
				{
					"fieldname": "custom_rate_hours_per_day",
					"label": "Rate: Hours per Day",
					"fieldtype": "Float",
					"insert_after": "custom_rate_days_per_month",
					"depends_on": HOURLY,
					"description": "Hours in a working day. Blank: 8. A daily wage is divided by this alone.",
				},
			]
		},
		update=True,
	)

	# The Rate Basis description named the divisors it no longer fixes.
	basis = "Salary Component-custom_rate_basis"
	if frappe.db.exists("Custom Field", basis):
		frappe.db.set_value(
			"Custom Field",
			basis,
			"description",
			"Hourly Basic is the employee's basic over the days and hours set below",
		)
	frappe.clear_cache(doctype="Salary Component")

	for name in frappe.get_all(
		"Salary Component",
		filters={"custom_rate_basis": "Hourly Basic × Multiplier"},
		pluck="name",
	):
		current = frappe.db.get_value("Salary Component", name, list(SEED), as_dict=True)
		values = {k: v for k, v in SEED.items() if not current.get(k)}
		if values:
			frappe.db.set_value("Salary Component", name, values, update_modified=False)
