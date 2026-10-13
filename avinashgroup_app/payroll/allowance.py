"""Allowances: a kind of Salary Component, a rate list on the structure, the person's rates on the assignment.

Every company in the group pays its own allowances (dearness, gas, HRA, tea,
meal, overtime, fuel…), the list grows, and nearly every person has their own
mix: some get gas, some rent, some neither (27 combinations across 195 people
in October 2026). The chart also keeps every staff cost three ways — O/O (Admin
& Accounts), S/D (Marketing), F/P (Plant).

Three screens, one job each:

  * Salary Component: what the allowance is and how it is counted —
    `custom_is_allowance` + `custom_allowance_kind` (ALLOWANCE_KINDS) — and,
    per company on its Accounts rows, the O/O account (the row's own
    `account`), `custom_account_marketing` and `custom_account_plant`. It holds
    no rate.
  * Salary Structure → Allowance Rates (`custom_allowance_rates`, child
    Structure Allowance Rate): the usual rate of each allowance in that
    structure (tea 235 a day, gas 1,690 a month, HRA 25 %). It decides nobody's
    pay: it fills the rate when HR picks the allowance on an assignment, and it
    is what a Salary Revision raises.
  * Salary Structure Assignment → Allowances (`custom_allowances`, child
    Assignment Allowance): the allowances this person gets and their Rate.
    No row, not paid. Payroll reads only this table.

So a person's pay is one dated record. A change — a raise, a new allowance, one
stopped — is a new assignment from the first of a BS month (Salary Revision),
and the old one stays as the record of what was paid.

Where each kind is paid:
  * Monthly / % of Initial Basic: added to the salary slip from the assignment's
    rows (payroll/salary_slip.py) — prorated by payment days like a structure
    row, and projected for income tax.
  * Per Day Present / Per Meal / Per Overtime Hour: counted from attendance by
    Prepare Payroll Inputs (payroll/attendance_allowance.py), times the row's
    Rate. Overtime's rate is worked out from the person's basic
    (`Hourly Basic × Multiplier` on the component), so its row carries none.
  * Entered by Hand / Yearly: Additional Salary, or their own buttons; never on
    an assignment or in a rate list.

The structure's Earnings and Deductions keep only what HRMS calculates by
formula (Basic, SSF Addition, SSF, Income Tax) and the Late Fine tag;
`validate_salary_structure` refuses an allowance there.

Hooks: doc_events → Salary Component / Salary Structure / Salary Structure
Assignment validate, Salary Structure before_update_after_submit.
Read by attendance_allowance.py, salary_slip.py, payroll_entry.py and Salary
Revision. See docs/allowances.md.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

MONTHLY = "Monthly"  # dearness, other, fixed, fuel, maintenance, transport, gas, education
PERCENT_OF_INITIAL_BASIC = "% of Initial Basic"  # HRA
PER_DAY_PRESENT = "Per Day Present"  # tea & conveyance
PER_MEAL = "Per Meal"  # meal
PER_OVERTIME_HOUR = "Per Overtime Hour"  # overtime
ENTERED_BY_HAND = "Entered by Hand"  # load / unload, typed as Additional Salary
YEARLY = "Yearly"  # dashain bonus, leave encashment — their own buttons

ALLOWANCE_KINDS = (
	MONTHLY,
	PERCENT_OF_INITIAL_BASIC,
	PER_DAY_PRESENT,
	PER_MEAL,
	PER_OVERTIME_HOUR,
	ENTERED_BY_HAND,
	YEARLY,
)
#: Paid on the slip from the assignment's rows.
FIXED_KINDS = (MONTHLY, PERCENT_OF_INITIAL_BASIC)
#: Counted from attendance, and the engine condition each one sets.
ATTENDANCE_KIND_CONDITION = {
	PER_DAY_PRESENT: "Status = Present",
	PER_MEAL: "Meal Entitlement",
	PER_OVERTIME_HOUR: "Authorised Overtime",
}
#: Paid when entered: never on an assignment or in a structure's rate list.
NOT_ON_ASSIGNMENT = (ENTERED_BY_HAND, YEARLY)
#: The unit a row's Rate is in.
UNIT_BY_KIND = {
	MONTHLY: "per month",
	PERCENT_OF_INITIAL_BASIC: "% of initial basic",
	PER_DAY_PRESENT: "per day present",
	PER_MEAL: "per meal",
	PER_OVERTIME_HOUR: "per overtime hour",
}
#: A component priced off the person's own basic, so its rows carry no rate.
COMPUTED_RATE_BASIS = "Hourly Basic × Multiplier"

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
			fields=["account", "custom_account_marketing", "custom_account_plant"],
			limit=1,
		)
		cache[key] = rows[0] if rows else None
	return cache[key]


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


# ── the allowance itself ────────────────────────────────────────────────────


def rate_is_computed(allowance: str) -> bool:
	"""Priced off the person's basic (overtime), so no row carries a rate for it."""
	return frappe.get_cached_value("Salary Component", allowance, "custom_rate_basis") == COMPUTED_RATE_BASIS


