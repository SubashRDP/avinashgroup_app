"""Mark which Shift Types take part in the monthly rotation.

Staff rotate between two of NGI's shifts month by month, and only those two; the
day shift and every other company's shifts are fixed. `hr/shift_rotation.py`
needs to know which is which, and that is HR's data to keep, so it is a checkbox
on the Shift Type — `Takes Part in Rotation` — rather than names in code.

Seeded here for the one company that rotates today: Nepal Gas Udhyog Pvt. Ltd.,
the 6 AM - 2 PM and 12 PM - 8 PM shifts. They are found by company and hours, not
by name, because the same two shifts are `NGI 6 AM - 2 PM` on one site and plain
`6 AM - 2 PM` on another. A site without that company, or without those hours,
is left with nothing ticked and HR ticks its own.

Only ticks, never unticks, and only when nothing in that company is ticked yet:
re-running it must not undo a choice HR has made since.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from avinashgroup_app.hr.shift_rotation import ROTATION_FIELD

# The developer's request, 2026-10-01: "morning 6 to 2 and 12 to 8 only can be in
# rotation". (company, ((start, end), ...)) — hours as HH:MM:SS.
SEED_COMPANY = "Nepal Gas Udhyog Pvt. Ltd."
SEED_HOURS = (("06:00:00", "14:00:00"), ("12:00:00", "20:00:00"))


def execute():
	create_custom_fields(
		{
			"Shift Type": [
				{
					"fieldname": ROTATION_FIELD,
					"label": "Takes Part in Rotation",
					"fieldtype": "Check",
					"default": "0",
					"insert_after": "custom_company",
					"in_list_view": 1,
					"in_standard_filter": 1,
					"description": (
						"Staff can be moved between the rotational shifts of one company, many at a "
						"time, with Move Staff to This Shift. A shift left unticked is fixed: nobody "
						"is rotated onto it or off it."
					),
				}
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Shift Type")

	if frappe.db.exists("Shift Type", {"custom_company": SEED_COMPANY, ROTATION_FIELD: 1}):
		return
	for name in shifts_to_seed():
		frappe.db.set_value("Shift Type", name, ROTATION_FIELD, 1, update_modified=False)


def shifts_to_seed():
	"""Names of the seed company's Shift Types that keep the seeded hours."""
	names = []
	for start, end in SEED_HOURS:
		names += frappe.get_all(
			"Shift Type",
			filters={"custom_company": SEED_COMPANY, "start_time": start, "end_time": end},
			pluck="name",
		)
	return names
