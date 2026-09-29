"""Let HR waive one day's lateness.

The late rules are deliberately blind: more than two hours late is a half day,
and every late minute is fined. Neither knows about the landslide on the highway
or the funeral, so HR had no answer for a late day everybody agreed should not
count except editing the attendance itself.

`Late Excused` on the Attendance is that answer. The lateness stays recorded —
the deviation fields, the attendance report and the Work on Holiday report all
still show the minutes — but the fine is not charged, and a day the late rule
demoted goes back to Present. A reason is asked for, because a waiver nobody has
to justify is a waiver nobody can audit.

Read in biometric/attendance_override.py (the half day) and
payroll/attendance_allowance.py (the fine).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Attendance": [
				{
					"fieldname": "custom_late_excused",
					"label": "Late Excused",
					"fieldtype": "Check",
					"insert_after": "custom_late_exit",
					"description": "Lateness stays recorded, but is not fined and does not make a half day",
				},
				{
					"fieldname": "custom_late_excuse_reason",
					"label": "Reason for Excusing",
					"fieldtype": "Small Text",
					"insert_after": "custom_late_excused",
					"depends_on": "custom_late_excused",
					"mandatory_depends_on": "custom_late_excused",
				},
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Attendance")
