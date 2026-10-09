"""Put a company's payroll on the system from its own monthly salary sheet.

Every company in the group already runs payroll — in Excel. The sheet is the
only record of who is paid what: which allowances each person gets, their grade,
whether they are in the SSF. So onboarding a company means reading its sheet,
not retyping it.

The four sheets use two pay models:

  Initial-basic (NGI, NGN) — one template. Basic Salary, plus HRA as a share of
      a separate Initial Basic, flat gas and education allowances for those
      flagged YES, dearness and other allowances per person, tea at the
      company rate (OLD), 40 for NEW staff or none, SSF 20% added and 31%
      deducted.

  Grade-scale (NGG, NGK) — the government scale. Basic plus increments plus
      grade is the salary scale; SSF is 20% / 31% of that scale; then a fixed
      allowance, dearness, other allowance and fuel per person. No HRA, gas or
      education, and no employee codes on the sheet — only names.

A profile per company says which model, where each column is, and the company's
own rates (NGN pays HRA at 27% where NGI pays 25%). `setup_company` builds the
components and the salary structure; `import_sheet` matches the sheet's people to
Employees, writes their pay inputs, and assigns the structure from the start of
the fiscal year. Both are safe to run again.

Pay lives on the Salary Structure Assignment, not the Employee: Basic is its
base, Initial Basic and SSF Applicable are its fields, and every allowance a
person gets is a row on its Allowances table, with their own amount (dearness, other,
fuel, fixed, maintenance) or blank for the company's rate (gas, education, HRA
%, tea, meal), which is the Default Rate on the component's Accounts row for
the company. The structure holds only what everyone shares: Basic, SSF
Addition, SSF, income tax and the attendance tags (tea, meal, overtime, late
fine). So a rate change is one edit, a new allowance is a component and some
rows, and a new starter is one Employee. See docs/allowances.md.

    bench --site <site> execute avinashgroup_app.payroll.onboarding.onboard \\
        --kwargs "{'key': 'NGN', 'path': '/path/to/NGN.xlsx'}"
"""

import difflib
import re

import frappe
from frappe import _
from frappe.utils import flt

from avinashgroup_app.payroll.allowance import sibling_account

FISCAL_YEAR = "83/84"

INITIAL_BASIC = "initial_basic"
GRADE_SCALE = "grade_scale"

PROFILES = {
	"NGI": {
		"company": "Nepal Gas Udhyog Pvt. Ltd.",
		"model": INITIAL_BASIC,
		"sheet": "Falgun salary",
		"first_row": 5,
		"match": "code",
		"cols": {
			"code": "B", "name": "C", "department": "D", "designation": "F", "attendance": "I",
			"initial_basic": "M", "basic": "N", "hra": "U", "dearness": "V", "other": "W",
			"fuel": "X", "gas": "Y", "edu": "Z", "tea": "AE", "ssf": "AJ",
		},
		"rates": {"hra": 0.25, "gas": 1690, "edu": 2780, "tea_old": 235, "tea_new": 40, "meal": 75},
	},
	"NGN": {
		"company": "Nepal Gas Udhyog (Narayani) Pvt. Ltd.",
		"model": INITIAL_BASIC,
		"sheet": "Falgun salary",
		"first_row": 5,
		"match": "code",
		"cols": {
			"code": "B", "name": "C", "department": "D", "designation": "E", "attendance": "H",
			"initial_basic": "L", "basic": "M", "hra": "T", "dearness": "U", "other": "V",
			"fuel": "W", "gas": "X", "edu": "Y", "tea": "AD", "ssf": "AH",
		},
		"rates": {"hra": 0.27, "gas": 1690.27, "edu": 1250, "tea_old": 265, "tea_new": 40, "meal": 75},
	},
	"NGG": {
		"company": "Nepal Gas Udhyog (Gandaki) Pvt. Ltd.",
		"model": GRADE_SCALE,
		"sheet": "Falgun salary",
		"first_row": 6,
		"match": "name",
		"cols": {
			"name": "B", "designation": "F", "basic_total": "K", "grade": "O",
			"fixed": "R", "dearness": ("S", "T"), "other": "V", "fuel": "W", "ssf": "AF",
		},
		# 10 holiday OT hours earned 200 of meal on the Falgun sheet: two meals.
		"rates": {"meal": 100},
	},
	"NGK": {
		"company": "Nepal Gas Udhyog (Karnali) Pvt. Ltd.",
		"model": GRADE_SCALE,
		"sheet": "Falgun sal",
		"first_row": 5,
		"match": "name",
		"cols": {
			"name": "B", "designation": "E", "basic_total": "J", "grade": "M",
			"fixed": "P", "dearness": ("Q", "R"), "other": "S", "fuel": "T",
			"maintenance": "U", "ssf": "Y",
		},
		"rates": {},
		# The sheet's Wages tab (labour at 754 a day) is not imported: labour is
		# paid in cash day to day, outside payroll (decided 2026-10-08).
	},
}


