"""The guards added after the October 2026 audit of avinas1.

  * the sheet import matches by name, the code only as a cross-check (NGN's
    codes drift one place from the ERP IDs);
  * a new Payroll Entry opens on the month after the last payroll;
  * Make Bank Entry refuses an unsaved or non-bank Payment Account;
  * a payroll month with no attendance is announced before slips are made;
  * the salary sheet names an account set for two sections;
  * overtime or replacement leave is read from the Employee's own ticks, and
    never both.

Run against avinas1's own data, as the other payroll suites do; a case whose
data is missing is skipped, never faked.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

NGI = "Nepal Gas Udhyog Pvt. Ltd."
NGN = "Nepal Gas Udhyog (Narayani) Pvt. Ltd."


class TestSheetMatching(FrappeTestCase):
	def test_code_is_taken_only_with_the_name(self):
		from avinashgroup_app.payroll.onboarding import EmployeeMatcher

		if frappe.db.get_value("Employee", "NGN-EMP-00045", "employee_name") != "Bal Krishna Neupane":
			self.skipTest("NGN employees not as on avinas1")
		matcher = EmployeeMatcher("NGN", NGN)
		# The sheet's NGN0045 is Parmeshwor Shah, who is NGN-EMP-00044.
		self.assertEqual(matcher.find({"code": "NGN0045", "name": "Parmeshwor Shah"}), "NGN-EMP-00044")
		# A code whose employee has the row's name is used as it is.
		self.assertEqual(matcher.find({"code": "NGN0003", "name": "Shiwa Narayan Mahato"}), "NGN-EMP-00003")
		# A name nobody has finds no one, whatever the code says.
		self.assertIsNone(matcher.find({"code": "NGN0003", "name": "Nobody Like This"}))


class TestDefaultMonth(FrappeTestCase):
	def test_month_after_the_last_payroll(self):
		from avinashgroup_app.payroll import payroll_month

		last = frappe.db.get_value(
			"Payroll Entry", {"company": NGI, "docstatus": ("<", 2)}, "end_date", order_by="end_date desc"
		)
		if not last:
			self.skipTest("NGI has no payroll entry")
		with patch.object(payroll_month, "today", return_value="2027-01-01"):
			month = payroll_month.default_month(NGI)
		after = payroll_month.month_of_date(NGI, frappe.utils.add_days(last, 1))
		self.assertEqual(month["label"], after.label)

	def test_never_past_the_running_month(self):
		from avinashgroup_app.payroll import payroll_month

		if not frappe.db.exists("Payroll Entry", {"company": NGI, "docstatus": ("<", 2)}):
			self.skipTest("NGI has no payroll entry")
		# On the last payroll's own end date, the month after it has not begun.
		last = frappe.db.get_value(
			"Payroll Entry", {"company": NGI, "docstatus": ("<", 2)}, "end_date", order_by="end_date desc"
		)
		with patch.object(payroll_month, "today", return_value=str(last)):
			month = payroll_month.default_month(NGI)
		self.assertEqual(month["label"], payroll_month.month_of_date(NGI, last).label)


class TestBankEntryGuard(FrappeTestCase):
	def entry(self):
		name = frappe.db.get_value("Payroll Entry", {"company": NGI, "docstatus": 1}, "name")
		if not name:
			self.skipTest("NGI has no submitted payroll entry")
		return frappe.get_doc("Payroll Entry", name)

	def test_no_payment_account(self):
		entry = self.entry()
		entry.payment_account = None
		with self.assertRaisesRegex(frappe.ValidationError, "press Update"):
			entry.make_bank_entry()

	def test_not_a_bank_account(self):
		entry = self.entry()
		stock = frappe.db.get_value("Account", {"company": NGI, "account_type": "Stock", "is_group": 0}, "name")
		if not stock:
			self.skipTest("NGI has no stock account")
		entry.payment_account = stock
		with self.assertRaisesRegex(frappe.ValidationError, "Bank or Cash"):
			entry.make_bank_entry()


class TestMissingAttendance(FrappeTestCase):
	def test_warns_with_the_count(self):
		from avinashgroup_app.payroll import payroll_month

		if frappe.db.get_single_value("Payroll Settings", "payroll_based_on") != "Attendance":
			self.skipTest("payroll is not based on attendance")
		employee = frappe.db.get_value("Employee", {"company": NGI, "status": "Active"}, "name")
		doc = frappe._dict(
			docstatus=0,
			start_date="2030-01-01",
			end_date="2030-01-31",  # no attendance can exist yet
			employees=[frappe._dict(employee=employee)],
		)
		with patch.object(payroll_month.frappe, "msgprint") as msgprint:
			payroll_month.warn_missing_attendance(doc)
		msgprint.assert_called_once()
		self.assertIn("1 of 1 employees", msgprint.call_args.args[0])


class TestSectionClash(FrappeTestCase):
	def test_account_in_two_sections_is_named(self):
		from avinashgroup_app.avinash_group_app.report.avinas_salary_statement.avinas_salary_statement import (
			section_of_accounts,
		)

		mapping, clashes = section_of_accounts(NGI)
		# NGI's rows are set right: each salary expense ledger has one section.
		self.assertFalse(clashes, clashes)
		self.assertEqual(mapping.get("547102 - Salary Expenses - S/D - NGI"), "S/D")

		with patch.object(
			frappe,
			"get_all",
			return_value=[
				frappe._dict(parent="Edu", account="O1", custom_account_marketing="O1", custom_account_plant="F1"),
				frappe._dict(parent="Basic", account="O1", custom_account_marketing="S1", custom_account_plant="F1"),
			],
		):
			mapping, clashes = section_of_accounts("any")
		# The answer does not depend on row order: O1 is O/O, and Edu is named.
		self.assertEqual(mapping, {"O1": "O/O", "S1": "S/D", "F1": "F/P"})
		self.assertEqual(clashes, [("Edu", "O1", "O/O", "S/D")])


ASHWIN = ("2026-09-17", "2026-10-17")  # 83/84, no slips made yet on avinas1


def _mark(employee, company, days, status):
	for day in days:
		doc = frappe.get_doc(
			{"doctype": "Attendance", "employee": employee, "attendance_date": day, "status": status, "company": company}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()


class TestPrepareInputsRerun(FrappeTestCase):
	def setUp(self):
		# The engine commits its own work; stubbed so the test's rows roll back.
		stub = patch.object(frappe.db, "commit")
		stub.start()
		self.addCleanup(stub.stop)

	def test_a_second_press_removes_what_is_no_longer_due(self):
		from avinashgroup_app.payroll.attendance_allowance import create_additional_salaries

		employee = frappe.db.sql(
			"""select s.employee from `tabSalary Structure Assignment` s
			join `tabAssignment Allowance` aa on aa.parent = s.name and aa.parenttype = 'Salary Structure Assignment'
			where s.docstatus = 1 and aa.allowance = 'Tea & Conveyance' and aa.rate > 0
			and not exists (select 1 from tabAttendance at where at.employee = s.employee
				and at.attendance_date between '2026-09-17' and '2026-10-17')
			limit 1"""
		)
		if not employee or frappe.db.exists(
			"Attendance", {"employee": employee[0][0], "attendance_date": ("between", ASHWIN)}
		):
			self.skipTest("no tea-paid employee with an empty Ashwin")
		employee = employee[0][0]
		company = frappe.db.get_value("Employee", employee, "company")
		_mark(employee, company, ["2026-09-22", "2026-09-23"], "Present")
		entry = frappe._dict(
			start_date=ASHWIN[0], end_date=ASHWIN[1], company=company, employees=[frappe._dict(employee=employee)]
		)
		live = lambda: frappe.db.count(  # noqa: E731
			"Additional Salary",
			{"employee": employee, "payroll_date": ASHWIN[1], "docstatus": 1, "salary_component": "Tea & Conveyance"},
		)
		create_additional_salaries(entry)
		self.assertEqual(live(), 1)

		for name in frappe.get_all(
			"Attendance", {"employee": employee, "attendance_date": ("between", ASHWIN)}, pluck="name"
		):
			frappe.db.set_value("Attendance", name, "status", "Absent")
		result = create_additional_salaries(entry)
		self.assertEqual(live(), 0, "the first press's tea must not stay paid")
		self.assertEqual([c["salary_component"] for c in result["cleared"]], ["Tea & Conveyance"])

	def test_the_button_checks_the_callers_rights(self):
		from avinashgroup_app.payroll.attendance_allowance import trigger_for_payroll_entry

		entry = frappe.db.get_value("Payroll Entry", {"docstatus": ("<", 2)})
		if not entry:
			self.skipTest("no payroll entry")
		frappe.set_user("Guest")
		try:
			self.assertRaises(frappe.PermissionError, trigger_for_payroll_entry, entry)
		finally:
			frappe.set_user("Administrator")


class TestAllowanceProration(FrappeTestCase):
	def test_resave_prorates_allowances_with_the_new_payment_days(self):
		row = frappe.db.sql(
			"""select s.employee, s.salary_structure from `tabSalary Structure Assignment` s
			join `tabAssignment Allowance` aa on aa.parent = s.name and aa.parenttype = 'Salary Structure Assignment'
			join `tabSalary Component` c on c.name = aa.allowance and c.custom_allowance_kind = 'Monthly'
			where s.docstatus = 1 and aa.rate > 0
			and not exists (select 1 from tabAttendance at where at.employee = s.employee
				and at.attendance_date between '2026-09-17' and '2026-10-17')
			limit 1""",
			as_dict=True,
		)
		if not row or frappe.db.exists("Attendance", {"employee": row[0].employee, "attendance_date": ("between", ASHWIN)}):
			self.skipTest("no monthly-allowance employee with an empty Ashwin")
		employee, structure = row[0].employee, row[0].salary_structure
		slip = frappe.new_doc("Salary Slip")
		slip.update(
			{"employee": employee, "posting_date": ASHWIN[1], "start_date": ASHWIN[0],
			 "salary_structure": structure, "payroll_frequency": "Monthly"}
		)
		slip.run_method("validate")
		_mark(employee, slip.company, ["2026-09-20", "2026-09-21"], "Absent")
		slip.run_method("validate")

		self.assertLess(slip.payment_days, slip.total_working_days)
		for e in slip.earnings:
			if frappe.get_cached_value("Salary Component", e.salary_component, "custom_allowance_kind") == "Monthly":
				expected = e.default_amount * slip.payment_days / slip.total_working_days
				self.assertAlmostEqual(e.amount, expected, delta=0.02, msg=e.salary_component)
		self.assertAlmostEqual(slip.gross_pay, sum(e.amount for e in slip.earnings), delta=0.02)


class TestTaxHistory(FrappeTestCase):
	def test_a_month_with_no_slip_and_no_opening_is_named(self):
		from avinashgroup_app.payroll.income_tax import tax_history_gaps

		row = frappe.db.sql(
			"""select s.name, s.employee, s.company from `tabSalary Structure Assignment` s
			join `tabPayroll Period` p on p.company = s.company and s.from_date = p.start_date
			where s.docstatus = 1 and p.start_date < %s and not exists (
				select 1 from `tabSalary Slip` ss where ss.employee = s.employee and ss.docstatus = 1
				and ss.start_date = p.start_date) limit 1""",
			ASHWIN[0],
			as_dict=True,
		)
		if not row:
			self.skipTest("everyone's first month has a slip")
		a = row[0]
		frappe.db.set_value("Salary Structure Assignment", a.name, {"taxable_earnings_till_date": 0, "tax_deducted_till_date": 0})
		self.assertIn(a.employee, tax_history_gaps(a.company, [a.employee], ASHWIN[0]))
		frappe.db.set_value("Salary Structure Assignment", a.name, "taxable_earnings_till_date", 100000)
		self.assertNotIn(a.employee, tax_history_gaps(a.company, [a.employee], ASHWIN[0]))

	def test_the_first_month_of_the_year_needs_nothing(self):
		from avinashgroup_app.payroll.income_tax import tax_history_gaps

		employee = frappe.db.get_value("Employee", {"company": NGI, "status": "Active"}, "name")
		self.assertEqual(tax_history_gaps(NGI, [employee], "2026-07-17"), [])


class TestNewYearSlab(FrappeTestCase):
	def test_rates_without_the_womens_rebate_are_refused(self):
		from avinashgroup_app.hr import year_setup
		from avinashgroup_app.payroll import income_tax

		year = frappe._dict(year_start_date="2099-07-17")
		with patch.dict(income_tax.TAX_SLABS_BY_YEAR, {"99/00": income_tax.FY_8384_SLABS}):
			self.assertRaises(frappe.ValidationError, year_setup.require_tax_table, "99/00", year, [NGI])
			with patch.dict(income_tax.WOMEN_REBATE_BY_YEAR, {"99/00": 10}):
				year_setup.require_tax_table("99/00", year, [NGI])
				name = year_setup.ensure_income_tax_slab(NGI, "NGI", "99/00", year)
		self.assertEqual(frappe.db.get_value("Income Tax Slab", name, "custom_women_rebate_percent"), 10)


class TestHolidayWorkRuleOnEmployee(FrappeTestCase):
	"""Overtime or replacement leave is two ticks on the Employee (2026-10-13),
	not the Employee Category — and a holiday worked earns one, never both."""

	def setUp(self):
		self.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not self.employee:
			self.skipTest("no active employee on this site")

	def _tick(self, ot, leave):
		frappe.db.set_value(
			"Employee",
			self.employee,
			{"custom_ot_eligibility": ot, "custom_compensatory_leave": leave},
			update_modified=False,
		)

	def _evaluate_on(self, day_type, work_type=None):
		from avinashgroup_app.hr import overtime

		with patch.object(overtime, "get_day_type", return_value=(day_type, None)), patch.object(
			overtime, "get_shift_window", return_value=("Test Shift", None, None)
		):
			return overtime.evaluate(self.employee, "2026-10-03", work_type)

	def test_both_ticks_are_refused(self):
		doc = frappe.get_doc("Employee", self.employee)
		doc.custom_ot_eligibility = 1
		doc.custom_compensatory_leave = 1
		with self.assertRaisesRegex(frappe.ValidationError, "not both"):
			doc.run_method("validate")

	def test_entitlement_follows_the_employee_ticks(self):
		from avinashgroup_app.hr import overtime

		self._tick(1, 0)
		self.assertEqual(self._evaluate_on(overtime.DAY_HOLIDAY)["entitlement"], overtime.ENTITLEMENT_OVERTIME)
		self.assertEqual(self._evaluate_on(overtime.DAY_WORKING)["entitlement"], overtime.ENTITLEMENT_OVERTIME)

		self._tick(0, 1)
		self.assertEqual(
			self._evaluate_on(overtime.DAY_WEEKLY_OFF)["entitlement"], overtime.ENTITLEMENT_REPLACEMENT_LEAVE
		)
		with self.assertRaisesRegex(overtime.OvertimeRuleError, "not ticked Overtime Eligible"):
			self._evaluate_on(overtime.DAY_WORKING)

		self._tick(0, 0)
		with self.assertRaisesRegex(overtime.OvertimeRuleError, "neither"):
			self._evaluate_on(overtime.DAY_HOLIDAY)

	def test_category_no_longer_decides(self):
		"""A category saying the opposite changes nothing."""
		from avinashgroup_app.hr import overtime
		from avinashgroup_app.hr.shift_day import overtime_eligibility

		leave_category = frappe.db.get_value("Employee Category", {"compensatory_leave": 1}, "name")
		if leave_category:
			frappe.db.set_value(
				"Employee", self.employee, "custom_employee_category", leave_category, update_modified=False
			)
		self._tick(1, 0)
		self.assertEqual(overtime.get_holiday_work_rule(self.employee), (True, False))
		self.assertEqual(overtime_eligibility([self.employee]), {self.employee: True})
