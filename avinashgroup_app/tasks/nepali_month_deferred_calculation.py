import pdb
import logging
from pydoc import doc
import frappe
from frappe import _
from frappe.utils import cint, today, date_diff, getdate, add_days, flt, rounded
import nepali_datetime
from datetime import timedelta
import random


from avinashgroup_app.utils.nepali_date import (
    is_first_of_nepali_month,
    get_previous_nepali_month_dates,
    get_today_nepali_date,
    get_nepali_month_name,
    log_nepali_date_info
)

from erpnext.accounts.deferred_revenue import (
    build_conditions,
    send_mail,
    get_already_booked_amount
)
from erpnext.accounts.utils import get_account_currency
from erpnext.accounts.general_ledger import make_gl_entries
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
)



def process_nepali_deferred_accounting():
    """
    Main function that runs daily at 12:00 AM
    Checks if today is 1st of Nepali month and processes deferred accounting
    """
    logger = frappe.logger()
    logger.setLevel(logging.INFO)
    
    log_nepali_date_info()
    
    if not is_first_of_nepali_month():
        frappe.logger().info("Not 1st of Nepali month. Skipping deferred accounting.")
        return
    
    # ✅ CORRECT: If ERPNext default is enabled, skip Nepali processing
    # We only run Nepali processing when default ERPNext processing is DISABLED
    if cint(frappe.db.get_singles_value("Accounts Settings", "automatically_process_deferred_accounting_entry")):
        frappe.logger().info("ERPNext default deferred accounting is enabled. Skipping Nepali processing.")
        return
    
    if not cint(frappe.db.get_singles_value("Accounts Settings", "process_deferred_accounting_in_nepali_month")):
        frappe.logger().info("Nepali deferred accounting is disabled in Accounts Settings.")
        return
    
    # Get previous Nepali month's date range
    start_date, end_date = get_previous_nepali_month_dates()
    frappe.logger().info(f"start date {start_date} end date {end_date}")
    # Get all companies
    companies = frappe.get_all("Company")
    
    # Process for each company
    for company in companies:
        try:
            # Process Revenue (Sales Invoice)
            process_nepali_deferred_revenue(
                company=company.name,
                start_date=start_date,
                end_date=end_date,
                posting_date=end_date
            )
            
            # Process Expense (Purchase Invoice)
            process_nepali_deferred_expense(
                company=company.name,
                start_date=start_date,
                end_date=end_date,
                posting_date=end_date
            )
            
            frappe.db.commit()
            
        except Exception as e:
            frappe.log_error(
                title=f"Nepali Deferred Accounting Error - {company.name}",
                message=frappe.get_traceback()
            )
            frappe.db.rollback()


def process_nepali_deferred_revenue(company, start_date, end_date, posting_date):
    """Process deferred revenue for given Nepali month period"""
    
    conditions = build_conditions("Income", None, company)
    
    invoices = frappe.db.sql_list(
        f"""
        SELECT DISTINCT item.parent
        FROM `tabSales Invoice Item` item, `tabSales Invoice` p
        WHERE item.service_start_date <= %s 
        AND item.service_end_date >= %s
        AND item.enable_deferred_revenue = 1 
        AND item.parent = p.name
        AND item.docstatus = 1 
        AND IFNULL(item.amount, 0) > 0
        {conditions}
        """,
        (end_date, start_date)
    )
    
    frappe.logger().info(f"Found {len(invoices)} sales invoices for {company}")
    
    if invoices:
        doc = frappe.get_doc(
            dict(
                doctype="Process Deferred Accounting",
                company=company,
                posting_date=posting_date,
                start_date=start_date,
                end_date=end_date,
                type="Income"
            )
        )
        
        try:
            doc.insert()
            
            for invoice in invoices:
                invoice_doc = frappe.get_doc("Sales Invoice", invoice)
                book_nepali_deferred_income_or_expense(invoice_doc, doc.name, posting_date)
            
            if not frappe.flags.deferred_accounting_error:
                doc.submit()
            else:
                send_mail(doc.name)
                
        except Exception as e:
            frappe.log_error(
                title=f"Error processing revenue for {company}",
                message=frappe.get_traceback()
            )


def process_nepali_deferred_expense(company, start_date, end_date, posting_date):
    """Process deferred expense for given Nepali month period"""
    
    conditions = build_conditions("Expense", None, company)
    
    invoices = frappe.db.sql_list(
        f"""
        SELECT DISTINCT item.parent
        FROM `tabPurchase Invoice Item` item, `tabPurchase Invoice` p
        WHERE item.service_start_date <= %s 
        AND item.service_end_date >= %s
        AND item.enable_deferred_expense = 1 
        AND item.parent = p.name
        AND item.docstatus = 1 
        AND IFNULL(item.amount, 0) > 0
        {conditions}
        """,
        (end_date, start_date)
    )
    
    frappe.logger().info(f"Found {len(invoices)} purchase invoices for {company}")
    
    if invoices:
        doc = frappe.get_doc(
            dict(
                doctype="Process Deferred Accounting",
                company=company,
                posting_date=posting_date,
                start_date=start_date,
                end_date=end_date,
                type="Expense"
            )
        )
        
        try:
            doc.insert()
            
            for invoice in invoices:
                invoice_doc = frappe.get_doc("Purchase Invoice", invoice)
                book_nepali_deferred_income_or_expense(invoice_doc, doc.name, posting_date)
            
            # ✅ FIXED: Changed from .error() to .info()
            if not frappe.flags.deferred_accounting_error:
                frappe.logger().info(f"Submitting Process Deferred Accounting: {doc.name}")
                doc.submit()
            else:
                send_mail(doc.name)
                
        except Exception as e:
            frappe.log_error(
                title=f"Error processing expense for {company}",
                message=frappe.get_traceback()
            )


def get_nepali_month_days(year, month):
    """
    Get the number of days in a Nepali month
    """
    if month == 12:
        next_month_first = nepali_datetime.date(year + 1, 1, 1)
    else:
        next_month_first = nepali_datetime.date(year, month + 1, 1)
    
    month_first = nepali_datetime.date(year, month, 1)
    
    month_last = next_month_first.to_datetime_date() - timedelta(days=1)
    month_first_gregorian = month_first.to_datetime_date()
    
    return date_diff(month_last, month_first_gregorian) + 1


