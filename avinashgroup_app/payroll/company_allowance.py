"""Company Allowance: what each company pays, at what rate, to which account.

Every company in the group pays its own set of allowances — tea and meal at
NGI and NGN, fuel and maintenance at NGK, gas, HRA, mobile recharge — and the
list grows. Before this, three things were wrong:

  * A Salary Component holds ONE account per company, so all of a company's
    tea posted to the O/O account although its chart keeps O/O (Admin &
    Accounts), S/D (Marketing) and F/P (Plant) apart. Only Salary Expenses was
    re-routed, by a hard-coded map in hr_journal.py.
  * Attendance allowances went to every employee; who did not get tea was
    expressed as a 0 rate on a group (Allowance Category).
  * The attendance rule (1.5 h for a meal, tea not on holidays) lived on the
    Salary Component, so every company had to share it.

So each company has one `Company Allowance` record, and each row of its
Allowances table (`Company Allowance Item`) holds one allowance's rule, the
company's default rate, who gets it, and three accounts. The employee's
own Allowances table (`Employee.custom_attendance_allowances`) says which ones
that person gets and at what rate. The section comes from the employee's
Department (`custom_payroll_section`).

Readers:
  * payroll/attendance_allowance.py — attendance-based allowances, monthly
  * payroll/salary_slip.py          — Fixed Monthly / % of Initial Basic rows
  * payroll/payroll_entry.py        — the accrual journal's account per section
  * `validate_employee_allowances`  — doc_events → Employee → validate

A component with no Company Allowance for a company keeps HRMS's own single
account and is never paid by the attendance engine at that company. See
docs/company-allowance.md.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

#: Department.custom_payroll_section values → the Company Allowance account
#: field for that section. The three sections are the chart's O/O, S/D, F/P.
SECTION_ACCOUNT_FIELD = {
	"Admin & Accounts": "account_admin",
	"Marketing": "account_marketing",
	"Plant": "account_plant",
}
DEFAULT_SECTION = "Admin & Accounts"

FIXED_MONTHLY = "Fixed Monthly"
PERCENT_OF_INITIAL_BASIC = "% of Initial Basic"
FROM_STRUCTURE = "From Salary Structure"
#: Calculations this app adds to the slip itself (payroll/salary_slip.py).
SLIP_CALCULATIONS = (FIXED_MONTHLY, PERCENT_OF_INITIAL_BASIC)


def _request_cache(key: str) -> dict:
	cache = getattr(frappe.local, key, None)
	if cache is None:
		cache = {}
		setattr(frappe.local, key, cache)
	return cache


def _company_rows(company: str) -> dict:
	"""{salary component: row dict} of the company's enabled allowances.

	Cached per request: the engine and the reports ask once per employee per
	day per component. Each row carries `company` so callers need not.
	"""
	cache = _request_cache("_agp_company_allowance")
	if company not in cache:
		rows = {}
		if frappe.db.exists("Company Allowance", company):
			for row in frappe.get_cached_doc("Company Allowance", company).allowances:
				if not row.disabled:
					rows[row.salary_component] = frappe._dict(row.as_dict(), company=company)
		cache[company] = rows
	return cache[company]


def get_company_allowance(company: str, salary_component: str):
	"""The company's enabled row for this allowance, as a dict, or None."""
	if not company or not salary_component:
		return None
	return _company_rows(company).get(salary_component)


def get_company_allowances(company: str) -> list:
	"""Every enabled allowance row of a company, as dicts."""
	return list(_company_rows(company).values()) if company else []


def company_allowance_doc(company: str):
	"""The company's Company Allowance record, or a new unsaved one."""
	if frappe.db.exists("Company Allowance", company):
		return frappe.get_doc("Company Allowance", company)
	return frappe.get_doc({"doctype": "Company Allowance", "company": company})


def get_employee_allowance_rows(employee: str, on_date=None) -> dict:
	"""{salary component: row} from the employee's Allowances table.

	A row whose Effective From is after `on_date` is not in force yet and is
	left out.
	"""
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


def employee_gets(allowance: dict, row) -> bool:
	"""Whether an employee with this Allowances row (or None) is paid it.

	Only employees tagged with the allowance — a row in their Allowances table,
	Eligible ticked — are paid it. Nobody gets an allowance by default.
	"""
	return row is not None and bool(row.get("eligible"))


def employee_rate(allowance: dict, row) -> float:
	"""The employee's own rate, else the company default."""
	return flt(row.get("rate")) if row is not None and flt(row.get("rate")) else flt(allowance.get("default_rate"))


def get_section(employee: str) -> str | None:
	"""The employee's payroll section, from their Department; None if unset."""
	cache = _request_cache("_agp_payroll_section")
	if employee not in cache:
		department = frappe.get_cached_value("Employee", employee, "department")
		cache[employee] = (
			frappe.get_cached_value("Department", department, "custom_payroll_section") if department else None
		) or None
	return cache[employee]


def section_account(allowance: dict, section: str | None) -> str | None:
	"""The account this section's cost posts to; blank S/D or F/P → O/O."""
	field = SECTION_ACCOUNT_FIELD.get(section or DEFAULT_SECTION, "account_admin")
	return allowance.get(field) or allowance.get("account_admin")


def has_section_accounts(allowance: dict) -> bool:
	return bool(allowance.get("account_marketing") or allowance.get("account_plant"))


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def allowance_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link search for the employee's Allowances table: the company's own list."""
	return frappe.get_all(
		"Company Allowance Item",
		filters={
			"parenttype": "Company Allowance",
			"parent": filters.get("company"),
			"disabled": 0,
			"salary_component": ["like", f"%{txt}%"],
		},
		fields=["salary_component", "component_type"],
		start=start,
		page_length=page_len,
		as_list=True,
	)


def validate_employee_allowances(doc, method=None):
	"""Check the employee's Allowances table and fill its read-only columns.

	Hook: doc_events → Employee → validate. Throws for an allowance the
	employee's company does not pay (NGI's tea on a Karnali employee would be
	paid at a rate nobody set) and for the same allowance listed twice.
	"""
	seen = set()
	for row in doc.get("custom_attendance_allowances") or []:
		if row.salary_component in seen:
			frappe.throw(_("Allowance {0} is listed twice").format(row.salary_component))
		seen.add(row.salary_component)

		allowance = get_company_allowance(doc.company, row.salary_component)
		if not allowance:
			frappe.throw(
				_("Row {0}: {1} is not an allowance of {2}. Add it to the company's Company Allowance first.").format(
					row.idx, row.salary_component, doc.company
				)
			)
		row.attendance_based = allowance.is_attendance_based
		row.calculation = allowance.based_on if allowance.is_attendance_based else allowance.calculation
		row.default_rate = allowance.default_rate
