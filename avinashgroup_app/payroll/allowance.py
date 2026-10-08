"""Allowances: a kind of Salary Component, given per employee, three accounts per company.

Every company in the group pays its own allowances (dearness, gas, HRA, tea,
meal, overtime, fuel…) and the list grows. Before this, each new allowance
needed a new Employee field and a new structure row reading it — and a
submitted structure cannot take a new row, so every addition meant new
structures for everyone. The chart also keeps every staff cost three ways —
O/O (Admin & Accounts), S/D (Marketing), F/P (Plant) — while a Salary
Component carried one account per company.

So:

  * Salary Component: `custom_is_allowance` + `custom_allowance_kind`
    (ALLOWANCE_KINDS). An attendance kind sets its own rule flags.
  * Its Accounts table (Salary Component Account), per company: the Admin &
    Accounts account (the row's own `account`), `custom_account_marketing`,
    `custom_account_plant`, and `custom_default_rate` — the company's rate
    (tea 235 at NGI, 265 at NGN; gas 1,690; HRA 25 %).
  * Salary Structure Assignment → Allowances (`custom_allowances`, child
    Assignment Allowance): one row per allowance the person gets, with their
    Amount (blank = the company rate), Active, From Date. The assignment also
    carries `custom_initial_basic` and `custom_ssf_applicable`.

Pay lives on the assignment, not the Employee: an employee is created without
any salary figure, whoever maintains employees does not see pay, and a change
is a new dated assignment that leaves the old one as the record (Salary
Revision works that way). Adding an allowance is a Salary Component and rows on
the assignments of the people who get it — no new field, no new structure.

Where each kind is paid:
  * Fixed per Person / Fixed Company Rate / % of Initial Basic: added to the
    salary slip from the assignment's rows (payroll/salary_slip.py) — prorated
    by payment days like a structure row, and projected for income tax.
  * Per Day Present / Per Meal / Per Hour: counted from attendance by Prepare
    Payroll Inputs (payroll/attendance_allowance.py). These may also be a tag
    row in the Salary Structure, which gives them to everyone on it (tea for
    all staff); a row on the assignment then only carries an exception.
  * Entered by Hand / Yearly: Additional Salary, or their own buttons.

The structure keeps only what every employee on it shares: Basic, SSF
Addition, SSF, Income Tax and the attendance tags. `validate_salary_structure`
refuses a fixed allowance there (it would be paid twice).

Hooks: doc_events → Salary Component / Salary Structure / Salary Structure
Assignment validate.
Read by attendance_allowance.py, salary_slip.py, payroll_entry.py and Salary
Revision. See docs/allowances.md.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

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
#: Paid on the slip from the employee's Allowances rows.
FIXED_KINDS = (FIXED_PER_PERSON, FIXED_COMPANY_RATE, PERCENT_OF_INITIAL_BASIC)
#: Counted from attendance, and the engine condition each one sets.
ATTENDANCE_KIND_CONDITION = {
	PER_DAY_PRESENT: "Status = Present",
	PER_MEAL: "Meal Entitlement",
	PER_HOUR_OVERTIME: "Authorised Overtime",
}
#: Never a structure row: fixed kinds come from the employee's rows, the rest
#: are paid when entered.
NOT_IN_STRUCTURE = FIXED_KINDS + (ENTERED_BY_HAND, YEARLY)
#: Never on the employee's Allowances table.
NOT_ON_EMPLOYEE = (ENTERED_BY_HAND, YEARLY)

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
	"""The component's Accounts row for the company, as a dict, or None. Cached per request."""
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


def has_section_accounts(company: str, salary_component: str) -> bool:
	row = get_account_row(company, salary_component)
	return bool(row and (row.custom_account_marketing or row.custom_account_plant))


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


def get_section(employee: str) -> str | None:
	"""The employee's payroll section, from their Department; None if unset."""
	cache = _request_cache("_agp_payroll_section")
	if employee not in cache:
		department = frappe.get_cached_value("Employee", employee, "department")
		cache[employee] = (
			frappe.get_cached_value("Department", department, "custom_payroll_section") if department else None
		) or None
	return cache[employee]


# ── the employee's allowances (on their salary assignment) ─────────────────


def current_assignment(employee: str, on_date):
	"""The employee's submitted Salary Structure Assignment in force on `on_date`, or None."""
	cache = _request_cache("_agp_assignment")
	key = (employee, str(getdate(on_date)))
	if key not in cache:
		cache[key] = frappe.db.get_value(
			"Salary Structure Assignment",
			{"employee": employee, "docstatus": 1, "from_date": ["<=", getdate(on_date)]},
			["name", "salary_structure", "base", "custom_initial_basic", "custom_ssf_applicable"],
			as_dict=True,
			order_by="from_date desc",
		)
	return cache[key]


