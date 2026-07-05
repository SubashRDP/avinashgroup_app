import fnmatch
import json
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


def _resolve_docno_fiscal_year(doc):
    if doc.get("custom_fiscal_year"):
        return doc.get("custom_fiscal_year")
    date_field = (
        doc.get("posting_date")
        or doc.get("transaction_date")
        or doc.get("custom_created_on")
    )
    return get_fiscal_year_from_date(date_field) if date_field else None


def _is_docno_position_segment(seg):
    """A segment that represents the number itself (not part of the series
    scope): a real Number segment, or the Document Field carrying
    custom_document_no / custom_document_word."""
    if seg.get("segment_type") == "Number":
        return True
    return seg.get("segment_type") == "Document Field" and seg.get("field") in (
        "custom_document_no",
        "custom_document_word",
    )


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

    Returns None when the rule has no number position (a pass-through rule),
    so the caller falls back to the legacy company+code+year scope."""
    sep = rule.get("separator") or "/"
    parts = []  # (value_or_wildcard, glue, is_number)
    number_seen = False
    for seg in rule.get("segments", []):
        glue = bool(seg.get("join_previous"))
        if _is_docno_position_segment(seg):
            # The word is the glued tail of the number and is covered by the same
            # wildcard, so only the number/custom_document_no adds a placeholder.
            if seg.get("segment_type") == "Number" or seg.get("field") == "custom_document_no":
                if not number_seen:
                    parts.append(("%", glue, True))
                    number_seen = True
            continue
        value = _pad_segment_value(seg, _resolve_segment(doc, seg, sep))
        parts.append((value, glue, False))

    if not number_seen:
        return None

    target = rule.get("target_field") or "custom_branch_name"
    # The pattern is matched against the rule's target field to find the current
    # max. If that field doesn't exist on this doctype the rule is inapplicable
    # (the engine skips it too) — fall back to the legacy scope.
    if not doc.meta.has_field(target):
        return None

    pattern = _join_parts([(v, g) for (v, g, _n) in parts], sep)
    key = _join_parts([(v, g) for (v, g, n) in parts if not n], sep) or ""
    return {"key": key, "pattern": pattern, "field": target}


def _docno_eligible(doc, rule):
    """Whether this document should get an auto document number.

      1. Rule-driven (the generalized path): the matching Numbering Configuration
         rule has 'Auto-fill Document No.' ticked AND the document satisfies the
         rule's separate DOCUMENT NO. CONDITIONS (Equals / In / Is Set …). These
         are independent of the Voucher No. conditions that select the rule, so
         you can format the name for a broad set but only number a subset.
         Empty Document No. conditions = number every document the rule applies to.
      2. Fallback: the hardcoded AUTO_NUMBER_CONFIG (type field in a fixed list),
         so day-one behaviour is unchanged for the doctypes shipped with it.
    """
    # A matching Auto-fill rule is AUTHORITATIVE for the Document No.: the doc is
    # numbered iff ALL of the rule's Document No. conditions match (empty list =
    # number every doc the rule applies to). This lets the conditions both turn
    # numbering ON for new types and RESTRICT it (e.g. only when a branch is set)
    # — the fallback below is NOT consulted once such a rule applies.
    if rule and rule.get("auto_document_no"):
        return all(_condition_matches(doc, c) for c in rule.get("document_no_conditions", []))

    # No Auto-fill rule applies -> hardcoded fallback (day-one behaviour): the
    # type field is in the shipped list.
    cfg = AUTO_NUMBER_CONFIG.get(doc.doctype)
    if not cfg:
        return False
    type_field = cfg.get("type_field")
    type_value = doc.get(type_field) if type_field else None
    return bool(type_value and type_value in cfg.get("types", []))


def _docno_scope(doc):
    """Series scope for the auto document number, or None when the doc is not
    eligible. Returns a dict {key, pattern, field}:

      * When a Numbering Configuration rule matches, the scope is DERIVED FROM
        THE RULE (branch / conditions aware) — see _rule_docno_scope.
      * Otherwise it falls back to the legacy company + code + fiscal-year scope,
        matched on custom_name (unchanged historical behaviour).

    Also back-fills custom_p_type_code on the doc when it was empty but
    resolvable, so the custom_name built later is correct even if the framework
    has not run its own fetch yet."""
    rule = _match_numbering_rule(doc)
    if not _docno_eligible(doc, rule):
        return None

    code = _resolve_p_type_code(doc)
    company_abbr = get_company_abbr(doc)
    fiscal_year = _resolve_docno_fiscal_year(doc)

    if doc.meta.has_field("custom_p_type_code") and code and not doc.get("custom_p_type_code"):
        doc.custom_p_type_code = code

    # Rule-derived scope (branch / condition aware) when the matching rule defines
    # a number position.
    if rule:
        rule_scope = _rule_docno_scope(doc, rule)
        if rule_scope and rule_scope.get("pattern"):
            return rule_scope

    # Legacy fallback scope needs the company + code + fiscal-year triple.
    if not (code and company_abbr and fiscal_year):
        return None
    return {
        "key": "|".join((company_abbr, code, fiscal_year)),
        "pattern": f"{company_abbr}-{code}-%-{fiscal_year}%",
        "field": "custom_name",
    }


def _current_max_document_no(doc, scope):
    """Highest custom_document_no already used in this scope (0 if none).
    Matches the scope's pattern against its target field, so per-branch scopes
    only ever see that branch's documents.

    CAST(... AS UNSIGNED) makes the max NUMERIC even where custom_document_no is
    a Data column (Purchase Receipt) rather than Int — a plain MAX() on a varchar
    compares lexicographically ("9" > "50"), which would compute a wrong floor
    and let auto numbers eventually collide with a higher manual number."""
    table = "tab" + doc.doctype.replace("`", "")
    field = scope["field"].replace("`", "")
    row = frappe.db.sql(
        "SELECT MAX(CAST(`custom_document_no` AS UNSIGNED)) "
        "FROM `{table}` WHERE `{field}` LIKE %s".format(table=table, field=field),
        (scope["pattern"],),
    )
    return int(row[0][0]) if row and row[0][0] is not None else 0


def _docno_series_key(doc, scope):
    return "docno:" + doc.doctype + "|" + scope["key"]


def _series_current(key):
    """Current counter for a series key, 0 if the row does not exist. Plain
    read — no lock — so it is safe to call from the preview path."""
    row = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE name = %s", key)
    return frappe.utils.cint(row[0][0]) if row and row[0][0] is not None else 0


def peek_next_document_no(doc):
    """Non-reserving preview of the number this doc would get right now.
    No lock, no side effects — safe for the live form preview. Mirrors the
    authoritative GREATEST(counter+1, data_max+1) so the preview matches what
    save assigns. Returns None when the type is not auto-numbered or the scope
    fields are incomplete."""
    scope = _docno_scope(doc)
    if not scope:
        return None
    return max(
        _current_max_document_no(doc, scope),
        _series_current(_docno_series_key(doc, scope)),
    ) + 1


def _next_number_hint(doc):
    """A ' Next available number is N.' fragment for duplicate-number errors,
    or '' when a next number can't be determined. Best-effort — never raises."""
    try:
        nxt = peek_next_document_no(doc)
    except Exception:
        nxt = None
    return f" Next available number is {nxt}." if nxt else ""