#: The payroll component catalogue: everything a structure or the attendance
#: engine can put on a slip.
#:
#: `payment_days` matters more than it looks. It is a fetch-from field on the
#: structure row, so a row that sets it to 0 is silently refilled from the
#: component — which is why the two SSF components must carry 0 themselves.
#: Their formulas already read Basic, which is prorated, and HRMS refuses a row
#: that would prorate the same amount twice.
#:
#: (name, abbr, type, payment_days, flags)
COMPONENTS = (
	("Basic", "B", "Earning", 1, {}),
	("Dearness Allowance", "DA", "Earning", 1, {"custom_is_allowance": 1, "custom_allowance_kind": "Fixed per Person"}),
	("Other Allowance", "OA", "Earning", 1, {"custom_is_allowance": 1, "custom_allowance_kind": "Fixed per Person"}),
	("Fixed Allowance", "FA", "Earning", 1, {"custom_is_allowance": 1, "custom_allowance_kind": "Fixed per Person"}),
	("Fuel Allowance", "FUEL", "Earning", 1, {"custom_is_allowance": 1, "custom_allowance_kind": "Fixed per Person"}),
	("Maintenance Allowance", "MNT", "Earning", 1, {"custom_is_allowance": 1, "custom_allowance_kind": "Fixed per Person"}),
	("House Rent Allowance", "HRA", "Earning", 1, {"custom_is_allowance": 1, "custom_allowance_kind": "% of Initial Basic"}),
	("Gas Allowance", "GAS", "Earning", 1, {"custom_is_allowance": 1, "custom_allowance_kind": "Fixed Company Rate"}),
	("Education Allowance", "EDU", "Earning", 1, {"custom_is_allowance": 1, "custom_allowance_kind": "Fixed Company Rate"}),
	("SSF Addition", "SSFA", "Earning", 0, {}),
	# Paid month by month on Payroll Adjustment when there was loading work.
	("Load/Unload Allowance", "LU", "Earning", 1, {"custom_is_allowance": 1, "custom_allowance_kind": "Entered by Hand"}),
	("Dashain Bonus", "DB", "Earning", 0, {"custom_is_allowance": 1, "custom_allowance_kind": "Yearly"}),
	("Salary Arrears", "ARR", "Earning", 0, {}),
	# Worked out from attendance each month by `payroll.attendance_allowance`.
	("Tea & Conveyance", "TEA", "Earning", 0, {
		"custom_is_allowance": 1, "custom_allowance_kind": "Per Day Present",
		"custom_pay_on_holiday": "Do Not Pay",
		"custom_is_attendance_driven": 1, "custom_condition_type": "Status = Present",
		"custom_unit": "Per Day", "custom_summary_group": "Tea", "custom_half_day_counts": "Full Day",
	}),
	("Meal", "MEAL", "Earning", 0, {
		"custom_is_allowance": 1, "custom_allowance_kind": "Per Meal",
		"custom_is_attendance_driven": 1, "custom_condition_type": "Meal Entitlement",
		"custom_unit": "Per Day", "custom_time_offset_hours": 1.5, "custom_summary_group": "Meal",
		"custom_max_per_day": 2, "custom_ot_eligible_only": 1,
	}),
	("Overtime", "OT", "Earning", 0, {
		"custom_is_allowance": 1, "custom_allowance_kind": "Per Hour (Overtime)", "custom_ot_eligible_only": 1,
		"custom_is_attendance_driven": 1, "custom_condition_type": "Authorised Overtime",
		"custom_unit": "Per Hour", "custom_rate_basis": "Hourly Basic × Multiplier",
		"custom_rate_multiplier": 1.5, "custom_summary_group": "Overtime",
	}),
	("SSF", "SSF", "Deduction", 0, {"exempted_from_income_tax": 1}),
	("Income Tax", "TAX", "Deduction", 0, {"variable_based_on_taxable_salary": 1}),
	("Late Fine", "LF", "Deduction", 0, {
		"custom_is_attendance_driven": 1, "custom_condition_type": "Late Time",
		"custom_unit": "Per Hour", "custom_rate_basis": "Hourly Basic × Multiplier",
		"custom_rate_multiplier": 1, "custom_summary_group": "Late Fine",
	}),
	("Salary Advance", "ADV", "Deduction", 0, {}),
)


