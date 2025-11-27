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
            "options": "Sub-Ledger",
            "width": 100
        },
        {
            "fieldname": "fuel",
            "label": _("Fuel"),
            "fieldtype": "Currency",
            "width": 80
        },
        {
            "fieldname": "repair",
            "label": _("Repair"),
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "fieldname": "others",
            "label": _("Others"),
            "fieldtype": "Currency",
            "width": 100
        }
    ]

def get_data(filters):
    """
    Fetch and combine expenses from Purchase Invoice and Journal Entry
    """
    if filters is None:
        filters = {}
    
    conditions_pi = get_pi_conditions(filters)
    conditions_je = get_je_conditions(filters)
    
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
        GROUP BY vehicle_no
        ORDER BY vehicle_no
    """.format(conditions_pi=conditions_pi, conditions_je=conditions_je)
    
    result = frappe.db.sql(query, as_dict=True)
    
    return result

def get_pi_conditions(filters):
    """Build WHERE conditions for Purchase Invoice"""
    conditions = ""
    
    if filters.get("company"):
        conditions += f" AND pi.company = '{filters.get('company')}'"
    
    if filters.get("department"):
        conditions += f" AND pi.department = '{filters.get('department')}'"
    
    if filters.get("period_start_date"):
        conditions += f" AND pi.posting_date >= '{filters.get('period_start_date')}'"
    
    if filters.get("period_end_date"):
        conditions += f" AND pi.posting_date <= '{filters.get('period_end_date')}'"

    if filters.get("vechile"):
        conditions += f" AND pic.custom_subtype = '{filters.get('vechile')}'"
    
    return conditions

def get_je_conditions(filters):
    """Build WHERE conditions for Journal Entry"""
    conditions = ""
    
    if filters.get("company"):
        conditions += f" AND je.company = '{filters.get('company')}'"
    
    if filters.get("department"):
        conditions += f" AND je.department = '{filters.get('department')}'"
    
    if filters.get("period_start_date"):
        conditions += f" AND je.posting_date >= '{filters.get('period_start_date')}'"
    
    if filters.get("period_end_date"):
        conditions += f" AND je.posting_date <= '{filters.get('period_end_date')}'"
    
    return conditions