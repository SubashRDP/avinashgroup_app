"""More than 2 hours late is a half day (policy 1.2), as hours rather than a clock time.

The rule already existed as `custom_late_arrival_cutoff_time`, an absolute time
per shift. That has to be re-typed whenever a shift's hours change, and on this
site two shifts had been saved with a stray 11:24:33.06 — which on the
12 PM - 8 PM shift would have made every attendance a half day, since that shift
starts at 12:00.

Adds `custom_half_day_if_late_by_hours` (default 2, measured from each shift's
own start) and clears cutoffs that can only be accidents: one that falls before
its shift starts, or one carrying seconds, since a typed cutoff is whole minutes.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DEFAULT_LATE_HOURS = 2  # policy 1.2: more than two hours late is a half day


def execute():
	create_custom_fields(
		{
			"Shift Type": [
				{
					"fieldname": "custom_half_day_if_late_by_hours",
					"label": "Half Day If Late By (Hours)",
					"fieldtype": "Float",
					"insert_after": "late_entry_grace_period",
					"default": DEFAULT_LATE_HOURS,
					"precision": "2",
					"description": (
						"Hours after this shift starts. Someone who punches in later than that "
						"has worked a half day, whatever their hours add up to. 0 turns it off."
					),
				}
			]
		},
		update=True,
	)

	# Existing shifts predate the field, so it is 0 on them: give them the policy.
	frappe.db.sql(
		"""update `tabShift Type` set custom_half_day_if_late_by_hours = %s
		where ifnull(custom_half_day_if_late_by_hours, 0) = 0""",
		DEFAULT_LATE_HOURS,
	)

	for shift in frappe.get_all(
		"Shift Type", ["name", "start_time", "custom_late_arrival_cutoff_time"]
	):
		cutoff = shift.custom_late_arrival_cutoff_time
		if not cutoff:
			continue
		accidental = (shift.start_time and cutoff <= shift.start_time) or cutoff.seconds % 60
		if accidental:
			frappe.db.set_value("Shift Type", shift.name, "custom_late_arrival_cutoff_time", None)
			frappe.logger().info(f"[late half day] cleared accidental cutoff on {shift.name}")
