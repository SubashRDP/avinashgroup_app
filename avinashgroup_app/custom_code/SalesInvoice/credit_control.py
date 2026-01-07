# import frappe
# from frappe.utils import getdate, nowdate

# def validate_sales_invoice(doc, method):
#     """
#     Validates a Sales Invoice against customer-specific limits:
#     1. Maximum unpaid invoice count
#     2. Maximum days allowed for unpaid invoices
#     3. Maximum cumulative amount allowed

#     """

#     today = getdate(doc.posting_date or nowdate())
#     customer = doc.customer

#     # 1. Fetch customer-specific limits
#     custom_bill_count = frappe.db.get_value("Customer", customer, "custom_bill_count") or 0
#     custom_days_limit = frappe.db.get_value("Customer", customer, "custom_days_limit") or 0
#     custom_amount_limit = frappe.db.get_value("Customer", customer, "custom_amount_limit") or 0

#     # 2. BILL COUNT CHECK
#     unpaid_count = frappe.db.count(
#         "Sales Invoice",
#         filters={
#             "customer": customer,
#             "docstatus": 1,
#             "outstanding_amount": [">", 0],
#             "is_return": 0,
#             "is_internal_customer": 0
#         }
#     )

#     if custom_bill_count and unpaid_count >= custom_bill_count:
#         frappe.throw(
#             f"Cannot create Sales Invoice.<br>"
#             f"Customer <b>{customer}</b> has <b>{unpaid_count}</b> unpaid invoices, "
#             f"which exceeds the allowed bill count limit of <b>{custom_bill_count}</b>."
#         )

#     # 3. DAYS LIMIT CHECK
#     if custom_days_limit:
#         oldest_posting_date = frappe.db.get_value(
#             "Sales Invoice",
#             filters={
#                 "customer": customer,
#                 "docstatus": 1,
#                 "outstanding_amount": [">", 0],
#                 "is_return": 0,
#                 "is_internal_customer": 0
#             },
#             fieldname="posting_date",
#             order_by="posting_date asc"
#         )

#         if oldest_posting_date:
#             days_passed = (today - getdate(oldest_posting_date)).days
#             if days_passed >= custom_days_limit:
#                 frappe.throw(
#                     f"Cannot create Sales Invoice.<br>"
#                     f"Customer has unpaid invoices since <b>{oldest_posting_date}</b> "
#                     f"(<b>{days_passed}</b> days), exceeding the allowed limit of "
#                     f"<b>{custom_days_limit}</b> days."
#                 )

#     # 4. AMOUNT LIMIT CHECK - ONLY OUTSTANDING FROM UNPAID INVOICES
#     if custom_amount_limit:
#         total_outstanding = frappe.db.sql("""
#             SELECT SUM(outstanding_amount)
#             FROM `tabSales Invoice`
#             WHERE customer = %s
#             AND docstatus = 1
#             AND outstanding_amount > 0
#             AND is_return = 0
#             AND is_internal_customer = 0
#             AND posting_date <= %s
#             AND name != %s
#         """, (customer, today, doc.name or ""))[0][0] or 0

#         new_invoice_amount = doc.grand_total or 0
#         final_exposure = total_outstanding + new_invoice_amount

        
#         if final_exposure > custom_amount_limit:
#             frappe.throw(
#                 f"Cannot create Sales Invoice.<br>"
#                 f"Customer balance after this invoice will be <b>{final_exposure}</b>, "
#                 f"which exceeds the allowed amount limit of <b>{custom_amount_limit}</b>."
#             )



import frappe
from frappe.utils import getdate, nowdate

