"""Tests for Company Allowance (payroll/company_allowance.py and its readers).

Covers:
- who is paid an attendance allowance: listed-only vs all, Eligible unticked,
  OT-eligible-only, the employee's own rate over the company default
- the rule is the employee's company's: another company's employee counts 0
- the meal rule's numbers come off the Company Allowance
- Fixed Monthly and % of Initial Basic rows on the salary slip: prorated like a
  structure row, not Additional Salary (so HRMS projects them for tax), and
  dropped when the employee loses the allowance
- the payroll journal posts each section to its own account, and refuses an
  employee whose Department has no section
- the record's own checks: double payment through a structure, prorating an
  attendance allowance, accounts of another company

Everything is built inside one transaction (own components, Company Allowances,
employees, structure) and rolled back by FrappeTestCase. The attendance count,
the Additional Salary writer and the commit are replaced in the engine test, so
it needs no Attendance on the site.

Run like the shift rotation suite (docs/shift-rotation.md, "Tests"), with
"avinashgroup_app.payroll.test_company_allowance" and site avinas1.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from avinashgroup_app.payroll import attendance_allowance
from avinashgroup_app.payroll.company_allowance import company_allowance_doc, get_company_allowance

COMPANY = "Nepal Gas Udhyog Pvt. Ltd."
OTHER_COMPANY = "Nepal Gas Udhyog (Gandaki) Pvt. Ltd."
ADMIN_DEPT = "Finance/ Accounts - NGI"
MARKETING_DEPT = "Sales/ Marketing - NGI"
PLANT_DEPT = "Plant/ Maintenance - NGI"
PERIOD_START, PERIOD_END = "2026-07-17", "2026-08-16"  # Shrawan 2083
OTHER = ("547110 - Other Allowance - O/O - NGI", "547111 - Other Allowance - S/D - NGI", "547112 - Other Allowance - F/P - NGI")
MEAL = ("547130 - Meal Allowance - O/O - NGI", "547131 - Meal Allowance - S/D - NGI", "547132 - Meal Allowance - F/P - NGI")


class TestCompanyAllowance(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.tea = cls._component("CA Test Tea", "CATEA", prorate=0)
		cls.meal = cls._component("CA Test Meal", "CAMEAL", prorate=0)
		cls.mobile = cls._component("CA Test Mobile", "CAMOB", prorate=1)
		cls.hra = cls._component("CA Test HRA", "CAHRA", prorate=1)

		cls._allowance(cls.tea, is_attendance_based=1, based_on="Status = Present", default_rate=235)
		cls._allowance(
			cls.meal,
			accounts=MEAL,
			is_attendance_based=1,
			based_on="Meal Entitlement",
			ot_eligible_only=1,
			default_rate=75,
			time_offset_hours=1.5,
			holiday_hours_one_meal=6,
			holiday_hours_two_meals=8,
			max_per_day=2,
		)
		cls._allowance(cls.mobile, calculation="Fixed Monthly", default_rate=1500)
		cls._allowance(cls.hra, calculation="% of Initial Basic", default_rate=25)
		cls.structure = cls._structure()

	@classmethod
	def _component(cls, name, abbr, prorate):
		doc = frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": name,
				"salary_component_abbr": abbr,
				"type": "Earning",
				"depends_on_payment_days": prorate,
				"is_tax_applicable": 1,
			}
		).insert(ignore_permissions=True)
		return doc.name

	@classmethod
	def _allowance(cls, component, accounts=OTHER, company=COMPANY, **values):
		"""Add one row to the company's Company Allowance and save it."""
		doc = company_allowance_doc(company)
		row = doc.append(
			"allowances",
			{
				"salary_component": component,
				"account_admin": accounts[0],
				"account_marketing": accounts[1],
				"account_plant": accounts[2],
				**values,
			},
		)
		doc.save(ignore_permissions=True)
		if hasattr(frappe.local, "_agp_company_allowance"):
			delattr(frappe.local, "_agp_company_allowance")
		return row

	@classmethod
	def _structure(cls):
		doc = frappe.get_doc(
			{
				"doctype": "Salary Structure",
				"name": "CA Test Structure",
				"company": COMPANY,
				"currency": "NPR",
				"payroll_frequency": "Monthly",
				"is_active": "Yes",
				"earnings": [
					{
						"salary_component": "Basic",
						"amount_based_on_formula": 1,
						"formula": "base",
						"depends_on_payment_days": 1,
					}
				],
			}
		).insert(ignore_permissions=True)
		doc.submit()
		return doc.name

	def setUp(self):
		frappe.clear_messages()
		for key in ("_agp_company_allowance", "_agp_payroll_section"):
			if hasattr(frappe.local, key):
				delattr(frappe.local, key)

	def _employee(self, rows=(), department=ADMIN_DEPT, company=COMPANY, **values):
		emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "Company Allowance Test",
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
		return emp.name

	# ── attendance allowances ────────────────────────────────────────────────

	def _run_engine(self, employees, qty=10):
		made = []

		def capture(employee, salary_component, allowance, amount, **kwargs):
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

	def test_only_tagged_employees_are_paid(self):
		listed = self._employee([{"salary_component": self.tea, "eligible": 1}])
		unlisted = self._employee()
		paid = self._run_engine([listed, unlisted])
		self.assertEqual(paid, {(listed, self.tea): 2350})

	def test_own_rate_beats_default_and_unticked_is_not_paid(self):
		new_staff = self._employee([{"salary_component": self.tea, "eligible": 1, "rate": 40}])
		stopped = self._employee([{"salary_component": self.tea, "eligible": 0}])
		paid = self._run_engine([new_staff, stopped])
		self.assertEqual(paid, {(new_staff, self.tea): 400})

	def test_blank_rate_uses_company_default(self):
		"""Tea: OLD staff are tagged with no rate and get the company's 235; NEW
		staff carry 40 on their row; staff on none have the row unticked."""
		old = self._employee([{"salary_component": self.tea, "eligible": 1}])
		new = self._employee([{"salary_component": self.tea, "eligible": 1, "rate": 40}])
		none = self._employee([{"salary_component": self.tea, "eligible": 0}])
		paid = self._run_engine([old, new, none])
		self.assertEqual(paid, {(old, self.tea): 2350, (new, self.tea): 400})

	def test_meal_only_for_ot_eligible(self):
		rows = [{"salary_component": self.meal, "eligible": 1}]
		eligible = self._employee(rows, custom_ot_eligibility=1)
		not_eligible = self._employee(rows, custom_ot_eligibility=0)
		paid = self._run_engine([eligible, not_eligible], qty=4)
		self.assertEqual(paid, {(eligible, self.meal): 300})

	def test_meal_rule_reads_company_allowance(self):
		employee = self._employee([{"salary_component": self.meal, "eligible": 1}])
		sc = frappe.get_cached_doc("Salary Component", self.meal)
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

	def test_other_company_has_no_rule(self):
		elsewhere = self._employee(company=OTHER_COMPANY)
		sc = frappe.get_cached_doc("Salary Component", self.tea)
		day = frappe._dict(status="Present", working_hours=8, custom_worked_on_holiday=0)
		self.assertEqual(attendance_allowance.evaluate_rule(day, sc, elsewhere), 0)

	# ── fixed allowances on the slip ─────────────────────────────────────────

	def _slip(self, employee):
		joined = str(frappe.db.get_value("Employee", employee, "date_of_joining"))
		frappe.get_doc(
			{
				"doctype": "Salary Structure Assignment",
				"employee": employee,
				"salary_structure": self.structure,
				"company": COMPANY,
				"currency": "NPR",
				"from_date": max(joined, PERIOD_START),
				"base": 30000,
				"income_tax_slab": f"Nepal 83/84 - {frappe.db.get_value('Company', COMPANY, 'abbr')}",
			}
		).insert(ignore_permissions=True).submit()
		slip = frappe.get_doc(
			{
				"doctype": "Salary Slip",
				"employee": employee,
				"start_date": PERIOD_START,
				"posting_date": PERIOD_END,
				"payroll_frequency": "Monthly",
				"company": COMPANY,
			}
		)
		slip.insert(ignore_permissions=True)
		return slip

	@staticmethod
	def _row(slip, component):
		return next((d for d in slip.earnings if d.salary_component == component), None)

	def test_fixed_allowances_on_slip(self):
		employee = self._employee(
			[{"salary_component": self.mobile, "eligible": 1}, {"salary_component": self.hra, "eligible": 1}],
			custom_initial_basic=20000,
			date_of_joining="2026-07-27",  # joins ten days in: the month is prorated
		)
		slip = self._slip(employee)
		self.assertLess(slip.payment_days, slip.total_working_days)

		mobile = self._row(slip, self.mobile)
		self.assertEqual(mobile.default_amount, 1500)
		self.assertFalse(mobile.additional_salary)  # structured, so projected for tax
		self.assertLess(mobile.amount, 1500)
		basic = self._row(slip, "Basic")
		self.assertAlmostEqual(mobile.amount / 1500, basic.amount / basic.default_amount, places=2)

		hra = self._row(slip, self.hra)
		self.assertEqual(hra.default_amount, 5000)  # 25% of 20,000

		emp = frappe.get_doc("Employee", employee)
		emp.custom_attendance_allowances = [r for r in emp.custom_attendance_allowances if r.salary_component != self.mobile]
		emp.save(ignore_permissions=True)
		frappe.clear_document_cache("Employee", employee)
		slip.reload()
		slip.save(ignore_permissions=True)
		self.assertIsNone(self._row(slip, self.mobile))
		self.assertIsNotNone(self._row(slip, self.hra))

	def test_fixed_allowance_is_projected_for_tax(self):
		"""HRMS projects structured rows over the rest of the year; an Additional
		Salary would count once. A year of 1,500 must show, not one month."""
		with_mobile = self._slip(self._employee([{"salary_component": self.mobile, "eligible": 1}]))
		without = self._slip(self._employee())
		self.assertGreaterEqual(with_mobile.annual_taxable_amount - without.annual_taxable_amount, 1500 * 11)

	def test_unlisted_employee_gets_no_fixed_allowance(self):
		slip = self._slip(self._employee())
		self.assertIsNone(self._row(slip, self.mobile))
		self.assertIsNone(self._row(slip, self.hra))

	# ── the payroll journal ──────────────────────────────────────────────────

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
		with self.assertRaises(frappe.ValidationError):
			self._journal_lines([employee])

	# ── the record's own checks ──────────────────────────────────────────────

	def test_attendance_allowance_must_not_prorate(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Depends on Payment Days"):
			self._allowance(self.mobile, company=OTHER_COMPANY, accounts=(None, None, None), is_attendance_based=1, based_on="Status = Present")

	def test_fixed_allowance_already_in_structure_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "already in salary structure"):
			self._allowance("Basic", calculation="Fixed Monthly", default_rate=1)

	def test_account_of_another_company_is_refused(self):
		gandaki = frappe.db.get_value("Account", {"company": OTHER_COMPANY, "is_group": 0, "root_type": "Expense"})
		fuel = self._component("CA Test Fuel", "CAFUEL", prorate=1)
		with self.assertRaisesRegex(frappe.ValidationError, "belongs to"):
			self._allowance(fuel, accounts=(gandaki, None, None), calculation="Fixed Monthly", default_rate=1)

	def test_same_allowance_twice_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "listed twice"):
			self._allowance(self.tea, is_attendance_based=1, based_on="Status = Present")

	def test_one_record_per_company(self):
		doc = frappe.get_doc("Company Allowance", COMPANY)
		self.assertEqual(
			{r.salary_component for r in doc.allowances} >= {self.tea, self.meal, self.mobile, self.hra}, True
		)

	def test_new_allowance_name_creates_its_component(self):
		"""HR types a new name in a row; the Salary Component is made on save."""
		self.assertFalse(frappe.db.exists("Salary Component", "CA Test Mobile Recharge"))
		self._allowance("CA Test Mobile Recharge", calculation="Fixed Monthly", default_rate=500)
		sc = frappe.get_doc("Salary Component", "CA Test Mobile Recharge")
		self.assertEqual((sc.type, sc.depends_on_payment_days), ("Earning", 1))
		self.assertEqual(sc.salary_component_abbr, "CTMR")
		self.assertEqual([(a.company, a.account) for a in sc.accounts], [(COMPANY, OTHER[0])])

		self._allowance("CA Test Night Tea", is_attendance_based=1, based_on="Status = Present", default_rate=50)
		self.assertEqual(frappe.db.get_value("Salary Component", "CA Test Night Tea", "depends_on_payment_days"), 0)

	def test_migration_tags_everyone_who_was_paid_untagged(self):
		"""An attendance component the old engine paid to all (overtime) becomes
		a tag on every active employee of the company; one already tagged keeps
		their own row."""
		from avinashgroup_app.patches import setup_company_allowance as patch_

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
				"accounts": [{"company": OTHER_COMPANY, "account": frappe.db.get_value(
					"Account", {"company": OTHER_COMPANY, "is_group": 0, "root_type": "Expense"})}],
			}
		).insert(ignore_permissions=True)
		own = self._employee(company=OTHER_COMPANY)
		patch_.add_employee_row(own, ot.name, rate=99)

		_created, paid_to_all = patch_.create_company_allowances()
		self.assertIn((OTHER_COMPANY, ot.name), paid_to_all)
		patch_.tag_everyone(paid_to_all)

		active = frappe.get_all("Employee", filters={"company": OTHER_COMPANY, "status": "Active"}, pluck="name")
		tagged = frappe.get_all(
			"Employee Attendance Allowance",
			filters={"salary_component": ot.name, "parenttype": "Employee"},
			fields=["parent", "rate"],
		)
		self.assertEqual({t.parent for t in tagged}, set(active))
		self.assertEqual(next(t.rate for t in tagged if t.parent == own), 99)
		row = get_company_allowance(OTHER_COMPANY, ot.name)
		self.assertEqual((row.based_on, row.ot_eligible_only), ("Authorised Overtime", 1))

	def test_saving_sets_the_component_account(self):
		account = frappe.db.get_value("Salary Component Account", {"parent": self.mobile, "company": COMPANY}, "account")
		self.assertEqual(account, OTHER[0])
		self.assertTrue(get_company_allowance(COMPANY, self.mobile))
