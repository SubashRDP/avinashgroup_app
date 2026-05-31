import frappe
from frappe.model.document import Document


class FiscalYearAccessControl(Document):
    def on_update(self):
        frappe.cache().delete_value(f"user_fiscal_access_{self.user}")

    def on_trash(self):
        frappe.cache().delete_value(f"user_fiscal_access_{self.user}")

