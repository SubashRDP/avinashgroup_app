"""Leave Application over days already marked Present: allowed, not refused.

Stock HRMS (`LeaveApplication.validate_attendance`) refuses any leave whose
dates hold a submitted Present / Work From Home attendance: "Attendance for
employee … is already marked for the following dates". Here that blocks the
ordinary backdated case: the device marked the day Present from the punches
(say 11:53 – 15:52), and the leave is filed afterwards. HR had to cancel the
attendance by hand first.

With the check gone, HRMS's own `update_attendance` takes the existing row on
approval (db_set → On Leave, leave type and application linked), exactly as it
already does over an Absent day. Then `biometric.attendance_override.
on_leave_submit` applies policy 3.4: a day the person punched on becomes a
Half Day with the leave kept. A Present day with no punch (hand-marked) simply
becomes On Leave. Cancelling the leave re-marks punched past days from the
punches (`on_leave_cancel`), so the Present day comes back.

Deliberately narrow:
  * a day inside a submitted regular salary slip is still refused — it was
    paid as worked, and HRMS's db_set would rewrite it behind payroll's back.
    Same rule as every other attendance change in this app (`_paid`).
  * nothing else in HRMS's validate changes: balance, overlap, allocation,
    Leave Period and the approval workflow all run as before.

Registered in hooks.override_doctype_class.
"""

import frappe
from frappe import _
from frappe.utils import formatdate, getdate

from hrms.hr.doctype.leave_application.leave_application import (
	AttendanceAlreadyMarkedError,
	LeaveApplication,
)

from avinashgroup_app.biometric.attendance_override import _paid


class BackdatedLeaveApplication(LeaveApplication):
	def validate_attendance(self):
		"""Refuse only Present days inside a submitted salary slip.

		Raises AttendanceAlreadyMarkedError (HRMS's own) naming those days."""
		present = frappe.get_all(
			"Attendance",
			# Same filter as HRMS's check, so exactly the days it would refuse.
			filters={
				"employee": self.employee,
				"attendance_date": ("between", [self.from_date, self.to_date]),
				"status": ("in", ["Present", "Work From Home"]),
				"docstatus": 1,
				"half_day_status": ("!=", "Absent"),
			},
			pluck="attendance_date",
			order_by="attendance_date",
		)
		paid = [d for d in present if _paid(self.employee, d)]
		if paid:
			frappe.throw(
				_(
					"Attendance for employee {0} is already marked Present on {1}, inside a submitted salary slip. Cancel the slip first, or leave those days out."
				).format(self.employee, ", ".join(formatdate(getdate(d)) for d in paid)),
				AttendanceAlreadyMarkedError,
			)
