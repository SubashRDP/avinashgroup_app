"""Leave days the person punched on, made Half Day (policy 3.4).

The rule only ran when an attendance was saved with an in-time. HRMS writes a
leave's attendance with none, and punches arriving later never re-save the
row, so a leave given over days already worked stayed a whole day On Leave
(NGI-LEAVE-83/84-00005: 11–13 Sep, punched in every day). The rule now runs on
leave submit and on punch sync (biometric.attendance_override
`half_day_if_came_in`, which leaves a day inside a submitted salary slip
alone); this applies it to the days already marked.
"""

import frappe

from avinashgroup_app.biometric.attendance_override import half_day_if_came_in


def execute():
	rows = frappe.db.sql(
		"""
		SELECT a.employee, a.attendance_date
		FROM `tabAttendance` a
		WHERE a.docstatus = 1 AND a.status = 'On Leave' AND IFNULL(a.leave_application, '') != ''
		  AND EXISTS (
			SELECT 1 FROM `tabEmployee Checkin` c
			WHERE c.employee = a.employee AND DATE(c.time) = a.attendance_date)
		""",
		as_dict=True,
	)
	for r in rows:
		half_day_if_came_in(r.employee, r.attendance_date)
