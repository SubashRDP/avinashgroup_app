"""Allowances: a kind of Salary Component, with three accounts per company.

Every company in the group pays its own allowances (dearness, gas, HRA, tea,
meal, overtime, fuel…) and the list grows. Three things needed fixing:

  * The chart keeps every staff cost three ways — O/O (Admin & Accounts), S/D
    (Marketing), F/P (Plant) — but a Salary Component has ONE account per
    company, so everything posted to O/O.
  * Nothing said which components are allowances, or how each one is worked
    out, so the setup lived only in people's heads and in the salary sheets.
  * Attendance allowances went to every employee unless a 0 rate said
    otherwise (the old Allowance Category).

So, on the Salary Component itself:

  * `custom_is_allowance` + `custom_allowance_kind` (ALLOWANCE_KINDS below). An
    attendance kind sets the attendance rule fields itself (validate hook).
  * Its Accounts table (Salary Component Account) gets, per company, a
    Marketing (S/D) and a Plant (F/P) account beside the existing one (now the
    Admin & Accounts one), and a Default Rate — tea is 235 at NGI, 265 at NGN.

Who gets an allowance is the Salary Structure: a row for it in the employee's
structure tags them. Fixed kinds are ordinary structure rows with an amount or
formula, computed by HRMS. An attendance kind's structure row only tags —
`validate_salary_structure` blanks its amount — and the attendance engine
(payroll/attendance_allowance.py) posts the month's figure. The employee's own
Allowances table (`custom_attendance_allowances`) holds exceptions only: their
own rate (NEW staff, tea at 40) or Eligible unticked; it also tags people on
sites set up before structures carried the tag.

Hooks: doc_events → Salary Component / Salary Structure / Employee validate.
Read by attendance_allowance.py and payroll_entry.py. See docs/allowances.md.

Dashain bonus and leave encashment are Yearly kinds, paid by their own buttons
on the Payroll Entry (not built yet); nothing here pays them.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

#: How each allowance is worked out (docs/allowances.md has the full table, from
#: the four companies' Falgun 2082 salary sheets).
FIXED_PER_PERSON = "Fixed per Person"  # dearness, other, fixed, fuel, maintenance, transport
FIXED_COMPANY_RATE = "Fixed Company Rate"  # gas, education, mobile
PERCENT_OF_INITIAL_BASIC = "% of Initial Basic"  # HRA
PER_DAY_PRESENT = "Per Day Present"  # tea & conveyance
PER_MEAL = "Per Meal"  # meal
PER_HOUR_OVERTIME = "Per Hour (Overtime)"  # overtime
ENTERED_BY_HAND = "Entered by Hand"  # load / unload, typed as Additional Salary
YEARLY = "Yearly"  # dashain bonus, leave encashment — their own buttons

ALLOWANCE_KINDS = (
	FIXED_PER_PERSON,
	FIXED_COMPANY_RATE,
	PERCENT_OF_INITIAL_BASIC,
	PER_DAY_PRESENT,
	PER_MEAL,
	PER_HOUR_OVERTIME,
	ENTERED_BY_HAND,
	YEARLY,
)

#: The attendance kinds and the engine condition each one sets on the component.
ATTENDANCE_KIND_CONDITION = {
	PER_DAY_PRESENT: "Status = Present",
	PER_MEAL: "Meal Entitlement",
	PER_HOUR_OVERTIME: "Authorised Overtime",
}
#: Kinds that must never be a monthly structure row: they would be paid every month.
NOT_IN_STRUCTURE = (ENTERED_BY_HAND, YEARLY)

#: Department.custom_payroll_section → the Salary Component Account field.
SECTION_ACCOUNT_FIELD = {
	"Admin & Accounts": "account",
	"Marketing": "custom_account_marketing",
	"Plant": "custom_account_plant",
}
SECTIONS = tuple(SECTION_ACCOUNT_FIELD)


def _request_cache(key: str) -> dict:
	cache = getattr(frappe.local, key, None)
	if cache is None:
		cache = {}
		setattr(frappe.local, key, cache)
	return cache


# ── per-company account rows ────────────────────────────────────────────────


def get_account_row(company: str, salary_component: str):
	"""The component's Accounts row for the company, as a dict, or None.

	Carries `account` (Admin & Accounts, O/O), `custom_account_marketing`,
	`custom_account_plant` and `custom_default_rate`. Cached per request.
	"""
	if not company or not salary_component:
		return None
	cache = _request_cache("_agp_account_row")
	key = (company, salary_component)
	if key not in cache:
		rows = frappe.get_all(
			"Salary Component Account",
			filters={"parent": salary_component, "parenttype": "Salary Component", "company": company},
			fields=["account", "custom_account_marketing", "custom_account_plant", "custom_default_rate"],
			limit=1,
		)
		cache[key] = rows[0] if rows else None
	return cache[key]


def company_default_rate(company: str, salary_component: str) -> float:
	row = get_account_row(company, salary_component)
	return flt(row.custom_default_rate) if row else 0.0


def section_account(company: str, salary_component: str, section: str | None) -> str | None:
	"""The account this section's cost posts to; blank S/D or F/P → O/O; None
	when the component has no row for the company (HRMS then throws its own)."""
	row = get_account_row(company, salary_component)
	if not row:
		return None
	return row.get(SECTION_ACCOUNT_FIELD.get(section or "", "account")) or row.account


def sibling_account(account: str, marker: str) -> str | None:
	"""The S/D or F/P twin of an O/O account, if the chart has one.

	The chart numbers the three apart (547130 / 547131 / 547132 Meal
	Allowance), so the match is on the name with `O/O` swapped.
	"""
	if not account or "O/O" not in account:
		return None
	twin = account.replace("O/O", marker)
	if frappe.db.exists("Account", twin):
		return twin
	if " - " not in account:
		return None
	name_part = account.split(" - ", 1)[1].replace("O/O", marker)
	company = frappe.db.get_value("Account", account, "company")
	return frappe.db.get_value("Account", {"company": company, "is_group": 0, "name": ["like", f"% - {name_part}"]})


def has_section_accounts(company: str, salary_component: str) -> bool:
	row = get_account_row(company, salary_component)
	return bool(row and (row.custom_account_marketing or row.custom_account_plant))


def get_section(employee: str) -> str | None:
	"""The employee's payroll section, from their Department; None if unset."""
	cache = _request_cache("_agp_payroll_section")
	if employee not in cache:
		department = frappe.get_cached_value("Employee", employee, "department")
		cache[employee] = (
			frappe.get_cached_value("Department", department, "custom_payroll_section") if department else None
		) or None
	return cache[employee]