# ───────────────────────────────────────────────────────────── entry point ──


def onboard(key, path):
	"""Set up the company and import its sheet. Returns what happened."""
	setup_company(key)
	result = import_sheet(key, path)
	frappe.db.commit()
	return result


# ────────────────────────────────────────────────────────────────── setup ──


def structure_name(key):
	return f"{key} Staff {FISCAL_YEAR}"


def structure_rows(profile):
	"""(component, formula, depends_on_payment_days) every employee of the company shares.

	Allowances are not here: they are rows on each employee (Employee →
	Allowances), added to the slip by payroll/salary_slip.py. SSF reads Basic,
	which is prorated already, so the two SSF rows are not payment-days rows.
	"""
	r = profile["rates"]
	earnings = [
		("Basic", "base", 1),
		("SSF Addition", "B * 0.20 if custom_ssf_applicable else 0", 0),
	]
	# Tags, not amounts: the allowance engine pays these from attendance to
	# whoever's structure carries them (payroll/allowance.py blanks the row).
	if r.get("tea_old"):
		earnings.append(("Tea & Conveyance", "", 0))
	if r.get("meal"):
		earnings.append(("Meal", "", 0))
	earnings.append(("Overtime", "", 0))

	deductions = [("SSF", "B * 0.31 if custom_ssf_applicable else 0", 0), ("Late Fine", "", 0)]
	return earnings, deductions


def setup_company(key):
	profile = PROFILES[key]
	company = profile["company"]

	ensure_payable_account(company)
	ensure_components()
	ensure_company_rates(key)

	name = structure_name(key)
	if frappe.db.exists("Salary Structure", {"name": name, "docstatus": 1}):
		# Assignments hang off a submitted structure, so it is never rebuilt
		# under them; a changed rate is a new structure for the next year.
		return name

	earnings, deductions = structure_rows(profile)
	doc = frappe.get_doc("Salary Structure", name) if frappe.db.exists("Salary Structure", name) else None
	if not doc:
		doc = frappe.new_doc("Salary Structure")
		doc.name = name
	doc.update(
		{
			"company": company,
			"currency": "NPR",
			"payroll_frequency": "Monthly",
			"is_active": "Yes",
			"payment_account": frappe.db.get_value("Company", company, "default_payroll_payable_account"),
			"earnings": [],
			"deductions": [],
		}
	)
	for component, formula, prorate in earnings:
		doc.append("earnings", _row(component, formula, prorate))
	for component, formula, prorate in deductions:
		doc.append("deductions", _row(component, formula, prorate))
	doc.append(
		"deductions",
		{"salary_component": "Income Tax", "variable_based_on_taxable_salary": 1, "depends_on_payment_days": 0},
	)
	doc.flags.ignore_permissions = True
	doc.save()
	doc.submit()
	return doc.name


def ensure_payable_account(company):
	"""Every company's chart has 347301 Salary Payable; Karnali's was never set."""
	if frappe.db.get_value("Company", company, "default_payroll_payable_account"):
		return
	abbr = frappe.db.get_value("Company", company, "abbr")
	account = f"347301 - Salary Payable - {abbr}"
	if frappe.db.exists("Account", account):
		frappe.db.set_value("Company", company, "default_payroll_payable_account", account)


