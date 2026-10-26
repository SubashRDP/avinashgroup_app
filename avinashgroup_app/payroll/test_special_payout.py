"""Dashain and leave encashment on their own payout slip (payroll/special_payout.py).

A fresh NGI employee on a 2,00,000 basic, so the allowance lands in the 20 %
band and the tax is visible; the Payroll Entries are made and submitted the way
HR does it, journal included. Everything is rolled back.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, now_datetime

from hrms.payroll.doctype.salary_slip.salary_slip import calculate_tax_by_tax_slab

from avinashgroup_app.payroll.special_payout import DASHAIN, ENCASHMENT, PAYOUT_FIELD

COMPANY = "Nepal Gas Udhyog Pvt. Ltd."
YEAR_START, YEAR_END = "2026-07-17", "2027-07-16"  # FY 83/84
ASHWIN = ("2026-09-17", "2026-10-16")  # the month Dashain is paid in
KARTIK = ("2026-10-17", "2026-11-15")
CUTOFF = "2026-10-11"  # Ghatasthapana 2083
BASIC = 200000
DEPARTMENT = "Administration - NGI"  # has a Payroll Section, so the journal can post


def _tax(slip):
	return sum(flt(r.amount) for r in slip.deductions if r.variable_based_on_taxable_salary)


class PayoutCase(FrappeTestCase):
	def setUp(self):
		self.structure = frappe.db.get_value(
			"Salary Structure Assignment", {"company": COMPANY, "docstatus": 1},
			["salary_structure", "income_tax_slab", "payroll_payable_account"], as_dict=True,
		)
		self.component = frappe.db.get_value("Salary Component", {"custom_is_festival_allowance": 1, "disabled": 0})
		if not (self.structure and self.component and frappe.db.exists("Department", DEPARTMENT)):
			self.skipTest("needs an NGI salary structure, a festival component and the NGI Administration department")
		if not frappe.get_meta("Salary Slip").has_field(PAYOUT_FIELD):
			self.skipTest("patch setup_special_payout not run")
		frappe.db.set_value("Salary Component", self.component, "custom_festival_pay_month", "06 - Ashwin")
		frappe.flags.audit_user = "Administrator"
		self.employee = frappe.get_doc(
			{
				"doctype": "Employee", "first_name": "Payout", "last_name": "Test", "gender": "Male",
				"date_of_birth": "1990-01-01", "date_of_joining": "2024-01-01", "company": COMPANY, "status": "Active",
				"department": DEPARTMENT, "holiday_list": frappe.db.get_value("Company", COMPANY, "default_holiday_list"),
				"custom_created_on": now_datetime(),
			}
		).insert(ignore_permissions=True).name
		ssa = frappe.get_doc(
			{
				"doctype": "Salary Structure Assignment", "employee": self.employee, **self.structure,
				"company": COMPANY, "from_date": YEAR_START, "base": BASIC, "currency": "NPR",
				"custom_created_on": now_datetime(),
			}
		).insert(ignore_permissions=True)
		ssa.submit()

	def tearDown(self):
		frappe.db.rollback()

	def entry(self, bs_month="06 - Ashwin", payout=None, **values):
		pe = frappe.new_doc("Payroll Entry")
		pe.update(
			{
				"company": COMPANY, "custom_fiscal_year": "83/84", "custom_bs_month": bs_month, PAYOUT_FIELD: payout,
				"custom_festival_component": self.component if payout == DASHAIN else None,
				"custom_festival_cutoff": CUTOFF, **values,
			}
		)
		pe.append("employees", {"employee": self.employee})
		pe.insert(ignore_permissions=True)
		return pe

	def run_entry(self, pe):
		"""Submit the entry (makes the slips), then submit the slips (posts the journal)."""
		pe.submit()
		pe.submit_salary_slips()
		pe.reload()
		self.assertFalse(pe.error_message, pe.error_message)
		return frappe.get_doc("Salary Slip", frappe.get_all("Salary Slip", {"payroll_entry": pe.name}, pluck="name")[0])

	def slip_in_memory(self, start, end):
		slip = frappe.new_doc("Salary Slip")
		slip.update(
			{
				"employee": self.employee, "posting_date": end, "start_date": start, "end_date": end,
				"salary_structure": self.structure.salary_structure, "payroll_frequency": "Monthly",
			}
		)
		slip.run_method("validate")
		return slip

	def marginal_tax(self, slip, amount):
		"""What the slab charges on the year with `amount` added, less the year without it."""
		eval_locals, __ = slip.get_data_for_eval()
		year = flt(slip.total_taxable_earnings)
		with_it = calculate_tax_by_tax_slab(year + amount, slip.tax_slab, slip.whitelisted_globals, eval_locals)[0]
		without = calculate_tax_by_tax_slab(year, slip.tax_slab, slip.whitelisted_globals, eval_locals)[0]
		return flt(with_it) - flt(without)


class TestDashainPayout(PayoutCase):
	def test_payout_slip_pays_only_dashain_and_its_tax(self):
		payout = self.run_entry(self.entry(payout=DASHAIN))
		self.assertEqual(payout.get(PAYOUT_FIELD), DASHAIN)
		self.assertEqual(payout.docstatus, 1)
		self.assertEqual([r.salary_component for r in payout.earnings], [self.component])
		self.assertAlmostEqual(flt(payout.earnings[0].amount), BASIC, 2)  # full year of service
		self.assertTrue(all(r.variable_based_on_taxable_salary for r in payout.deductions))
		additional = frappe.get_doc("Additional Salary", payout.earnings[0].additional_salary)
		self.assertEqual((additional.get(PAYOUT_FIELD), additional.disabled), (DASHAIN, 1))

		# Its tax is the whole tax the allowance adds to the month's projected year.
		regular = self.slip_in_memory(*ASHWIN)
		self.assertNotIn(self.component, [r.salary_component for r in regular.earnings])
		self.assertGreater(_tax(payout), 0)
		self.assertAlmostEqual(_tax(payout), self.marginal_tax(regular, BASIC), delta=0.01)
		self.assertAlmostEqual(flt(payout.net_pay), BASIC - _tax(payout), 2)

		# Its own journal, the allowance on its own expense account.
		self.assertTrue(payout.journal_entry)
		debits = frappe.get_all(
			"Journal Entry Account", {"parent": payout.journal_entry, "debit_in_account_currency": (">", 0)},
			pluck="account",
		)
		self.assertTrue(debits)
		self.assertTrue(all("Dashain" in a for a in debits), debits)

		# A payout slip does not lock the month's attendance.
		from avinashgroup_app.biometric.attendance_override import _paid

		self.assertFalse(_paid(self.employee, ASHWIN[0]))

	def test_salary_and_payout_side_by_side_tax_the_year_once(self):
		payout = self.run_entry(self.entry(payout=DASHAIN))
		regular = self.run_entry(self.entry())
		self.assertFalse(regular.get(PAYOUT_FIELD))
		self.assertNotIn(self.component, [r.salary_component for r in regular.earnings])
		self.assertTrue(frappe.db.exists("Salary Slip", {"employee": self.employee, "docstatus": 1, PAYOUT_FIELD: DASHAIN}))

		# Next month counts both slips: their earnings and the tax both deducted.
		kartik = self.slip_in_memory(*KARTIK)
		regular_taxable = sum(flt(r.amount) for r in regular.earnings if r.is_tax_applicable) - sum(
			flt(r.amount) for r in regular.deductions if r.exempted_from_income_tax
		)
		self.assertAlmostEqual(flt(kartik.previous_taxable_earnings), regular_taxable + BASIC, delta=0.01)
		self.assertAlmostEqual(flt(kartik.previous_total_paid_taxes), _tax(regular) + _tax(payout), delta=0.01)
		# ... so the rest of the year's tax is spread as if the allowance had been
		# taxed in full on the Ashwin salary slip: Kartik is charged what Ashwin was.
		self.assertAlmostEqual(_tax(kartik), _tax(regular), delta=1)

		# The salary sheet shows one kind at a time.
		from avinashgroup_app.avinash_group_app.report.avinas_salary_statement.avinas_salary_statement import execute

		filters = {"company": COMPANY, "fiscal_year": "83/84", "bs_month": "06 - Ashwin", "docstatus": "1 - Submitted"}
		for payout_type, slip in (("Salary", regular), (DASHAIN, payout)):
			rows = execute({**filters, "payout_type": payout_type})[1]
			mine = [r for r in rows if r.get("employee") == self.employee]
			self.assertEqual([r.slip for r in mine], [slip.name], payout_type)

	def test_order_does_not_change_the_payout_tax(self):
		regular = self.run_entry(self.entry())
		expected = self.marginal_tax(self.slip_in_memory(*ASHWIN), BASIC)
		# Get Employees still finds the person already paid this month's salary.
		# (HRMS's own Get Employees drops anyone with any submitted slip for the month.)
		pe = frappe.new_doc("Payroll Entry")
		pe.update({"company": COMPANY, "custom_fiscal_year": "83/84", "custom_bs_month": "06 - Ashwin",
			PAYOUT_FIELD: DASHAIN, "custom_festival_component": self.component, "custom_festival_cutoff": CUTOFF})
		pe.insert(ignore_permissions=True)  # an empty list is filled on save
		self.assertIn(self.employee, [e.employee for e in pe.employees])
		frappe.delete_doc("Payroll Entry", pe.name, ignore_permissions=True)
		payout = self.run_entry(self.entry(payout=DASHAIN))
		self.assertAlmostEqual(_tax(payout), expected, delta=0.01)
		self.assertFalse(regular.get(PAYOUT_FIELD))

	def test_second_slip_of_the_same_kind_is_refused(self):
		self.run_entry(self.entry())
		self.assertRaises(frappe.ValidationError, self.entry().submit)
		self.run_entry(self.entry(payout=DASHAIN))
		self.assertRaises(frappe.ValidationError, self.entry(payout=DASHAIN).submit)

	def test_salary_entry_no_longer_pays_dashain(self):
		pe = self.entry(custom_pay_dashain=1, custom_festival_component=self.component)
		self.assertEqual(pe.custom_pay_dashain, 0)
		slip = self.run_entry(pe)
		self.assertNotIn(self.component, [r.salary_component for r in slip.earnings])
		self.assertFalse(frappe.db.exists("Payroll Adjustment", {"payroll_entry": pe.name}))

	def test_nobody_due_is_refused(self):
		pe = self.entry(payout=ENCASHMENT)  # no leave allocation, nothing to encash
		self.assertRaises(frappe.ValidationError, pe.submit)


class TestEncashmentPayout(PayoutCase):
	def setUp(self):
		super().setUp()
		policy = frappe.db.get_value("Leave Policy", {"docstatus": 1}, "name")
		period = frappe.db.get_value("Leave Period", {"company": COMPANY, "from_date": YEAR_START})
		if not (policy and period):
			self.skipTest("needs a Leave Policy and the NGI 83/84 Leave Period")
		for leave_type in ("Casual Leave", "Sick Leave"):
			frappe.db.set_value("Leave Type", leave_type, {
				"allow_encashment": 1, "custom_encash_at_separation": 1, "custom_encash_at_year_end": 1,
				"earning_component": "Leave Encashment", "max_encashable_leaves": 0, "non_encashable_leaves": 0,
			})
			frappe.clear_document_cache("Leave Type", leave_type)
		frappe.db.set_value("Employee", self.employee, "date_of_joining", YEAR_START)
		assignment = frappe.get_doc(
			{
				"doctype": "Leave Policy Assignment", "employee": self.employee, "leave_policy": policy,
				"assignment_based_on": "Leave Period", "leave_period": period,
				"effective_from": YEAR_START, "effective_to": YEAR_END, "custom_created_on": now_datetime(),
			}
		).insert(ignore_permissions=True)
		assignment.submit()
		frappe.db.set_value("Employee", self.employee, "relieving_date", ASHWIN[1])

	def tearDown(self):
		super().tearDown()
		frappe.clear_document_cache("Leave Type", "Casual Leave")
		frappe.clear_document_cache("Leave Type", "Sick Leave")

	def test_leaver_encashment_on_its_own_slip(self):
		payout = self.run_entry(self.entry(payout=ENCASHMENT))
		self.assertEqual({r.salary_component for r in payout.earnings}, {"Leave Encashment"})
		encashments = frappe.get_all(
			"Leave Encashment", {"employee": self.employee, "docstatus": 1}, ["encashment_amount", "status", "additional_salary"]
		)
		self.assertTrue(encashments)
		self.assertAlmostEqual(flt(payout.gross_pay), sum(flt(e.encashment_amount) for e in encashments), delta=0.01)
		self.assertEqual({e.status for e in encashments}, {"Paid"})
		self.assertEqual(
			{frappe.db.get_value("Additional Salary", e.additional_salary, PAYOUT_FIELD) for e in encashments}, {ENCASHMENT}
		)

		# The final salary slip pays the month without the encashment.
		final = self.run_entry(self.entry(custom_pay_leave_encashment=1))
		self.assertNotIn("Leave Encashment", [r.salary_component for r in final.earnings])
		self.assertFalse(frappe.get_all("Leave Encashment", {"employee": self.employee, "docstatus": ("<", 2), "status": "Unpaid"}))
