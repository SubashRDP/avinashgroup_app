"""The salary sheet adds up to the slips and checks itself against the journal.

Runs on the submitted Shrawan 83/84 test month of NGI (docs/allowances.md),
whose journal NGI-JE-83/84-00004 was checked by hand.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from avinashgroup_app.avinash_group_app.report.avinas_salary_statement.avinas_salary_statement import execute

COMPANY = "Nepal Gas Udhyog Pvt. Ltd."
FILTERS = {"company": COMPANY, "fiscal_year": "83/84", "bs_month": "04 - Shrawan", "docstatus": "1 - Submitted"}


class TestSalaryStatement(FrappeTestCase):
	def setUp(self):
		slips = frappe.get_all(
			"Salary Slip",
			filters={"company": COMPANY, "docstatus": 1, "start_date": "2026-07-17", "end_date": "2026-08-16"},
			fields=["gross_pay", "net_pay"],
		)
		if not slips:
			self.skipTest("No submitted Shrawan 83/84 slips for NGI on this site.")
		self.slips = slips

	def test_columns_add_up_to_the_slips(self):
		columns, data, _message, _chart, summary = execute(FILTERS)
		names = [c["fieldname"] for c in columns]
		earnings = names[names.index("regular_salary") + 1 : names.index("gross_pay")]
		deductions = names[names.index("gross_pay") + 1 : names.index("total_deduction")]
		people = [r for r in data if r.get("employee")]
		self.assertEqual(len(people), len(self.slips))
		for r in people:
			self.assertAlmostEqual(r.regular_salary + sum(flt(r.get(f)) for f in earnings), r.gross_pay, 2, r.employee)
			self.assertAlmostEqual(sum(flt(r.get(f)) for f in deductions), r.total_deduction, 2, r.employee)
			self.assertAlmostEqual(r.gross_pay - r.total_deduction, r.net_pay, 2, r.employee)
			self.assertAlmostEqual(r.basic_salary - r.basic_deduction, r.net_basic, 2, r.employee)

		grand = data[-1]
		self.assertEqual(grand.employee_name, "Grand Total")
		self.assertAlmostEqual(grand.gross_pay, sum(flt(s.gross_pay) for s in self.slips), 2)
		self.assertAlmostEqual(grand.net_pay, sum(flt(s.net_pay) for s in self.slips), 2)

		# Sections subtotal to the grand total.
		subtotals = {r.section: r for r in data if r.get("bold") and r.get("section")}  # the summary repeats them: same values
		self.assertAlmostEqual(sum(r.net_pay for r in subtotals.values()), grand.net_pay, 2)

	def test_matches_the_journal(self):
		summary = execute(FILTERS)[4]
		self.assertIn("Matches Journal", [c["label"] for c in summary], summary)
