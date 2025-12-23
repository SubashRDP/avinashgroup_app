import frappe
from frappe import _
from frappe.utils import flt
from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

# def before_save_purchaseinvoice(doc, method=None):
#     """
#     Main hook that runs before saving Purchase Invoice
#     Calculates excise, VAT, TDS, and totals
#     Only calculates if user hasn't manually provided values
#     """
#     # calculate_item_excise_and_totals(doc)
#     calculate_total_excise_amount(doc)
#     calculate_custom_total(doc)
#     calculate_item_vat_amounts(doc)
#     calculate_total_vat_amount(doc)
#     calculate_item_tds_amounts(doc)
#     calculate_total_tds_amount(doc)
#     update_taxes_table(doc)
#     calculate_custom_total_amount(doc)
#     doc.calculate_taxes_and_totals()
def before_save_purchaseinvoice(doc, method=None):
    """
    Final reviewed before_save hook for Purchase Invoice

    Rules:
    - Excise value is manual and NEVER recalculated
    - custom_total = amount + custom_excise_value
    - VAT:
        - Percentage (%) -> ALWAYS recalculated
        - Amount -> NEVER recalculated
    - TDS follows existing logic
    - Taxes table updated after all calculations
    """

    # 1. Calculate item-level totals (manual excise respected)
    calculate_custom_total(doc)

    # 2. VAT calculation (strict rules)
    calculate_item_vat_amounts(doc)
    calculate_total_vat_amount(doc)

    # 3. TDS calculation (unchanged behavior)
    calculate_item_tds_amounts(doc)
    tds_by_account = calculate_total_tds_amount(doc)

    # 4. Excise totals (manual aggregation only)
    calculate_total_excise_amount(doc)

    # 5. Update taxes table (Excise, VAT, TDS)
    update_taxes_table(doc)

    # 6. Let ERPNext finalize standard totals
    doc.calculate_taxes_and_totals()


def calculate_item_excise_and_totals(doc):
    """
    Calculate excise value and total for each item
    Only calculates if custom_excise_value is not manually set
    custom_excise_value = custom_excise_duty * qty
    custom_total = amount + custom_excise_value
    """
    for item in doc.items:
        # Check if this is a new calculation or user provided value
        should_calculate_excise = should_calculate_field(item, 'custom_excise_value')
        
        qty = flt(item.qty) or 0
        amount = flt(item.amount) or 0
        custom_excise_duty = flt(item.custom_excise_duty) or 0
        
        if should_calculate_excise:
            # Calculate excise value
            custom_excise_value = flt(custom_excise_duty * qty, 2)
            item.custom_excise_value = custom_excise_value
        else:
            custom_excise_value = flt(item.custom_excise_value) or 0
            frappe.logger().debug(
                f"Using user-provided excise for {item.item_code}: {custom_excise_value}"
            )
            # Clear custom_excise_duty when value is manual
            if custom_excise_value > 0:
                item.custom_excise_duty = 0
                frappe.logger().debug(
                    f"Manual excise value for {item.item_code}: {custom_excise_value}, cleared custom_excise_duty"
                )
        
        # Always calculate custom_total based on current excise value
        custom_total = flt(amount + custom_excise_value, 2)
        item.custom_total = custom_total

def calculate_custom_total(doc):
    for item in doc.items:
        amount = flt(item.amount) or 0
        excise_value = flt(item.custom_excise_value) or 0
        item.custom_total = flt(amount + excise_value, 2)

def calculate_total_excise_amount(doc):
    total_excise = sum(
        flt(item.custom_excise_value) or 0 for item in doc.items
    )

    doc.custom_total_excise_amount = flt(total_excise, 2)
    doc.custom_excise = flt(total_excise, 2)

# def calculate_total_excise_amount(doc):
#     """
#     Sum all custom_excise_value from items
#     """
#     total_excise_amount = 0
    
#     for item in doc.items:
#         total_excise_amount += flt(item.custom_excise_value) or 0
    
#     doc.custom_total_excise_amount = flt(total_excise_amount, 2)
#     doc.custom_excise = flt(total_excise_amount, 2)


# def calculate_item_vat_amounts(doc):
#     """
#     Calculate VAT amount for each item based on custom_vat_apply_on selection
    
