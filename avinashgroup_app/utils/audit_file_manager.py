import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


class AuditBase:
    doctypes = [
        "Quotation",
        "Request for Quotation",
        "Supplier Quotation",
        "Purchase Order",
        "Stock Entry",
        "Holiday List",
        "Customer",
        "Supplier",
        "Employee",
        "Stock Reconciliation",
        "Payment Entry",
        "Delivery Note",
        "Sales Order",
        "Purchase Receipt",
        "Journal Entry",
        "Purchase Invoice",
        "Material Request",
        "Sales Invoice"
    ]


class AuditFieldsManager(AuditBase):

    def __init__(self):
        self.custom_fields = {}

    def get_field_definitions(self):
        return [
            {
                "fieldname": "custom_created_by",
                "label": "Created By",
                "fieldtype": "Link",
                "options": "User",
                "insert_after": None,
                "read_only": 1,
                "no_copy": 1,
                "print_hide": 1,
                "is_standard_filter":1,
            },
            {
                "fieldname": "custom_created_on",
                "label": "Created On",
                "fieldtype": "Datetime",
                "insert_after": "custom_created_by",
                "read_only": 1,
                "no_copy": 1,
                "print_hide": 1,
                "is_standard_filter":1,
            },
            {
                "fieldname": "custom_modified_by",
                "label": "Modified By",
                "fieldtype": "Link",
                "options": "User",
                "insert_after": "custom_created_on",
                "read_only": 1,
                "no_copy": 1,
                "print_hide": 1,
                "is_standard_filter":1,
            }
        ]

    def prepare_custom_fields(self):
        field_definitions = self.get_field_definitions()
        for doctype in self.doctypes:
            self.custom_fields[doctype] = field_definitions
        return self.custom_fields

    def create_fields(self):
        try:
            self.prepare_custom_fields()
            create_custom_fields(self.custom_fields, update=True)
            frappe.db.commit()
            return {"success": True, "message": f"Custom fields added to {len(self.doctypes)} doctypes!"}
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "message": str(e)}

    def remove_fields(self):
        try:
            for doctype in self.doctypes:
                for field in ["custom_created_by", "custom_created_on", "custom_modified_by"]:
                    custom_field = frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field})
                    if custom_field:
                        frappe.delete_doc("Custom Field", custom_field)
            frappe.db.commit()
            return {"success": True, "message": "Custom fields removed!"}
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "message": str(e)}

    def verify_fields(self):
        report = {}
        for doctype in self.doctypes:
            fields_status = {}
            for field in ["custom_created_by", "custom_created_on", "custom_modified_by"]:
                exists = frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field})
                fields_status[field] = "✓ Exists" if exists else "✗ Missing"
            report[doctype] = fields_status
        return report

    @staticmethod
    def set_audit_fields(doc, method=None):
        """Set audit fields on document insert and save"""
        if doc.is_new():
            doc.custom_created_by = frappe.session.user
            doc.custom_created_on = frappe.utils.now_datetime()
        doc.custom_modified_by = frappe.session.user


class AuditEventMapper(AuditBase):
    """Maps audit field handlers to document events"""

    @staticmethod
    def get_doc_events():
        """Returns a dictionary of document events for all doctypes
        
        Returns a dict with string paths (not function objects) for Frappe hooks
        """
        handler_path = "avinashgroup_app.utils.audit_file_manager.set_audit_fields"
        
        events = {}

        for dt in AuditEventMapper.doctypes:


            events[dt] = {
                "before_insert": handler_path,
                "before_save": handler_path,
            
            }

        return events


# Standalone function for hooks to call
def set_audit_fields(doc, method=None):
    # Default to UI
    from_ui = False

    # 1️⃣ Check if we are in a web request context (desk UI)
    if hasattr(frappe.local, "request") and frappe.local.request:
        from_ui = True

    # 2️⃣ Optionally, check if this is a Data Import job
    # frappe.flags.in_import is True when importing from Excel / CSV
    if getattr(frappe.flags, "in_import", False):
        from_ui = False

    if from_ui:
        if doc.is_new():
            doc.custom_created_by = frappe.session.user
            doc.custom_created_on = frappe.utils.now_datetime()
        doc.custom_modified_by = frappe.session.user

  

    