def calculate_service_period_months(service_start_date, service_end_date):
    """
    Calculate month distribution for a service period
    
    Returns:
    - total_months: Number of Nepali months the service spans
    - start_month_days: Days in the starting partial month
    - end_month_days: Days in the ending partial month
    - complete_months: Number of complete months in between
    - month_distribution: List of (year, month, days) for each month
    """
    service_start_nepali = nepali_datetime.date.from_datetime_date(service_start_date)
    service_end_nepali = nepali_datetime.date.from_datetime_date(service_end_date)
    
    month_distribution = []
    
    current_year = service_start_nepali.year
    current_month = service_start_nepali.month
    
    while True:
        # Get first and last day of current processing month
        month_first_day = 1
        month_last_day = get_nepali_month_days(current_year, current_month)
        
        # Determine the actual start and end within this month
        if current_year == service_start_nepali.year and current_month == service_start_nepali.month:
            # Starting month - may be partial
            actual_start_day = service_start_nepali.day
        else:
            # Subsequent months start from day 1
            actual_start_day = 1
        
        if current_year == service_end_nepali.year and current_month == service_end_nepali.month:
            # Ending month - may be partial
            actual_end_day = service_end_nepali.day
        else:
            # Previous months end at last day
            actual_end_day = month_last_day
        
        # Calculate days in this month for the service period
        days_in_this_month = actual_end_day - actual_start_day + 1
        
        # Determine if this is a complete month
        is_complete = (actual_start_day == 1 and actual_end_day == month_last_day)
        
        month_distribution.append({
            'year': current_year,
            'month': current_month,
            'month_name': get_nepali_month_name(current_month),
            'days_in_month': days_in_this_month,
            'total_month_days': month_last_day,
            'is_complete': is_complete,
            'start_day': actual_start_day,
            'end_day': actual_end_day
        })
        
        # Break if we've reached the end month
        if current_year == service_end_nepali.year and current_month == service_end_nepali.month:
            break
        
        # Move to next month
        if current_month == 12:
            current_month = 1
            current_year += 1
        else:
            current_month += 1
    
    # Calculate summary
    total_months = len(month_distribution)
    complete_months = sum(1 for m in month_distribution if m['is_complete'])
    
    return {
        'total_months': total_months,
        'complete_months': complete_months,
        'month_distribution': month_distribution
    }


# def calculate_nepali_monthly_amount(
#     doc, item, last_gl_entry, start_date, end_date, 
#     total_days, total_booking_days, account_currency
# ):
#     """
#     ✅ COMPLETELY REWRITTEN
    
#     Calculate monthly amount using EQUAL distribution for complete months
#     and proportional distribution for partial months
    
#     LOGIC:
#     1. Identify all months in service period
#     2. Count complete months vs partial months
#     3. For complete months: divide amount equally
#     4. For partial months: prorate by (days_used / total_days_in_that_month)
#     """
    
#     amount, base_amount = 0, 0
    
#     if not last_gl_entry:
#         # Get month distribution for entire service period
#         period_info = calculate_service_period_months(
#             item.service_start_date, 
#             item.service_end_date
#         )
        
#         total_months = period_info['total_months']
#         complete_months = period_info['complete_months']
#         month_distribution = period_info['month_distribution']
        
#         # Calculate base monthly amount for complete months
#         # Formula: Total Amount / Total Months (treating all months equally first)
#         base_monthly_amount = flt(item.base_net_amount / total_months, item.precision("base_net_amount"))
        
#         # Now adjust for partial months
#         # Complete months get full share, partial months get prorated share
        
#         # Calculate total weight
#         total_weight = 0
#         for month_info in month_distribution:
#             if month_info['is_complete']:
#                 total_weight += 1.0  # Complete month = weight 1.0
#             else:
#                 # Partial month = weight based on days used vs total days in that month
#                 weight = flt(month_info['days_in_month']) / flt(month_info['total_month_days'])
#                 total_weight += weight
        
#         # Amount per "weight unit"
#         amount_per_weight = flt(item.base_net_amount / total_weight, item.precision("base_net_amount"))
        
#         # Now find which month we're currently booking
#         start_nepali = nepali_datetime.date.from_datetime_date(start_date)
#         end_nepali = nepali_datetime.date.from_datetime_date(end_date)
        
#         # Find the current month in distribution
#         current_month_info = None
#         for month_info in month_distribution:
#             if month_info['year'] == start_nepali.year and month_info['month'] == start_nepali.month:
#                 current_month_info = month_info
#                 break
        
#         if current_month_info:
#             if current_month_info['is_complete']:
#                 # Complete month - book full share
#                 base_amount = amount_per_weight
#             else:
#                 # Partial month - book prorated share
#                 weight = flt(current_month_info['days_in_month']) / flt(current_month_info['total_month_days'])
#                 base_amount = flt(amount_per_weight * weight, item.precision("base_net_amount"))
            
#             # Prevent over-booking
#             already_booked_amount, already_booked_amount_in_account_currency = get_already_booked_amount(
#                 doc, item
#             )
            
#             if base_amount + already_booked_amount > item.base_net_amount:
#                 base_amount = item.base_net_amount - already_booked_amount
            
#             # Handle multi-currency
#             if account_currency == doc.company_currency:
#                 amount = base_amount
#             else:
#                 # Apply same logic to foreign currency amount
#                 fc_amount_per_weight = flt(item.net_amount / total_weight, item.precision("net_amount"))
                
#                 if current_month_info['is_complete']:
#                     amount = fc_amount_per_weight
#                 else:
#                     weight = flt(current_month_info['days_in_month']) / flt(current_month_info['total_month_days'])
#                     amount = flt(fc_amount_per_weight * weight, item.precision("net_amount"))
                
#                 if amount + already_booked_amount_in_account_currency > item.net_amount:
#                     amount = item.net_amount - already_booked_amount_in_account_currency
    
#     else:
#         # Last entry - book exact remaining balance
#         already_booked_amount, already_booked_amount_in_account_currency = get_already_booked_amount(
#             doc, item
#         )
        
#         base_amount = flt(item.base_net_amount - already_booked_amount, item.precision("base_net_amount"))
        
#         if account_currency == doc.company_currency:
#             amount = base_amount
#         else:
#             amount = flt(
#                 item.net_amount - already_booked_amount_in_account_currency, 
#                 item.precision("net_amount")
#             )
    
#     return amount, base_amount

# def calculate_nepali_monthly_amount(
#     doc, item, last_gl_entry, start_date, end_date, 
#     total_days, total_booking_days, account_currency
# ):
#     """
#     ✅ NEW SIMPLIFIED ALGORITHM
    
#     Logic:
#     1. Calculate per_month_amount = Total Amount / (Total Months - 1)
#     2. For COMPLETE months: Book per_month_amount
#     3. For FIRST partial month: 
#        - Get first month consumed days + last month consumed days = total_partial_days
#        - Prorate using (first_month_days / total_partial_days) * per_month_amount
#     4. For LAST month: Book remaining balance to avoid overbooking
#     """
    
#     amount, base_amount = 0, 0
    
#     if not last_gl_entry:
#         # Get month distribution for entire service period
#         period_info = calculate_service_period_months(
#             item.service_start_date, 
#             item.service_end_date
#         )
        
#         total_months = period_info['total_months']
#         month_distribution = period_info['month_distribution']
        
