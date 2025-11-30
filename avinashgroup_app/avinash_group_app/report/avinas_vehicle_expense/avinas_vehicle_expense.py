# import frappe
# from frappe import _

# def execute(filters=None):
#     columns = get_columns()
#     data = get_data(filters)
#     return columns, data

# def get_columns():
#     return [
#         {
#             "fieldname": "vehicle_no",
#             "label": _("Vehicle No"),
#             "fieldtype": "Link",
#             "options": "Sub-Ledger Category",
#             "width": 180
#         },
#         {
#             "fieldname": "fuel",
#             "label": _("Fuel"),
#             "fieldtype": "Currency",
#             "width": 150
#         },
#         {
#             "fieldname": "repair",
#             "label": _("Repair"),
#             "fieldtype": "Currency",
#             "width": 150
#         },
#         {
#             "fieldname": "others",
#             "label": _("Others"),
#             "fieldtype": "Currency",
#             "width": 200
#         }
#     ]

# def get_data(filters):
#     """
#     Fetch and combine expenses from Purchase Invoice and Journal Entry
#     """
#     if filters is None:
#         filters = {}
    
#     conditions_pi = get_pi_conditions(filters)
#     conditions_je = get_je_conditions(filters)
    
#     query = """
#         SELECT
#             vehicle_no,
#             SUM(FUEL) AS fuel,
#             SUM(Repair) AS repair,
#             SUM(Others) AS others
#         FROM (
#             -- Purchase Invoice Expenses
#             SELECT
#                 pic.custom_subtype as vehicle_no,
#                 SUM(CASE WHEN pic.expense_account IN ('547136 - Fuel Allowance - O/O - NGK',
#                                                 '547137 - Fuel Allowance - S/D - NGK',
#                                                 '547138 - Fuel Allowance - F/P - NGK') 
#                         THEN pic.amount ELSE 0 END) AS FUEL,
#                 SUM(CASE WHEN pic.expense_account IN ('549301 - R & M - Vehicles O/O - NGK',
#                                                 '549302 - R & M - Vehicles S/D - NGK',
#                                                 '549303 - R & M - Vehicles F/P - NGK') 
#                         THEN pic.amount ELSE 0 END) AS Repair,
#                 SUM(CASE WHEN pic.expense_account IN ('542902 - Other Vehicle Expenses - O/O - NGK',
#                                                 '552002 - Other Vehicle Expenses - S/D - NGK') 
#                         THEN pic.amount ELSE 0 END) AS Others
#             FROM
#                 `tabPurchase Invoice` pi
#                 JOIN `tabPurchase Invoice Item` pic ON pi.name = pic.parent
#             WHERE
#                 pi.docstatus = 1
#                  AND pic.expense_account IN ('547136 - Fuel Allowance - O/O - NGK',
#                                     '547137 - Fuel Allowance - S/D - NGK',
#                                     '547138 - Fuel Allowance - F/P - NGK',
#                                     '549301 - R & M - Vehicles O/O - NGK',
#                                     '549302 - R & M - Vehicles S/D - NGK',
#                                     '549303 - R & M - Vehicles F/P - NGK',
#                                     '542902 - Other Vehicle Expenses - O/O - NGK',
#                                     '552002 - Other Vehicle Expenses - S/D - NGK')
#                 {conditions_pi}
#             GROUP BY pic.custom_subtype
            
#             UNION ALL
            
#             -- Journal Entry Expenses
#             SELECT
#                 jea.custom_subtype as vehicle_no,
#                 SUM(CASE WHEN jea.account IN ('547136 - Fuel Allowance - O/O - NGK',
#                                             '547137 - Fuel Allowance - S/D - NGK',
#                                             '547138 - Fuel Allowance - F/P - NGK') 
#                     THEN jea.debit - jea.credit ELSE 0 END) AS FUEL,
#                 SUM(CASE WHEN jea.account IN ('549301 - R & M - Vehicles O/O - NGK',
#                                             '549302 - R & M - Vehicles S/D - NGK',
#                                             '549303 - R & M - Vehicles F/P - NGK') 
#                     THEN jea.debit - jea.credit ELSE 0 END) AS Repair,
#                 SUM(CASE WHEN jea.account IN ('542902 - Other Vehicle Expenses - O/O - NGK',
#                                             '552002 - Other Vehicle Expenses - S/D - NGK') 
#                     THEN jea.debit - jea.credit ELSE 0 END) AS Others
#             FROM
#                 `tabJournal Entry` je
#                 INNER JOIN `tabJournal Entry Account` jea ON je.name = jea.parent
#             WHERE
#                 je.docstatus = 1
#                 AND jea.account IN ('547136 - Fuel Allowance - O/O - NGK',
#                                     '547137 - Fuel Allowance - S/D - NGK',
#                                     '547138 - Fuel Allowance - F/P - NGK',
#                                     '549301 - R & M - Vehicles O/O - NGK',
#                                     '549302 - R & M - Vehicles S/D - NGK',
#                                     '549303 - R & M - Vehicles F/P - NGK',
#                                     '542902 - Other Vehicle Expenses - O/O - NGK',
#                                     '552002 - Other Vehicle Expenses - S/D - NGK')
#                 {conditions_je}
#             GROUP BY jea.custom_subtype
#         ) AS combined
#         GROUP BY vehicle_no
#         ORDER BY vehicle_no
#     """.format(conditions_pi=conditions_pi, conditions_je=conditions_je)
    
