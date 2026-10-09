"""Tests for allowances (payroll/allowance.py, salary_slip.py, attendance_allowance.py).

Covers:
- an allowance's kind sets its attendance settings; S/D and F/P accounts must
  be the row's company's
- the structure holds only shared lines: an attendance allowance's row is a
  tag; a fixed, yearly or hand-entered allowance is refused there
- the assignment's Allowances: allowances only, not yearly / hand-entered, a
  per-person allowance needs its amount
- the slip: per-person amount, company rate, own amount over the company rate,
  % of Initial Basic; prorated like Basic; projected for income tax; dropped
  when the row is made inactive
- attendance allowances: tagged by the structure or the person's own row, an
  inactive row stops it, OT-eligible-only, own rate over the company rate
- the meal rule; counting the previous BS month's attendance
- the payroll journal posts each section to its own account, and refuses an
  employee whose Department has no section
- the migration reads the old structures' company rates from their formulas

Everything is built inside one transaction and rolled back by FrappeTestCase.
The attendance count, the Additional Salary writer and the commit are replaced
in the engine tests, so they need no Attendance on the site.

Run like the shift rotation suite (docs/shift-rotation.md, "Tests"), with
"avinashgroup_app.payroll.test_allowance" and site avinas1.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from avinashgroup_app.payroll import attendance_allowance

COMPANY = "Nepal Gas Udhyog Pvt. Ltd."
OTHER_COMPANY = "Nepal Gas Udhyog (Gandaki) Pvt. Ltd."
ADMIN_DEPT = "Finance/ Accounts - NGI"
MARKETING_DEPT = "Sales/ Marketing - NGI"
PLANT_DEPT = "Plant/ Maintenance - NGI"
PERIOD_START, PERIOD_END = "2026-07-17", "2026-08-16"  # Shrawan 2083
OTHER = ("547110 - Other Allowance - O/O - NGI", "547111 - Other Allowance - S/D - NGI", "547112 - Other Allowance - F/P - NGI")
MEAL = ("547130 - Meal Allowance - O/O - NGI", "547131 - Meal Allowance - S/D - NGI", "547132 - Meal Allowance - F/P - NGI")
TAX_SLAB = "Nepal 83/84 - NGI"


def _clear_request_caches():
	for key in ("_agp_account_row", "_agp_payroll_section", "_agp_structure_components"):
		if hasattr(frappe.local, key):
			delattr(frappe.local, key)


class TestAllowance(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.tea = cls._component("CA Test Tea", "CATEA", "Per Day Present", rate=235)
		cls.meal = cls._component(
			"CA Test Meal",
			"CAMEAL",
			"Per Meal",
			accounts=MEAL,
			rate=75,
			custom_ot_eligible_only=1,
			custom_time_offset_hours=1.5,
			custom_max_per_day=2,
		)
		cls.da = cls._component("CA Test DA", "CADA", "Fixed per Person")
		cls.mobile = cls._component("CA Test Mobile", "CAMOB", "Fixed Company Rate", rate=1500)
		cls.hra = cls._component("CA Test HRA", "CAHRA", "% of Initial Basic", rate=25)
		basic = {"salary_component": "Basic", "amount_based_on_formula": 1, "formula": "base", "depends_on_payment_days": 1}
		cls.structure = cls._structure(
			"CA Test Structure",
			# The tea row is a tag: the hook blanks the 999.
			earnings=[basic, {"salary_component": cls.tea, "amount": 999}, {"salary_component": cls.meal}],
		)
		cls.bare_structure = cls._structure("CA Test Bare Structure", earnings=[dict(basic)])

	@classmethod
	def _component(cls, name, abbr, kind, accounts=OTHER, rate=0, company=COMPANY, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": name,
				"salary_component_abbr": abbr,
				"type": "Earning",
				"depends_on_payment_days": 1,  # an attendance kind turns this off itself
				"is_tax_applicable": 1,
				"custom_is_allowance": 1,
				"custom_allowance_kind": kind,
				"accounts": [
					{
						"company": company,
						"account": accounts[0],
						"custom_account_marketing": accounts[1],
						"custom_account_plant": accounts[2],
						"custom_default_rate": rate,
					}
				],
				**values,
			}
		).insert(ignore_permissions=True)
		return doc.name

	@classmethod
	def _structure(cls, name, earnings):
		doc = frappe.get_doc(
			{
				"doctype": "Salary Structure",
				"name": name,
				"company": COMPANY,
				"currency": "NPR",
				"payroll_frequency": "Monthly",
				"is_active": "Yes",
				"earnings": earnings,
			}
		).insert(ignore_permissions=True)
		doc.submit()
		return doc.name

	def setUp(self):
		frappe.clear_messages()
		_clear_request_caches()

	def _employee(
		self, allowances=(), department=ADMIN_DEPT, company=COMPANY, structure=None, initial_basic=0, **values
	):
		"""An employee; with a structure, an assignment carrying the allowances
		as (allowance, amount, active) tuples and the Initial Basic."""
		emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "Allowance Test",
				"gender": "Male",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": company,
				"department": department if company == COMPANY else None,
				"status": "Active",
				**values,
			}
		).insert(ignore_permissions=True)
		if structure:
			frappe.get_doc(
				{
					"doctype": "Salary Structure Assignment",
					"employee": emp.name,
					"salary_structure": structure,
					"company": COMPANY,
					"currency": "NPR",
					"from_date": max(str(emp.date_of_joining), PERIOD_START),
					"base": 30000,
					"income_tax_slab": TAX_SLAB,
					"custom_initial_basic": initial_basic,
					"custom_allowances": [
						{"allowance": a, "amount": amount, "active": active} for a, amount, active in allowances
					],
				}
			).insert(ignore_permissions=True).submit()
		return emp.name

	def _slip(self, employee):
		return frappe.get_doc(
			{
				"doctype": "Salary Slip",
				"employee": employee,
				"start_date": PERIOD_START,
				"posting_date": PERIOD_END,
				"payroll_frequency": "Monthly",
				"company": COMPANY,
			}
		).insert(ignore_permissions=True)

	# ── the component and the structure ─────────────────────────────────────

	def test_attendance_kind_sets_its_flags(self):
		tea = frappe.get_doc("Salary Component", self.tea)
		self.assertEqual(
			(tea.custom_is_attendance_driven, tea.custom_condition_type, tea.depends_on_payment_days, tea.remove_if_zero_valued),
			(1, "Status = Present", 0, 1),
		)
		mobile = frappe.get_doc("Salary Component", self.mobile)
		self.assertEqual((mobile.custom_is_attendance_driven, mobile.depends_on_payment_days), (0, 1))

	def test_structure_row_of_attendance_allowance_is_a_tag(self):
		doc = frappe.get_doc("Salary Structure", self.structure)
		tea = next(r for r in doc.earnings if r.salary_component == self.tea)
		self.assertEqual((tea.amount, tea.formula or "", tea.amount_based_on_formula), (0, "", 0))

	def test_fixed_and_yearly_allowances_refused_in_structure(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Allowances table"):
			self._structure("CA Test Fixed Structure", earnings=[{"salary_component": self.mobile, "amount": 1500}])
		bonus = self._component("CA Test Bonus", "CABON", "Yearly")
		with self.assertRaisesRegex(frappe.ValidationError, "paid when entered"):
			self._structure("CA Test Yearly Structure", earnings=[{"salary_component": bonus, "amount": 1}])

	def test_section_account_of_another_company_is_refused(self):
		gandaki = frappe.db.get_value("Account", {"company": OTHER_COMPANY, "is_group": 0, "root_type": "Expense"})
		with self.assertRaisesRegex(frappe.ValidationError, "is not an account of"):
			self._component("CA Test Fuel", "CAFUEL", "Fixed per Person", accounts=(OTHER[0], gandaki, None))

	# ── the assignment's table ──────────────────────────────────────────────

	def test_assignment_table_checks(self):
		bonus = self._component("CA Test Bonus 2", "CABON2", "Yearly")
		with self.assertRaisesRegex(frappe.ValidationError, "paid when entered"):
			self._employee([(bonus, 1, 1)], structure=self.bare_structure)
		with self.assertRaisesRegex(frappe.ValidationError, "monthly amount"):
			self._employee([(self.da, 0, 1)], structure=self.bare_structure)
		with self.assertRaisesRegex(frappe.ValidationError, "not an allowance"):
			self._employee([("Basic", 1, 1)], structure=self.bare_structure)

	def test_employee_holds_no_pay(self):
		meta = frappe.get_meta("Employee")
		for field in ("custom_dearness_allowance", "custom_initial_basic", "custom_ssf_applicable", "custom_allowances"):
			self.assertFalse(meta.has_field(field), field)

	# ── fixed allowances on the slip ────────────────────────────────────────

	def test_slip_has_the_employees_fixed_allowances(self):
		employee = self._employee(
			[(self.da, 7380, 1), (self.mobile, 0, 1), (self.hra, 0, 1)],
			structure=self.bare_structure,
			initial_basic=20000,
		)
		slip = self._slip(employee)
		rows = {d.salary_component: d for d in slip.earnings}
		self.assertEqual(rows[self.da].default_amount, 7380)  # their own amount
		self.assertEqual(rows[self.mobile].default_amount, 1500)  # the company rate
		self.assertEqual(rows[self.hra].default_amount, 5000)  # 25 % of 20,000
		basic = rows["Basic"]
		ratio = basic.amount / basic.default_amount
		for component in (self.da, self.mobile, self.hra):
			self.assertFalse(rows[component].additional_salary)  # projected for tax
			self.assertAlmostEqual(rows[component].amount / rows[component].default_amount, ratio, places=3)

		# A change is a new dated assignment; this one stops the mobile allowance.
		assignment = frappe.get_last_doc("Salary Structure Assignment", {"employee": employee, "docstatus": 1})
		frappe.db.set_value(
			"Assignment Allowance", {"parent": assignment.name, "allowance": self.mobile}, "active", 0
		)
		slip.reload()
		slip.save(ignore_permissions=True)
		self.assertNotIn(self.mobile, {d.salary_component for d in slip.earnings})

	def test_own_amount_beats_company_rate(self):
		slip = self._slip(self._employee([(self.mobile, 2000, 1)], structure=self.bare_structure))
		self.assertEqual(next(d for d in slip.earnings if d.salary_component == self.mobile).default_amount, 2000)

	def test_fixed_allowance_is_projected_for_tax(self):
		with_mobile = self._slip(self._employee([(self.mobile, 0, 1)], structure=self.bare_structure))
		without = self._slip(self._employee(structure=self.bare_structure))
		self.assertGreaterEqual(with_mobile.annual_taxable_amount - without.annual_taxable_amount, 1500 * 11)

	def test_tag_rows_print_nothing_on_the_slip(self):
		slip = self._slip(self._employee(structure=self.structure))
		self.assertFalse({self.tea, self.meal} & {d.salary_component for d in slip.earnings})

	# ── attendance allowances ───────────────────────────────────────────────

	def _run_engine(self, employees, qty=10):
		made = []

		def capture(employee, salary_component, amount, **kwargs):
			made.append((employee, salary_component.name, amount))
			return frappe._dict(name="x")

		entry = frappe._dict(
			company=COMPANY,
			start_date=PERIOD_START,
			end_date=PERIOD_END,
			employees=[frappe._dict(employee=e) for e in employees],
		)
		with (
			patch.object(attendance_allowance, "_qty_for_employee", return_value=qty),
			patch.object(attendance_allowance, "_make_additional_salary", side_effect=capture),
			patch.object(attendance_allowance, "_delete_existing_draft"),
			patch.object(attendance_allowance, "refresh_draft_slips", return_value=0),
			patch.object(frappe.db, "commit"),
		):
			attendance_allowance.create_additional_salaries(entry)
		return {(e, c): a for e, c, a in made if c in (self.tea, self.meal)}

	def test_structure_tags_who_is_paid_at_company_rate(self):
		tagged = self._employee(structure=self.structure)
		untagged = self._employee(structure=self.bare_structure)
		paid = self._run_engine([tagged, untagged])
		self.assertEqual(paid, {(tagged, self.tea): 2350})

	def test_own_rate_inactive_and_row_tag(self):
		new_staff = self._employee([(self.tea, 40, 1)], structure=self.structure)
		no_tea = self._employee([(self.tea, 0, 0)], structure=self.structure)
		row_only = self._employee([(self.tea, 0, 1)], structure=self.bare_structure)
		paid = self._run_engine([new_staff, no_tea, row_only])
		self.assertEqual(paid, {(new_staff, self.tea): 400, (row_only, self.tea): 2350})

	def test_meal_only_for_ot_eligible(self):
		eligible = self._employee(structure=self.structure, custom_ot_eligibility=1)
		not_eligible = self._employee(structure=self.structure, custom_ot_eligibility=0)
		paid = {k: v for k, v in self._run_engine([eligible, not_eligible], qty=4).items() if k[1] == self.meal}
		self.assertEqual(paid, {(eligible, self.meal): 300})

	def _overtime_sheet(self, employee, work_date, entitlement="Overtime"):
		"""A submitted Overtime Sheet calling the employee in on that date."""
		sheet = frappe.get_doc(
			{
				"doctype": "Overtime Sheet",
				"company": COMPANY,
				"work_date": work_date,
				"reason": "Test: called in",
				"employees": [{"employee": employee, "entitlement": entitlement, "work_type": "Overtime"}],
			}
		)
		sheet.flags.ignore_validate = True
		sheet.flags.ignore_links = True
		sheet.insert(ignore_permissions=True)
		sheet.db_set("docstatus", 1)
		frappe.local._agp_on_ot_sheet = {}

	def test_meal_rule(self):
		"""A meal follows overtime the company authorised, for OT-eligible staff
		only: 1.5 h early or late on a working day = 1 each, a holiday = 2, max 2."""
		sc = frappe.get_doc("Salary Component", self.meal)
		day, holiday = "2026-07-20", "2026-07-25"

		def meals(employee, date, early=0, late=0, on_holiday=0):
			row = frappe._dict(
				status="Present",
				attendance_date=date,
				working_hours=11,
				custom_worked_on_holiday=on_holiday,
				custom_early_entry=early * 60,
				custom_late_exit=late * 60,
			)
			return attendance_allowance.evaluate_rule(row, sc, employee)

		called = self._employee(custom_ot_eligibility=1)
		self._overtime_sheet(called, day)
		self._overtime_sheet(called, holiday)
		self.assertEqual(meals(called, day, early=100, late=105), 2)  # IN 07:20, OUT 18:45
		self.assertEqual(meals(called, day, early=100, late=30), 1)  # IN 07:20, OUT 17:30
		self.assertEqual(meals(called, day, early=60, late=60), 0)  # neither side reaches 1.5 h
		self.assertEqual(meals(called, holiday, on_holiday=1), 2)  # a holiday, any hours

		on_own = self._employee(custom_ot_eligibility=1)  # same punches, nobody called them
		self.assertEqual(meals(on_own, day, early=100, late=105), 0)
		self.assertEqual(meals(on_own, holiday, on_holiday=1), 0)

		not_eligible = self._employee(custom_ot_eligibility=0)
		self._overtime_sheet(not_eligible, day)
		self.assertEqual(meals(not_eligible, day, early=100, late=105), 0)

		replacement = self._employee(custom_ot_eligibility=1)
		self._overtime_sheet(replacement, holiday, entitlement="Replacement Leave")
		self.assertEqual(meals(replacement, holiday, on_holiday=1), 0)

	def test_previous_attendance_month(self):
		sc = frappe._dict(custom_attendance_month="Previous Month")
		start, end = attendance_allowance._attendance_period(sc, getdate("2026-08-17"), getdate("2026-09-16"))
		self.assertEqual((str(start), str(end)), (PERIOD_START, PERIOD_END))  # Bhadra pays Shrawan
		same = attendance_allowance._attendance_period(frappe._dict(), getdate(PERIOD_START), getdate(PERIOD_END))
		self.assertEqual(tuple(map(str, same)), (PERIOD_START, PERIOD_END))

	# ── the payroll journal ─────────────────────────────────────────────────

	def _journal_lines(self, employees):
		entry = frappe.new_doc("Payroll Entry")
		entry.company = COMPANY
		items = [
			frappe._dict(
				salary_component=self.mobile,
				amount=1000,
				parentfield="earnings",
				additional_salary=None,
				salary_structure=self.structure,
				employee=e,
			)
			for e in employees
		]
		with (
			patch.object(type(entry), "get_salary_components", return_value=items),
			patch.object(type(entry), "get_payroll_cost_centers_for_employee", return_value={"Main - NGI": 100}),
		):
			return entry.get_salary_component_total(component_type="earnings")

	def test_each_section_posts_to_its_own_account(self):
		admin = self._employee(department=ADMIN_DEPT)
		marketing = self._employee(department=MARKETING_DEPT)
		plant = self._employee(department=PLANT_DEPT)
		plant_2 = self._employee(department=PLANT_DEPT)
		lines = self._journal_lines([admin, marketing, plant, plant_2])
		self.assertEqual(
			lines,
			{(OTHER[0], "Main - NGI"): 1000, (OTHER[1], "Main - NGI"): 1000, (OTHER[2], "Main - NGI"): 2000},
		)

	def test_department_without_section_is_refused(self):
		dept = frappe.get_doc(
			{"doctype": "Department", "department_name": "CA Test No Section", "company": COMPANY}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Department", dept.name, "custom_payroll_section", None)
		employee = self._employee(department=dept.name)
		with self.assertRaisesRegex(frappe.ValidationError, "Payroll Section"):
			self._journal_lines([employee])

	# ── the migration ───────────────────────────────────────────────────────

	def test_migration_reads_company_rate_from_old_formula(self):
		from avinashgroup_app.patches import move_pay_to_salary_assignment as patch_

		gas = self._component("Gas Allowance" if not frappe.db.exists("Salary Component", "Gas Allowance") else "CA Test Gas", "CAGAS", "Fixed Company Rate")
		frappe.db.set_value("Salary Component Account", {"parent": gas, "company": COMPANY}, "custom_default_rate", 0)
		old = frappe.get_doc(
			{
				"doctype": "Salary Structure",
				"name": "CA Test Old Structure",
				"company": COMPANY,
				"currency": "NPR",
				"payroll_frequency": "Monthly",
				"is_active": "Yes",
				"earnings": [{"salary_component": gas, "amount_based_on_formula": 1, "formula": "1690 if custom_gas_allowance else 0"}],
			}
		)
		old.flags.ignore_validate = True  # an old structure, from before the check
		old.insert(ignore_permissions=True)
		old.submit()
		with patch.object(patch_, "RATE_IN_FORMULA", {gas: 1}):
			patch_.rates_from_structures()
		self.assertEqual(
			frappe.db.get_value("Salary Component Account", {"parent": gas, "company": COMPANY}, "custom_default_rate"), 1690
		)
