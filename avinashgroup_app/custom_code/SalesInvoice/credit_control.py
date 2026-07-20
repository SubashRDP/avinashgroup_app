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


# import frappe
# from frappe.utils import getdate, nowdate

# def validate_sales_invoice(doc, method):
#     today = getdate(doc.posting_date or nowdate())
#     customer = doc.customer

#     # 1. Customer limits
#     custom_bill_count = frappe.db.get_value("Customer", customer, "custom_bill_count") or 0
#     custom_days_limit = frappe.db.get_value("Customer", customer, "custom_days_limit") or 0
#     custom_amount_limit = frappe.db.get_value("Customer", customer, "custom_amount_limit") or 0

#     # 2. Total unallocated advance
#     total_advance = frappe.db.sql("""
#         SELECT IFNULL(SUM(unallocated_amount), 0)
#         FROM `tabPayment Entry`
#         WHERE party_type = 'Customer'
#         AND party = %s
#         AND docstatus = 1
#         AND unallocated_amount > 0
#         AND payment_type IN ('Receive', 'Internal Transfer')
#     """, (customer,))[0][0] or 0

#     # 3. Outstanding invoices after advance
#     result = frappe.db.sql("""
#         SELECT 
#             name,
#             posting_date,
#             outstanding_amount,
#             cumulative_outstanding,
#             previous_cumulative,
#             CASE 
#                 WHEN previous_cumulative >= %(advance)s THEN outstanding_amount
#                 WHEN cumulative_outstanding > %(advance)s THEN cumulative_outstanding - %(advance)s
#                 ELSE 0
#             END AS remaining_outstanding_for_this_invoice
#         FROM (
#             SELECT 
#                 name,
#                 posting_date,
#                 outstanding_amount,
#                 SUM(outstanding_amount) OVER (
#                     ORDER BY posting_date ASC, name ASC
#                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
#                 ) AS cumulative_outstanding,
#                 COALESCE(
#                     SUM(outstanding_amount) OVER (
#                         ORDER BY posting_date ASC, name ASC
#                         ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
#                     ), 0
#                 ) AS previous_cumulative
#             FROM `tabSales Invoice`
#             WHERE customer = %(customer)s
#             AND docstatus = 1
#             AND outstanding_amount > 0
#             AND is_return = 0
#             AND is_internal_customer = 0
#             AND name != %(current_doc)s
#         ) inv
#         WHERE cumulative_outstanding > %(advance)s
#         ORDER BY posting_date ASC, name ASC
#     """, {
#         "customer": customer,
#         "current_doc": doc.name or "",
#         "advance": total_advance
#     }, as_dict=1)

#     if not result:
#         return

#     # 4. Metrics
#     first_unpaid = result[0]
#     unpaid_count = len(result)
#     total_outstanding = sum(
#         r.remaining_outstanding_for_this_invoice for r in result
#     )

#     # 5. Bill count check
#     if custom_bill_count and unpaid_count >= custom_bill_count:
#         frappe.throw(
#             f"Cannot create Sales Invoice.<br>"
#             f"Customer <b>{customer}</b> has <b>{unpaid_count}</b> unpaid invoices "
#             f"(after applying advance of <b>{total_advance:,.2f}</b>), "
#             f"exceeding allowed limit of <b>{custom_bill_count}</b>."
#         )

#     # 6. Days limit check
#     if custom_days_limit:
#         days_passed = (today - getdate(first_unpaid.posting_date)).days
#         if days_passed >= custom_days_limit:
#             frappe.throw(
#                 f"Cannot create Sales Invoice.<br>"
#                 f"Oldest unpaid invoice <b>{first_unpaid.name}</b> dated "
#                 f"<b>{first_unpaid.posting_date}</b> "
#                 f"({days_passed} days old) exceeds allowed limit of "
#                 f"<b>{custom_days_limit}</b> days."
#             )

#     # 7. Amount limit check
#     if custom_amount_limit:
#         new_amount = doc.grand_total or 0
#         final_exposure = total_outstanding + new_amount
#         if final_exposure > custom_amount_limit:
#             frappe.throw(
#                 f"Cannot create Sales Invoice.<br>"
#                 f"Customer exposure will be <b>{final_exposure:,.2f}</b> "
#                 f"(limit: <b>{custom_amount_limit:,.2f}</b>).<br>"
#                 f"Outstanding: <b>{total_outstanding:,.2f}</b><br>"
#                 f"New invoice: <b>{new_amount:,.2f}</b>"
#             )




import frappe
from frappe.utils import getdate, nowdate, flt



