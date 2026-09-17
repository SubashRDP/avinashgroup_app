"""Put many employees into an Employee Category at once.

Setting the category employee by employee is the job this replaces: 295 staff
across seven companies, where the one person missed is paid overtime they are not
owed, or denied the replacement leave they are. It works the way the HRMS Shift
Assignment Tool does — filters on top, a checkbox grid of the employees they
match, one button — and reuses the same `hrms.*` front-end helpers, so it looks
and behaves like the tools HR already uses.

The list leaves out anyone already in the chosen category, so what is shown is
only who would actually change.

Each employee is saved through the ORM, not written with SQL: `fetch_from` then
sets `custom_ot_eligibility` from the category, and the change lands in the
employee's history. One employee failing validation is reported and skipped; it
does not stop the rest.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from hrms.hr.utils import notify_bulk_action_status, validate_bulk_tool_fields

QUICK_FILTER_FIELDS = ("company", "branch", "department", "designation")


class EmployeeCategoryTool(Document):
	@frappe.whitelist()
	def get_employees(self, advanced_filters: list | None = None) -> list:
		"""Active employees matching the filters and not already in the category."""
		if not self.employee_category:
			return []

		filters = [["status", "=", "Active"]]
		for field in QUICK_FILTER_FIELDS:
			if self.get(field):
				filters.append([field, "=", self.get(field)])

		# Frappe's != keeps rows where the field is empty, which is what we want:
		# the uncategorised are exactly the people most in need of a category.
		filters.append(["custom_employee_category", "!=", self.employee_category])

		if self.only_uncategorised:
			filters.append(["custom_employee_category", "is", "not set"])
		elif self.current_category:
			filters.append(["custom_employee_category", "=", self.current_category])

		return frappe.get_list(
			"Employee",
			filters=filters + (advanced_filters or []),
			fields=[
				"name as employee",
				"employee_name",
				"company",
				"department",
				"designation",
				"custom_employee_category",
			],
			order_by="company asc, name asc",
			limit_page_length=0,
		)

	@frappe.whitelist()
	def bulk_assign(self, employees: list):
		validate_bulk_tool_fields(self, ["employee_category"], employees)

		success, failure = [], []
		for employee in employees:
			savepoint = "before_category_assignment"
			try:
				frappe.db.savepoint(savepoint)
				doc = frappe.get_doc("Employee", employee)
				doc.custom_employee_category = self.employee_category
				doc.save()
				success.append({"doc": employee, "employee": employee})
			except Exception:
				frappe.db.rollback(save_point=savepoint)
				frappe.log_error(
					title="Employee Category assignment failed",
					message=f"employee={employee} category={self.employee_category}\n{frappe.get_traceback()}",
					reference_doctype="Employee",
					reference_name=employee,
				)
				failure.append(employee)

		frappe.db.commit()
		notify_bulk_action_status("Employee", failure, success)
		return {"success": len(success), "failure": failure}
