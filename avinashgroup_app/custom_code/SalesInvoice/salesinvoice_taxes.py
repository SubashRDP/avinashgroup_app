import frappe
from frappe import _
from frappe.utils import flt


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
    
    # 0. Ensure VAT Apply On defaults are set
    ensure_vat_apply_on_defaults(doc)
    
    # 1. Calculate item-level totals (respects manual excise)
    calculate_custom_total(doc)
    
    # 2. Calculate total amount including excise (sum of custom_total from all items)
    calculate_total_amount_including_excise(doc)
    
    # 3. VAT calculation (strict rules)
    calculate_item_vat_amounts(doc)
    calculate_total_vat_amount(doc)
    
    # 4. Excise totals (aggregation only, no calculation)
    calculate_total_excise_amount(doc)
    
    # 5. Update taxes table
    update_taxes_table(doc)
    
    # 6. Calculate custom_total_amount
    calculate_custom_total_amount(doc)
    
    # 7. Let ERPNext calculate standard totals
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
    custom_total = net_amount + custom_excise_value
    
    Note: custom_excise_value is ALWAYS manual (never calculated)
    """
    for item in doc.items:
        net_amount = flt(item.net_amount) or 0
        excise_value = flt(item.custom_excise_value) or 0
        
        item.custom_total = flt(net_amount + excise_value, 5)
        
        frappe.logger().debug(
            f"Custom Total for {item.item_code}: "
            f"net_amount={net_amount} + excise={excise_value} = {item.custom_total}"
        )


def calculate_total_amount_including_excise(doc):
    """Sum all custom_total from items"""
    total_including_excise = sum(flt(item.custom_total) or 0 for item in doc.items)
    doc.custom_total_amount_including_excise = flt(total_including_excise, 5)
    
    frappe.logger().debug(f"Total Amount Including Excise: {total_including_excise}")


def calculate_total_excise_amount(doc):
    """
    Sum all custom_excise_value from items
    No calculation, just aggregation
    """
    total_excise = sum(flt(item.custom_excise_value) or 0 for item in doc.items)
    
    doc.custom_total_excise_amount = flt(total_excise, 5)
    doc.custom_excise = flt(total_excise, 5)
    
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
            item.custom_vat_amount = flt((custom_total * custom_vat_rate) / 100, 5)
            
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
    
    doc.custom_total_vat_amount = flt(total_vat,5)
    
    frappe.logger().debug(f"Total VAT: {total_vat}")


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


def calculate_custom_total_amount(doc):
    """
    Calculate custom_total_amount (total excluding excise)
    This is the sum of all item net_amounts (qty * net_rate)
    """
    custom_total_amount = 0
    
    for item in doc.items:
        net_amount = flt(item.net_amount) or 0
        custom_total_amount += net_amount
    
    doc.custom_total_amount = flt(custom_total_amount, 5)
    
    frappe.logger().debug(f"Custom Total Amount (excluding excise): {custom_total_amount}")


def validate_salesinvoice(doc, method=None):
    """
    Hook that runs during validation
    """
    validate_custom_fields(doc)


def validate_custom_fields(doc):
    """
    Validate and set default values for custom fields
    """
    for item in doc.items:
        # Default VAT Apply On to Percentage
        if not hasattr(item, 'custom_vat_apply_on') or not item.custom_vat_apply_on:
            item.custom_vat_apply_on = 'Percentage (%)'
        
        if not hasattr(item, 'custom_vat_rate'):
            item.custom_vat_rate = 0


@frappe.whitelist()
def populate_item_custom_fields(item_code):
    """
    Fetch VAT rate from Item Tax Template's maximum_net_rate field
    Called from frontend when item is selected
    NO excise duty or TDS for Sales Invoice
    """
    if not item_code:
        return {
            "custom_vat_rate": 0
        }
    
    try:
        item = frappe.get_doc("Item", item_code)
        
        # Get VAT rate from Item Tax Template's maximum_net_rate
        custom_vat_rate = 0
        if hasattr(item, 'taxes') and item.taxes:
            for tax in item.taxes:
                if hasattr(tax, 'maximum_net_rate') and tax.maximum_net_rate:
                    custom_vat_rate = flt(tax.maximum_net_rate)
                    frappe.logger().debug(
                        f"Found VAT rate from Item Tax Template: {custom_vat_rate}% "
                        f"(template: {tax.item_tax_template})"
                    )
                    break
        
        return {
            "custom_vat_rate": custom_vat_rate
        }
    except Exception as e:
        frappe.logger().error(f"Error fetching item custom fields for {item_code}: {str(e)}")
        return {
            "custom_vat_rate": 0
        }