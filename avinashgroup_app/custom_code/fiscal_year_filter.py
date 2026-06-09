import frappe
import frappe.client
from frappe import _
from frappe.utils.caching import request_cache
from datetime import datetime, date

# Submittable transaction doctypes with a fiscal-year date field.
FILTERED_DOCTYPES = (
    "Additional Salary",
    "Appraisal",
    "Asset Capitalization",
    "Asset Movement",
    "Asset Value Adjustment",
    "Attendance",
    "Attendance Fix",
    "Attendance Request",
    "Bank Guarantee",
    "Bank Transaction",
    "Blanket Order",
    "Cashier Closing",
    "Closing Stock Balance",
    "Contract",
    "Delivery Note",
    "Dunning",
    "Employee Advance",
    "Employee Benefit Application",
    "Employee Grievance",
    "Employee Referral",
    "Exchange Rate Revaluation",
    "Exit Interview",
    "Expense Claim",
    "Full and Final Statement",
    "Gratuity",
    "Invoice Discounting",
    "Job Card",
    "Journal Entry",
    "Landed Cost Voucher",
    "Leave Adjustment",
    "Leave Allocation",
    "Leave Application",
    "Leave Encashment",
    "Leave Ledger Entry",
    "Maintenance Schedule",
    "Material Request",
    "Overtime Slip",
    "POS Closing Entry",
    "POS Invoice",
    "POS Invoice Merge Log",
    "POS Opening Entry",
    "Payment Entry",
    "Payment Order",
    "Payment Request",
    "Payroll Entry",
    "Period Closing Voucher",
    "Process Deferred Accounting",
    "Process Subscription",
    "Production Plan",
    "Project Update",
    "Purchase Invoice",
    "Purchase Order",
    "Purchase Receipt",
    "Quotation",
    "Repost Item Valuation",
    "Repost Payment Ledger",
    "Request for Quotation",
    "Salary Slip",
    "Salary Structure Assignment",
    "Salary Withholding",
    "Sales Invoice",
    "Sales Order",
    "Serial and Batch Bundle",
    "Share Transfer",
    "Shift Assignment",
    "Shift Request",
    "Staffing Plan",
    "Stock Entry",
    "Stock Reconciliation",
    "Subcontracting Order",
    "Subcontracting Receipt",
    "Supplier Quotation",
    "Supplier Scorecard Period",
    "Timesheet",
    "Vehicle Log",
)


def _is_admin(user):
    """Check if user should bypass fiscal-year filtering."""
    if not user or user == "Guest":
        return False
    if user == "Administrator":
        return True
    try:
        result = frappe.db.sql("""
            SELECT role FROM tabUserRole WHERE parent = %s AND role = 'System Manager'
            LIMIT 1
        """, (user,))
        return bool(result)
    except Exception:
        return False


DATE_FIELD_MAP = {
    "Additional Salary": "from_date",
    "Appraisal": "start_date",
    "Asset Capitalization": "posting_date",
    "Asset Movement": "transaction_date",
    "Asset Value Adjustment": "date",
    "Attendance": "attendance_date",
    "Attendance Fix": "from_date",
    "Attendance Request": "from_date",
    "Bank Guarantee": "start_date",
    "Bank Transaction": "date",
    "Blanket Order": "from_date",
    "Cashier Closing": "date",
    "Closing Stock Balance": "from_date",
    "Contract": "start_date",
    "Delivery Note": "posting_date",
    "Dunning": "posting_date",
    "Employee Advance": "posting_date",
    "Employee Benefit Application": "date",
    "Employee Grievance": "date",
    "Employee Referral": "date",
    "Exchange Rate Revaluation": "posting_date",
    "Exit Interview": "date",
    "Expense Claim": "posting_date",
    "Full and Final Statement": "transaction_date",
    "Gratuity": "posting_date",
    "Invoice Discounting": "posting_date",
    "Job Card": "posting_date",
    "Journal Entry": "posting_date",
    "Landed Cost Voucher": "posting_date",
    "Leave Adjustment": "posting_date",
    "Leave Allocation": "from_date",
    "Leave Application": "posting_date",
    "Leave Encashment": "posting_date",
    "Leave Ledger Entry": "from_date",
    "Maintenance Schedule": "transaction_date",
    "Material Request": "transaction_date",
    "Overtime Slip": "posting_date",
    "POS Closing Entry": "posting_date",
    "POS Invoice": "posting_date",
    "POS Invoice Merge Log": "posting_date",
    "POS Opening Entry": "posting_date",
    "Payment Entry": "posting_date",
    "Payment Order": "posting_date",
    "Payment Request": "transaction_date",
    "Payroll Entry": "posting_date",
    "Period Closing Voucher": "transaction_date",
    "Process Deferred Accounting": "posting_date",
    "Process Subscription": "posting_date",
    "Production Plan": "posting_date",
    "Project Update": "date",
    "Purchase Invoice": "posting_date",
    "Purchase Order": "transaction_date",
    "Purchase Receipt": "posting_date",
    "Quotation": "transaction_date",
    "Repost Item Valuation": "posting_date",
    "Repost Payment Ledger": "posting_date",
    "Request for Quotation": "transaction_date",
    "Salary Slip": "posting_date",
    "Salary Structure Assignment": "from_date",
    "Salary Withholding": "posting_date",
    "Sales Invoice": "posting_date",
    "Sales Order": "transaction_date",
    "Serial and Batch Bundle": "posting_date",
    "Share Transfer": "date",
    "Shift Assignment": "start_date",
    "Shift Request": "from_date",
    "Staffing Plan": "from_date",
    "Stock Entry": "posting_date",
    "Stock Reconciliation": "posting_date",
    "Subcontracting Order": "transaction_date",
    "Subcontracting Receipt": "posting_date",
    "Supplier Quotation": "transaction_date",
    "Supplier Scorecard Period": "start_date",
    "Timesheet": "start_date",
    "Vehicle Log": "date",
}


