import fnmatch
import hashlib
import json
import re

import frappe
from frappe import _
from frappe.model.naming import make_autoname
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
    """Get the fiscal year name for a date. Results cached per-request."""
    if not date_field:
        return None

    # Per-request cache: avoid re-fetching the same fiscal year multiple times
    if not hasattr(frappe.local, "_fiscal_year_cache"):
        frappe.local._fiscal_year_cache = {}

    date_key = frappe.utils.cstr(date_field)
    if date_key in frappe.local._fiscal_year_cache:
        return frappe.local._fiscal_year_cache[date_key]

    fiscal_year = frappe.db.get_value(
        "Fiscal Year",
        {
            "year_start_date": ["<=", date_field],
            "year_end_date": [">=", date_field]
        },
        "name"
    )

    frappe.local._fiscal_year_cache[date_key] = fiscal_year
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
    elif hasattr(doc, "attendance_date") and doc.attendance_date:
        date_field = doc.attendance_date
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


# ---------------------------------------------------------------------------
# Document No. (custom_document_no)
#
# custom_document_no is the running sequence number that ultimately drives the
# voucher name for BOTH numbering paths:
#   * the legacy custom_name path (e.g. Journal Entry), and
#   * the Numbering Configuration engine (e.g. Payment Entry, whose rules feed
#     custom_document_no into a "Document Field" segment).
# Neither path owns a counter of its own, so this is the single place a number
# is generated. It is a per-scope running number: max(existing) + 1, scoped by
# company abbr + p-type code + fiscal year.
#
# The number has two deliberately separated lifecycle stages:
#   * PREVIEW (before save) — peek_next_document_no(): a non-reserving guess
#     shown live on the form. Consumes/locks nothing.
#   * ASSIGN (at save) — apply_document_no(): the authoritative number, drawn
#     atomically under a per-scope row lock so two users saving the same scope
#     concurrently can never receive the same number.
#
# Manual override: custom_document_no_manual = 1 means the user typed the number
# themselves; it is kept verbatim and only checked for uniqueness. When 0 (or
# the flag field is not deployed yet) the number is auto-managed.
# ---------------------------------------------------------------------------


def _resolve_p_type_code(doc):
    """Prefix code for the selected type. Prefer the value already on the doc;
    otherwise resolve it from the linked type record via the field's fetch_from
    definition, so eligibility never depends on client/server fetch ordering."""
    code = doc.get("custom_p_type_code")
    if code:
        return code
    if not doc.meta.has_field("custom_p_type_code"):
        return None
    df = doc.meta.get_field("custom_p_type_code")
    fetch_from = getattr(df, "fetch_from", None) if df else None
    if not fetch_from or "." not in fetch_from:
        return None
    link_field, source_field = fetch_from.split(".", 1)
    link_value = doc.get(link_field)
    link_dt = _link_target_doctype(doc, link_field)
    if not link_value or not link_dt:
        return None
    return frappe.get_cached_value(link_dt, link_value, source_field) or None


def _resolve_docno_fiscal_year(doc, rule=None):
    if doc.get("custom_fiscal_year"):
        return doc.get("custom_fiscal_year")
    date_field = (
        (doc.get(rule["date_field"]) if rule and rule.get("date_field") else None)
        or doc.get("posting_date")
        or doc.get("transaction_date")
        or doc.get("custom_created_on")
    )
    return get_fiscal_year_from_date(date_field) if date_field else None


def _rule_docno_scope(doc, rule):
    """Derive the Document No. series scope from a matching Numbering
    Configuration rule, so the number counts exactly the way the rule groups
    vouchers — per branch when the rule has a Branch Abbr segment, per company,
    per condition, and so on.

      * key     — the rule's resolved prefix WITHOUT the number position; this
                  is the counter's identity (two vouchers with the same prefix
                  share a series). A Branch Abbr segment puts the branch in the
                  key → each branch counts on its own.
      * pattern — the same prefix but with the number position as a wildcard,
                  matched against the rule's target field to find the current
                  max (continues an existing series and stays above any
                  manually-typed number), per branch too.

    The number position is a Number segment OR the Document Field referencing the
    rule's configured document_no_field — so a rule that stores the number in a
    non-default field is still recognised (and isn't mistaken for a scope part).

    Returns None when the rule has no number position (a pass-through rule),
    so the caller falls back to the legacy company+code+year scope."""
    number_field = _docno_field(rule)
    sep = rule.get("separator") or "/"
    parts = []  # (value_or_wildcard, glue, is_number)
    number_seen = False
    for seg in rule.get("segments", []):
        glue = bool(seg.get("join_previous"))
        stype = seg.get("segment_type")
        fld = seg.get("field")
        # Name Number varies per document (it mirrors the doc name's number)
        # — it is a number position, never a scope part
        is_number = stype in ("Number", "Name Number") or (
            stype == "Document Field" and fld == number_field
        )
        # custom_document_word is the glued letter tail of the number (e.g. 7A) —
        # covered by the number's wildcard — UNLESS it IS the number field itself.
        is_word_tail = (
            stype == "Document Field"
            and fld == "custom_document_word"
            and number_field != "custom_document_word"
        )
        if is_number:
            if not number_seen:
                parts.append(("%", glue, True))
                number_seen = True
            continue
        if is_word_tail:
            continue
        value = _pad_segment_value(seg, _resolve_segment(doc, seg, sep, rule))
        parts.append((value, glue, False))

    if not number_seen:
        return None

    target = _safe_col(rule.get("target_field")) or "custom_branch_name"
    # The pattern is matched against the rule's target field to find the current
    # max. If that field doesn't exist on this doctype (or isn't backed by a
    # real DB column, e.g. a Table field) the rule is inapplicable — fall back
    # to the legacy scope instead of erroring every save.
    target_df = doc.meta.get_field(target)
    if not target_df or target_df.fieldtype in frappe.model.no_value_fields + frappe.model.table_fields:
        return None

    pattern = _join_parts([(v, g) for (v, g, _n) in parts], sep)
    key = _join_parts([(v, g) for (v, g, n) in parts if not n], sep) or ""
    # Isolate counters per number field when it's non-default, so two rules that
    # share a prefix but write DIFFERENT fields never share one counter. The
    # default field appends nothing, preserving existing series continuity.
    if number_field != "custom_document_no":
        key = (key + "|" + number_field) if key else number_field
    return {"key": key, "pattern": pattern, "field": target, "number_field": number_field}


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _safe_col(name):
    """Validate a rule-configured fieldname before it is formatted into SQL as
    an identifier. Only plain identifiers pass; anything else (a stray %, which
    would break pymysql parameter binding, quotes, spaces...) returns None so
    callers can fail soft instead of erroring every save."""
    name = (name or "").strip()
    return name if _IDENTIFIER_RE.match(name) else None


def _docno_field(rule):
    """The field the auto Document No. is written into. Configurable per rule
    (document_no_field); defaults to custom_document_no so the shipped doctypes
    are unchanged. A malformed configured name falls back to the default (and
    the doc.meta.has_field gate downstream keeps a wrong name from breaking
    saves)."""
    return _safe_col(rule.get("document_no_field") if rule else None) or "custom_document_no"


def _docno_mode(doc, rule):
    """Auto/Manual mode of the rule for THIS document: return_docno_mode when
    the doc is a return (is_return checked), normal_docno_mode otherwise.
    Blank/missing (rules saved before the fields shipped) = Auto, preserving
    the old 'auto_document_no numbers everything' behaviour."""
    is_return = doc.meta.has_field("is_return") and frappe.utils.cint(doc.get("is_return"))
    mode = rule.get("return_docno_mode") if is_return else rule.get("normal_docno_mode")
    return mode or "Auto"


def _docno_eligible(doc, rule):
    """Whether this document should get an auto document number.

      1. Rule-driven (the generalized path): the matching Numbering Configuration
         rule has 'Auto-fill Document No.' ticked, the Normal/Return mode for
         this document is Auto (Normal Documents / Return Documents selects on
         the rule — e.g. normal = Manual, return = Auto in one rule), AND the
         document satisfies the rule's separate DOCUMENT NO. CONDITIONS
         (Equals / In / Is Set …). Conditions are independent of the Voucher No.
         conditions that select the rule, so you can format the name for a broad
         set but only number a subset. Empty conditions = number everything the
         mode allows.
      2. Fallback: the hardcoded AUTO_NUMBER_CONFIG (type field in a fixed list),
         so day-one behaviour is unchanged for the doctypes shipped with it.
    """
    # A matching Auto-fill rule is AUTHORITATIVE for the Document No.: the doc is
    # numbered iff its Normal/Return mode is Auto AND ALL Document No. conditions
    # match. This lets one rule turn numbering ON for new types and RESTRICT it
    # (e.g. returns auto, normal manual) — the fallback below is NOT consulted
    # once such a rule applies.
    if rule and rule.get("auto_document_no"):
        if _docno_mode(doc, rule) != "Auto":
            return False
        return all(_condition_matches(doc, c) for c in rule.get("document_no_conditions", []))

    # No Auto-fill rule applies -> hardcoded fallback (day-one behaviour): the
    # type field is in the shipped list.
    cfg = AUTO_NUMBER_CONFIG.get(doc.doctype)
    if not cfg:
        return False
    type_field = cfg.get("type_field")
    type_value = doc.get(type_field) if type_field else None
    return bool(type_value and type_value in cfg.get("types", []))


