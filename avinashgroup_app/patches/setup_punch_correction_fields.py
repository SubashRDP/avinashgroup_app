"""Stamp an Employee Checkin that HR corrected by hand.

hr/punch_correction.py lets HR set a day's first IN and last OUT from the
Monthly Attendance BS grid, moving or adding punches. A punch that says 09:00
because the device read 09:00 and one that says 09:00 because somebody typed it
must not look the same: payroll is paid from them. These fields keep the
device's original reading, who changed it, when and why, and the report
highlights every day that carries one.

On the punch, not the Attendance: a corrected day's attendance is rebuilt, and
self-heal or a backdated shift change may rebuild it again, but the punches stay.

All read-only — they are written by the correction, never typed.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Employee Checkin": [
				{
					"fieldname": "custom_correction_section",
					"label": "HR Correction",
					"fieldtype": "Section Break",
					"insert_after": "shift_actual_end",
					"collapsible": 1,
					"depends_on": "custom_time_edited",
				},
				{
					"fieldname": "custom_time_edited",
					"label": "Corrected by HR",
					"fieldtype": "Check",
					"insert_after": "custom_correction_section",
					"read_only": 1,
					"in_standard_filter": 1,
					"description": "Time set by hand from Monthly Attendance BS, not read from the device",
				},
				{
					"fieldname": "custom_original_time",
					"label": "Device Time",
					"fieldtype": "Datetime",
					"insert_after": "custom_time_edited",
					"read_only": 1,
					"description": "What the device recorded. Blank when the punch was added by hand",
				},
				{
					"fieldname": "custom_edit_reason",
					"label": "Reason",
					"fieldtype": "Small Text",
					"insert_after": "custom_original_time",
					"read_only": 1,
				},
				{
					"fieldname": "custom_correction_column",
					"fieldtype": "Column Break",
					"insert_after": "custom_edit_reason",
				},
				{
					"fieldname": "custom_edited_by",
					"label": "Corrected By",
					"fieldtype": "Link",
					"options": "User",
					"insert_after": "custom_correction_column",
					"read_only": 1,
				},
				{
					"fieldname": "custom_edited_on",
					"label": "Corrected On",
					"fieldtype": "Datetime",
					"insert_after": "custom_edited_by",
					"read_only": 1,
				},
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Employee Checkin")
