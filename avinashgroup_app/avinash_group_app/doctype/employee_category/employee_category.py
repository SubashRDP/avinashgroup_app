"""A named group of employees — a label only, since 2026-10-13.

It used to decide holiday-work pay (policy 2.2 as corrected 2026-09-16, and 2.5:
overtime for staff below officer level, a replacement leave day for officer and
admin level — never both), with `Employee.custom_ot_eligibility` fetched from
`ot_eligible`. HR asked for that answer on the Employee itself, so it is now two
ticks there — Overtime Eligible (`custom_ot_eligibility`) and Replacement Leave
for Holiday Work (`custom_compensatory_leave`) — set per person and read by
`hr/overtime.py`, the allowance engine and the reports. Patch
`holiday_work_rule_on_employee` copied every member's answer across.

Nothing reads `ot_eligible` / `compensatory_leave` here any more, and editing a
category no longer touches its members. The record and the Employee link are kept
until HR decides whether the grouping is still wanted.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class EmployeeCategory(Document):
	def validate(self):
		if self.ot_eligible and self.compensatory_leave:
			frappe.throw(
				_("A category gets either overtime or replacement leave for holiday work, not both")
			)
