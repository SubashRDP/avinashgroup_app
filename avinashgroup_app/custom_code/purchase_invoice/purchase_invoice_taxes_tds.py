import frappe
from frappe import _
from frappe.utils import flt


def before_save_purchaseinvoice(doc, method=None):
    """
    Main hook that runs before saving Purchase Invoice
    
    Calculation Rules:
    1. Excise Value: ALWAYS MANUAL (never recalculated)
    2. custom_total: amount + custom_excise_value
    3. VAT:
        - Percentage (%): ALWAYS recalculated from custom_total * custom_vat_rate / 100
        - Amount: NEVER recalculated (manual entry)
    4. TDS: Existing logic (percentage-based calculation)
    5. Taxes table: Updated with Excise, VAT, TDS
    """
    
    # 0. Ensure VAT Apply On defaults are set
    ensure_vat_apply_on_defaults(doc)
    
    # 1. Calculate item-level totals (respects manual excise)
    calculate_custom_total(doc)
    
    # 2. VAT calculation (strict rules)
    calculate_item_vat_amounts(doc)
    calculate_total_vat_amount(doc)
    
    # 3. TDS calculation
    calculate_item_tds_amounts(doc)
    calculate_total_tds_amount(doc)
    
    # 4. Excise totals (aggregation only, no calculation)
    calculate_total_excise_amount(doc)
    
    # 5. Update taxes table
    update_taxes_table(doc)
    
    # 6. Let ERPNext calculate standard totals
    doc.calculate_taxes_and_totals()


def ensure_vat_apply_on_defaults(doc):
    """
    Ensure all items have custom_vat_apply_on set to default 'Percentage (%)'
    This runs before any other calculation
    """
    for item in doc.items:
        if not hasattr(item, 'custom_vat_apply_on') or not item.custom_vat_apply_on:
            item.custom_vat_apply_on = 'Percentage (%)'
            frappe.logger().debug(
                f"Set default VAT Apply On to 'Percentage (%)' for {item.item_code}"
            )


def calculate_custom_total(doc):
    """
    Calculate custom_total for each item
    custom_total = amount + custom_excise_value
    
    Note: custom_excise_value is ALWAYS manual (never calculated)
    """
    for item in doc.items:
        amount = flt(item.amount) or 0
        excise_value = flt(item.custom_excise_value) or 0
        
        item.custom_total = flt(amount + excise_value, 2)
        
        frappe.logger().debug(
            f"Custom Total for {item.item_code}: "
            f"amount={amount} + excise={excise_value} = {item.custom_total}"
        )


def calculate_total_excise_amount(doc):
    """
    Sum all custom_excise_value from items
    No calculation, just aggregation
    """
    total_excise = sum(flt(item.custom_excise_value) or 0 for item in doc.items)
    
    doc.custom_total_excise_amount = flt(total_excise, 2)
    doc.custom_excise = flt(total_excise, 2)
    
    frappe.logger().debug(f"Total Excise: {total_excise}")


def calculate_item_vat_amounts(doc):
    """
    Calculate VAT amount for each item based on custom_vat_apply_on
    
    STRICT RULES:
    - Percentage (%): ALWAYS recalculate on every save (DEFAULT BEHAVIOR)
        custom_vat_amount = (custom_total * custom_vat_rate) / 100
    - Amount: NEVER calculate, keep manual value
        custom_vat_rate forced to 0
    """
    for item in doc.items:
        # Get vat_apply_on (should already be set by ensure_vat_apply_on_defaults)
        vat_apply_on = getattr(item, 'custom_vat_apply_on', 'Percentage (%)')
        
        # Safeguard: if still not set, default to Percentage
        if not vat_apply_on:
            item.custom_vat_apply_on = 'Percentage (%)'
            vat_apply_on = 'Percentage (%)'
        
        if vat_apply_on == 'Percentage (%)':
            # ALWAYS recalculate in Percentage mode (DEFAULT)
            custom_total = flt(item.custom_total) or 0
            custom_vat_rate = flt(item.custom_vat_rate) or 0
            
            # Calculate VAT amount
            item.custom_vat_amount = flt((custom_total * custom_vat_rate) / 100, 2)
            
            frappe.logger().debug(
                f"[VAT % - DEFAULT] Calculated for {item.item_code}: "
                f"total={custom_total}, rate={custom_vat_rate}%, "
                f"vat_amount={item.custom_vat_amount}"
            )
            
        elif vat_apply_on == 'Amount':
            # NEVER calculate in Amount mode (MANUAL OVERRIDE)
            # Force rate to 0, keep amount as-is
            item.custom_vat_rate = 0
            
            frappe.logger().debug(
                f"[VAT Amount - MANUAL] Kept manual for {item.item_code}: "
                f"{item.custom_vat_amount} (rate forced to 0)"
            )


def calculate_total_vat_amount(doc):
    """
    Sum all custom_vat_amount from items
    """
    total_vat = sum(flt(item.custom_vat_amount) or 0 for item in doc.items)
    
    doc.custom_total_vat_amount = flt(total_vat, 2)
    
    frappe.logger().debug(f"Total VAT: {total_vat}")


