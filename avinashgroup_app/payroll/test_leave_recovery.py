"""Leave taken ahead of the credit, capped at the year, recovered from a leaver.

hr/leave_ceiling.validate_application_within_year and
payroll/leave_encashment.recover_month. A fresh NGI employee on the company's
Leave Policy, so every case starts from the policy's own credit; everything is
rolled back.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, date_diff, flt, now_datetime

from avinashgroup_app.hr.leave_from_report import give_leave
from avinashgroup_app.payroll.leave_encashment import (
	RECOVERY_COMPONENT,
	encash_month,
	per_day_rate,
	recover_month,
	settlement_balance,
)

COMPANY = "Nepal Gas Udhyog Pvt. Ltd."
YEAR_START, YEAR_END = "2026-07-17", "2027-07-16"  # FY 83/84
ASHWIN = ("2026-09-17", "2026-10-16")


def _days(start, end):
	return json.dumps([str(add_days(start, i)) for i in range(date_diff(end, start) + 1)])


class TestLeaveRecovery(FrappeTestCase):
	def setUp(self):
		policy = frappe.db.get_value("Leave Policy", {"docstatus": 1}, "name")
		period = frappe.db.get_value("Leave Period", {"company": COMPANY, "from_date": YEAR_START})
		structure = frappe.db.get_value(
			"Salary Structure Assignment", {"company": COMPANY, "docstatus": 1},
			["salary_structure", "income_tax_slab", "payroll_payable_account"], as_dict=True,
		)
		if not (policy and period and structure):
			self.skipTest("needs an NGI Leave Policy, Leave Period and salary structure")
		from avinashgroup_app.patches import setup_leave_recovery

		setup_leave_recovery.execute()
		frappe.clear_document_cache("Leave Type", "Casual Leave")
		frappe.flags.audit_user = "Administrator"
		self.employee = frappe.get_doc(
			{
				"doctype": "Employee", "first_name": "Leave", "last_name": "Recovery", "gender": "Male",
				"date_of_birth": "1990-01-01", "date_of_joining": YEAR_START, "company": COMPANY, "status": "Active",
				"holiday_list": frappe.db.get_value("Company", COMPANY, "default_holiday_list")
				or frappe.db.get_value("Holiday List", {"from_date": ("<=", YEAR_START), "to_date": (">=", YEAR_END)}),
				"custom_created_on": now_datetime(),
			}
		).insert(ignore_permissions=True).name
		assignment = frappe.get_doc(
			{
				"doctype": "Leave Policy Assignment", "employee": self.employee, "leave_policy": policy,
				"assignment_based_on": "Leave Period", "leave_period": period,
				"effective_from": YEAR_START, "effective_to": YEAR_END, "custom_created_on": now_datetime(),
			}
		).insert(ignore_permissions=True)
		assignment.submit()
		ssa = frappe.get_doc(
			{
				"doctype": "Salary Structure Assignment", "employee": self.employee, **structure,
				"company": COMPANY, "from_date": YEAR_START, "base": 20000, "currency": "NPR",
				"custom_created_on": now_datetime(),
			}
		).insert(ignore_permissions=True)
		ssa.submit()

	def tearDown(self):
		frappe.db.rollback()
		frappe.clear_document_cache("Leave Type", "Casual Leave")

	def _give(self, leave_type, start, end):
		return give_leave(self.employee, leave_type, _days(start, end), "test")

	def _leave(self, relieving):
		frappe.db.set_value("Employee", self.employee, "relieving_date", relieving)

	def test_leave_ahead_of_the_credit_is_allowed(self):
		self._give("Casual Leave", "2026-07-17", "2026-08-06")  # all 21 of the year in Shrawan
		self.assertEqual(
			frappe.db.count("Leave Application", {"employee": self.employee, "leave_type": "Casual Leave", "docstatus": 1}), 1
		)

	def test_leave_past_the_year_is_refused(self):
		self._give("Casual Leave", "2026-07-17", "2026-08-06")
		with self.assertRaises(frappe.ValidationError):
			self._give("Casual Leave", "2026-09-01", "2026-09-01")

	def test_leaver_with_excess_is_recovered(self):
		self._give("Casual Leave", "2026-07-17", "2026-08-06")
		self._leave(ASHWIN[1])
		allocation = frappe.db.get_value("Leave Allocation", {"employee": self.employee, "leave_type": "Casual Leave", "docstatus": 1})
		short = -settlement_balance(self.employee, "Casual Leave", allocation, ASHWIN[1])
		self.assertGreater(short, 0)
		made = [m for m in recover_month(COMPANY, [self.employee], *ASHWIN)["made"] if m["leave_type"] == "Casual Leave"]
		self.assertEqual(len(made), 1)
		rate = per_day_rate(self.employee, "Casual Leave", ASHWIN[1])[2]
		self.assertAlmostEqual(made[0]["amount"], short * rate, delta=0.01)
		doc = frappe.get_doc("Additional Salary", made[0]["name"])
		self.assertEqual((doc.salary_component, doc.type, doc.docstatus), (RECOVERY_COMPONENT, "Deduction", 1))

	def test_leaver_with_leave_left_is_encashed_not_recovered(self):
		self._leave(ASHWIN[1])
		self.assertFalse(recover_month(COMPANY, [self.employee], *ASHWIN)["made"])
		self.assertTrue(encash_month(COMPANY, "NPR", [self.employee], *ASHWIN)["created"])

	def test_rerun_replaces_not_doubles(self):
		self._give("Casual Leave", "2026-07-17", "2026-08-06")
		self._leave(ASHWIN[1])
		first = recover_month(COMPANY, [self.employee], *ASHWIN)
		second = recover_month(COMPANY, [self.employee], *ASHWIN)
		self.assertEqual(first["total"], second["total"])
		self.assertEqual(
			frappe.db.count(
				"Additional Salary", {"employee": self.employee, "salary_component": RECOVERY_COMPONENT, "docstatus": 1}
			),
			len(second["made"]),
		)