#     If custom_vat_apply_on = 'Percentage (%)':
#         - custom_vat_amount = (custom_total * custom_vat_rate) / 100
#         - custom_vat_rate is visible and editable (from Item Master)
#         - custom_vat_amount is hidden/read-only (auto-calculated)
    
#     If custom_vat_apply_on = 'Amount':
#         - custom_vat_amount is manually entered by user
#         - custom_vat_rate is hidden and forced to 0
#         - No auto-calculation
#     """
#     for item in doc.items:
#         # Default custom_vat_apply_on to 'Percentage (%)' if not set
#         if not hasattr(item, 'custom_vat_apply_on') or not item.custom_vat_apply_on:
#             item.custom_vat_apply_on = 'Percentage (%)'
        
#         vat_apply_on = item.custom_vat_apply_on
        
#         if vat_apply_on == 'Percentage (%)':
#             # VAT Rate % mode - calculate VAT amount
#             should_calculate_vat = should_calculate_field(item, 'custom_vat_amount')
            
#             if should_calculate_vat:
#                 custom_total = flt(item.custom_total) or 0
#                 custom_vat_rate = flt(item.custom_vat_rate) or 0
                
#                 # Calculate VAT amount (custom_vat_rate is percentage)
#                 custom_vat_amount = flt((custom_total * custom_vat_rate) / 100, 2)
#                 item.custom_vat_amount = custom_vat_amount
                
#                 frappe.logger().debug(
#                     f"Calculated VAT for {item.item_code}: "
#                     f"custom_total={custom_total}, vat_rate%={custom_vat_rate}, vat_amount={custom_vat_amount}"
#                 )
#             else:
#                 # User manually changed the calculated amount
#                 custom_vat_amount = flt(item.custom_vat_amount) or 0
#                 frappe.logger().debug(
#                     f"Using user-provided VAT amount for {item.item_code}: {custom_vat_amount}"
#                 )
                
#         elif vat_apply_on == 'Amount':
#             # Manual Amount mode - do not calculate, use user input
#             # Force custom_vat_rate to 0 when in Amount mode
#             item.custom_vat_rate = 0
            
#             # Use manual VAT amount (no calculation)
#             custom_vat_amount = flt(item.custom_vat_amount) or 0
            
#             frappe.logger().debug(
#                 f"Manual VAT Amount mode for {item.item_code}: {custom_vat_amount}, cleared custom_vat_rate"
#             )
def calculate_item_vat_amounts(doc):
    """
    VAT rules (STRICT):
    - Percentage (%): ALWAYS recalculate VAT on every save
    - Amount: NEVER calculate, always keep manual value
    """
    for item in doc.items:

        vat_apply_on = getattr(item, 'custom_vat_apply_on', 'Percentage (%)')

        if vat_apply_on == 'Percentage (%)':
            custom_total = flt(item.custom_total) or 0
            custom_vat_rate = flt(item.custom_vat_rate) or 0

            # ALWAYS recalculate
            item.custom_vat_amount = flt(
                (custom_total * custom_vat_rate) / 100, 2
            )

            frappe.logger().debug(
                f"[VAT %] Recalculated for {item.item_code}: "
                f"custom_total={custom_total}, rate={custom_vat_rate}, "
                f"vat_amount={item.custom_vat_amount}"
            )

        elif vat_apply_on == 'Amount':
            # NEVER calculate in Amount mode
            # Force rate to 0, keep amount as user entered
            item.custom_vat_rate = 0

            frappe.logger().debug(
                f"[VAT Amount] Manual VAT kept for {item.item_code}: "
                f"{item.custom_vat_amount}"
            )


def calculate_total_vat_amount(doc):
    """
    Sum all custom_vat_amount from items
    """
    total_vat_amount = 0
    
    for item in doc.items:
        total_vat_amount += flt(item.custom_vat_amount) or 0
    
    doc.custom_total_vat_amount = flt(total_vat_amount, 2)