def _row(component, formula, prorate):
	flags = frappe.db.get_value(
		"Salary Component", component, ["is_tax_applicable", "exempted_from_income_tax"], as_dict=True
	)
	return {
		"salary_component": component,
		"amount_based_on_formula": 1,
		"formula": formula,
		"depends_on_payment_days": prorate,
		# The slip reads these off the row, not the component.
		"is_tax_applicable": flags.is_tax_applicable,
		"exempted_from_income_tax": flags.exempted_from_income_tax,
	}


def ensure_components():
	"""Create any missing component, and keep the payment-days flag true.

	Only `depends_on_payment_days` is corrected on a component that already
	exists — everything else a company may have tuned by hand is left alone.
	"""
	for name, abbr, kind, payment_days, flags in COMPONENTS:
		if frappe.db.exists("Salary Component", name):
			if frappe.db.get_value("Salary Component", name, "depends_on_payment_days") != payment_days:
				frappe.db.set_value("Salary Component", name, "depends_on_payment_days", payment_days)
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": name,
				"salary_component_abbr": abbr,
				"type": kind,
				"depends_on_payment_days": payment_days,
				"is_tax_applicable": 1 if kind == "Earning" else 0,
				"round_to_the_nearest_integer": 0,
			}
		)
		doc.update(flags)
		doc.flags.ignore_permissions = True
		doc.insert()
	frappe.clear_cache(doctype="Salary Component")


#: The sheet's company-wide rates → the allowance they price.
RATE_COMPONENTS = (
	("tea_old", "Tea & Conveyance", 1),
	("meal", "Meal", 1),
	("gas", "Gas Allowance", 1),
	("edu", "Education Allowance", 1),
	("hra", "House Rent Allowance", 100),  # 0.25 → 25 (%)
)


def ensure_company_rates(key):
	"""The company's rates as Default Rate on each component's Accounts row.

	The row is created without an account if the accountant has not mapped one
	yet (map_component_accounts fills it in later). A rate already typed is left
	alone.
	"""
	profile = PROFILES[key]
	company, r = profile["company"], profile["rates"]
	for rate_key, component, factor in RATE_COMPONENTS:
		rate = flt(r.get(rate_key)) * factor
		if not rate or not frappe.db.exists("Salary Component", component):
			continue
		doc = frappe.get_doc("Salary Component", component)
		row = next((a for a in doc.accounts if a.company == company), None)
		if row and flt(row.custom_default_rate):
			continue
		if not row:
			row = doc.append("accounts", {"company": company})
		row.custom_default_rate = rate
		doc.flags.ignore_permissions = True
		doc.save()


# ───────────────────────────────────────────────────────────────── import ──


def import_sheet(key, path):
	import openpyxl

	profile = PROFILES[key]
	company = profile["company"]
	sheet = openpyxl.load_workbook(path, data_only=True)[profile["sheet"]]
	matcher = EmployeeMatcher(key, company)

	matched, unmatched, assigned, notes = [], [], [], []
	for row in _sheet_rows(sheet, profile):
		employee = matcher.find(row)
		if not employee:
			unmatched.append(row["name"])
			continue
		matched.append(employee)
		set_department(employee, company, row.get("department"))

		values, base, note, allowances = employee_values(key, profile, row)
		if note:
			notes.append(f"{row['name']}: {note}")
		if base and assign(employee, key, company, base, values=values, allowances=allowances):
			assigned.append(employee)

	return {
		"company": company,
		"structure": structure_name(key),
		"employees_matched": len(matched),
		"assignments_created": len(assigned),
		"unmatched": unmatched,
		"notes": notes,
	}


def set_department(employee, company, sheet_department):
	"""Give the employee the sheet's department when they have none.

	The department decides the payroll section (O/O, S/D, F/P) and so the
	journal's account; without it the payroll journal stops. The NGI sheet
	spells one "Genaral Management", so the match tolerates a near spelling
	within the company's own departments. A department already set is kept.
	"""
	if not sheet_department or frappe.db.get_value("Employee", employee, "department"):
		return
	departments = frappe.get_all("Department", filters={"company": company, "is_group": 0}, pluck="name")
	by_name = {EmployeeMatcher.norm(d.rsplit(" - ", 1)[0]): d for d in departments}
	key = EmployeeMatcher.norm(str(sheet_department))
	match = by_name.get(key) or next(
		iter(by_name[k] for k in difflib.get_close_matches(key, list(by_name), n=1, cutoff=0.85)), None
	)
	if match:
		frappe.db.set_value("Employee", employee, "department", match, update_modified=False)


