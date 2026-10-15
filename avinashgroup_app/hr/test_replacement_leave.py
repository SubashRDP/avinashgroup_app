"""Tests for hr/replacement_leave.py — holiday work earns a full replacement day
for turning up at all (user, 2026-10-15).

Covers:
- shown_up: one punch is enough; a hand-keyed attendance with an in-time too
- ReplacementLeaveRequest skips HRMS's Present / ½-day check only for grants
  flagged shown_up_on_holiday
- holiday_meals thresholds (payroll/attendance_allowance.py)
- a grant already taken as leave is kept when the sheet is cancelled or the
  punch goes; one not taken is cancelled and the row says so

Run:
    bench --site avinas1 run-tests --app avinashgroup_app \
        --module avinashgroup_app.hr.test_replacement_leave
"""

from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from avinashgroup_app.hr import replacement_leave
from avinashgroup_app.hr.replacement_leave import CANCELLED_NOTE, ReplacementLeaveRequest, shown_up
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

	def test_used_reads_the_balance_against_the_days_granted(self):
		request = _Request()
		with patch(BALANCE, return_value=0.5):
			self.assertTrue(replacement_leave.used(request))  # a full day granted, half left
		with patch(BALANCE, return_value=1):
			self.assertFalse(replacement_leave.used(request))

	def test_sheet_cancel_keeps_a_used_day_and_takes_back_the_rest(self):
		used_row, spare_row = _Row("CLR-USED"), _Row("CLR-SPARE")
		requests = {"CLR-USED": _Request("CLR-USED"), "CLR-SPARE": _Request("CLR-SPARE")}
		sheet = frappe._dict(employees=[used_row, spare_row])
		with patch.object(frappe, "get_doc", side_effect=lambda dt, name: requests[name]), patch.object(
			replacement_leave, "used", side_effect=lambda r: r.name == "CLR-USED"
		), patch.object(frappe, "msgprint") as warned:
			replacement_leave.on_sheet_cancel(sheet)

		self.assertFalse(requests["CLR-USED"].cancelled)
		self.assertEqual(used_row.compensatory_leave_request, "CLR-USED")
		self.assertIn("already used", used_row.settlement_note)
		warned.assert_called_once()

		self.assertTrue(requests["CLR-SPARE"].cancelled)
		self.assertIsNone(spare_row.compensatory_leave_request)
		self.assertEqual(spare_row.settlement_note, CANCELLED_NOTE)

	def test_a_used_day_stays_when_its_punch_goes(self):
		row = _Row("CLR-USED")
		sheet = frappe._dict(work_date=self.day)
		with patch.object(replacement_leave, "shown_up", return_value=False), patch.object(
			frappe, "get_doc", return_value=_Request("CLR-USED")
		), patch.object(replacement_leave, "used", return_value=True):
			line = replacement_leave._resync_row(sheet, row)
		self.assertTrue(line.startswith("⚠"))
		self.assertEqual(row.compensatory_leave_request, "CLR-USED")
		self.assertIn("already used", row.settlement_note)


BALANCE = "hrms.hr.doctype.leave_application.leave_application.get_leave_balance_on"


class _Request(frappe._dict):
	"""A submitted Compensatory Leave Request for one day."""

	def __init__(self, name="CLR-TEST"):
		super().__init__(
			name=name, docstatus=1, half_day=0, employee="EMP", leave_type="Replacement Leave",
			work_from_date="2026-08-28", work_end_date="2026-08-28", cancelled=False, flags=frappe._dict(),
		)

	def cancel(self):
		self.cancelled = True


class _Row(frappe._dict):
	"""An Overtime Sheet row that records what db_set wrote."""

	def __init__(self, request):
		super().__init__(name="row-" + request, employee="EMP", employee_name="Test", compensatory_leave_request=request)

	def db_set(self, field, value, update_modified=True):
		self[field] = value