def calculate_item_tds_amounts(doc):
    """
    Calculate TDS amount for each item
    custom_tds_amount = (custom_total * custom_tds_rate) / 100
    
    If custom_tds_amount is manually set, respect it and clear custom_tds_rate
    """
    for item in doc.items:
        custom_tds_rate = flt(item.custom_tds_rate) or 0
        custom_tds_amount = flt(item.custom_tds_amount) or 0
        
        # Check if this should be calculated
        should_calculate = should_calculate_tds(item)
        
        if should_calculate and custom_tds_rate > 0:
            # Calculate TDS
            custom_total = flt(item.custom_total) or 0
            item.custom_tds_amount = flt((custom_total * custom_tds_rate) / 100, 2)
            
            frappe.logger().debug(
                f"Calculated TDS for {item.item_code}: "
                f"total={custom_total}, rate={custom_tds_rate}%, "
                f"tds_amount={item.custom_tds_amount}"
            )
        else:
            # Manual TDS amount
            if custom_tds_amount > 0 and custom_tds_rate > 0:
                item.custom_tds_rate = 0
                frappe.logger().debug(
                    f"Manual TDS for {item.item_code}: {custom_tds_amount} (rate cleared)"
                )


def should_calculate_tds(item):
    """
    Determine if TDS should be calculated or use manual value
    Returns True if should calculate, False if should use manual value
    """
    current_tds = flt(item.custom_tds_amount) or 0
    
    # New item without TDS amount - calculate
    if not item.name and current_tds == 0:
        return True
    
    # New item with TDS amount - manual
    if not item.name and current_tds > 0:
        return False
    
    try:
        # Get old values from database
        old_doc = frappe.db.get_value(
            "Purchase Invoice Item",
            item.name,
            ["custom_tds_amount", "custom_total", "custom_tds_rate"],
            as_dict=True
        )
        
        if not old_doc:
            # Item doesn't exist yet
            return current_tds == 0
        
        old_tds = flt(old_doc.get('custom_tds_amount')) or 0
        old_total = flt(old_doc.get('custom_total')) or 0
        old_rate = flt(old_doc.get('custom_tds_rate')) or 0
        
        current_total = flt(item.custom_total) or 0
        current_rate = flt(item.custom_tds_rate) or 0
        
        # Check if values changed
        total_changed = abs(old_total - current_total) > 0.01
        rate_changed = abs(old_rate - current_rate) > 0.01
        tds_changed = abs(old_tds - current_tds) > 0.01
        
        # If base values changed, recalculate
        if total_changed or rate_changed:
            return True
        
        # If TDS manually changed, don't recalculate
        if tds_changed:
            return False
        
        # Calculate expected old value
        expected_old = flt((old_total * old_rate) / 100, 2)
        
        # If old value was manual, keep manual unless base changed
        if abs(old_tds - expected_old) > 0.01:
            return False
        
        # Default: calculate
        return True
        
    except Exception as e:
        frappe.logger().error(f"Error in should_calculate_tds: {str(e)}")
        return current_tds == 0


def calculate_total_tds_amount(doc):
    """
    Sum all custom_tds_amount from items, grouped by account
    Returns dictionary {account: total_tds}
    """
    tds_by_account = {}
    
    for item in doc.items:
        tds_amount = flt(item.custom_tds_amount) or 0
        tds_account = item.custom_account
        
        if tds_account and tds_amount > 0:
            if tds_account not in tds_by_account:
                tds_by_account[tds_account] = 0
            tds_by_account[tds_account] += tds_amount
    
    total_tds = sum(tds_by_account.values())
    doc.custom_total_tds_amount = flt(total_tds, 2)
    
    frappe.logger().debug(f"TDS by account: {tds_by_account}")
    frappe.logger().debug(f"Total TDS: {total_tds}")
    
    return tds_by_account


def update_taxes_table(doc):
    """
    Update or create tax rows in the taxes table
    1. Excise Duty (account starting with 348204) - position 0
    2. VAT (account starting with VAT) - position 1
    3. TDS (accounts from items) - position 2+ (as deduction)
    """
    total_excise = flt(doc.custom_total_excise_amount) or 0
    total_vat = flt(doc.custom_total_vat_amount) or 0
    tds_by_account = {}
    
    # Recalculate TDS by account
    for item in doc.items:
        tds_amount = flt(item.custom_tds_amount) or 0
        tds_account = item.custom_account
        
        if tds_account and tds_amount > 0:
            if tds_account not in tds_by_account:
                tds_by_account[tds_account] = 0
            tds_by_account[tds_account] += tds_amount
    
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
    
    # Update or create TDS rows
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
        
        frappe.logger().debug(
            f"Updated tax row: {account_head} = {tax_amount} ({add_deduct})"
        )
        
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
        
        frappe.logger().debug(
            f"Created tax row: {account_head} = {tax_amount} ({add_deduct})"
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
    
    # Remove from current position
    row = doc.taxes.pop(from_index)
    
    # Insert at new position
    doc.taxes.insert(to_index, row)
    
    # Update idx for all rows
    for idx, tax_row in enumerate(doc.taxes):
        tax_row.idx = idx + 1
    
    frappe.logger().debug(f"Moved tax row from {from_index} to {to_index}")


def validate_purchaseinvoice(doc, method=None):
    """
    Hook that runs during validation
    """
    validate_custom_fields(doc)


def validate_custom_fields(doc):
    """
    Validate and set default values for custom fields
    """
    for item in doc.items:
        # Set defaults if not present
        if not hasattr(item, 'custom_excise_duty'):
            item.custom_excise_duty = 0
        
        if not hasattr(item, 'custom_tds_rate'):
            item.custom_tds_rate = 0
        
        # Default VAT Apply On to Percentage
        if not hasattr(item, 'custom_vat_apply_on') or not item.custom_vat_apply_on:
            item.custom_vat_apply_on = 'Percentage (%)'


@frappe.whitelist()
def populate_item_custom_fields(item_code):
    """
    Fetch custom fields from Item master
    Called from frontend when item is selected
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