def calculate_item_tds_amounts(doc):
    """
    Calculate TDS amount for each item
    Only calculates if custom_tds_amount is not manually set
    If custom_tds_rate is present: custom_tds_amount = (custom_total * custom_tds_rate) / 100
    If custom_tds_amount is manually entered: clear custom_tds_rate
    """
    for item in doc.items:
        custom_tds_rate = flt(item.custom_tds_rate) or 0
        custom_tds_amount = flt(item.custom_tds_amount) or 0
        
        # Check if this is a manual entry or calculated value
        should_calculate = should_calculate_field(item, 'custom_tds_amount')
        
        if should_calculate:
            # Calculate TDS amount only if rate is present
            if custom_tds_rate > 0:
                custom_total = flt(item.custom_total) or 0
                
                # Calculate TDS amount (custom_tds_rate is percentage of custom_total)
                custom_tds_amount = flt((custom_total * custom_tds_rate) / 100, 2)
                item.custom_tds_amount = custom_tds_amount
                
                frappe.logger().debug(
                    f"Calculated TDS for {item.item_code}: "
                    f"custom_total={custom_total}, tds_rate%={custom_tds_rate}, tds_amount={custom_tds_amount}"
                )
        else:
            # User manually entered the amount
            frappe.logger().debug(
                f"Using user-provided TDS amount for {item.item_code}: {custom_tds_amount}"
            )
            
            # Clear custom_tds_rate only when amount is manually entered
            if custom_tds_amount > 0 and custom_tds_rate > 0:
                item.custom_tds_rate = 0
                frappe.logger().debug(
                    f"Manual TDS amount for {item.item_code}: {custom_tds_amount}, cleared custom_tds_rate"
                )


def calculate_total_tds_amount(doc):
    """
    Sum all custom_tds_amount from items grouped by TDS account
    Returns a dictionary with account as key and total TDS as value
    """
    tds_by_account = {}
    
    for item in doc.items:
        tds_amount = flt(item.custom_tds_amount) or 0
        tds_account = item.custom_account
        
        if tds_account and tds_amount > 0:
            if tds_account not in tds_by_account:
                tds_by_account[tds_account] = 0
            tds_by_account[tds_account] += tds_amount
    
    # Store total TDS amount
    total_tds_amount = sum(tds_by_account.values())
    doc.custom_total_tds_amount = flt(total_tds_amount, 2)
    
    frappe.logger().debug(f"TDS by account: {tds_by_account}")
    frappe.logger().debug(f"Total TDS Amount: {total_tds_amount}")
    
    return tds_by_account


