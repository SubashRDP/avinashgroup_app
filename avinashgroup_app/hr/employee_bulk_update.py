"""Set the same HR field on many employees at once.

Employee setup here is group-shaped, not person-shaped: 295 staff need a Grade
(which decides OT eligibility, and through it who gets replacement leave for
holiday work), women need their company's (Women) Holiday List, and plant staff
need a Default Shift. Doing that one form at a time is a day's clicking, and the
one person missed is found in payroll.

Stock ERPNext offers list-view Bulk Edit and Data Import for this. Both work, but
neither shows who is *missing* the value, which is the question being asked
("who still has no Grade?"), and Data Import needs a spreadsheet round trip for
what is one value.

Entry point is the `Employee Bulk Update` single doctype, which collects the
filters and calls `get_employees()` then `apply_values()`.

Deliberately narrow:
  * four fields only — Grade, Holiday List, Default Shift, OT Eligible. Anything
    else is a Data Import, deliberately, so this never becomes a way to edit
    arbitrary employee data without a trace.
  * every employee is saved through the ORM, so hooks and fetch-from still run
    and the change lands in the version history.
  * a save that fails is reported and skipped; the rest still go through.
"""

import frappe
from frappe import _

# Fields this tool is allowed to touch, and the doctype field each value comes
# from on the tool itself.
TARGET_FIELDS = {
	"grade": "new_grade",
	"holiday_list": "new_holiday_list",
	"default_shift": "new_default_shift",
	"custom_ot_eligibility": "new_ot_eligible",
}

FILTER_FIELDS = ("company", "department", "designation", "branch", "employment_type", "gender", "grade")


def get_employees(filters, only_missing_field=None):
	"""Active employees matching `filters`.

	`only_missing_field` limits the answer to employees where that field is
	empty — the "who still has no Grade?" question. Returns the columns the tool
	shows, so the operator can see what they are about to change.
	"""
	conditions = {"status": "Active"}
	for field in FILTER_FIELDS:
		value = filters.get(field)
		if value:
			conditions[field] = value

	if only_missing_field:
		conditions[only_missing_field] = ["in", ["", None]]

	return frappe.get_all(
		"Employee",
		filters=conditions,
		fields=[
			"name",
			"employee_name",
			"company",
			"department",
			"designation",
			"gender",
			"grade",
			"holiday_list",
			"default_shift",
			"custom_ot_eligibility",
		],
		order_by="company asc, name asc",
		limit_page_length=0,
	)


def apply_values(employees, values):
	"""Write `values` (fieldname -> value) on each employee. Returns a report.

	Saved through `Document.save()` rather than `db_set` so fetch-from fields
	(Employee.custom_ot_eligibility follows its Grade) and any doc_event hook
	still run. One employee failing validation must not stop the rest, so the
	failure is logged with the employee id and collected.
	"""
	values = {k: v for k, v in values.items() if v not in (None, "")}
	if not values:
		frappe.throw(_("Nothing to set — fill at least one value"))
	if not employees:
		frappe.throw(_("Select at least one employee"))

	changed, unchanged, failed = [], [], []
	for employee in employees:
		doc = frappe.get_doc("Employee", employee)
		if all(str(doc.get(field) or "") == str(value) for field, value in values.items()):
			unchanged.append(employee)
			continue

		try:
			savepoint = "before_employee_update"
			frappe.db.savepoint(savepoint)
			doc.update(values)
			doc.save(ignore_permissions=True)
			changed.append(f"{employee} {doc.employee_name}")
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(
				title="Employee Bulk Update failed",
				message=f"employee={employee} values={values}\n{frappe.get_traceback()}",
			)
			failed.append(employee)

	frappe.db.commit()
	return {"changed": changed, "unchanged": unchanged, "failed": failed}
