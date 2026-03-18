import frappe


@frappe.whitelist()
def search_party(doctype, txt, searchfield, start, page_len, filters):
    party_type = (filters or {}).get("party_type") or doctype
    company = (filters or {}).get("company")

    if not party_type:
        return []

    if not company:
        return frappe.desk.search.search_link(
            party_type, txt, searchfield, start, page_len, None, None
        )

    company_fields = _get_company_fields_for_party(party_type)
    if not company_fields:
        return []

    meta = frappe.get_meta(party_type)
    filters_list = []
    if _doctype_has_field(meta, "disabled"):
        filters_list.append(["disabled", "=", 0])
    if txt:
        filters_list.append([searchfield, "like", f"%{txt}%"])

    or_filters = [[fieldname, "=", company] for fieldname in company_fields]

    rows = frappe.get_all(
        party_type,
        filters=filters_list,
        or_filters=or_filters,
        fields=["name", meta.title_field] if meta.title_field else ["name"],
        limit_start=start,
        limit_page_length=page_len,
    )
    title_field = meta.title_field
    if title_field:
        return [[d.name, d.get(title_field) or d.name] for d in rows]
    return [[d.name] for d in rows]


def _get_company_fields_for_party(doctype):
    override = {
        "Customer": ["custom_company"],
        "Supplier": ["custom_company"],
        "Employee": ["company"],
        "Shareholder": ["company"],
    }
    if doctype in override:
        return override[doctype]

    meta = frappe.get_meta(doctype)
    fields = []
    if _doctype_has_field(meta, "custom_company"):
        fields.append("custom_company")
    if _doctype_has_field(meta, "company"):
        fields.append("company")
    return fields


def _doctype_has_field(meta, fieldname):
    return any(f.fieldname == fieldname for f in (meta.fields or []))

# def validate_company_matching(doc, method=None):
#     # Get company from either 'company' or 'custom_company' field
#     company = None
#     if hasattr(doc, 'company') and doc.company:
#         company = doc.company
#     elif hasattr(doc, 'custom_company') and doc.custom_company:
#         company = doc.custom_company
    
#     # If no company field found, return


    
#     errors = []
    
#     # Validate Supplier
#     if hasattr(doc, 'supplier') and doc.supplier:
#         supplier_company = frappe.db.get_value('Supplier', doc.supplier, 'custom_company')
#         if not supplier_company:
#             supplier_company = frappe.db.get_value('Supplier', doc.supplier, 'company')
        
#         if supplier_company and supplier_company != company:
#             errors.append(
#                 _("Supplier '{0}' belongs to company '{1}'").format(
#                     doc.supplier, supplier_company
#                 )
#             )
    
#     # Validate Customer
#     if hasattr(doc, 'customer') and doc.customer:
#         customer_company = frappe.db.get_value('Customer', doc.customer, 'custom_company')
#         if not customer_company:
#             customer_company = frappe.db.get_value('Customer', doc.customer, 'company')
        
#         if customer_company and customer_company != company:
#             errors.append(
#                 _("Customer '{0}' belongs to company '{1}'").format(
#                     doc.customer, customer_company
#                 )
#             )
    
#     # Validate Employee
#     if hasattr(doc, 'employee') and doc.employee:
#         employee_company = frappe.db.get_value('Employee', doc.employee, 'custom_company')
#         if not employee_company:
#             employee_company = frappe.db.get_value('Employee', doc.employee, 'company')
        
#         if employee_company and employee_company != company:
#             errors.append(
#                 _("Employee '{0}' belongs to company '{1}'").format(
#                     doc.employee, employee_company
#                 )
#             )
    
#     # Validate Items in child table
#     if hasattr(doc, 'items') and doc.items:
#         item_codes = [item.item_code for item in doc.items if item.item_code]
#         if item_codes:
#             # Fetch all items in one query for better performance
#             item_companies = frappe.get_all(
#                 'Item',
#                 filters={'name': ['in', item_codes]},
#                 fields=['name', 'custom_company', 'company']
#             )
            
#             item_company_map = {}
#             for item in item_companies:
#                 # Prefer custom_company, fallback to company
#                 item_company_map[item.name] = item.custom_company or item.company
            
#             mismatched_items = []
#             for item_code in item_codes:
#                 item_company = item_company_map.get(item_code)
#                 if item_company and item_company != company:
#                     mismatched_items.append(item_code)
            
#             if mismatched_items:
#                 errors.append(
#                     _("The following items do not belong to company '{0}': {1}").format(
#                         company, ', '.join(mismatched_items)
#                     )
#                 )
    
#     # Validate custom_suppliers field if exists
#     if hasattr(doc, 'custom_suppliers') and doc.custom_suppliers:
#         supplier_company = frappe.db.get_value('Supplier', doc.custom_suppliers, 'custom_company')
#         if not supplier_company:
#             supplier_company = frappe.db.get_value('Supplier', doc.custom_suppliers, 'company')
        
