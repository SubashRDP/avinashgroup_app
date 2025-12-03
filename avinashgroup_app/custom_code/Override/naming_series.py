import frappe
from frappe.model.naming import make_autoname
from frappe.model.document import Document


def get_fiscal_year_from_date(date_field):
    if not date_field:
        return None
    
    fiscal_year = frappe.db.get_value(
        "Fiscal Year",
        {
            "year_start_date": ["<=", date_field],
            "year_end_date": [">=", date_field]
        },
        "name"
    )
    
    return fiscal_year

def get_company_abbr(doc):
    
    company_name = None

    if hasattr(doc, "company") and doc.company:
        company_name = doc.company

    elif hasattr(doc, "custom_company") and doc.custom_company:
        company_name = doc.custom_company

    if not company_name:
        return None

    return frappe.get_cached_value("Company", company_name, "abbr")


def make_name_simple(prefix, doc, sequence_length=5):
    """
    Generate simple name with company abbreviation (no fiscal year) for Masters 
    """
    company_abbr = get_company_abbr(doc)
    sequence = "#" * sequence_length
    
    if company_abbr:
        naming_pattern = f'{company_abbr}-{prefix}-.{sequence}'
    else:
        naming_pattern = f'{prefix}-.{sequence}'
    
    return make_autoname(naming_pattern)

def make_name_with_fiscal_year(prefix, doc, sequence_length=7):
    company_abbr = get_company_abbr(doc)

    date_field = None
    if hasattr(doc, "posting_date") and doc.posting_date:
        date_field = doc.posting_date
    elif hasattr(doc, "transaction_date") and doc.transaction_date:
        date_field = doc.transaction_date

    fiscal_year = None
    if date_field:
        fiscal_year = get_fiscal_year_from_date(date_field)

    # Build naming pattern
    sequence = "#" * sequence_length

    if company_abbr and fiscal_year:
        naming_pattern = f".{company_abbr}.-{prefix}-.{sequence}.-.{fiscal_year}."
    elif company_abbr:
        naming_pattern = f"{company_abbr}-{prefix}-.{sequence}"
    else:
        naming_pattern = f"{prefix}-.{sequence}"

    return make_autoname(naming_pattern)


def autoname(self, method):
    
    doctype = self.doctype

    if doctype == "Customer":
            self.name = make_name_simple("CUS", self, sequence_length=5)
    elif doctype == "Sales Invoice":

        if hasattr(self, "is_return") and self.is_return == 1:
            self.name = make_name_with_fiscal_year("SINV-RET", self, sequence_length=7)
        else:
            self.name = make_name_with_fiscal_year("SINV", self, sequence_length=7)
    elif  doctype == "Purchase Invoice":
            if hasattr(self, "is_return") and self.is_return == 1:
                self.name = make_name_with_fiscal_year("PUR-RET", self, sequence_length=7)
            else:    
                self.name = make_name_with_fiscal_year("PUR", self, sequence_length=7)
    elif doctype == "Purchase Receipt":
            if hasattr(self, "is_return") and self.is_return == 1:
                self.name = make_name_simple("PR-RET", self, sequence_length=5)
            else:
                self.name = make_name_simple("PR", self, sequence_length=5)


    elif doctype == "Customer":
            self.name = make_name_simple("CUS", self, sequence_length=5)
    elif doctype == "Supplier":
            self.name = make_name_simple("SUPPP", self, sequence_length=5)
    elif doctype == "Employee":
            self.name = make_name_simple("EMP", self, sequence_length=5)
    elif doctype == "Stock Reconciliation":
            self.name = make_name_simple("MAT-RECO", self, sequence_length=5)
    elif doctype == "Payment Entry":
            self.name = make_name_simple("PAY", self, sequence_length=5)
    elif doctype == "Delivery Note":
            self.name = make_name_simple("MAT-DN", self, sequence_length=5)
    elif doctype == "Sales Order":
            self.name = make_name_simple("SO", self, sequence_length=5)

    
 
        #   # Switch-like condition structure for different DocTypes
        # if doctype == "Customer":
        #     self.name = make_autoname('CUST-.####')
            
        # elif doctype == "Supplier":
        #     self.name = make_autoname('SUPP-.####')
            
        # elif doctype == "Sales Invoice":
        #     # Get company abbreviation from company field
        #     if hasattr(self, 'company') and self.company:
        #         company_abbr = frappe.get_cached_value('Company', self.company, 'abbr')
        #         self.name = make_autoname(f'{company_abbr}-INV-.YYYY.-.#####')
        #     else:
        #         self.name = make_autoname('INV-.YYYY.-.#####')
            
        # elif doctype == "Purchase Order":
        #     self.name = make_autoname('PO-.YY.MM.-.####')

        # elif doctype == "Purchase Invoice":
        #     self.name = make_name_with_fiscal_year("PUR", self, sequence_length=7)

        # else: 
        #     pass




