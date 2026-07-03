import re
import frappe
from frappe.model.naming import make_autoname, getseries
from frappe.model.document import Document

# NOTE: the old BRANCH_CODE_CONFIG / BRANCH_NAME_COMPANY hardcoded branch
# numbering was migrated to seeded "Numbering Configuration" rules — see
# avinashgroup_app/scripts/seed_numbering_rules.py (identical formats and
# tabSeries keys, so sequences continue unchanged).

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
        # The number was entered manually. Do NOT reject here on the bare
        # custom_document_no: the real voucher number is number + word
        # (custom_document_word), so "65" and "65A" are *different* vouchers
        # and must both be allowed. Uniqueness of the full voucher number is
        # enforced downstream by validate_custom_name_unique() against
        # custom_name — the single source of truth for duplicates. Keep the
        # user's number untouched.
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

    fiscal_year = ""
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


def validate_document_no(doc):
    """
    Document No. (custom_document_no) must be a whole number greater than zero
    — no decimals, no letters, no negatives. The letter part of a voucher
    number always lives in custom_document_word, never here, so the number
    itself is a plain positive integer for every doctype that carries the field
    (Payment Entry, Journal Entry, Purchase Invoice, Purchase Receipt, and any
    future doctype that adds custom_document_no).

    Empty is allowed on purpose: auto-numbered types fill it with
    "highest + 1" via set_auto_document_no(), so only a *non-empty* value is
    checked here. Companies/doctypes that skip custom_name — e.g. Grihalaxmi
    Metal Industries, where set_custom_name_field() blanks it — are exempt.
    """
    if not getattr(doc, "custom_name", ""):
        return

    if not hasattr(doc, "custom_document_no"):
        return

    raw = getattr(doc, "custom_document_no", None)
    s = "" if raw is None else str(raw).strip()

    # Empty / 0 == "not entered" → left to the highest-number+1 auto-assign.
    if s in ("", "0"):
        return

    if not re.fullmatch(r"\d+", s) or int(s) <= 0:
        frappe.throw(
            f"Document No. must be a whole number greater than zero "
            f"(no decimals or letters). Got: {raw}",
            title="Invalid Document Number",
        )


def validate_custom_name_unique(doc):
    """
    Guard against duplicate custom_name / custom_document_no.

    Runs for EVERY document that has a non-empty custom_name, regardless of
    whether its type is listed in AUTO_NUMBER_CONFIG. The auto-number path in
    set_auto_document_no() only validates the small set of auto-numbered types
    (e.g. Purchase Return), so manually-numbered documents — like a normal
    Purchase Invoice — would otherwise save duplicate custom_document_no values
    that collapse into an identical custom_name. This closes that gap.

    Cancelled documents (docstatus = 2) are ignored so an amendment can reuse
    the original number; the -1/-2 amendment suffix already makes the amended
    custom_name distinct anyway. The document itself is excluded by name.
    """
    if not hasattr(doc, "custom_name"):
        return

    custom_name = getattr(doc, "custom_name", None)
    if not custom_name:
        return

    filters = {
        "custom_name": custom_name,
        "docstatus": ["<", 2],
    }
    doc_name = getattr(doc, "name", None)
    if doc_name:
        filters["name"] = ["!=", doc_name]

    existing = frappe.db.get_value(doc.doctype, filters=filters, fieldname="name")
    if existing:
        frappe.throw(
            f"Document number {getattr(doc, 'custom_document_no', '')} already exists "
            f"({existing} → {custom_name}). Please enter a different number.",
            title="Duplicate Document Number",
        )


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


# ---------------------------------------------------------------------------
# Numbering Configuration engine
#
# A fully data-driven document numbering system. Each "Numbering Configuration"
# rule is scoped by document_type (+ optional company/branch) and an optional
# list of conditions (field == value, all must match). The most specific matching
# rule wins and builds a number by joining an ordered list of SEGMENTS with a
# configurable separator. Each segment is one of:
#   Static Text | Document Field | Fetch from Link | Company Abbr | Fiscal Year | Number
# Empty segments are skipped. The number is written to the rule's Target Field.
# ---------------------------------------------------------------------------

