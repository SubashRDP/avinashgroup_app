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
            p_type = invoice.get("custom_p_type_code") or ""
            doc_no = str(invoice.get("custom_document_no")).zfill(5) if invoice.get("custom_document_no") else "00000"
            fiscal_year = invoice.get("custom_fiscal_year") or "82/83"
            
            new_custom_name = f"{company_code}-{p_type}-{doc_no}-{fiscal_year}"
            
            # Update directly in database
            frappe.db.set_value(
                "Purchase Invoice",
                invoice.name,
                "custom_name",
                new_custom_name,
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