#     result = frappe.db.sql(query, filters, as_dict=True)
    
#     return result

# def get_pi_conditions(filters):
#     """Build WHERE conditions for Purchase Invoice"""
#     conditions = ""
    
#     if filters.get("company"):
#         conditions += " AND pi.company = %(company)s"
    
#     if filters.get("department"):
#         ledger_query = "select account_name from tabAccount where custom_department = %(department)s"
#         params = {"department": filters.get("department")}
#         department_coa = frappe.db.sql(ledger_query, params, as_dict=False)
        
#         if department_coa:
#             # Extract account names from tuple results
#             account_names = [row[0] for row in department_coa]
#             params["department_coa"] = account_names
#             conditions += " AND pi.expense_account in %(department_coa)s"

#         if filters.get("fiscal_year"):
#             fiscal_year_query = """
#                 SELECT year_start_date, year_end_date
#                 FROM `tabFiscal Year`
#                 WHERE name = %(fiscal_year)s
#             """
#             fiscal_year_param = {"fiscal_year": filters.get("fiscal_year")}
#             fiscal_year_data = frappe.db.sql(fiscal_year_query, fiscal_year_param, as_dict=True)

#             if fiscal_year_data:
#                 # fiscal_year_data is a list of dicts: [{'year_start_date': '2025-04-01', 'year_end_date': '2026-03-31'}]
#                 fy_start = fiscal_year_data[0]["year_start_date"]
#                 fy_end = fiscal_year_data[0]["year_end_date"]

#                 # Add conditions
#                 conditions += f" AND pi.posting_date >= '{fy_start}'"
#                 conditions += f" AND pi.posting_date <= '{fy_end}'"
           
    
#     if filters.get("period_start_date"):
#         conditions += " AND pi.posting_date >= %(period_start_date)s"
    
#     if filters.get("period_end_date"):
#         conditions += " AND pi.posting_date <= %(period_end_date)s"

#     if filters.get("vehicle_no"):
#         conditions += " AND pic.custom_subtype = %(vehicle_no)s"
    
#     return conditions

# def get_je_conditions(filters):
#     """Build WHERE conditions for Journal Entry"""
#     conditions = ""
    
#     if filters.get("company"):
#         conditions += " AND je.company = %(company)s"

#     if filters.get("department"):
#         ledger_query = "select account_name from tabAccount where custom_department = %(department)s"
#         params = {"department": filters.get("department")}
#         department_coa = frappe.db.sql(ledger_query, params, as_dict=False)
        
#         if department_coa:
#             # Extract account names from tuple results
#             account_names = [row[0] for row in department_coa]
#             params["department_coa"] = account_names
#             conditions += " AND pi.expense_account in %(department_coa)s"

    
#         if filters.get("fiscal_year"):
#     # Fetch start and end date for the selected fiscal year
#             fiscal_year_query = """
#                 SELECT year_start_date, year_end_date
#                 FROM `tabFiscal Year`
#                 WHERE name = %(fiscal_year)s
#             """
#             fiscal_year_param = {"fiscal_year": filters.get("fiscal_year")}
#             fiscal_year_data = frappe.db.sql(fiscal_year_query, fiscal_year_param, as_dict=True)

#             if fiscal_year_data:
#                 # fiscal_year_data is a list of dicts: [{'year_start_date': '2025-04-01', 'year_end_date': '2026-03-31'}]
#                    if filters.get("fiscal_year"):
#                         fiscal_year_query = """
#                             SELECT year_start_date, year_end_date
#                             FROM `tabFiscal Year`
#                             WHERE name = %(fiscal_year)s
#                         """
#                         fiscal_year_param = {"fiscal_year": filters.get("fiscal_year")}
#                         fiscal_year_data = frappe.db.sql(fiscal_year_query, fiscal_year_param, as_dict=True)

#                         if fiscal_year_data:
#                             # fiscal_year_data is a list of dicts: [{'year_start_date': '2025-04-01', 'year_end_date': '2026-03-31'}]
#                             fy_start = fiscal_year_data[0]["year_start_date"]
#                             fy_end = fiscal_year_data[0]["year_end_date"]

#                             # Add conditions
#                             conditions += f" AND je.posting_date >= '{fy_start}'"
#                             conditions += f" AND je.posting_date <= '{fy_end}'"
                

#     if filters.get("period_start_date"):
#         conditions += " AND je.posting_date >= %(period_start_date)s"
    
#     if filters.get("period_end_date"):
#         conditions += " AND je.posting_date <= %(period_end_date)s"

