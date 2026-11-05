"""Field Duty — controller. The rule itself lives in hr/field_duty.py."""

from frappe.model.document import Document

from avinashgroup_app.hr import field_duty as rule


class FieldDuty(Document):
	def validate(self):
		rule.validate_duty(self)

	def on_submit(self):
		rule.apply_duty(self)

	def on_cancel(self):
		rule.apply_duty(self, cancelling=True)
