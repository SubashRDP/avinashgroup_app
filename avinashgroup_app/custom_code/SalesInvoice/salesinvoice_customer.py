import frappe
from frappe import _
from frappe.utils import nowdate, add_days, getdate, flt, formatdate, fmt_money

@frappe.whitelist()
def check_customer_credit_limit_on_load(customer):
    """
    Check ONLY days and bill count on customer selection (load/change)
    Amount check will be done on save with current invoice amount
    """
    
    # Get customer credit settings
    customer_doc = frappe.get_cached_value(
        'Customer', 
        customer, 
        ['custom_days', 'custom_amount', 'custom_bill_count'],
        as_dict=True
    )
    
    if not customer_doc:
        return {'status': 'error', 'message': 'Customer not found'}
    
    days = customer_doc.get('custom_days') or 0
    bill_count_limit = customer_doc.get('custom_bill_count') or 0
    
    # Calculate borderline date
    borderline_date = add_days(nowdate(), -days)
    
    # METHOD 1: Get total outstanding from Customer Ledger Summary (FASTEST & SIMPLEST)
    company = frappe.defaults.get_user_default('Company') or frappe.db.get_single_value('Global Defaults', 'default_company')
    total_outstanding = frappe.db.get_value(
        'Customer Ledger Summary',
        {'customer': customer, 'company': company},
        'outstanding_amount'
    ) or 0
    
    # METHOD 2: Get detailed invoice list for overdue and bill count checks
    query = """
        SELECT 
            si.name,
            si.posting_date,
            si.grand_total,
            si.outstanding_amount,
            si.status,
            CASE 
                WHEN si.posting_date < %(borderline_date)s THEN 1 
                ELSE 0 
            END as is_overdue
        FROM `tabSales Invoice` si
        WHERE 
            si.customer = %(customer)s
            AND si.docstatus = 1
            AND si.status NOT IN ('Paid', 'Cancelled', 'Return', 'Credit Note')
            AND si.outstanding_amount > 0
        ORDER BY si.posting_date ASC
    """
    
    invoices = frappe.db.sql(query, {
        'customer': customer,
        'borderline_date': borderline_date
    }, as_dict=True)
    
    # Calculate metrics
    overdue_invoices = [inv for inv in invoices if inv.is_overdue]
    unpaid_count = len(invoices)
    overdue_amount = sum(flt(inv.outstanding_amount) for inv in overdue_invoices)
    
    # Use Customer Ledger Summary for total outstanding (most accurate)
    total_outstanding = flt(total_outstanding)
    
    # Prepare result
    result = {
        'status': 'success',
        'is_blocked': False,
        'warnings': [],
        'customer': customer,
        'limits': {
            'days': days,
            'amount_limit': customer_doc.get('custom_amount') or 0,
            'bill_count_limit': bill_count_limit,
            'borderline_date': borderline_date
        },
        'current': {
            'total_outstanding': total_outstanding,
            'unpaid_count': unpaid_count,
            'overdue_count': len(overdue_invoices),
            'overdue_amount': overdue_amount
        },
        'overdue_invoices': []
    }
    
    # Check 1: Overdue invoices (ONLY days check)
    if overdue_invoices:
        result['is_blocked'] = True
        result['warnings'].append({
            'type': 'overdue',
            'title': 'OVERDUE PAYMENTS DETECTED',
            'message': f'{len(overdue_invoices)} invoice(s) overdue beyond {days} days (Older than {formatdate(borderline_date)})',
            'amount': overdue_amount
        })
        result['overdue_invoices'] = [
            {
                'name': inv.name,
                'posting_date': str(inv.posting_date),
                'outstanding_amount': flt(inv.outstanding_amount),
                'grand_total': flt(inv.grand_total)
            } 
            for inv in overdue_invoices
        ]
    
    # Check 2: Bill count exceeded (ONLY count check)
    if flt(unpaid_count) > flt(bill_count_limit):
        result['is_blocked'] = True
        result['warnings'].append({
            'type': 'bill_count',
            'title': 'UNPAID BILL COUNT EXCEEDED',
            'message': f'Unpaid bills: {unpaid_count} exceeds limit: {bill_count_limit}',
            'excess_bills': unpaid_count - bill_count_limit
        })
    
    # Add info message for amount (will be checked on save)
    result['info_message'] = f'Current outstanding: {(total_outstanding)}. Amount limit will be validated on save.'
    
    return result