#         # ✅ IMPORTANT: For calculation, use (total_months - 1)
#         # Because if service spans 6 calendar months, it's actually 5 month periods
#         calculation_months = total_months - 1 if total_months > 1 else 1
        
#         # ✅ Step 1: Calculate per-month amount (simple division)
#         per_month_base_amount = flt(
#             item.base_net_amount / calculation_months, 
#             item.precision("base_net_amount")
#         )
        
#         # ✅ Get first and last month info for prorate calculation
#         first_month_info = month_distribution[0]
#         last_month_info = month_distribution[-1]
        
#         # Calculate total partial days (first month + last month consumed days)
#         first_month_days = first_month_info['days_in_month']
#         last_month_days = last_month_info['days_in_month']
#         total_partial_days = first_month_days + last_month_days
        
#         frappe.logger().info(
#             f"Total calendar months: {total_months}, "
#             f"Calculation months: {calculation_months}, "
#             f"Per-month amount: {per_month_base_amount}, "
#             f"First month days: {first_month_days}, "
#             f"Last month days: {last_month_days}, "
#             f"Total partial days: {total_partial_days}"
#         )
        
#         # Find which month we're currently booking
#         start_nepali = nepali_datetime.date.from_datetime_date(start_date)
        
#         current_month_info = None
#         current_month_index = None
        
#         for idx, month_info in enumerate(month_distribution):
#             if month_info['year'] == start_nepali.year and month_info['month'] == start_nepali.month:
#                 current_month_info = month_info
#                 current_month_index = idx
#                 break
        
#         if current_month_info:
#             # ✅ Step 2: Determine booking amount based on month type
            
#             if current_month_info['is_complete']:
#                 # Complete month - book full per-month amount
#                 base_amount = per_month_base_amount
#                 frappe.logger().info(
#                     f"Complete month: {current_month_info['month_name']} - "
#                     f"Booking full per-month amount: {base_amount}"
#                 )
            
#             elif current_month_index == 0:
#                 # ✅ FIRST partial month - prorate based on first month days / total partial days
#                 if not first_month_info['is_complete'] and not last_month_info['is_complete']:
#                     # Both first and last are partial
#                     prorate_factor = flt(first_month_days) / flt(total_partial_days)
#                     base_amount = flt(
#                         per_month_base_amount * prorate_factor, 
#                         item.precision("base_net_amount")
#                     )
#                     frappe.logger().info(
#                         f"First partial month: {current_month_info['month_name']} - "
#                         f"Days: {first_month_days} / Total partial days: {total_partial_days} - "
#                         f"Prorate factor: {prorate_factor:.4f} - Amount: {base_amount}"
#                     )
#                 else:
#                     # Only first month is partial (last is complete)
#                     prorate_factor = flt(first_month_days) / flt(first_month_info['total_month_days'])
#                     base_amount = flt(
#                         per_month_base_amount * prorate_factor, 
#                         item.precision("base_net_amount")
#                     )
#                     frappe.logger().info(
#                         f"First partial month (last complete): {current_month_info['month_name']} - "
#                         f"Days: {first_month_days}/{first_month_info['total_month_days']} - "
#                         f"Prorate factor: {prorate_factor:.4f} - Amount: {base_amount}"
#                     )
            
#             else:
#                 # Middle or last partial month (not first)
#                 # Book full per-month amount, will be corrected in last entry
#                 base_amount = per_month_base_amount
#                 frappe.logger().info(
#                     f"Partial month (not first): {current_month_info['month_name']} - "
#                     f"Booking full per-month amount: {base_amount}"
#                 )
            
#             # ✅ Step 3: Check for overbooking
#             already_booked_amount, already_booked_amount_in_account_currency = get_already_booked_amount(
#                 doc, item
#             )
            
#             if base_amount + already_booked_amount > item.base_net_amount:
#                 base_amount = item.base_net_amount - already_booked_amount
#                 frappe.logger().warning(
#                     f"Overbooking prevented! Adjusted to remaining: {base_amount}"
#                 )
            
#             # ✅ Step 4: Handle multi-currency
#             if account_currency == doc.company_currency:
#                 amount = base_amount
#             else:
#                 # Apply same logic to foreign currency
#                 per_month_fc_amount = flt(
#                     item.net_amount / calculation_months, 
#                     item.precision("net_amount")
#                 )
                
#                 if current_month_info['is_complete']:
#                     amount = per_month_fc_amount
#                 elif current_month_index == 0:
#                     # First partial month - same prorate logic
#                     if not first_month_info['is_complete'] and not last_month_info['is_complete']:
#                         prorate_factor = flt(first_month_days) / flt(total_partial_days)
#                     else:
#                         prorate_factor = flt(first_month_days) / flt(first_month_info['total_month_days'])
#                     amount = flt(per_month_fc_amount * prorate_factor, item.precision("net_amount"))
#                 else:
#                     amount = per_month_fc_amount
                
#                 # Check overbooking for foreign currency
#                 if amount + already_booked_amount_in_account_currency > item.net_amount:
#                     amount = item.net_amount - already_booked_amount_in_account_currency
    
#     else:
#         # ✅ LAST ENTRY - Book exact remaining balance to ensure accuracy
#         already_booked_amount, already_booked_amount_in_account_currency = get_already_booked_amount(
#             doc, item
#         )
        
#         base_amount = flt(
#             item.base_net_amount - already_booked_amount, 
#             item.precision("base_net_amount")
#         )
        
#         if account_currency == doc.company_currency:
#             amount = base_amount
#         else:
#             amount = flt(
#                 item.net_amount - already_booked_amount_in_account_currency, 
#                 item.precision("net_amount")
#             )
        
#         frappe.logger().info(
#             f"LAST ENTRY - Booking remaining balance: {base_amount} "
#             f"(Total: {item.base_net_amount}, Already booked: {already_booked_amount})"
#         )
    
#     return amount, base_amount




# def get_nepali_booking_dates(doc, item, posting_date=None, prev_posting_date=None):
#     """
#     Get booking dates using NEPALI month boundaries
#     """
    
#     if not posting_date:
#         posting_date = add_days(today(), -1)
    
#     last_gl_entry = False
    
#     deferred_account = (
#         "deferred_revenue_account" if doc.doctype == "Sales Invoice" else "deferred_expense_account"
#     )
    
#     if not prev_posting_date:
#         # Check for previous GL entries
#         prev_gl_entry = frappe.db.sql(
#             """
#             SELECT name, posting_date FROM `tabGL Entry` 
#             WHERE company=%s AND account=%s AND voucher_type=%s 
#             AND voucher_no=%s AND voucher_detail_no=%s AND is_cancelled = 0
#             ORDER BY posting_date DESC LIMIT 1
#             """,
#             (doc.company, item.get(deferred_account), doc.doctype, doc.name, item.name),
#             as_dict=True,
#         )
        
