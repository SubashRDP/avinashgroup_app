import frappe
from frappe import _
from frappe.utils.caching import request_cache
from datetime import datetime

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


@request_cache
def _get_user_fiscal_access(user):
    """
    Get all fiscal year access rules for a user.
    Returns dict: {doctype_name: [{"fiscal_year": "...", "full_access": bool}]}
    """
    if not user or user == "Guest":
        return {}

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
        return {}

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

        if row.get("full_access"):
            access_map.setdefault(doctype_name, []).append({
                "full_access": True
            })
        else:
            fiscal_year = row.get("fiscal_year")
            if fiscal_year:
                access_map.setdefault(doctype_name, []).append({
                    "fiscal_year": fiscal_year,
                    "full_access": False
                })

    return access_map


def _get_legacy_user_fiscal_access(user):
    """Temporary fallback for sites that have not run the migration patch yet."""
    try:
        full_access = frappe.db.get_value("User", user, "full_access")
    except Exception:
        return {}

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
        return {}

    access_map = {}
    for row in rows:
        doctype_name = row.get("doctype_name")
        if not doctype_name:
            continue

        if row.get("full_access"):
            access_map.setdefault(doctype_name, []).append({"full_access": True})
            continue

        fiscal_year = row.get("fiscal_year")
        if fiscal_year:
            access_map.setdefault(doctype_name, []).append({
                "fiscal_year": fiscal_year,
                "full_access": False,
            })

    return access_map


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


def apply_fiscal_year_filter_to_list(doctype, filters=None, **kwargs):
    """
    Hook for list view filtering. Modifies filters to include fiscal year restrictions.
    This is called from frappe's list filtering system.
    """
    if doctype not in FILTERED_DOCTYPES:
        return

    user = frappe.session.user

    # Check if user is System Manager - admins bypass filtering
    if _is_admin(user):
        return

    access_map = _get_user_fiscal_access(user)

    # Check for global full access
    if access_map.get("__full_access__"):
        return

    doctype_access = access_map.get(doctype, [])

    if not doctype_access:
        # User has no access to this doctype - add filter that returns no results
        if filters is None:
            filters = []
        filters.append([doctype, "name", "=", None])
        return

    # Check if user has full access for this doctype
    for rule in doctype_access:
        if rule.get("full_access"):
            return  # No filter needed

    # Build date ranges from fiscal years
    date_ranges = []
    for rule in doctype_access:
        fiscal_year = rule.get("fiscal_year")
        if fiscal_year:
            from_date, to_date = _get_fiscal_year_dates(fiscal_year)
            if from_date and to_date:
                date_ranges.append((from_date, to_date))

    if not date_ranges:
        # No valid date ranges configured
        if filters is None:
            filters = []
        filters.append([doctype, "name", "=", None])
        return

    # Build OR filter for all date ranges
    date_field = DATE_FIELD_MAP.get(doctype, "posting_date")

    if filters is None:
        filters = []

    # Handle single vs multiple date ranges
    if len(date_ranges) == 1:
        from_date, to_date = date_ranges[0]
        filters.append([doctype, date_field, ">=", from_date])
        filters.append([doctype, date_field, "<=", to_date])
    else:
        # Multiple fiscal years - use OR condition
        or_filters = []
        for from_date, to_date in date_ranges:
            or_filters.append([date_field, ">=", from_date])
            or_filters.append([date_field, "<=", to_date])
            or_filters.append("or")
        # Remove last "or"
        if or_filters and or_filters[-1] == "or":
            or_filters.pop()
        if or_filters:
            filters.append(or_filters)


def validate_fiscal_year_access(doc, method=None):
    """Validate that user has access to this document's fiscal year."""
    if doc.doctype not in FILTERED_DOCTYPES:
        return

    user = frappe.session.user

    # Check if user is System Manager - admins bypass filtering
    if _is_admin(user):
        return

    access_map = _get_user_fiscal_access(user)

    # Check for global full access
    if access_map.get("__full_access__"):
        return

    doctype_access = access_map.get(doc.doctype, [])

    if not doctype_access:
        frappe.throw(_("You do not have access to {0}").format(doc.doctype),
                     title=_("Access Denied"))

    # Check if user has full access for this doctype
    for rule in doctype_access:
        if rule.get("full_access"):
            return

    # Check if document date is within allowed fiscal years
    date_field = DATE_FIELD_MAP.get(doc.doctype, "posting_date")
    doc_date = getattr(doc, date_field, None)

    if not doc_date:
        return  # No date to validate

    # Convert to date if needed
    if isinstance(doc_date, str):
        try:
            doc_date = datetime.strptime(doc_date, "%Y-%m-%d").date()
        except:
            return

    # Check if date is in any allowed fiscal year
    for rule in doctype_access:
        fiscal_year = rule.get("fiscal_year")
        if fiscal_year:
            from_date, to_date = _get_fiscal_year_dates(fiscal_year)
            if from_date and to_date:
                # Handle date comparisons
                if isinstance(from_date, str):
                    from_date = datetime.strptime(from_date, "%Y-%m-%d").date()
                if isinstance(to_date, str):
                    to_date = datetime.strptime(to_date, "%Y-%m-%d").date()

                if from_date <= doc_date <= to_date:
                    return  # Found matching fiscal year

    frappe.throw(
        _("Document date ({0}) is outside your allowed fiscal year ranges.").format(doc_date),
        title=_("Fiscal Year Access Denied")
    )


