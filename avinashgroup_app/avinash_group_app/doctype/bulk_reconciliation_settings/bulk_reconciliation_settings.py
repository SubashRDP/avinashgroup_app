import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

SETTINGS = "Bulk Reconciliation Settings"


class BulkReconciliationSettings(Document):
	def validate(self):
		if cint(self.interval_hours) < 1:
			frappe.throw(_("Run Every (Hours) must be at least 1"))

		# Each switch-on starts a new window, so entries from before it stay out.
		if self.enabled and self.has_value_changed("enabled"):
			self.started_from = now_datetime()
			self.is_stopped = 0


@frappe.whitelist()
def stop_auto_run():
	"""Stop button: the scheduled job does nothing until Resume."""
	set_stopped(1)


@frappe.whitelist()
def resume_auto_run():
	"""Resume button: the next scheduled run works again. Started From is not
	changed, so entries made while stopped are picked up too."""
	set_stopped(0)


def set_stopped(value):
	frappe.has_permission(SETTINGS, "write", throw=True)
	frappe.db.set_single_value(SETTINGS, "is_stopped", value)