def _numbering_rules_for(doctype):
    """All enabled Numbering Configuration rules for a doctype, with conditions + segments."""
    rules = frappe.get_all(
        "Numbering Configuration",
        filters={"document_type": doctype, "enabled": 1},
        fields=[
            "name", "company", "branch", "target_field", "separator",
            "date_field", "legacy_upto", "legacy_source_field",
        ],
    )
    for r in rules:
        r["conditions"] = frappe.get_all(
            "Numbering Condition",
            filters={"parent": r["name"], "parenttype": "Numbering Configuration"},
            fields=["field", "value"],
            order_by="idx",
        )
        r["segments"] = frappe.get_all(
            "Numbering Segment",
            filters={"parent": r["name"], "parenttype": "Numbering Configuration"},
            fields=["segment_type", "static_value", "return_value", "field", "fetch_field", "number_length"],
            order_by="idx",
        )
    return rules


def _rule_date(doc, rule):
    """The document date the rule's legacy cut-over is compared against."""
    if rule.get("date_field"):
        return doc.get(rule["date_field"])
    return _doc_date(doc)


def _rule_matches(doc, rule):
    """True if the document satisfies the rule's company/branch scope
    and ALL conditions."""
    if rule.get("company") and rule["company"] != getattr(doc, "company", None):
        return False
    if rule.get("branch") and rule["branch"] != getattr(doc, "custom_branch", None):
        return False

    for cond in rule.get("conditions", []):
        if frappe.utils.cstr(doc.get(cond["field"])) != frappe.utils.cstr(cond["value"]):
            return False
    return True


def _rule_specificity(rule):
    """Higher = more specific: 1 for company, 1 for branch, 1 per condition."""
    return (
        (1 if rule.get("company") else 0)
        + (1 if rule.get("branch") else 0)
        + len(rule.get("conditions", []))
    )


def _matching_numbering_rules(doc):
    """All enabled rules matching the document, most specific first
    (deterministic tie-break by name)."""
    matches = [r for r in _numbering_rules_for(doc.doctype) if _rule_matches(doc, r)]
    matches.sort(key=lambda r: (_rule_specificity(r), r["name"]), reverse=True)
    return matches


def _match_numbering_rule(doc):
    """Return the most specific enabled rule matching the document, or None."""
    matches = _matching_numbering_rules(doc)
    return matches[0] if matches else None


def _doc_date(doc):
    return (
        (getattr(doc, "posting_date", None) if hasattr(doc, "posting_date") else None)
        or (getattr(doc, "transaction_date", None) if hasattr(doc, "transaction_date") else None)
    )


def _link_target_doctype(doc, fieldname):
    try:
        df = doc.meta.get_field(fieldname)
        return df.options if df else None
    except Exception:
        return None


def _resolve_segment(doc, seg, sep):
    """Resolve one non-Number segment to a string ('' if empty/not applicable)."""
    stype = seg.get("segment_type")

    if stype == "Static Text":
        return (seg.get("static_value") or "").strip()

    if stype == "Normal / Return Code":
        # one segment, two codes: the return code applies when is_return == 1
        if getattr(doc, "is_return", 0) and (seg.get("return_value") or "").strip():
            return (seg.get("return_value") or "").strip()
        return (seg.get("static_value") or "").strip()

    if stype == "Company Abbr":
        return get_company_abbr(doc) or ""

    if stype == "Branch Abbr":
        branch = getattr(doc, "custom_branch", None)
        if not branch:
            return ""
        return frappe.utils.cstr(
            frappe.db.get_value("Branch", branch, "custom_abbr") or ""
        )

    if stype == "Fiscal Year":
        fy = get_fiscal_year_from_date(_doc_date(doc)) or ""
        # avoid separator collision when the separator is '/'
        return fy.replace("/", "-") if sep == "/" else fy

    if stype == "Document Field":
        return frappe.utils.cstr(doc.get(seg.get("field")))

    if stype == "Fetch from Link":
        link_field = seg.get("field")
        link_value = doc.get(link_field) if link_field else None
        if not link_value:
            return ""
        link_dt = _link_target_doctype(doc, link_field)
        if not link_dt or not seg.get("fetch_field"):
            return ""
        return frappe.utils.cstr(
            frappe.db.get_value(link_dt, link_value, seg.get("fetch_field")) or ""
        )

    return ""