def _group_by_scope(doc, rule):
    """Scope from the rule's explicit GROUP BY fields ("Group Document No. By"):
    each unique combination of the configured field values counts on its own
    sequence. Returns None when the rule has no group-by rows.

    Unlike the prefix/pattern scopes, this one scans by FILTERS on the real
    columns (`where` + `params`), so history is visible even when the stored
    voucher format changes — an existing series continues instead of restarting.

    Special case: custom_fiscal_year groups by the FISCAL YEAR of the document's
    posting/transaction date (resolved, not the raw column — the stored column
    may be empty on old rows), matched as a date-range filter."""
    group_fields = [r.get("field") for r in (rule.get("docno_group_by") or []) if r.get("field")]
    if not group_fields:
        return None

    where, params, key_parts = [], [], []
    for name in group_fields:
        col = _safe_col(name)
        if not col:
            continue
        if col in ("custom_fiscal_year", "fiscal_year"):
            fy = _resolve_docno_fiscal_year(doc, rule)
            if not fy:
                return None  # scope incomplete until a date is set
            rule_date_col = _safe_col(rule.get("date_field"))
            if rule_date_col and doc.meta.has_field(rule_date_col):
                date_col = rule_date_col
            else:
                date_col = "posting_date" if doc.meta.has_field("posting_date") else (
                    "transaction_date" if doc.meta.has_field("transaction_date") else None)
            bounds = frappe.get_cached_value("Fiscal Year", fy,
                                             ["year_start_date", "year_end_date"])
            if not (date_col and bounds):
                return None
            where.append("`{0}` BETWEEN %s AND %s".format(date_col))
            params.extend([bounds[0], bounds[1]])
            key_parts.append("fy=" + fy)
            continue
        df = doc.meta.get_field(col)
        if not df or df.fieldtype in frappe.model.no_value_fields + frappe.model.table_fields:
            continue
        value = frappe.utils.cstr(doc.get(col))
        # IFNULL: a blank value is its own group and must match stored NULLs too
        where.append("IFNULL(`{0}`, '') = %s".format(col))
        params.append(value)
        key_parts.append("{0}={1}".format(col, value))

    if not key_parts:
        return None
    # The tabSeries name column is short (140 incl. the "docno:<doctype>|"
    # prefix) and full company/branch names easily overflow it — store a
    # stable hash as the key; `group` keeps the readable form for debugging.
    readable = "|".join(key_parts)
    key = "gb|" + hashlib.sha1(readable.encode("utf-8")).hexdigest()[:24]
    return {
        "key": key,
        "group": readable,
        "where": " AND ".join(where),
        "params": params,
        "number_field": _docno_field(rule),
    }


def _docno_scope(doc):
    """Series scope for the auto document number, or None when the doc is not
    eligible. Returns a dict — either {key, pattern, field} (prefix-matched) or
    {key, where, params} (column-filtered):

      * When the matching rule has GROUP BY fields, the scope is those field
        values (see _group_by_scope) — fully admin-configurable grouping.
      * Else, when a rule matches, the scope is DERIVED FROM THE RULE's number
        prefix (branch / conditions aware) — see _rule_docno_scope.
      * Otherwise it falls back to the legacy company + code + fiscal-year scope,
        matched on custom_name (unchanged historical behaviour).

    Also back-fills custom_p_type_code on the doc when it was empty but
    resolvable, so the custom_name built later is correct even if the framework
    has not run its own fetch yet."""
    rule = _match_numbering_rule(doc)
    if not _docno_eligible(doc, rule):
        return None

    number_field = _docno_field(rule)  # which field holds the counter
    code = _resolve_p_type_code(doc)
    company_abbr = get_company_abbr(doc)
    fiscal_year = _resolve_docno_fiscal_year(doc, rule)

    if doc.meta.has_field("custom_p_type_code") and code and not doc.get("custom_p_type_code"):
        doc.custom_p_type_code = code

    if rule:
        # 1) Explicit "Group Document No. By" fields — the admin's grouping.
        group_scope = _group_by_scope(doc, rule)
        if group_scope:
            return group_scope
        # 2) Rule-derived scope (branch / condition aware) when the matching
        #    rule defines a number position.
        rule_scope = _rule_docno_scope(doc, rule)
        if rule_scope and rule_scope.get("pattern"):
            rule_scope["number_field"] = number_field
            return rule_scope

    # Legacy fallback scope needs the company + code + fiscal-year triple.
    if not (code and company_abbr and fiscal_year):
        return None
    key = "|".join((company_abbr, code, fiscal_year))
    if number_field != "custom_document_no":
        key += "|" + number_field
    return {
        "key": key,
        "pattern": f"{company_abbr}-{code}-%-{fiscal_year}%",
        "field": "custom_name",
        "number_field": number_field,
    }


def _scope_where(doc, scope):
    """(where_sql, params) that selects this scope's documents — either the
    prefix pattern (LIKE on the scope's target field) or a group-by filter
    (`where` + `params` built by _group_by_scope). None when unusable."""
    if scope.get("where"):
        return scope["where"], list(scope.get("params") or [])
    field = _safe_col(scope.get("field"))
    if not field:
        return None
    return "`{0}` LIKE %s".format(field), [scope["pattern"]]


def _current_max_document_no(doc, scope):
    """Highest custom_document_no already used in this scope (0 if none).
    Scoped by the scope's own selector (prefix pattern or group-by filters),
    so per-branch/per-group scopes only ever see their own documents.

    CAST(... AS UNSIGNED) makes the max NUMERIC even where custom_document_no is
    a Data column (Purchase Receipt) rather than Int — a plain MAX() on a varchar
    compares lexicographically ("9" > "50"), which would compute a wrong floor
    and let auto numbers eventually collide with a higher manual number."""
    table = "tab" + doc.doctype.replace("`", "")
    number_field = _safe_col(scope.get("number_field", "custom_document_no"))
    selector = _scope_where(doc, scope)
    if not (selector and number_field):
        return 0
    where, params = selector
    row = frappe.db.sql(
        "SELECT MAX(CAST(`{nf}` AS UNSIGNED)) "
        "FROM `{table}` WHERE {where}".format(nf=number_field, table=table, where=where),
        params,
    )
    return int(row[0][0]) if row and row[0][0] is not None else 0


def _docno_series_key(doc, scope):
    return "docno:" + doc.doctype + "|" + scope["key"]


def _series_current(key):
    """Current counter for a series key, 0 if the row does not exist. Plain
    read — no lock — so it is safe to call from the preview path."""
    row = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE name = %s", key)
    return frappe.utils.cint(row[0][0]) if row and row[0][0] is not None else 0


# --- O(1) fast path: skip the MAX() data scan while the counter is verified --
#
# The tabSeries counter is authoritative: every in-app write keeps it at or
# above the highest stored number (draws increment it, manual entries bump it
# via _keep_counter_above_manual, delete-revert only returns the newest draw).
# The MAX(CAST(...)) scan on every draw/preview exists solely to catch data
# written OUTSIDE the app (raw-SQL imports, restored backups) — but it is O(n)
# over the scope and dominates save time past ~1M rows. So: after a scan
# OBSERVES the committed invariant (data max <= counter), remember that for an
# hour in Redis and skip the scan. The marker is deliberately NOT set when the
# invariant only becomes true through this transaction's own reseed — a later
# rollback would revert the counter but not the Redis marker.

FLOOR_VERIFY_TTL = 3600


def _floor_key(series_key):
    return "docno_floor_verified:" + series_key


def _floor_verified(series_key):
    try:
        return bool(frappe.cache().get_value(_floor_key(series_key)))
    except Exception:
        return False


def _mark_floor_verified(series_key):
    try:
        frappe.cache().set_value(_floor_key(series_key), 1, expires_in_sec=FLOOR_VERIFY_TTL)
    except Exception:
        pass


def _clear_floor_verified(series_key):
    """Drop a series' verification, forcing the next draw to rescan — called
    when a freshly drawn number turns out to be taken (external write within
    the marker's TTL)."""
    try:
        frappe.cache().delete_value(_floor_key(series_key))
    except Exception:
        pass


def _series_row_exists(key):
    """True when the tabSeries row itself exists — _series_current can't tell
    "no row" from "current = 0", and the scan skip is only safe with a row."""
    return bool(frappe.db.sql("SELECT 1 FROM `tabSeries` WHERE name = %s", key))


def peek_next_document_no(doc):
    """Non-reserving preview of the number this doc would get right now.
    No lock, no side effects — safe for the live form preview. Mirrors the
    authoritative GREATEST(counter+1, data_max+1) so the preview matches what
    save assigns. Returns None when the type is not auto-numbered or the scope
    fields are incomplete."""
    scope = _docno_scope(doc)
    if not scope:
        return None
    key = _docno_series_key(doc, scope)
    if _series_row_exists(key) and _floor_verified(key):
        return _series_current(key) + 1
    data_max = _current_max_document_no(doc, scope)
    current = _series_current(key)
    if data_max <= current:
        _mark_floor_verified(key)
    return max(data_max, current) + 1


