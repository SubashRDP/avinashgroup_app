"""Worked on Special Holiday: a flat rate per Dashain / Tihar day worked, for everyone.

Pure rule tests: the Holiday List lookup is patched, so no Employee, Holiday
List or Salary Structure is needed.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from avinashgroup_app.payroll import attendance_allowance as aa

DASHAIN = "2026-10-21"
SATURDAY = "2026-10-24"


class TestSpecialHoliday(FrappeTestCase):
	def setUp(self):
		self.sc = frappe._dict(
			name="Special Holiday Allowance",
			custom_condition_type=aa.SPECIAL_HOLIDAY,
			custom_unit="Per Hour",  # left over on the form: must not turn it hourly
			custom_special_holiday_rate=200,
			custom_ot_eligible_only=1,  # likewise: everyone is paid
		)
		patches = [
			patch.object(aa, "_employee_holiday_list", return_value="HL"),
			patch.object(aa, "special_holiday_dates", return_value=frozenset({getdate(DASHAIN)})),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

	def qty(self, date, status="Present", on_holiday=1):
		row = frappe._dict(
			attendance_date=date, status=status, working_hours=9.5, custom_worked_on_holiday=on_holiday
		)
		return aa.evaluate_rule(row, self.sc, "EMP-1")

	def test_only_a_special_day_worked_counts(self):
		self.assertEqual(self.qty(DASHAIN), 1)
		self.assertEqual(self.qty(DASHAIN, status="Half Day"), 1)
		self.assertEqual(self.qty(DASHAIN, status="Absent"), 0)
		self.assertEqual(self.qty(SATURDAY), 0)  # a holiday, but not a special one
		self.assertEqual(self.qty(DASHAIN, on_holiday=0), 0)  # not a holiday on their list

	def test_everyone_at_the_components_rate(self):
		employee = frappe._dict(custom_ot_eligibility=0)
		self.assertTrue(aa._gets("EMP-1", self.sc, None, getdate(DASHAIN)))
		self.assertFalse(aa._skip_for_eligibility(employee, self.sc))
		self.assertEqual(aa._resolve_rate(None, self.sc, "EMP-1", getdate(DASHAIN), 30), 200)

		self.sc.custom_special_holiday_rate = 250  # HR changes it on the component
		self.assertEqual(aa._resolve_rate(None, self.sc, "EMP-1", getdate(DASHAIN), 30), 250)