@frappe.whitelist()
def check_customer_credit_limit_on_save(customer, current_invoice_amount, current_invoice_name=None):
    """
    Check ALL conditions including amount on save
    Includes current invoice amount in calculation
    """
    
    # Get customer credit settings
    customer_doc = frappe.get_cached_value(
        'Customer', 
        customer, 
        ['custom_days', 'custom_amount', 'custom_bill_count'],
        as_dict=True
    )
    
    if not customer_doc:
        return {'status': 'error', 'message': 'Customer not found'}
    
    days = customer_doc.get('custom_days') or 0
    amount_limit = customer_doc.get('custom_amount') or 0
    bill_count_limit = customer_doc.get('custom_bill_count') or 0
    current_amount = flt(current_invoice_amount)
    
    # Calculate borderline date
    borderline_date = add_days(nowdate(), -days)
    
    # METHOD 1: Get total outstanding from Customer Ledger Summary (FASTEST)
    company = frappe.defaults.get_user_default('Company') or frappe.db.get_single_value('Global Defaults', 'default_company')
    existing_outstanding = flt(frappe.db.get_value(
        'Customer Ledger Summary',
        {'customer': customer, 'company': company},
        'outstanding_amount'
    ) or 0)
    
    # METHOD 2: Get detailed invoice list (for overdue & bill count checks, excluding current invoice)
    query = """
        SELECT 
            si.name,
            si.posting_date,
            si.grand_total,
            si.outstanding_amount,
            si.status,
            CASE 
                WHEN si.posting_date < %(borderline_date)s THEN 1 
                ELSE 0 
            END as is_overdue
        FROM `tabSales Invoice` si
        WHERE 
            si.customer = %(customer)s
            AND si.docstatus = 1
            AND si.status NOT IN ('Paid', 'Cancelled', 'Return', 'Credit Note')
            AND si.outstanding_amount > 0
            {exclude_current}
        ORDER BY si.posting_date ASC
    """.format(
        exclude_current=f"AND si.name != %(current_invoice_name)s" if current_invoice_name else ""
    )
    
    invoices = frappe.db.sql(query, {
        'customer': customer,
        'borderline_date': borderline_date,
        'current_invoice_name': current_invoice_name
    }, as_dict=True)
    
    # Calculate metrics INCLUDING current invoice
    overdue_invoices = [inv for inv in invoices if inv.is_overdue]
    unpaid_count = len(invoices)
    overdue_amount = sum(flt(inv.outstanding_amount) for inv in overdue_invoices)
    
    # Total outstanding = Customer Ledger Summary + Current Invoice
    # Note: If editing existing invoice, subtract old amount first
    total_outstanding_with_current = existing_outstanding + current_amount
    
    # Prepare result
    result = {
        'status': 'success',
        'is_blocked': False,
        'warnings': [],
        'customer': customer,
        'limits': {
            'days': days,
            'amount_limit': amount_limit,
            'bill_count_limit': bill_count_limit,
            'borderline_date': borderline_date
        },
        'current': {
            'existing_outstanding': existing_outstanding,
            'current_invoice_amount': current_amount,
            'total_outstanding_with_current': total_outstanding_with_current,
            'unpaid_count': unpaid_count,
            'overdue_count': len(overdue_invoices),
            'overdue_amount': overdue_amount
        },
        'overdue_invoices': []
    }
    
    # Check 1: Overdue invoices
    if overdue_invoices:
        result['is_blocked'] = True
        result['warnings'].append({
            'type': 'overdue',
            'title': 'OVERDUE PAYMENTS DETECTED',
            'message': f'{len(overdue_invoices)} invoice(s) overdue beyond {days} days (Older than {formatdate(borderline_date)})',
            'amount': overdue_amount
        })
        result['overdue_invoices'] = [
            {
                'name': inv.name,
                'posting_date': str(inv.posting_date),
                'outstanding_amount': flt(inv.outstanding_amount),
                'grand_total': flt(inv.grand_total)
            } 
            for inv in overdue_invoices
        ]
    
    # Check 2: Amount limit exceeded (INCLUDING current invoice)
    if total_outstanding_with_current > amount_limit:
        result['is_blocked'] = True
        result['warnings'].append({
            'type': 'amount',
            'title': 'CREDIT LIMIT WILL BE EXCEEDED',
            'message': f'Total outstanding ({fmt_money(total_outstanding_with_current, currency="NPR")}) will exceed limit ({fmt_money(amount_limit, currency="NPR")})',
            'breakdown': {
                'existing_outstanding': existing_outstanding,
                'current_invoice': current_amount,
                'total': total_outstanding_with_current,
                'limit': amount_limit,
                'exceeded_by': total_outstanding_with_current - amount_limit
            }
        })
    
    # Check 3: Bill count exceeded
    if unpaid_count > bill_count_limit:
        result['is_blocked'] = True
        result['warnings'].append({
            'type': 'bill_count',
            'title': 'UNPAID BILL COUNT EXCEEDED',
            'message': f'Unpaid bills: {unpaid_count} exceeds limit: {bill_count_limit}',
            'excess_bills': unpaid_count - bill_count_limit
        })
    
    return result


