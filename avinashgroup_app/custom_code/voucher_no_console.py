import frappe

def update_purchase_invoice_custom_names():
    """
    Update custom_name field for all existing Purchase Invoices
    that don't have it set or need recalculation
    """
    
    # Get all Purchase Invoices (both draft and submitted)
    invoices = frappe.get_all(
        "Purchase Invoice",
        fields=[
            "name",
            "custom_abbr",
            "custom_p_type_code",
            "custom_purchase_type",
            "custom_document_no",
            "custom_fiscal_year",
            "docstatus"
        ],
        filters={
            # Optional: Add filters if you want to target specific invoices
            # "custom_name": ["in", [None, ""]]  # Only update empty ones
        }
    )
    
    updated_count = 0
    error_count = 0
    
    for invoice in invoices:
        try:
            # Build custom_name using the same logic
            company_code = invoice.get("custom_abbr") or ""
            
            # Get p_type_code
            p_type = invoice.get("custom_p_type_code") or ""
            
            # If custom_p_type_code is empty, fetch from linked Purchase Type
            if not p_type and invoice.get("custom_purchase_type"):
                purchase_type = frappe.get_value(
                    "Purchase Type",
                    invoice.get("custom_purchase_type"),
                    "purchase_type_code"
                )
                p_type = purchase_type or ""
            
            doc_no = str(invoice.get("custom_document_no")).zfill(5) if invoice.get("custom_document_no") else "00000"
            fiscal_year = invoice.get("custom_fiscal_year") or "82/83"
            
            custom_name = f"{company_code}-{p_type}-{doc_no}-{fiscal_year}"
            
            # Update directly in database
            frappe.db.set_value(
                "Purchase Invoice",
                invoice.name,
                "custom_name",
                custom_name,
                update_modified=False  # Don't update modified timestamp
            )
            
            updated_count += 1
            
            # Log progress every 100 records
            if updated_count % 100 == 0:
                frappe.db.commit()
                print(f"Updated {updated_count} invoices...")
                
        except Exception as e:
            error_count += 1
            frappe.log_error(
                message=f"Error updating Purchase Invoice {invoice.name}: {str(e)}",
                title="Custom Name Update Error"
            )
            print(f"Error updating {invoice.name}: {str(e)}")
    
    # Final commit
    frappe.db.commit()
    
    print(f"\nUpdate Complete!")
    print(f"Successfully updated: {updated_count}")
    print(f"Errors: {error_count}")
    
    return {
        "updated": updated_count,
        "errors": error_count
    }


# Execute the update
# Run this in Frappe console or as a script
import frappe

def list_payment_entries_empty_custom_name():
    """
    List all Payment Entries where custom_name field is empty
    """
    
    # Get all Payment Entries with empty custom_name
    payment_entries = frappe.get_all(
        "Journal Entry",
        fields=[
            "name",
            "posting_date",
            "custom_name"
        ],
        filters={
            "custom_name": ["in", [None, ""]]
        },
        order_by="posting_date desc"
    )
    
    if not payment_entries:
        print("No Payment   Entries found with empty custom_name field!")
        return []
    
    print(f"\n{'='*100}")
    print(f"Found {len(payment_entries)} Payment Entries with empty custom_name field")
    print(f"{'='*100}\n")
    
    # Print in a formatted table
    print(f"{'No.':<10} {'Name':<20} {'Date':<12}")
    print(f"{'-'*100}")
    
    for idx, entry in enumerate(payment_entries, 1):
        status = "Draft" if entry.docstatus == 0 else "Submitted" if entry.docstatus == 1 else "Cancelled"
        print(f"{idx:<5} {entry.name:<20} {str(entry.posting_date):<12}")
    
    print(f"\n{'='*100}")
    print(f"Total: {len(payment_entries)} Payment Entries")
    print(f"{'='*100}\n")
    
    return payment_entries





def update_journal_entry_custom_names():
    """
    Update custom_name field for specific Journal Entries
    """
    
    # Specific Journal Entry IDs to update
    je_ids = [
        "NGK-JV-0007",
        "NGK-JV-0006",
        "NGK-JV-0005",
        "NGK-JV-0004",
        "NGK-JV-0003"
    ]
    
    # Get these specific Journal Entries
    journals = frappe.get_all(
        "Journal Entry",
        fields=[
            "name",
            "custom_abbr",
            "custom_p_type_code",
            "custom_p_type",
            "custom_document_no",
            "custom_fiscal_year",
            "docstatus"
        ],
        filters={
            "name": ["in", je_ids]
        }
    )
    
    if not journals:
        print("No Journal Entries found with the specified IDs!")
        return {"updated": 0, "errors": 0}
    
    print(f"\nFound {len(journals)} Journal Entries to update")
    print("Starting update...\n")
    
    updated_count = 0
    error_count = 0
    
    for journal in journals:
        try:
            # Build custom_name using the same logic
            company_code = journal.get("custom_abbr") or ""
            
            # Get p_type_code
            p_type = journal.get("custom_p_type_code") or ""
            
            # If custom_p_type_code is empty, fetch from linked JV Type
            if not p_type and journal.get("custom_p_type"):
                jv_type_code = frappe.get_value(
                    "JV Type",
                    journal.get("custom_p_type"),
                    "jv_type_code"
                )
                p_type = jv_type_code or ""
            
            doc_no = str(journal.get("custom_document_no")).zfill(5) if journal.get("custom_document_no") else "00000"
            fiscal_year = journal.get("custom_fiscal_year") or "82/83"
            
            custom_name = f"{company_code}-{p_type}-{doc_no}-{fiscal_year}"
            
            # Update directly in database
            frappe.db.set_value(
                "Journal Entry",
                journal.name,
                "custom_name",
                custom_name,
                update_modified=False  # Don't update modified timestamp
            )
            
            print(f"Updated {journal.name}: {custom_name}")
            updated_count += 1
            
            # Log progress every 100 records
            if updated_count % 100 == 0:
                frappe.db.commit()
                print(f"Updated {updated_count} journal entries...")
                
        except Exception as e:
            error_count += 1
            frappe.log_error(
                message=f"Error updating Journal Entry {journal.name}: {str(e)}",
                title="Custom Name Update Error"
            )
            print(f"Error updating {journal.name}: {str(e)}")
    
    # Final commit
    frappe.db.commit()
    
    print(f"\n{'='*60}")
    print(f"Update Complete!")
    print(f"Successfully updated: {updated_count}")
    print(f"Errors: {error_count}")
    print(f"{'='*60}\n")
    
    return {
        "updated": updated_count,
        "errors": error_count
    }


# Execute the update
if __name__ == "__main__":
    update_journal_entry_custom_names()