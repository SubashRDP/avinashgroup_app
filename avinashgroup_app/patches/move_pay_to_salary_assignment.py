"""Pay moves off the Employee onto the Salary Structure Assignment.

Each allowance had its own Employee field (Dearness Allowance, Other, Fuel,
Fixed, Maintenance; ticks for HRA, Gas, Education), read by a structure
formula, plus Initial Basic and SSF Applicable, and a separate table held
exceptions to attendance allowances. A new allowance meant a new field and a
new structure, and anyone who could edit an employee saw their pay.

Now the assignment carries it (payroll/allowance.py): Initial Basic, SSF
Applicable, and an Allowances table (Assignment Allowance: allowance, amount,
active, from date). The structure formulas keep working unchanged: HRMS puts
the assignment's fields in scope, and with the Employee's same-named fields
gone nothing shadows them.

This patch, re-runnable:

  1. Adds the assignment's Pay Details and Allowances sections.
  2. Copies each employee's old values onto their latest submitted assignment:
     Initial Basic, SSF Applicable, an amount row for each per-person
     allowance, a blank (company rate) row for an HRA / Gas / Education tick,
     and the old exception rows (tea at 40, an unticked row for no tea).
  3. Reads the company rates the old structures wrote into their formulas
     (gas 1690, education 2780, HRA 0.25) onto each component's Accounts row
     for that company, as Default Rate (HRA as 25).
  4. Removes the old Employee fields, the old table and Salary Component's
     single Default Rate. A field is kept, and printed, while a submitted
     active structure's formula still reads it, or while an employee with no
     assignment still holds a value in it — nothing is dropped unmoved.
"""

import re

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt

#: Old Employee allowance field → (allowance, how the value is read).
OLD_FIELDS = {
	"custom_dearness_allowance": ("Dearness Allowance", "amount"),
	"custom_other_allowance": ("Other Allowance", "amount"),
	"custom_fuel_allowance": ("Fuel Allowance", "amount"),
	"custom_fixed_allowance": ("Fixed Allowance", "amount"),
	"custom_maintenance_allowance": ("Maintenance Allowance", "amount"),
	"custom_hra_eligible": ("House Rent Allowance", "tick"),
	"custom_gas_allowance": ("Gas Allowance", "tick"),
	"custom_education_allowance": ("Education Allowance", "tick"),
}
#: Old Employee fields that become the assignment's own (same names).
MOVED_FIELDS = ("custom_initial_basic", "custom_ssf_applicable")
#: Layout-only Employee fields that go with them.
LAYOUT_FIELDS = (
	"custom_payroll_inputs_section",
	"custom_payroll_inputs_cb",
	"custom_attendance_allowances_section",
	"custom_attendance_allowances",
)
OLD_TABLE = "Employee Attendance Allowance"
#: Allowances whose company rate the old structures kept in their formula.
RATE_IN_FORMULA = {"Gas Allowance": 1, "Education Allowance": 1, "House Rent Allowance": 100}


def execute():
	frappe.reload_doc("avinash_group_app", "doctype", "assignment_allowance")
	add_fields()
	moved, unassigned = move_to_assignments()
	rates = rates_from_structures()
	kept = remove_old(unassigned)
	for doctype in ("Employee", "Salary Structure Assignment", "Salary Component"):
		frappe.clear_cache(doctype=doctype)
	print(f"Pay on assignments: {moved} allowance rows; {rates} company rates read from structure formulas")
	if kept:
		print(f"  Employee fields kept: {', '.join(kept)} (still read by a structure, or held by employees with no assignment)")


def add_fields():
	create_custom_fields(
		{
			"Salary Structure Assignment": [
				{
					"fieldname": "custom_pay_details_section",
					"label": "Pay Details",
					"fieldtype": "Section Break",
					"insert_after": "variable",
				},
				{
					"fieldname": "custom_initial_basic",
					"label": "Initial Basic",
					"fieldtype": "Currency",
					"insert_after": "custom_pay_details_section",
					"description": "NGI / NGN: the basic HRA is a percentage of.",
				},
				{
					"fieldname": "custom_pay_details_cb",
					"fieldtype": "Column Break",
					"insert_after": "custom_initial_basic",
				},
				{
					"fieldname": "custom_ssf_applicable",
					"label": "SSF Applicable",
					"fieldtype": "Check",
					"default": "1",
					"insert_after": "custom_pay_details_cb",
					"description": "Adds 20 % and deducts 31 % of Basic; without it the 1 % SST applies.",
				},
				{
					"fieldname": "custom_allowances_section",
					"label": "Allowances",
					"fieldtype": "Section Break",
					"insert_after": "custom_ssf_applicable",
				},
				{
					"fieldname": "custom_allowances",
					"label": "Allowances",
					"fieldtype": "Table",
					"options": "Assignment Allowance",
					"insert_after": "custom_allowances_section",
					"description": (
						"Every allowance this person gets. Amount: their own monthly figure for a "
						"per-person allowance (dearness, other, fuel); blank = the company's rate "
						"(gas, education, HRA %, tea, meal). Untick Active to stop one. Tea, meal "
						"and overtime also come from the Salary Structure; a row here gives this "
						"person their own rate or stops it."
					),
				},
			]
		},
		update=True,
	)


def latest_assignment(employee: str):
	return frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1},
		["name", "custom_initial_basic", "custom_ssf_applicable"],
		as_dict=True,
		order_by="from_date desc",
	)


