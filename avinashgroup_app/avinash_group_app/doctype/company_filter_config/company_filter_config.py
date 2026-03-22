import frappe
from frappe.model.document import Document


class CompanyFilterConfig(Document):

    def on_update(self):
        frappe.cache().delete_value("company_filter_config")
        frappe.msgprint(
            f"Company Filter cache cleared for <b>{self.name}</b>. Refresh your browser to apply changes.",
            indicator="green",
            alert=True
        )

    def on_trash(self):
        frappe.cache().delete_value("company_filter_config")