def _next_number_hint(doc):
    """A ' Next available number is N.' fragment for duplicate-number errors,
    or '' when a next number can't be determined. Best-effort — never raises."""
    try:
        nxt = peek_next_document_no(doc)
    except Exception:
        nxt = None
    return f" Next available number is {nxt}." if nxt else ""


def _keep_counter_above_manual(doc, field, scope=None):
    """A manually-entered number is not drawn from the counter, so bump the
    counter up to it. Future auto draws in the same scope then skip past manual
    numbers even across concurrent transactions — the draw's upsert reads the
    latest committed `current` under a row lock, so once a manual number has
    raised the counter no auto draw can reissue it. Best-effort; never blocks
    the save.

    Side effect relied on by apply_document_no: the upsert's row lock (held to
    commit) SERIALIZES concurrent saves of the same scope — the duplicate
    locking-read that follows it is only race-free behind this lock."""
    n = frappe.utils.cint(doc.get(field))
    if n <= 0:
        return
    scope = scope or _docno_scope(doc)
    if not scope:
        return
    try:
        frappe.db.sql(
            "INSERT INTO `tabSeries` (`name`, `current`) VALUES (%(k)s, %(n)s) "
            "ON DUPLICATE KEY UPDATE `current` = GREATEST(`current`, %(n)s)",
            {"k": _docno_series_key(doc, scope), "n": n},
        )
    except Exception:
        pass


def _draw_next_document_no(doc, scope):
    """Atomic, deadlock-resistant next number for a scope.

    A single `INSERT ... ON DUPLICATE KEY UPDATE` bumps a per-scope counter in
    `tabSeries`, never dropping below the existing data max (the seed floor, so
    the counter continues an existing series and jumps past any manually-typed
    number). Two saves for the same scope hit the SAME row and serialize on a
    brief row lock — not a transaction-long `SELECT ... FOR UPDATE` — which is
    what avoids the gap-lock deadlock against core `getseries` (the doc-name
    series) that a long-held lock would cause. The counter is authoritative:
    `current + 1` guarantees each concurrent save a distinct number.

    Fast path: while the scope's floor is verified (see _floor_verified) the
    O(n) data scan is skipped — floor=1 makes the GREATEST upsert a pure
    counter increment."""
    key = _docno_series_key(doc, scope)
    if _series_row_exists(key) and _floor_verified(key):
        floor = 1
    else:
        data_max = _current_max_document_no(doc, scope)
        floor = data_max + 1
        if data_max <= _series_current(key):
            _mark_floor_verified(key)
    frappe.db.sql(
        "INSERT INTO `tabSeries` (`name`, `current`) VALUES (%(key)s, %(floor)s) "
        "ON DUPLICATE KEY UPDATE `current` = GREATEST(`current` + 1, %(floor)s)",
        {"key": key, "floor": floor},
    )
    return _series_current(key)


def _is_desk_form_save():
    """True only for a desk FORM save (savedocs) — the one path where the
    number field may hold a stale client preview and our JS manages the
    manual flag. Everywhere else (Data Import, REST API, server code) a
    value in the field is intentional data and must never be discarded."""
    if frappe.flags.in_import:
        return False
    form_dict = getattr(frappe.local, "form_dict", None) or {}
    return form_dict.get("cmd") == "frappe.desk.form.save.savedocs"


def _is_manual_document_no(doc, field="custom_document_no"):
    """True when the number field carries a value that must be preserved
    (only uniqueness-checked), not auto-drawn. The manual flag follows the
    convention <field>_manual (custom_document_no -> custom_document_no_manual)."""
    flag = field + "_manual"
    if doc.meta.has_field(flag) and frappe.utils.cint(doc.get(flag)):
        return True
    if not doc.get(field):
        return False
    if not doc.meta.has_field(flag):
        # No flag field: we cannot tell a user value from a stale preview,
        # so treat any existing value as manual (never overwrite).
        return True
    # A STORED document's flag is authoritative: 0 = auto-drawn (matters for
    # delete-revert: auto numbers return to the counter, manual ones don't).
    if not doc.is_new():
        return False
    # NEW doc, value present, flag unset: in a desk FORM save that's our own
    # preview fill — the auto path overwrites it with the authoritative draw.
    # In an import / REST / script save there is no preview: the value came
    # in the payload on purpose (e.g. legacy numbers in an import file) and
    # silently renumbering it would be data loss.
    return not _is_desk_form_save()


def _document_no_taken(doc, scope, value, for_update=False):
    """Name of another live document in this scope already holding the given
    Document No., or None. Scoped by the same LIKE pattern as
    _current_max_document_no, so per-branch series only see their own branch.
    CAST keeps the comparison numeric on Data-typed number columns.

    for_update=True makes this a LOCKING read: under REPEATABLE READ a plain
    SELECT uses the transaction's snapshot and CANNOT see a row a concurrent
    save committed after this transaction started — a locking read always
    reads latest-committed. Callers must hold the scope's tabSeries row lock
    first (_keep_counter_above_manual / _draw_next_document_no), which
    serializes same-scope savers so the peer's row is committed by the time
    this runs."""
    n = frappe.utils.cint(value)
    if n <= 0:
        return None
    table = "tab" + doc.doctype.replace("`", "")
    number_field = _safe_col(scope.get("number_field", "custom_document_no"))
    selector = _scope_where(doc, scope)
    if not (selector and number_field):
        return None
    where, params = selector
    row = frappe.db.sql(
        ("SELECT `name` FROM `{table}` WHERE {where} "
         "AND CAST(`{nf}` AS UNSIGNED) = %s AND `docstatus` < 2 AND `name` != %s "
         "LIMIT 1" + (" FOR UPDATE" if for_update else "")).format(
            table=table, where=where, nf=number_field),
        params + [n, doc.name or ""],
    )
    return row[0][0] if row else None


def _locked_group_fields(rule):
    """Fieldnames in the rule's "Group Document No. By" table marked
    Lock After Numbering. The rule-level "Lock All Group Fields After
    Numbering" check locks every row without ticking them one by one."""
    lock_all = frappe.utils.cint((rule or {}).get("lock_group_fields"))
    return [
        r.get("field") for r in ((rule or {}).get("docno_group_by") or [])
        if r.get("field")
        and (lock_all or frappe.utils.cint(r.get("lock_after_numbering")))
    ]


def _enforce_locked_group_fields(doc):
    """Group-by fields marked "Lock After Numbering" must not change once the
    document carries a Document No. — the change would strand the number in
    another group's sequence. Unlocked fields keep the default behavior (the
    draft renumbers into its new group, _redraw_docno_if_scope_changed).
    Applies to auto AND manual numbers, and to amendments — their number is
    PINNED to the cancelled original, so their locked fields must match the
    original's values."""
    if doc.get("docstatus") != 0:
        return
    rule = _match_numbering_rule(doc)
    locked = _locked_group_fields(rule)
    if not locked:
        return
    field = _docno_field(rule)
    if not doc.meta.has_field(field):
        return

    if doc.get("amended_from"):
        try:
            before = frappe.get_doc(doc.doctype, doc.get("amended_from"))
        except Exception:
            return
        # the pin will force the original's number onto this amendment
        number = doc.get(field) or before.get(field)
    elif not doc.is_new():
        before = doc.get_doc_before_save()
        number = doc.get(field)
    else:
        return  # a plain new doc has nothing to compare against
    if not (before and number):
        return

    changed = []
    for name in locked:
        col = _safe_col(name)
        if not col:
            continue
        if col in ("custom_fiscal_year", "fiscal_year"):
            # grouped by the RESOLVED fiscal year of the rule's document date
            # — the lock is on that, not on the raw (often empty) column
            if _resolve_docno_fiscal_year(before, rule) != _resolve_docno_fiscal_year(doc, rule):
                changed.append(_("Fiscal Year"))
            continue
        df = doc.meta.get_field(col)
        if not df or df.fieldtype in frappe.model.no_value_fields + frappe.model.table_fields:
            continue
        if frappe.utils.cstr(before.get(col)) != frappe.utils.cstr(doc.get(col)):
            changed.append(_(df.label) if df.label else col)

    if changed:
        frappe.throw(
            _("{0} cannot be changed after Document No. {1} is assigned — "
              "numbering rule {2} groups Document No. sequences by it "
              "(Group Document No. By → Lock After Numbering).").format(
                ", ".join(frappe.bold(c) for c in changed),
                frappe.bold(number),
                frappe.bold(rule.get("name")),
            ),
            title=_("Field Locked by Numbering"),
        )


