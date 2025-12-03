import frappe
from frappe import _

def validate_company_matching(doc, method=None):
  
    if not doc.company:
        return
    
    company = doc.company
    errors = []
    
    # Validate Supplier
    if hasattr(doc, 'supplier') and doc.supplier:
        supplier_company = frappe.db.get_value('Supplier', doc.supplier, 'custom_company')
        if supplier_company and supplier_company != company:
            errors.append(
                _("Supplier '{0}' belongs to company '{1}").format(
                    doc.supplier, supplier_company
                )
            )
    
    # Validate Customer
    if hasattr(doc, 'customer') and doc.customer:
        customer_company = frappe.db.get_value('Customer', doc.customer, 'custom_company')
        if customer_company and customer_company != company:
            errors.append(
                _("Customer '{0}' belongs to company '{1}'").format(
                    doc.customer, customer_company
                )
            )
    
    # Validate Employee
    if hasattr(doc, 'employee') and doc.employee:
        employee_company = frappe.db.get_value('Employee', doc.employee, 'custom_company')
        if employee_company and employee_company != company:
            errors.append(
                _("Employee '{0}' belongs to company '{1}'").format(
                    doc.employee, employee_company, company
                )
            )
    
    # Validate Items in child table
    if hasattr(doc, 'items') and doc.items:
        item_codes = [item.item_code for item in doc.items if item.item_code]
        
        if item_codes:
            # Fetch all items in one query for better performance
            item_companies = frappe.get_all(
                'Item',
                filters={'name': ['in', item_codes]},
                fields=['name', 'custom_company']
            )
            
            item_company_map = {item.name: item.custom_company for item in item_companies}
            
            mismatched_items = []
            for item_code in item_codes:
                item_company = item_company_map.get(item_code)
                if item_company and item_company != company:
                    mismatched_items.append(item_code)
            
            if mismatched_items:
                errors.append(
                    _("The following items do not belong to company '{0}': {1}").format(
                        company, ', '.join(mismatched_items)
                    )
                )
    
    # Validate custom_suppliers field if exists
    if hasattr(doc, 'custom_suppliers') and doc.custom_suppliers:
        supplier_company = frappe.db.get_value('Supplier', doc.custom_suppliers, 'custom_company')
        if supplier_company and supplier_company != company:
            errors.append(
                _("Supplier '{0}' in custom_suppliers belongs to company '{1}'").format(
                    doc.custom_suppliers, supplier_company
                )
            )
    
    # Validate customer_name field if exists
    if hasattr(doc, 'customer_name') and doc.customer_name:
        # Assuming customer_name is a link to Customer doctype
        customer_company = frappe.db.get_value('Customer', doc.customer_name, 'custom_company')
        if customer_company and customer_company != company:
            errors.append(
                _("Customer '{0}' in customer_name belongs to company '{1}', but the document is for company '{2}'").format(
                    doc.customer_name, customer_company, company
                )
            )
    
    # If there are any errors, raise validation error
    if errors:
        frappe.throw(
            '<br>'.join(errors),
            title=_('Company Mismatch Error'),
            exc=frappe.ValidationError
        )