def _peek_series(key, digits):
    """Next number for a series WITHOUT incrementing the counter (for previews)."""
    row = frappe.db.sql("select current from `tabSeries` where name=%s", key)
    current = row[0][0] if row and row[0][0] is not None else 0
    return ("%0" + str(int(digits)) + "d") % (current + 1)


def _resolve_segments(doc, rule, sep):
    """Return an ordered list of resolved parts:
       [{"num": True, "len": n} | {"num": False, "value": str}] and whether a Number exists.
    """
    resolved = []
    has_number = False
    for seg in rule.get("segments", []):
        if seg.get("segment_type") == "Number":
            resolved.append({"num": True, "len": int(seg.get("number_length") or 6)})
            has_number = True
        else:
            resolved.append({"num": False, "value": _resolve_segment(doc, seg, sep)})
    return resolved, has_number


def _build_from_segments(doc, rule, commit_series=True):
    """Build the number by joining resolved segments (in order) with the separator.

    - Non-empty non-Number segments identify the series (the counter key).
    - The Number segment is replaced by the running counter (getseries), or by the
      next value without incrementing when commit_series is False (preview/test).
    - The Number may sit anywhere in the order (supports e.g. code-number-year).
    - A rule with NO Number segment is a PASS-THROUGH rule: it just joins the
      resolved segment values (e.g. a single "Document Field: narration" segment
      copies the legacy invoice number as-is; no counter is consumed). Returns
      None when the source values are empty, so a less specific rule can apply.
    Returns None if nothing to show.
    """
    # ONE-RULE cut-over: up to Legacy Upto the number is COPIED from the
    # rule's Legacy Source Field (the old ERP number) instead of generated.
    # Empty source -> None, so the engine can fall through to another rule.
    if rule.get("legacy_upto"):
        doc_date = _rule_date(doc, rule)
        if doc_date and frappe.utils.getdate(doc_date) <= frappe.utils.getdate(rule["legacy_upto"]):
            source = rule.get("legacy_source_field")
            return (frappe.utils.cstr(doc.get(source)).strip() or None) if source else None

    sep = rule.get("separator") or "/"
    resolved, has_number = _resolve_segments(doc, rule, sep)
    if not has_number:
        # pass-through: copy the resolved values directly, no counter involved
        values = [r["value"] for r in resolved if r.get("value")]
        return sep.join(values) if values else None

    key_parts = [r["value"] for r in resolved if not r["num"] and r.get("value")]
    series_key = sep.join(key_parts) + sep
    number_len = next((r["len"] for r in resolved if r["num"]), 6)

    seq = getseries(series_key, number_len) if commit_series else _peek_series(series_key, number_len)

    display = []
    for r in resolved:
        if r["num"]:
            display.append(seq)
        elif r.get("value"):
            display.append(r["value"])
    return sep.join(display) if display else None


