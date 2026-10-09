"""The guards added after the October 2026 audit of avinas1.

  * the sheet import matches by name, the code only as a cross-check (NGN's
    codes drift one place from the ERP IDs);
  * a new Payroll Entry opens on the month after the last payroll;
  * Make Bank Entry refuses an unsaved or non-bank Payment Account;
  * a payroll month with no attendance is announced before slips are made;
  * the salary sheet names an account set for two sections.

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
