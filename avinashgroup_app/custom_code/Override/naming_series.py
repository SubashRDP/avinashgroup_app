import re
import frappe
from frappe.model.naming import make_autoname, getseries
from frappe.model.document import Document

BRANCH_NAME_COMPANY = "Grishma Enterprises Pvt. Ltd."

# branch_code per doctype per branch (normal and return)
BRANCH_CODE_CONFIG = {
    "Sales Invoice": {
        "GEPL-Branch-00001": {"normal": "INV", "return": "RT"},
        "GEPL-Branch-00002":     {"normal": "SB",  "return": "BSR"},
        "GEPL-Branch-00003":    {"normal": "GEP", "return": "RTN"},
    },
    "Purchase Receipt": {
        "GEPL-Branch-00001": {"normal": "AN"},
        "GEPL-Branch-00002":     {"normal": "BRC"},
        "GEPL-Branch-00003":    {"normal": "RC"},
    },
    "Purchase Invoice": {
        "GEPL-Branch-00001": {"normal": "PBA"},
        "GEPL-Branch-00002":     {"normal": "PBB"},
        "GEPL-Branch-00003":    {"normal": "PB"},
    },
}

## "Item", "Salary Structure", "Contact"
NAMING_CONFIG = {
    #MASTERS DATA
    "Vehicle" : {
        "prefix": "VEH",
        "sequence_length": 5,
        "use_fiscal_year": False
    },
    "Vehicle Log" : {
        "prefix": "VeLOG",
        "sequence_length": 5,
        "use_fiscal_year": True
    },
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
    "Item Price": {
        "prefix": "ITEM-P",
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
    # "Leave Type": {
    #     "prefix": "L.Type",
    #     "use_fiscal_year": False,
    #     "sequence_length": 5
    # },

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
        "has_custom_name": True,
        "has_branch_name": True
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
        "has_custom_name": True,
        "purchase_type_field": "custom_purchase_type"
    },
    "Purchase Receipt": {
        "prefix": "GRN",
        "use_fiscal_year": True,
        "sequence_length": 5,
        "has_custom_name": True,
        "has_branch_name": True,
        "purchase_type_field": "custom_receipt_type"
    },
    "Purchase Invoice": {
        "prefix": "PI",
        "return_prefix": "PRTN",
        "use_fiscal_year": True,
        "sequence_length": 5,
        "has_custom_name": True,
        "has_branch_name": True,
        "purchase_type_field": "custom_purchase_type"
    },

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
    "Leave Allocation": {
        "prefix": "HR-LAL",
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
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Communication":{
        "prefix": "COM",
        "use_fiscal_year": True,
        "sequence_length": 5
    },
    "Designation": {
        "prefix": "DESIG",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Shift Type": {
        "prefix": "SHIFT",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Asset Maintenance Team": {
        "prefix": "ASSET-MT",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Asset Value Adjustment": {
        "prefix": "ASSET-ADJ",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Prospect": {
        "prefix": "PROSPECT",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
    "Manufacturer": {
        "prefix": "MANUFACTURER",
        "use_fiscal_year": False,
        "sequence_length": 5
    },
}

AUTO_NUMBER_CONFIG = {
    "Purchase Receipt": {
        "type_field": "custom_receipt_type",
        "types": [
            "Other Purchase Receipt",
        ]
    },
    "Purchase Invoice": {
        "type_field": "custom_purchase_type",
        "types": [
            "Purchase Return",
        ]
    },
    "Payment Entry": {
        "type_field": "custom_p_type",
        "types": [
            "Bank Customers Receipt",
            "NOC Payment",
            "Contra Voucher- cash to bank",
        ]
    },
    "Journal Entry": {
        "type_field": "custom_p_type",
        "types": [
            "Bank Entry",
            "Party Journal",
            "Debit Note",
            "Credit Note",
        ]
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


def _get_doc_no_digits(doctype):
    try:
        rows = frappe.get_all(
            "Voucher Number Settings Item",
            filters={"doctype_name": doctype},
            fields=["voucher_no_digits"],
            limit=1
        )
        if rows:
            return int(rows[0].voucher_no_digits or 6)
    except Exception:
        pass
    return 6


def format_document_number(doc):
    digits = _get_doc_no_digits(doc.doctype)
    doc_no = "0" * digits
    doc_word = ""

    if hasattr(doc, 'custom_document_no') and doc.custom_document_no:
        doc_no = str(doc.custom_document_no).zfill(digits)

    if hasattr(doc, 'custom_document_word') and doc.custom_document_word:
        doc_word = str(doc.custom_document_word).strip()

    return f"{doc_no}{doc_word}"


def set_auto_document_no(doc):
    """
    Auto-sets custom_document_no for new documents whose type matches
    AUTO_NUMBER_CONFIG. Falls back to manual entry if the type is not configured.

    custom_p_type_code is NOT modified here — it must already be set on the doc
    from the UI before this function runs.
    """
    doctype = doc.doctype

    if not hasattr(doc, "custom_document_no"):
        return


    if doctype not in AUTO_NUMBER_CONFIG:
        return

    cfg = AUTO_NUMBER_CONFIG[doctype]
    type_field = cfg.get("type_field")
    type_value = getattr(doc, type_field, None) if type_field else None
    types = cfg.get("types", [])

    # If the selected type is not in config, leave custom_document_no untouched
    if isinstance(types, dict):
        if not type_value or type_value not in types:
            return
    elif isinstance(types, list):
        if not type_value or type_value not in types:
            return
    else:
        return

    # Read custom_p_type_code — set by UI from the linked type doctype
    prefix = getattr(doc, "custom_p_type_code", None)
    company_abbr = get_company_abbr(doc)

    if not prefix or not company_abbr:
        return

    fiscal_year = None
    if hasattr(doc, "custom_fiscal_year") and doc.custom_fiscal_year:
        fiscal_year = doc.custom_fiscal_year
    else:
        date_field = None
        if hasattr(doc, "posting_date") and doc.posting_date:
            date_field = doc.posting_date
        elif hasattr(doc, "transaction_date") and doc.transaction_date:
            date_field = doc.transaction_date
        elif hasattr(doc, "custom_created_on") and doc.custom_created_on:
            date_field = doc.custom_created_on

        if date_field:
            fiscal_year = get_fiscal_year_from_date(date_field)

    if not fiscal_year:
        return

    # Filter by custom_name pattern — reliable because it is set on ALL documents
    # regardless of whether older docs have the type_field populated.
    # Pattern: {company_abbr}-{p_type_code}-*-{fiscal_year} e.g. SGU-RC-000006-82/83
    name_pattern = f"{company_abbr}-{prefix}-%-{fiscal_year}%"

    if getattr(doc, "custom_document_no", None):
        similar_docs = frappe.db.get_value(
            doctype,
            filters={"custom_document_no": doc.custom_document_no,
                     "custom_name": ["like", name_pattern]},
            fieldname="name"
            
        )
        if similar_docs:           
            frappe.throw(
                f"Document number {doc.custom_document_no} already exists for the {similar_docs}. Please enter a different number.",
                title="Duplicate Document Number"
            )
        return


    max_no = frappe.db.get_value(
        doctype,
        filters={
            "custom_name": ["like", name_pattern],
        },
        fieldname="max(custom_document_no)",
    ) or 0

    doc.custom_document_no = int(max_no) + 1


@frappe.whitelist()
def get_next_custom_document_no(**kwargs):
    """
    Client helper: return next custom_document_no for a draft doc.
    Respects AUTO_NUMBER_CONFIG rules; returns None if type is not eligible.
    """
    doc = frappe._dict(kwargs)
    set_auto_document_no(doc)
    return getattr(doc, "custom_document_no", None)


def set_custom_name_field(doc):
    if not hasattr(doc, 'custom_name'):
        return
    company_name = None
    if hasattr(doc, 'company') and doc.company:
        company_name = doc.company
    elif hasattr(doc, 'custom_company') and doc.custom_company:
        company_name = doc.custom_company
    if company_name and company_name == "Grihalaxmi Metal Industries Pvt. Ltd":
        doc.custom_name = ""
        return

    company_code = get_company_abbr(doc) or ""

    p_type = ""
    if hasattr(doc, 'custom_p_type_code') and doc.custom_p_type_code:
        p_type = doc.custom_p_type_code

    doc_no = format_document_number(doc)

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

    if doctype not in NAMING_CONFIG:
        return

    config = NAMING_CONFIG[doctype]

    company_abbr = get_company_abbr(doc)
    if not company_abbr:
        frappe.throw(
            f"Company abbreviation is required for {doctype}. Please ensure 'Company' field is set with a valid company.",
            title="Missing Company Abbreviation"
        )

    if config["use_fiscal_year"]:
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


def set_custom_branch_name(doc):
    """
    Sets custom_branch_name field based on branch-wise naming.
    Format: {company_abbr}-{branch_code}-{######}-{fiscal_year}
    Only generated once (skipped if already set).
    For non-Grishma companies: custom_branch_name = doc.name
    """
    if not hasattr(doc, 'custom_branch_name'):
        return

    if doc.custom_branch_name:
        return

    company_name = None
    if hasattr(doc, 'company') and doc.company:
        company_name = doc.company
    elif hasattr(doc, 'custom_company') and doc.custom_company:
        company_name = doc.custom_company

    if not company_name or company_name != BRANCH_NAME_COMPANY:
        doc.custom_branch_name = doc.name or ""
        return

    if doc.doctype not in BRANCH_CODE_CONFIG:
        doc.custom_branch_name = doc.name or ""
        return

    branch = getattr(doc, 'custom_branch', None)
    if not branch:
        doc.custom_branch_name = doc.name or ""
        return

    branch_config = BRANCH_CODE_CONFIG[doc.doctype]
    if branch not in branch_config:
        doc.custom_branch_name = doc.name or ""
        return

    is_return = getattr(doc, 'is_return', 0)
    if is_return:
        branch_code = branch_config[branch].get("return", branch_config[branch]["normal"])
    else:
        branch_code = branch_config[branch]["normal"]

    company_abbr = get_company_abbr(doc) or ""

    fiscal_year = ""
    date_field = None
    if hasattr(doc, 'posting_date') and doc.posting_date:
        date_field = doc.posting_date
    elif hasattr(doc, 'transaction_date') and doc.transaction_date:
        date_field = doc.transaction_date
    if date_field:
        fiscal_year = get_fiscal_year_from_date(date_field) or ""

    series_key = f"{company_abbr}-{branch_code}-{fiscal_year}-"
    seq_number = getseries(series_key, 6)

    doc.custom_branch_name = f"{company_abbr}-{branch_code}-{seq_number}-{fiscal_year}"


def handle_before_insert(doc, method=None):
    naming_requirements_before_insert(doc)


def handle_validate(doc, method=None):
    if doc.is_new():
        set_auto_document_no(doc)
    set_custom_name_field(doc)
    set_custom_branch_name(doc)


def handle_before_save(doc, method=None):
    """
    Ensure numbering happens after fields like custom_p_type_code
    are set (often during save). This is the final chance before insert.
    """
    if doc.is_new():
        set_auto_document_no(doc)
    set_custom_name_field(doc)
    set_custom_branch_name(doc)


def naming_series_autoname(self, method):
    doctype = self.doctype
    if doctype not in NAMING_CONFIG:
        return

    config = NAMING_CONFIG[doctype]

    prefix = config["prefix"]
    if hasattr(self, "is_return") and self.is_return == 1 and "return_prefix" in config:
        prefix = config["return_prefix"]

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

    if config.get("has_branch_name", False):
        set_custom_branch_name(self)
