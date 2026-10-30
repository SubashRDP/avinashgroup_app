"""Let HR excuse a late day on submitted Attendance, without cancel and amend.

Until 2026-10-29 Late Excused and its reason could only be set on a draft, so
excusing a device-marked day meant Cancel → Amend → tick → Submit, which also
replaced the Attendance with a "-1" copy. Both fields are now Allow on Submit;
the late rule that `validate` used to apply is carried by the Update after
Submit hooks in biometric/attendance_override.py, which also refuse the change
once the day's salary slip is submitted.
"""

import frappe


def execute():
	for fieldname in ("custom_late_excused", "custom_late_excuse_reason"):
		name = frappe.db.get_value("Custom Field", {"dt": "Attendance", "fieldname": fieldname}, "name")
		if name:
			frappe.db.set_value("Custom Field", name, "allow_on_submit", 1)
	frappe.clear_cache(doctype="Attendance")
