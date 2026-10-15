"""Attendance Correction Log — who changed which day's attendance by hand, and why.

Punches moved, added or deleted, and shifts changed for a day, from the Monthly
Attendance BS edit dialog or the Employee Checkin form, all re-mark attendance
that payroll pays from. The stamps on each punch and Shift Assignment say what
happened to THAT record; this is the one list HR and management open to see
every correction, by employee, date, user or kind.

Written only by hr/punch_correction.log_correction, inside the same transaction
as the correction, so an entry exists exactly when the change does. Nobody
creates or edits one (in_create, read-only fields, no write permission); only a
System Manager may delete.
"""

import frappe
from frappe.model.document import Document


class AttendanceCorrectionLog(Document):
	def validate(self):
		if not self.is_new() and not frappe.flags.in_patch:
			frappe.throw(frappe._("A correction log entry cannot be changed."))