def unit_for(allowance: str) -> str:
	"""The unit a Rate for this allowance is in, as the rate tables show it."""
	if not allowance:
		return ""
	kind, multiplier = frappe.get_cached_value(
		"Salary Component", allowance, ["custom_allowance_kind", "custom_rate_multiplier"]
	) or (None, None)
	if rate_is_computed(allowance):
		return _("from basic × {0}").format(frappe.format(flt(multiplier) or 1, {"fieldtype": "Float"}))
	return _(UNIT_BY_KIND.get(kind, ""))


# ── the structure's rate list ───────────────────────────────────────────────


def structure_rate(salary_structure: str, allowance: str) -> float:
	"""The rate the structure lists for an allowance; 0 when it lists none."""
	if not salary_structure or not allowance:
		return 0.0
	return flt(
		frappe.db.get_value(
			"Structure Allowance Rate",
			{"parent": salary_structure, "parenttype": "Salary Structure", "allowance": allowance},
			"rate",
		)
	)


@frappe.whitelist()
def get_rate_for_assignment(salary_structure: str, allowance: str) -> dict:
	"""What a new Allowances row on an assignment starts with: the structure's rate and the unit."""
	frappe.has_permission("Salary Structure", "read", salary_structure, throw=True)
	return {
		"rate": 0 if rate_is_computed(allowance) else structure_rate(salary_structure, allowance),
		"unit": unit_for(allowance),
	}


@frappe.whitelist()
def get_structure_allowances(salary_structure: str) -> list[dict]:
	"""The Allowances rows an assignment starts with when its structure is picked.

	One row per allowance on the structure's Allowance Rates, in its order, at
	the usual rate (0 where it lists none, or where `computed`: worked out from basic).
	The form puts them in as a starting list: HR removes the ones this person
	does not get and types the 0 rates — the assignment's validate refuses a row
	still at 0. Disabled allowances and Entered by Hand / Yearly ones are left out.
	Called only from the form (public/js/salary_structure_assignment.js); a
	saved assignment is never filled from its structure, since no row means not paid.
	"""
	frappe.has_permission("Salary Structure", "read", salary_structure, throw=True)
	rows = frappe.get_all(
		"Structure Allowance Rate",
		filters={"parent": salary_structure, "parenttype": "Salary Structure", "parentfield": "custom_allowance_rates"},
		fields=["allowance", "rate"],
		order_by="idx asc",
	)
	out = []
	for row in rows:
		kind, disabled = frappe.get_cached_value(
			"Salary Component", row.allowance, ["custom_allowance_kind", "disabled"]
		) or (None, 1)
		if disabled or kind in NOT_ON_ASSIGNMENT:
			continue
		computed = rate_is_computed(row.allowance)
		out.append(
			{
				"allowance": row.allowance,
				"rate": 0 if computed else flt(row.rate),
				"unit": unit_for(row.allowance),
			}
		)
	return out


