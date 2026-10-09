"""Allowance kinds and three accounts on Salary Component; payroll sections.

See payroll/allowance.py for why. On a site that already pays through the old
setup this keeps every slip and every journal the same:

  1. Fields: Salary Component gets Is Allowance, Allowance Kind, Attendance
     Month and Only OT-Eligible Staff; its Accounts rows get Marketing (S/D),
     Plant (F/P) and Default Rate, and the existing account is labelled Admin &
     Accounts (O/O); Department gets Payroll Section.
  2. Departments are seeded by name (Plant… → Plant, Sales…/Marketing… →
     Marketing, the rest Admin & Accounts), the way NGI's Falgun sheet charges
     them. Printed, for HR to check; one already set is left alone.
  3. Every Accounts row gets the S/D and F/P siblings of its account where the
     chart has them, and the component's old Default Rate as the company's.
  4. Known components are marked as allowances of their kind (by name, or by
     their attendance condition); overtime-type ones become OT-eligible only,
     which is what the engine used to hard-code.
  5. Allowance Category rates become rows on each member's own Allowances table
     (a 0 rate an unticked row); the category doctypes and Employee field go.
  6. Who gets an attendance allowance is now a tag: the structure, or the
     employee's own row. Existing structures carry no tag rows, so whatever the
     old engine paid without one — overtime, late fine, and tea or
     meal where no category decided it or the component had a default rate —
     is tagged on every active employee of the company. Nobody stops being paid.
  7. The rule fields the earlier Company Allowance build hid are shown again,
     and its doctypes are removed where a site has them.
  8. Daily Wage is disabled and its rate basis option dropped: labour is paid
     in cash day to day, outside payroll (decided 2026-10-08). This runs
     before the tagging, so nobody is tagged with it.

Re-runnable: nothing already set is overwritten.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.utils import flt

from avinashgroup_app.payroll.allowance import (
	ALLOWANCE_KINDS,
	FIXED_COMPANY_RATE,
	FIXED_PER_PERSON,
	PER_DAY_PRESENT,
	PER_HOUR_OVERTIME,
	PER_MEAL,
	PERCENT_OF_INITIAL_BASIC,
	SECTIONS,
	YEARLY,
	ENTERED_BY_HAND,
	sibling_account,
)

#: Allowances by name, from the four companies' Falgun 2082 sheets.
KIND_BY_NAME = {
	"Dearness Allowance": FIXED_PER_PERSON,
	"Other Allowance": FIXED_PER_PERSON,
	"Fixed Allowance": FIXED_PER_PERSON,
	"Fuel Allowance": FIXED_PER_PERSON,
	"Maintenance Allowance": FIXED_PER_PERSON,
	"Transport Allowance": FIXED_PER_PERSON,
	"Gas Allowance": FIXED_COMPANY_RATE,
	"Education Allowance": FIXED_COMPANY_RATE,
	"Mobile Recharge": FIXED_COMPANY_RATE,
	"House Rent Allowance": PERCENT_OF_INITIAL_BASIC,
	"Load/Unload Allowance": ENTERED_BY_HAND,
	"Dashain Allowance": YEARLY,
	"Dashain Bonus": YEARLY,
	"Leave Encashment": YEARLY,
}
#: Attendance conditions that are allowances, and their kind.
KIND_BY_CONDITION = {
	"Status = Present": PER_DAY_PRESENT,
	"Meal Entitlement": PER_MEAL,
	"Authorised Overtime": PER_HOUR_OVERTIME,
}
#: Conditions the engine used to pay only to OT-eligible staff.
OT_ONLY_CONDITIONS = ("Late Stay After", "Early Entry Before", "Authorised Overtime")
#: Conditions the engine used to pay to everyone, category or not.
PAID_TO_ALL_CONDITIONS = OT_ONLY_CONDITIONS + ("Late Time", "Late Arrival After")
#: Salary Component fields the Company Allowance build hid.
RULE_FIELDS = (
	"custom_condition_type",
	"custom_unit",
	"custom_default_rate",
	"custom_half_day_counts",
	"custom_pay_on_holiday",
	"custom_time_offset_hours",
	"custom_max_per_day",
	"custom_rate_basis",
	"custom_rate_multiplier",
	"custom_rate_days_per_month",
	"custom_rate_hours_per_day",
)


def execute():
	frappe.reload_doc("avinash_group_app", "doctype", "employee_attendance_allowance")
	add_fields()
	show_rule_fields()
	seed_sections()
	rows = seed_account_rows()
	retire_daily_wage()
	marked = mark_allowances()
	moved = move_categories()
	tagged = tag_paid_to_all()
	remove_categories()
	remove_company_allowance()
	for doctype in ("Salary Component", "Salary Component Account", "Department", "Employee"):
		frappe.clear_cache(doctype=doctype)
	print(
		f"Allowances: {marked} components marked; {rows} account rows given S/D, F/P or a rate; "
		f"{moved} employee rows from Allowance Category; {tagged} employees tagged with what was paid to all"
	)


def add_fields():
	create_custom_fields(
		{
			"Salary Component": [
				{
					"fieldname": "custom_allowance_section",
					"label": "Allowance",
					"fieldtype": "Section Break",
					"insert_after": "formula",
					"collapsible": 1,
				},
				{
					"fieldname": "custom_is_allowance",
					"label": "Is Allowance",
					"fieldtype": "Check",
					"insert_after": "custom_allowance_section",
					"in_standard_filter": 1,
				},
				{
					"fieldname": "custom_allowance_kind",
					"label": "Allowance Kind",
					"fieldtype": "Select",
					"options": "\n" + "\n".join(ALLOWANCE_KINDS),
					"insert_after": "custom_is_allowance",
					"depends_on": "eval:doc.custom_is_allowance",
					"mandatory_depends_on": "eval:doc.custom_is_allowance",
					"in_standard_filter": 1,
					"in_list_view": 1,
					"description": (
						"Fixed per Person, Fixed Company Rate, % of Initial Basic: a row in the Salary Structure. "
						"Per Day Present, Per Meal, Per Hour: counted from attendance each month (Prepare "
						"Payroll Inputs); a row in the structure tags who gets it. Entered by Hand: typed as "
						"Additional Salary. Yearly: Dashain / leave encashment, by their own buttons."
					),
				},
				{
					"fieldname": "custom_attendance_month",
					"label": "Attendance Month",
					"fieldtype": "Select",
					"options": "Same as Salary\nPrevious Month",
					"default": "Same as Salary",
					"insert_after": "custom_unit",
					"depends_on": "eval:doc.custom_is_attendance_driven",
					"description": "Which BS month's attendance this month's salary counts.",
				},
				{
					"fieldname": "custom_ot_eligible_only",
					"label": "Only OT-Eligible Staff",
					"fieldtype": "Check",
					"insert_after": "custom_attendance_month",
					"depends_on": "eval:doc.custom_is_attendance_driven",
					"description": "Pay only employees with OT Eligible ticked (policy 2.2: overtime and meals).",
				},
			],
			"Salary Component Account": [
				{
					"fieldname": "custom_account_marketing",
					"label": "Marketing (S/D)",
					"fieldtype": "Link",
					"options": "Account",
					"insert_after": "account",
					"in_list_view": 1,
				},
				{
					"fieldname": "custom_account_plant",
					"label": "Plant (F/P)",
					"fieldtype": "Link",
					"options": "Account",
					"insert_after": "custom_account_marketing",
					"in_list_view": 1,
				},
				{
					"fieldname": "custom_default_rate",
					"label": "Default Rate",
					"fieldtype": "Float",
					"insert_after": "custom_account_plant",
					"in_list_view": 1,
					"description": "This company's rate for an attendance allowance: per day, meal or hour.",
				},
			],
			"Department": [
				{
					"fieldname": "custom_payroll_section",
					"label": "Payroll Section",
					"fieldtype": "Select",
					"options": "\n" + "\n".join(SECTIONS),
					"insert_after": "payroll_cost_center",
					"in_list_view": 1,
					"description": (
						"Which account of each Salary Component this department's pay posts to: "
						"Admin & Accounts (O/O), Marketing (S/D) or Plant (F/P)."
					),
				}
			],
		},
		update=True,
	)
	make_property_setter(
		"Salary Component Account", "account", "label", "Admin & Accounts (O/O)", "Data", validate_fields_for_doctype=False
	)
	for fieldname, values in (
		("custom_attendance_rule_section", {"insert_after": "custom_allowance_kind"}),
		# Payroll Inputs hung off the removed Allowance Category field; without a
		# new anchor the section loses its place on the form.
		("custom_payroll_inputs_section", {"insert_after": "custom_late_fine_exempt", "collapsible": 0}),
		("custom_attendance_allowances_section", {"label": "Allowance Exceptions", "insert_after": "custom_maintenance_allowance"}),
		(
			"custom_attendance_allowances",
			{
				"label": "Allowance Exceptions",
				"description": (
					"Only for exceptions to an attendance allowance (tea, meal, overtime): this "
					"employee's own rate, or Eligible unticked to stop it. Who gets an allowance is "
					"their Salary Structure."
				),
			},
		),
	):
		dt = "Salary Component" if fieldname == "custom_attendance_rule_section" else "Employee"
		name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname})
		if name:
			frappe.db.set_value("Custom Field", name, values)


def show_rule_fields():
	for fieldname in RULE_FIELDS:
		name = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": fieldname})
		if name:
			frappe.db.set_value("Custom Field", name, "hidden", 0)
	name = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": "custom_is_attendance_driven"})
	if name:
		frappe.db.set_value(
			"Custom Field",
			name,
			{"read_only": 0, "description": "Set automatically for a Per Day / Per Meal / Per Hour allowance."},
		)


def section_for_department(name: str) -> str:
	lowered = name.lower()
	if "plant" in lowered:
		return "Plant"
	if "sales" in lowered or "marketing" in lowered:
		return "Marketing"
	return "Admin & Accounts"


def seed_sections():
	for dept in frappe.get_all("Department", filters={"is_group": 0}, fields=["name", "custom_payroll_section"]):
		if dept.custom_payroll_section:
			continue
		section = section_for_department(dept.name)
		frappe.db.set_value("Department", dept.name, "custom_payroll_section", section, update_modified=False)
		print(f"  {dept.name}: {section}")


def seed_account_rows() -> int:
	changed = 0
	for row in frappe.get_all(
		"Salary Component Account",
		filters={"parenttype": "Salary Component", "account": ["is", "set"]},
		fields=["name", "parent", "account", "custom_account_marketing", "custom_account_plant", "custom_default_rate"],
	):
		values = {}
		if not row.custom_account_marketing and (sd := sibling_account(row.account, "S/D")):
			values["custom_account_marketing"] = sd
		if not row.custom_account_plant and (fp := sibling_account(row.account, "F/P")):
			values["custom_account_plant"] = fp
		old_rate = flt(frappe.db.get_value("Salary Component", row.parent, "custom_default_rate"))
		if not flt(row.custom_default_rate) and old_rate:
			values["custom_default_rate"] = old_rate
		if values:
			frappe.db.set_value("Salary Component Account", row.name, values, update_modified=False)
			changed += 1
	return changed


def retire_daily_wage():
	if frappe.db.exists("Salary Component", "Daily Wage"):
		frappe.db.set_value("Salary Component", "Daily Wage", "disabled", 1, update_modified=False)
	name = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": "custom_rate_basis"})
	if name:
		options = (frappe.db.get_value("Custom Field", name, "options") or "").split("\n")
		frappe.db.set_value("Custom Field", name, "options", "\n".join(o for o in options if o != "Daily Wage"))


def mark_allowances() -> int:
	marked = 0
	for sc in frappe.get_all(
		"Salary Component",
		fields=["name", "custom_is_allowance", "custom_is_attendance_driven", "custom_condition_type"],
	):
		values = {}
		if sc.custom_is_attendance_driven and sc.custom_condition_type in OT_ONLY_CONDITIONS:
			values["custom_ot_eligible_only"] = 1
		kind = KIND_BY_NAME.get(sc.name) or (
			KIND_BY_CONDITION.get(sc.custom_condition_type) if sc.custom_is_attendance_driven else None
		)
		if kind and sc.name != "Daily Wage" and not sc.custom_is_allowance:
			values.update({"custom_is_allowance": 1, "custom_allowance_kind": kind})
			marked += 1
		if values:
			frappe.db.set_value("Salary Component", sc.name, values, update_modified=False)
	return marked


def add_employee_row(employee: str, component: str, rate: float = 0, eligible: int = 1) -> bool:
	"""Give an employee their own row for an allowance unless they have one."""
	if frappe.db.exists(
		"Employee Attendance Allowance",
		{"parent": employee, "parenttype": "Employee", "salary_component": component},
	):
		return False
	idx = frappe.db.count("Employee Attendance Allowance", {"parent": employee, "parenttype": "Employee"}) + 1
	child = frappe.new_doc("Employee Attendance Allowance")
	child.update(
		{
			"parent": employee,
			"parenttype": "Employee",
			"parentfield": "custom_attendance_allowances",
			"idx": idx,
			"salary_component": component,
			"rate": flt(rate),
			"eligible": eligible,
		}
	)
	child.db_insert()
	return True


def move_categories() -> int:
	if not frappe.db.table_exists("Allowance Category Rate") or not frappe.db.has_column(
		"Employee", "custom_allowance_category"
	):
		return 0
	moved = 0
	for emp in frappe.get_all(
		"Employee", filters={"custom_allowance_category": ["is", "set"]}, fields=["name", "custom_allowance_category"]
	):
		# Plain SQL: on a site where the doctype record is already gone, its
		# table can outlive it, and get_all needs the doctype.
		for rate in frappe.db.sql(
			"""select salary_component, rate from `tabAllowance Category Rate`
			where parent = %s and parenttype = 'Allowance Category'""",
			emp.custom_allowance_category,
			as_dict=True,
		):
			moved += add_employee_row(emp.name, rate.salary_component, rate.rate, 1 if flt(rate.rate) else 0)

	field = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": "custom_allowance_category"})
	if field:
		frappe.delete_doc("Custom Field", field, force=True, ignore_permissions=True)
	return moved


def remove_categories():
	"""After tag_paid_to_all has read which components a category decided."""
	for doctype in ("Allowance Category", "Allowance Category Rate"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
		frappe.db.sql_ddl(f"drop table if exists `tab{doctype}`")


def tag_paid_to_all() -> int:
	"""Tag everyone with each attendance component the old engine paid untagged.

	Runs after move_categories: categorised staff already have their own row
	(kept), so only the rest are added — exactly who the old engine paid.
	"""
	category_components = set()
	if frappe.db.table_exists("Allowance Category Rate"):
		category_components = set(
			frappe.db.sql_list("select distinct salary_component from `tabAllowance Category Rate`")
		)
	tagged = 0
	for sc in frappe.get_all(
		"Salary Component",
		filters={"custom_is_attendance_driven": 1, "disabled": 0},
		fields=["name", "custom_condition_type", "custom_default_rate"],
	):
		paid_to_all = (
			sc.name not in category_components
			or sc.custom_condition_type in PAID_TO_ALL_CONDITIONS
			or flt(sc.custom_default_rate)
		)
		if not paid_to_all:
			continue
		companies = frappe.get_all(
			"Salary Component Account", filters={"parent": sc.name, "parenttype": "Salary Component"}, pluck="company"
		)
		for employee in frappe.get_all(
			"Employee", filters={"company": ["in", companies], "status": "Active"}, pluck="name"
		):
			tagged += add_employee_row(employee, sc.name)
	return tagged


def remove_company_allowance():
	"""The Company Allowance build (never released) left two doctypes on the dev site."""
	for doctype in ("Company Allowance", "Company Allowance Item"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
			frappe.db.sql_ddl(f"drop table if exists `tab{doctype}`")