def _sheet_rows(sheet, profile):
	from openpyxl.utils import column_index_from_string

	def cell(r, col):
		if isinstance(col, tuple):
			return sum(flt(cell(r, c)) for c in col)
		return sheet.cell(r, column_index_from_string(col)).value

	cols = profile["cols"]
	for r in range(profile["first_row"], sheet.max_row + 1):
		name = cell(r, cols["name"])
		if not isinstance(name, str) or not name.strip():
			continue
		if profile["match"] == "code":
			code = cell(r, cols["code"])
			if not isinstance(code, str) or not re.search(r"\d", code):
				continue
		elif not isinstance(sheet.cell(r, 1).value, (int, float)):
			continue
		yield {field: cell(r, col) for field, col in cols.items()} | {"name": name.strip(), "_row": r}


#: Sheet column → the allowance it is the person's own amount of.
PER_PERSON = (
	("dearness", "Dearness Allowance"),
	("other", "Other Allowance"),
	("fuel", "Fuel Allowance"),
	("fixed", "Fixed Allowance"),
	("maintenance", "Maintenance Allowance"),
)
#: Sheet column whose amount means "gets it at the company rate".
AT_COMPANY_RATE = (
	("hra", "House Rent Allowance"),
	("gas", "Gas Allowance"),
	("edu", "Education Allowance"),
)


def employee_values(key, profile, row):
	"""The assignment fields this person's row decides, their basic, a note, and
	their allowances as {allowance: amount}: a figure is their own amount, None
	the company rate, 0 an inactive row (on no tea)."""
	num = lambda v: flt(v) if isinstance(v, (int, float)) else 0.0
	note = None
	cols = profile["cols"]
	values = {"custom_ssf_applicable": 1 if num(row.get("ssf")) else 0}
	allowances = {}

	if profile["model"] == INITIAL_BASIC:
		base = num(row.get("basic"))
		values["custom_initial_basic"] = num(row.get("initial_basic"))
		tea = tea_exception(profile, num(row.get("tea")), num(row.get("attendance")))
		if tea is not None:
			allowances["Tea & Conveyance"] = tea
	else:
		# Basic + increments + grade, taken from its parts: the sheet's own scale
		# column is prorated for anyone who joined mid-month.
		base = num(row.get("basic_total")) + num(row.get("grade"))

	for col, allowance in PER_PERSON:
		if col in cols and num(row.get(col)):
			allowances[allowance] = num(row.get(col))
	for col, allowance in AT_COMPANY_RATE:
		# The sheet shows the outcome, not the flag: an amount means YES.
		if col in cols and num(row.get(col)):
			allowances[allowance] = None

	if not base:
		note = _("no basic on the sheet — not assigned a salary")
	return values, base, note, allowances


def tea_exception(profile, tea, attendance):
	"""Tea paid at the company rate (OLD) needs nothing: the structure tags it.
	NEW staff get their own rate, staff on none an unticked row (0). None when
	there is nothing to record, or the sheet cannot say (no attendance)."""
	r = profile["rates"]
	if not attendance or "tea_old" not in r:
		return None
	if not tea:
		return 0
	if abs(tea / attendance - r["tea_new"]) < 1:
		return r["tea_new"]
	return None


def assign(employee, key, company, base, structure=None, values=None, allowances=None):
	"""Assign the company structure from the fiscal year's first day, once.

	`values` are the assignment's own fields (Initial Basic, SSF Applicable);
	`allowances` is {allowance: amount}: a figure is their own amount, None the
	company rate (blank), 0 an inactive row, so the record says "not paid", not
	"unknown"."""
	fy_start = frappe.db.get_value("Fiscal Year", FISCAL_YEAR, "year_start_date")
	if frappe.db.exists(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1, "from_date": [">=", fy_start]},
	):
		return False

	doc = frappe.new_doc("Salary Structure Assignment")
	doc.update(
		{
			"employee": employee,
			"salary_structure": structure or structure_name(key),
			"from_date": fy_start,
			"company": company,
			"currency": "NPR",
			"base": base,
			"variable": 0,
			# The Payroll Entry finds its employees by this account, so an
			# assignment written without it is silently left out of every run.
			"payroll_payable_account": frappe.db.get_value(
				"Company", company, "default_payroll_payable_account"
			),
			"income_tax_slab": frappe.db.get_value(
				"Income Tax Slab", {"company": company, "docstatus": 1, "disabled": 0}, "name",
				order_by="effective_from desc",
			),
		}
	)
	doc.update(values or {})
	for allowance, amount in (allowances or {}).items():
		doc.append(
			"custom_allowances",
			{"allowance": allowance, "amount": flt(amount) if amount else 0, "active": 0 if amount == 0 else 1},
		)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return True


