



import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {
            "fieldname": "vehicle_no",
            "label": _("Vehicle No"),
            "fieldtype": "Link",
            "options": "Sub-Ledger Category",
            "width": 180
        },
        {
            "fieldname": "fuel",
            "label": _("Fuel"),
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "fieldname": "repair",
            "label": _("Repair"),
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "fieldname": "others",
            "label": _("Others"),
            "fieldtype": "Currency",
            "width": 200
        }
    ]

def get_data(filters):
    """
    Fetch and combine expenses from Purchase Invoice and Journal Entry
    """
    filters = filters or {}
    
    # Prepare filter values
    filter_values = prepare_filter_values(filters)
    
    # Build conditions
    conditions_pi = build_conditions(filter_values, "pi", "pic")
    conditions_je = build_conditions(filter_values, "je", "jea")
    
    query = """
        SELECT
            vehicle_no,
            SUM(fuel) AS fuel,
            SUM(repair) AS repair,
            SUM(others) AS others
        FROM (
            -- Purchase Invoice Expenses
            SELECT
                pic.custom_subtype AS vehicle_no,
                SUM(CASE WHEN acc.account_name LIKE '%%Fuel Expenses%%'
                        THEN pic.amount ELSE 0 END) AS fuel,
                SUM(CASE WHEN acc.account_name LIKE '%%R & M - Vehicles%%'
                        THEN pic.amount ELSE 0 END) AS repair,
                SUM(CASE WHEN acc.account_name LIKE '%%Other Vehicle Expenses%%'
                        THEN pic.amount ELSE 0 END) AS others
            FROM
                `tabPurchase Invoice` pi
                JOIN `tabPurchase Invoice Item` pic ON pi.name = pic.parent
                JOIN `tabAccount` acc ON acc.name = pic.expense_account
            WHERE
                pi.docstatus = 1
                AND (
                    acc.account_name LIKE '%%Fuel Expenses%%'
                    OR acc.account_name LIKE '%%R & M - Vehicles%%'
                    OR acc.account_name LIKE '%%Other Vehicle Expenses%%'
                )
                {conditions_pi}
            GROUP BY pic.custom_subtype

            UNION ALL

            -- Journal Entry Expenses
            SELECT
                jea.custom_subtype AS vehicle_no,
                SUM(CASE WHEN acc.account_name LIKE '%%Fuel Expenses%%'
                        THEN jea.debit - jea.credit ELSE 0 END) AS fuel,
                SUM(CASE WHEN acc.account_name LIKE '%%R & M - Vehicles%%'
                        THEN jea.debit - jea.credit ELSE 0 END) AS repair,
                SUM(CASE WHEN acc.account_name LIKE '%%Other Vehicle Expenses%%'
                        THEN jea.debit - jea.credit ELSE 0 END) AS others
            FROM
                `tabJournal Entry` je
                INNER JOIN `tabJournal Entry Account` jea ON je.name = jea.parent
                JOIN `tabAccount` acc ON acc.name = jea.account
            WHERE
                je.docstatus = 1
                AND (
                    acc.account_name LIKE '%%Fuel Expenses%%'
                    OR acc.account_name LIKE '%%R & M - Vehicles%%'
                    OR acc.account_name LIKE '%%Other Vehicle Expenses%%'
                )
                {conditions_je}
            GROUP BY jea.custom_subtype
        ) AS combined
        WHERE vehicle_no IS NOT NULL AND vehicle_no != ''
        GROUP BY vehicle_no
        ORDER BY vehicle_no
    """.format(conditions_pi=conditions_pi, conditions_je=conditions_je)

    return frappe.db.sql(query, filter_values, as_dict=True)

def prepare_filter_values(filters):
    """Prepare all filter values with a single DB call per filter type"""
    filter_values = filters.copy()

    # Handle fiscal year filter
    if filters.get("fiscal_year"):
        fiscal_data = frappe.get_value(
            "Fiscal Year",
            filters.get("fiscal_year"),
            ["year_start_date", "year_end_date"],
            as_dict=True
        )
        if fiscal_data:
            filter_values["fiscal_start"] = fiscal_data["year_start_date"]
            filter_values["fiscal_end"] = fiscal_data["year_end_date"]
        else:
                   frappe.throw(
                _("Fiscal Year {0} not found or is invalid. Please select a valid fiscal year.").format(
                    frappe.bold(filters.get("fiscal_year"))
                ),
                title=_("Invalid Fiscal Year")
            )
    
    return filter_values

def build_conditions(filter_values, doc_prefix, child_prefix):
    """Build WHERE conditions using pre-fetched filter values"""
    conditions = ""

    # Company is taken from the matched Account's own company field, so each
    # company only ever sees its own expense accounts (works for NGK, NGI and
    # any other company without hardcoding account names/abbreviations).
    if filter_values.get("company"):
        conditions += " AND acc.company = %(company)s"

    if filter_values.get("fiscal_start"):
        conditions += f" AND {doc_prefix}.posting_date >= %(fiscal_start)s"
        conditions += f" AND {doc_prefix}.posting_date <= %(fiscal_end)s"
    
    if filter_values.get("period_start_date"):
        conditions += f" AND {doc_prefix}.posting_date >= %(period_start_date)s"
    
    if filter_values.get("period_end_date"):
        conditions += f" AND {doc_prefix}.posting_date <= %(period_end_date)s"
    
    if filter_values.get("vehicle_no"):
        conditions += f" AND {child_prefix}.custom_subtype = %(vehicle_no)s"
    
    return conditions