# ============================================
# SALES INVOICE VALIDATION (Before Submit)
# ============================================

def validate(doc, method):
    """
    Server-side validation before submit
    This ensures validation even if client-side is bypassed
    """
    if doc.customer and doc.docstatus == 0:  # Only on draft
        result = check_customer_credit_limit_on_save(
            doc.customer, 
            doc.grand_total,
            doc.name if not doc.is_new() else None
        )
        
        if result.get('is_blocked'):
            # Build detailed error message
            error_messages = []
            
            for warning in result.get('warnings', []):
                if warning['type'] == 'overdue':
                    error_messages.append(
                        f"<strong>{warning['title']}</strong><br>{warning['message']}<br>"
                        f"Overdue Amount: {fmt_money(warning['amount'], currency='NPR')}"
                    )
                elif warning['type'] == 'amount':
                    breakdown = warning.get('breakdown', {})
                    error_messages.append(
                        f"<strong>{warning['title']}</strong><br>"
                        f"Existing Outstanding: {fmt_money(breakdown.get('existing_outstanding', 0), currency='NPR')}<br>"
                        f"Current Invoice: {fmt_money(breakdown.get('current_invoice', 0), currency='NPR')}<br>"
                        f"Total: {fmt_money(breakdown.get('total', 0), currency='NPR')}<br>"
                        f"Limit: {fmt_money(breakdown.get('limit', 0), currency='NPR')}<br>"
                        f"<span style='color: red;'>Exceeded By: {fmt_money(breakdown.get('exceeded_by', 0), currency='NPR')}</span>"
                    )
                elif warning['type'] == 'bill_count':
                    error_messages.append(
                        f"<strong>{warning['title']}</strong><br>{warning['message']}"
                    )
            
            # Throw validation error
            frappe.throw(
                _("Cannot save Sales Invoice for customer {0}:<br><br>{1}<br><br>"
                  "Please clear outstanding payments or reduce invoice amount.").format(
                    frappe.bold(doc.customer),
                    "<br><br>".join(error_messages)
                ),
                title=_("Credit Limit Validation Failed")
            )

