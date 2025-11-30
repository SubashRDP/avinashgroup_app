import frappe

# def set_custom_name_field(doc, method):
#     company_code = doc.custom_abbr or ""
#     p_type = doc.custom_p_type_code or ""
    
#     doc_no = str(doc.custom_document_no).zfill(5) if doc.custom_document_no else "00000"
#     fiscal_year = doc.custom_fiscal_year or "82/83"
    
#     doc.custom_name = f"{company_code}-{p_type}-{doc_no}-{fiscal_year}"


# def set_custom_name_field(doc, method=None):
#     try:
#         if not hasattr(doc, 'custom_name'):
#             return
        
#         company_code = getattr(doc, 'custom_abbr', '') or ""
#         p_type = getattr(doc, 'custom_p_type_code', '') or ""
        
#         doc_no = "00000"
#         if hasattr(doc, 'custom_document_no') and doc.custom_document_no:
#             doc_no = str(doc.custom_document_no).zfill(5)
        
#         fiscal_year = getattr(doc, 'custom_fiscal_year', '82/83') or "82/83"
        
#         doc.custom_name = f"{company_code}-{p_type}-{doc_no}-{fiscal_year}"
        
#     except Exception as e:
#         frappe.log_error(f"Error in set_custom_name_field for {doc.doctype}: {str(e)}")



def handle_naming_and_fiscal_year(doc, method=None):

    update_fiscal_year(doc)
    
    set_naming_series_based_on_return(doc)
    
    set_custom_name_field(doc)



def update_fiscal_year(doc):

    if not hasattr(doc, 'custom_fiscal_year'):
        return
    
    date_to_use = None
    
    if hasattr(doc, 'posting_date') and doc.posting_date:
        date_to_use = doc.posting_date
    elif hasattr(doc, 'transaction_date') and doc.transaction_date:
        date_to_use = doc.transaction_date
    
    if not date_to_use:
        return
    
    fiscal_year = frappe.db.get_value(
        "Fiscal Year",
        filters={
            "year_start_date": ["<=", date_to_use],
            "year_end_date": [">=", date_to_use]
        },
        fieldname="name"
    )    
    doc.custom_fiscal_year = fiscal_year if fiscal_year else "Not Found"


def set_custom_name_field(doc):

    if not hasattr(doc, 'custom_name'):
        return
    
    company_code = doc.custom_abbr if hasattr(doc, 'custom_abbr') and doc.custom_abbr else ""
    p_type = doc.custom_p_type_code if hasattr(doc, 'custom_p_type_code') and doc.custom_p_type_code else ""
    
    doc_no = "00000"
    if hasattr(doc, 'custom_document_no') and doc.custom_document_no:
        doc_no = str(doc.custom_document_no).zfill(5)
    
    fiscal_year = doc.custom_fiscal_year if hasattr(doc, 'custom_fiscal_year') and doc.custom_fiscal_year else "82/83"
    
    doc.custom_name = f"{company_code}-{p_type}-{doc_no}-{fiscal_year}"


def set_naming_series_based_on_return(doc):
    if not hasattr(doc, 'naming_series') or not hasattr(doc, 'custom_fiscal_year'):
        return
    
    naming_patterns = {
        "Sales Invoice": {
            "normal": ".{custom_abbr}.-SB-.######.-.{custom_fiscal_year}",
            "return": ".{custom_abbr}.-SB-RTN-.######.-.{custom_fiscal_year}"
        },
        "Purchase Invoice": {
            "normal": ".{custom_abbr}.-PUR-.######.-.{custom_fiscal_year}",
            "return": ".{custom_abbr}.-PUR-RTN-.######.-.{custom_fiscal_year}"
        },
    }

    patterns = naming_patterns.get(doc.doctype)
    
    if not patterns:
        doc.naming_series = ".{custom_abbr}.######.-.{custom_fiscal_year}"
        return
    
    if hasattr(doc, 'is_return') and doc.is_return == 1:
        doc.naming_series = patterns.get("return", patterns.get("normal"))
    else:
        doc.naming_series = patterns.get("normal")


####For backend update script to update fiscal year in existing Sales Invoices
import frappe
from frappe.utils import getdate

