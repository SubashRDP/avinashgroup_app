import frappe
from frappe import _
from frappe.utils.caching import request_cache
from datetime import datetime

# Transaction doctypes that need fiscal year filtering
FILTERED_DOCTYPES = {
    "Sales Invoice",
    "Sales Order",
    "Quotation",
    "Delivery Note",
    "Purchase Invoice",
    "Purchase Order",
    "Request for Quotation",
    "Supplier Quotation",
    "Material Request",
    "Stock Entry",
    "Stock Reconciliation",
    "Journal Entry",
    "Payment Entry",
    "Attendance",
}

# Date field to use for filtering (most transactions use posting_date)
DATE_FIELD_MAP = {
    "Attendance": "attendance_date",
    "Quotation": "transaction_date",
    "Sales Order": "transaction_date",
    "Delivery Note": "posting_date",
    "Purchase Order": "transaction_date",
    "Request for Quotation": "transaction_date",
    "Stock Entry": "posting_date",
    "Stock Reconciliation": "posting_date",
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
        user_doc = frappe.get_cached_doc("User", user)
    except Exception:
        return {}

    # If user has global full access, return special marker
    if user_doc.get("full_access"):
        return {"__full_access__": True}

    # Get all rows from user_fiscal_years child table
    access_map = {}
    for row in user_doc.get("user_fiscal_years", []):
        doctype_name = row.get("doctype_name")
        if not doctype_name:
            continue

        if row.get("full_access"):
            # Full access for this doctype → all fiscal years allowed
            access_map.setdefault(doctype_name, []).append({
                "full_access": True
            })
        else:
            # Specific fiscal year
            fiscal_year = row.get("fiscal_year")
            if fiscal_year:
                access_map.setdefault(doctype_name, []).append({
                    "fiscal_year": fiscal_year,
                    "full_access": False
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

    # Check if user is Administrator - admins bypass filtering
    if frappe.db.get_value("User", user, "user_type") == "System User":
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

    # Check if user is Administrator
    if frappe.db.get_value("User", user, "user_type") == "System User":
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
