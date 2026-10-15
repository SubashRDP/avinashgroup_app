"""Recoveries on a Payroll Entry: already-paid people, a leaver's advance, the cap.

payroll/attendance_allowance.create_additional_salaries (skips a submitted
month), payroll/advance_recovery.post_recoveries (a leaver repays the whole
balance), payroll/recovery_cap.cap_recoveries (no slip below zero), and
payroll/allowance._check_type_for_condition (overtime and late fines are never
tax-exempt). A fresh NGI employee on a real salary structure; everything is
rolled back.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, now_datetime

from avinashgroup_app.payroll.advance_recovery import COMPONENT as ADVANCE_COMPONENT
from avinashgroup_app.payroll.advance_recovery import post_recoveries
from avinashgroup_app.payroll.attendance_allowance import create_additional_salaries
from avinashgroup_app.payroll.recovery_cap import cap_slip

COMPANY = "Nepal Gas Udhyog Pvt. Ltd."
ASHWIN = ("2026-09-17", "2026-10-16")
FAKE_ENTRY = "TEST-PAYROLL-RECOVERY"


def _entry(*employees):
	return frappe._dict(
		name=FAKE_ENTRY, company=COMPANY, start_date=ASHWIN[0], end_date=ASHWIN[1],
		employees=[frappe._dict(employee=e) for e in employees],
	)


class TestPayrollRecoveries(FrappeTestCase):
	def setUp(self):
		structure = frappe.db.get_value(
			"Salary Structure Assignment", {"company": COMPANY, "docstatus": 1},
			["salary_structure", "income_tax_slab", "payroll_payable_account"], as_dict=True,
		)
		if not structure:
			self.skipTest("needs an NGI salary structure")
		from avinashgroup_app.patches import late_fine_and_overtime_not_tax_exempt, setup_salary_advance_component

		setup_salary_advance_component.execute()
		late_fine_and_overtime_not_tax_exempt.execute()
		frappe.flags.audit_user = "Administrator"
		self.employee = frappe.get_doc(
			{
				"doctype": "Employee", "first_name": "Payroll", "last_name": "Recovery", "gender": "Male",
				"date_of_birth": "1990-01-01", "date_of_joining": "2026-07-17", "company": COMPANY, "status": "Active",
				"holiday_list": frappe.db.get_value("Company", COMPANY, "default_holiday_list"),
				"custom_created_on": now_datetime(),
			}
		).insert(ignore_permissions=True).name
		ssa = frappe.get_doc(
			{
				"doctype": "Salary Structure Assignment", "employee": self.employee, **structure,
				"company": COMPANY, "from_date": "2026-07-17", "base": 20000, "currency": "NPR",
				"custom_created_on": now_datetime(),
			}
		).insert(ignore_permissions=True)
		ssa.submit()

	def tearDown(self):
		frappe.db.rollback()

	def _advance(self, amount, instalment):
		doc = frappe.get_doc(
			{
				"doctype": "Employee Advance", "employee": self.employee, "company": COMPANY,
				"posting_date": "2026-08-01", "advance_amount": amount, "purpose": "test",
				"exchange_rate": 1, "currency": "NPR", "repay_unclaimed_amount_from_salary": 1,
				"custom_monthly_instalment": instalment, "custom_created_on": now_datetime(),
				"advance_account": frappe.db.get_value("Account", {"company": COMPANY, "name": ("like", "148003%")}),
			}
		)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_validate = True
		doc.insert()
		frappe.db.set_value("Employee Advance", doc.name, {"docstatus": 1, "paid_amount": amount, "status": "Paid"})
		return doc.name

	def _leave_at_month_end(self):
		frappe.db.set_value("Employee", self.employee, "relieving_date", ASHWIN[1])

	def test_month_already_paid_is_left_alone(self):
		paid = frappe.db.get_value(
			"Salary Slip", {"docstatus": 1, "company": COMPANY, "start_date": ("<=", "2026-09-16"), "end_date": (">=", "2026-09-16")},
			"employee",
		)
		if not paid:
			self.skipTest("needs a submitted NGI slip for Bhadra")
		entry = frappe._dict(_entry(paid), start_date="2026-08-17", end_date="2026-09-16")
		result = create_additional_salaries(entry, commit=False)
		self.assertEqual(result["already_paid"], [paid])
		self.assertFalse(result["skipped"])
		self.assertFalse(result["created"])

	def test_leaver_repays_the_whole_advance(self):
		advance = self._advance(50000, 5000)
		self._leave_at_month_end()
		posted = post_recoveries(_entry(self.employee))
		self.assertEqual([(p["advance"], p["amount"]) for p in posted], [(advance, 50000)])

	def test_staying_employee_repays_one_instalment(self):
		advance = self._advance(50000, 5000)
		posted = post_recoveries(_entry(self.employee))
		self.assertEqual([(p["advance"], p["amount"]) for p in posted], [(advance, 5000)])

	def test_recovery_is_cut_to_what_the_slip_can_bear(self):
		advance = self._advance(90000, 5000)
		self._leave_at_month_end()
		post_recoveries(_entry(self.employee))
		slip = frappe.get_doc(
			{
				"doctype": "Salary Slip", "employee": self.employee, "company": COMPANY, "payroll_frequency": "Monthly",
				"posting_date": ASHWIN[1], "start_date": ASHWIN[0], "end_date": ASHWIN[1],
			}
		)
		slip.flags.ignore_permissions = True
		slip.insert()
		self.assertLess(flt(slip.net_pay), 0)

		shortfalls = cap_slip(slip)
		slip.reload()
		self.assertAlmostEqual(flt(slip.net_pay), 0, delta=0.01)
		self.assertEqual([s["component"] for s in shortfalls], [ADVANCE_COMPONENT])
		taken = flt(frappe.db.get_value(
			"Additional Salary", {"ref_docname": advance, "docstatus": 1}, "sum(amount)"
		))
		self.assertAlmostEqual(taken + shortfalls[0]["amount"], 90000, delta=0.01)
		# What was not taken is still owed on the advance.
		self.assertAlmostEqual(flt(frappe.db.get_value("Employee Advance", advance, "return_amount")), taken, delta=0.01)

	def test_late_fine_and_overtime_cannot_be_tax_exempt(self):
		for name in frappe.get_all(
			"Salary Component", filters={"custom_condition_type": ("in", ("Late Time", "Authorised Overtime"))}, pluck="name"
		):
			doc = frappe.get_doc("Salary Component", name)
			self.assertFalse(doc.exempted_from_income_tax, name)
			doc.exempted_from_income_tax = 1
			with self.assertRaises(frappe.ValidationError, msg=name):
				doc.save()

	def test_leave_recovery_gives_way_before_the_advance(self):
		from avinashgroup_app.payroll.leave_encashment import RECOVERY_COMPONENT, RECOVERY_SOURCE

		if not frappe.db.exists("Salary Component", RECOVERY_COMPONENT):
			self.skipTest("needs the Leave Recovery component (patch setup_leave_recovery)")
		self._advance(10000, 10000)
		post_recoveries(_entry(self.employee))
		leave = frappe.get_doc(
			{
				"doctype": "Additional Salary", "employee": self.employee, "company": COMPANY,
				"salary_component": RECOVERY_COMPONENT, "type": "Deduction", "amount": 60000,
				"payroll_date": ASHWIN[1], "overwrite_salary_structure_amount": 0, "custom_source": RECOVERY_SOURCE,
			}
		)
		leave.flags.ignore_permissions = True
		leave.insert()
		leave.submit()
		slip = frappe.get_doc(
			{
				"doctype": "Salary Slip", "employee": self.employee, "company": COMPANY, "payroll_frequency": "Monthly",
				"posting_date": ASHWIN[1], "start_date": ASHWIN[0], "end_date": ASHWIN[1],
			}
		)
		slip.flags.ignore_permissions = True
		slip.insert()
		over = -flt(slip.net_pay)
		self.assertGreater(over, 0)
		self.assertLess(over, 60000)  # the leave recovery alone covers it

		shortfalls = cap_slip(slip)
		self.assertEqual([s["component"] for s in shortfalls], [RECOVERY_COMPONENT])
		self.assertAlmostEqual(shortfalls[0]["amount"], over, delta=0.01)
		slip.reload()
		self.assertAlmostEqual(flt(slip.net_pay), 0, delta=0.01)
		self.assertTrue(any(d.salary_component == ADVANCE_COMPONENT and flt(d.amount) == 10000 for d in slip.deductions))
