import frappe
from frappe import _
from frappe.utils import flt
from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

def before_save_salesinvoice(doc, method=None):
    """
    Main hook that runs before saving Sales Invoice
    Calculates excise, VAT, and totals
    Only calculates if user hasn't manually provided values
    """
    calculate_item_excise_and_totals(doc)
    calculate_total_excise_amount(doc)
    calculate_item_vat_amounts(doc)
    calculate_total_vat_amount(doc)
    update_taxes_table(doc)
    calculate_custom_total_amount(doc)
    doc.calculate_taxes_and_totals()

# def calculate_taxes_and_totals(doc):
#     calculate_taxes_and_totals()

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
            
            # frappe.logger().debug(
            #     f"Calculated excise for {item.item_code}: "
            #     f"excise_duty={custom_excise_duty}, qty={qty}, excise_value={custom_excise_value}"
            # )
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
            else:
                frappe.logger().debug(
                    f"Using user-provided excise for {item.item_code}: {custom_excise_value}"
                )
        
        # Always calculate custom_total based on current excise value
        custom_total = flt(amount + custom_excise_value, 2)
        item.custom_total = custom_total


def calculate_total_excise_amount(doc):
    """
    Sum all custom_excise_value from items
    """
    total_excise_amount = 0
    
    for item in doc.items:
        total_excise_amount += flt(item.custom_excise_value) or 0
    
    doc.custom_total_excise_amount = flt(total_excise_amount, 2)
    doc.custom_excise = flt(total_excise_amount, 2)
    
    # frappe.logger().debug(f"Total Excise Amount: {total_excise_amount}")


def calculate_item_vat_amounts(doc):
    """
    Calculate VAT amount for each item
    Only calculates if custom_vat_amount is not manually set
    custom_vat_amount = (custom_total * custom_vat) / 100
    """
    for item in doc.items:
        # Check if user manually set VAT amount
        should_calculate_vat = should_calculate_field(item, 'custom_vat_amount')
        
        if should_calculate_vat:
            custom_total = flt(item.custom_total) or 0
            custom_vat = flt(item.custom_vat) or 0
            
            # Calculate VAT amount (custom_vat is percentage)
            custom_vat_amount = flt((custom_total * custom_vat) / 100, 2)
            item.custom_vat_amount = custom_vat_amount
            
            # frappe.logger().debug(
            #     f"Calculated VAT for {item.item_code}: "
            #     f"custom_total={custom_total}, vat%={custom_vat}, vat_amount={custom_vat_amount}"
            # )
        else:
            custom_vat_amount = flt(item.custom_vat_amount) or 0

             # Clear custom_vat percentage when amount is manual
            if custom_vat_amount > 0:
                item.custom_vat = 0
                frappe.logger().debug(
                    f"Manual VAT amount for {item.item_code}: {custom_vat_amount}, cleared custom_vat%"
                )
            else:
                frappe.logger().debug(
                    f"Using user-provided VAT for {item.item_code}: {custom_vat_amount}"
                )


def calculate_total_vat_amount(doc):
    """
    Sum all custom_vat_amount from items
    """
    total_vat_amount = 0
    
    for item in doc.items:
        total_vat_amount += flt(item.custom_vat_amount) or 0
    
    doc.custom_total_vat_amount = flt(total_vat_amount, 2)
    
    # frappe.logger().debug(f"Total VAT Amount: {total_vat_amount}")


