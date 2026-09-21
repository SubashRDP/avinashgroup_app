"""A group of employees paid the same rate for an attendance-driven allowance.

Tea & conveyance at NGI is the case this was built for: the Falgun sheet pays
235 a day to one group and 40 a day to another, decided by a category on each
employee, not by their department — plant has both, and so does the office.

Putting the rate here means two things HR asked for:

  * moving one person between groups changes what they are paid, by editing one
    field on their Employee record;
  * changing what a group is paid — 235 becomes 250 — is one edit here, not 51.

A category can carry a rate for several components at once (tea today, meals or
an OT multiplier later), so a new group is a record, not a code change.

Read by `avinashgroup_app.payroll.attendance_allowance`, which resolves a rate as:
employee's own override row -> this category -> the component's default rate.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class AllowanceCategory(Document):
	def validate(self):
		seen = set()
		for row in self.rates:
			if row.salary_component in seen:
				frappe.throw(_("{0} is listed twice").format(row.salary_component))
			seen.add(row.salary_component)


def validate_employee_category(doc, method=None):
	"""An employee may only be put in a category of their own company.

	Hook: doc_events -> Employee -> validate. NGI pays tea at 235 a day and NGN at
	265; picking the wrong company's category would quietly pay the wrong rate.
	"""
	category = doc.get("custom_allowance_category")
	if not category:
		return
	company = frappe.db.get_value("Allowance Category", category, "company")
	if company and company != doc.company:
		frappe.throw(
			_("Allowance Category {0} belongs to {1}, not {2}").format(category, company, doc.company)
		)