def _draw_next_document_no(doc, scope):
    """Atomic, deadlock-resistant next number for a scope.

    A single `INSERT ... ON DUPLICATE KEY UPDATE` bumps a per-scope counter in
    `tabSeries`, never dropping below the existing data max (the seed floor, so
    the counter continues an existing series and jumps past any manually-typed
    number). Two saves for the same scope hit the SAME row and serialize on a
    brief row lock — not a transaction-long `SELECT ... FOR UPDATE` — which is
    what avoids the gap-lock deadlock against core `getseries` (the doc-name
    series) that a long-held lock would cause. The counter is authoritative:
    `current + 1` guarantees each concurrent save a distinct number."""
    key = _docno_series_key(doc, scope)
    floor = _current_max_document_no(doc, scope) + 1
    frappe.db.sql(
        "INSERT INTO `tabSeries` (`name`, `current`) VALUES (%(key)s, %(floor)s) "
        "ON DUPLICATE KEY UPDATE `current` = GREATEST(`current` + 1, %(floor)s)",
        {"key": key, "floor": floor},
    )
    return _series_current(key)


def _is_manual_document_no(doc):
    """True when custom_document_no was entered by the user and must be
    preserved (only uniqueness-checked), not auto-drawn."""
    if doc.meta.has_field("custom_document_no_manual"):
        return bool(frappe.utils.cint(doc.get("custom_document_no_manual")))
    # Flag field not deployed yet: we cannot tell a user value from a stale
    # client preview, so treat any existing value as manual (never overwrite).
    return bool(doc.get("custom_document_no"))


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
    if not doc.is_new():
        return
    # Any doctype that carries custom_document_no can be auto-numbered — via a
    # rule (auto_document_no) or the hardcoded fallback. Eligibility is decided
    # inside _docno_scope; here we only skip doctypes without the field.
    if not doc.meta.has_field("custom_document_no"):
        return

    if _is_manual_document_no(doc):
        doc.flags._docno_assigned = True
        return

    # Amendment: keep the number copied from the cancelled original so the
    # amended voucher stays tied to it (custom_name adds the -1/-2 suffix). A
    # plain Duplicate/Copy is NOT an amendment (no amended_from) and correctly
    # falls through to draw a fresh number.
    if doc.get("amended_from") and doc.get("custom_document_no"):
        doc.flags._docno_assigned = True
        return

    scope = _docno_scope(doc)
    if not scope:
        # Not eligible yet (missing code / company / fiscal year, or a type that
        # is simply not auto-numbered). Blank it for manual entry and do NOT set
        # the assigned flag, so a later hook retries once the scope is complete.
        doc.custom_document_no = None
        return

    doc.custom_document_no = _draw_next_document_no(doc, scope)
    if doc.meta.has_field("custom_document_no_manual"):
        doc.custom_document_no_manual = 0
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
        data = doc if doc is not None else kwargs
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict) or not data.get("doctype"):
            return None
        # Only expose the next number to users who can read the doctype (the
        # sibling preview_document_number does the same) — the number leaks the
        # scope's current count otherwise.
        if not frappe.has_permission(data["doctype"], "read"):
            return None
        scalars = {k: v for k, v in data.items() if not isinstance(v, (list, dict))}
        return peek_next_document_no(frappe.get_doc(scalars))
    except Exception:
        return None