def _rule_dict_from_config(cfg):
    """Build the engine rule dict from a Numbering Configuration document (saved or not)."""
    return {
        "name": cfg.name,
        "company": cfg.company,
        "branch": cfg.branch,
        "target_field": cfg.target_field,
        "separator": cfg.separator,
        "date_field": cfg.get("date_field"),
        "legacy_upto": cfg.get("legacy_upto"),
        "legacy_source_field": cfg.get("legacy_source_field"),
        "conditions": [{"field": c.field, "value": c.value} for c in (cfg.conditions or [])],
        "segments": [
            {
                "segment_type": s.segment_type,
                "static_value": s.static_value,
                "return_value": s.get("return_value"),
                "field": s.field,
                "fetch_field": s.fetch_field,
                "number_length": s.number_length,
            }
            for s in (cfg.segments or [])
        ],
    }


def _number_belongs_to_other_doc(doc, target):
    """True if the target field holds a number already used by another document."""
    value = doc.get(target)
    if not value or value == doc.name:
        return False

    filters = {target: value, "docstatus": ["<", 2]}
    if doc.name:
        filters["name"] = ["!=", doc.name]
    return bool(frappe.db.get_value(doc.doctype, filters, "name"))


def _validate_unique_number(doc, target):
    """No two documents of a doctype may share a generated number.

    Cancelled documents (docstatus = 2) are ignored so an amendment can reuse
    a freed number, mirroring validate_custom_name_unique above.
    """
    value = doc.get(target)
    if not value or value == doc.name:
        return

    filters = {target: value, "docstatus": ["<", 2]}
    if doc.name:
        filters["name"] = ["!=", doc.name]

    existing = frappe.db.get_value(doc.doctype, filters, "name")
    if existing:
        frappe.throw(
            f"Number {value} is already used by {existing}. "
            f"Leave the field empty to get the next number automatically.",
            title="Duplicate Document Number",
        )


def set_custom_branch_name(doc):
    """
    Sets custom_branch_name field based on branch-wise naming.
    Only generated once (skipped if already set).

    Precedence:
      1. Numbering Configuration rules (generic engine), tried most-specific
         first. A rule may be a normal counter rule (has a Number segment) or a
         pass-through rule (no Number segment, e.g. a single "Document Field:
         narration" segment for migrated legacy invoices). If the best rule
         produces an empty value (e.g. narration is blank), the next matching
         rule gets a chance.
      2. Otherwise custom_branch_name = doc.name (usual numbering, unchanged).

    The old hardcoded BRANCH_CODE_CONFIG (Grishma) path was migrated to seeded
    Numbering Configuration rules (avinashgroup_app/scripts/seed_numbering_rules.py)
    which produce identical formats and series keys.
    """
    # 1) Rule-driven numbering (Numbering Configuration) — generic engine.
    for rule in _matching_numbering_rules(doc):
        target = rule.get("target_field") or "custom_branch_name"
        if not doc.meta.has_field(target):
            continue

        # A NEW document arriving with another document's number means the
        # value was carried over by a copy path that bypassed no_copy
        # (server copy_doc, API, import). Clear it so a fresh number is
        # generated — new data must never keep an old number.
        if doc.is_new() and _number_belongs_to_other_doc(doc, target):
            doc.set(target, None)

        if doc.get(target):
            # already numbered (generate once) — keep guarding collisions.
            _validate_unique_number(doc, target)
            return

        number = _build_from_segments(doc, rule)
        if number:
            doc.set(target, number)
            _validate_unique_number(doc, target)
            return
        # rule matched but produced nothing (e.g. empty source field) ->
        # fall through to the next matching rule.

    # 2) No rule produced a value -> mirror the document's usual name.
    if not hasattr(doc, 'custom_branch_name'):
        return

    if doc.custom_branch_name:
        return

    doc.custom_branch_name = doc.name or ""


def _revert_series_if_last(key, deleted_number):
    """
    Same logic as frappe.model.naming.revert_series_if_last: decrement the
    tabSeries counter by one only when the deleted document held the current
    (highest) number. Called with the exact series key instead of the core
    helper because our keys are built dynamically (company abbr + fiscal
    year) and may contain dots (e.g. GEPL-C.GR-), which the core helper's
    pattern parsing would mangle.
    """
    current = frappe.db.sql(
        "select current from `tabSeries` where name=%s for update", key
    )
    if current and current[0][0] == deleted_number:
        frappe.db.sql(
            "UPDATE `tabSeries` SET `current` = `current` - 1 WHERE `name`=%s", key
        )