def clear_user_fiscal_cache(doc, method=None):
    """Called when User is saved/updated."""
    cache_key = f"user_fiscal_access_{doc.name}"
    frappe.cache().delete_value(cache_key)


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

    if access_map.get("__full_access__"):
        return ""

    doctype_access = access_map.get(doctype, [])

    if not doctype_access:
        return "1=0"

    # Full access for this doctype
    for rule in doctype_access:
        if rule.get("full_access"):
            return ""

    date_field = DATE_FIELD_MAP.get(doctype, "posting_date")
    table_name = f"`tab{doctype}`"

    conditions = []
    for rule in doctype_access:
        fiscal_year = rule.get("fiscal_year")
        if fiscal_year:
            from_date, to_date = _get_fiscal_year_dates(fiscal_year)
            if from_date and to_date:
                conditions.append(
                    f"({table_name}.`{date_field}` BETWEEN '{from_date}' AND '{to_date}')"
                )

    if not conditions:
        return "1=0"

    return "(" + " OR ".join(conditions) + ")"


def _make_query_conditions_for(doctype):
    """Factory to create per-doctype permission_query_conditions function."""
    def query_conditions(user=None):
        return _build_query_conditions(doctype, user)
    query_conditions.__name__ = f"query_conditions_{doctype.replace(' ', '_').lower()}"
    return query_conditions


# Dynamically generate one function per filtered doctype, registered at module level
# so hooks.py can reference them as
# avinashgroup_app.custom_code.fiscal_year_filter.query_conditions_<doctype>
for _dt in FILTERED_DOCTYPES:
    _func_name = f"query_conditions_{_dt.replace(' ', '_').lower()}"
    globals()[_func_name] = _make_query_conditions_for(_dt)


def has_fiscal_year_permission(doc, ptype=None, user=None):
    """
    has_permission hook: check if user has access to this document
    based on fiscal year assignments.
    """
    if not user:
        user = frappe.session.user

    if _is_admin(user):
        return True

    # Resolve doctype from doc (can be Document object or dict)
    doctype = getattr(doc, "doctype", None) or (doc.get("doctype") if isinstance(doc, dict) else None)
    if not doctype or doctype not in FILTERED_DOCTYPES:
        return True

    access_map = _get_user_fiscal_access(user)

    if access_map.get("__full_access__"):
        return True

    doctype_access = access_map.get(doctype, [])

    if not doctype_access:
        return False

    for rule in doctype_access:
        if rule.get("full_access"):
            return True

    date_field = DATE_FIELD_MAP.get(doctype, "posting_date")
    doc_date = getattr(doc, date_field, None) if not isinstance(doc, dict) else doc.get(date_field)

    if not doc_date:
        return True

    if isinstance(doc_date, str):
        try:
            doc_date = datetime.strptime(doc_date, "%Y-%m-%d").date()
        except Exception:
            return True

    for rule in doctype_access:
        fiscal_year = rule.get("fiscal_year")
        if fiscal_year:
            from_date, to_date = _get_fiscal_year_dates(fiscal_year)
            if from_date and to_date:
                if isinstance(from_date, str):
                    from_date = datetime.strptime(from_date, "%Y-%m-%d").date()
                if isinstance(to_date, str):
                    to_date = datetime.strptime(to_date, "%Y-%m-%d").date()
                if from_date <= doc_date <= to_date:
                    return True

    return False


@frappe.whitelist(allow_guest=False)
def filtered_get_list(doctype, *args, **kwargs):
    """
    Override for frappe.client.get_list to apply fiscal year filtering.
    This is called before the original get_list method.
    """
    if doctype not in FILTERED_DOCTYPES:
        # Not a filtered doctype, call original method
        return frappe.call("frappe.client.get_list", args={"doctype": doctype, **kwargs}, async_=False)

    user = frappe.session.user

    # Check if user is System Manager - admins bypass filtering
    if _is_admin(user):
        return frappe.call("frappe.client.get_list", args={"doctype": doctype, **kwargs}, async_=False)

    access_map = _get_user_fiscal_access(user)

    # Check for global full access
    if access_map.get("__full_access__"):
        return frappe.call("frappe.client.get_list", args={"doctype": doctype, **kwargs}, async_=False)

    doctype_access = access_map.get(doctype, [])

    if not doctype_access:
        # User has no access to this doctype
        return []

    # Check if user has full access for this doctype
    for rule in doctype_access:
        if rule.get("full_access"):
            return frappe.call("frappe.client.get_list", args={"doctype": doctype, **kwargs}, async_=False)

    # Build date ranges from fiscal years
    date_ranges = []
    for rule in doctype_access:
        fiscal_year = rule.get("fiscal_year")
        if fiscal_year:
            from_date, to_date = _get_fiscal_year_dates(fiscal_year)
            if from_date and to_date:
                date_ranges.append((from_date, to_date))

    if not date_ranges:
        return []

    # Add date range filters to kwargs
    date_field = DATE_FIELD_MAP.get(doctype, "posting_date")

    # Get existing filters
    filters = kwargs.get("filters", [])
    if not filters:
        filters = []
    elif isinstance(filters, dict):
        filters = list(filters.items()) if filters else []

    # Add date range filters
    if len(date_ranges) == 1:
        from_date, to_date = date_ranges[0]
        filters.append([doctype, date_field, ">=", from_date])
        filters.append([doctype, date_field, "<=", to_date])
    else:
        # Multiple date ranges
        or_filters = []
        for from_date, to_date in date_ranges:
            or_filters.append([[doctype, date_field, ">=", from_date], [doctype, date_field, "<=", to_date]])
        filters.append(or_filters)

    kwargs["filters"] = filters

    # Call original get_list with modified filters
    return frappe.call("frappe.client.get_list", args={"doctype": doctype, **kwargs}, async_=False)
