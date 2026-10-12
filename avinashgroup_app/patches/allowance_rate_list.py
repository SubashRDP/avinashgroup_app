"""Allowance rates move to the structure's rate list; payroll reads only the assignment.

Before: a company's usual rate (tea 235, gas 1,690, HRA 25 %) was Default Rate
on the component's Accounts row; an assignment row with no figure meant "the
company's rate", an unticked one "not paid"; and a Tea / Meal / Overtime row in
the structure's Earnings gave the allowance to everyone on it.

After (payroll/allowance.py):
  * the component holds no rate;
  * each Salary Structure lists the usual rates (Allowance Rates);
  * each assignment row carries the rate the person is paid, and an allowance
    with no row is not paid.

So, without changing anybody's pay:
  1. Add Allowance Rates to Salary Structure; rename the kinds by how they are
     counted (Fixed per Person and Fixed Company Rate are both Monthly).
  2. Copy each row's old Amount into Rate.
  3. Each structure lists its company's Default Rates, the allowances its
     people carry, and its old tag allowances.
  4. Each submitted assignment gets an explicit row for each tag allowance it
     was paid through the structure, the company rate on every row that relied
     on it, and loses the rows that said "not paid".
  5. The tag rows leave the structures' Earnings; Default Rate leaves the
     component's Accounts rows.

Prints one line of counts. Safe to run again.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt

from avinashgroup_app.payroll.allowance import (
	ALLOWANCE_KINDS,
	COMPUTED_RATE_BASIS,
	MONTHLY,
	PER_OVERTIME_HOUR,
	unit_for,
)

KIND_RENAMES = {
	"Fixed per Person": MONTHLY,
	"Fixed Company Rate": MONTHLY,
	"Per Hour (Overtime)": PER_OVERTIME_HOUR,
}
#: Written by move_pay_to_salary_assignment for a "not paid" row.
EXCLUDED_RATE = -1


def execute():
	for doctype in ("structure_allowance_rate", "assignment_allowance"):
		frappe.reload_doc("avinash_group_app", "doctype", doctype)
	add_fields()
	renamed = rename_kinds()
	frappe.clear_cache(doctype="Salary Component")
	copied = copy_amount_to_rate()

	default_rates = company_default_rates()
	listed = rows_added = rates_filled = removed = 0
	for structure in frappe.get_all("Salary Structure", filters={"docstatus": ["<", 2]}, fields=["name", "company"]):
		tags = tag_allowances(structure.name)
		company_rates = default_rates.get(structure.company, {})
		listed += list_rates(structure, tags, company_rates)
		for assignment in frappe.get_all(
			"Salary Structure Assignment",
			filters={"salary_structure": structure.name, "docstatus": 1},
			pluck="name",
		):
			a, f, r = settle_assignment(assignment, tags, company_rates)
			rows_added += a
			rates_filled += f
			removed += r
		drop_tag_rows(structure.name, tags)

	fill_units()
	remove_default_rate_field()
	frappe.clear_cache(doctype="Salary Structure")
	frappe.clear_cache(doctype="Salary Structure Assignment")
	print(
		f"allowance_rate_list: {renamed} kinds renamed, {copied} amounts copied to rate, "
		f"{listed} structure rates listed, {rows_added} assignment rows added for structure tags, "
		f"{rates_filled} company rates written onto rows, {removed} 'not paid' rows removed"
	)


def add_fields():
	create_custom_fields(
		{
			"Salary Structure": [
				{
					"fieldname": "custom_allowance_rates_section",
					"label": "Allowance Rates",
					"fieldtype": "Section Break",
					"insert_after": "deductions",
					"allow_on_submit": 1,
				},
				{
					"fieldname": "custom_allowance_rates",
					"label": "Allowance Rates",
					"fieldtype": "Table",
					"options": "Structure Allowance Rate",
					"insert_after": "custom_allowance_rates_section",
					"allow_on_submit": 1,
					"description": (
						"The usual rate of each allowance for people on this structure. Picking the "
						"allowance on a Salary Structure Assignment fills in this rate; who gets which "
						"allowance is each person's assignment. To raise a rate, make a Salary Revision "
						"(Raise Rate): it moves the people on it too."
					),
				},
			]
		},
		update=True,
	)
	name = frappe.db.get_value("Custom Field", {"dt": "Salary Component", "fieldname": "custom_allowance_kind"})
	if name:
		frappe.db.set_value(
			"Custom Field",
			name,
			{
				"options": "\n" + "\n".join(ALLOWANCE_KINDS),
				"description": (
					"How the allowance is counted. Monthly, % of Initial Basic: a fixed amount each month. "
					"Per Day Present, Per Meal, Per Overtime Hour: counted from attendance each month "
					"(Prepare Payroll Inputs). Entered by Hand: typed as Additional Salary. Yearly: its "
					"own button. The rate is on the salary structure (usual) and the assignment (the person's)."
				),
			},
		)


def rename_kinds() -> int:
	renamed = 0
	for old, new in KIND_RENAMES.items():
		for name in frappe.get_all("Salary Component", filters={"custom_allowance_kind": old}, pluck="name"):
			frappe.db.set_value("Salary Component", name, "custom_allowance_kind", new, update_modified=False)
			renamed += 1
	return renamed


def _columns(doctype: str) -> set:
	return set(frappe.db.get_table_columns(doctype))


def copy_amount_to_rate() -> int:
	if "amount" not in _columns("Assignment Allowance"):
		return 0
	frappe.db.sql(
		"""update `tabAssignment Allowance` set rate = amount
		where ifnull(rate, 0) = 0 and ifnull(amount, 0) <> 0"""
	)
	return frappe.db.sql("select row_count()")[0][0]


def company_default_rates() -> dict:
	"""{company: {allowance: rate}} from the old Default Rate on Accounts rows."""
	if "custom_default_rate" not in _columns("Salary Component Account"):
		return {}
	out = {}
	for r in frappe.db.sql(
		"""select company, parent, custom_default_rate from `tabSalary Component Account`
		where parenttype = 'Salary Component' and ifnull(custom_default_rate, 0) <> 0""",
		as_dict=True,
	):
		out.setdefault(r.company, {})[r.parent] = flt(r.custom_default_rate)
	return out


def tag_allowances(structure: str) -> list:
	"""The allowances the structure's Earnings / Deductions gave to everyone on it."""
	return frappe.db.sql_list(
		"""select sd.salary_component from `tabSalary Detail` sd
		join `tabSalary Component` sc on sc.name = sd.salary_component
		where sd.parent = %s and sd.parenttype = 'Salary Structure' and sc.custom_is_allowance = 1""",
		structure,
	)