# ── who gets an attendance allowance ────────────────────────────────────────


def get_employee_allowance_rows(employee: str, on_date=None) -> dict:
	"""{salary component: row} of the employee's exceptions table, in force on `on_date`."""
	rows = frappe.get_all(
		"Employee Attendance Allowance",
		filters={"parent": employee, "parenttype": "Employee"},
		fields=["salary_component", "rate", "eligible", "effective_from"],
	)
	on_date = getdate(on_date) if on_date else None
	return {
		r.salary_component: r
		for r in rows
		if not (on_date and r.effective_from and getdate(r.effective_from) > on_date)
	}


def structure_components(employee: str, on_date) -> set:
	"""Every component in the employee's salary structure as of `on_date`."""
	cache = _request_cache("_agp_structure_components")
	key = (employee, str(getdate(on_date)))
	if key not in cache:
		structure = frappe.db.get_value(
			"Salary Structure Assignment",
			{"employee": employee, "docstatus": 1, "from_date": ["<=", getdate(on_date)]},
			"salary_structure",
			order_by="from_date desc",
		)
		cache[key] = (
			set(
				frappe.get_all(
					"Salary Detail",
					filters={"parent": structure, "parenttype": "Salary Structure"},
					pluck="salary_component",
				)
			)
			if structure
			else set()
		)
	return cache[key]