# class CustomDocument(Document):
#     def autoname(self):
#         doctype = self.doctype
         
#         if doctype == "Purchase Invoice":
#             self.name = make_name_with_fiscal_year("PUR", self, sequence_length=7)
        
#         elif doctype == "Sales Invoice":
#             self.name = make_name_with_fiscal_year("SINV", self, sequence_length=7)
        
#         elif doctype == "Customer":
#             self.name = make_name_simple("CUS", self, sequence_length=5)
        
#         else:
#             pass


# def run_custom_autoname(doc, method):
#     # create an instance of your class using the existing doc
#     handler = CustomDocument(doc)
#     handler.autoname()


# def universal_autoname(doc, method):

#     doctype = doc.doctype
    
#     # Switch-like condition structure for different DocTypes
#     if doctype == "Customer": 
#             company_abbr = frappe.get_cached_value('Company', doc.custom_company, 'abbr')
#             doc.name = make_autoname(f'{company_abbr}.-CUS-.####')

#     elif doctype == "Supplier":
#         company_abbr = frappe.get_cached_value('Company', doc.custom_company, 'abbr')
#         doc.name = make_autoname(f'{company_abbr}.-SUP-.####')
    
#     elif doctype == "Employee":
#         company_abbr = frappe.get_cached_value('Company', doc.company, 'abbr')
#         doc.name = make_autoname(f'{company_abbr}.-EMP-.####')

#     elif doctype == "Stock Reconciliation":
#         company_abbr = frappe.get_cached_value('Company', doc.company, 'abbr')
#         doc.name = make_autoname(f'{company_abbr}.-MAT-.RECO.-.#####')

#     # elif doctype == "Purchase Invoice":
#     #     company_abbr = frappe.get_cached_value('Company', doc.company, 'abbr')
#     #     fiscal_year = 
#     #     doc.name = make_autoname(f.{custom_abbr}.-PUR-.#######.-.{custom_fiscal_year}')


    
        
#     # elif doctype == "Sales Invoice":
#     #     # Get company abbreviation from company field
#     #     if hasattr(doc, 'company') and doc.company:
#     #         company_abbr = frappe.get_cached_value('Company', doc.company, 'abbr')
#     #         doc.name = make_autoname(f'{company_abbr}-INV-.YYYY.-.#####')
#     #     else:
#     #         doc.name = make_autoname('INV-.YYYY.-.#####')
        
#     # elif doctype == "Purchase Order":
#     #     doc.name = make_autoname('PO-.YY.MM.-.####')
        
#     # elif doctype == "Sales Order":
#     #     doc.name = make_autoname('SO-.YYYY.-.#####')
        
#     # elif doctype == "Quotation":
#     #     doc.name = make_autoname('QTN-.YY.-.####')
        
#     # elif doctype == "Delivery Note":
#     #     doc.name = make_autoname('DN-.YYYY.MM.-.####')
        
#     # elif doctype == "Payment Entry":
#     #     doc.name = make_autoname('PAY-.YYYY.-.#####')
        
#     # elif doctype == "Journal Entry":
#     #     doc.name = make_autoname('JV-.YYYY.-.#####')
        
#     # elif doctype == "Employee":
#     #     doc.name = make_autoname('EMP-.#####')
        
#     # elif doctype == "Project":
#     #     doc.name = make_autoname('PROJ-.YYYY.-.####')
        
#     # elif doctype == "Task":
#     #     doc.name = make_autoname('TASK-.#####')
        
#     # elif doctype == "Lead":
#     #     doc.name = make_autoname('LEAD-.#####')
        
#     # elif doctype == "Opportunity":
#     #     doc.name = make_autoname('OPP-.YYYY.-.####')
        
#     # elif doctype == "Material Request":
#     #     doc.name = make_autoname('MR-.YYYY.-.#####')
        
#     # elif doctype == "Stock Entry":
#     #     doc.name = make_autoname('STE-.YYYY.MM.-.#####')
        
#     # elif doctype == "Purchase Receipt":
#     #     doc.name = make_autoname('PR-.YYYY.-.#####')
        
#     # elif doctype == "Issue":
#     #     doc.name = make_autoname('ISS-.#####')
        
#     # elif doctype == "Timesheet":
#     #     doc.name = make_autoname('TS-.YYYY.MM.-.####')
        
#     # elif doctype == "Expense Claim":
#     #     doc.name = make_autoname('EXP-.YYYY.-.####')
        
#     else:
#         # For DocTypes not listed above, let default naming take over
#         # Don't set doc.name - ERPNext will use its default naming
#         pass

