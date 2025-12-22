import frappe
from frappe.model.naming import make_autoname
from frappe.model.document import Document

## "Item", "Salary Structure", "Contact"
NAMING_CONFIG = {
    #MASTERS DATA
    "Holiday List": {
        "prefix": "Holiday",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Request for Quotation": {
        "prefix": "RFQ",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Supplier Quotation": {
        "prefix": "SQ",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Item Group": {
        "prefix": "I.GR",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Item":{
        "prefix": "ITEM",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Price List": {
        "prefix": "P.List",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Branch": {
        "prefix": "Branch",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Operation": {
        "prefix": "OPR",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Workstation": {
        "prefix": "WS",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Routing": {
        "prefix": "ROU",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Asset Category": {
        "prefix": "A.Cat",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Asset": {
        "prefix": "AST",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Project": {
        "prefix": "PROJ",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Task": {
        "prefix": "TASK",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Serial No": {
        "prefix": "SRLNO",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Batch": {
        "prefix": "BATCH",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Expense Claim Type": {
        "prefix": "EC.Type",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Mode of Payment": {
        "prefix": "MOP",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Bank Account": {
        "prefix": "B.AC",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Leave Type": {
        "prefix": "L.Type",
        "use_fiscal_year": False,
        "sequence_length": 5
    },

    "Customer":{
        "prefix": "CUS",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
     "Customer Group":{
        "prefix": "C.GR",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Supplier":{
        "prefix": "SUP",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Supplier Group":{
        "prefix": "S.GR",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Employee":{
        "prefix": "EMP",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Address":{
        "prefix": "ADD",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Contact":{
        "prefix": "CON",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "BOM":{
        "prefix": "BOM",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Salary Structure":{
        "prefix": "SAL-STR",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Sales Order": {
        "prefix": "SO",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Sales Invoice": {
        "prefix": "SB",
        "return_prefix": "SRTN",
        "use_fiscal_year": True,
        "sequence_length": 5,
        "has_custom_name": True
    },
    "Delivery Note": {
        "prefix": "DN",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Quotation": {
        "prefix": "QTN",
        "use_fiscal_year": True,
        "sequence_length": 5
    },

    "Purchase Order": {
        "prefix": "PO",
        "use_fiscal_year": True,
        "sequence_length": 5,
        "has_custom_name": True
    },
    "Purchase Receipt": {
        "prefix": "GRN",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    # "Purchase Receipt Return": {
    #     "prefix": "PRRET",
    #     "use_fiscal_year": True,
    #     "sequence_length": 5
    # },
    "Purchase Invoice": {
        "prefix": "PI",
        "return_prefix": "PRTN",
        "use_fiscal_year": True,
        "sequence_length": 5,
        "has_custom_name": True
    },
    # "Purchase Invoice Return": {
    #     "prefix": "PIR",
    #     "use_fiscal_year": True,
    #     "sequence_length": 5
    # },

    "Material Request": {
        "prefix": "MR",
        "use_fiscal_year": True,
        "sequence_length": 5,
        "has_custom_name": True
    },
    "Material Transfer": {
        "prefix": "STE-MT",
        "use_fiscal_year": True,
        "sequence_length": 3
    },
    "Material Issue": {
        "prefix": "STE-MI",
        "use_fiscal_year": True,
        "sequence_length": 3
    },
    "Material Receipt": {
        "prefix": "STE-MR",
        "use_fiscal_year": True,
        "sequence_length": 3
    },
    "Stock Entry": {
        "prefix": "STE",
        "use_fiscal_year": True,
        "sequence_length": 3
    },
    "Stock Reconciliation": {
        "prefix": "SR",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Stock Reservation Entry": {
        "prefix": "SRE",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Pick List": {
        "prefix": "PICK",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Packing Slip": {
        "prefix": "PACK",
        "use_fiscal_year": True,
        "sequence_length": 5
    },

    "Payment Entry": {
        "prefix": "PAY.REC",
        "use_fiscal_year": True,
        "sequence_length": 5,
        "has_custom_name": True
    },
    "Payment Term":{
        "prefix": "PT",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Payment Request": {
        "prefix": "PREQ",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Payment Order": {
        "prefix": "PORDER",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Bank Transaction": {
        "prefix": "BTN",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Journal Entry": {
        "prefix": "JE",
        "use_fiscal_year": True,
        "sequence_length": 5,
        "has_custom_name": True
    },
    "Landed Cost Voucher": {
        "prefix": "LCV",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Expense Claim": {
        "prefix": "EC.Type",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Employee Advance": {
        "prefix": "EADV",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Work Order"  : {
        "prefix": "WO",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Job Card" : {
        "prefix": "JC",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Manufacturing Entry"  : {
        "prefix": "MFG",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Leave Application": {
        "prefix": "LEAVE",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Attendance": {
        "prefix": "ATT",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Payroll Entry": {
        "prefix": "PAYR",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Asset Movement": {
        "prefix": "AM",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Asset Repair": {
        "prefix": "AR",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Asset Capitalization": {
        "prefix": "ACAP",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Project Update": {
        "prefix": "PRJUPD",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Maintenance Visit": {
        "prefix": "MV",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Warranty Claim": {
        "prefix": "WAR",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Job Applicant": {
        "prefix": "JOBAPP",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Job Offer": {
        "prefix": "JO",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Appointment Letter": {
        "prefix": "AL",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Issue": {
        "prefix": "TKT",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Timesheet": {
        "prefix": "TS",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "BOM Update Tool":{
        "prefix": "BUPD",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Salary Slip":{
        "prefix": "SAL",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Subscription": {
        "prefix": "SUB",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "POS Profile": {
        "prefix": "POSP",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    
    "Sales Partner": {
        "prefix": "SP",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "POS Opening Entry": {
        "prefix": "POSE",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "POS Closing Entry": {
        "prefix": "POSC",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Subscription Invoice": {
        "prefix": "SUBINV",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "POS Invoice": {
        "prefix": "POSINV",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Interview":{
        "prefix": "INT",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Interview Feedback":{
        "prefix": "IF",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Training Event":{
        "prefix": "TREVT",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Opportunity":{
        "prefix": "OPPTY",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Lead":{
        "prefix": "LEAD",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Communication":{
        "prefix": "COM",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
}

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


def get_amendment_suffix(doc):
    """
    Get amendment suffix from the standard name field
    Returns: "-1", "-2", etc., or empty string if not amended
    """
    if not hasattr(doc, 'name') or not doc.name:
        return ""
    
    if not hasattr(doc, 'amended_from') or not doc.amended_from:
        return ""
    
    name = str(doc.name)
    
    import re
    match = re.search(r'-(\d+)$', name)
    
    if match:
        return f"-{match.group(1)}"
    
    return ""


def make_name_simple(prefix, doc, sequence_length=5):
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
    elif hasattr(doc, "custom_created_on") and doc.custom_created_on:
        date_field = doc.custom_created_on

    fiscal_year = None
    if date_field:
        fiscal_year = get_fiscal_year_from_date(date_field)

    sequence = "#" * sequence_length

    if company_abbr and fiscal_year:
        naming_pattern = f".{company_abbr}.-{prefix}-.{fiscal_year}.-.{sequence}."
    elif company_abbr:
        naming_pattern = f"{company_abbr}-{prefix}-.{sequence}"
    else:
        naming_pattern = f"{prefix}-.{sequence}"

    return make_autoname(naming_pattern)


def set_custom_name_field(doc):
    if not hasattr(doc, 'custom_name'):
        return
    
    company_code = get_company_abbr(doc) or ""
    
    p_type = ""
    if hasattr(doc, 'custom_p_type_code') and doc.custom_p_type_code:
        p_type = doc.custom_p_type_code
    
    doc_no = "00000"
    if hasattr(doc, 'custom_document_no') and doc.custom_document_no:
        doc_no = str(doc.custom_document_no).zfill(5)
    
    fiscal_year = "82/83"
    if hasattr(doc, 'custom_fiscal_year') and doc.custom_fiscal_year:
        fiscal_year = doc.custom_fiscal_year
    else:
        date_field = None
        if hasattr(doc, 'posting_date') and doc.posting_date:
            date_field = doc.posting_date
        elif hasattr(doc, 'transaction_date') and doc.transaction_date:
            date_field = doc.transaction_date
        
        if date_field:
            calculated_fy = get_fiscal_year_from_date(date_field)
            if calculated_fy:
                fiscal_year = calculated_fy
    
    base_custom_name = f"{company_code}-{p_type}-{doc_no}-{fiscal_year}"
    amendment_suffix = get_amendment_suffix(doc)
    doc.custom_name = f"{base_custom_name}{amendment_suffix}"


def naming_requirements_before_insert(doc):
    doctype = doc.doctype
    # frappe.msgprint("From before insert ")
    
    if doctype not in NAMING_CONFIG:
        return
    
    config = NAMING_CONFIG[doctype]
    
    # Check if company abbreviation is required and available
    company_abbr = get_company_abbr(doc)
    if not company_abbr:
        frappe.throw(
            f"Company abbreviation is required for {doctype}. Please ensure 'Company' field is set with a valid company.",
            title="Missing Company Abbreviation"
        )
    
    # Check fiscal year requirement
    if config["use_fiscal_year"]:
        # Get the first available date field with content
        date_field = (
            (getattr(doc, "posting_date", None) if hasattr(doc, "posting_date") else None) or
            (getattr(doc, "transaction_date", None) if hasattr(doc, "transaction_date") else None) or
            (getattr(doc, "custom_created_on", None) if hasattr(doc, "custom_created_on") else None)
        )
        
        if not date_field:
            frappe.throw(
                f"Date field (posting_date, transaction_date, or custom_created_on) is required for {doctype}.",
                title="Missing Date Field"
            )
        
        fiscal_year = get_fiscal_year_from_date(date_field)
        if not fiscal_year:
            frappe.throw(
                f"No fiscal year found for date {date_field}. Please ensure fiscal year is set up correctly in the system.",
                title="Missing Fiscal Year"
            )

def handle_before_insert(doc, method=None):
    naming_requirements_before_insert(doc)

def handle_validate(doc, method=None):
    set_custom_name_field(doc)


def naming_series_autoname(self, method):
    doctype = self.doctype
    # Check if doctype has naming configuration
    if doctype not in NAMING_CONFIG:
        return
    
    config = NAMING_CONFIG[doctype]
    
    # Determine prefix (check for return documents)
    prefix = config["prefix"]
    if hasattr(self, "is_return") and self.is_return == 1 and "return_prefix" in config:
        prefix = config["return_prefix"]
    
    # Generate name based on configuration
    if config["use_fiscal_year"]:
        self.name = make_name_with_fiscal_year(
            prefix, 
            self, 
            sequence_length=config["sequence_length"]
        )
    else:
        self.name = make_name_simple(
            prefix, 
            self, 
            sequence_length=config["sequence_length"]
        )
    
    # Set custom name field if configured
    if config.get("has_custom_name", False):
        set_custom_name_field(self)