def add_row(assignment: str, allowance: str, amount=0.0, active=1, effective_from=None) -> bool:
	if not frappe.db.exists("Salary Component", allowance) or frappe.db.exists(
		"Assignment Allowance",
		{"parent": assignment, "parenttype": "Salary Structure Assignment", "allowance": allowance},
	):
		return False
	idx = frappe.db.count("Assignment Allowance", {"parent": assignment, "parenttype": "Salary Structure Assignment"}) + 1
	child = frappe.new_doc("Assignment Allowance")
	child.update(
		{
			"parent": assignment,
			"parenttype": "Salary Structure Assignment",
			"parentfield": "custom_allowances",
			"idx": idx,
			"allowance": allowance,
			"amount": flt(amount),
			"active": active,
			"effective_from": effective_from,
		}
	)
	child.db_insert()
	return True


def move_to_assignments():
	"""Copy old Employee pay onto latest assignments; returns (rows, employees
	that hold old values but have no assignment)."""
	old_rows = {}
	if frappe.db.table_exists(OLD_TABLE):
		# Plain SQL: the doctype record may already be gone.
		for r in frappe.db.sql(
			f"""select parent, salary_component, rate, eligible, effective_from from `tab{OLD_TABLE}`
			where parenttype = 'Employee'""",
			as_dict=True,
		):
			old_rows.setdefault(r.parent, []).append(r)

	fields = [f for f in (*OLD_FIELDS, *MOVED_FIELDS) if frappe.db.has_column("Employee", f)]
	moved, unassigned = 0, set()
	for emp in frappe.get_all("Employee", fields=["name", *fields]):
		holds = any(flt(emp.get(f)) for f in fields if f != "custom_ssf_applicable") or emp.name in old_rows
		assignment = latest_assignment(emp.name)
		if not assignment:
			if holds:
				unassigned.add(emp.name)
			continue

		values = {}
		if "custom_initial_basic" in fields and not flt(assignment.custom_initial_basic) and flt(emp.custom_initial_basic):
			values["custom_initial_basic"] = emp.custom_initial_basic
		if "custom_ssf_applicable" in fields:
			values["custom_ssf_applicable"] = 1 if emp.custom_ssf_applicable else 0
		if values:
			frappe.db.set_value("Salary Structure Assignment", assignment.name, values, update_modified=False)

		for field in fields:
			if field not in OLD_FIELDS:
				continue
			allowance, how = OLD_FIELDS[field]
			value = flt(emp.get(field))
			if value:
				moved += add_row(assignment.name, allowance, value if how == "amount" else 0)
		for r in old_rows.get(emp.name, []):
			moved += add_row(assignment.name, r.salary_component, r.rate, 1 if r.eligible else 0, r.effective_from)
	return moved, unassigned


def rates_from_structures() -> int:
	set_count = 0
	rows = frappe.db.sql(
		"""select ss.company, sd.salary_component, sd.formula
		from `tabSalary Structure` ss
		join `tabSalary Detail` sd on sd.parent = ss.name and sd.parenttype = 'Salary Structure'
		where ss.docstatus = 1 and sd.salary_component in %s and ifnull(sd.formula, '') != ''""",
		(tuple(RATE_IN_FORMULA),),
		as_dict=True,
	)
	for r in rows:
		numbers = re.findall(r"\d+(?:\.\d+)?", r.formula)
		if not numbers:
			continue
		rate = flt(numbers[0]) * RATE_IN_FORMULA[r.salary_component]
		doc = frappe.get_doc("Salary Component", r.salary_component)
		row = next((a for a in doc.accounts if a.company == r.company), None)
		if row and flt(row.custom_default_rate):
			continue
		if not row:
			row = doc.append("accounts", {"company": r.company})
		row.custom_default_rate = rate
		doc.flags.ignore_permissions = True
		doc.save()
		set_count += 1
	return set_count


def still_read(field: str) -> bool:
	return bool(
		frappe.db.sql(
			"""select 1 from `tabSalary Structure` ss
			join `tabSalary Detail` sd on sd.parent = ss.name and sd.parenttype = 'Salary Structure'
			where ss.docstatus = 1 and ss.is_active = 'Yes'
			  and (sd.formula like %(f)s or sd.`condition` like %(f)s) limit 1""",
			{"f": f"%{field}%"},
		)
	)


def remove_old(unassigned) -> list:
	kept = []
	for field in (*OLD_FIELDS, *MOVED_FIELDS, *LAYOUT_FIELDS):
		# Initial Basic and SSF Applicable are read by the formulas from the
		# assignment now (same names), so only the allowance fields count here.
		if field in OLD_FIELDS and still_read(field):
			kept.append(field)
			continue
		if unassigned and field in (*OLD_FIELDS, *MOVED_FIELDS, "custom_attendance_allowances"):
			kept.append(field)
			continue
		name = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": field})
		if name:
			frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)

	if not unassigned:
		if frappe.db.exists("DocType", OLD_TABLE):
			frappe.delete_doc("DocType", OLD_TABLE, force=True, ignore_permissions=True)
		if frappe.db.table_exists(OLD_TABLE):
			frappe.db.sql_ddl(f"drop table `tab{OLD_TABLE}`")
	elif kept:
		print(f"  employees holding pay with no assignment: {', '.join(sorted(unassigned)[:20])}")

	# One rate for every company is replaced by Default Rate per company on the
	# Accounts rows (setup_allowance_kinds copied it there).
	name = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": "custom_default_rate"})
	if name:
		frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
	return kept