#         prev_gl_via_je = frappe.db.sql(
#             """
#             SELECT p.name, p.posting_date FROM `tabJournal Entry` p, `tabJournal Entry Account` c
#             WHERE p.name = c.parent AND p.company=%s AND c.account=%s
#             AND c.reference_type=%s AND c.reference_name=%s AND c.reference_detail_no=%s 
#             AND c.docstatus < 2 ORDER BY posting_date DESC LIMIT 1
#             """,
#             (doc.company, item.get(deferred_account), doc.doctype, doc.name, item.name),
#             as_dict=True,
#         )
        
#         if prev_gl_via_je:
#             if (not prev_gl_entry) or (
#                 prev_gl_entry and prev_gl_entry[0].posting_date < prev_gl_via_je[0].posting_date
#             ):
#                 prev_gl_entry = prev_gl_via_je
        
#         if prev_gl_entry:
#             start_date = getdate(add_days(prev_gl_entry[0].posting_date, 1))
#         else:
#             start_date = item.service_start_date
#     else:
#         start_date = getdate(add_days(prev_posting_date, 1))
    
#     # Convert start_date to Nepali
#     start_nepali = nepali_datetime.date.from_datetime_date(start_date)
    
#     # Calculate last day of THIS Nepali month
#     if start_nepali.month == 12:
#         next_month_first_nepali = nepali_datetime.date(start_nepali.year + 1, 1, 1)
#     else:
#         next_month_first_nepali = nepali_datetime.date(start_nepali.year, start_nepali.month + 1, 1)
    
#     next_month_first_gregorian = next_month_first_nepali.to_datetime_date()
#     end_date = next_month_first_gregorian - timedelta(days=1)
    
#     # Check if we've reached service end
#     if end_date >= item.service_end_date:
#         end_date = item.service_end_date
#         last_gl_entry = True
#     elif item.service_stop_date and end_date >= item.service_stop_date:
#         end_date = item.service_stop_date
#         last_gl_entry = True
    
#     # Don't go beyond posting date
#     if end_date > getdate(posting_date):
#         end_date = posting_date
    
#     if getdate(start_date) <= getdate(end_date):
#         return start_date, end_date, last_gl_entry
#     else:
#         return None, None, None



def calculate_nepali_monthly_amount(
    doc, item, last_gl_entry, start_date, end_date, 
    total_days, total_booking_days, account_currency
):
    """
    ✅ NEPALI DEFERRED ACCOUNTING CALCULATION
    
    Logic:
    1. Determine calculation_months based on whether first/last months are complete:
       - If BOTH first AND last are partial: calculation_months = total_months - 1
       - Otherwise: calculation_months = total_months
    2. Calculate per_month_amount = Total Amount / calculation_months
    3. For COMPLETE months: Book per_month_amount
    4. For FIRST partial month: 
       - If both first and last are partial: Prorate using (first_month_days / total_partial_days) * per_month_amount
       - If only first is partial: Prorate using (first_month_days / total_days_in_first_month) * per_month_amount
    5. For LAST month: Book exact remaining balance to avoid overbooking
    
    Examples:
    - Baishak 5 to Ashwin 5 (both partial): Divide by 5, prorate first month by 28/33
    - Baishak 1 to Ashwin 30 (both complete): Divide by 6, all months equal
    - Baishak 1 to Ashwin 5 (first complete, last partial): Divide by 6, first month full
    - Baishak 5 to Ashwin 30 (first partial, last complete): Divide by 6, prorate first month
    """
    
    amount, base_amount = 0, 0
    
    if not last_gl_entry:
        # Get month distribution for entire service period
        period_info = calculate_service_period_months(
            item.service_start_date, 
            item.service_end_date
        )
        
        total_months = period_info['total_months']
        month_distribution = period_info['month_distribution']
        
        # Get first and last month info for calculation
        first_month_info = month_distribution[0]
        last_month_info = month_distribution[-1]
        
        # Calculate consumed days in first and last months
        first_month_days = first_month_info['days_in_month']
        last_month_days = last_month_info['days_in_month']
        total_partial_days = first_month_days + last_month_days
        
        # ✅ CRITICAL: Determine calculation months based on whether months are complete
        if not first_month_info['is_complete'] and not last_month_info['is_complete']:
            # Both first and last are partial - use (total_months - 1)
            # Example: Baishak 5 to Ashwin 5 = 6 calendar months but only 5 month periods
            calculation_months = total_months - 1 if total_months > 1 else 1
            frappe.logger().info(
                f"Both endpoints partial - using calculation_months = {calculation_months} (total: {total_months})"
            )
        else:
            # At least one endpoint is complete - use total_months
            # Examples:
            # - Baishak 1 to Ashwin 30 (both complete) = 6 months, divide by 6
            # - Baishak 1 to Ashwin 5 (first complete) = 6 months, divide by 6
            # - Baishak 5 to Ashwin 30 (last complete) = 6 months, divide by 6
            calculation_months = total_months
            frappe.logger().info(
                f"At least one endpoint complete - using calculation_months = {calculation_months}"
            )
        
        # ✅ Step 1: Calculate per-month amount (simple division)
        per_month_base_amount = flt(
            item.base_net_amount / calculation_months, 
            item.precision("base_net_amount")
        )
        
        frappe.logger().info(
            f"Total calendar months: {total_months}, "
            f"Calculation months: {calculation_months}, "
            f"Per-month amount: {per_month_base_amount}, "
            f"First month days: {first_month_days} (complete: {first_month_info['is_complete']}), "
            f"Last month days: {last_month_days} (complete: {last_month_info['is_complete']}), "
            f"Total partial days: {total_partial_days}"
        )
        
        # Find which month we're currently booking
        start_nepali = nepali_datetime.date.from_datetime_date(start_date)
        
        current_month_info = None
        current_month_index = None
        
        for idx, month_info in enumerate(month_distribution):
            if month_info['year'] == start_nepali.year and month_info['month'] == start_nepali.month:
                current_month_info = month_info
                current_month_index = idx
                break
        
        if current_month_info:
            # ✅ Step 2: Determine booking amount based on month type
            
            if current_month_info['is_complete']:
                # Complete month - book full per-month amount
                base_amount = per_month_base_amount
                frappe.logger().info(
                    f"Complete month: {current_month_info['month_name']} - "
                    f"Booking full per-month amount: {base_amount}"
                )
            
            elif current_month_index == 0:
                # ✅ FIRST partial month - apply appropriate prorate logic
                if not first_month_info['is_complete'] and not last_month_info['is_complete']:
                    # Both first and last are partial
                    # Prorate based on: first_month_days / (first_month_days + last_month_days)
                    prorate_factor = flt(first_month_days) / flt(total_partial_days)
                    base_amount = flt(
                        per_month_base_amount * prorate_factor, 
                        item.precision("base_net_amount")
                    )
                    frappe.logger().info(
                        f"First partial month (both partial): {current_month_info['month_name']} - "
                        f"Days: {first_month_days} / Total partial days: {total_partial_days} - "
                        f"Prorate factor: {prorate_factor:.4f} - Amount: {base_amount}"
                    )
                else:
                    # Only first month is partial (last is complete)
                    # Prorate based on: first_month_days / total_days_in_first_month
                    prorate_factor = flt(first_month_days) / flt(first_month_info['total_month_days'])
                    base_amount = flt(
                        per_month_base_amount * prorate_factor, 
                        item.precision("base_net_amount")
                    )
                    frappe.logger().info(
                        f"First partial month (last complete): {current_month_info['month_name']} - "
                        f"Days: {first_month_days}/{first_month_info['total_month_days']} - "
                        f"Prorate factor: {prorate_factor:.4f} - Amount: {base_amount}"
                    )
            
            else:
                # Middle or other partial month (not first)
                # Book full per-month amount, will be corrected in last entry
                base_amount = per_month_base_amount
                frappe.logger().info(
                    f"Month (not first): {current_month_info['month_name']} - "
                    f"Booking full per-month amount: {base_amount}"
                )
            
            # ✅ Step 3: Check for overbooking
            already_booked_amount, already_booked_amount_in_account_currency = get_already_booked_amount(
                doc, item
            )
            
            if base_amount + already_booked_amount > item.base_net_amount:
                base_amount = item.base_net_amount - already_booked_amount
                frappe.logger().warning(
                    f"Overbooking prevented! Adjusted to remaining: {base_amount}"
                )
            
            # ✅ Step 4: Handle multi-currency
            if account_currency == doc.company_currency:
                amount = base_amount
            else:
                # Apply same logic to foreign currency
                per_month_fc_amount = flt(
                    item.net_amount / calculation_months, 
                    item.precision("net_amount")
                )
                
                if current_month_info['is_complete']:
                    amount = per_month_fc_amount
                elif current_month_index == 0:
                    # First partial month - same prorate logic
                    if not first_month_info['is_complete'] and not last_month_info['is_complete']:
                        prorate_factor = flt(first_month_days) / flt(total_partial_days)
                    else:
                        prorate_factor = flt(first_month_days) / flt(first_month_info['total_month_days'])
                    amount = flt(per_month_fc_amount * prorate_factor, item.precision("net_amount"))
                else:
                    amount = per_month_fc_amount
                
                # Check overbooking for foreign currency
                if amount + already_booked_amount_in_account_currency > item.net_amount:
                    amount = item.net_amount - already_booked_amount_in_account_currency
    
    else:
        # ✅ LAST ENTRY - Book exact remaining balance to ensure accuracy
        already_booked_amount, already_booked_amount_in_account_currency = get_already_booked_amount(
            doc, item
        )
        
        base_amount = flt(
            item.base_net_amount - already_booked_amount, 
            item.precision("base_net_amount")
        )
        
        if account_currency == doc.company_currency:
            amount = base_amount
        else:
            amount = flt(
                item.net_amount - already_booked_amount_in_account_currency, 
                item.precision("net_amount")
            )
        
        frappe.logger().info(
            f"LAST ENTRY - Booking remaining balance: {base_amount} "
            f"(Total: {item.base_net_amount}, Already booked: {already_booked_amount})"
        )
    
    return amount, base_amount



