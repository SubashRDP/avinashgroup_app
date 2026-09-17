"""The group an employee belongs to for holiday-work pay.

Policy from the client meeting of 2026-09-15, minute 2.2 as corrected on
2026-09-16, and minute 2.5 (`docs/hr-decisions/00-policy-minutes-2026-09-15.txt`):
staff below officer level are paid overtime for a holiday or Saturday worked, and
officer and admin level get a replacement leave day instead — never both.

Each category states its own rule, so a third group later (a driver pool, say) is
a new record, not a code change. An Employee carries its category in
`custom_employee_category`, set in bulk with the Employee Category Tool, and
`Employee.custom_ot_eligibility` fetches `ot_eligible` from it — that flag is what
the allowance engine already reads.

Deliberately narrow: this records the rule. Paying the overtime belongs to the
allowance engine, and granting the replacement leave to a separate step that reads
`compensatory_leave`.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class EmployeeCategory(Document):
	def validate(self):
		# The policy is either/or: a holiday worked is paid OR given back as leave.
		if self.ot_eligible and self.compensatory_leave:
			frappe.throw(
				_("A category gets either overtime or replacement leave for holiday work, not both")
			)

	def on_update(self):
		self.sync_employees()

	def sync_employees(self):
		"""Push `ot_eligible` onto everyone already in this category.

		`fetch_from` only refreshes the Employee field when the Employee is saved,
		so changing the rule here would otherwise leave every existing member on
		the old value until somebody happened to edit them.
		"""
		if not self.has_value_changed("ot_eligible"):
			return

		frappe.db.sql(
			"""update `tabEmployee` set custom_ot_eligibility = %s
			where custom_employee_category = %s""",
			(1 if self.ot_eligible else 0, self.name),
		)
