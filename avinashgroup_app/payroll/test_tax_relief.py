"""Tax reliefs (payroll/tax_relief.py): the women's rebate and the exemption caps.

Run against avinas1's own data, as the other payroll suites do; a case whose
data is missing is skipped, never faked.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from avinashgroup_app.payroll.tax_relief import validate_womens_tax_rebate, women_rebate_fraction

SLAB_10 = frappe._dict(custom_women_rebate_percent=10)


def _employee(gender):
	return frappe.db.get_value("Employee", {"status": "Active", "gender": gender}, "name")


def _slip(employee):
	"""An unsaved slip for Ashwin 83/84, through every validate hook."""
	assignment = frappe.db.get_value(
		"Salary Structure Assignment", {"employee": employee, "docstatus": 1}, "salary_structure"
	)
	slip = frappe.new_doc("Salary Slip")
	slip.update(
		{
			"employee": employee,
			"posting_date": "2026-10-17",
			"start_date": "2026-09-17",
			"salary_structure": assignment,
			"payroll_frequency": "Monthly",
		}
	)
	slip.run_method("validate")  # doc.validate() alone skips the app's hooks
	return slip


def _tax(slip):
	return sum(flt(r.amount) for r in slip.deductions if r.variable_based_on_taxable_salary)


class TestWomensRebate(FrappeTestCase):
	def test_needs_the_tick_not_just_gender(self):
		woman = _employee("Female")
		if not woman:
			self.skipTest("no female employee")
		frappe.db.set_value("Employee", woman, "custom_womens_tax_rebate", 0)
		self.assertEqual(women_rebate_fraction(frappe._dict(employee=woman), SLAB_10), 0)
		frappe.db.set_value("Employee", woman, "custom_womens_tax_rebate", 1)
		self.assertAlmostEqual(women_rebate_fraction(frappe._dict(employee=woman), SLAB_10), 0.1)

	def test_blank_slab_percent_is_no_rebate(self):
		woman = _employee("Female")
		if not woman:
			self.skipTest("no female employee")
		frappe.db.set_value("Employee", woman, "custom_womens_tax_rebate", 1)
		self.assertEqual(women_rebate_fraction(frappe._dict(employee=woman), frappe._dict()), 0)

	def test_a_man_cannot_be_ticked(self):
		man = _employee("Male")
		if not man:
			self.skipTest("no male employee")
		doc = frappe.get_doc("Employee", man)
		doc.custom_womens_tax_rebate = 1
		self.assertRaises(frappe.ValidationError, validate_womens_tax_rebate, doc)
		# and a tick slipped into the database still gives him nothing
		frappe.db.set_value("Employee", man, "custom_womens_tax_rebate", 1)
		self.assertEqual(women_rebate_fraction(frappe._dict(employee=man), SLAB_10), 0)

	def test_slip_tax_is_cut_by_the_rebate(self):
		women = frappe.get_all(
			"Salary Structure Assignment",
			filters={"docstatus": 1, "employee": ["in", frappe.get_all(
				"Employee", filters={"status": "Active", "gender": "Female"}, pluck="name"
			)]},
			pluck="employee",
		)
		for woman in women:
			frappe.db.set_value("Employee", woman, "custom_womens_tax_rebate", 0)
			without = _tax(_slip(woman))
			if without > 0:
				break
		else:
			self.skipTest("no woman pays tax this month")

		slab = _slip(woman).tax_slab.name
		frappe.db.set_value("Income Tax Slab", slab, "custom_women_rebate_percent", 10)
		frappe.db.set_value("Employee", woman, "custom_womens_tax_rebate", 1)
		slip = _slip(woman)
		self.assertEqual(flt(slip.custom_women_rebate), 10)
		self.assertLess(_tax(slip), without)


INSURANCE_CATEGORY = "Insurance Premium"


class TestExemptionCaps(FrappeTestCase):
	def test_insurance_is_cut_to_each_limit(self):
		# By category, not by name: sites call them "Life Insurance" or
		# "Life Insurance Premium".
		limits = dict(
			frappe.get_all(
				"Employee Tax Exemption Sub Category",
				filters={"exemption_category": INSURANCE_CATEGORY},
				fields=["name", "max_amount"],
				as_list=True,
			)
		)
		if not limits:
			self.skipTest("insurance categories not set up")
		limits = {s: flt(v) for s, v in limits.items()}
		employee = frappe.db.get_value("Employee", {"status": "Active", "company": "Nepal Gas Udhyog Pvt. Ltd."})
		declaration = frappe.get_doc(
			{
				"doctype": "Employee Tax Exemption Declaration",
				"employee": employee,
				"company": "Nepal Gas Udhyog Pvt. Ltd.",
				"payroll_period": "83/84 - NGI",
				"currency": "NPR",
				"declarations": [
					{"exemption_sub_category": s, "amount": limit + 5000} for s, limit in limits.items()
				],
			}
		).insert(ignore_permissions=True)
		self.assertEqual(flt(declaration.total_exemption_amount), sum(limits.values()))