def set_custom_name_field(doc):
    if not hasattr(doc, 'custom_name'):
        return
    if _engine_owns_field(doc, "custom_name"):
        # a Numbering Configuration rule targets Voucher No. for this doc —
        # the engine (set_custom_branch_name) generates it; don't overwrite.
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
    rules = frappe.get_all(
        "Numbering Configuration",
        filters={"document_type": doctype, "enabled": 1},
        fields=[
            "name", "company", "branch", "target_field", "separator",
            "date_field", "legacy_upto", "legacy_source_field", "auto_document_no",
        ],
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
    seg_by_parent = _group(segments)

    for r in rules:
        # rules with zero children still get empty lists
        r["conditions"] = cond_by_parent.get(r["name"], [])
        r["document_no_conditions"] = docno_cond_by_parent.get(r["name"], [])
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
    """The document date the rule's legacy cut-over is compared against."""
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

    if op == "Is Set":
        return field_value.strip() != ""
    if op == "Is Not Set":
        return field_value.strip() == ""

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
            frappe.get_cached_value("Branch", branch, "custom_abbr") or ""
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
            frappe.get_cached_value(link_dt, link_value, seg.get("fetch_field")) or ""
        )

    return ""


def _peek_series(key, digits):
    """Next number for a series WITHOUT incrementing the counter (for previews)."""
    row = frappe.db.sql("select current from `tabSeries` where name=%s", key)
    current = row[0][0] if row and row[0][0] is not None else 0
    return ("%0" + str(int(digits)) + "d") % (current + 1)


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
            value = _pad_segment_value(seg, _resolve_segment(doc, seg, sep))
            resolved.append({"num": False, "value": value, "glue": glue})
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
            value = (frappe.utils.cstr(doc.get(source)).strip() or None) if source else None
            return value + get_amendment_suffix(doc) if value else None

    sep = rule.get("separator") or "/"
    resolved, has_number = _resolve_segments(doc, rule, sep)
    if not has_number:
        # pass-through: rebuilt from the same (copied) inputs, so an amendment
        # would collide with its cancelled original — the -1/-2 suffix from the
        # amended name keeps them apart, matching the legacy voucher behavior.
        # Counter rules below don't need this: an amendment draws a fresh number.
        value = _join_parts([(r["value"], r["glue"]) for r in resolved], sep)
        return value + get_amendment_suffix(doc) if value else None

    key_parts = [r["value"] for r in resolved if not r["num"] and r.get("value")]
    series_key = sep.join(key_parts) + sep
    number_len = next((r["len"] for r in resolved if r["num"]), 6)

    seq = getseries(series_key, number_len) if commit_series else _peek_series(series_key, number_len)

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
        "conditions": [
            {"field": c.field, "value": c.value}
            for c in (cfg.conditions or [])
        ],
        "document_no_conditions": [
            {"field": c.field, "value": c.value, "operator": c.get("operator")}
            for c in (cfg.get("document_no_conditions") or [])
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


@frappe.whitelist()
def get_numbering_preview_config():
    """Doctypes that have enabled Numbering Configuration rules, with the doc
    fields whose change should refresh the live number preview in the form."""
    config = {}
    for rule in frappe.get_all(
        "Numbering Configuration", filters={"enabled": 1}, pluck="name"
    ):
        cfg = frappe.get_cached_doc("Numbering Configuration", rule)
        fields = config.setdefault(cfg.document_type, set())
        fields.update(["company", "posting_date", "transaction_date", "is_return"])
        if cfg.date_field:
            fields.add(cfg.date_field)
        if cfg.legacy_source_field:
            fields.add(cfg.legacy_source_field)
        for c in cfg.conditions or []:
            if c.field:
                fields.add(c.field)
        for s in cfg.segments or []:
            if s.field:
                fields.add(s.field)
            if s.segment_type == "Branch Abbr":
                fields.add("custom_branch")
    return {dt: sorted(fields) for dt, fields in config.items()}


@frappe.whitelist()
def preview_document_number(doc):
    """Live form preview: the number the engine would assign to this (unsaved)
    document right now. Counters are peeked, never consumed."""
    data = json.loads(doc) if isinstance(doc, str) else doc
    doctype = data.get("doctype")
    if not doctype or not frappe.has_permission(doctype, "write"):
        return None

    d = frappe.get_doc(data)
    for rule in _matching_numbering_rules(d):
        target = rule.get("target_field") or "custom_branch_name"
        if not d.meta.has_field(target):
            continue
        value = _build_from_segments(d, rule, commit_series=False)
        if value:
            return {
                "target_field": target,
                "label": d.meta.get_label(target),
                "number": value,
                "rule": rule["name"],
            }
    return None


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
    new_key = sep.join(r["value"] for r in resolved if not r["num"] and r.get("value")) + sep
    if old_key == new_key:
        return

    _revert_series_if_last(old_key, old_no)
    fresh = _build_from_segments(doc, rule)
    if fresh:
        doc.set(target, fresh)


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
        return key, int(parts[num_index])

    # shape changed (e.g. a Branch Abbr that was empty is now filled): the
    # counter is the single all-digit part of the configured width.
    digit_idx = [i for i, p in enumerate(parts) if p.isdigit() and len(p) == number_len]
    if len(digit_idx) == 1:
        i = digit_idx[0]
        key = sep.join(parts[:i] + parts[i + 1:]) + sep
        return key, int(parts[i])

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
    if doc.doctype not in AUTO_NUMBER_CONFIG or not doc.meta.has_field("custom_document_no"):
        return
    # Manual numbers and amendments never consumed the counter -> never revert.
    if _is_manual_document_no(doc) or doc.get("amended_from"):
        return
    number = frappe.utils.cint(doc.get("custom_document_no"))
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
    if doc.is_new():
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
    if doc.is_new():
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
    if doc.is_new():
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