def should_calculate_field(item, fieldname):
    """
    Determine if a field should be calculated or use user-provided value
    Special handling for VAT when custom_vat_apply_on = 'Amount'
    """
    # Special case: VAT Amount in 'Amount' mode should never be calculated
    if fieldname == 'custom_vat_amount':
        vat_apply_on = getattr(item, 'custom_vat_apply_on', 'Percentage (%)')
        if vat_apply_on == 'Amount':
            # In Amount mode, always use user input (never calculate)
            return False
    
    current_value = flt(item.get(fieldname)) or 0
    
    if not item.name:
        # New item - unless user explicitly set a value
        if current_value > 0:
            return False  # User provided value
        return True  # Calculate
    
    # For existing items, check if value was manually changed
    try:
        # Get the old document from database
        old_doc = frappe.db.get_value(
            "Purchase Invoice Item",
            item.name,
            [fieldname, "qty", "rate", "amount",  "custom_vat_rate", "custom_tds_rate", "custom_total", "custom_vat_apply_on"],
            as_dict=True
        )
        
        if not old_doc:
            # Item doesn't exist in DB yet (new item)
            if current_value > 0:
                return False  # User provided value
            return True  # Calculate
        
        old_value = flt(old_doc.get(fieldname)) or 0
        
        # Check if the base values changed (qty, rate, excise_duty, vat_rate%, tds_rate)
        if fieldname == 'custom_excise_value':
            old_qty = flt(old_doc.get('qty')) or 0
            old_excise_duty = flt(old_doc.get('custom_excise_duty')) or 0
            current_qty = flt(item.qty) or 0
            current_excise_duty = flt(item.custom_excise_duty) or 0
            
            base_values_changed = (old_qty != current_qty or old_excise_duty != current_excise_duty)
            
            # Calculate expected value based on old data
            expected_old_value = flt(old_excise_duty * old_qty, 2)
            
        elif fieldname == 'custom_vat_amount':
            # Check if VAT Apply On mode changed
            old_apply_on = old_doc.get('custom_vat_apply_on') or 'Percentage (%)'
            current_apply_on = getattr(item, 'custom_vat_apply_on', 'Percentage (%)')
            
            # If switched to Amount mode, never calculate
            if current_apply_on == 'Amount':
                return False
            
            old_custom_total = flt(old_doc.get('custom_total')) or 0
            old_vat_rate = flt(old_doc.get('custom_vat_rate')) or 0
            current_custom_total = flt(item.custom_total) or 0
            current_vat_rate = flt(item.custom_vat_rate) or 0
            
            base_values_changed = (old_custom_total != current_custom_total or old_vat_rate != current_vat_rate or old_apply_on != current_apply_on)
            
            if current_apply_on =='Percentage(%)' and old_custom_total!= current_custom_total:
                return True
            
            # Calculate expected value based on old data
            expected_old_value = flt((old_custom_total * old_vat_rate) / 100, 2)
            
        elif fieldname == 'custom_tds_amount':
            old_custom_total = flt(old_doc.get('custom_total')) or 0
            old_tds_rate = flt(old_doc.get('custom_tds_rate')) or 0
            current_custom_total = flt(item.custom_total) or 0
            current_tds_rate = flt(item.custom_tds_rate) or 0
            
            base_values_changed = (old_custom_total != current_custom_total or old_tds_rate != current_tds_rate)
            
            # Calculate expected value based on old data
            expected_old_value = flt((old_custom_total * old_tds_rate) / 100, 2)
        else:
            return True  # Unknown field, calculate
        
        # If old value differs from expected calculation, user manually edited it
        if abs(old_value - expected_old_value) > 0.01:  # Allow 0.01 rounding difference
            # User had manually set a value
            if base_values_changed:
                # Base values changed, recalculate
                return True
            else:
                # Base values same, keep user's manual value
                if current_value == old_value:
                    return False  # Keep user's value
                else:
                    # User changed it again, keep new value
                    return False
        
        # If current value differs from calculated value, user is setting it now
        if fieldname == 'custom_excise_value':
            calculated_value = flt((flt(item.custom_excise_duty) or 0) * (flt(item.qty) or 0), 2)
        elif fieldname == 'custom_vat_amount':
            calculated_value = flt(((flt(item.custom_total) or 0) * (flt(item.custom_vat_rate) or 0)) / 100, 2)
        else:  # custom_tds_amount
            calculated_value = flt(((flt(item.custom_total) or 0) * (flt(item.custom_tds_rate) or 0)) / 100, 2)
        
        if current_value > 0 and abs(current_value - calculated_value) > 0.01:
            # Current value is different from calculated, user set it manually
            return False
        
        # Default: calculate
        return True
        
    except Exception as e:
        frappe.logger().error(f"Error in should_calculate_field: {str(e)}")
        # On error, calculate if no value exists
        return current_value == 0


def update_taxes_table(doc):
    """
    Update or create tax rows in the taxes table
    1. Excise Duty (account starting with 348204) - position 0
    2. VAT (account starting with VAT) - position 1
    3. TDS (accounts from items' custom_account field) - position 2 onwards (as deduction)
    """
    total_excise = flt(doc.custom_total_excise_amount) or 0
    total_vat = flt(doc.custom_total_vat_amount) or 0
    tds_by_account = calculate_total_tds_amount(doc)
    
    # Find excise and VAT accounts
    excise_account = find_account_by_prefix(doc.company, "348204")
    vat_account = find_account_by_prefix(doc.company, "VAT")
    
    if not excise_account:
        frappe.logger().warning(f"No excise account found starting with 348204 for company {doc.company}")
    
    if not vat_account:
        frappe.logger().warning(f"No VAT account found starting with VAT for company {doc.company}")
    
    position = 0
    
    # Update or create excise row
    if excise_account and total_excise > 0:
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
    
    # Update or create VAT row
    if vat_account and total_vat > 0:
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
    
    # Update or create TDS rows (one per unique account)
    for tds_account, tds_amount in tds_by_account.items():
        if tds_account and tds_amount > 0:
            update_or_create_tax_row(
                doc,
                account_head=tds_account,
                tax_amount=tds_amount,
                position=position,
                description=f"TDS - {tds_account}",
                charge_type="Actual",
                add_deduct="Deduct"
            )
            position += 1