# ── the person's allowances (on their salary assignment) ───────────────────


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

	Each row carries the person's `rate`. A row whose From Date is later is not
	in force yet. An allowance with no row is not paid.
	"""
	on_date = getdate(on_date) if on_date else getdate()
	assignment = current_assignment(employee, on_date)
	if not assignment:
		return {}
	rows = frappe.get_all(
		"Assignment Allowance",
		filters={"parent": assignment.name, "parenttype": "Salary Structure Assignment"},
		fields=["allowance", "rate", "effective_from"],
	)
	return {
		r.allowance: frappe._dict(salary_component=r.allowance, rate=r.rate, effective_from=r.effective_from)
		for r in rows
		if not (r.effective_from and getdate(r.effective_from) > on_date)
	}


def structure_components(employee: str, on_date) -> set:
	"""Every component in the Earnings / Deductions of the employee's structure as of `on_date`.

	Used for the attendance components that are not allowances (the late fine),
	which a structure row still tags.
	"""
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


def fixed_allowance_amounts(employee: str, on_date) -> dict:
	"""{allowance: full-month amount} of the employee's monthly allowances.

	Monthly: the row's Rate. % of Initial Basic: the Rate %, of the
	assignment's Initial Basic.
	"""
	amounts = {}
	initial_basic = flt((current_assignment(employee, on_date) or {}).get("custom_initial_basic"))
	for allowance, row in get_employee_allowance_rows(employee, on_date).items():
		kind = frappe.get_cached_value("Salary Component", allowance, "custom_allowance_kind")
		if kind not in FIXED_KINDS:
			continue
		amount = flt(row.rate)
		if kind == PERCENT_OF_INITIAL_BASIC:
			amount = initial_basic * amount / 100
		if amount:
			amounts[allowance] = flt(amount, 2)
	return amounts


def allowance_rate(assignment, allowance: str) -> float:
	"""The Rate on an assignment's row for this allowance (0 if none)."""
	return flt(
		frappe.db.get_value(
			"Assignment Allowance",
			{"parent": assignment, "parenttype": "Salary Structure Assignment", "allowance": allowance},
			"rate",
		)
		if assignment
		else 0
	)


# ── hooks ───────────────────────────────────────────────────────────────────


def validate_salary_component(doc, method=None):
	"""An allowance's kind decides its attendance settings; accounts are the company's.

	Hook: doc_events → Salary Component → validate. Throws for an O/O, S/D or
	F/P account of another company, or a group account. An attendance kind turns the component into an
	attendance-driven one with the matching condition, no Depends on Payment
	Days (the count already leaves out absences) and Remove if Zero Valued.
	"""
	for row in doc.get("accounts") or []:
		for field in SECTION_ACCOUNT_FIELD.values():
			account = row.get(field)
			if not account:
				continue
			company, is_group = frappe.db.get_value("Account", account, ["company", "is_group"]) or (None, 0)
			if company != row.company:
				frappe.throw(
					_("Accounts row {0}: {1} is not an account of {2}").format(row.idx, account, row.company or _("(no company)"))
				)
			if is_group:
				frappe.throw(_("Accounts row {0}: {1} is a group account; pick a ledger account").format(row.idx, account))

	if doc.get("custom_is_allowance"):
		kind = doc.get("custom_allowance_kind")
		if not kind:
			frappe.throw(_("Choose the Allowance Kind"))
		condition = ATTENDANCE_KIND_CONDITION.get(kind)
		if condition:
			doc.custom_is_attendance_driven = 1
			doc.custom_condition_type = condition
			if kind == PER_OVERTIME_HOUR:
				doc.custom_unit = "Per Hour"
		else:
			doc.custom_is_attendance_driven = 0
	else:
		doc.custom_allowance_kind = None

	if doc.get("custom_is_attendance_driven"):
		# Counted on the days worked, so not cut again for absences; and paid
		# only through Additional Salary, so a 0 must not print on the slip.
		doc.depends_on_payment_days = 0
		doc.remove_if_zero_valued = 1


