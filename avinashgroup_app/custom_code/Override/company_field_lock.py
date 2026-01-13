"""
Company Field Lock Module
Prevents modification of company/custom_company fields after document naming
"""

import frappe
from frappe import _


def validate_company_field_lock(doc, method=None):
    """
    Validates that company field is not changed after document is named.
    
    This function prevents users from changing the company or custom_company field
    after the document has been saved and named, since the name contains the company abbreviation.
    
    Args:
        doc: Document object
        method: Hook method (optional)
    
    Raises:
        frappe.ValidationError: If company field is changed after naming
    """
    # Skip if document is new (not yet saved)
    if doc.is_new():
        return
    
    # Skip if document is being cancelled or amended
    if doc.docstatus == 2 or hasattr(doc, 'amended_from') and doc.amended_from:
        return
    
    # Get the appropriate company field name
    company_field = get_company_field_name(doc)
    
    if not company_field:
        return
    
    # Get the current company value
    current_company = getattr(doc, company_field, None)
    
    if not current_company:
        return
    
    # Get the old company value from database
    old_company = frappe.db.get_value(doc.doctype, doc.name, company_field)
    
    # If company has been changed, throw error
    if old_company and old_company != current_company:
        frappe.throw(
            _(f"Cannot change Company from '{old_company}' to '{current_company}' after document is named. "
              f"The document name '{doc.name}' contains the company abbreviation and cannot be changed."),
            title=_("Company Field Locked")
        )


def get_company_field_name(doc):
    """
    Determines which company field exists in the document.
    
    Args:
        doc: Document object
    
    Returns:
        str: Field name ('company' or 'custom_company') or None
    """
    # Check if standard company field exists and has value
    if hasattr(doc, 'company') and doc.company:
        return 'company'
    
    # Check if custom_company field exists and has value
    if hasattr(doc, 'custom_company') and doc.custom_company:
        return 'custom_company'
    
    return None


def set_company_field_readonly_property(doctype):
    """
    Sets the custom_company field as read-only after document is saved.
    This ONLY updates Custom Field definitions, NOT standard ERPNext fields.
    
    
    Args:
        doctype (str): Name of the doctype
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # ONLY update custom_company field (not standard company field from ERPNext)
        # This prevents modifying ERPNext core DocType JSON files
        custom_fields = frappe.get_all(
            "Custom Field",
            filters={
                "dt": doctype,
                "fieldname": "custom_company"  # Only custom_company, not company
            },
            fields=["name", "fieldname"]
        )
        
        updated = False
        for cf in custom_fields:
            frappe.db.set_value(
                "Custom Field",
                cf.name,
                "read_only_depends_on",
                "eval:!doc.__islocal"
            )
            frappe.logger().info(f"Updated custom field {cf.fieldname} in {doctype} to be read-only after save")
            updated = True
        
        return updated
        
    except Exception as e:
        frappe.logger().error(f"Error setting read-only property for {doctype}: {str(e)}")
        return False


def bulk_update_company_field_readonly(doctypes=None):
    """
    Bulk updates custom_company fields to be read-only after save across multiple doctypes.
    
    IMPORTANT: This only updates CUSTOM fields (custom_company).
    Standard 'company' fields from ERPNext core are NOT modified to avoid 
    editing ERPNext app files. Backend validation protects both field types.
    
    Args:
        doctypes (list): List of doctype names. If None, uses AuditBase.doctypes
    
    Returns:
        dict: Summary of updates
    """
    if doctypes is None:
        # Use AuditBase.doctypes - more efficient than importing NAMING_CONFIG
        from avinashgroup_app.utils.audit_file_manager import AuditBase
        doctypes = AuditBase.doctypes
    
    updated_count = 0
    skipped_count = 0
    failed_doctypes = []
    
    for doctype in doctypes:
        try:
            # Check if this doctype has custom_company field
            has_custom_company = frappe.db.exists(
                "Custom Field",
                {"dt": doctype, "fieldname": "custom_company"}
            )
            
            if has_custom_company:
                if set_company_field_readonly_property(doctype):
                    updated_count += 1
                else:
                    skipped_count += 1
            else:
                # Skip doctypes with only standard company field
                skipped_count += 1
                
        except Exception as e:
            failed_doctypes.append(f"{doctype}: {str(e)}")
            frappe.logger().error(f"Error processing {doctype}: {str(e)}")
    
    frappe.db.commit()
    
    return {
        "success": len(failed_doctypes) == 0,
        "updated": updated_count,
        "skipped": skipped_count,
        "failed": failed_doctypes,
        "message": f"Updated {updated_count} custom fields. Skipped: {skipped_count}. Failed: {len(failed_doctypes)}"
    }


# Console command function for manual execution
def setup_company_field_lock():
    """
    Console command to set custom_company fields as read-only after first save.
    
    IMPORTANT NOTES:
    - This only updates CUSTOM fields (custom_company)
    - Standard 'company' fields from ERPNext are NOT modified
    - Backend validation protects both field types
    - This approach avoids editing ERPNext core app files
    
    Execute this from bench console:
    
    from avinashgroup_app.custom_code.company_field_lock import setup_company_field_lock
    setup_company_field_lock()
    """
    print("Starting company field lock setup...")
    result = bulk_update_company_field_readonly()
    
    print(f"\n=== Company Field Lock Setup ===")
    print(f"Updated: {result['updated']} custom fields")
    print(f"Skipped: {result['skipped']} (no custom_company field or already set)")
    
    if result['failed']:
        print(f"\nFailed doctypes:")
        for dt in result['failed']:
            print(f"  - {dt}")
    else:
        print("\n✓ All custom_company fields updated successfully!")
    
    print("\n📌 NOTE: Standard 'company' fields are protected by backend validation only.")
    print("   This prevents modifying ERPNext core files.")
    
    return result