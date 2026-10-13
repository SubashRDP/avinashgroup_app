"""More than 2 hours late is a half day (policy 1.2), as hours rather than a clock time.

The rule already existed as `custom_late_arrival_cutoff_time`, an absolute time
per shift. That has to be re-typed whenever a shift's hours change, and on this
site two shifts had been saved with a stray 11:24:33.06 — which on the
12 PM - 8 PM shift would have made every attendance a half day, since that shift
starts at 12:00.

Adds `custom_half_day_if_late_by_hours` (default 2, measured from each shift's
own start). It used to also clear accidental cutoffs; the cutoff field itself is
now gone (drop_late_arrival_cutoff, 2026-10-13), so there is nothing to clear.
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