def validate_sales_invoice(doc, method):
    """
    Validates a Sales Invoice against customer-specific limits:
    1. Maximum unpaid invoice count
    2. Maximum days allowed for unpaid invoices
    3. Maximum cumulative amount allowed
    
    Considers unallocated advance payments before validation.
    """

    today = getdate(doc.posting_date or nowdate())
    customer = doc.customer

    # 1. Fetch customer-specific limits
    custom_bill_count = frappe.db.get_value("Customer", customer, "custom_bill_count") or 0
    custom_days_limit = frappe.db.get_value("Customer", customer, "custom_days_limit") or 0
    custom_amount_limit = frappe.db.get_value("Customer", customer, "custom_amount_limit") or 0

    # 2. GET TOTAL UNALLOCATED ADVANCE AMOUNT
    total_advance = frappe.db.sql("""
        SELECT IFNULL(SUM(unallocated_amount), 0)
        FROM `tabPayment Entry`
        WHERE party_type = 'Customer'
        AND party = %s
        AND docstatus = 1
        AND unallocated_amount > 0
        AND payment_type IN ('Receive', 'Internal Transfer')
    """, (customer,))[0][0] or 0

    # 3. GET FIRST UNPAID INVOICE AFTER APPLYING ADVANCE & COUNT/AMOUNT
    result = frappe.db.sql("""
        WITH RankedInvoices AS (
            SELECT 
                name,
                posting_date,
                outstanding_amount,
                SUM(outstanding_amount) OVER (
                    ORDER BY posting_date ASC, creation ASC
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) as cumulative_outstanding,
                SUM(outstanding_amount) OVER (
                    ORDER BY posting_date ASC, creation ASC
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ) as previous_cumulative
            FROM `tabSales Invoice`
            WHERE customer = %s
            AND docstatus = 1
            AND outstanding_amount > 0
            AND is_return = 0
            AND is_internal_customer = 0
            AND name != %s
        )
        SELECT 
            name,
            posting_date,
            outstanding_amount,
            cumulative_outstanding,
            IFNULL(previous_cumulative, 0) as previous_cumulative,
            CASE 
                WHEN IFNULL(previous_cumulative, 0) >= %s THEN outstanding_amount
                WHEN cumulative_outstanding > %s THEN cumulative_outstanding - %s
                ELSE 0
            END as remaining_outstanding_for_this_invoice
        FROM RankedInvoices
        WHERE cumulative_outstanding > %s
        ORDER BY posting_date ASC, creation ASC
    """, (customer, doc.name or "", total_advance, total_advance, total_advance, total_advance), as_dict=1)

    if not result:
        # All invoices can be paid by advance, no restrictions
        return

    # 4. CALCULATE METRICS
    first_unpaid_invoice = result[0]
    unpaid_count_after_advance = len(result)
    total_outstanding_after_advance = sum(
        inv.remaining_outstanding_for_this_invoice for inv in result
    )

    # 5. BILL COUNT CHECK
    if custom_bill_count and unpaid_count_after_advance >= custom_bill_count:
        frappe.throw(
            f"Cannot create Sales Invoice.<br>"
            f"Customer <b>{customer}</b> has <b>{unpaid_count_after_advance}</b> unpaid invoices "
            f"(after applying advance of <b>{total_advance:,.2f}</b>), "
            f"which exceeds the allowed bill count limit of <b>{custom_bill_count}</b>."
        )

    # 6. DAYS LIMIT CHECK
    if custom_days_limit:
        oldest_posting_date = first_unpaid_invoice.posting_date
        days_passed = (today - getdate(oldest_posting_date)).days
        
        if days_passed >= custom_days_limit:
            frappe.throw(
                f"Cannot create Sales Invoice.<br>"
                f"Customer has unpaid invoice <b>{first_unpaid_invoice.name}</b> since <b>{oldest_posting_date}</b> "
                f"(<b>{days_passed}</b> days), exceeding the allowed limit of "
                f"<b>{custom_days_limit}</b> days.<br>"
                f"(After applying advance of <b>{total_advance:,.2f}</b>)"
            )

    # 7. AMOUNT LIMIT CHECK
    if custom_amount_limit:
        new_invoice_amount = doc.grand_total or 0
        final_exposure = total_outstanding_after_advance + new_invoice_amount
        
        if final_exposure > custom_amount_limit:
            frappe.throw(
                f"Cannot create Sales Invoice.<br>"
                f"Customer balance after this invoice will be <b>{final_exposure:,.2f}</b> "
                f"(after applying advance of <b>{total_advance:,.2f}</b>), "
                f"which exceeds the allowed amount limit of <b>{custom_amount_limit:,.2f}</b>.<br>"
                f"Current outstanding: <b>{total_outstanding_after_advance:,.2f}</b><br>"
                f"New invoice: <b>{new_invoice_amount:,.2f}</b>"
            )