def get_nepali_booking_dates(doc, item, posting_date=None, prev_posting_date=None):
    """
    Get booking dates using NEPALI month boundaries
    """
    logger = frappe.logger("deferred_revenue", allow_site=True, file_count=50)
    
    # Log function entry
    logger.info(f"=== Starting get_nepali_booking_dates ===")
    logger.info(f"Document: {doc.doctype} - {doc.name}")
    logger.info(f"Item: {item.name}, Service Period: {item.service_start_date} to {item.service_end_date}")
    logger.info(f"Posting Date: {posting_date}, Previous Posting Date: {prev_posting_date}")
    
    if not posting_date:
        posting_date = add_days(today(), -1)
        logger.info(f"No posting_date provided, using yesterday: {posting_date}")
    
    last_gl_entry = False
    
    deferred_account = (
        "deferred_revenue_account" if doc.doctype == "Sales Invoice" else "deferred_expense_account"
    )
    logger.info(f"Using deferred account type: {deferred_account}")
    logger.info(f"Deferred account value: {item.get(deferred_account)}")
    
    if not prev_posting_date:
        logger.info("No prev_posting_date provided, checking for previous GL entries...")
        
        # Check for previous GL entries
        prev_gl_entry = frappe.db.sql(
            """
            SELECT name, posting_date FROM `tabGL Entry` 
            WHERE company=%s AND account=%s AND voucher_type=%s 
            AND voucher_no=%s AND voucher_detail_no=%s AND is_cancelled = 0
            ORDER BY posting_date DESC LIMIT 1
            """,
            (doc.company, item.get(deferred_account), doc.doctype, doc.name, item.name),
            as_dict=True,
        )
        
        if prev_gl_entry:
            logger.info(f"Found previous GL Entry: {prev_gl_entry[0].name}, Date: {prev_gl_entry[0].posting_date}")
        else:
            logger.info("No previous GL Entry found")
        
        # Check for previous Journal Entries
        prev_gl_via_je = frappe.db.sql(
            """
            SELECT p.name, p.posting_date FROM `tabJournal Entry` p, `tabJournal Entry Account` c
            WHERE p.name = c.parent AND p.company=%s AND c.account=%s
            AND c.reference_type=%s AND c.reference_name=%s AND c.reference_detail_no=%s 
            AND c.docstatus < 2 ORDER BY posting_date DESC LIMIT 1
            """,
            (doc.company, item.get(deferred_account), doc.doctype, doc.name, item.name),
            as_dict=True,
        )
        
        if prev_gl_via_je:
            logger.info(f"Found previous Journal Entry: {prev_gl_via_je[0].name}, Date: {prev_gl_via_je[0].posting_date}")
            
            if (not prev_gl_entry) or (
                prev_gl_entry and prev_gl_entry[0].posting_date < prev_gl_via_je[0].posting_date
            ):
                logger.info("Using Journal Entry as it's more recent than GL Entry")
                prev_gl_entry = prev_gl_via_je
        else:
            logger.info("No previous Journal Entry found")
        
        if prev_gl_entry:
            start_date = getdate(add_days(prev_gl_entry[0].posting_date, 1))
            logger.info(f"Start date set to day after previous entry: {start_date}")
        else:
            start_date = item.service_start_date
            logger.info(f"No previous entries, using service_start_date: {start_date}")
    else:
        start_date = getdate(add_days(prev_posting_date, 1))
        logger.info(f"Using day after prev_posting_date as start_date: {start_date}")
    
    # Convert start_date to Nepali
    start_nepali = nepali_datetime.date.from_datetime_date(start_date)
    logger.info(f"Converted to Nepali date: {start_nepali} (Year: {start_nepali.year}, Month: {start_nepali.month}, Day: {start_nepali.day})")
    
    # Calculate last day of THIS Nepali month
    if start_nepali.month == 12:
        next_month_first_nepali = nepali_datetime.date(start_nepali.year + 1, 1, 1)
        logger.info(f"Current month is 12, next month is: {next_month_first_nepali} (new year)")
    else:
        next_month_first_nepali = nepali_datetime.date(start_nepali.year, start_nepali.month + 1, 1)
        logger.info(f"Next month first day (Nepali): {next_month_first_nepali}")
    
    next_month_first_gregorian = next_month_first_nepali.to_datetime_date()
    end_date = next_month_first_gregorian - timedelta(days=1)
    logger.info(f"Calculated month end date (Gregorian): {end_date}")
    
    # Check if we've reached service end
    if end_date >= item.service_end_date:
        logger.info(f"End date {end_date} >= service_end_date {item.service_end_date}, using service_end_date")
        end_date = item.service_end_date
        last_gl_entry = True
        logger.info("This will be the LAST GL entry for this item")
    elif item.service_stop_date and end_date >= item.service_stop_date:
        logger.info(f"End date {end_date} >= service_stop_date {item.service_stop_date}, using service_stop_date")
        end_date = item.service_stop_date
        last_gl_entry = True
        logger.info("This will be the LAST GL entry for this item (due to stop date)")
    
    # Don't go beyond posting date
    if end_date > getdate(posting_date):
        logger.info(f"End date {end_date} > posting_date {posting_date}, adjusting to posting_date")
        end_date = posting_date
    
    # Final validation
    if getdate(start_date) <= getdate(end_date):
        logger.info(f"=== Result: Valid date range ===")
        logger.info(f"Start Date: {start_date}")
        logger.info(f"End Date: {end_date}")
        logger.info(f"Last GL Entry: {last_gl_entry}")
        logger.info(f"Days in period: {(getdate(end_date) - getdate(start_date)).days + 1}")
        return start_date, end_date, last_gl_entry
    else:
        logger.warning(f"=== Result: INVALID date range ===")
        logger.warning(f"Start Date {start_date} > End Date {end_date}")
        logger.warning("Returning None values")
        return None, None, None