def find_account_by_prefix(company, prefix):
    """
    Find account that starts with the given prefix for the company
    """
    accounts = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "name": ["like", f"{prefix}%"]
        },
        fields=["name"],
        limit=1
    )
    
    return accounts[0].name if accounts else None


def update_or_create_tax_row(doc, account_head, tax_amount, position, description, charge_type="Actual", add_deduct="Add"):
    """
    Update existing tax row or create new one at specified position
    """
    # Find existing row
    existing_row = None
    existing_index = -1
    
    for idx, tax_row in enumerate(doc.taxes or []):
        if tax_row.account_head == account_head and tax_row.charge_type == charge_type:
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
        
        frappe.logger().debug(
            f"Updated existing tax row: {account_head} = {tax_amount} ({add_deduct})"
        )
        
        # Move to correct position if needed
        if existing_index != position:
            move_tax_row_to_position(doc, existing_index, position)
    else:
        # Create new row
        new_row = doc.append("taxes", {
            "charge_type": charge_type,
            "account_head": account_head,
            "description": description,
            "tax_amount": tax_amount,
            "base_tax_amount": tax_amount,
            "add_deduct_tax": add_deduct,
            "category": "Total",
            "included_in_print_rate": 0
        })
        
        frappe.logger().debug(
            f"Created new tax row: {account_head} = {tax_amount} ({add_deduct})"
        )
        
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
    
    # Remove row from current position
    row = doc.taxes.pop(from_index)
    
    # Insert at new position
    doc.taxes.insert(to_index, row)
    
    # Update idx for all rows
    for idx, tax_row in enumerate(doc.taxes):
        tax_row.idx = idx + 1
    
    frappe.logger().debug(f"Moved tax row from position {from_index} to {to_index}")


def calculate_custom_total_amount(doc):
    """
    Calculate custom_total_amount (total excluding excise)
    This is the sum of all item amounts (qty * rate)
    """
    custom_total_excluding_excise = 0
    
    for item in doc.items:
        amount = flt(item.amount) or 0
        custom_total_excluding_excise += amount
    
    doc.custom_total_amount = flt(custom_total_excluding_excise, 2)
    
    frappe.logger().debug(f"Custom Total Amount (excluding excise): {custom_total_excluding_excise}")


def on_submit(doc, method=None):
    """
    Hook that runs on submit
    Can be used for additional validations or calculations
    """
    pass


def validate_purchaseinvoice(doc, method=None):
    """
    Hook that runs during validation
    Can be used for custom validations
    """
    # Ensure all required custom fields are populated
    validate_custom_fields(doc)


def validate_custom_fields(doc):
    """
    Validate that custom fields have proper values
    """
    for item in doc.items:
        if not hasattr(item, 'custom_excise_duty'):
            item.custom_excise_duty = 0
        
        if not hasattr(item, 'custom_tds_rate'):
            item.custom_tds_rate = 0
        
        # Default custom_vat_apply_on to Percentage (%)
        if not hasattr(item, 'custom_vat_apply_on') or not item.custom_vat_apply_on:
            item.custom_vat_apply_on = 'Percentage (%)'


# Helper function for data import
@frappe.whitelist()
def populate_item_custom_fields(item_code):
    """
    Fetch custom_excise_duty, custom_vat_rate, custom_tds_rate, and custom_account from Item master
    This can be called during data import or from frontend
    """
    if not item_code:
        return {
            "custom_excise_duty": 0,
            "custom_vat_rate": 0,
            "custom_tds_rate": 0,
            "custom_account": None
        }
    
    item = frappe.get_doc("Item", item_code)
    
    custom_excise_duty = flt(item.custom_excise_duty) if hasattr(item, 'custom_excise_duty') else 0
    custom_tds_rate = flt(item.custom_tds_rate) if hasattr(item, 'custom_tds_rate') else 0
    custom_account = item.custom_account if hasattr(item, 'custom_account') else None
    custom_vat_rate = 0
    
    # Get VAT from Item Tax template
    if hasattr(item, 'taxes') and item.taxes:
        custom_vat_rate = flt(item.taxes[0].maximum_net_rate) if item.taxes[0].maximum_net_rate else 0
    
    return {
        "custom_excise_duty": custom_excise_duty,
        "custom_vat_rate": custom_vat_rate,
        "custom_tds_rate": custom_tds_rate,
        "custom_account": custom_account
    }