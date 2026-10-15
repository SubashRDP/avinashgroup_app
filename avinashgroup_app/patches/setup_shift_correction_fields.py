"""Mark a Shift Assignment that HR made to correct a misplaced shift.

hr/punch_correction.py lets HR put an employee on another shift for a day or a
few days from the Monthly Attendance BS grid. It creates a Shift Assignment
covering exactly those days (the standing one is cut around them), and these
fields say why it exists: the shift the days were on before, who, when and the
reason. The report highlights every day such an assignment covers, so a day
re-marked on a hand-picked shift never reads like the roster's own.

On the assignment, not the Attendance: the attendance is rebuilt by the
correction and may be rebuilt again later; the assignment is what decides the
shift and stays.

All read-only — written by the correction, never typed.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Shift Assignment": [
				{
					"fieldname": "custom_correction_section",
					"label": "Shift Correction",
					"fieldtype": "Section Break",
					"insert_after": "amended_from",
					"collapsible": 1,
					"depends_on": "custom_shift_corrected",
				},
				{
					"fieldname": "custom_shift_corrected",
					"label": "Corrected from Monthly Attendance",
					"fieldtype": "Check",
					"insert_after": "custom_correction_section",
					"read_only": 1,
					"in_standard_filter": 1,
				},
				{
					"fieldname": "custom_corrected_from_shift",
					"label": "Shift Before",
					"fieldtype": "Data",
					"insert_after": "custom_shift_corrected",
					"read_only": 1,
					"description": "The shift (or shifts) these days were on before the correction",
				},
				{
					"fieldname": "custom_shift_correction_reason",
					"label": "Reason",
					"fieldtype": "Small Text",
					"insert_after": "custom_corrected_from_shift",
					"read_only": 1,
				},
				{
					"fieldname": "custom_shift_correction_column",
					"fieldtype": "Column Break",
					"insert_after": "custom_shift_correction_reason",
				},
				{
					"fieldname": "custom_shift_corrected_by",
					"label": "Corrected By",
					"fieldtype": "Link",
					"options": "User",
					"insert_after": "custom_shift_correction_column",
					"read_only": 1,
				},
				{
					"fieldname": "custom_shift_corrected_on",
					"label": "Corrected On",
					"fieldtype": "Datetime",
					"insert_after": "custom_shift_corrected_by",
					"read_only": 1,
				},
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Shift Assignment")
