"""Overtime and the late fine, priced the way NGI's salary sheet prices them.

The Falgun 2082 sheet derives both from each person's own basic, at the Labour
Act's hourly wage of basic / 30 days / 8 hours:

    OT Rate / Hr         = Basic / 30 / 8 * 1.5     (column O)
    Late Deduction Rate  = Basic / 30 / 8 / 60      (column P, per minute)

So neither is a flat rate someone types — a pay rise moves both. Components now
carry a rate basis: `Fixed Rate` (tea at 235 a day) or `Hourly Basic ×
Multiplier` (1.5 for overtime, 1 for the fine, applied to hours).

What each one counts:

    Overtime   `Authorised Overtime` — hours authorised on a submitted Overtime
               Sheet and backed by the punches. Policy 5.1: the per-day sheet
               decides eligibility. It used to be `Worked on Holiday` per hour
               for everybody, officers included.
    Late Fine  `Late Time` — late arrival plus leaving early, against the day's
               shift, which is the sheet's "Late Time" and the report's.

The sheet types the late rate as 0 for its managers, so the fine has a per-person
exemption: `Late Fine Exempt` on the Employee.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

NEW_CONDITIONS = ("Authorised Overtime", "Late Time")


def execute():
	create_custom_fields(
		{
			"Salary Component": [
				{
					"fieldname": "custom_rate_basis",
					"label": "Rate Basis",
					"fieldtype": "Select",
					"options": "Fixed Rate\nHourly Basic × Multiplier",
					"default": "Fixed Rate",
					"insert_after": "custom_default_rate",
					"depends_on": "custom_is_attendance_driven",
					"description": "Hourly Basic is the employee's basic / 30 / 8 — the Labour Act hourly wage",
				},
				{
					"fieldname": "custom_rate_multiplier",
					"label": "Multiplier",
					"fieldtype": "Float",
					"default": "1",
					"insert_after": "custom_rate_basis",
					"depends_on": 'eval:doc.custom_rate_basis=="Hourly Basic × Multiplier"',
					"description": "1.5 for overtime, 1 for the late fine",
				},
			],
			"Employee": [
				{
					"fieldname": "custom_late_fine_exempt",
					"label": "Late Fine Exempt",
					"fieldtype": "Check",
					"insert_after": "custom_ot_eligibility",
					"description": "Late time is still recorded, but not fined — NGI's managers",
				},
			],
		},
		ignore_validate=True,
	)

	add_conditions()

	configure(
		"Overtime",
		condition="Authorised Overtime",
		unit="Per Hour",
		multiplier=1.5,
		kind="Earning",
	)
	configure(
		"Late Fine",
		condition="Late Time",
		unit="Per Hour",
		multiplier=1,
		kind="Deduction",
	)
	frappe.clear_cache(doctype="Salary Component")


def add_conditions():
	name = frappe.db.get_value(
		"Custom Field", {"dt": "Salary Component", "fieldname": "custom_condition_type"}, "name"
	)
	if not name:
		return
	options = (frappe.db.get_value("Custom Field", name, "options") or "").split("\n")
	for condition in NEW_CONDITIONS:
		if condition not in options:
			options.append(condition)
	frappe.db.set_value("Custom Field", name, "options", "\n".join(options))


def configure(component, condition, unit, multiplier, kind):
	if not frappe.db.exists("Salary Component", component):
		return
	frappe.db.set_value(
		"Salary Component",
		component,
		{
			"type": kind,
			"custom_is_attendance_driven": 1,
			"custom_condition_type": condition,
			"custom_unit": unit,
			"custom_rate_basis": "Hourly Basic × Multiplier",
			"custom_rate_multiplier": multiplier,
			"custom_default_rate": 0,
			"depends_on_payment_days": 0,
		},
	)
