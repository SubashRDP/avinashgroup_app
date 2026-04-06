
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from avinashgroup_app.custom_code.Override.naming_series import handle_validate, handle_before_save, naming_series_autoname, handle_before_insert, naming_requirements_before_insert
from avinashgroup_app.custom_code.globalfilter.globalfilter import validate_company_matching
from avinashgroup_app.custom_code.SalesInvoice.salesinvoice_taxes import before_save_salesinvoice, validate_salesinvoice
from avinashgroup_app.custom_code.purchase_invoice.purchase_invoice_taxes_tds import before_save_purchaseinvoice, validate_purchaseinvoice
from avinashgroup_app.custom_code.Override.company_field_lock import validate_company_field_lock
class AuditBase:
    doctypes = [
    "Address",
    "Salary Structure",
    "Vehicle",
    "Vehicle Log",
    "Appointment Letter",
    "Asset Capitalization",
    "Asset Movement",
    "Asset Repair",
    "Asset",
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
    "Sales Invoice",
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
    "Project Update",
    "Item",
    "Asset Maintenance Team",
    "Asset Value Adjustment",
    "Designation",
    "Manufacturer",
    "Prospect",
   #Item master
    "Item Group",
    "Customer Group",
    "Supplier Group",
    "Price List",
    "Address",
    "Contact",
    "Branch",
    "Operation",
    "Workstation",
    "Routing",
    "Asset Category",
    "Project",
    "Task",    
    "Serial No",
    "Batch",
    "Expense Claim Type",
    "Mode of Payment",
    "Bank Account",
    "Holiday List",
    "Leave Type",
    "BOM",
    "Designation",
    # "BOM Template"
    ]

    

#for naming series
    master_doctypes = [
        "Item Group",
        "Customer Group",
        "Supplier Group",
        "Price List",
        "Address",
        "Contact",
        "Branch",
        "Operation",
        "Workstation",
        "Routing",
        "Asset Category",
        "Project",
        "Task",    
        "Serial No",
        "Batch",
        "Expense Claim Type",
        "Mode of Payment",
        "Bank Account",
        "Holiday List",
        "Leave Type",
        "Designation",
        "Asset Maintenance Team",
        "Asset Value Adjustment",
        "Manufacturer",
        "Prospect",
        # "BOM Template"
    ]
    
  

