import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class BiometricDeviceCommand(Document):
    def before_insert(self):
        if not self.requested_by:
            self.requested_by = frappe.session.user
        if not self.requested_at:
            self.requested_at = now_datetime()
        if not self.status:
            self.status = "Pending"

    def validate(self):
        if self.status not in ("Pending", "Running", "Done", "Failed"):
            frappe.throw(_("Invalid status {0}").format(self.status))