def get_employee_allowance_rows(employee: str, on_date=None) -> dict:
	"""{allowance: row} on the employee's assignment in force on `on_date`.

	Each row carries `rate` (the Amount column) and `eligible` (Active), the
	names the attendance engine reads. A row whose From Date is later is not in
	force yet.
	"""
	on_date = getdate(on_date) if on_date else getdate()
	assignment = current_assignment(employee, on_date)
	if not assignment:
		return {}
	rows = frappe.get_all(
		"Assignment Allowance",
		filters={"parent": assignment.name, "parenttype": "Salary Structure Assignment"},
		fields=["allowance", "amount", "active", "effective_from"],
	)
	return {
		r.allowance: frappe._dict(salary_component=r.allowance, rate=r.amount, eligible=r.active, effective_from=r.effective_from)
		for r in rows
		if not (r.effective_from and getdate(r.effective_from) > on_date)
	}


def structure_components(employee: str, on_date) -> set:
	"""Every component in the employee's salary structure as of `on_date`."""
	cache = _request_cache("_agp_structure_components")
	key = (employee, str(getdate(on_date)))
	if key not in cache:
		assignment = current_assignment(employee, on_date)
		structure = assignment.salary_structure if assignment else None
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
	"""Given an attendance allowance: an Active row of their own, or a tag row
	in their structure. An unticked row of their own always wins."""
	if row is not None:
		return bool(row.get("eligible"))
	return salary_component in structure_components(employee, on_date)


def fixed_allowance_amounts(employee: str, company: str, on_date) -> dict:
	"""{allowance: full-month amount} of the employee's fixed allowances.

	Fixed per Person: their Amount. Fixed Company Rate: their Amount, else the
	company's rate. % of Initial Basic: their Amount, else the company's %, of
	the assignment's Initial Basic. A row without a figure to pay is left out.
	"""
	amounts = {}
	initial_basic = flt((current_assignment(employee, on_date) or {}).get("custom_initial_basic"))
	for allowance, row in get_employee_allowance_rows(employee, on_date).items():
		if not row.eligible:
			continue
		kind = frappe.get_cached_value("Salary Component", allowance, "custom_allowance_kind")
		if kind not in FIXED_KINDS:
			continue
		amount = flt(row.rate)
		if not amount and kind != FIXED_PER_PERSON:
			amount = company_default_rate(company, allowance)
		if kind == PERCENT_OF_INITIAL_BASIC:
			amount = initial_basic * amount / 100
		if amount:
			amounts[allowance] = flt(amount, 2)
	return amounts


def allowance_amount(assignment, allowance: str) -> float:
	"""The Amount on an assignment's row for this allowance (0 if none)."""
	return flt(
		frappe.db.get_value(
			"Assignment Allowance",
			{"parent": assignment, "parenttype": "Salary Structure Assignment", "allowance": allowance},
			"amount",
		)
		if assignment
		else 0
	)


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
	"""A structure holds what everyone on it shares; allowances come from the employee.

	Hook: doc_events → Salary Structure → validate. Refuses a fixed allowance
	(the employee's row pays it, so it would be paid twice) and a Yearly or
	hand-entered one (it would be paid every month). An attendance allowance's
	row is a tag: its amount and formula are blanked.
	"""
	for table in ("earnings", "deductions"):
		for row in doc.get(table) or []:
			attendance, kind = frappe.get_cached_value(
				"Salary Component", row.salary_component, ["custom_is_attendance_driven", "custom_allowance_kind"]
			)
			if kind in NOT_IN_STRUCTURE:
				where = (
					_("give it on the employee's Allowances table")
					if kind in FIXED_KINDS
					else _("it is paid when entered, not every month")
				)
				frappe.throw(
					_("Row {0}: {1} is a {2} allowance: {3}").format(row.idx, row.salary_component, kind, where)
				)
			if attendance:
				row.amount = 0
				row.formula = None
				row.condition = None
				row.amount_based_on_formula = 0


def validate_assignment_allowances(doc, method=None):
	"""Assignment → Allowances: allowances only, once each, with an amount where one is needed.

	Hook: doc_events → Salary Structure Assignment → validate.
	"""
	seen = set()
	for row in doc.get("custom_allowances") or []:
		if row.allowance in seen:
			frappe.throw(_("Allowance {0} is listed twice").format(row.allowance))
		seen.add(row.allowance)
		is_allowance, kind = frappe.db.get_value(
			"Salary Component", row.allowance, ["custom_is_allowance", "custom_allowance_kind"]
		)
		if not is_allowance:
			frappe.throw(_("Row {0}: {1} is not an allowance").format(row.idx, row.allowance))
		if kind in NOT_ON_EMPLOYEE:
			frappe.throw(_("Row {0}: {1} is a {2} allowance and is paid when entered").format(row.idx, row.allowance, kind))
		if kind == FIXED_PER_PERSON and row.active and not flt(row.amount):
			frappe.throw(_("Row {0}: type {1}'s monthly amount").format(row.idx, row.allowance))