def _revert_engine_series(doc, rule):
    """Revert a Numbering Configuration engine series if this doc held its last number."""
    target = rule.get("target_field") or "custom_branch_name"
    number_str = doc.get(target) if doc.meta.has_field(target) else None
    if not number_str or number_str == doc.name:
        return

    # legacy window: the number was COPIED from a document field, no counter
    # was consumed — never step a series back for it.
    if rule.get("legacy_upto"):
        doc_date = _rule_date(doc, rule)
        if doc_date and frappe.utils.getdate(doc_date) <= frappe.utils.getdate(rule["legacy_upto"]):
            return

    sep = rule.get("separator") or "/"
    resolved, has_number = _resolve_segments(doc, rule, sep)
    if not has_number:
        return

    key_parts = [r["value"] for r in resolved if not r["num"] and r.get("value")]
    series_key = sep.join(key_parts) + sep

    # locate the Number's index among the non-empty display parts
    num_index, display_count = None, 0
    for r in resolved:
        if r["num"]:
            num_index = display_count
            display_count += 1
        elif r.get("value"):
            display_count += 1

    parts = str(number_str).split(sep)
    if num_index is None or len(parts) != display_count:
        return
    if parts[num_index].isdigit():
        _revert_series_if_last(series_key, int(parts[num_index]))


def revert_series_on_delete(doc, method=None):
    """
    Called on after_delete. Mirrors what frappe.model.delete_doc does for
    standard naming_series doctypes: if the deleted document was the last
    one issued in its series, the counter steps back so the number is reused.
    Mid-series gaps are left alone, exactly like core.
    """
    doctype = doc.doctype

    # 1) Numbering Configuration engine series — recompute the series key from the
    #    rule's segments and revert if this document held the last number. The
    #    Number segment may sit anywhere in the order, so it is located by position.
    rule = _match_numbering_rule(doc)
    if rule:
        _revert_engine_series(doc, rule)

    if doctype not in NAMING_CONFIG:
        return

    # 2) Main document name: series key is everything before the trailing digit
    #    run, e.g. GEPL-SB-82/83-00015 -> key "GEPL-SB-82/83-", number 15.
    #    Amended names (…-00015-1) derive a key with no Series row -> skipped.
    m = re.match(r"^(.+?)(\d+)$", str(doc.name or ""))
    if m:
        _revert_series_if_last(m.group(1), int(m.group(2)))

    # 3) Legacy hardcoded BRANCH_CODE_CONFIG branch series (dash format), only
    #    when no engine rule handled this document.
    if not rule and NAMING_CONFIG[doctype].get("has_branch_name", False):
        branch_name = getattr(doc, "custom_branch_name", None)
        if branch_name and branch_name != doc.name:
            m = re.match(r"^(.+)-(\d{6,})-(.+)$", str(branch_name))
            if m:
                _revert_series_if_last(
                    f"{m.group(1)}-{m.group(3)}-", int(m.group(2))
                )


def handle_before_insert(doc, method=None):
    naming_requirements_before_insert(doc)


def handle_validate(doc, method=None):
    if doc.is_new():
        set_auto_document_no(doc)
    set_custom_name_field(doc)
    validate_document_no(doc)
    validate_custom_name_unique(doc)
    set_custom_branch_name(doc)


def handle_before_save(doc, method=None):
    """
    Ensure numbering happens after fields like custom_p_type_code
    are set (often during save). This is the final chance before insert.
    """
    if doc.is_new():
        set_auto_document_no(doc)
    set_custom_name_field(doc)
    validate_document_no(doc)
    validate_custom_name_unique(doc)
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