def _check_allowance_row(row, label: str):
	"""An allowance row in a rate table: a payable allowance, its unit set, no rate when worked out from basic."""
	is_allowance, kind = frappe.get_cached_value(
		"Salary Component", row.allowance, ["custom_is_allowance", "custom_allowance_kind"]
	)
	if not is_allowance:
		frappe.throw(_("{0} row {1}: {2} is not an allowance").format(label, row.idx, row.allowance))
	if kind in NOT_ON_ASSIGNMENT:
		frappe.throw(
			_("{0} row {1}: {2} is a {3} allowance and is paid when entered").format(label, row.idx, row.allowance, kind)
		)
	if flt(row.rate) < 0:
		frappe.throw(_("{0} row {1}: {2}'s rate cannot be negative").format(label, row.idx, row.allowance))
	if rate_is_computed(row.allowance):
		row.rate = 0
	row.unit = unit_for(row.allowance)


def _check_listed_once(rows, label: str):
	seen = set()
	for row in rows:
		if row.allowance in seen:
			frappe.throw(_("{0}: {1} is listed twice").format(label, row.allowance))
		seen.add(row.allowance)


def validate_salary_structure(doc, method=None):
	"""Earnings and Deductions hold formula lines; allowances go in Allowance Rates.

	Hook: doc_events → Salary Structure → validate. An allowance in Earnings
	would be paid to everyone on the structure, whatever their assignment says,
	so it is refused there.
	"""
	for table in ("earnings", "deductions"):
		for row in doc.get(table) or []:
			if frappe.get_cached_value("Salary Component", row.salary_component, "custom_is_allowance"):
				frappe.throw(
					_(
						"{0} row {1}: {2} is an allowance. List its rate under Allowance Rates; "
						"each person gets it from the Allowances on their salary assignment."
					).format(_(table.title()), row.idx, row.salary_component)
				)
			if frappe.get_cached_value("Salary Component", row.salary_component, "custom_is_attendance_driven"):
				# The late fine: a tag, its amount posted by Prepare Payroll Inputs.
				row.amount = 0
				row.formula = None
				row.condition = None
				row.amount_based_on_formula = 0

	rates = doc.get("custom_allowance_rates") or []
	_check_listed_once(rates, _("Allowance Rates"))
	for row in rates:
		_check_allowance_row(row, _("Allowance Rates"))


def guard_structure_rates(doc, method=None):
	"""A submitted structure's rate changes only through a Salary Revision.

	Hook: doc_events → Salary Structure → before_update_after_submit. Adding or
	removing an allowance is fine. Changing a listed rate here would leave the
	people already on it at the old rate, and a later raise would then find
	nobody at the structure's rate — so the revision changes both together.
	"""
	validate_salary_structure(doc)
	if frappe.flags.in_salary_revision:
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	old = {r.allowance: flt(r.rate) for r in before.get("custom_allowance_rates") or []}
	for row in doc.get("custom_allowance_rates") or []:
		if row.allowance in old and flt(row.rate) != old[row.allowance]:
			frappe.throw(
				_(
					"Allowance Rates row {0}: to change {1} from {2} to {3}, make a Salary Revision "
					"(Raise Rate). It moves the people paid {2} on this structure to the new rate too."
				).format(row.idx, row.allowance, old[row.allowance], flt(row.rate)),
				title=_("Use a Salary Revision"),
			)


def validate_assignment_allowances(doc, method=None):
	"""Assignment → Allowances: allowances only, once each, each with the rate this person is paid.

	Hook: doc_events → Salary Structure Assignment → validate. A row left
	without a rate takes the structure's (the same thing the form does when
	the allowance is picked), so an import or a script gets the same result as
	HR typing it. A row still at 0 is refused: no row means not paid.
	"""
	rows = doc.get("custom_allowances") or []
	_check_listed_once(rows, _("Allowances"))
	for row in rows:
		_check_allowance_row(row, _("Allowances"))
		if rate_is_computed(row.allowance):
			continue
		if not flt(row.rate):
			row.rate = structure_rate(doc.salary_structure, row.allowance)
		if not flt(row.rate):
			frappe.throw(
				_("Allowances row {0}: type {1}'s rate for this person, or remove the row if they do not get it").format(
					row.idx, row.allowance
				)
			)
