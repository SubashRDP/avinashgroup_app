import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from avinashgroup_app.custom_code.Override.naming_series import handle_validate, naming_series_autoname
from avinashgroup_app.custom_code.globalfilter.globalfilter import validate_company_matching

class AuditBase:
    doctypes = [
    "Address",
    "Appointment Letter",
    "Asset Capitalization",
    "Asset Movement",
    "Asset Repair",
    "Attendance",
    "Bank Transaction",
    "BOM Update Tool",
    "Communication",
    "Contact",
    "Customer",
    "Customer Group",
    "Delivery Note",
    "Employee",
    "Employee Advance",
    "Expense Claim",
    "Holiday List",
    "Interview",
    "Interview Feedback",
    "Issue",
    "Job Applicant",
    "Job Card",
    "Job Offer",
    "Journal Entry",
    "Landed Cost Voucher",
    "Lead",
    "Leave Application",
    "Maintenance Visit",
    "Material Request",
    "Opportunity",
    "Packing Slip",
    "Payment Entry",
    "Payment Order",
    "Payment Request",
    "Payment Term",
    "Payroll Entry",
    "Pick List",
    "POS Closing Entry",
    "POS Invoice",
    "POS Opening Entry",
    "POS Profile",
    "Project Update",
    "Purchase Invoice",
    "Purchase Order",
    "Purchase Receipt",
    "Quotation",
    "Request for Quotation",
   # "Sales Invoice",
    "Sales Order",
    "Sales Partner",
    "Salary Slip",
    "Stock Entry",
    "Stock Reconciliation",
    "Stock Reservation Entry",
    "Subscription",
    "Subscription Invoice",
    "Supplier",
    "Supplier Quotation",
    "Timesheet",
    "Training Event",
    "Warranty Claim",
    "Work Order",
    "Project Update"
        # "Quotation",
        # "Request for Quotation",
        # "Supplier Quotation",
        # "Purchase Order",
        # "Stock Entry",
        # "Holiday List",
        # "Customer",
        # "Supplier",
        # "Employee",
        # "Stock Reconciliation",
        # "Payment Entry",
        # "Delivery Note",
        # "Sales Order",
        # "Purchase Receipt",
        # "Journal Entry",
        # "Purchase Invoice",
        # "Material Request",
        # "Sales Invoice",
        # "Address",
        # "Contact",
    ]