def is_tagged(employee: str, salary_component: str, row, on_date) -> bool:
	"""Tagged = in their structure, or an Eligible row of their own; an
	unticked row of their own always wins (staff on no tea)."""
	if row is not None:
		return bool(row.get("eligible"))
	return salary_component in structure_components(employee, on_date)


# ── hooks ───────────────────────────────────────────────────────────────────


def validate_salary_component(doc, method=None):
	"""An allowance's kind decides its attendance settings; accounts are the company's.

	Hook: doc_events → Salary Component → validate. Throws for an S/D or F/P
	account of another company. An attendance kind turns the component into an
	attendance-driven one with the matching condition, no Depends on Payment
	Days (the count already leaves out absences) and Remove if Zero Valued (its
	structure row is only a tag).
	"""
	for row in doc.get("accounts") or []:
		for field in ("custom_account_marketing", "custom_account_plant"):
			account = row.get(field)
			if account and frappe.db.get_value("Account", account, "company") != row.company:
				frappe.throw(_("Accounts row {0}: {1} is not an account of {2}").format(row.idx, account, row.company))

	if doc.get("custom_is_allowance"):
		kind = doc.get("custom_allowance_kind")
		if not kind:
			frappe.throw(_("Choose the Allowance Kind"))
		condition = ATTENDANCE_KIND_CONDITION.get(kind)
		if condition:
			doc.custom_is_attendance_driven = 1
			doc.custom_condition_type = condition
			if kind == PER_HOUR_OVERTIME:
				doc.custom_unit = "Per Hour"
		else:
			doc.custom_is_attendance_driven = 0
	else:
		doc.custom_allowance_kind = None

	if doc.get("custom_is_attendance_driven"):
		# Counted on the days worked, so not cut again for absences; and its
		# structure row is only a tag, so a 0 there must not print on the slip.
		doc.depends_on_payment_days = 0
		doc.remove_if_zero_valued = 1


def validate_salary_structure(doc, method=None):
	"""Attendance allowance rows are tags; Yearly and hand-entered kinds stay out.

	Hook: doc_events → Salary Structure → validate. An attendance allowance's
	row would otherwise be paid by its own formula as well as by the engine.
	"""
	for table in ("earnings", "deductions"):
		for row in doc.get(table) or []:
			attendance, kind = frappe.get_cached_value(
				"Salary Component", row.salary_component, ["custom_is_attendance_driven", "custom_allowance_kind"]
			)
			if kind in NOT_IN_STRUCTURE:
				frappe.throw(
					_("Row {0}: {1} is a {2} allowance; it is paid when entered, not every month in the structure").format(
						row.idx, row.salary_component, kind
					)
				)
			if attendance:
				row.amount = 0
				row.formula = None
				row.condition = None
				row.amount_based_on_formula = 0


def validate_employee_allowances(doc, method=None):
	"""The employee's exceptions table: attendance allowances only, once each.

	Hook: doc_events → Employee → validate. A fixed allowance is set in the
	salary structure, so a row for one here would do nothing — refused rather
	than left to mislead. Fills the row's read-only Kind and Company Default
	Rate columns.
	"""
	seen = set()
	for row in doc.get("custom_attendance_allowances") or []:
		if row.salary_component in seen:
			frappe.throw(_("Allowance {0} is listed twice").format(row.salary_component))
		seen.add(row.salary_component)
		attendance, kind = frappe.db.get_value(
			"Salary Component", row.salary_component, ["custom_is_attendance_driven", "custom_allowance_kind"]
		)
		if not attendance:
			frappe.throw(
				_("Row {0}: {1} is not attendance based; set it in the Salary Structure instead").format(
					row.idx, row.salary_component
				)
			)
		row.attendance_based = 1
		row.calculation = kind
		row.default_rate = company_default_rate(doc.company, row.salary_component)
