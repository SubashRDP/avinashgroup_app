"""Tests for hr/leave_from_report.py — leave given from Monthly Attendance BS.

Covers:
- chosen days are grouped into runs of consecutive dates, one application each
- giving Leave Without Pay files approved, submitted Leave Applications, HRMS
  marks the days On Leave, and each day is in the Attendance Correction Log
- a reason is required; a day already marked Present is refused by HRMS

Run:
    bench --site avinas1 run-tests --app avinashgroup_app \
        --module avinashgroup_app.hr.test_leave_from_report
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from avinashgroup_app.hr.leave_from_report import _runs, give_leave


class TestLeaveFromReport(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# HRMS refuses leave for anyone with no holiday list, own or the company's.
		company = frappe.get_all(
			"Company", filters={"default_holiday_list": ("is", "set")}, pluck="name", order_by="creation", limit=1
		)[0]
		emp = frappe.new_doc("Employee")
		emp.first_name = "Leave From Report Test"
		emp.gender = "Male"
		emp.date_of_birth = "1990-01-01"
		emp.date_of_joining = "2024-01-01"
		emp.company = company
		emp.status = "Active"
		emp.holiday_list = None
		emp.insert(ignore_permissions=True)
		cls.employee = emp.name
		cls.company = company
		cls.lwp = frappe.get_all("Leave Type", filters={"is_lwp": 1}, pluck="name", limit=1)[0]

	def _days(self, *offsets):
		return [str(getdate(add_days(today(), o))) for o in offsets]

	def test_runs(self):
		days = [getdate(d) for d in ("2026-10-01", "2026-10-02", "2026-10-06", "2026-10-07", "2026-10-09")]
		self.assertEqual(
			[(str(a), str(b)) for a, b in _runs(days)],
			[("2026-10-01", "2026-10-02"), ("2026-10-06", "2026-10-07"), ("2026-10-09", "2026-10-09")],
		)

	def _working_runs(self):
		"""Two consecutive working days and a third apart from them: HRMS marks
		no leave attendance on a holiday for a type that excludes holidays, so
		the days must miss the company's holiday list."""
		holidays = {
			getdate(d)
			for d in frappe.get_all(
				"Holiday", filters={"parent": frappe.db.get_value("Company", self.company, "default_holiday_list")},
				pluck="holiday_date",
			)
		}
		working = [getdate(add_days(today(), o)) for o in range(-40, -9) if getdate(add_days(today(), o)) not in holidays]
		for first, second in zip(working, working[1:]):
			if (second - first).days == 1:
				third = next(d for d in working if (d - second).days >= 2)
				return [str(first), str(second), str(third)]
		self.skipTest("no two consecutive working days in the last 40")

	def test_lwp_given_for_two_runs(self):
		days = self._working_runs()
		result = give_leave(self.employee, self.lwp, json.dumps(days), "Phoned in sick")
		self.assertEqual(len(result["made"]), 2)
		for made in result["made"]:
			la = frappe.get_doc("Leave Application", made["leave_application"])
			self.assertEqual((la.docstatus, la.status), (1, "Approved"))
		for day in days:
			status = frappe.db.get_value(
				"Attendance", {"employee": self.employee, "attendance_date": day, "docstatus": 1}, "status"
			)
			self.assertEqual(status, "On Leave")
			self.assertTrue(
				frappe.db.exists(
					"Attendance Correction Log",
					{"employee": self.employee, "attendance_date": day, "correction_type": "Leave Given"},
				)
			)

	def test_reason_required(self):
		self.assertRaises(frappe.ValidationError, give_leave, self.employee, self.lwp, json.dumps(self._days(-30)), " ")

	def test_present_day_refused(self):
		day = self._days(-25)[0]
		frappe.get_doc(
			{"doctype": "Attendance", "employee": self.employee, "attendance_date": day, "status": "Present"}
		).submit()
		self.assertRaises(frappe.ValidationError, give_leave, self.employee, self.lwp, json.dumps([day]), "x")
