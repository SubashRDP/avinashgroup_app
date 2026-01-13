
import frappe

def setup_company_field_lock():
    """Set company fields as read-only after first save for Parent Test and Check"""
    
    doctypes = ["Parent Test", "Check"]
    updated_doctypes = []
    
    for doctype in doctypes:
        try:
            # Check standard fields
            doc = frappe.get_doc("DocType", doctype)
            field_updated = False
            
            for field in doc.fields:
                if field.fieldname in ["company", "custom_company"]:
                    field.read_only_depends_on = "eval:!doc.__islocal"
                    field_updated = True
                    print(f"Updated standard field: {field.fieldname} in {doctype}")
            
            if field_updated:
                doc.save()
                updated_doctypes.append(doctype)
            
            # Check custom fields
            custom_fields = frappe.get_all("Custom Field",
                                          filters={"dt": doctype, "fieldname": ["in", ["company", "custom_company"]]},
                                          fields=["name", "fieldname"])
            
            for cf in custom_fields:
                frappe.db.set_value("Custom Field", cf.name, "read_only_depends_on", "eval:!doc.__islocal")
                print(f"Updated custom field: {cf.fieldname} in {doctype}")
                if doctype not in updated_doctypes:
                    updated_doctypes.append(doctype)
                    
        except Exception as e:
            print(f"Error processing {doctype}: {str(e)}")
            continue
    
    frappe.db.commit()
    print(f"\nCompany fields locked for {len(updated_doctypes)} doctypes:")
    print(updated_doctypes)