def _parse_date(date_obj):
    """Convert date object or string to date. Returns None if conversion fails."""
    if date_obj is None:
        return None
    if isinstance(date_obj, date):
        return date_obj
    if isinstance(date_obj, str):
        try:
            return datetime.strptime(date_obj, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None


@request_cache
def _get_user_fiscal_access(user):
    """
    Get all fiscal year access rules for a user.
    Returns dict: {doctype_name: [{"fiscal_year": "...", "full_access": bool}]}
    If no restriction record exists, returns {"__full_access__": True} (default allow all).
    """
    if not user or user == "Guest":
        return {"__full_access__": True}

    try:
        access_doc = frappe.db.sql(
            """
            SELECT name, full_access
            FROM `tabFiscal Year Access Control`
            WHERE user = %s
            LIMIT 1
            """,
            (user,),
            as_dict=True,
        )
    except Exception:
        return _get_legacy_user_fiscal_access(user)

    if not access_doc:
        return {"__full_access__": True}

    access_doc = access_doc[0]
    if access_doc.get("full_access"):
        return {"__full_access__": True}

    access_map = {}
    rows = frappe.db.sql(
        """
        SELECT doctype_name, fiscal_year, full_access
        FROM `tabUser Fiscal Year Access`
        WHERE parenttype = 'Fiscal Year Access Control'
            AND parentfield = 'access_details'
            AND parent = %s
        ORDER BY idx
        """,
        (access_doc.name,),
        as_dict=True,
    )

    for row in rows:
        doctype_name = row.get("doctype_name")
        if not doctype_name:
            continue
        # Row-level full access = all fiscal years for this doctype.
        if row.get("full_access"):
            access_map[doctype_name] = "__full_access__"
            continue
        # A doctype already granted full access can't be narrowed by another row.
        if access_map.get(doctype_name) == "__full_access__":
            continue
        fiscal_year = row.get("fiscal_year")
        if fiscal_year:
            access_map.setdefault(doctype_name, []).append({"fiscal_year": fiscal_year})

    return access_map


def _get_legacy_user_fiscal_access(user):
    """Temporary fallback for sites that have not run the migration patch yet.
    If no restriction record exists, returns full access (default allow).
    """
    try:
        full_access = frappe.db.get_value("User", user, "full_access")
    except Exception:
        return {"__full_access__": True}

    if full_access:
        return {"__full_access__": True}

    try:
        rows = frappe.db.sql(
            """
            SELECT doctype_name, fiscal_year, full_access
            FROM `tabUser Fiscal Year Access`
            WHERE parenttype = 'User'
                AND parentfield = 'user_fiscal_years'
                AND parent = %s
            ORDER BY idx
            """,
            (user,),
            as_dict=True,
        )
    except Exception:
        return {"__full_access__": True}

    access_map = {}
    for row in rows:
        doctype_name = row.get("doctype_name")
        if not doctype_name:
            continue
        if row.get("full_access"):
            access_map[doctype_name] = "__full_access__"
            continue
        if access_map.get(doctype_name) == "__full_access__":
            continue
        fiscal_year = row.get("fiscal_year")
        if fiscal_year:
            access_map.setdefault(doctype_name, []).append({"fiscal_year": fiscal_year})

    return access_map if access_map else {"__full_access__": True}


@request_cache
def _get_fiscal_year_dates(fiscal_year_name):
    """Get from_date and to_date for a fiscal year."""
    if not fiscal_year_name:
        return None, None
    try:
        fy = frappe.get_cached_doc("Fiscal Year", fiscal_year_name)
        return fy.year_start_date, fy.year_end_date
    except Exception:
        return None, None


def _has_doctype_access(doctype, access_map):
    """Check if user has any access to a doctype. Returns access list or None."""
    if access_map.get("__full_access__"):
        return "__full_access__"
    return access_map.get(doctype)


def _check_has_full_access_for_doctype(doctype_access):
    """Check if user has unrestricted access (no restriction record)."""
    return doctype_access == "__full_access__"


def _build_date_ranges(doctype_access):
    """Extract date ranges from doctype access rules."""
    if doctype_access == "__full_access__":
        return []
    date_ranges = []
    for rule in (doctype_access or []):
        fiscal_year = rule.get("fiscal_year")
        if fiscal_year:
            from_date, to_date = _get_fiscal_year_dates(fiscal_year)
            if from_date and to_date:
                date_ranges.append((from_date, to_date))
    return date_ranges


def apply_fiscal_year_filter_to_list(doctype, filters=None, **kwargs):
    """Hook for list view filtering. Modifies filters to include fiscal year restrictions."""
    if doctype not in FILTERED_DOCTYPES:
        return

    user = frappe.session.user
    if _is_admin(user):
        return

    access_map = _get_user_fiscal_access(user)
    doctype_access = _has_doctype_access(doctype, access_map)

    if not doctype_access:
        if filters is None:
            filters = []
        filters.append([doctype, "name", "=", None])
        return

    if _check_has_full_access_for_doctype(doctype_access):
        return

    date_ranges = _build_date_ranges(doctype_access)
    if not date_ranges:
        if filters is None:
            filters = []
        filters.append([doctype, "name", "=", None])
        return

    date_field = DATE_FIELD_MAP.get(doctype, "posting_date")
    if filters is None:
        filters = []

    if len(date_ranges) == 1:
        from_date, to_date = date_ranges[0]
        filters.append([doctype, date_field, ">=", from_date])
        filters.append([doctype, date_field, "<=", to_date])
    else:
        or_filters = []
        for from_date, to_date in date_ranges:
            or_filters.append([date_field, ">=", from_date])
            or_filters.append([date_field, "<=", to_date])
            or_filters.append("or")
        if or_filters and or_filters[-1] == "or":
            or_filters.pop()
        if or_filters:
            filters.append(or_filters)


def validate_fiscal_year_access(doc, method=None):
    """Validate that user has access to this document's fiscal year."""
    if doc.doctype not in FILTERED_DOCTYPES:
        return

    user = frappe.session.user
    if _is_admin(user):
        return

    access_map = _get_user_fiscal_access(user)
    doctype_access = _has_doctype_access(doc.doctype, access_map)

    if not doctype_access:
        frappe.throw(_("You do not have access to {0}").format(doc.doctype),
                     title=_("Access Denied"))

    if _check_has_full_access_for_doctype(doctype_access):
        return

    date_field = DATE_FIELD_MAP.get(doc.doctype, "posting_date")
    doc_date = getattr(doc, date_field, None)
    doc_date = _parse_date(doc_date)

    if not doc_date:
        return

    for rule in (doctype_access or []):
        fiscal_year = rule.get("fiscal_year")
        if fiscal_year:
            from_date, to_date = _get_fiscal_year_dates(fiscal_year)
            if from_date and to_date:
                from_date = _parse_date(from_date)
                to_date = _parse_date(to_date)
                if from_date and to_date and from_date <= doc_date <= to_date:
                    return

    frappe.throw(
        _("Document date ({0}) is outside your allowed fiscal year ranges.").format(doc_date),
        title=_("Fiscal Year Access Denied")
    )


def clear_user_fiscal_cache(doc, method=None):
    """Called when User is saved/updated."""
    frappe.cache().delete_value(f"_get_user_fiscal_access_{doc.name}")


@frappe.whitelist()
def get_user_fiscal_access(user=None):
    """Whitelist method to get user's fiscal year access - for debugging."""
    if not user:
        user = frappe.session.user
    return _get_user_fiscal_access(user)


def _build_query_conditions(doctype, user):
    """
    Build SQL WHERE clause for list view filtering.
    Returns a string used by Frappe's permission_query_conditions hook.
    Empty string = no restriction. "1=0" = no rows.
    """
    if not user:
        user = frappe.session.user

    if _is_admin(user):
        return ""

    access_map = _get_user_fiscal_access(user)
    doctype_access = _has_doctype_access(doctype, access_map)

    if not doctype_access:
        return "1=0"

    if _check_has_full_access_for_doctype(doctype_access):
        return ""

    date_ranges = _build_date_ranges(doctype_access)
    if not date_ranges:
        return "1=0"

    date_field = DATE_FIELD_MAP.get(doctype, "posting_date")
    table_name = f"`tab{doctype}`"

    # permission_query_conditions must return a SQL *string*; inline the
    # (escaped) dates rather than executing a query.
    conditions = []
    for from_date, to_date in date_ranges:
        fd = frappe.db.escape(str(from_date))
        td = frappe.db.escape(str(to_date))
        conditions.append(f"({table_name}.`{date_field}` BETWEEN {fd} AND {td})")

    if not conditions:
        return "1=0"

    return "(" + " OR ".join(conditions) + ")"


def _make_query_conditions_for(doctype):
    """Factory to create per-doctype permission_query_conditions function."""
    def query_conditions(user=None):
        return _build_query_conditions(doctype, user)
    query_conditions.__name__ = f"query_conditions_{doctype.replace(' ', '_').lower()}"
    return query_conditions


for _dt in FILTERED_DOCTYPES:
    _func_name = f"query_conditions_{_dt.replace(' ', '_').lower()}"
    globals()[_func_name] = _make_query_conditions_for(_dt)


def has_fiscal_year_permission(doc, ptype=None, user=None):
    """has_permission hook: check if user has access to this document based on fiscal year assignments."""
    if not user:
        user = frappe.session.user

    if _is_admin(user):
        return True

    doctype = getattr(doc, "doctype", None) or (doc.get("doctype") if isinstance(doc, dict) else None)
    if not doctype or doctype not in FILTERED_DOCTYPES:
        return True

    access_map = _get_user_fiscal_access(user)
    doctype_access = _has_doctype_access(doctype, access_map)

    if not doctype_access:
        return False

    if _check_has_full_access_for_doctype(doctype_access):
        return True

    date_field = DATE_FIELD_MAP.get(doctype, "posting_date")
    doc_date = getattr(doc, date_field, None) if not isinstance(doc, dict) else doc.get(date_field)
    doc_date = _parse_date(doc_date)

    if not doc_date:
        return True

    for rule in (doctype_access or []):
        fiscal_year = rule.get("fiscal_year")
        if fiscal_year:
            from_date, to_date = _get_fiscal_year_dates(fiscal_year)
            if from_date and to_date:
                from_date = _parse_date(from_date)
                to_date = _parse_date(to_date)
                if from_date and to_date and from_date <= doc_date <= to_date:
                    return True

    return False


@frappe.whitelist(allow_guest=False)
def filtered_get_list(doctype, *args, **kwargs):
    """Override for frappe.client.get_list to apply fiscal year filtering."""
    kwargs.pop('cmd', None)
    if doctype not in FILTERED_DOCTYPES:
        return frappe.client.get_list(doctype, **kwargs)

    user = frappe.session.user
    if _is_admin(user):
        return frappe.client.get_list(doctype, **kwargs)

    access_map = _get_user_fiscal_access(user)
    doctype_access = _has_doctype_access(doctype, access_map)

    if not doctype_access:
        return []

    if _check_has_full_access_for_doctype(doctype_access):
        return frappe.client.get_list(doctype, **kwargs)

    date_ranges = _build_date_ranges(doctype_access)
    if not date_ranges:
        return []

    date_field = DATE_FIELD_MAP.get(doctype, "posting_date")
    filters = kwargs.get("filters", []) or []
    if isinstance(filters, dict):
        filters = list(filters.items()) if filters else []

    if len(date_ranges) == 1:
        from_date, to_date = date_ranges[0]
        filters.append([doctype, date_field, ">=", from_date])
        filters.append([doctype, date_field, "<=", to_date])
    else:
        or_filters = []
        for from_date, to_date in date_ranges:
            or_filters.append([[doctype, date_field, ">=", from_date], [doctype, date_field, "<=", to_date]])
        filters.append(or_filters)

    kwargs["filters"] = filters
    return frappe.client.get_list(doctype, **kwargs)