def make_nepali_gl_entries(
    doc, credit_account, debit_account, against, amount, base_amount,
    posting_date, project, account_currency, cost_center, item, deferred_process=None
):
    """
    Create GL entries for Nepali deferred accounting
    """
    
    if amount == 0:
        return
    
    gl_entries = []
    
    # Credit entry
    gl_entries.append(
        doc.get_gl_dict(
            {
                "account": credit_account,
                "against": against,
                "credit": base_amount,
                "credit_in_account_currency": amount,
                "cost_center": cost_center,
                "voucher_detail_no": item.name,
                "posting_date": posting_date,
                "project": project,
                "against_voucher_type": "Process Deferred Accounting",
                "against_voucher": deferred_process,
            },
            account_currency,
            item=item,
        )
    )
    
    # Debit entry
    gl_entries.append(
        doc.get_gl_dict(
            {
                "account": debit_account,
                "against": against,
                "debit": base_amount,
                "debit_in_account_currency": amount,
                "cost_center": cost_center,
                "voucher_detail_no": item.name,
                "posting_date": posting_date,
                "project": project,
                "against_voucher_type": "Process Deferred Accounting",
                "against_voucher": deferred_process,
            },
            account_currency,
            item=item,
        )
    )
    
    if gl_entries:
        try:
            make_gl_entries(gl_entries, cancel=(doc.docstatus == 2), merge_entries=True)
            frappe.db.commit()
        except Exception as e:
            if frappe.flags.in_test:
                doc.log_error(f"Error while processing deferred accounting for Invoice {doc.name}")
                raise e
            else:
                frappe.db.rollback()
                doc.log_error(f"Error while processing deferred accounting for Invoice {doc.name}")
                frappe.flags.deferred_accounting_error = True


# def book_nepali_deferred_income_or_expense(doc, deferred_process, posting_date=None):
#     """
#     Book deferred income or expense using Nepali month boundaries
#     """

#     frappe.logger().info(f"inside booking nepali deferred invoice or expense")

#     enable_check = "enable_deferred_revenue" if doc.doctype == "Sales Invoice" else "enable_deferred_expense"
#     accounts_frozen_upto = frappe.db.get_single_value("Accounts Settings", "acc_frozen_upto")

#     def _book_deferred_revenue_or_expense(
#         item, via_journal_entry, submit_journal_entry, 
#         book_deferred_entries_based_on, prev_posting_date=None
#     ):
#         start_date, end_date, last_gl_entry = get_nepali_booking_dates(
#             doc, item, posting_date=posting_date, prev_posting_date=prev_posting_date
#         )
        
#         if not (start_date and end_date):
#             return
        
#         account_currency = get_account_currency(item.expense_account or item.income_account)
        
#         if doc.doctype == "Sales Invoice":
#             against, project = doc.customer, doc.project
#             credit_account, debit_account = item.income_account, item.deferred_revenue_account
#         else:
#             against, project = doc.supplier, item.project
#             credit_account, debit_account = item.deferred_expense_account, item.expense_account
        
#         total_days = date_diff(item.service_end_date, item.service_start_date) + 1
#         total_booking_days = date_diff(end_date, start_date) + 1
        
#         # Always use monthly calculation with equal distribution
#         amount, base_amount = calculate_nepali_monthly_amount(
#             doc, item, last_gl_entry, start_date, end_date,
#             total_days, total_booking_days, account_currency
#         )
        
#         if not amount:
#             prev_posting_date = end_date
#         else:
#             gl_posting_date = end_date
#             prev_posting_date = None
            
#             # Check if books are frozen
#             if accounts_frozen_upto and getdate(end_date) <= getdate(accounts_frozen_upto):
#                 from frappe.utils import get_last_day
#                 gl_posting_date = get_last_day(add_days(accounts_frozen_upto, 1))
#                 prev_posting_date = end_date
            
#             if via_journal_entry:
#                 book_revenue_via_journal_entry(
#                     doc, credit_account, debit_account, amount, base_amount,
#                     gl_posting_date, project, account_currency, item.cost_center,
#                     item, deferred_process, submit_journal_entry
#                 )
#             else:
#                 make_nepali_gl_entries(
#                     doc, credit_account, debit_account, against, amount, base_amount,
#                     gl_posting_date, project, account_currency, item.cost_center,
#                     item, deferred_process
#                 )
        
#         if frappe.flags.deferred_accounting_error:
#             return
        