def validate_sales_invoice(doc, method):
    """
    Validates Sales Invoice against customer credit limits with advance payment consideration.
    Optimized for performance with early exits and minimal DB hits.
    """
    # Early exit: Skip draft amendments or cancelled docs
    if doc.docstatus == 2 or doc.is_return:
        return
    
    customer = doc.customer
    today = getdate(doc.posting_date or nowdate())
    new_invoice_amount = flt(doc.grand_total)
    
    # Early exit: Zero-value invoices don't affect credit
    if new_invoice_amount <= 0:
        return

    # ============================================================
    # 1. LOAD CUSTOMER LIMITS (Single DB Hit)
    # ============================================================
    limits = frappe.db.get_value(
        "Customer",
        customer,
        ["custom_bill_count", "custom_days_limit", "custom_amount_limit"],
        as_dict=True
    )
    
    if not limits:
        return
    
    bill_limit = flt(limits.get("custom_bill_count"))
    days_limit = flt(limits.get("custom_days_limit"))
    amount_limit = flt(limits.get("custom_amount_limit"))
    
    # Early exit: No limits configured
    if not (bill_limit or days_limit or amount_limit):
        return

    # ============================================================
    # 2. GET UNALLOCATED ADVANCE (Indexed Query)
    # ============================================================
    advance = flt(frappe.db.sql("""
        SELECT IFNULL(SUM(unallocated_amount), 0)
        FROM `tabPayment Entry`
        WHERE party_type = 'Customer'
          AND party = %s
          AND docstatus = 1
          AND unallocated_amount > 0.01
          AND payment_type IN ('Receive', 'Internal Transfer')
    """, customer)[0][0])

    # ============================================================
    # 3. FETCH UNPAID INVOICES (FIFO Order, Optimized)
    # ============================================================
    # Use indexed columns only, avoid SELECT *
    invoices = frappe.db.sql("""
        SELECT 
            name,
            posting_date,
            outstanding_amount
        FROM `tabSales Invoice`
        WHERE customer = %s
          AND docstatus = 1
          AND outstanding_amount > 0.01
          AND is_return = 0
          AND is_internal_customer = 0
          AND name != %s
        ORDER BY posting_date ASC, name ASC
    """, (customer, doc.name or ""), as_dict=True)
    
    # Early exit: No unpaid invoices
    if not invoices:
        return

    # ============================================================
    # 4. APPLY ADVANCE FIFO (Ultra-Fast Loop with Early Exits)
    # ============================================================
    remaining_advance = advance
    unpaid_list = []
    total_unpaid = 0.0
    
    for inv in invoices:
        outstanding = flt(inv.outstanding_amount)
        
        # Fully covered by advance
        if remaining_advance >= outstanding:
            remaining_advance -= outstanding
            continue
        
        # Partially covered or not covered
        actual_unpaid = outstanding - remaining_advance
        remaining_advance = 0
        
        unpaid_list.append({
            "name": inv.name,
            "date": inv.posting_date,
            "amount": actual_unpaid
        })
        total_unpaid += actual_unpaid

    # Early exit: All invoices covered by advance
    if not unpaid_list:
        return

    # ============================================================
    # 5. VALIDATION CHECKS (Ordered by Performance)
    # ============================================================
    
    # CHECK 1: Bill Count (Fastest - Simple Comparison)
    if bill_limit:
        unpaid_count = len(unpaid_list)
        if unpaid_count >= bill_limit:
            frappe.throw(
                f"<b>Credit Limit: Bill Count Exceeded</b><br><br>"
                f"Customer: <b>{customer}</b><br>"
                f"Unpaid Bills: <b>{unpaid_count}</b> (after applying ₹{advance:,.2f} advance)<br>"
                f"Maximum Allowed: <b>{int(bill_limit)}</b><br><br>"
                f"<i>Please clear existing invoices before creating new ones.</i>",
                title="Credit Limit Exceeded"
            )
    
    # CHECK 2: Days Limit (Fast - Date Comparison)
    if days_limit:
        oldest = unpaid_list[0]  # Already sorted FIFO
        days_overdue = (today - getdate(oldest["date"])).days
        
        if days_overdue >= days_limit:
            frappe.throw(
                f"<b>Credit Limit: Days Exceeded</b><br><br>"
                f"Customer: <b>{customer}</b><br>"
                f"Oldest Unpaid Invoice: <b>{oldest['name']}</b><br>"
                f"Date: <b>{oldest['date']}</b> ({days_overdue} days ago)<br>"
                f"Maximum Days Allowed: <b>{int(days_limit)}</b><br><br>"
                f"<i>Payment is overdue. Please collect payment before new sales.</i>",
                title="Credit Days Exceeded"
            )
    
    # CHECK 3: Amount Limit (Requires Calculation)
    if amount_limit:
        final_exposure = total_unpaid + new_invoice_amount
        
        if final_exposure > amount_limit:
            available_credit = amount_limit - total_unpaid
            frappe.throw(
                f"<b>Credit Limit: Amount Exceeded</b><br><br>"
                f"Customer: <b>{customer}</b><br>"
                f"Current Outstanding: <b>₹{total_unpaid:,.2f}</b><br>"
                f"New Invoice Amount: <b>₹{new_invoice_amount:,.2f}</b><br>"
                f"Total Exposure: <b>₹{final_exposure:,.2f}</b><br>"
                f"Maximum Credit Limit: <b>₹{amount_limit:,.2f}</b><br>"
                f"Available Credit: <b>₹{available_credit:,.2f}</b><br><br>"
                f"<i>Advance applied: ₹{advance:,.2f}</i>",
                title="Credit Amount Exceeded"
            )