def _redraw_docno_if_scope_changed(doc):
    """A saved DRAFT edited onto a different series must not keep a number
    from the old one (e.g. branch an -> kt with per-branch counting: keeping
    an's 5 would corrupt kt's sequence and desync an's). Give the old number
    back to its series (only if it was the last drawn — same rule as delete)
    and draw fresh from the new series. Manual numbers and amendments belong
    to the user and are never touched. Submitted documents are immutable."""
    if doc.get("docstatus") != 0 or doc.get("amended_from"):
        return
    rule = _match_numbering_rule(doc)
    field = _docno_field(rule)
    field_df = doc.meta.get_field(field)
    if not field_df or field_df.fieldtype in frappe.model.no_value_fields + frappe.model.table_fields:
        return
    if not doc.get(field) or _is_manual_document_no(doc, field):
        return
    before = doc.get_doc_before_save()
    if not before:
        return
    new_scope = _docno_scope(doc)
    if not new_scope:
        # the edit made the doc ineligible — leave the number (the field is
        # mandatory on the audited doctypes; the user can overtype it)
        return
    try:
        old_scope = _docno_scope(before)
    except Exception:
        old_scope = None
    if old_scope and old_scope["key"] == new_scope["key"]:
        return  # same series — number stays
    if old_scope:
        _revert_series_if_last(
            _docno_series_key(before, old_scope), frappe.utils.cint(doc.get(field))
        )
    doc.set(field, _draw_next_document_no(doc, new_scope))
    doc.flags._docno_assigned = True


def _duplicate_action(rule):
    """Per-rule policy when a manually-typed number is already used:
    'Throw Error' (default — the save is rejected with a next-number hint) or
    'Use Next Available Number' (the number is bumped and the user alerted)."""
    return (rule.get("duplicate_action") if rule else None) or "Throw Error"


def _pin_amended_docno(doc):
    """An amendment is the SAME voucher re-entered after cancellation, so its
    Document No. is the ORIGINAL's — always. The form shows the field
    read-only; here the number stored on the cancelled original overwrites
    whatever arrived in the payload (stale preview, typed value, API copy),
    on every save of the amended doc, so it can never drift onto a different
    number. The manual flag is copied too, keeping delete-revert semantics.

    Returns True when the number is settled (pinned, or kept when the
    original can't be read), False when there is no number anywhere so the
    normal draw applies (e.g. amending a legacy doc from before numbering)."""
    field = _docno_field(_match_numbering_rule(doc))
    field_df = doc.meta.get_field(field)
    if not field_df or field_df.fieldtype in frappe.model.no_value_fields + frappe.model.table_fields:
        return False
    flag = field + "_manual"
    has_flag = doc.meta.has_field(flag)
    fetch = [field] + ([flag] if has_flag else [])
    row = frappe.db.get_value(doc.doctype, doc.get("amended_from"), fetch, as_dict=True)
    if row and row.get(field):
        doc.set(field, row.get(field))
        if has_flag:
            doc.set(flag, frappe.utils.cint(row.get(flag)))
        doc.flags._docno_assigned = True
        return True
    # Original missing or unnumbered: keep an incoming value as-is (it was
    # copied from the amend source client-side), otherwise fall through so
    # the normal draw can number the doc.
    if doc.get(field):
        doc.flags._docno_assigned = True
        return True
    return False


def apply_document_no(doc):
    """Authoritative, collision-free assignment of custom_document_no at save.

    - Manual numbers are kept as-is (validated for uniqueness downstream).
    - Auto numbers ignore any optimistic client preview and are drawn atomically
      under a per-scope lock, so concurrent users never receive the same number.
    - When the doc is not (yet) eligible the field is left blank, so a later
      hook can fill it once more fields are set, and so ineligible types fall
      back to manual entry.

    Idempotent within a single save via doc.flags._docno_assigned."""
    if doc.flags.get("_docno_assigned"):
        return
    # Locked group-by fields win over every renumber/pin path: a change is
    # rejected outright (covers saved drafts AND amendments vs their original).
    _enforce_locked_group_fields(doc)

    # Amendments never draw or keep their own number — it is pinned to the
    # cancelled original's before manual/auto classification can touch it.
    if doc.get("amended_from") and _pin_amended_docno(doc):
        return
    if not doc.is_new():
        # An existing DRAFT's number must follow its scope: editing branch /
        # company / type / date onto a different series redraws the number
        # (mirror of _renumber_if_scope_changed for the name).
        _redraw_docno_if_scope_changed(doc)
        return

    # Which field holds the number — configurable per rule, default
    # custom_document_no. Any doctype carrying that field can be auto-numbered.
    # The field must be backed by a real DB column (a configured Table/Section
    # field would crash the CAST in every draw query — fail soft instead).
    field = _docno_field(_match_numbering_rule(doc))
    field_df = doc.meta.get_field(field)
    if not field_df or field_df.fieldtype in frappe.model.no_value_fields + frappe.model.table_fields:
        return

    if _is_manual_document_no(doc, field):
        scope = _docno_scope(doc)
        # ORDER MATTERS (concurrency): bump the counter FIRST — its
        # INSERT..ON DUPLICATE KEY UPDATE takes the scope's tabSeries row lock
        # (held to commit), so a concurrent save of the same scope blocks here
        # until this one commits. Only THEN check for a duplicate, with a
        # LOCKING read that sees the peer's committed row (a plain SELECT's
        # REPEATABLE READ snapshot would miss it, letting two users who typed
        # the same free number both save it).
        _keep_counter_above_manual(doc, field, scope)
        if scope:
            taken_by = _document_no_taken(doc, scope, doc.get(field), for_update=True)
            if taken_by:
                # Per-rule duplicate policy. Imports always take the throw
                # path: silently renumbering imported data would be invisible
                # in a background job — a visible row error is safer.
                bump = (
                    _duplicate_action(_match_numbering_rule(doc)) == "Use Next Available Number"
                    and not frappe.flags.in_import
                )
                if bump:
                    old = doc.get(field)
                    doc.set(field, _draw_next_document_no(doc, scope))
                    flag = field + "_manual"
                    if doc.meta.has_field(flag):
                        doc.set(flag, 0)
                    frappe.msgprint(
                        _("Document No. {0} is already used by {1} — assigned the next available number {2} instead.").format(
                            old, taken_by, doc.get(field)
                        ),
                        indicator="orange",
                        alert=True,
                    )
                else:
                    frappe.throw(
                        _("Document No. {0} is already used by {1}.{2} "
                          "Leave the field empty to get the next number automatically.").format(
                            doc.get(field), taken_by, _next_number_hint(doc)
                        ),
                        title=_("Duplicate Document Number"),
                    )
            else:
                # The kept value is manual from here on — persist that in the
                # flag so the STORED doc is classified consistently (imports /
                # API payloads arrive with the flag unset).
                flag = field + "_manual"
                if doc.meta.has_field(flag):
                    doc.set(flag, 1)
        doc.flags._docno_assigned = True
        return

    scope = _docno_scope(doc)
    if not scope:
        # Not eligible yet (missing code / company / fiscal year, or a type that
        # is simply not auto-numbered). In a desk FORM save, clear a stale
        # client preview so the field falls back to manual entry — but NEVER
        # blank a value that arrived by import/REST/script (no client preview
        # there; blanking would be silent data loss). Do NOT set the assigned
        # flag, so a later hook retries once the scope is complete.
        if _is_desk_form_save():
            doc.set(field, None)
        return

    # Data Import must carry the number in the file: an uploaded row is only
    # checked for duplicates, never auto-numbered. Reaching here means the row
    # is eligible for a number but left the field blank — silently drawing one
    # inside a background import job would be invisible and unauditable, so fail
    # the row loudly and make the operator supply the number in the sheet.
    if frappe.flags.in_import:
        frappe.throw(
            _("Document No. is blank for this {0} row. Provide it in the import "
              "file — auto-numbering is disabled during data upload.").format(doc.doctype),
            title=_("Missing Document Number"),
        )

    doc.set(field, _draw_next_document_no(doc, scope))
    flag = field + "_manual"
    if doc.meta.has_field(flag):
        doc.set(flag, 0)
    doc.flags._docno_assigned = True


@frappe.whitelist()
def get_next_custom_document_no(doc=None, **kwargs):
    """Client helper: non-reserving preview of the next document number for a
    draft. Never raises — returns None when the type is not auto-numbered, the
    scope fields are incomplete, or the payload can't be parsed, so the form
    simply leaves the field for manual entry.

    The form sends the whole draft as `doc`; child tables (e.g. Journal Entry
    accounts) arrive as JSON strings/lists and are irrelevant to numbering, so
    only scalar fields are kept before building a lightweight in-memory doc."""
    try:
        d = _client_payload_doc(doc, kwargs)
        return peek_next_document_no(d) if d else None
    except Exception:
        return None


