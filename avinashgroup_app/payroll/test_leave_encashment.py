"""Leave encashment (payroll/leave_encashment.py): year-end balance, rate, cap, re-run, slip.

Run against avinas1's own data (an NGI employee's salary assignment); the
allocations are made here and everything is rolled back. avinas1 has no leave
allocations of its own yet.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, getdate, now_datetime

from avinashgroup_app.payroll.leave_encashment import (
	YEAR_END,
	encash_month,
	per_day_rate,
)

COMPANY = "Nepal Gas Udhyog Pvt. Ltd."
YEAR_START, YEAR_END_DATE = "2026-07-17", "2027-07-16"  # FY 83/84


def _bs_month(ad_date):
	from rdp_common_app.utils.bs_boundaries import get_bs_month_end, get_bs_month_start

	ad_date = getdate(ad_date)
	return getdate(get_bs_month_start(ad_date)), getdate(get_bs_month_end(ad_date))


def _set_leave_type(name, **values):
	frappe.db.set_value("Leave Type", name, values)
	frappe.clear_document_cache("Leave Type", name)


class TestYearEndEncashment(FrappeTestCase):
	def setUp(self):
		row = frappe.db.sql(
			"""select a.employee, a.base from `tabSalary Structure Assignment` a
			join tabEmployee e on e.name = a.employee
			where a.docstatus = 1 and e.status = 'Active' and e.company = %s and a.base > 0
			  and a.from_date <= %s order by a.base limit 1""",
			(COMPANY, YEAR_START),
		)
		if not row:
			self.skipTest("no NGI employee with an assignment from the year's start")
		self.employee, self.basic = row[0][0], flt(row[0][1])
		frappe.db.set_value("Employee", self.employee, "relieving_date", None)
		self.ashadh = _bs_month(YEAR_END_DATE)
		for leave_type in ("Casual Leave", "Sick Leave"):
			_set_leave_type(leave_type, allow_encashment=1, max_encashable_leaves=0, non_encashable_leaves=0,
				custom_encash_at_year_end=1, custom_encash_at_separation=1, custom_encashment_days_per_month=0,
				earning_component="Leave Encashment")
		self.leave_period = frappe.db.get_value(
			"Leave Period", {"company": COMPANY, "from_date": YEAR_START, "to_date": YEAR_END_DATE}
		) or frappe.get_doc(
			{"doctype": "Leave Period", "company": COMPANY, "from_date": YEAR_START, "to_date": YEAR_END_DATE, "is_active": 1}
		).insert(ignore_permissions=True).name
		self.casual = self._allocate("Casual Leave", 21)
		self.sick = self._allocate("Sick Leave", 12)

	def tearDown(self):
		# Each case makes its own allocations for the same year; keep them apart.
		frappe.db.rollback()
		frappe.clear_document_cache("Leave Type", "Casual Leave")
		frappe.clear_document_cache("Leave Type", "Sick Leave")

	def _allocate(self, leave_type, days):
		doc = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee,
				"leave_type": leave_type,
				"from_date": YEAR_START,
				"to_date": YEAR_END_DATE,
				"new_leaves_allocated": days,
				# the naming series takes its fiscal year from this (custom_code/Override/naming_series.py)
				"custom_created_on": now_datetime(),
			}
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc.name

	def _run(self):
		return encash_month(COMPANY, "NPR", [self.employee], *self.ashadh)

	def test_remaining_balance_encashed_at_basic_per_day(self):
		result = self._run()
		casual = [c for c in result["created"] if c["leave_type"] == "Casual Leave"]
		self.assertEqual(len(casual), 1)
		self.assertEqual(flt(casual[0]["days"]), 21)
		basic, divisor, rate = per_day_rate(self.employee, "Casual Leave", YEAR_END_DATE)
		self.assertEqual(basic, self.basic)
		self.assertIn(divisor, (29, 30, 31, 32))  # Ashadh's actual length
		self.assertAlmostEqual(casual[0]["amount"], 21 * self.basic / divisor, delta=0.01)
		doc = frappe.get_doc("Leave Encashment", casual[0]["name"])
		self.assertEqual(doc.custom_occasion, YEAR_END)
		self.assertEqual(getdate(doc.encashment_date), getdate(YEAR_END_DATE))

	def test_fixed_divisor(self):
		_set_leave_type("Casual Leave", custom_encashment_days_per_month=30)
		casual = [c for c in self._run()["created"] if c["leave_type"] == "Casual Leave"][0]
		self.assertAlmostEqual(casual["amount"], 21 * self.basic / 30, delta=0.01)

	def test_non_encashable_type_is_ignored(self):
		_set_leave_type("Sick Leave", allow_encashment=0)
		types = {c["leave_type"] for c in self._run()["created"]}
		self.assertEqual(types, {"Casual Leave"})

	def test_days_cap(self):
		_set_leave_type("Casual Leave", max_encashable_leaves=10)
		casual = [c for c in self._run()["created"] if c["leave_type"] == "Casual Leave"][0]
		self.assertEqual(flt(casual["days"]), 10)

	def test_rerun_does_not_double(self):
		first = self._run()
		second = self._run()
		self.assertEqual(len(first["created"]), len(second["created"]))
		self.assertEqual(
			frappe.db.count("Leave Encashment", {"employee": self.employee, "docstatus": 0}), len(second["created"])
		)
		for c in second["created"]:
			frappe.get_doc("Leave Encashment", c["name"]).submit()
		third = self._run()
		self.assertEqual(third["created"], [])
		self.assertTrue(all(x["reason"] == "already encashed" for x in third["left_out"]))
		# and by hand, a second encashment of the same allocation is refused
		dup = frappe.get_doc(
			{"doctype": "Leave Encashment", "employee": self.employee, "leave_type": "Casual Leave",
			 "encashment_date": YEAR_END_DATE, "company": COMPANY, "currency": "NPR", "leave_period": self.leave_period}
		)
		self.assertRaises(frappe.ValidationError, dup.insert)

	def test_mid_year_date_is_refused(self):
		doc = frappe.get_doc(
			{"doctype": "Leave Encashment", "employee": self.employee, "leave_type": "Casual Leave",
			 "encashment_date": "2027-01-15", "company": COMPANY, "currency": "NPR", "leave_period": self.leave_period}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_separation_off_is_refused(self):
		frappe.db.set_value("Employee", self.employee, "relieving_date", "2027-01-15")
		_set_leave_type("Casual Leave", custom_encash_at_separation=0)
		doc = frappe.get_doc(
			{"doctype": "Leave Encashment", "employee": self.employee, "leave_type": "Casual Leave",
			 "encashment_date": "2027-01-15", "company": COMPANY, "currency": "NPR", "leave_period": self.leave_period}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)
		_set_leave_type("Casual Leave", custom_encash_at_separation=1)
		doc.insert()
		self.assertEqual(doc.custom_occasion, "Separation")

	def test_amount_reaches_the_ashadh_slip(self):
		casual = [c for c in self._run()["created"] if c["leave_type"] == "Casual Leave"][0]
		enc = frappe.get_doc("Leave Encashment", casual["name"])
		enc.submit()
		enc.reload()
		self.assertTrue(enc.additional_salary)
		additional = frappe.get_doc("Additional Salary", enc.additional_salary)
		self.assertEqual(additional.deduct_full_tax_on_selected_payroll_date, 1)
		self.assertEqual(getdate(additional.payroll_date), getdate(YEAR_END_DATE))

		structure = frappe.db.get_value(
			"Salary Structure Assignment", {"employee": self.employee, "docstatus": 1}, "salary_structure"
		)
		slip = frappe.new_doc("Salary Slip")
		slip.update(
			{
				"employee": self.employee,
				"posting_date": YEAR_END_DATE,
				"start_date": self.ashadh[0],
				"salary_structure": structure,
				"payroll_frequency": "Monthly",
			}
		)
		slip.run_method("validate")
		rows = [r for r in slip.earnings if r.salary_component == "Leave Encashment"]
		self.assertEqual(len(rows), 1)
		self.assertAlmostEqual(flt(rows[0].amount), flt(enc.encashment_amount), delta=0.01)

		# cancelling the encashment takes the payment back
		enc.cancel()
		self.assertEqual(frappe.db.get_value("Additional Salary", additional.name, "docstatus"), 2)
