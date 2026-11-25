"""Days per Month for Pay = 30: one day costs monthly ÷ 30 in every BS month.

Absent, half day and overtime must all be priced off that one day's value
(user, 2026-11-25). Pure tests: the settings, month length and assignment are
patched, so nothing is written.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rdp_common_app.nepal_hrms_common.doctype.nepal_hrms_settings import nepal_hrms_settings
from rdp_common_app.nepal_hrms_common.payroll import salary_slip_bs

from avinashgroup_app.payroll import attendance_allowance as aa

BASIC = 30000
DAY = BASIC / 30  # 1,000


class TestPayOn30DayMonth(FrappeTestCase):
	def setUp(self):
		for target, value in (
			(salary_slip_bs, "get_pay_days_per_month"),
			(nepal_hrms_settings, "get_pay_days_per_month"),
			(aa, "get_pay_days_per_month"),
		):
			p = patch.object(target, value, return_value=30)
			p.start()
			self.addCleanup(p.stop)
		p = patch.object(salary_slip_bs, "_is_bs_payroll_enabled", return_value=True)
		p.start()
		self.addCleanup(p.stop)

	def basic_paid(self, month_days, unpaid):
		slip = frappe.new_doc("Salary Slip")
		slip.company = "x"
		slip.start_date = "2026-07-17"
		slip.salary_structure = "x"
		slip._salary_structure_doc = frappe._dict(salary_component=None)
		slip.total_working_days = month_days
		slip.payment_days = month_days - unpaid
		row = frappe.new_doc("Salary Detail")
		row.update(
			{"salary_component": "Basic", "amount": BASIC, "default_amount": BASIC, "depends_on_payment_days": 1}
		)
		with patch.object(salary_slip_bs.BSSalarySlip, "get_total_working_days_in_bs_month", return_value=month_days):
			amount = slip.get_amount_based_on_payment_days(row)[0]
		# The slip keeps the true days for reports.
		self.assertEqual((slip.total_working_days, slip.payment_days), (month_days, month_days - unpaid))
		return amount

	def test_same_cut_in_every_month(self):
		for month_days in (29, 30, 31, 32):
			with self.subTest(month_days=month_days):
				self.assertEqual(self.basic_paid(month_days, 0), BASIC)  # full month, even 32 days
				self.assertEqual(self.basic_paid(month_days, 1), BASIC - DAY)  # absent
				self.assertEqual(self.basic_paid(month_days, 0.5), BASIC - DAY / 2)  # half day
				self.assertEqual(self.basic_paid(month_days, 31), 0)  # never below nothing

	def test_overtime_hour_is_off_the_same_day(self):
		with patch.object(aa, "_assignment", return_value=frappe._dict(base=BASIC)):
			for month_days in (29, 32):
				self.assertEqual(aa.overtime_rate("EMP-1", "2026-07-17", month_days), DAY / 8 * 1.5)
			# A component's own Rate: Days per Month still wins.
			sc = frappe._dict(custom_rate_days_per_month=26)
			self.assertEqual(aa._hourly_basic("EMP-1", "2026-07-17", sc, 32), BASIC / 26 / 8)

	def test_arrears_share_matches_the_slip(self):
		self.assertEqual(nepal_hrms_settings.paid_share(32, 32), 1)
		self.assertEqual(nepal_hrms_settings.paid_share(32, 27), 25 / 30)
		self.assertEqual(nepal_hrms_settings.paid_share(29, 24), 25 / 30)
