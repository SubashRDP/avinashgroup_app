



import frappe
from frappe import _

# The three expense categories are matched by the SAME substring `like`
# patterns that the SQL used to embed as leading-wildcard LIKEs.  Resolving
# the matching Account names ONCE (below) lets the SQL use indexed IN lookups
# instead of re-running non-sargable `account_name LIKE '%...%'` up to 4x per
# matched row, while keeping membership byte-for-byte identical.
EXPENSE_ACCOUNT_PATTERNS = {
    "fuel": "%Fuel Expenses%",
    "repair": "%R & M - Vehicles%",
    "others": "%Other Vehicle Expenses%",
}

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {
            "fieldname": "vehicle_no",
            "label": _("Vehicle No"),
            "fieldtype": "Data",
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

    # Resolve the matching Account names ONCE (indexed IN instead of scan LIKE).
    # Adds the per-category tuples + the combined tuple onto filter_values so
    # they get bound as %(...)s params below.
    resolve_expense_accounts(filter_values)

    # Build conditions
    conditions_pi = build_conditions(filter_values, "pi", "pic")
    conditions_je = build_conditions(filter_values, "je", "jea")

    query = """
        SELECT
            combined.vehicle AS vehicle,
            COALESCE(v.license_plate, combined.vehicle) AS vehicle_no,
            SUM(combined.fuel) AS fuel,
            SUM(combined.repair) AS repair,
            SUM(combined.others) AS others
        FROM (
            -- Purchase Invoice Expenses
            SELECT
                pic.custom_subtype AS vehicle,
                SUM(CASE WHEN acc.name IN %(fuel_accounts)s
                        THEN pic.amount ELSE 0 END) AS fuel,
                SUM(CASE WHEN acc.name IN %(repair_accounts)s
                        THEN pic.amount ELSE 0 END) AS repair,
                SUM(CASE WHEN acc.name IN %(others_accounts)s
                        THEN pic.amount ELSE 0 END) AS others
            FROM
                `tabPurchase Invoice` pi
                JOIN `tabPurchase Invoice Item` pic ON pi.name = pic.parent
                JOIN `tabAccount` acc ON acc.name = pic.expense_account
            WHERE
                pi.docstatus = 1
                AND acc.name IN %(all_expense_accounts)s
                {conditions_pi}
            GROUP BY pic.custom_subtype

            UNION ALL

            -- Journal Entry Expenses
            SELECT
                jea.custom_subtype AS vehicle,
                SUM(CASE WHEN acc.name IN %(fuel_accounts)s
                        THEN jea.debit - jea.credit ELSE 0 END) AS fuel,
                SUM(CASE WHEN acc.name IN %(repair_accounts)s
                        THEN jea.debit - jea.credit ELSE 0 END) AS repair,
                SUM(CASE WHEN acc.name IN %(others_accounts)s
                        THEN jea.debit - jea.credit ELSE 0 END) AS others
            FROM
                `tabJournal Entry` je
                INNER JOIN `tabJournal Entry Account` jea ON je.name = jea.parent
                JOIN `tabAccount` acc ON acc.name = jea.account
            WHERE
                je.docstatus = 1
                AND acc.name IN %(all_expense_accounts)s
                {conditions_je}
            GROUP BY jea.custom_subtype
        ) AS combined
        LEFT JOIN `tabVehicle` v ON v.name = combined.vehicle
        WHERE combined.vehicle IS NOT NULL AND combined.vehicle != ''
        GROUP BY combined.vehicle, COALESCE(v.license_plate, combined.vehicle)
        ORDER BY vehicle_no
    """.format(conditions_pi=conditions_pi, conditions_je=conditions_je)

    return frappe.db.sql(query, filter_values, as_dict=True)

def resolve_expense_accounts(filter_values):
    """
    Resolve, ONCE, the set of Account names that match each expense category,
    using the SAME `like` patterns the SQL used to embed. Stores parameterized
    tuples on filter_values for binding as %(...)s.

    Company scope mirrors the old WHERE `acc.company = %(company)s`: when a
    company filter is set we only resolve that company's accounts (the SQL
    still applies `acc.company` in build_conditions, so behaviour is identical).

    Empty categories are bound as `(None,)` so the SQL renders `IN (NULL)` --
    valid SQL that matches nothing -- instead of an illegal `IN ()`.
    """
    base_filters = {}
    if filter_values.get("company"):
        base_filters["company"] = filter_values["company"]

    all_accounts = set()
    for category, pattern in EXPENSE_ACCOUNT_PATTERNS.items():
        names = frappe.get_all(
            "Account",
            filters={**base_filters, "account_name": ["like", pattern]},
            pluck="name",
        )
        all_accounts.update(names)
        # `tuple(names) or (None,)` -> empty list becomes (None,) => IN (NULL)
        filter_values[f"{category}_accounts"] = tuple(names) or (None,)

    filter_values["all_expense_accounts"] = tuple(all_accounts) or (None,)

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