#         # Recursive call for next period
#         if getdate(end_date) < getdate(posting_date) and not last_gl_entry:
#             _book_deferred_revenue_or_expense(
#                 item, via_journal_entry, submit_journal_entry,
#                 book_deferred_entries_based_on, prev_posting_date
#             )
    
#     via_journal_entry = cint(
#         frappe.db.get_singles_value("Accounts Settings", "book_deferred_entries_via_journal_entry")
#     )
#     submit_journal_entry = cint(
#         frappe.db.get_singles_value("Accounts Settings", "submit_journal_entries")
#     )
#     book_deferred_entries_based_on = frappe.db.get_singles_value(
#         "Accounts Settings", "book_deferred_entries_based_on"
#     )
    
#     for item in doc.get("items"):
#         if item.get(enable_check):
#             frappe.logger(item.name, via_journal_entry, submit_journal_entry, book_deferred_entries_based_on)
#             _book_deferred_revenue_or_expense(
#                 item, via_journal_entry, submit_journal_entry, book_deferred_entries_based_on
#             )






def book_nepali_deferred_income_or_expense(doc, deferred_process, posting_date=None):
    """
    Book deferred income or expense using Nepali month boundaries
    """
    frappe.logger().info(f"Starting Nepali deferred booking for {doc.doctype} {doc.name}")
    
    enable_check = "enable_deferred_revenue" if doc.doctype == "Sales Invoice" else "enable_deferred_expense"
    accounts_frozen_upto = frappe.db.get_single_value("Accounts Settings", "acc_frozen_upto")
    
    def _book_deferred_revenue_or_expense(
        item, via_journal_entry, submit_journal_entry, 
        book_deferred_entries_based_on, prev_posting_date=None
    ):
        frappe.logger().info(f"Processing item: {item.name}, prev_posting_date: {prev_posting_date}")
        
        try:
            # Get booking dates
            start_date, end_date, last_gl_entry = get_nepali_booking_dates(
                doc, item, posting_date=posting_date, prev_posting_date=prev_posting_date
            )
            frappe.logger().info(f"Dates - start: {start_date}, end: {end_date}, last_gl: {last_gl_entry}")
            
            if not (start_date and end_date):
                frappe.logger().info(f"No booking dates for item {item.name}, skipping")
                return
            
            # Get account details
            account_currency = get_account_currency(item.expense_account or item.income_account)
            
            if doc.doctype == "Sales Invoice":
                against, project = doc.customer, doc.project
                credit_account, debit_account = item.income_account, item.deferred_revenue_account
            else:
                against, project = doc.supplier, item.project
                credit_account, debit_account = item.deferred_expense_account, item.expense_account
            
            frappe.logger().info(f"Accounts - credit: {credit_account}, debit: {debit_account}")
            
            # Calculate days and amounts
            total_days = date_diff(item.service_end_date, item.service_start_date) + 1
            total_booking_days = date_diff(end_date, start_date) + 1
            
            frappe.logger().info(f"Calling calculate_nepali_monthly_amount...")
            amount, base_amount = calculate_nepali_monthly_amount(
                doc, item, last_gl_entry, start_date, end_date,
                total_days, total_booking_days, account_currency
            )
            frappe.logger().info(f"Calculated amounts - amount: {amount}, base_amount: {base_amount}")
            
            if not amount:
                frappe.logger().info(f"No amount to book for item {item.name}")
                prev_posting_date = end_date
            else:
                gl_posting_date = end_date
                prev_posting_date = None
                
                # Check if books are frozen
                if accounts_frozen_upto and getdate(end_date) <= getdate(accounts_frozen_upto):
                    frappe.logger().info(f"Books frozen, adjusting date from {end_date}")
                    gl_posting_date = get_last_day(add_days(accounts_frozen_upto, 1))
                    prev_posting_date = end_date
                    frappe.logger().info(f"Adjusted gl_posting_date: {gl_posting_date}")
                
                # Book the entry
                frappe.logger().info(f"Booking entry with gl_posting_date: {gl_posting_date}")
                if via_journal_entry == 1 or via_journal_entry == 0:
                    frappe.logger().info("Creating journal entry...")
                    book_revenue_via_journal_entry(
                        doc, credit_account, debit_account, amount, base_amount,
                        gl_posting_date, project, account_currency, item.cost_center,
                        item, deferred_process, submit_journal_entry
                    )
                    frappe.logger().info("Journal entry created successfully")
                else:
                    frappe.logger().info("Creating GL entries...")
                    make_nepali_gl_entries(
                        doc, credit_account, debit_account, against, amount, base_amount,
                        gl_posting_date, project, account_currency, item.cost_center,
                        item, deferred_process
                    )
                    frappe.logger().info("GL entries created successfully")
                
                # Check for errors
                if frappe.flags.deferred_accounting_error:
                    frappe.logger().error("Deferred accounting error flag set, stopping")
                    return
                
                # Recursive call for next period
                if getdate(end_date) < getdate(posting_date) and not last_gl_entry:
                    frappe.logger().info(f"Making recursive call with prev_posting_date: {prev_posting_date}")
                    _book_deferred_revenue_or_expense(
                        item, via_journal_entry, submit_journal_entry,
                        book_deferred_entries_based_on, prev_posting_date
                    )
                else:
                    frappe.logger().info("Booking complete for this item")
        
        except Exception as e:
            frappe.logger().error(f"Error processing item {item.name}: {str(e)}")
            frappe.log_error(title=f"Deferred Booking Error - {item.name}", message=frappe.get_traceback())
            raise
    
    # Main execution
    try:
        # Get settings
        frappe.logger().info("Fetching account settings...")
        via_journal_entry = cint(
            frappe.db.get_singles_value("Accounts Settings", "book_deferred_entries_via_journal_entry")
        )
        submit_journal_entry = cint(
            frappe.db.get_singles_value("Accounts Settings", "submit_journal_entries")
        )
        book_deferred_entries_based_on = frappe.db.get_singles_value(
            "Accounts Settings", "book_deferred_entries_based_on"
        )
        frappe.logger().info(f"Settings - via_je: {via_journal_entry}, submit: {submit_journal_entry}, based_on: {book_deferred_entries_based_on}")
        
        # Process items
        processed = 0
        skipped = 0
        for item in doc.get("items"):
            if item.get(enable_check):
                frappe.logger().info(f"Processing deferred item: {item.name}")
                _book_deferred_revenue_or_expense(
                    item, via_journal_entry, submit_journal_entry, book_deferred_entries_based_on
                )
                processed += 1
            else:
                skipped += 1
        
        frappe.logger().info(f"Completed - processed: {processed}, skipped: {skipped}")
    
    except Exception as e:
        frappe.logger().error(f"Fatal error in book_nepali_deferred_income_or_expense: {str(e)}")
        frappe.log_error(title="Nepali Deferred Booking Fatal Error", message=frappe.get_traceback())
        raise






