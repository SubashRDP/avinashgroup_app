import frappe
from frappe.utils import getdate, nowdate

def validate_sales_invoice(doc, method):
    """
    Validates a Sales Invoice against customer-specific limits:
    1. Maximum unpaid invoice count
    2. Maximum days allowed for unpaid invoices
    3. Maximum cumulative amount allowed

    """

    today = getdate(doc.posting_date or nowdate())
    customer = doc.customer

    # 1. Fetch customer-specific limits
    custom_bill_count = frappe.db.get_value("Customer", customer, "custom_bill_count") or 0
    custom_days_limit = frappe.db.get_value("Customer", customer, "custom_days_limit") or 0
    custom_amount_limit = frappe.db.get_value("Customer", customer, "custom_amount_limit") or 0

    # 2. BILL COUNT CHECK
    unpaid_count = frappe.db.count(
        "Sales Invoice",
        filters={
            "customer": customer,
            "docstatus": 1,
            "outstanding_amount": [">", 0],
            "is_return": 0,
            "is_internal_customer": 0
        }
    )

    if custom_bill_count and unpaid_count >= custom_bill_count:
        frappe.throw(
            f"Cannot create Sales Invoice.<br>"
            f"Customer <b>{customer}</b> has <b>{unpaid_count}</b> unpaid invoices, "
            f"which exceeds the allowed bill count limit of <b>{custom_bill_count}</b>."
        )

    # 3. DAYS LIMIT CHECK
    if custom_days_limit:
        oldest_posting_date = frappe.db.get_value(
            "Sales Invoice",
            filters={
                "customer": customer,
                "docstatus": 1,
                "outstanding_amount": [">", 0],
                "is_return": 0,
                "is_internal_customer": 0
            },
            fieldname="posting_date",
            order_by="posting_date asc"
        )

        if oldest_posting_date:
            days_passed = (today - getdate(oldest_posting_date)).days
            if days_passed >= custom_days_limit:
                frappe.throw(
                    f"Cannot create Sales Invoice.<br>"
                    f"Customer has unpaid invoices since <b>{oldest_posting_date}</b> "
                    f"(<b>{days_passed}</b> days), exceeding the allowed limit of "
                    f"<b>{custom_days_limit}</b> days."
                )

    # 4. AMOUNT LIMIT CHECK - ONLY OUTSTANDING FROM UNPAID INVOICES
    if custom_amount_limit:
        total_outstanding = frappe.db.sql("""
            SELECT SUM(outstanding_amount)
            FROM `tabSales Invoice`
            WHERE customer = %s
            AND docstatus = 1
            AND outstanding_amount > 0
            AND is_return = 0
            AND is_internal_customer = 0
            AND posting_date <= %s
            AND name != %s
        """, (customer, today, doc.name or ""))[0][0] or 0

        new_invoice_amount = doc.grand_total or 0
        final_exposure = total_outstanding + new_invoice_amount

        
        if final_exposure > custom_amount_limit:
            frappe.throw(
                f"Cannot create Sales Invoice.<br>"
                f"Customer balance after this invoice will be <b>{final_exposure}</b>, "
                f"which exceeds the allowed amount limit of <b>{custom_amount_limit}</b>."
            )