def update_sales_invoice_fiscal_year():
    """
    Update custom_fiscal_year field for all existing Sales Invoices
    based on their posting_date
    """
    
    # Get all Sales Invoices
    invoices = frappe.get_all(
        "Sales Invoice",
        fields=["name", "posting_date", "custom_fiscal_year", "docstatus"],
        filters={
            # Optional: Only update where fiscal year is empty or "Not Found"
            # "custom_fiscal_year": ["in", [None, "", "Not Found"]]
        }
    )
    
    if not invoices:
        print("No Sales Invoices found!")
        return {"updated": 0, "errors": 0, "not_found": 0}
    
    print(f"\nFound {len(invoices)} Sales Invoices to update")
    print("Starting update...\n")
    
    updated_count = 0
    error_count = 0
    not_found_count = 0
    
    for invoice in invoices:
        try:
            if not invoice.posting_date:
                print(f"Skipping {invoice.name}: No posting date")
                continue
            
            # Find the fiscal year for this posting date
            fiscal_year = frappe.db.get_value(
                "Fiscal Year",
                {
                    "year_start_date": ["<=", invoice.posting_date],
                    "year_end_date": [">=", invoice.posting_date]
                },
                "name"
            )
            
            if fiscal_year:
                # Update directly in database
                frappe.db.set_value(
                    "Sales Invoice",
                    invoice.name,
                    "custom_fiscal_year",
                    fiscal_year,
                    update_modified=False
                )
                print(f"✓ {invoice.name}: {fiscal_year}")
                updated_count += 1
            else:
                # No fiscal year found for this date
                frappe.db.set_value(
                    "Sales Invoice",
                    invoice.name,
                    "custom_fiscal_year",
                    "Not Found",
                    update_modified=False
                )
                print(f"⚠ {invoice.name}: No fiscal year found for {invoice.posting_date}")
                not_found_count += 1
            
            # Commit every 100 records
            if (updated_count + not_found_count) % 100 == 0:
                frappe.db.commit()
                print(f"Progress: {updated_count + not_found_count} invoices processed...")
                
        except Exception as e:
            error_count += 1
            frappe.log_error(
                message=f"Error updating Sales Invoice {invoice.name}: {str(e)}",
                title="Fiscal Year Update Error"
            )
            print(f"✗ Error updating {invoice.name}: {str(e)}")
    
    # Final commit
    frappe.db.commit()
    
    print(f"\n{'='*60}")
    print(f"Update Complete!")
    print(f"Successfully updated: {updated_count}")
    print(f"Fiscal year not found: {not_found_count}")
    print(f"Errors: {error_count}")
    print(f"{'='*60}\n")
    
    return {
        "updated": updated_count,
        "not_found": not_found_count,
        "errors": error_count
    }


from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def create_created_by_and_created_on_fields():
    """
    Create custom_created_by and custom_created_on fields in ALL doctypes
    (both transactions and masters)
    """
    
    # Automatically get all doctypes from the system
    all_doctypes = frappe.get_all(
        "DocType",
        filters={
            "istable": 0,  # Exclude child tables
            "issingle": 0,  # Exclude single doctypes
            "module": ["not in", ["Core", "Custom", "Desk", "Email", "Printing", "Website", "Portal"]],  
        },
        pluck="name"
    )
    
    print(f"\nFound {len(all_doctypes)} doctypes to update")
    print(f"{'='*60}\n")
    
    # Define custom fields
    custom_fields = {}
    
    for doctype in all_doctypes:
        custom_fields[doctype] = [
            {
                "fieldname": "custom_created_by",
                "label": "Created By",
                "fieldtype": "Link",
                "options": "User",
                "insert_after": "amended_from",  # Adjust based on your form
                "read_only": 1,
                "no_copy": 1,
                "print_hide": 1,
            },
            {
                "fieldname": "custom_created_on",
                "label": "Created On",
                "fieldtype": "Datetime",
                "insert_after": "custom_created_by",
                "read_only": 1,
                "no_copy": 1,
                "print_hide": 1,
            }
        ]
    
    # Create the custom fields one by one to handle errors gracefully
    success_count = 0
    error_count = 0
    error_doctypes = []
    
    for doctype in all_doctypes:
        try:
            create_custom_fields({doctype: custom_fields[doctype]}, update=True)
            success_count += 1
            print(f"✓ {doctype}")
        except Exception as e:
            error_count += 1
            error_doctypes.append(doctype)
            print(f"✗ {doctype}: {str(e)}")
            frappe.log_error(
                message=f"Doctype: {doctype}\nError: {str(e)}",
                title="Custom Field Creation Error"
            )
    
    print(f"\n{'='*60}")
    print(f"Successfully created custom fields in {success_count} doctypes!")
    print(f"Failed: {error_count} doctypes")
    print(f"{'='*60}\n")
    print("Fields created:")
    print("- custom_created_by (Link to User)")
    print("- custom_created_on (Datetime)")
    
    if error_doctypes:
        print(f"\n⚠ Failed doctypes:")
        for dt in error_doctypes:
            print(f"  - {dt}")


def populate_created_by_and_created_on():
    """
    Populate custom_created_by and custom_created_on for existing records
    Uses the standard 'owner' and 'creation' fields from the database
    """
    
    # Get all doctypes automatically
    all_doctypes = frappe.get_all(
        "DocType",
        filters={
            "istable": 0,
            "issingle": 0,
            "module": ["not in", ["Core", "Custom", "Desk", "Email", "Printing", "Website", "Portal"]],
        },
        pluck="name"
    )
    
    total_updated = 0
    
    for doctype in all_doctypes:
        try:
            # Update all records in this doctype
            frappe.db.sql(f"""
                UPDATE `tab{doctype}`
                SET custom_created_by = owner,
                    custom_created_on = creation
                WHERE custom_created_by IS NULL OR custom_created_on IS NULL
            """)
            
            count = frappe.db.sql(f"SELECT COUNT(*) FROM `tab{doctype}`")[0][0]
            total_updated += count
            print(f"Updated {doctype}: {count} records")
            
        except Exception as e:
            print(f"Error updating {doctype}: {str(e)}")
    
    frappe.db.commit()
    
    print(f"\n{'='*60}")
    print(f"Total records updated: {total_updated}")
    print(f"{'='*60}\n")


# if __name__ == "__main__":
    # Step 1: Create the custom fields
    # create_created_by_and_created_on_fields()
    
    # Step 2: Populate existing records
    # Uncomment the line below after fields are created
    # populate_created_by_and_created_on()