#         if supplier_company and supplier_company != company:
#             errors.append(
#                 _("Supplier '{0}' in custom_suppliers belongs to company '{1}'").format(
#                     doc.custom_suppliers, supplier_company
#                 )
#             )
    
#     # Validate customer_name field if exists
#     if hasattr(doc, 'customer_name') and doc.customer_name:
#         # Assuming customer_name is a link to Customer doctype
#         customer_company = frappe.db.get_value('Customer', doc.customer_name, 'custom_company')
#         if not customer_company:
#             customer_company = frappe.db.get_value('Customer', doc.customer_name, 'company')
        
#         if customer_company and customer_company != company:
#             errors.append(
#                 _("Customer '{0}' in customer_name belongs to company '{1}', but the document is for company '{2}'").format(
#                     doc.customer_name, customer_company, company
#                 )
#             )
    
#     # If there are any errors, raise validation error
#     if errors:
#         frappe.throw(
#             '<br>'.join(errors),
#             title=_('Company Mismatch Error'),
#             exc=frappe.ValidationError
#         )
# # import frappe
# # from frappe import _

# # def validate_company_matching(doc, method=None):
  
# #     if not doc.company:
# #         return
    
# #     company = doc.company
# #     errors = []
    
# #     # Validate Supplier
# #     if hasattr(doc, 'supplier') and doc.supplier:
# #         supplier_company = frappe.db.get_value('Supplier', doc.supplier, 'custom_company')
# #         if supplier_company and supplier_company != company:
# #             errors.append(
# #                 _("Supplier '{0}' belongs to company '{1}").format(
# #                     doc.supplier, supplier_company
# #                 )
# #             )
    
# #     # Validate Customer
# #     if hasattr(doc, 'customer') and doc.customer:
# #         customer_company = frappe.db.get_value('Customer', doc.customer, 'custom_company')
# #         if customer_company and customer_company != company:
# #             errors.append(
# #                 _("Customer '{0}' belongs to company '{1}'").format(
# #                     doc.customer, customer_company
# #                 )
# #             )
    
# #     # Validate Employee
# #     if hasattr(doc, 'employee') and doc.employee:
# #         employee_company = frappe.db.get_value('Employee', doc.employee, 'custom_company')
# #         if employee_company and employee_company != company:
# #             errors.append(
# #                 _("Employee '{0}' belongs to company '{1}'").format(
# #                     doc.employee, employee_company, company
# #                 )
# #             )
    
# #     # Validate Items in child table
# #     if hasattr(doc, 'items') and doc.items:
# #         item_codes = [item.item_code for item in doc.items if item.item_code]
        
# #         if item_codes:
# #             # Fetch all items in one query for better performance
# #             item_companies = frappe.get_all(
# #                 'Item',
# #                 filters={'name': ['in', item_codes]},
# #                 fields=['name', 'custom_company']
# #             )
            
# #             item_company_map = {item.name: item.custom_company for item in item_companies}
            
# #             mismatched_items = []
# #             for item_code in item_codes:
# #                 item_company = item_company_map.get(item_code)
# #                 if item_company and item_company != company:
# #                     mismatched_items.append(item_code)
            
# #             if mismatched_items:
# #                 errors.append(
# #                     _("The following items do not belong to company '{0}': {1}").format(
# #                         company, ', '.join(mismatched_items)
# #                     )
# #                 )
    
# #     # Validate custom_suppliers field if exists
# #     if hasattr(doc, 'custom_suppliers') and doc.custom_suppliers:
# #         supplier_company = frappe.db.get_value('Supplier', doc.custom_suppliers, 'custom_company')
# #         if supplier_company and supplier_company != company:
# #             errors.append(
# #                 _("Supplier '{0}' in custom_suppliers belongs to company '{1}'").format(
# #                     doc.custom_suppliers, supplier_company
# #                 )
# #             )
    
# #     # Validate customer_name field if exists
# #     if hasattr(doc, 'customer_name') and doc.customer_name:
# #         # Assuming customer_name is a link to Customer doctype
# #         customer_company = frappe.db.get_value('Customer', doc.customer_name, 'custom_company')
# #         if customer_company and customer_company != company:
# #             errors.append(
# #                 _("Customer '{0}' in customer_name belongs to company '{1}', but the document is for company '{2}'").format(
# #                     doc.customer_name, customer_company, company
# #                 )
# #             )
    
# #     # If there are any errors, raise validation error
# #     if errors:
# #         frappe.throw(
# #             '<br>'.join(errors),
# #             title=_('Company Mismatch Error'),
# #             exc=frappe.ValidationError
# #         )