class EmployeeMatcher:
	"""Sheet row → Employee: by name, with the sheet's code as a cross-check.

	The code alone is not enough. The NGN sheet's codes drift one place from
	the ERP IDs from about NGN0035 (sheet NGN0045 "Parmeshwor Shah" is
	NGN-EMP-00044; NGN-EMP-00045 is Bal Krishna Neupane), and trusting the code
	put fifteen people on a neighbour's pay in October 2026. So a code is taken
	only when the employee it points at has the row's name; otherwise the name
	decides.

	Names on the grade-scale sheets carry titles and stray spacing ("Mr Jiwan
	Chhatkuli", "Rupak Chaudhary "), so names are compared stripped of titles
	and anything but letters, and a near spelling is accepted only when it is
	the single close candidate.
	"""

	#: How alike two normalised names must be to count as the same person
	#: ("Bishnu Prasad Upadhayay" / "Upadhyay" pass, "Ratna" / "Raju Kumar
	#: Shrestha" do not).
	SAME_NAME_RATIO = 0.88

	TITLES = re.compile(r"^(mr|mrs|ms|miss|dr)\.?\s+", re.I)

	def __init__(self, key, company):
		self.key = key
		self.by_name = {}
		for e in frappe.get_all(
			"Employee", filters={"company": company, "status": "Active"}, fields=["name", "employee_name"]
		):
			self.by_name.setdefault(self.norm(e.employee_name), []).append(e.name)

	@classmethod
	def norm(cls, name):
		return re.sub(r"[^a-z]", "", cls.TITLES.sub("", (name or "").strip()).lower())

	def find(self, row):
		key = self.norm(row["name"])
		code = row.get("code")
		digits = "".join(ch for ch in str(code or "") if ch.isdigit())
		if digits:
			candidate = f"{self.key}-EMP-{int(digits):05d}"
			name = frappe.db.get_value("Employee", candidate, "employee_name")
			if name and self.same_name(key, self.norm(name)):
				return candidate

		exact = self.by_name.get(key)
		if exact and len(exact) == 1:
			return exact[0]

		close = difflib.get_close_matches(key, list(self.by_name), n=2, cutoff=self.SAME_NAME_RATIO)
		if len(close) == 1 and len(self.by_name[close[0]]) == 1:
			return self.by_name[close[0]][0]
		return None

	@classmethod
	def same_name(cls, a, b):
		return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= cls.SAME_NAME_RATIO


#: Each sheet's columns for the month's regular salary and the SSF deduction.
SHEET_TOTALS = {"NGI": ("AD", "AJ"), "NGN": ("AC", "AH"), "NGG": ("X", "AF"), "NGK": ("V", "Y")}


