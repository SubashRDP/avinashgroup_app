import frappe
from frappe.utils import getdate, nowdate, flt



def validate_sales_invoice(doc, method):
    """
    Validates Sales Invoice against customer credit limits with advance payment consideration.
    Optimized for performance with early exits and minimal DB hits.
    """
    return
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

    # Unlinked Journal Entry rows on the Debtors / customer-advance accounts.
    # Rows referenced against an invoice are excluded — their effect is already
    # inside that invoice's outstanding_amount. Net credit means the customer
    # has deposited money, so it joins the advance pool and nets against the
    # oldest bills exactly like a Payment Entry advance. Net debit is extra
    # debt with no bill behind it, so it can only be added in the amount check.
    je_net = flt(frappe.db.sql("""
        SELECT IFNULL(SUM(jea.debit - jea.credit), 0)
        FROM `tabJournal Entry Account` jea
        INNER JOIN `tabJournal Entry` je ON je.name = jea.parent
        WHERE je.docstatus = 1
          AND jea.party_type = 'Customer'
          AND jea.party = %s
          AND IFNULL(jea.reference_name, '') = ''
          AND jea.account IN (
              SELECT name FROM `tabAccount`
              WHERE account_name IN (
                  'Debtors A/c - Domestic',
                  'Advance Received',
                  'Advance From Customer'
              )
          )
    """, customer)[0][0])

    je_debit = 0.0
    if je_net < 0:
        advance += -je_net
    else:
        je_debit = je_net

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
        final_exposure = total_unpaid + je_debit + new_invoice_amount

        if final_exposure > amount_limit:
            available_credit = amount_limit - total_unpaid - je_debit
            frappe.throw(
                f"<b>Credit Limit: Amount Exceeded</b><br><br>"
                f"Customer: <b>{customer}</b><br>"
                f"Current Outstanding: <b>₹{total_unpaid:,.2f}</b><br>"
                f"Journal Debit Adjustment: <b>₹{je_debit:,.2f}</b><br>"
                f"New Invoice Amount: <b>₹{new_invoice_amount:,.2f}</b><br>"
                f"Total Exposure: <b>₹{final_exposure:,.2f}</b><br>"
                f"Maximum Credit Limit: <b>₹{amount_limit:,.2f}</b><br>"
                f"Available Credit: <b>₹{available_credit:,.2f}</b><br><br>"
                f"<i>Advance applied: ₹{advance:,.2f}</i>",
                title="Credit Amount Exceeded"
            )