def should_calculate_field(item, fieldname):
    """
    Determine if we should calculate the field or use user-provided value
    
    Logic:
    1. If field has a non-zero value in the database (old value), keep it (user edited)
    2. If field is newly set to non-zero in current save, keep it (user provided)
    3. Otherwise, calculate it
    
    Args:
        item: Sales Invoice Item row
        fieldname: Field to check (custom_excise_value or custom_vat_amount)
    
    Returns:
        bool: True if should calculate, False if should use existing value
    """
    current_value = flt(item.get(fieldname)) or 0
    
    if not item.name:
        # Unless user explicitly set a value
        if current_value > 0:
            return False  # User provided value
        return True  # Calculate
    
    # For existing items, check if value was manually changed
    try:
        # Get the old document from database
        old_doc = frappe.db.get_value(
            "Sales Invoice Item",
            item.name,
            [fieldname, "qty", "rate", "amount", "custom_excise_duty", "custom_vat", "custom_total"],
            as_dict=True
        )
        
        if not old_doc:
            # Item doesn't exist in DB yet (new item)
            if current_value > 0:
                return False  # User provided value
            return True  # Calculate
        
        old_value = flt(old_doc.get(fieldname)) or 0
        
        # Check if the base values changed (qty, rate, excise_duty, vat%)
        if fieldname == 'custom_excise_value':
            old_qty = flt(old_doc.get('qty')) or 0
            old_excise_duty = flt(old_doc.get('custom_excise_duty')) or 0
            current_qty = flt(item.qty) or 0
            current_excise_duty = flt(item.custom_excise_duty) or 0
            
            base_values_changed = (old_qty != current_qty or old_excise_duty != current_excise_duty)
            
            # Calculate expected value based on old data
            expected_old_value = flt(old_excise_duty * old_qty, 2)
            
        elif fieldname == 'custom_vat_amount':
            old_custom_total = flt(old_doc.get('custom_total')) or 0
            old_vat = flt(old_doc.get('custom_vat')) or 0
            current_custom_total = flt(item.custom_total) or 0
            current_vat = flt(item.custom_vat) or 0
            
            base_values_changed = (old_custom_total != current_custom_total or old_vat != current_vat)
            
            # Calculate expected value based on old data
            expected_old_value = flt((old_custom_total * old_vat) / 100, 2)
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
        else:  # custom_vat_amount
            calculated_value = flt(((flt(item.custom_total) or 0) * (flt(item.custom_vat) or 0)) / 100, 2)
        
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
    """
    total_excise = flt(doc.custom_total_excise_amount) or 0
    total_vat = flt(doc.custom_total_vat_amount) or 0
    
    # Find excise account
    excise_account = find_account_by_prefix(doc.company, "348204")
    vat_account = find_account_by_prefix(doc.company, "VAT")
    
    if not excise_account:
        frappe.logger().warning(f"No excise account found starting with 348204 for company {doc.company}")
    
    if not vat_account:
        frappe.logger().warning(f"No VAT account found starting with VAT for company {doc.company}")
    
    # Update or create excise row
    if excise_account and total_excise > 0:
        update_or_create_tax_row(
            doc, 
            account_head=excise_account, 
            tax_amount=total_excise, 
            position=0,
            description=f"Excise Duty - {doc.company}"
        )
    
    # Update or create VAT row
    if vat_account and total_vat > 0:
        update_or_create_tax_row(
            doc, 
            account_head=vat_account, 
            tax_amount=total_vat, 
            position=1,
            description=f"VAT - {doc.company}"
        )


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


def update_or_create_tax_row(doc, account_head, tax_amount, position, description):
    """
    Update existing tax row or create new one at specified position
    """
    # Find existing row
    existing_row = None
    existing_index = -1
    
    for idx, tax_row in enumerate(doc.taxes or []):
        if tax_row.account_head == account_head and tax_row.charge_type == "Actual":
            existing_row = tax_row
            existing_index = idx
            break
    
    if existing_row:
        # Update existing row
        existing_row.tax_amount = tax_amount
        existing_row.base_tax_amount = tax_amount
        
        frappe.logger().debug(
            f"Updated existing tax row: {account_head} = {tax_amount}"
        )
        
        # Move to correct position if needed
        if existing_index != position:
            move_tax_row_to_position(doc, existing_index, position)
    else:
        # Create new row
        new_row = doc.append("taxes", {
            "charge_type": "Actual",
            "account_head": account_head,
            "description": description,
            "tax_amount": tax_amount,
            "base_tax_amount": tax_amount
        })
        
        frappe.logger().debug(
            f"Created new tax row: {account_head} = {tax_amount}"
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


def validate_salesinvoice(doc, method=None):
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
        
        # if not hasattr(item, 'custom_vat'):
        #     item.custom_vat = 0


# Helper function for data import
@frappe.whitelist()
def populate_item_custom_fields(item_code):
    """
    Fetch custom_excise_duty and custom_vat from Item master
    This can be called during data import or from frontend
    """
    if not item_code:
        return {"custom_excise_duty": 0, "custom_vat": 0}
    
    item = frappe.get_doc("Item", item_code)
    
    custom_excise_duty = flt(item.custom_excise_duty) if hasattr(item, 'custom_excise_duty') else 0
    custom_vat = 0
    
    # Get VAT from Item Tax template
    if hasattr(item, 'taxes') and item.taxes:
        custom_vat = flt(item.taxes[0].maximum_net_rate) if item.taxes[0].maximum_net_rate else 0
    
    return {
        "custom_excise_duty": custom_excise_duty,
        "custom_vat": custom_vat
    }
    