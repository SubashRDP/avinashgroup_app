"""Shift Early Closure — controller. The rule itself lives in hr/shift_early_closure.py."""

from frappe.model.document import Document

from avinashgroup_app.hr import shift_early_closure as rule


class ShiftEarlyClosure(Document):
	def validate(self):
		rule.validate_closure(self)

	def on_submit(self):
		rule.apply_closure(self)

	def on_cancel(self):
		rule.apply_closure(self, cancelling=True)