def check_against_sheet(key, path, posting_date=None):
	"""Make every matched employee's slip for a full month and compare it with
	the sheet's regular salary and SSF. Read-only: nothing is saved.

	    bench --site <site> execute avinashgroup_app.payroll.onboarding.check_against_sheet \\
	        --kwargs "{'key': 'NGI', 'path': '/path/to/NGI.xlsx'}"

	posting_date: any day of the BS month to try (default: the first month of
	the fiscal year). Prints and returns the people who differ.
	"""
	from unittest.mock import patch

	import openpyxl
	from openpyxl.utils import column_index_from_string

	profile = PROFILES[key]
	company = profile["company"]
	posting_date = posting_date or frappe.db.get_value("Fiscal Year", FISCAL_YEAR, "year_start_date")
	total_col, ssf_col = SHEET_TOTALS[key]
	sheet = openpyxl.load_workbook(path, data_only=True)[profile["sheet"]]
	matcher = EmployeeMatcher(key, company)
	matched, differ, not_found = 0, [], []
	frappe.db.savepoint("check_against_sheet")
	try:
		with patch.object(frappe.db, "commit"):
			for row in _sheet_rows(sheet, profile):
				employee = matcher.find(row)
				if not employee:
					not_found.append(row["name"])
					continue
				if not frappe.db.exists(
					"Salary Structure Assignment", {"employee": employee, "docstatus": 1}
				):
					continue
				slip = frappe.get_doc(
					{
						"doctype": "Salary Slip",
						"employee": employee,
						"posting_date": posting_date,
						"start_date": posting_date,
						"payroll_frequency": "Monthly",
						"company": company,
					}
				).insert(ignore_permissions=True)
				gross = sum(flt(d.amount) for d in slip.earnings)
				ssf = sum(flt(d.amount) for d in slip.deductions if d.salary_component == "SSF")
				want = flt(sheet.cell(row["_row"], column_index_from_string(total_col)).value)
				want_ssf = flt(sheet.cell(row["_row"], column_index_from_string(ssf_col)).value)
				if abs(gross - want) < 1 and abs(ssf - want_ssf) < 1:
					matched += 1
				else:
					differ.append((row["name"], employee, round(want, 2), round(gross, 2), slip.payment_days, slip.total_working_days))
	finally:
		frappe.db.rollback(save_point="check_against_sheet")
	print(f"{key}: {matched} match the sheet, {len(differ)} differ, {len(not_found)} not found as employees")
	for name, employee, want, got, days, total in differ:
		print(f"  {name} ({employee}): sheet {want}, slip {got}, days {days}/{total}")
	for name in not_found:
		print(f"  not found: {name}")
	return {"matched": matched, "differ": differ, "not_found": not_found}


# ─────────────────────────────────────────────────────────────── accounts ──

#: A PROPOSAL for the accountant, not applied by `onboard`. Every company's chart
#: carries the same codes, so one mapping serves all seven. Proven end to end on
#: nepalgas (inside a rolled-back transaction): 87 NGI slips submitted and the
#: accrual journal balanced, crediting Salary Payable with exactly the net pay.
#:
#: Open question for the accountant: the chart has three salary expense accounts
#: (547101 O/O office, 547102 S/D sales & distribution, 547103 F/P filling
#: plant) but no matching cost centres, and a component maps to one account. So
#: this posts every earning to 547101 until cost centres exist to split it.
PROPOSED_ACCOUNTS = {
	"__earnings__": "547101 - Salary Expenses - O/O",
	"SSF": "347302 - SSF Payable",
	"Additional SSF": "347302 - SSF Payable",
	"Income Tax": "348102 - 11112 TDS-Remuneration Income Tax",
	"Salary Advance": "148003 - Staff Advance",
	# No fines-income account exists; a fine reduces what the salary cost.
	"Late Fine": "547101 - Salary Expenses - O/O",
}


def map_component_accounts(company):
	"""Give every salary component its GL account for one company.

	Without this the payroll journal cannot be written and submitting the
	month's salary slips fails. Run only once the accountant has agreed the
	mapping above. A row with an account is left as it is; a row made earlier
	only to hold the company's rate gets its account.
	"""
	abbr = frappe.db.get_value("Company", company, "abbr")
	done = []
	for component in frappe.get_all("Salary Component", filters={"disabled": 0}, fields=["name", "type"]):
		base = PROPOSED_ACCOUNTS.get(component.name) or (
			PROPOSED_ACCOUNTS["__earnings__"] if component.type == "Earning" else None
		)
		if not base:
			continue
		account = f"{base} - {abbr}"
		if not frappe.db.exists("Account", account):
			continue
		doc = frappe.get_doc("Salary Component", component.name)
		row = next((a for a in doc.accounts if a.company == company), None)
		if row and row.account:
			continue
		if not row:
			row = doc.append("accounts", {"company": company})
		row.update(
			{
				"account": account,
				"custom_account_marketing": sibling_account(account, "S/D"),
				"custom_account_plant": sibling_account(account, "F/P"),
			}
		)
		doc.flags.ignore_permissions = True
		doc.save()
		done.append((component.name, account))
	key = next((k for k, p in PROFILES.items() if p["company"] == company), None)
	if key:
		ensure_company_rates(key)
	return done
