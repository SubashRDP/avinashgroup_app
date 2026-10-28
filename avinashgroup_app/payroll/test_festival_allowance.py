"""Dashain allowance (payroll/festival_allowance.py): factor, cap, re-run, tax.

Run against avinas1's own data (NGI's salary assignments), as the other payroll
suites do; everything written is rolled back. A case whose data is missing is
skipped, never faked.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from avinashgroup_app.payroll.festival_allowance import (
	compute_rows,
	festival_amount,
	make_festival_adjustment,
	service_factor,
)

COMPANY = "Nepal Gas Udhyog Pvt. Ltd."
CUTOFF = "2026-10-11"  # Ghatasthapana 2083
SLIP_START, SLIP_END = "2026-09-17", "2026-10-16"  # Ashwin 2083, the month Dashain is paid in


def festival_component():
	"""The site's Dashain component, found by its flag: sites spell it
	differently ("Dashain Allowance", "Dashain Alllowance")."""
	name = frappe.db.get_value("Salary Component", {"custom_is_festival_allowance": 1, "disabled": 0}, "name")
	if not name:
		raise unittest.SkipTest("no festival allowance component on this site")
	return name


def _rules(**overrides):
	rules = frappe._dict(
		name=festival_component(),
		custom_festival_min_service_days=0,
		custom_festival_prorate=1,
		custom_festival_include_daily_wage=0,
		custom_festival_include_leavers=0,
		custom_festival_pay_month="06 - Ashwin",
	)
	rules.update(overrides)
	return rules


def _paid_employee():
	"""An active NGI employee with a salary assignment, and their basic."""
	row = frappe.db.sql(
		"""select a.employee, a.base from `tabSalary Structure Assignment` a
		join tabEmployee e on e.name = a.employee
		where a.docstatus = 1 and e.status = 'Active' and e.company = %s and a.base > 0
		  and a.from_date <= %s
		order by a.from_date desc limit 1""",
		(COMPANY, CUTOFF),  # paid on the cut-off, or there is no basic to give
	)
	return (row[0][0], flt(row[0][1])) if row else (None, 0)


def _ashwin_entry():
	pe = frappe.new_doc("Payroll Entry")
	pe.update({"company": COMPANY, "custom_fiscal_year": "83/84", "custom_bs_month": "06 - Ashwin"})
	pe.insert(ignore_permissions=True)
	return pe


class TestServiceFactor(FrappeTestCase):
	def test_joined_more_than_a_year_ago_is_full(self):
		self.assertEqual(service_factor("2020-01-01", CUTOFF)[2], 1.0)

	def test_joined_exactly_one_year_before_is_full(self):
		service, year_days, factor = service_factor("2025-10-11", CUTOFF)
		self.assertEqual((service, year_days, factor), (365, 365, 1.0))

	def test_a_day_short_of_a_year_is_prorated(self):
		self.assertAlmostEqual(service_factor("2025-10-12", CUTOFF)[2], 364 / 365)

	def test_half_year_is_about_half(self):
		service, year_days, factor = service_factor("2026-04-11", CUTOFF)
		self.assertEqual((service, year_days), (183, 365))
		self.assertAlmostEqual(factor, 0.5, delta=0.01)

	def test_joined_on_or_after_cutoff_is_nothing(self):
		self.assertEqual(service_factor(CUTOFF, CUTOFF)[2], 0.0)
		self.assertEqual(service_factor("2026-11-01", CUTOFF)[2], 0.0)

	def test_leap_year_has_366_days(self):
		self.assertEqual(service_factor("2027-09-01", "2028-03-15")[1], 366)

	def test_factor_above_one_is_clamped(self):
		self.assertEqual(festival_amount(30000, 1.7), 30000)
		self.assertEqual(festival_amount(30000, -0.5), 0)
		self.assertEqual(festival_amount(30000, 0.5), 15000)

	def test_proration_off_pays_a_full_month(self):
		self.assertEqual(festival_amount(30000, 0.25, prorate=0), 30000)


class TestComputeRows(FrappeTestCase):
	def setUp(self):
		self.employee, self.basic = _paid_employee()
		if not self.employee:
			self.skipTest("no NGI employee with a salary assignment")

	def _row(self, rules=None):
		result = compute_rows(COMPANY, [self.employee], rules or _rules(), CUTOFF)
		return (result["rows"] or [None])[0], result["left_out"]

	def test_full_year_is_one_months_basic(self):
		frappe.db.set_value("Employee", self.employee, {"date_of_joining": "2015-01-01", "relieving_date": None})
		row, _ = self._row()
		self.assertEqual(row["amount"], flt(self.basic, 2))
		self.assertEqual(row["base_amount"], flt(self.basic, 2))
		self.assertEqual(row["prorate_factor"], 1)

	def test_half_year_joiner_gets_about_half(self):
		frappe.db.set_value("Employee", self.employee, {"date_of_joining": "2026-04-11", "relieving_date": None})
		row, _ = self._row()
		self.assertEqual(row["service_days"], 183)
		self.assertAlmostEqual(row["amount"], self.basic * 183 / 365, delta=0.01)

	def test_joiner_after_cutoff_is_left_out(self):
		frappe.db.set_value("Employee", self.employee, {"date_of_joining": "2026-10-12", "relieving_date": None})
		row, left_out = self._row()
		self.assertIsNone(row)
		self.assertEqual(left_out[0]["employee"], self.employee)

	def test_leaver_before_cutoff_excluded_by_default(self):
		frappe.db.set_value("Employee", self.employee, {"date_of_joining": "2026-04-11", "relieving_date": "2026-10-01"})
		row, left_out = self._row()
		self.assertIsNone(row)
		self.assertIn("before the cut-off", left_out[0]["reason"])

	def test_leaver_included_is_prorated_to_relieving_date(self):
		frappe.db.set_value("Employee", self.employee, {"date_of_joining": "2026-04-11", "relieving_date": "2026-10-01"})
		row, _ = self._row(_rules(custom_festival_include_leavers=1))
		# 2026-04-11 → 2026-10-01 is 173 days, of the 365 ending 2026-10-01
		self.assertEqual(row["service_days"], 173)
		self.assertAlmostEqual(row["amount"], self.basic * 173 / 365, delta=0.01)

	def test_minimum_service(self):
		frappe.db.set_value("Employee", self.employee, {"date_of_joining": "2026-09-01", "relieving_date": None})
		row, _ = self._row(_rules(custom_festival_min_service_days=90))
		self.assertIsNone(row)


class TestAdjustmentRun(FrappeTestCase):
	def setUp(self):
		# The rule under test, whatever the site has typed on its component.
		frappe.db.set_value("Salary Component", festival_component(), "custom_festival_pay_month", "06 - Ashwin")

	def test_rerun_does_not_double_and_cap_holds(self):
		pe = _ashwin_entry()
		if not pe.employees:
			self.skipTest("no NGI employees on an Ashwin entry")
		first = make_festival_adjustment(pe.name, festival_component(), CUTOFF)
		if not first["payroll_adjustment"]:
			# A first run needs someone not yet paid this year's Dashain.
			self.skipTest("everyone on the Ashwin entry is already paid this Dashain")
		self.assertTrue(first["payroll_adjustment"])
		second = make_festival_adjustment(pe.name, festival_component(), CUTOFF)
		self.assertEqual(first["payroll_adjustment"], second["payroll_adjustment"])
		self.assertEqual(first["count"], second["count"])
		self.assertEqual(frappe.db.count("Payroll Adjustment", {"payroll_entry": pe.name}), 1)

		doc = frappe.get_doc("Payroll Adjustment", first["payroll_adjustment"])
		row = doc.adjustments[0]
		row.amount = flt(row.base_amount) + 1
		self.assertRaises(frappe.ValidationError, doc.save)
		doc.reload()
		doc.submit()
		self.assertEqual(
			frappe.db.count("Additional Salary", {"salary_component": festival_component(), "docstatus": 1, "employee": ("in", [r.employee for r in doc.adjustments])}),
			len(doc.adjustments),
		)

		third = make_festival_adjustment(pe.name, festival_component(), CUTOFF)
		self.assertEqual(third["count"], 0)
		self.assertIsNone(third["payroll_adjustment"])
		# Everyone the first run paid is now left out as paid; others (no
		# assignment on the cut-off, say) keep their own reason.
		paid = {r.employee for r in doc.adjustments}
		self.assertTrue(paid <= {x["employee"] for x in third["left_out"] if "already paid" in x["reason"]})

	def test_wrong_month_is_refused(self):
		pe = frappe.new_doc("Payroll Entry")
		pe.update({"company": COMPANY, "custom_fiscal_year": "83/84", "custom_bs_month": "07 - Kartik"})
		try:
			pe.insert(ignore_permissions=True)
		except Exception as e:
			self.skipTest(f"cannot make a Kartik entry: {e}")
		self.assertRaises(frappe.ValidationError, make_festival_adjustment, pe.name, festival_component(), CUTOFF)


class TestTaxOnSlip(FrappeTestCase):
	def _slip(self, employee):
		structure = frappe.db.get_value(
			"Salary Structure Assignment", {"employee": employee, "docstatus": 1}, "salary_structure"
		)
		slip = frappe.new_doc("Salary Slip")
		slip.update(
			{
				"employee": employee,
				"posting_date": SLIP_END,
				"start_date": SLIP_START,
				# Explicit: with BS-month payroll off in Nepal HRMS Settings a bare
				# slip runs to the English month end and misses the allowance.
				"end_date": SLIP_END,
				"salary_structure": structure,
				"payroll_frequency": "Monthly",
			}
		)
		slip.run_method("validate")
		return slip

	@staticmethod
	def _tax(slip):
		return sum(flt(r.amount) for r in slip.deductions if r.variable_based_on_taxable_salary)

	def test_dashain_stays_off_the_salary_slip(self):
		# Paid on its own Dashain payout slip since 2026-10-26; the payout's slip
		# and tax are payroll/test_special_payout.py's.
		row = frappe.db.sql(
			"""select a.employee, a.base from `tabSalary Structure Assignment` a
			join tabEmployee e on e.name = a.employee
			where a.docstatus = 1 and e.status = 'Active' and e.company = %s
			  and a.from_date <= %s order by a.base desc limit 1""",
			(COMPANY, SLIP_START),  # an assignment the Ashwin slip can use
		)
		if not row:
			self.skipTest("no NGI assignment")
		employee, basic = row[0][0], flt(row[0][1])
		without = self._slip(employee)

		adj = frappe.get_doc(
			{
				"doctype": "Payroll Adjustment",
				"company": COMPANY,
				"payroll_date": SLIP_END,
				"adjustments": [{"employee": employee, "salary_component": festival_component(), "amount": basic}],
			}
		)
		adj.insert(ignore_permissions=True)
		adj.submit()
		additional = frappe.get_doc("Additional Salary", adj.adjustments[0].additional_salary)
		self.assertEqual(additional.deduct_full_tax_on_selected_payroll_date, 1)
		self.assertEqual(additional.custom_payout_type, "Dashain Allowance")

		salary = self._slip(employee)
		self.assertNotIn(festival_component(), [r.salary_component for r in salary.earnings])
		self.assertAlmostEqual(self._tax(salary), self._tax(without), delta=0.01)