#     if filters.get("vehicle_no"):
#         conditions += " AND jea.custom_subtype = %(vehicle_no)s"
    
#     return conditions




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
            SUM(FUEL) AS fuel,
            SUM(Repair) AS repair,
            SUM(Others) AS others
        FROM (
            -- Purchase Invoice Expenses
            SELECT
                pic.custom_subtype as vehicle_no,
                SUM(CASE WHEN pic.expense_account IN ('547136 - Fuel Allowance - O/O - NGK',
                                                '547137 - Fuel Allowance - S/D - NGK',
                                                '547138 - Fuel Allowance - F/P - NGK') 
                        THEN pic.amount ELSE 0 END) AS FUEL,
                SUM(CASE WHEN pic.expense_account IN ('549301 - R & M - Vehicles O/O - NGK',
                                                '549302 - R & M - Vehicles S/D - NGK',
                                                '549303 - R & M - Vehicles F/P - NGK') 
                        THEN pic.amount ELSE 0 END) AS Repair,
                SUM(CASE WHEN pic.expense_account IN ('542902 - Other Vehicle Expenses - O/O - NGK',
                                                '552002 - Other Vehicle Expenses - S/D - NGK') 
                        THEN pic.amount ELSE 0 END) AS Others
            FROM
                `tabPurchase Invoice` pi
                JOIN `tabPurchase Invoice Item` pic ON pi.name = pic.parent
            WHERE
                pi.docstatus = 1
                AND pic.expense_account IN ('547136 - Fuel Allowance - O/O - NGK',
                                    '547137 - Fuel Allowance - S/D - NGK',
                                    '547138 - Fuel Allowance - F/P - NGK',
                                    '549301 - R & M - Vehicles O/O - NGK',
                                    '549302 - R & M - Vehicles S/D - NGK',
                                    '549303 - R & M - Vehicles F/P - NGK',
                                    '542902 - Other Vehicle Expenses - O/O - NGK',
                                    '552002 - Other Vehicle Expenses - S/D - NGK')
                {conditions_pi}
            GROUP BY pic.custom_subtype
            
            UNION ALL
            
            -- Journal Entry Expenses
            SELECT
                jea.custom_subtype as vehicle_no,
                SUM(CASE WHEN jea.account IN ('547136 - Fuel Allowance - O/O - NGK',
                                            '547137 - Fuel Allowance - S/D - NGK',
                                            '547138 - Fuel Allowance - F/P - NGK') 
                    THEN jea.debit - jea.credit ELSE 0 END) AS FUEL,
                SUM(CASE WHEN jea.account IN ('549301 - R & M - Vehicles O/O - NGK',
                                            '549302 - R & M - Vehicles S/D - NGK',
                                            '549303 - R & M - Vehicles F/P - NGK') 
                    THEN jea.debit - jea.credit ELSE 0 END) AS Repair,
                SUM(CASE WHEN jea.account IN ('542902 - Other Vehicle Expenses - O/O - NGK',
                                            '552002 - Other Vehicle Expenses - S/D - NGK') 
                    THEN jea.debit - jea.credit ELSE 0 END) AS Others
            FROM
                `tabJournal Entry` je
                INNER JOIN `tabJournal Entry Account` jea ON je.name = jea.parent
            WHERE
                je.docstatus = 1
                AND jea.account IN ('547136 - Fuel Allowance - O/O - NGK',
                                    '547137 - Fuel Allowance - S/D - NGK',
                                    '547138 - Fuel Allowance - F/P - NGK',
                                    '549301 - R & M - Vehicles O/O - NGK',
                                    '549302 - R & M - Vehicles S/D - NGK',
                                    '549303 - R & M - Vehicles F/P - NGK',
                                    '542902 - Other Vehicle Expenses - O/O - NGK',
                                    '552002 - Other Vehicle Expenses - S/D - NGK')
                {conditions_je}
            GROUP BY jea.custom_subtype
        ) AS combined
        WHERE vehicle_no IS NOT NULL
        GROUP BY vehicle_no
        ORDER BY vehicle_no
    """.format(conditions_pi=conditions_pi, conditions_je=conditions_je)
    
    return frappe.db.sql(query, filter_values, as_dict=True)

def prepare_filter_values(filters):
    """Prepare all filter values with a single DB call per filter type"""
    filter_values = filters.copy()
    
    # Handle department filter
    if filters.get("department"):
        department_coa = frappe.get_all(
            "Account",
            filters={"custom_department": filters.get("department")},
            pluck="account_name"
        )
        if department_coa:
            filter_values["department_coa"] = department_coa
    
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
    
    return filter_values

def build_conditions(filter_values, doc_prefix, child_prefix):
    """Build WHERE conditions using pre-fetched filter values"""
    conditions = ""
    
    if filter_values.get("company"):
        conditions += f" AND {doc_prefix}.company = %(company)s"
    
    if filter_values.get("department_coa"):
        account_field = "expense_account" if doc_prefix == "pi" else "account"
        conditions += f" AND {child_prefix}.{account_field} IN %(department_coa)s"
    
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