import frappe
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice

class CustomPurchaseInvoice(PurchaseInvoice):
    def autoname(self):
        company_code = self.custom_abbr 
        purchase_type = self.custom_purchase_type_code 
        doc_no = str(self.custom_document_no).zfill(5) if self.custom_document_no else "00000"
        fiscal_year = self.custom_fiscal_year
        # self.name = f"{company_code}-{purchase_type}-{doc_no}-{fiscal_year}"
        
        if self.is_return:
            self.name = f"{company_code}-RTN-{doc_no}-{fiscal_year}"
        else:
            self.name = f"{company_code}-{purchase_type}-{doc_no}-{fiscal_year}"


import frappe

def set_custom_name_field(doc, method):
    company_code = doc.custom_abbr or ""
    
    p_type = ""
    if doc.custom_p_type:
        p_type = frappe.db.get_value(
            "Payment - Receipt Type", 
            doc.custom_p_type, 
            "data_hrcj"
        ) or ""
    
    doc_no = str(doc.custom_document_no).zfill(5) if doc.custom_document_no else "00000"
    fiscal_year = doc.custom_fiscal_year or ""
    
    doc.custom_name = f"{company_code}-{p_type}-{doc_no}-{fiscal_year}"





def set_custom_name_jv(doc, method):
    company_code = doc.custom_abbr or ""
    
    p_type = ""
    if doc.custom_p_type:
        p_type = frappe.db.get_value(
            "JV Type", 
            doc.custom_p_type, 
            "jv_type_code"
        ) or ""
    
    doc_no = str(doc.custom_document_no).zfill(5) if doc.custom_document_no else "00000"
    fiscal_year = doc.custom_fiscal_year or ""
    
    doc.custom_name = f"{company_code}-{p_type}-{doc_no}-{fiscal_year}"