def _computed(allowance: str) -> bool:
	return frappe.db.get_value("Salary Component", allowance, "custom_rate_basis") == COMPUTED_RATE_BASIS


def list_rates(structure, tags: list, company_rates: dict) -> int:
	"""The structure's rate list: its company's rates for what its people carry or its tags give."""
	carried = frappe.db.sql_list(
		"""select distinct aa.allowance from `tabAssignment Allowance` aa
		join `tabSalary Structure Assignment` ssa on ssa.name = aa.parent
		where ssa.salary_structure = %s and ssa.docstatus = 1 and aa.parenttype = 'Salary Structure Assignment'""",
		structure.name,
	)
	wanted = []
	for allowance in [*tags, *sorted(carried)]:
		if allowance not in wanted and frappe.db.get_value("Salary Component", allowance, "custom_is_allowance"):
			wanted.append(allowance)
	have = set(
		frappe.get_all(
			"Structure Allowance Rate",
			filters={"parent": structure.name, "parenttype": "Salary Structure"},
			pluck="allowance",
		)
	)
	added = 0
	for allowance in wanted:
		if allowance in have:
			continue
		rate = 0 if _computed(allowance) else company_rates.get(allowance, 0)
		_insert_child(
			"Structure Allowance Rate", "Salary Structure", structure.name, "custom_allowance_rates",
			{"allowance": allowance, "rate": rate},
		)
		added += 1
	return added


def settle_assignment(assignment: str, tags: list, company_rates: dict) -> tuple:
	"""Make the assignment's rows say exactly what it was paid. Returns (added, filled, removed)."""
	columns = _columns("Assignment Allowance")
	fields = ["name", "allowance", "rate"] + (["active"] if "active" in columns else [])
	rows = frappe.get_all(
		"Assignment Allowance",
		filters={"parent": assignment, "parenttype": "Salary Structure Assignment"},
		fields=fields,
	)
	added = filled = removed = 0
	by_allowance = {r.allowance: r for r in rows}

	for row in rows:
		excluded = flt(row.rate) == EXCLUDED_RATE or ("active" in row and not row.active)
		if excluded:
			frappe.db.delete("Assignment Allowance", {"name": row.name})
			removed += 1
			continue
		if flt(row.rate) or _computed(row.allowance):
			continue
		rate = company_rates.get(row.allowance, 0)
		if rate:
			frappe.db.set_value("Assignment Allowance", row.name, "rate", rate, update_modified=False)
			filled += 1
		else:
			# No figure and no company rate: the old code paid nothing for it.
			frappe.db.delete("Assignment Allowance", {"name": row.name})
			removed += 1

	for allowance in tags:
		if allowance in by_allowance:
			continue
		rate = 0 if _computed(allowance) else company_rates.get(allowance, 0)
		if not rate and not _computed(allowance):
			# A tag with no company rate paid nothing.
			continue
		_insert_child(
			"Assignment Allowance", "Salary Structure Assignment", assignment, "custom_allowances",
			{"allowance": allowance, "rate": rate},
		)
		added += 1
	return added, filled, removed


def _insert_child(doctype, parenttype, parent, parentfield, values):
	idx = frappe.db.count(doctype, {"parent": parent, "parenttype": parenttype}) + 1
	child = frappe.new_doc(doctype)
	child.update({"parent": parent, "parenttype": parenttype, "parentfield": parentfield, "idx": idx, **values})
	child.db_insert()


def drop_tag_rows(structure: str, tags: list):
	if tags:
		frappe.db.delete(
			"Salary Detail",
			{"parent": structure, "parenttype": "Salary Structure", "salary_component": ["in", tags]},
		)


def fill_units():
	"""The Unit column the forms show, on every existing row."""
	for doctype in ("Structure Allowance Rate", "Assignment Allowance"):
		for allowance in frappe.get_all(doctype, distinct=True, pluck="allowance"):
			frappe.db.sql(
				f"update `tab{doctype}` set unit = %s where allowance = %s", (unit_for(allowance), allowance)
			)


def remove_default_rate_field():
	name = frappe.db.get_value("Custom Field", {"dt": "Salary Component Account", "fieldname": "custom_default_rate"})
	if name:
		frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
