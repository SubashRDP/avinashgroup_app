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