@frappe.whitelist()
def get_document_no_status(doc=None, **kwargs):
    """Client helper for the form. Returns the current Document No. STATUS of a
    draft so the field can reflect the server's decision instead of guessing:

      * auto      — a numbering rule (or fallback) numbers this doc, so the field
                    is shown read-only and the server assigns the number at save.
      * next      — non-reserving preview of that number, or None when the scope
                    fields aren't resolvable yet (shown as "assigned on save").
      * ambiguous — two or more enabled rules tie for most specific on this doc,
                    so which one applies is arbitrary; the form warns the admin.
      * locked_fields — group-by fields marked Lock After Numbering: once the
                    doc carries a number, the form renders them read-only
                    (custom_fiscal_year is excluded — its lock is on the FY of
                    the date, and within-FY date edits stay allowed; the server
                    check rejects cross-FY moves precisely).

    `auto` is decided by eligibility (the type/rule), NOT by whether every scope
    field is filled — so the field locks as soon as the type says auto, even
    before company/date are set. Never raises; returns auto=False when it can't
    tell, so the form falls back to manual (required) entry."""
    blank = {"auto": False, "next": None, "ambiguous": False, "locked_fields": []}
    try:
        d = _client_payload_doc(doc, kwargs)
        if not d:
            return blank
        rule = _match_numbering_rule(d)
        auto = _docno_eligible(d, rule)
        locked = [
            f for f in _locked_group_fields(rule)
            if f not in ("custom_fiscal_year", "fiscal_year") and d.meta.has_field(f)
        ]
        return {
            "auto": bool(auto),
            "next": peek_next_document_no(d) if auto else None,
            "ambiguous": bool(_ambiguous_numbering_rules(d)),
            "locked_fields": locked,
        }
    except Exception:
        return blank


def _client_payload_doc(doc, kwargs):
    """Parse a client-sent draft payload into an in-memory doc, gated by
    DOC-LEVEL read permission — a role-only check would let a user restricted
    (by User Permissions) to one company/branch probe another's series by
    posting a payload for it. Returns None when unparsable or not permitted."""
    data = doc if doc is not None else kwargs
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict) or not data.get("doctype"):
        return None
    scalars = {k: v for k, v in data.items() if not isinstance(v, (list, dict))}
    d = frappe.get_doc(scalars)
    # doc= applies User Permissions against the payload's own field values
    # (company, branch, ...), not just the role's doctype access.
    if not frappe.has_permission(d.doctype, "read", doc=d):
        return None
    return d


@frappe.whitelist()
def check_document_no_availability(doc=None, **kwargs):
    """Client helper: is the manually-typed Document No. free in this draft's
    scope? Returns {"taken": bool, "used_by": name, "next": int} — or None when
    it can't tell (type not auto-numbered, scope incomplete, unparsable payload).
    Never raises: the form only uses it to show a warning hint while typing."""
    try:
        d = _client_payload_doc(doc, kwargs)
        if not d:
            return None
        scope = _docno_scope(d)
        if not scope:
            return None
        # The form types into custom_document_no; fall back to it when the
        # rule's configured number field isn't in the payload, so rules with a
        # non-default field still warn.
        value = frappe.utils.cint(
            d.get(scope["number_field"]) or d.get("custom_document_no")
        )
        if value <= 0:
            return None
        used_by = _document_no_taken(d, scope, value)
        return {
            "taken": bool(used_by),
            "used_by": used_by,
            "next": peek_next_document_no(d) if used_by else None,
        }
    except Exception:
        return None


def set_custom_name_field(doc):
    if not hasattr(doc, 'custom_name'):
        return
    if _engine_owns_field(doc, "custom_name"):
        # a Numbering Configuration rule targets Voucher No. for this doc —
        # the engine (set_custom_branch_name) generates it; don't overwrite.
        return
    # Amendment: keep the ORIGINAL's voucher number + the -1/-2 suffix instead
    # of recomputing the base (which would drift with an edited date/type),
    # matching the engine path and how the Document No. is already pinned.
    if doc.get("amended_from") and _pin_amended_name(doc, "custom_name"):
        return
    company_name = None
    if hasattr(doc, 'company') and doc.company:
        company_name = doc.company
    elif hasattr(doc, 'custom_company') and doc.custom_company:
        company_name = doc.custom_company
    if company_name and company_name == "Grihalaxmi Metal Industries Pvt. Ltd":
        # None, not "": custom_name carries a UNIQUE DB index — NULLs may
        # repeat freely, but a second empty-string row would violate it.
        doc.custom_name = None
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

    if _engine_owns_field(doc, "custom_name"):
        # engine-owned Voucher No.: set_custom_branch_name first clears
        # numbers carried over by copy paths, THEN runs its own uniqueness
        # guard — throwing here would reject the doc before that cleanup.
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
            f"Document No. {getattr(doc, 'custom_document_no', '')} is already used "
            f"by {existing}.{_next_number_hint(doc)} Please enter a different number.",
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
            (getattr(doc, "attendance_date", None) if hasattr(doc, "attendance_date") else None) or
            (getattr(doc, "custom_created_on", None) if hasattr(doc, "custom_created_on") else None)
        )

        if not date_field:
            frappe.throw(
                f"Date field (posting_date, transaction_date, attendance_date, or custom_created_on) is required for {doctype}.",
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

def _configured_doctypes():
    """Doctypes that have at least one enabled rule. Cached in redis (cleared
    when a Numbering Configuration is saved/deleted) + per request, so the
    wildcard hooks cost ~nothing for the vast majority of doctypes."""
    if not hasattr(frappe.local, "_numbering_doctypes_cache"):
        cached = frappe.cache().get_value("numbering_configured_doctypes")
        if cached is None:
            cached = frappe.get_all(
                "Numbering Configuration",
                filters={"enabled": 1},
                distinct=True,
                pluck="document_type",
            )
            frappe.cache().set_value("numbering_configured_doctypes", cached)
        frappe.local._numbering_doctypes_cache = set(cached)
    return frappe.local._numbering_doctypes_cache


def _numbering_rules_key(doctype):
    """Redis key holding the fully-assembled rules (with conditions + segments)
    for a single doctype."""
    return f"numbering_rules::{doctype}"


def clear_numbering_rules_cache():
    """Called when a Numbering Configuration changes."""
    frappe.cache().delete_value("numbering_configured_doctypes")
    # assembled-rules keys are per-doctype (numbering_rules::<doctype>)
    frappe.cache().delete_keys("numbering_rules::")
    for attr in ("_numbering_doctypes_cache", "_numbering_rules_cache"):
        if hasattr(frappe.local, attr):
            delattr(frappe.local, attr)


def _build_numbering_rules(doctype):
    """Assemble a doctype's enabled rules with their conditions + segments in a
    fixed 3 queries (1 rules + 2 batched child fetches), grouping the children
    in Python by parent — instead of the old 2 queries PER rule (N+1).
    Conditions and segments keep exact idx ordering."""
    # duplicate_action shipped after the other columns: in the deploy window
    # between code reload and `bench migrate`, selecting it would 1054-error
    # every save of every configured doctype. Probe once per build (results
    # are redis-cached, so this is not a hot path).
    fields = [
        "name", "company", "branch", "target_field", "separator",
        "date_field", "legacy_upto", "legacy_source_field", "auto_document_no",
        "document_no_field",
    ]
    # columns that shipped after the originals: probe so the deploy window
    # between code reload and `bench migrate` can't 1054-error every save
    for late_col in ("duplicate_action", "normal_docno_mode", "return_docno_mode",
                     "lock_group_fields"):
        if frappe.db.has_column("Numbering Configuration", late_col):
            fields.append(late_col)
    rules = frappe.get_all(
        "Numbering Configuration",
        filters={"document_type": doctype, "enabled": 1},
        fields=fields,
    )
    if not rules:
        return rules

    rule_names = [r["name"] for r in rules]

    # Voucher No. conditions (name generation) — no operator, plain equality.
    conditions = frappe.get_all(
        "Numbering Condition",
        filters={"parent": ["in", rule_names], "parenttype": "Numbering Configuration"},
        fields=["parent", "field", "value"],
        order_by="idx",
    )
    # Document No. conditions (auto-fill gate) — with operators.
    docno_conditions = frappe.get_all(
        "Numbering Document No Condition",
        filters={"parent": ["in", rule_names], "parenttype": "Numbering Configuration"},
        fields=["parent", "field", "value", "operator"],
        order_by="idx",
    )
    # Group Document No. By fields (series grouping). Table probe: shipped
    # after the others — must not 1054 in the deploy window before migrate.
    # Same for lock_after_numbering, a column shipped after the table.
    group_by_rows = []
    if frappe.db.table_exists("Numbering Group By Field"):
        group_by_fields = ["parent", "field"]
        if frappe.db.has_column("Numbering Group By Field", "lock_after_numbering"):
            group_by_fields.append("lock_after_numbering")
        group_by_rows = frappe.get_all(
            "Numbering Group By Field",
            filters={"parent": ["in", rule_names], "parenttype": "Numbering Configuration"},
            fields=group_by_fields,
            order_by="idx",
        )
    segments = frappe.get_all(
        "Numbering Segment",
        filters={"parent": ["in", rule_names], "parenttype": "Numbering Configuration"},
        fields=["parent", "segment_type", "static_value", "return_value", "field", "fetch_field", "number_length", "join_previous"],
        order_by="idx",
    )

    # group children by parent, preserving idx order (rows arrive idx-ascending;
    # grouping keeps each parent's relative order intact)
    def _group(rows):
        out = {}
        for row in rows:
            out.setdefault(row.pop("parent"), []).append(row)
        return out

    cond_by_parent = _group(conditions)
    docno_cond_by_parent = _group(docno_conditions)
    group_by_parent = _group(group_by_rows)
    seg_by_parent = _group(segments)

    for r in rules:
        # rules with zero children still get empty lists
        r["conditions"] = cond_by_parent.get(r["name"], [])
        r["document_no_conditions"] = docno_cond_by_parent.get(r["name"], [])
        r["docno_group_by"] = group_by_parent.get(r["name"], [])
        r["segments"] = seg_by_parent.get(r["name"], [])

    return rules


def _numbering_rules_for(doctype):
    """All enabled Numbering Configuration rules for a doctype, with conditions + segments.
    Layered cache: per-request (frappe.local) on top of redis on top of a batched DB
    build. Redis holds the fully-assembled rule dicts in the exact shape returned here,
    so both saves and (separate-request) live previews avoid the N+1 rule fetch."""
    # Per-request cache: if rules have already been fetched, return the cached copy
    if not hasattr(frappe.local, "_numbering_rules_cache"):
        frappe.local._numbering_rules_cache = {}

    if doctype in frappe.local._numbering_rules_cache:
        return frappe.local._numbering_rules_cache[doctype]

    if doctype not in _configured_doctypes():
        frappe.local._numbering_rules_cache[doctype] = []
        return []

    # Redis layer: fully-assembled rules, built once per doctype and reused across
    # requests (invalidated by clear_numbering_rules_cache on any rule change).
    rules = frappe.cache().get_value(_numbering_rules_key(doctype))
    if rules is None:
        rules = _build_numbering_rules(doctype)
        frappe.cache().set_value(_numbering_rules_key(doctype), rules)

    frappe.local._numbering_rules_cache[doctype] = rules
    return rules


def _rule_date(doc, rule):
    """The rule's document date: the configured Document Date Field when set,
    else the hardcoded Posting/Transaction Date fallback. Drives the Fiscal
    Year segment and the legacy cut-over comparison."""
    if rule.get("date_field"):
        return doc.get(rule["date_field"])
    return _doc_date(doc)


def _condition_matches(doc, cond):
    """Evaluate one condition with its operator. A blank/absent operator means
    Equals — so rules created before operators existed behave exactly as before.

    Operators:
      Equals / Not Equals  — scalar compare (string-normalised)
      In / Not In          — value is a comma-separated list
      Is Set / Is Not Set  — the field is (non-)empty; value ignored
    """
    op = (cond.get("operator") or "Equals").strip()
    field_value = frappe.utils.cstr(doc.get(cond.get("field")))

    if op in ("Is Set", "Is Not Set"):
        # A blank, "0", or 0.0 is "not set" — covers Check/Int gate fields where
        # 0/unchecked is semantically empty, as well as truly-empty text/links.
        is_set = field_value.strip() not in ("", "0", "0.0")
        return is_set if op == "Is Set" else not is_set

    if op in ("In", "Not In"):
        items = [v.strip() for v in frappe.utils.cstr(cond.get("value")).split(",") if v.strip()]
        in_list = field_value in items
        return in_list if op == "In" else not in_list

    target = frappe.utils.cstr(cond.get("value"))
    if op == "Not Equals":
        return field_value != target
    return field_value == target  # Equals (default)


def _rule_matches(doc, rule):
    """True if the document satisfies the rule's company/branch scope
    and ALL conditions."""
    if rule.get("company") and rule["company"] != getattr(doc, "company", None):
        return False
    if rule.get("branch") and rule["branch"] != getattr(doc, "custom_branch", None):
        return False

    for cond in rule.get("conditions", []):
        if not _condition_matches(doc, cond):
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


def _ambiguous_numbering_rules(doc):
    """Enabled rules that TIE for most-specific on this document. The winner is
    still deterministic (broken by name in _matching_numbering_rules), but a tie
    means the choice is arbitrary — two overlapping rules the admin probably
    didn't intend. Returns the tied rules (len >= 2) so the form/config can warn;
    empty when the match is unambiguous."""
    matches = _matching_numbering_rules(doc)
    if len(matches) < 2:
        return []
    top = _rule_specificity(matches[0])
    tied = [r for r in matches if _rule_specificity(r) == top]
    return tied if len(tied) > 1 else []


def _engine_owns_field(doc, fieldname):
    """True when an enabled Numbering Configuration rule matching this doc
    targets `fieldname` — the engine then owns that field and legacy
    generators must not write it."""
    return any(
        (r.get("target_field") or "custom_branch_name") == fieldname
        for r in _matching_numbering_rules(doc)
    )


def _is_counterless(doc, rule):
    """True when the rule produces this doc's number WITHOUT consuming a
    counter: either a pass-through rule (no Number segment) or the doc falls
    in the rule's legacy window (number copied from the legacy source field).
    Counterless values are safe to recompute on every draft save."""
    if rule.get("legacy_upto"):
        doc_date = _rule_date(doc, rule)
        if doc_date and frappe.utils.getdate(doc_date) <= frappe.utils.getdate(rule["legacy_upto"]):
            return True
    return not any(
        seg.get("segment_type") == "Number" for seg in rule.get("segments", [])
    )


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


def _resolve_segment(doc, seg, sep, rule=None):
    """Resolve one non-Number segment to a string ('' if empty/not applicable).
    `rule` supplies rule-level settings (the Document Date Field for the
    Fiscal Year segment); without it the hardcoded date fallback applies."""
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
            frappe.get_cached_value("Branch", branch, "custom_abbr") or ""
        )

    if stype == "Fiscal Year":
        doc_date = _rule_date(doc, rule) if rule else _doc_date(doc)
        fy = get_fiscal_year_from_date(doc_date) or ""
        # avoid separator collision when the separator is '/'
        return fy.replace("/", "-") if sep == "/" else fy

    if stype == "Name Number":
        # Mirror of the DOCUMENT NAME's running number (its trailing digit
        # run), zero-padded to the segment's Digits. No counter of its own —
        # the voucher number can never drift from the name's number, even
        # when the rule's resolved prefix equals the name-series prefix.
        name = frappe.utils.cstr(doc.get("name") or "")
        if doc.get("amended_from"):
            # amended names end in -1/-2 …; the number is in the base name
            name = re.sub(r"-\d+$", "", name)
        m = re.search(r"(\d+)$", name)
        if not m:
            return ""
        length = int(seg.get("number_length") or 0)
        return m.group(1).zfill(length) if length else m.group(1)

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
            frappe.get_cached_value(link_dt, link_value, seg.get("fetch_field")) or ""
        )

    return ""


