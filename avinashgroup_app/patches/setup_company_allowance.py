"""Move allowance setup onto Company Allowance, and give Departments a section.

See payroll/company_allowance.py for why. On a site that already pays through
the old setup this keeps every slip the same:

  1. Department gets `custom_payroll_section`, seeded from the department's
     name (Plant… → Plant, Sales…/Marketing… → Marketing, the rest Admin &
     Accounts), the way NGI's Falgun sheet charges them. Printed, for HR to
     check; a department already set is left alone.
  2. Every Salary Component that has an account for a company becomes a
     Company Allowance of that company. The O/O account is the existing one,
     and the S/D and F/P accounts are its siblings with `O/O` swapped, where the
     chart has them. Attendance-driven components carry their rule across from
     the component's fields; everything else is "From Salary Structure", so
     structures go on computing it.
  3. Allowance Category rates become rows on each member's Allowances table (a
     0 rate becomes an unticked row), so who is paid tea, and at what rate, does
     not move. The category doctypes and the Employee field then go.
  4. Only tagged employees are paid an allowance now. Whatever used to go to
     everyone without a tag — overtime, late fine, daily wage, and tea or meal
     where no category decided it — is tagged on every active employee of the
     company, so nobody silently stops being paid. Their own gates (OT
     Eligible, Late Fine Exempt, a daily-wage structure) still apply.
  5. The rule fields on Salary Component are hidden: the Company Allowance owns
     them now, per company.

Re-runnable: an existing Company Allowance or employee row is never touched.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt

SECTIONS = "Admin & Accounts\nMarketing\nPlant"

#: Salary Component custom field → Company Allowance field.
RULE_FIELDS = {
	"custom_condition_type": "based_on",
	"custom_unit": "unit",
	"custom_default_rate": "default_rate",
	"custom_half_day_counts": "half_day_counts",
	"custom_pay_on_holiday": "pay_on_holiday",
	"custom_time_offset_hours": "time_offset_hours",
	"custom_holiday_hours_one_meal": "holiday_hours_one_meal",
	"custom_holiday_hours_two_meals": "holiday_hours_two_meals",
	"custom_max_per_day": "max_per_day",
	"custom_rate_basis": "rate_basis",
	"custom_rate_multiplier": "rate_multiplier",
	"custom_rate_days_per_month": "rate_days_per_month",
	"custom_rate_hours_per_day": "rate_hours_per_day",
}
#: Conditions that paid OT-eligible staff only, before the flag existed.
OT_ONLY_CONDITIONS = ("Late Stay After", "Early Entry Before", "Authorised Overtime")
#: Rules that used to apply to everyone, category or not.
ALL_EMPLOYEE_CONDITIONS = OT_ONLY_CONDITIONS + ("Late Time", "Late Arrival After")


def execute():
	frappe.reload_doc("avinash_group_app", "doctype", "company_allowance_item")
	frappe.reload_doc("avinash_group_app", "doctype", "company_allowance")
	frappe.reload_doc("avinash_group_app", "doctype", "employee_attendance_allowance")
	add_fields()
	seed_sections()
	created, paid_to_all = create_company_allowances()
	moved = move_categories()
	tagged = tag_everyone(paid_to_all)
	hide_component_rule_fields()
	print(
		f"Company Allowance: {created} created; {moved} employee rows from Allowance Category; "
		f"{tagged} rows tagging everyone with what was paid to all"
	)


def add_fields():
	create_custom_fields(
		{
			"Department": [
				{
					"fieldname": "custom_payroll_section",
					"label": "Payroll Section",
					"fieldtype": "Select",
					"options": "\n" + SECTIONS,
					"insert_after": "payroll_cost_center",
					"in_list_view": 1,
					"description": (
						"Which of the company's three accounts this department's pay posts to: "
						"Admin & Accounts (O/O), Marketing (S/D) or Plant (F/P)."
					),
				}
			]
		},
		update=True,
	)
	for fieldname, label in (
		("custom_attendance_allowances_section", "Allowances"),
		("custom_attendance_allowances", "Allowances"),
	):
		name = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": fieldname})
		if name:
			frappe.db.set_value("Custom Field", name, "label", label)
	name = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": "custom_attendance_allowances"})
	if name:
		frappe.db.set_value(
			"Custom Field",
			name,
			"description",
			"The allowances this employee gets. Rate blank = the company default on Company Allowance; "
			"untick Eligible to stop one.",
		)
	frappe.clear_cache(doctype="Employee")
	frappe.clear_cache(doctype="Department")


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


def sibling_account(account: str, marker: str) -> str | None:
	"""The S/D or F/P twin of an O/O account, if the chart has one."""
	if "O/O" not in account:
		return None
	twin = account.replace("O/O", marker)
	if frappe.db.exists("Account", twin):
		return twin
	# Numbers differ between the three (547130 / 547131 / 547132): match on the name.
	name_part = account.split(" - ", 1)[1].replace("O/O", marker) if " - " in account else None
	if not name_part:
		return None
	company = frappe.db.get_value("Account", account, "company")
	return frappe.db.get_value("Account", {"company": company, "is_group": 0, "name": ["like", f"% - {name_part}"]})


def create_company_allowances() -> int:
	from avinashgroup_app.payroll.company_allowance import company_allowance_doc

	created = 0
	paid_to_all = []  # (company, component) that went to everyone, untagged
	rows = frappe.get_all(
		"Salary Component Account",
		filters={"parenttype": "Salary Component", "account": ["is", "set"]},
		fields=["parent", "company", "account"],
		order_by="company, parent",
	)
	docs = {}
	for r in rows:
		doc = docs.get(r.company) or docs.setdefault(r.company, company_allowance_doc(r.company))
		if any(row.salary_component == r.parent for row in doc.allowances):
			continue
		sc = frappe.get_doc("Salary Component", r.parent)
		row = {
			"salary_component": sc.name,
			"account_admin": r.account,
			"account_marketing": sibling_account(r.account, "S/D"),
			"account_plant": sibling_account(r.account, "F/P"),
		}
		if sc.get("custom_is_attendance_driven"):
			row["is_attendance_based"] = 1
			for old, new in RULE_FIELDS.items():
				if sc.get(old) not in (None, ""):
					row[new] = sc.get(old)
			row["ot_eligible_only"] = 1 if row.get("based_on") in OT_ONLY_CONDITIONS else 0
			has_category = frappe.db.table_exists("Allowance Category Rate") and frappe.db.exists(
				"Allowance Category Rate", {"salary_component": sc.name}
			)
			# The old engine paid anyone without a category the component's
			# default rate, if it had one; categorised staff are tagged from
			# their category first, so only the rest get this row.
			if (
				not has_category
				or row.get("based_on") in ALL_EMPLOYEE_CONDITIONS
				or flt(sc.get("custom_default_rate"))
			):
				paid_to_all.append((r.company, sc.name))
		else:
			row["calculation"] = "From Salary Structure"
		doc.append("allowances", row)
		created += 1

	for doc in docs.values():
		doc.flags.ignore_permissions = True
		# Old data is moved as it is, even where the new checks would refuse it
		# (an attendance component that also prorates): what paid yesterday
		# pays today, and the record says what to fix when it is next saved.
		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.save()
	return created, paid_to_all


def add_employee_row(employee: str, component: str, rate: float = 0, eligible: int = 1) -> bool:
	"""Tag an employee with an allowance unless they already have a row for it."""
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


def tag_everyone(paid_to_all) -> int:
	tagged = 0
	for company, component in paid_to_all:
		for employee in frappe.get_all("Employee", filters={"company": company, "status": "Active"}, pluck="name"):
			tagged += add_employee_row(employee, component)
	return tagged


def move_categories() -> int:
	if not frappe.db.table_exists("Allowance Category") or not frappe.db.has_column("Employee", "custom_allowance_category"):
		return 0
	moved = 0
	for emp in frappe.get_all(
		"Employee", filters={"custom_allowance_category": ["is", "set"]}, fields=["name", "custom_allowance_category"]
	):
		rates = frappe.get_all(
			"Allowance Category Rate",
			filters={"parent": emp.custom_allowance_category, "parenttype": "Allowance Category"},
			fields=["salary_component", "rate"],
		)
		for rate in rates:
			moved += add_employee_row(emp.name, rate.salary_component, rate.rate, 1 if flt(rate.rate) else 0)

	field = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": "custom_allowance_category"})
	if field:
		frappe.delete_doc("Custom Field", field, force=True, ignore_permissions=True)
	for doctype in ("Allowance Category", "Allowance Category Rate"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
	return moved


def hide_component_rule_fields():
	"""The rule is per company now; the component's own copy would mislead."""
	for fieldname in RULE_FIELDS:
		name = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": fieldname})
		if name:
			frappe.db.set_value("Custom Field", name, "hidden", 1)
	name = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": "custom_is_attendance_driven"})
	if name:
		frappe.db.set_value(
			"Custom Field",
			name,
			{"read_only": 1, "description": "Set from Company Allowance (Attendance Based)."},
		)
	frappe.clear_cache(doctype="Salary Component")