class AuditFieldsManager(AuditBase):
    """Manages custom audit fields across multiple doctypes."""
    
    def __init__(self, doctypes=None):
        """
        Initialize the manager.
        
        Args:
            doctypes (list): List of doctype names to manage audit fields for
        """
        super().__init__()
        self.custom_fields = {}
        self.doctypes = doctypes or self.doctypes

    def get_last_tab_break(self, doctype):
            try:
                meta = frappe.get_meta(doctype)
                tab_fields = [f.fieldname for f in meta.fields if f.fieldtype == "Tab Break"]
                return tab_fields[-1] if tab_fields else None
            except Exception as e:
                frappe.log_error(f"Error finding last tab for {doctype}: {str(e)}")
                return None
            
    def doctype_has_company_field(self, doctype):
        try:
            meta = frappe.get_meta(doctype)
    
            # Check for custom_company field
            custom_company = frappe.db.exists(
                "Custom Field",
                {"dt": doctype, "fieldname": "custom_company"}
            )
            
            return meta.has_field("company") or bool(custom_company)

        except Exception as e:
            frappe.log_error(f"Error checking company field for {doctype}: {str(e)}")
            return False
        
    def get_field_definitions(self, doctype):
        """
        Returns the field definitions for audit fields including a custom tab.
        
        Args:
            doctype (str): Name of the doctype
            
        Returns:
            list: List of field definitions with tab and fields
        """
        has_company = self.doctype_has_company_field(doctype)
        last_tab = self.get_last_tab_break(doctype)
        
        fields = [
            {
                "fieldname": "audit_section",
                "label": "Audit",
                "fieldtype": "Section Break",
            }
        ]
        
        # Add company field if doctype doesn't have one
        if not has_company:
            fields.extend([{
                "fieldname": "custom_company",
                "label": "Company",
                "fieldtype": "Link",
                "options": "Company",
                "mandatory": 1,
                "in_standard_filter": 1,
                "in_list_view": 0,
                "in_global_search": 0,
                "bold": 0,
                "allow_on_submit": 0,
                "insert_after": "",
            }])
            
         
        
        # Add audit fields
        fields.extend([
            {
                "fieldname": "custom_created_by",
                "label": "Created By",
                "fieldtype": "Link",
                "options": "User",
                "insert_after": "audit_section",
                "read_only": 1,
                "no_copy": 1,
                "print_hide": 1,
                "is_standard_filter": 1,
            },
            {
                "fieldname": "custom_created_on",
                "label": "Created On",
                "fieldtype": "Datetime",
                "insert_after": "audit_section",
                "read_only": 1,
                "no_copy": 1,
                "print_hide": 1,
                "is_standard_filter": 1,
            },
            {
                "fieldname": "custom_modified_by",
                "label": "Modified By",
                "fieldtype": "Link",
                "options": "User",
                "insert_after": "audit_section",
                "read_only": 1,
                "no_copy": 1,
                "print_hide": 1,
                "is_standard_filter": 1,
            }
        ])
        
        return fields
    

        



    
    def prepare_custom_fields(self):
        """
        Prepares custom fields dictionary for all doctypes.
        
        Returns:
            dict: Dictionary mapping doctypes to field definitions
        """
        for doctype in self.doctypes:
            field_definitions = self.get_field_definitions(doctype)
            self.custom_fields[doctype] = field_definitions
        return self.custom_fields
    

    def create_fields(self):
        """
        Creates custom fields in the database.
        
        Returns:
            dict: Success status and message with details
        """
        failed_doctypes = []
        success_count = 0
        
        for doctype in self.doctypes:
            try:
                field_definitions = self.get_field_definitions(doctype)
                create_custom_fields({doctype: field_definitions}, update=True)
                success_count += 1
            except Exception as e:
                failed_doctypes.append(f"{doctype}: {str(e)}")
                frappe.log_error(f"Error creating fields for {doctype}: {str(e)}")
        
        frappe.db.commit()
        
        if failed_doctypes:
            return {
                "success": False,
                "message": f"Added fields to {success_count} doctypes. Failed for: {', '.join(failed_doctypes)}"
            }
        
        return {
            "success": True,
            "message": f"Custom fields added to {success_count} doctypes!"
        }
    

    # def create_fields(self):
    #     """
    #     Creates custom fields in the database.
        
    #     Returns:
    #         dict: Success status and message with details
    #     """
    #     try:
    #         self.prepare_custom_fields()
    #         create_custom_fields(self.custom_fields, update=True)
    #         frappe.db.commit()
    #     except Exception as e:
    #         frappe.db.rollback()
    #         frappe.log_error(f"Error creating custom fields: {str(e)}")
    #         return {"success": False, "message": str(e)}
    
    def remove_fields(self):
        """
        Removes custom audit fields from all doctypes.
        
        Returns:
            dict: Success status and message
        """
        try:
            for doctype in self.doctypes:
                fields_to_remove = [
                    "audit_tab",
                    "custom_created_by",
                    "custom_created_on",
                    "custom_modified_by",
                    "custom_company"
                ]
                for field in fields_to_remove:
                    custom_field = frappe.db.exists(
                        "Custom Field",
                        {"dt": doctype, "fieldname": field}
                    )
                    if custom_field:
                        frappe.delete_doc("Custom Field", custom_field)
            
            frappe.db.commit()
            return {"success": True, "message": "Custom fields removed!"}
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "message": str(e)}
    
    def verify_fields(self):
        """
        Verifies the existence of custom fields across all doctypes.
        
        Returns:
            dict: Report showing field status for each doctype
        """
        report = {}
        for doctype in self.doctypes:
            fields_status = {}
            fields_to_check = [
                "audit_tab",
                "custom_created_by",
                "custom_created_on",
                "custom_modified_by",
                "custom_company"
            ]
            for field in fields_to_check:
                exists = frappe.db.exists(
                    "Custom Field",
                    {"dt": doctype, "fieldname": field}
                )
                fields_status[field] = "✓ Exists" if exists else "✗ Missing"
            report[doctype] = fields_status
        return report
    


    def remove_fields(self):
        try:
            for doctype in self.doctypes:
                for field in ["custom_created_by", "custom_created_on", "custom_modified_by","custom_company"]:
                    custom_field = frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field})
                    if custom_field:
                        frappe.delete_doc("Custom Field", custom_field)
            frappe.db.commit()
            return {"success": True, "message": "Custom fields removed!"}
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "message": str(e)}




class AuditEventMapper(AuditBase):
    """Maps audit field handlers to document events"""

    @staticmethod
    def get_doc_events():
        """Returns a dictionary of document events for all doctypes
        
        Returns a dict with string paths (not function objects) for Frappe hooks
        """
        before_insert_handler_path = "avinashgroup_app.utils.audit_file_manager.before_insert"
        before_save_handler_path = "avinashgroup_app.utils.audit_file_manager.before_save"
        validate_handler_path = "avinashgroup_app.utils.audit_file_manager.validate"
        autoname_handler_path ="avinashgroup_app.utils.audit_file_manager.autoname"

        events = {}

        for dt in AuditEventMapper.doctypes:


            events[dt] = {
                "before_insert": before_insert_handler_path,
                "before_save": before_save_handler_path,
                "validate":validate_handler_path,
                "autoname":autoname_handler_path,
            
            }

        return events


# Standalone function for hooks to call
def set_audit_fields(doc, method=None):
    # Default to UI
    from_ui = False

    # Check if we are in a web request context (desk UI)
    if hasattr(frappe.local, "request") and frappe.local.request:
        from_ui = True

    # Optionally, check if this is a Data Import job
    # frappe.flags.in_import is True when importing from Excel / CSV
    if getattr(frappe.flags, "in_import", False):
        from_ui = False

    if from_ui:
        if doc.is_new():
            doc.custom_created_by = frappe.session.user
            doc.custom_created_on = frappe.utils.now_datetime()
        doc.custom_modified_by = frappe.session.user



def validate(doc, method=None):
    validate_company_matching(doc)
    handle_validate(doc)

def before_insert(doc, method=None):
    set_audit_fields(doc, method)

def before_save(doc, method=None):
    set_audit_fields(doc, method)

def autoname(doc, method=None):
    naming_series_autoname(doc, method)