def test_nepali_deferred_accounting_auto():
    """AUTO TEST - Runs every minute for testing"""
    logger = frappe.logger()
    logger.setLevel(logging.INFO)
    
    frappe.logger().info("=" * 60)
    frappe.logger().info("🧪 AUTO TEST: Nepali Deferred Accounting")
    frappe.logger().info("=" * 60)
    
    if not cint(frappe.db.get_singles_value("Accounts Settings", "process_deferred_accounting_in_nepali_month")):
        frappe.logger().info("⚠️  Nepali deferred accounting is DISABLED")
        return
    
    start_date, end_date = get_previous_nepali_month_dates()
    today_nepali = get_today_nepali_date()
    prev_month = today_nepali.month - 1 if today_nepali.month > 1 else 12
    prev_year = today_nepali.year if today_nepali.month > 1 else today_nepali.year - 1
    
    frappe.logger().info(f"📅 Today: {today_nepali}")
    frappe.logger().info(f"📊 Processing: {get_nepali_month_name(prev_month)} {prev_year}")
    frappe.logger().info(f"📆 Period: {start_date} to {end_date}")
    
    companies = frappe.get_all("Company")
    frappe.logger().info(f"🏢 Companies: {len(companies)}")
    
    for company in companies:
        frappe.logger().info(f"\n📍 Processing: {company.name}")
        
        try:
            frappe.logger().info("   💰 Revenue...")
            process_nepali_deferred_revenue(
                company=company.name,
                start_date=start_date,
                end_date=end_date,
                posting_date=end_date
            )
            
            frappe.logger().info("   💸 Expense...")
            process_nepali_deferred_expense(
                company=company.name,
                start_date=start_date,
                end_date=end_date,
                posting_date=end_date
            )
            
            frappe.db.commit()
            frappe.logger().info(f"   ✅ {company.name} completed!")
            
        except Exception as e:
            frappe.logger().error(f"   ❌ {company.name} failed: {str(e)}")
            frappe.log_error(
                title=f"Test Nepali Deferred - {company.name}",
                message=frappe.get_traceback()
            )
            frappe.db.rollback()
    
    frappe.logger().info("=" * 60)
    frappe.logger().info("🎉 AUTO TEST COMPLETED")
    frappe.logger().info("=" * 60)




# def book_revenue_via_journal_entry(
# doc,
# credit_account,
# debit_account,
# amount,
# base_amount,
# posting_date,
# project,
# account_currency,
# cost_center,
# item,
# deferred_process=None,
# submit="No",
# ):
       
#     if amount == 0:
#         return

#     journal_entry = frappe.new_doc("Journal Entry")
#     journal_entry.posting_date = posting_date
#     journal_entry.company = doc.company
#     journal_entry.voucher_type = "Deferred Revenue" if doc.doctype == "Sales Invoice" else "Deferred Expense"
#     journal_entry.process_deferred_accounting = deferred_process

#     debit_entry = {
#         "account": credit_account,
#         "credit": base_amount,
#         "credit_in_account_currency": amount,
#         "account_currency": account_currency,
#         "reference_name": doc.name,
#         "reference_type": doc.doctype,
#         "reference_detail_no": item.name,
#         "cost_center": cost_center,
#         "project": project,
#     }

#     credit_entry = {
#         "account": debit_account,
#         "debit": base_amount,
#         "debit_in_account_currency": amount,
#         "account_currency": account_currency,
#         "reference_name": doc.name,
#         "reference_type": doc.doctype,
#         "reference_detail_no": item.name,
#         "cost_center": cost_center,
#         "project": project,
#     }

#     for dimension in get_accounting_dimensions():
#         debit_entry.update({dimension: item.get(dimension)})

#         credit_entry.update({dimension: item.get(dimension)})

#     journal_entry.append("accounts", debit_entry)
#     journal_entry.append("accounts", credit_entry)

#     try:
#         journal_entry.save()

#         if submit:
#             journal_entry.submit()

#         frappe.db.commit()
#     except Exception:
#         frappe.db.rollback()
#         doc.log_error(f"Error while processing deferred accounting for Invoice {doc.name}")
#         frappe.flags.deferred_accounting_error = True




def book_revenue_via_journal_entry(
    doc,
    credit_account,
    debit_account,
    amount,
    base_amount,
    posting_date,
    project,
    account_currency,
    cost_center,
    item,
    deferred_process=None,
    submit="No",
):
    # Skip zero amount
    if amount == 0:
        frappe.logger().debug(
            f"[SKIPPED] Zero amount | Doc: {doc.doctype} {doc.name} | Item: {item.name}"
        )
        return

    frappe.logger().info(
        f"[START] Deferred JE | Doc: {doc.doctype} {doc.name} | "
        f"Item: {item.name} | Amount: {amount} | Base: {base_amount} | "
        f"Posting Date: {posting_date}"
    )


    journal_entry = frappe.new_doc("Journal Entry")
    journal_entry.posting_date = posting_date
    journal_entry.custom_p_type = "Deferred Accounting"
    random_number = random.sample(range(1, 1_000_000), 1000)
    journal_entry.custom_document_no = random_number[0]
    journal_entry.company = doc.company
    journal_entry.voucher_type = (
        "Deferred Revenue" if doc.doctype == "Sales Invoice" else "Deferred Expense"
    )
    journal_entry.process_deferred_accounting = deferred_process

    debit_entry = {
        "account": credit_account,
        "credit": base_amount,
        "credit_in_account_currency": amount,
        "account_currency": account_currency,
        "reference_name": doc.name,
        "reference_type": doc.doctype,
        "reference_detail_no": item.name,
        "cost_center": cost_center,
        "project": project,
    }

    credit_entry = {
        "account": debit_account,
        "debit": base_amount,
        "debit_in_account_currency": amount,
        "account_currency": account_currency,
        "reference_name": doc.name,
        "reference_type": doc.doctype,
        "reference_detail_no": item.name,
        "cost_center": cost_center,
        "project": project,
    }

    for dimension in get_accounting_dimensions():
        debit_entry[dimension] = item.get(dimension)
        credit_entry[dimension] = item.get(dimension)

    journal_entry.append("accounts", debit_entry)
    journal_entry.append("accounts", credit_entry)

    try:
        journal_entry.save()

        if submit:
            journal_entry.submit()

        frappe.db.commit()

        frappe.logger().info(
            f"[SUCCESS] Deferred JE Created | JE: {journal_entry.name} | "
            f"Doc: {doc.name} | Item: {item.name}"
        )

    except Exception:
        frappe.db.rollback()

        error_trace = frappe.get_traceback()

        frappe.logger().error(
            f"[FAILED] Deferred JE | Doc: {doc.doctype} {doc.name} | "
            f"Item: {item.name}\n{error_trace}"
        )

        doc.log_error(
            title="Deferred Accounting Error",
            message=error_trace
        )

        frappe.flags.deferred_accounting_error = True