def _peek_series(key, digits, floor=0):
    """Next number for a series WITHOUT incrementing the counter (for previews).
    Mirrors _draw_engine_series: never below the data floor."""
    row = frappe.db.sql("select current from `tabSeries` where name=%s", key)
    current = row[0][0] if row and row[0][0] is not None else 0
    return ("%0" + str(int(digits)) + "d") % (max(int(current), int(floor)) + 1)


def _like_escape(text):
    """Escape a literal string for use inside a LIKE pattern."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _series_data_floor(doc, rule, resolved, sep):
    """Highest counter value already STORED in the rule's target column for
    this series shape (prefix/suffix around the Number segment), 0 if none.

    The tabSeries counter can lag the data — a hand-edited target value, a
    restored backup, a series that predates the rule — and a plain counter
    draw would then re-issue a taken number and die on the uniqueness check
    (e.g. every duplicate of the lone invoice in a series failing with
    "Number ... is already used"). Drawing above this floor self-heals."""
    target = _safe_col(rule.get("target_field")) or "custom_branch_name"
    target_df = doc.meta.get_field(target)
    if not target_df or target_df.fieldtype in frappe.model.no_value_fields + frappe.model.table_fields:
        return 0

    sentinel = "\x00"
    built = _join_parts(
        [(sentinel if r["num"] else r.get("value"), r["glue"]) for r in resolved], sep
    )
    if not built or sentinel not in built:
        return 0
    prefix, _, suffix = built.partition(sentinel)

    table = "tab" + doc.doctype.replace("`", "")
    number_sql = (
        "SUBSTRING(`{col}`, %(plen)s + 1, "
        "CHAR_LENGTH(`{col}`) - %(plen)s - %(slen)s)"
    ).format(col=target)
    row = frappe.db.sql(
        "SELECT MAX(CAST({num} AS UNSIGNED)) FROM `{table}` "
        "WHERE `{col}` LIKE %(like)s AND docstatus < 2 "
        "AND {num} REGEXP '^[0-9]+$'".format(num=number_sql, table=table, col=target),
        {
            "plen": len(prefix),
            "slen": len(suffix),
            "like": _like_escape(prefix) + "%" + _like_escape(suffix),
        },
    )
    return int(row[0][0]) if row and row[0][0] is not None else 0


# Engine voucher counters are NAMESPACED in tabSeries: a rule's resolved
# prefix can be byte-identical to a CORE DOC-NAME series key (e.g. segments
# Company Abbr + "SB" + Fiscal Year resolve to "NGN-SB-82/83-", exactly the
# key make_name_with_fiscal_year's pattern feeds core getseries). Without a
# namespace both counters share one tabSeries row and every save increments
# it twice — names and vouchers each skip numbers and drift apart.
ENGINE_SERIES_NAMESPACE = "ncfg:"


def _engine_series_name(key):
    """tabSeries row name for an engine voucher series. Continuity across the
    namespace switch is preserved by the data-floor scan: a namespaced series
    with no row yet starts at MAX(stored numbers) + 1."""
    return ENGINE_SERIES_NAMESPACE + key


def _draw_engine_series(key, digits, floor):
    """Atomic next voucher-name counter, never below the data floor — the same
    deadlock-resistant upsert as _draw_next_document_no, instead of core
    getseries, so a counter that lags the stored data jumps past the taken
    numbers rather than re-issuing one."""
    frappe.db.sql(
        "INSERT INTO `tabSeries` (`name`, `current`) VALUES (%(key)s, %(floor)s) "
        "ON DUPLICATE KEY UPDATE `current` = GREATEST(`current` + 1, %(floor)s)",
        {"key": key, "floor": int(floor) + 1},
    )
    return ("%0" + str(int(digits)) + "d") % _series_current(key)


def _pad_segment_value(seg, value):
    """Zero-pad a Document Field / Fetch from Link value when it is a plain
    number and the segment has Digits set — mirrors the legacy voucher
    padding (e.g. 655 -> 000655)."""
    if not value or seg.get("segment_type") not in ("Document Field", "Fetch from Link"):
        return value
    length = int(seg.get("number_length") or 0)
    if length and value.isdigit():
        return value.zfill(length)
    return value


def _resolve_segments(doc, rule, sep):
    """Return an ordered list of resolved parts:
       [{"num": True, "len": n, "glue": bool} | {"num": False, "value": str, "glue": bool}]
       and whether a Number exists. "glue" joins the part directly onto the
       previous one (no separator), e.g. a Document Word after the number.
    """
    resolved = []
    has_number = False
    for seg in rule.get("segments", []):
        glue = bool(seg.get("join_previous"))
        if seg.get("segment_type") == "Number":
            resolved.append({"num": True, "len": int(seg.get("number_length") or 6), "glue": glue})
            has_number = True
        else:
            value = _pad_segment_value(seg, _resolve_segment(doc, seg, sep, rule))
            part = {"num": False, "value": value, "glue": glue}
            if seg.get("segment_type") == "Name Number" and not value:
                # the number IS the voucher's identity — a build without it
                # must yield None (fall through), never a truncated voucher
                part["nn_empty"] = True
            resolved.append(part)
    return resolved, has_number


def _join_parts(parts, sep):
    """Join resolved [(value, glue)] pairs: glued parts concatenate onto the
    previous part, everything else is separated by `sep`. Empty values are
    skipped."""
    chunks = []
    for value, glue in parts:
        if not value:
            continue
        if glue and chunks:
            chunks[-1] += value
        else:
            chunks.append(value)
    return sep.join(chunks) if chunks else None


def _build_from_segments(doc, rule, commit_series=True, force_scan=False):
    """Build the number by joining resolved segments (in order) with the separator.

    - Non-empty non-Number segments identify the series (the counter key).
    - The Number segment is replaced by the running counter (atomic draw, never
      below the highest number already stored in the target column), or by the
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
    if rule.get("legacy_upto"):
        doc_date = _rule_date(doc, rule)
        if doc_date and frappe.utils.getdate(doc_date) <= frappe.utils.getdate(rule["legacy_upto"]):
            source = rule.get("legacy_source_field")
            value = (frappe.utils.cstr(doc.get(source)).strip() or None) if source else None
            if value:
                return value + get_amendment_suffix(doc)
            # Empty source:
            #  * source == target — the "keep the imported number" config. A
            #    NEW document backdated into the window has nothing to keep;
            #    generate below like any other doc instead of silently saving
            #    it without a voucher number.
            #  * source != target — the old number lives in another field
            #    (e.g. narration); empty means fall through to the next
            #    matching rule (documented behavior).
            if source != (rule.get("target_field") or "custom_branch_name"):
                return None

    sep = rule.get("separator") or "/"
    resolved, has_number = _resolve_segments(doc, rule, sep)
    if any(r.get("nn_empty") for r in resolved):
        # a Name Number segment couldn't resolve (doc has no name yet, or the
        # name carries no number) — never store a voucher without its number
        return None
    if not has_number:
        # pass-through: rebuilt from the same (copied) inputs, so an amendment
        # would collide with its cancelled original — the -1/-2 suffix from the
        # amended name keeps them apart, matching the legacy voucher behavior.
        # Counter rules below don't need this: an amendment draws a fresh number.
        value = _join_parts([(r["value"], r["glue"]) for r in resolved], sep)
        return value + get_amendment_suffix(doc) if value else None

    key_parts = [r["value"] for r in resolved if not r["num"] and r.get("value")]
    raw_key = sep.join(key_parts) + sep
    number_len = next((r["len"] for r in resolved if r["num"]), 6)

    # NAME-MIRROR: when the rule's series IS the document name's series — the
    # name is exactly this prefix + a digit run (e.g. rule parts NGN, SB,
    # 82/83 and name NGN-SB-82/83-00004) — the voucher takes the NAME's
    # number (padded to the rule's Digits) instead of drawing its own.
    # One series must never be counted twice: drawing here would double-step
    # the shared counter and make name and voucher drift apart.
    doc_name = frappe.utils.cstr(doc.get("name") or "")
    if doc_name.startswith(raw_key):
        m = re.match(r"^(\d+)(-\d+)?$", doc_name[len(raw_key):])  # -N = amendment
        if m:
            seq = ("%0" + str(int(number_len)) + "d") % int(m.group(1))
            return _join_parts(
                [(seq if r["num"] else r.get("value"), r["glue"]) for r in resolved], sep
            )

    series_key = _engine_series_name(raw_key)

    # Same fast path as _draw_next_document_no: skip the O(n) data-floor scan
    # while the series is verified; floor=0 leaves the counter authoritative.
    # force_scan (the collision self-heal in set_custom_branch_name) drops the
    # marker and takes the scan unconditionally.
    if not force_scan and _series_row_exists(series_key) and _floor_verified(series_key):
        floor = 0
    else:
        if force_scan:
            _clear_floor_verified(series_key)
        floor = _series_data_floor(doc, rule, resolved, sep)
        if floor <= _series_current(series_key):
            _mark_floor_verified(series_key)
    seq = (
        _draw_engine_series(series_key, number_len, floor)
        if commit_series
        else _peek_series(series_key, number_len, floor)
    )

    return _join_parts(
        [(seq if r["num"] else r.get("value"), r["glue"]) for r in resolved], sep
    )


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
        "auto_document_no": cfg.get("auto_document_no"),
        "normal_docno_mode": cfg.get("normal_docno_mode"),
        "return_docno_mode": cfg.get("return_docno_mode"),
        "document_no_field": cfg.get("document_no_field"),
        "duplicate_action": cfg.get("duplicate_action"),
        "conditions": [
            {"field": c.field, "value": c.value}
            for c in (cfg.conditions or [])
        ],
        "document_no_conditions": [
            {"field": c.field, "value": c.value, "operator": c.get("operator")}
            for c in (cfg.get("document_no_conditions") or [])
        ],
        "lock_group_fields": cfg.get("lock_group_fields"),
        "docno_group_by": [
            {"field": g.field, "lock_after_numbering": g.get("lock_after_numbering")}
            for g in (cfg.get("docno_group_by") or [])
        ],
        "segments": [
            {
                "segment_type": s.segment_type,
                "static_value": s.static_value,
                "return_value": s.get("return_value"),
                "field": s.field,
                "fetch_field": s.fetch_field,
                "number_length": s.number_length,
                "join_previous": s.get("join_previous"),
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
            f"Number {value} is already used by {existing}.{_next_number_hint(doc)} "
            f"Leave the field empty to get the next number automatically.",
            title="Duplicate Document Number",
        )


def _renumber_if_scope_changed(doc, rule, target):
    """A DRAFT's counter number must follow its series scope: when the branch,
    company or fiscal year changed after the number was drawn, the document
    would keep a number from the wrong series. Give the old number back to
    its series (only if it was the last one issued — same rule as delete)
    and draw a fresh one from the current series. Values that can't be
    recognised as this rule's output are left untouched."""
    old_key, old_no = _parse_engine_number(doc, rule, doc.get(target))
    if old_key is None:
        return

    sep = rule.get("separator") or "/"
    resolved, _ = _resolve_segments(doc, rule, sep)
    new_key = _engine_series_name(
        sep.join(r["value"] for r in resolved if not r["num"] and r.get("value")) + sep
    )
    if old_key == new_key:
        return

    _revert_series_if_last(old_key, old_no)
    fresh = _build_from_segments(doc, rule)
    if fresh:
        doc.set(target, fresh)


def _pin_amended_name(doc, target):
    """An amendment is the SAME voucher re-issued after cancellation, so its
    voucher number (the target field, e.g. custom_name) is the ORIGINAL's plus
    the -1/-2 amendment suffix — never re-derived from the amendment's own
    (editable) fields. Mirror of _pin_amended_docno, which pins the Document No.
    the same way. Without this the name is rebuilt from segments/legacy on every
    save, so editing the amendment's date (e.g. into the legacy cut-over window)
    or its type would silently change the voucher number.

    Returns True when the name was pinned; False when there is nothing to pin
    (not an amendment, or the original carries no number) so normal generation
    applies (e.g. amending a legacy/Grihalaxmi doc that had no custom_name).
    """
    parent = doc.get("amended_from")
    if not parent:
        return False
    row = frappe.db.get_value(doc.doctype, parent, [target, "amended_from"], as_dict=True)
    if not row or not row.get(target):
        return False
    suffix = get_amendment_suffix(doc)
    if not suffix:
        # Name not assigned yet (no -N to distinguish this from the original):
        # fall through to normal generation rather than pinning to the exact
        # original name and colliding with it on the unique index.
        return False
    base = frappe.utils.cstr(row.get(target))
    if row.get("amended_from"):
        # the parent is itself an amendment: its value ends in its own -N
        # suffix (the final -digits); strip just that so suffixes don't stack.
        base = re.sub(r"-\d+$", "", base)
    doc.set(target, base + suffix)
    return True


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

        # Amendment: the voucher number is the ORIGINAL's + the -1/-2 suffix,
        # never re-derived (which could drift with an edited date — e.g. into
        # the legacy cut-over window — or type). Mirrors _pin_amended_docno,
        # which already pins the Document No. this way.
        if doc.get("amended_from") and _pin_amended_name(doc, target):
            _validate_unique_number(doc, target)
            return

        # A STORED number never changes from OUTSIDE: a client/API/import edit
        # of an already-numbered document is discarded in favor of the stored
        # value (the form field is read-only, but REST and scripts are not).
        # Only the engine itself may renumber (counterless recompute and the
        # draft scope-change redraw below); a deliberate correction can opt in
        # via frappe.flags.allow_number_overwrite.
        if not doc.is_new() and not frappe.flags.get("allow_number_overwrite"):
            stored = frappe.db.get_value(doc.doctype, doc.name, target)
            if stored and doc.get(target) != stored:
                doc.set(target, stored)

        # A NEW document arriving with another document's number means the
        # value was carried over by a copy path that bypassed no_copy
        # (server copy_doc, API, import). Clear it so a fresh number is
        # generated — new data must never keep an old number.
        if doc.is_new() and _number_belongs_to_other_doc(doc, target):
            doc.set(target, None)

        if doc.get(target):
            # already numbered (generate once) — but drafts still track their
            # inputs: counterless values (pass-through / legacy copy) follow
            # their source fields, and counter numbers follow their series
            # scope (branch / company / fiscal year).
            if doc.docstatus == 0:
                if _is_counterless(doc, rule):
                    fresh = _build_from_segments(doc, rule)  # no counter consumed
                    if fresh and fresh != doc.get(target):
                        doc.set(target, fresh)
                else:
                    _renumber_if_scope_changed(doc, rule, target)
            _validate_unique_number(doc, target)
            return

        number = _build_from_segments(doc, rule)
        if number:
            doc.set(target, number)
            if _number_belongs_to_other_doc(doc, target):
                # A FRESH draw can only collide when the counter lags numbers
                # stored behind its back (raw-SQL write, restored backup) and
                # the fast path skipped the healing scan. Rescan and redraw
                # once; _validate_unique_number still throws if even the
                # rescanned draw collides.
                healed = _build_from_segments(doc, rule, force_scan=True)
                if healed:
                    doc.set(target, healed)
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


def _parse_engine_number(doc, rule, value):
    """Derive (series_key, counter) from a STORED engine-generated number.

    The key is reconstructed from the stored string itself — not from the
    document's current field values — so it stays correct even when scope
    fields (branch, company, date) changed after the number was drawn.
    Returns (None, None) when the value cannot be confidently recognised as
    a number generated by this rule; callers must then leave it alone.
    """
    sep = rule.get("separator") or "/"
    resolved, has_number = _resolve_segments(doc, rule, sep)
    if not has_number:
        return None, None

    number_len = next((r["len"] for r in resolved if r["num"]), 6)

    # locate the Number's index among the non-empty display parts
    num_index, display_count = None, 0
    for r in resolved:
        if r["num"]:
            num_index = display_count
            display_count += 1
        elif r.get("value"):
            display_count += 1

    parts = str(value).split(sep)

    # exact current shape (same segments non-empty then and now)
    if num_index is not None and len(parts) == display_count and parts[num_index].isdigit():
        key = sep.join(parts[:num_index] + parts[num_index + 1:]) + sep
        return _engine_series_name(key), int(parts[num_index])

    # shape changed (e.g. a Branch Abbr that was empty is now filled): the
    # counter is the single all-digit part of the configured width.
    digit_idx = [i for i, p in enumerate(parts) if p.isdigit() and len(p) == number_len]
    if len(digit_idx) == 1:
        i = digit_idx[0]
        key = sep.join(parts[:i] + parts[i + 1:]) + sep
        return _engine_series_name(key), int(parts[i])

    return None, None


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

    series_key, number = _parse_engine_number(doc, rule, number_str)
    if series_key:
        _revert_series_if_last(series_key, number)


def _revert_document_no_series(doc):
    """Step the document-number counter back when the deleted document held the
    last number in its scope, so the number is reused — mirroring the historical
    max+1 self-heal. Mid-series gaps are left alone. Manual numbers never
    consumed the counter, so they are skipped."""
    field = _docno_field(_match_numbering_rule(doc))
    if not doc.meta.has_field(field):
        return
    # Manual numbers and amendments never consumed the counter -> never revert.
    if _is_manual_document_no(doc, field) or doc.get("amended_from"):
        return
    number = frappe.utils.cint(doc.get(field))
    if not number:
        return
    scope = _docno_scope(doc)
    if not scope:
        return
    # Only revert when the stored number still belongs to the CURRENT scope. If
    # branch / company / date / type changed after the number was drawn, the
    # recomputed scope points at a DIFFERENT series and must not be stepped back
    # (that would gap this series and could wrongly decrement another). The
    # stored target value was built with the scope at draw time, so it matches
    # the current pattern only when the scope is unchanged.
    # Group-by (filter) scopes have no stored prefix to compare — their scope is
    # computed from the doc's own field values, and drafts are already redrawn
    # onto the right series whenever those fields change, so the recomputed
    # scope IS the draw-time scope.
    if scope.get("pattern"):
        stored = frappe.utils.cstr(doc.get(scope["field"]))
        if not fnmatch.fnmatch(stored, scope["pattern"].replace("%", "*")):
            return
    _revert_series_if_last(_docno_series_key(doc, scope), number)


def revert_series_on_delete(doc, method=None):
    """
    Called on after_delete. Mirrors what frappe.model.delete_doc does for
    standard naming_series doctypes: if the deleted document was the last
    one issued in its series, the counter steps back so the number is reused.
    Mid-series gaps are left alone, exactly like core.
    """
    doctype = doc.doctype

    # 0) Document-number counter (custom_document_no) revert.
    _revert_document_no_series(doc)

    # 1) Numbering Configuration engine series revert now happens in the
    #    wildcard revert_engine_series_on_delete (all doctypes); here the rule
    #    lookup only gates the legacy branch-series fallback below.
    rule = _match_numbering_rule(doc)

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
    # engine numbering (set_custom_branch_name) is NOT called here: the
    # wildcard doc_events run apply_engine_numbering for EVERY doctype right
    # after these doctype-specific handlers — same order, single execution.
    # apply_document_no handles both lifecycles: draw for new docs, redraw
    # for saved drafts whose series scope changed.
    apply_document_no(doc)
    set_custom_name_field(doc)
    validate_document_no(doc)
    validate_custom_name_unique(doc)


def handle_before_save(doc, method=None):
    """
    Ensure numbering happens after fields like custom_p_type_code
    are set (often during save). This is the final chance before insert.
    apply_document_no is idempotent within a save, so the assignment (and its
    per-scope lock) happens exactly once even though this runs after validate.
    """
    apply_document_no(doc)
    set_custom_name_field(doc)
    validate_document_no(doc)
    validate_custom_name_unique(doc)


def apply_engine_numbering(doc, method=None):
    """Wildcard validate/before_save hook: rule-driven numbering for EVERY
    doctype. Doctypes without enabled rules exit via the cached
    _configured_doctypes() gate inside the engine (plus the plain
    custom_branch_name = doc.name fallback where that field exists)."""
    if doc.meta.istable or frappe.flags.in_install or frappe.flags.in_migrate:
        return
    # Draw the document number first (idempotent via flags — a no-op for the
    # audited doctypes where handle_validate already ran it), then build the
    # name from it. This wildcard makes rule-driven auto-numbering work for ANY
    # doctype that carries custom_document_no, not just the audited ones.
    # Non-new drafts get the scope-change redraw inside apply_document_no.
    apply_document_no(doc)
    set_custom_branch_name(doc)


def revert_engine_series_on_delete(doc, method=None):
    """Wildcard after_delete hook: step the engine series back when the
    deleted document held the last issued number."""
    if doc.meta.istable or frappe.flags.in_install or frappe.flags.in_migrate:
        return
    if doc.doctype not in _configured_doctypes():
        return
    rule = _match_numbering_rule(doc)
    if rule:
        _revert_engine_series(doc, rule)


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