class AuditFieldsManager(AuditBase):

    def is_master_doctype(self, doctype):
        return doctype in self.master_doctypes

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

    def get_last_field(self, doctype):
            try:
                meta = frappe.get_meta(doctype)
                if meta.fields:
                  return meta.fields[-1].fieldname
         
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
        last_feild = self.get_last_field(doctype)
        is_master = self.is_master_doctype(doctype)


        
        fields = [
            {
                "fieldname": "audit_section",
                "label": "Audit",
                "fieldtype": "Section Break",
                "insert_after": last_feild,
                  "read_only": 1,
            }
        ]
        
        # Add company field if doctype doesn't have one
        if not has_company:
            fields.append({
                "fieldname": "custom_company",
                "label": "Company",
                "fieldtype": "Link",
                "options": "Company",
                "reqd": 1,
                "in_standard_filter": 1,
                "in_list_view": 0,
                "in_global_search": 0,
                "bold": 0,
                "allow_on_submit": 0,
                "read_only_depends_on": "eval:!doc.__islocal",
                "insert_after": "",
            })
            
            # Add naming series field for master doctypes after custom_company
            if is_master:
                fields.append({
                    "fieldname": "custom_naming_series",
                    "label": "Naming Series",
                    "fieldtype": "Data",
                    "mandatory": 0,
                    "in_standard_filter": 0,
                    "in_list_view": 0,
                    "insert_after": "custom_company",
                })
        else:
            # If company field exists, add naming series after company or custom_company
            if is_master:
                # Determine the insert_after field
                company_field = "company" if has_company and not frappe.db.exists(
                    "Custom Field", {"dt": doctype, "fieldname": "custom_company"}
                ) else "custom_company"
                
                fields.append({
                    "fieldname": "custom_naming_series",
                    "label": "Naming Series",
                    "fieldtype": "Data",
                    "mandatory": 0,
                    "in_standard_filter": 0,
                    "in_list_view": 0,
                    "insert_after": company_field,
                })
        
        # Add audit fields
        fields.extend([
            {
                "fieldname": "custom_created_by",
                "label": "Created By",
                "fieldtype": "Link",
                "options": "User",
                "insert_after": "audit_tab",
                "read_only": 1,
                "no_copy": 1,
                "print_hide": 1,
                "is_standard_filter": 1,
            },
            {
                "fieldname": "custom_created_on",
                "label": "Created On",
                "fieldtype": "Datetime",
                "insert_after": "custom_created_by",
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
                "insert_after": "custom_created_on",
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
                    "custom_company",
                    "custom_naming_series"
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
            
            # Add naming series check for master doctypes
            if self.is_master_doctype(doctype):
                fields_to_check.append("custom_naming_series")
            
            for field in fields_to_check:
                exists = frappe.db.exists(
                    "Custom Field",
                    {"dt": doctype, "fieldname": field}
                )
                fields_status[field] = "✓ Exists" if exists else "✗ Missing"
            report[doctype] = fields_status
        return report
    
    def update_custom_company_reqd(self, doctype):
    
        doctypes = AuditBase.doctypes
        
        updated_count = 0
        skipped_count = 0
        error_count = 0

        for doctype in doctypes:
            try:
                # Check if custom_company field exists
                custom_field = frappe.db.get_value(
                    "Custom Field",
                    {"dt": doctype, "fieldname": "custom_company"},
                    ["name", "reqd"],
                    as_dict=True
                )
                
                if custom_field:
                    # If reqd is already 1, skip
                    if custom_field.reqd == 1:
                        print(f"✓ {doctype}: custom_company already mandatory")
                        skipped_count += 1
                    else:
                        # Update to make it mandatory
                        frappe.db.set_value("Custom Field", custom_field.name, "reqd", 1)
                        print(f"✓ {doctype}: custom_company set to mandatory")
                        updated_count += 1
                else:
                    print(f"⊘ {doctype}: custom_company field not found")
                    
            except Exception as e:
                print(f"✗ {doctype}: Error - {str(e)}")
                error_count += 1

        # Commit the changes
        frappe.db.commit()

        print(f"\n=== Summary ===")
        print(f"Updated: {updated_count}")
        print(f"Already mandatory: {skipped_count}")
        print(f"Errors: {error_count}")
        print(f"Total processed: {len(doctypes)}")
        
        return {
            "updated": updated_count,
            "skipped": skipped_count,
            "errors": error_count,
            "total": len(doctypes)
        }
        


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
        autoname_handler_path = "avinashgroup_app.utils.audit_file_manager.autoname"

        events = {}

        for dt in AuditEventMapper.doctypes:
            events[dt] = {
                "before_insert": before_insert_handler_path,
                "before_save": before_save_handler_path,
                "validate": validate_handler_path,
                "autoname": autoname_handler_path,
            }

        return events
    
    
def update_custom_company_reqd():
    # import frappe
    # from avinashgroup_app.utils.audit_file_manager import AuditBase
    
    doctypes = AuditBase.doctypes
    
    updated_count = 0
    skipped_count = 0
    error_count = 0

    for doctype in doctypes:
        try:
           
            custom_field = frappe.db.get_value(
                "Custom Field",
                {"dt": doctype, "fieldname": "custom_company"},
                ["name", "reqd"],
                as_dict=True
            )
            
            if custom_field:
                # If reqd is already 1, skip
                if custom_field.reqd == 1:
                    print(f"{doctype}: custom_company already mandatory")
                    skipped_count += 1
                else:
                    # Update to make it mandatory
                    frappe.db.set_value("Custom Field", custom_field.name, "reqd", 1)
                    print(f"{doctype}: custom_company set to mandatory")
                    updated_count += 1
            else:
                print(f"{doctype}: custom_company field not found")
                
        except Exception as e:
            print(f"{doctype}: Error - {str(e)}")
            error_count += 1


    frappe.db.commit()

    print(f"\n=== Summary ===")
    print(f"Updated: {updated_count}")
    print(f"Already mandatory: {skipped_count}")
    print(f"Errors: {error_count}")
    print(f"Total processed: {len(doctypes)}")
    
    return {
        "updated": updated_count,
        "skipped": skipped_count,
        "errors": error_count,
        "total": len(doctypes)
    }



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
    validate_company_field_lock(doc, method)
    validate_company_matching(doc)
    handle_validate(doc)    

def before_insert(doc, method=None):
    set_audit_fields(doc, method)
    naming_requirements_before_insert(doc)

def before_save(doc, method=None):
    set_audit_fields(doc, method)
    handle_before_save(doc)

def autoname(doc, method=None):
    naming_series_autoname(doc, method)


