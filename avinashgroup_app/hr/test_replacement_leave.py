"""Tests for hr/replacement_leave.py — holiday work earns a full replacement day
for turning up at all (user, 2026-10-15).

Covers:
- shown_up: one punch is enough; a hand-keyed attendance with an in-time too
- ReplacementLeaveRequest skips HRMS's Present / ½-day check only for grants
  flagged shown_up_on_holiday
- holiday_meals thresholds (payroll/attendance_allowance.py)

Run:
    bench --site avinas1 run-tests --app avinashgroup_app \
        --module avinashgroup_app.hr.test_replacement_leave
"""

from datetime import datetime

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from avinashgroup_app.hr.replacement_leave import ReplacementLeaveRequest, shown_up
from avinashgroup_app.payroll.attendance_allowance import holiday_meals


class TestReplacementLeave(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = frappe.get_all("Company", pluck="name", order_by="creation", limit=1)[0]
		emp = frappe.new_doc("Employee")
		emp.first_name = "Replacement Leave Test"
		emp.gender = "Female"
		emp.date_of_birth = "1990-01-01"
		emp.date_of_joining = "2024-01-01"
		emp.company = company
		emp.status = "Active"
		emp.insert(ignore_permissions=True)
		cls.employee = emp.name
		cls.day = getdate(add_days(today(), -4))

	def test_one_punch_is_showing_up(self):
		self.assertFalse(shown_up(self.employee, self.day))
		frappe.flags.in_biometric_day_reconcile = True  # a device punch, not a hand correction
		try:
			frappe.get_doc(
				{
					"doctype": "Employee Checkin",
					"employee": self.employee,
					"time": datetime.combine(self.day, datetime.strptime("11:07", "%H:%M").time()),
					"log_type": "IN",
				}
			).insert(ignore_permissions=True)
		finally:
			frappe.flags.in_biometric_day_reconcile = False
		self.assertTrue(shown_up(self.employee, self.day))

	def test_attendance_check_skipped_only_for_our_grants(self):
		request = ReplacementLeaveRequest(
			{"doctype": "Compensatory Leave Request", "employee": self.employee, "work_from_date": self.day, "work_end_date": self.day}
		)
		request.flags.shown_up_on_holiday = True
		request.validate_attendance()  # no attendance at all, and no error
		request.flags.shown_up_on_holiday = False
		self.assertRaises(frappe.ValidationError, request.validate_attendance)

	def test_holiday_meal_thresholds(self):
		self.assertEqual([holiday_meals(h) for h in (0, 5.5, 6, 7.5, 8, 11)], [0, 0, 1, 1, 2, 2])
