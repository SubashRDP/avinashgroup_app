import frappe
from frappe.utils import flt, getdate, nowdate

_account_cache = {}

def before_save_salesinvoice(doc, method=None):
    """
    Main hook that runs before saving Sales Invoice
    
    Calculation Rules:
    1. Excise Value: ALWAYS MANUAL (never recalculated)
    2. custom_total: net_amount + custom_excise_value
    3. VAT:
        - Percentage (%): ALWAYS recalculated from custom_total * custom_vat_rate / 100
        - Amount: NEVER recalculated (manual entry)
    4. NO TDS in Sales Invoice
    5. Taxes table: Updated with Excise and VAT
    """
    
    # 0. Calculate all item-level and total fields in a single pass
    calculate_all_item_fields(doc)
    
    # 5. Update taxes table
    update_taxes_table(doc)
    
    # 6. Let ERPNext calculate standard totals
    doc.calculate_taxes_and_totals()

    # 8. For return invoices, ensure VAT amounts are negative (must run last)
    apply_return_vat_sign(doc)


def calculate_all_item_fields(doc):
    """
    Single-pass calculation over items for all custom totals and VAT logic.
    """
    total_including_excise = 0
    total_excise = 0
    total_vat = 0
    custom_total_amount = 0

    for item in doc.items:
        if not hasattr(item, "custom_vat_apply_on") or not item.custom_vat_apply_on:
            item.custom_vat_apply_on = "VAT 0%"

        base_net_amount = flt(item.base_net_amount) or 0
        excise_value = flt(item.custom_excise_value) or 0

        item.custom_total = flt(base_net_amount + excise_value, 5)

        vat_apply_on = item.custom_vat_apply_on
        if vat_apply_on == "VAT 13%":
            item.custom_vat_rate = 13
            item.custom_vat_amount = flt((item.custom_total * 13) / 100, 5)
        elif vat_apply_on == "VAT 0%":
            item.custom_vat_rate = 0
            item.custom_vat_amount = 0
        elif vat_apply_on == "Amount":
            item.custom_vat_rate = 0

        total_including_excise += flt(item.custom_total) or 0
        total_excise += excise_value
        total_vat += flt(item.custom_vat_amount) or 0
        custom_total_amount += base_net_amount

    doc.custom_total_amount_including_excise = flt(total_including_excise, 5)
    doc.custom_total_excise_amount = flt(total_excise, 5)
    doc.custom_excise = flt(total_excise, 5)
    doc.custom_total_vat_amount = flt(total_vat, 5)
    doc.custom_total_amount = flt(custom_total_amount, 5)


def update_taxes_table(doc):
    """
    Update or create tax rows in the taxes table
    1. Excise Duty (account starting with 348204) - position 0
    2. VAT (account starting with VAT) - position 1
    NO TDS in Sales Invoice
    """
    total_excise = flt(doc.custom_total_excise_amount) or 0
    total_vat = flt(doc.custom_total_vat_amount) or 0
    
    # Find accounts
    excise_account = find_account_by_prefix(doc.company, "348204")
    vat_account = find_account_by_prefix(doc.company, "VAT")
    
    if not excise_account:
        frappe.logger().warning(
            f"No excise account found starting with 348204 for {doc.company}"
        )
    
    if not vat_account:
        frappe.logger().warning(
            f"No VAT account found starting with VAT for {doc.company}"
        )
    
    position = 0
    

    if excise_account and total_excise != 0:
        update_or_create_tax_row(
            doc,
            account_head=excise_account,
            tax_amount=total_excise,
            position=position,
            description=f"Excise Duty - {doc.company}",
            charge_type="Actual",
            add_deduct="Add"
        )
        position += 1


    if vat_account and total_vat != 0:
        update_or_create_tax_row(
            doc,
            account_head=vat_account,
            tax_amount=total_vat,
            position=position,
            description=f"VAT - {doc.company}",
            charge_type="Actual",
            add_deduct="Add"
        )
        position += 1


def find_account_by_prefix(company, prefix):
    """
    Find account that starts with the given prefix for the company
    """
    key = (company, prefix)
    if key not in _account_cache:
        accounts = frappe.get_all(
            "Account",
            filters={
                "company": company,
                "name": ["like", f"{prefix}%"]
            },
            fields=["name"],
            limit=1
        )
        _account_cache[key] = accounts[0].name if accounts else None

    return _account_cache[key]


def update_or_create_tax_row(doc, account_head, tax_amount, position, 
                             description, charge_type="Actual", add_deduct="Add"):
    """
    Update existing tax row or create new one at specified position
    """
    # Find existing row
    existing_row = None
    existing_index = -1
    
    for idx, tax_row in enumerate(doc.taxes or []):
        if (tax_row.account_head == account_head and 
            tax_row.charge_type == charge_type):
            existing_row = tax_row
            existing_index = idx
            break
    
    if existing_row:
        # Update existing row
        existing_row.tax_amount = tax_amount
        existing_row.base_tax_amount = tax_amount
        existing_row.add_deduct_tax = add_deduct
        existing_row.category = "Total"
        existing_row.included_in_print_rate = 0
        
        # Move to correct position if needed
        if existing_index != position:
            move_tax_row_to_position(doc, existing_index, position)
    else:
        # Create new row
        doc.append("taxes", {
            "charge_type": charge_type,
            "account_head": account_head,
            "description": description,
            "tax_amount": tax_amount,
            "base_tax_amount": tax_amount,
            "add_deduct_tax": add_deduct,
            "category": "Total",
            "included_in_print_rate": 0
        })
        
        # Move to correct position
        new_index = len(doc.taxes) - 1
        if new_index != position and position < len(doc.taxes):
            move_tax_row_to_position(doc, new_index, position)


def move_tax_row_to_position(doc, from_index, to_index):
    """
    Move a tax row from one position to another
    """
    if not doc.taxes or from_index == to_index:
        return
    
    if from_index >= len(doc.taxes) or to_index >= len(doc.taxes):
        return
    
    # Remove from current position
    row = doc.taxes.pop(from_index)
    
    # Insert at new position
    doc.taxes.insert(to_index, row)
    
    # Update idx for all rows
    for idx, tax_row in enumerate(doc.taxes):
        tax_row.idx = idx + 1
    


def validate_salesinvoice(doc, method=None):
    """
    Hook that runs during validation
    """
    # validate_sales_invoice(doc, method)
    validate_custom_fields(doc)


def apply_return_vat_sign(doc):
    """
    For return invoices, force custom_vat_amount negative on each item.
    """
    if not getattr(doc, "is_return", 0):
        return

    for item in doc.items:
        item.custom_vat_amount = -abs(flt(item.custom_vat_amount) or 0)



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
        
        # Early exit: If amount limit check can already fail
        if amount_limit and (total_unpaid + new_invoice_amount) > amount_limit:
            break

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


def validate_custom_fields(doc):
    """
    Validate and set default values for custom fields
    """
    for item in doc.items:
        if not hasattr(item, 'custom_vat_apply_on') or not item.custom_vat_apply_on:
            item.custom_vat_apply_on = 'VAT 13%'
        
        if not hasattr(item, 'custom_vat_rate'):
            item.custom_vat_rate = 0


@frappe.whitelist()
def populate_item_custom_fields(item_code):
    """VAT rate is now determined by custom_vat_apply_on selection (VAT 13% / VAT 0% / Amount).
    No longer fetched from Item Master."""
    return {}
