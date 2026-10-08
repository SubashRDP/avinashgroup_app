"""Tests for allowances on Salary Component (payroll/allowance.py and its readers).

Covers:
- an allowance's kind sets its attendance settings; S/D and F/P accounts must
  be the row's company's
- an attendance allowance's structure row is only a tag; Yearly and
  hand-entered kinds are refused in a structure
- who is paid: tagged by their structure, or by their own row; an unticked row
  stops it; OT-eligible-only; the employee's rate, else the company's
  Default Rate on the Accounts row
- the meal rule; a component counting the previous BS month's attendance
- the salary slip: a fixed allowance is a normal structure row, the tag row
  prints nothing
- the payroll journal posts each section to its own account, and refuses an
  employee whose Department has no section
- the exceptions table takes attendance allowances only
- the migration: allowances marked by name, and whatever the old engine paid
  to all is tagged on every active employee

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
		cls.tea = cls._component("CA Test Tea", "CATEA", "Per Day Present", accounts=OTHER, rate=235)
		cls.meal = cls._component(
			"CA Test Meal",
			"CAMEAL",
			"Per Meal",
			accounts=MEAL,
			rate=75,
			custom_ot_eligible_only=1,
			custom_time_offset_hours=1.5,
			custom_holiday_hours_one_meal=6,
			custom_holiday_hours_two_meals=8,
			custom_max_per_day=2,
		)
		cls.mobile = cls._component("CA Test Mobile", "CAMOB", "Fixed Company Rate", accounts=OTHER)
		cls.structure = cls._structure(
			"CA Test Structure",
			earnings=[
				{"salary_component": "Basic", "amount_based_on_formula": 1, "formula": "base", "depends_on_payment_days": 1},
				{"salary_component": cls.mobile, "amount": 1500, "depends_on_payment_days": 1},
				# A tag: the hook blanks the 999.
				{"salary_component": cls.tea, "amount": 999},
				{"salary_component": cls.meal},
			],
		)
		cls.bare_structure = cls._structure(
			"CA Test Bare Structure",
			earnings=[{"salary_component": "Basic", "amount_based_on_formula": 1, "formula": "base", "depends_on_payment_days": 1}],
		)

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

	def _employee(self, rows=(), department=ADMIN_DEPT, company=COMPANY, structure=None, **values):
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
				"custom_attendance_allowances": [dict(r) for r in rows],
				**values,
			}
		).insert(ignore_permissions=True)
		if structure:
			joined = str(emp.date_of_joining)
			frappe.get_doc(
				{
					"doctype": "Salary Structure Assignment",
					"employee": emp.name,
					"salary_structure": structure,
					"company": COMPANY,
					"currency": "NPR",
					"from_date": max(joined, PERIOD_START),
					"base": 30000,
					"income_tax_slab": TAX_SLAB,
				}
			).insert(ignore_permissions=True).submit()
		return emp.name

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

	def test_yearly_allowance_refused_in_structure(self):
		bonus = self._component("CA Test Bonus", "CABON", "Yearly")
		with self.assertRaisesRegex(frappe.ValidationError, "Yearly"):
			self._structure("CA Test Yearly Structure", earnings=[{"salary_component": bonus, "amount": 1}])

	def test_section_account_of_another_company_is_refused(self):
		gandaki = frappe.db.get_value("Account", {"company": OTHER_COMPANY, "is_group": 0, "root_type": "Expense"})
		with self.assertRaisesRegex(frappe.ValidationError, "is not an account of"):
			self._component("CA Test Fuel", "CAFUEL", "Fixed per Person", accounts=(OTHER[0], gandaki, None))

	# ── who is paid an attendance allowance ─────────────────────────────────

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
			patch.object(frappe.db, "commit"),
		):
			attendance_allowance.create_additional_salaries(entry)
		return {(e, c): a for e, c, a in made if c in (self.tea, self.meal)}

	def test_structure_tags_who_is_paid_at_company_rate(self):
		tagged = self._employee(structure=self.structure)
		untagged = self._employee(structure=self.bare_structure)
		paid = self._run_engine([tagged, untagged])
		self.assertEqual(paid, {(tagged, self.tea): 2350})

	def test_own_row_rate_unticked_and_legacy_tag(self):
		new_staff = self._employee([{"salary_component": self.tea, "eligible": 1, "rate": 40}], structure=self.structure)
		no_tea = self._employee([{"salary_component": self.tea, "eligible": 0}], structure=self.structure)
		row_only = self._employee([{"salary_component": self.tea, "eligible": 1}], structure=self.bare_structure)
		paid = self._run_engine([new_staff, no_tea, row_only])
		self.assertEqual(paid, {(new_staff, self.tea): 400, (row_only, self.tea): 2350})

	def test_meal_only_for_ot_eligible(self):
		eligible = self._employee(structure=self.structure, custom_ot_eligibility=1)
		not_eligible = self._employee(structure=self.structure, custom_ot_eligibility=0)
		paid = {k: v for k, v in self._run_engine([eligible, not_eligible], qty=4).items() if k[1] == self.meal}
		self.assertEqual(paid, {(eligible, self.meal): 300})

	def test_meal_rule(self):
		employee = self._employee()
		sc = frappe.get_doc("Salary Component", self.meal)
		day = frappe._dict(
			status="Present",
			working_hours=11,
			custom_worked_on_holiday=0,
			custom_early_entry=100 * 60,  # 1 h 40 m early
			custom_late_exit=105 * 60,  # 1 h 45 m late
		)
		self.assertEqual(attendance_allowance.evaluate_rule(day, sc, employee), 2)
		day.custom_late_exit = 30 * 60
		self.assertEqual(attendance_allowance.evaluate_rule(day, sc, employee), 1)
		holiday = frappe._dict(status="Present", working_hours=6.5, custom_worked_on_holiday=1)
		self.assertEqual(attendance_allowance.evaluate_rule(holiday, sc, employee), 1)

	def test_previous_attendance_month(self):
		sc = frappe._dict(custom_attendance_month="Previous Month")
		start, end = attendance_allowance._attendance_period(sc, getdate("2026-08-17"), getdate("2026-09-16"))
		self.assertEqual((str(start), str(end)), (PERIOD_START, PERIOD_END))  # Bhadra pays Shrawan
		same = attendance_allowance._attendance_period(frappe._dict(), getdate(PERIOD_START), getdate(PERIOD_END))
		self.assertEqual(tuple(map(str, same)), (PERIOD_START, PERIOD_END))

	def test_exceptions_take_attendance_allowances_only(self):
		with self.assertRaisesRegex(frappe.ValidationError, "not attendance based"):
			self._employee([{"salary_component": self.mobile, "eligible": 1}])

	# ── the salary slip ─────────────────────────────────────────────────────

	def test_slip_has_fixed_allowance_and_no_tag_line(self):
		employee = self._employee(structure=self.structure)
		slip = frappe.get_doc(
			{
				"doctype": "Salary Slip",
				"employee": employee,
				"start_date": PERIOD_START,
				"posting_date": PERIOD_END,
				"payroll_frequency": "Monthly",
				"company": COMPANY,
			}
		).insert(ignore_permissions=True)
		lines = {d.salary_component: d.amount for d in slip.earnings}
		self.assertEqual(lines.get(self.mobile), 1500)
		self.assertNotIn(self.tea, lines)
		self.assertNotIn(self.meal, lines)

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

	def test_migration_marks_and_tags_what_was_paid_to_all(self):
		from avinashgroup_app.patches import setup_allowance_kinds as patch_

		expense = frappe.db.get_value("Account", {"company": OTHER_COMPANY, "is_group": 0, "root_type": "Expense"})
		ot = frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": "CA Test Old Overtime",
				"salary_component_abbr": "CAOOT",
				"type": "Earning",
				"depends_on_payment_days": 0,
				"custom_is_attendance_driven": 1,
				"custom_condition_type": "Authorised Overtime",
				"custom_unit": "Per Hour",
				"accounts": [{"company": OTHER_COMPANY, "account": expense}],
			}
		).insert(ignore_permissions=True)
		own = self._employee(company=OTHER_COMPANY)
		patch_.add_employee_row(own, ot.name, rate=99)

		patch_.mark_allowances()
		values = frappe.db.get_value(
			"Salary Component", ot.name, ["custom_is_allowance", "custom_allowance_kind", "custom_ot_eligible_only"]
		)
		self.assertEqual(tuple(values), (1, "Per Hour (Overtime)", 1))

		patch_.tag_paid_to_all()
		active = frappe.get_all("Employee", filters={"company": OTHER_COMPANY, "status": "Active"}, pluck="name")
		tagged = frappe.get_all(
			"Employee Attendance Allowance",
			filters={"salary_component": ot.name, "parenttype": "Employee"},
			fields=["parent", "rate"],
		)
		self.assertEqual({t.parent for t in tagged}, set(active))
		self.assertEqual(next(t.rate for t in tagged if t.parent == own), 99)
