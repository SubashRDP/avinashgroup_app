import frappe
from frappe import _
from frappe.utils import flt


def before_save_purchaseinvoice(doc, method=None):
    """
    Main hook that runs before saving Purchase Invoice
    
    Uses custom_tax_withholding_category_custom field (NOT system's tax_withholding_category)
    This prevents ERPNext's built-in TDS logic from interfering
    """

    # 0. Ensure Apply On defaults are set
    ensure_apply_on_defaults(doc)
    
    # 1. Calculate item-level totals (respects manual excise)
    calculate_custom_total(doc)
    
    # 2. Calculate total amount including excise (sum of custom_total from all items)
    calculate_total_amount_including_excise(doc)
    
    # 3. VAT calculation (strict rules)
    calculate_item_vat_amounts(doc)
    calculate_total_vat_amount(doc)
    
    # 4. TDS calculation (using CUSTOM field)
    calculate_item_tds_amounts(doc)
    calculate_total_tds_amount(doc)
    
    # 5. Excise totals (aggregation only, no calculation)
    calculate_total_excise_amount(doc)
    
    # 6. Update taxes table (with our custom TDS)
    update_taxes_table(doc)
    
    # 7. Let ERPNext calculate standard totals
    # System's TDS won't trigger because we're using custom field
    doc.calculate_taxes_and_totals()


def ensure_apply_on_defaults(doc):
    """Ensure all items have custom_vat_apply_on and custom_tds_apply_on set to default 'Percentage (%)'"""
    for item in doc.items:
        # VAT Apply On default
        if not hasattr(item, 'custom_vat_apply_on') or not item.custom_vat_apply_on:
            item.custom_vat_apply_on = 'Percentage (%)'
        
        # TDS Apply On default
        if not hasattr(item, 'custom_tds_apply_on') or not item.custom_tds_apply_on:
            item.custom_tds_apply_on = 'Percentage (%)'

def calculate_custom_total(doc):
    """Calculate custom_total = base_net_amount + custom_excise_value"""
    for item in doc.items:
        base_net_amount = flt(item.base_net_amount) or 0
        excise_value = flt(item.custom_excise_value) or 0
        item.custom_total = flt(base_net_amount + excise_value,5)


def calculate_total_amount_including_excise(doc):
    """Sum all custom_total from items"""
    total_including_excise = sum(flt(item.custom_total) or 0 for item in doc.items)
    doc.custom_total_amount_including_excise = flt(total_including_excise, 5)


def calculate_total_excise_amount(doc):
    """Sum all custom_excise_value from items"""
    total_excise = sum(flt(item.custom_excise_value) or 0 for item in doc.items)
    doc.custom_total_excise_amount = flt(total_excise, 5)
    doc.custom_excise = flt(total_excise, 5)


def calculate_item_vat_amounts(doc):
    """Calculate VAT amount based on Percentage or Amount mode"""
    for item in doc.items:
        vat_apply_on = getattr(item, 'custom_vat_apply_on', 'Percentage (%)')
        
        if not vat_apply_on:
            item.custom_vat_apply_on = 'Percentage (%)'
            vat_apply_on = 'Percentage (%)'
        
        if vat_apply_on == 'Percentage (%)':
            custom_total = flt(item.custom_total) or 0
            custom_vat_rate = flt(item.custom_vat_rate) or 0
            item.custom_vat_amount = flt((custom_total * custom_vat_rate) / 100, 5)
        elif vat_apply_on == 'Amount':
            item.custom_vat_rate = 0


def calculate_total_vat_amount(doc):
    """Sum all custom_vat_amount from items"""
    total_vat = sum(flt(item.custom_vat_amount) or 0 for item in doc.items)
    doc.custom_total_vat_amount = flt(total_vat, 5)



def calculate_item_tds_amounts(doc):
    """
    Calculate TDS amount for each item based on Percentage or Amount mode
    
    Only 2 conditions need to be true:
    1. custom_tax_withholding_category_custom has a value (at invoice level)
    2. apply_tds is checked at line item level
    
    NEW: Respects custom_tds_apply_on field (Percentage vs Amount)
    """
    # Check invoice-level condition - only custom tax category
    invoice_tax_category_custom = getattr(doc, 'custom_tax_withholding_category_custom', None)
    
    # Get TDS rate from CUSTOM Tax Withholding Category
    tds_rate_from_category = get_tds_rate_from_custom_tax_withholding(doc)
    
    for item in doc.items:
        # Check line item apply_tds
        item_apply_tds = getattr(item, 'apply_tds', False)
        
        # Only 2 conditions must be true
        if not (invoice_tax_category_custom and item_apply_tds):
            item.custom_tds_amount = 0
            item.custom_tds_rate = 0
            frappe.logger().debug(
                f"TDS skipped for {item.item_code}: "
                f"custom_category={invoice_tax_category_custom}, "
                f"item_apply_tds={item_apply_tds}"
            )
            continue
        
        # Get TDS Apply On mode (default to Percentage if not set)
        tds_apply_on = getattr(item, 'custom_tds_apply_on', 'Percentage (%)')
        
        if not tds_apply_on:
            item.custom_tds_apply_on = 'Percentage (%)'
            tds_apply_on = 'Percentage (%)'
        
        if tds_apply_on == 'Percentage (%)':
            # PERCENTAGE MODE: Calculate from rate
            
            # Set TDS rate from Tax Withholding Category if not manually set
            if tds_rate_from_category and not item.custom_tds_rate:
                item.custom_tds_rate = tds_rate_from_category
            
            custom_tds_rate = flt(item.custom_tds_rate) or 0
            
            if custom_tds_rate > 0:
                # Calculate: custom_tds_amount = custom_total * custom_tds_rate / 100
                custom_total = flt(item.custom_total) or 0
                item.custom_tds_amount = flt((custom_total * custom_tds_rate) / 100, 5)
                
                frappe.logger().debug(
                    f"Calculated TDS (Percentage) for {item.item_code}: "
                    f"custom_total={custom_total}, rate={custom_tds_rate}%, "
                    f"tds_amount={item.custom_tds_amount}"
                )
            else:
                item.custom_tds_amount = 0
        
        elif tds_apply_on == 'Amount':
            # AMOUNT MODE: Use manual amount, clear rate
            item.custom_tds_rate = 0
            # custom_tds_amount is already set manually by user
            
            frappe.logger().debug(
                f"Using manual TDS amount for {item.item_code}: "
                f"tds_amount={item.custom_tds_amount}"
            )




def calculate_total_tds_amount(doc):
    """
    Sum all custom_tds_amount from items
    
    Only checks if custom_tax_withholding_category_custom has value
    Does NOT check apply_tds at invoice level
    """
    invoice_tax_category_custom = getattr(doc, 'custom_tax_withholding_category_custom', None)
    
    if not invoice_tax_category_custom:
        doc.custom_total_tds_amount = 0
        frappe.logger().debug("TDS not applicable (custom category not set)")
        return
    
    total_tds = 0
    for item in doc.items:
        # Only include items with apply_tds checked
        item_apply_tds = getattr(item, 'apply_tds', False)
        if item_apply_tds:
            total_tds += flt(item.custom_tds_amount) or 0
    
    doc.custom_total_tds_amount = flt(total_tds,5)
    
    frappe.logger().info(f"📊 Total TDS Amount (from custom field): {total_tds}")


def get_tds_rate_from_custom_tax_withholding(doc):
    """
    Get TDS rate from custom_tax_withholding_category_custom → Rates Table
    Uses CUSTOM field, not system field
    """
    custom_tax_category = getattr(doc, 'custom_tax_withholding_category_custom', None)
    
    if not custom_tax_category:
        return None
    
    try:
        # Fetch Tax Withholding Category document
        tax_category = frappe.get_doc("Tax Withholding Category", custom_tax_category)
        
        # Get rate from rates table
        if hasattr(tax_category, 'rates') and tax_category.rates:
            for rate_row in tax_category.rates:
                if hasattr(rate_row, 'tax_withholding_rate'):
                    tds_rate = flt(rate_row.tax_withholding_rate)
                    frappe.logger().debug(
                        f"Found TDS rate from CUSTOM Tax Withholding Category: {tds_rate}%"
                    )
                    return tds_rate
        
        frappe.logger().warning(
            f"No TDS rate found in custom Tax Withholding Category '{custom_tax_category}'"
        )
        return None
        
    except Exception as e:
        frappe.logger().error(
            f"Error fetching TDS rate from custom category: {str(e)}"
        )
        return None


def get_tds_account_from_custom_tax_withholding(doc):
    """
    Get TDS account from custom_tax_withholding_category_custom → Accounts Table
    
    Only checks if custom_tax_withholding_category_custom has value
    Does NOT check apply_tds at invoice level
    """
    # Get CUSTOM Tax Withholding Category field
    custom_tax_category = getattr(doc, 'custom_tax_withholding_category_custom', None)
    
    if not custom_tax_category:
        frappe.logger().debug("TDS not applicable (custom_tax_withholding_category_custom not set)")
        return None
    
    try:
        # Fetch Tax Withholding Category document
        tax_category = frappe.get_doc("Tax Withholding Category", custom_tax_category)
        
        # Find account for this company
        tds_account = None
        if hasattr(tax_category, 'accounts') and tax_category.accounts:
            for account_row in tax_category.accounts:
                if account_row.company == doc.company:
                    tds_account = account_row.account
                    frappe.logger().info(
                        f"✅ Found TDS account from CUSTOM Tax Withholding Category: {tds_account} "
                        f"for company {doc.company}"
                    )
                    break
        
        if not tds_account:
            frappe.logger().warning(
                f"No TDS account found in custom Tax Withholding Category '{custom_tax_category}' "
                f"for company {doc.company}"
            )
        
        return tds_account
        
    except Exception as e:
        frappe.logger().error(
            f"Error fetching TDS account from custom Tax Withholding Category: {str(e)}"
        )
        return None


def update_taxes_table(doc):
    """
    Update or create tax rows for Excise, VAT, and TDS
    TDS account comes from custom_tax_withholding_category_custom field
    """
    total_excise = flt(doc.custom_total_excise_amount, 5)
    total_vat = flt(doc.custom_total_vat_amount, 5)
    total_tds = flt(doc.custom_total_tds_amount, 5)
    
    frappe.logger().info(
        f"Updating taxes table: Excise={total_excise}, VAT={total_vat}, TDS={total_tds}"
    )
    
    # Find accounts
    excise_account = find_account_by_prefix(doc.company, "348204")
    vat_account = find_account_by_prefix(doc.company, "VAT")
    tds_account = get_tds_account_from_custom_tax_withholding(doc)  # Uses CUSTOM field
    
    position = 0
    
    # Update or create excise row
    if excise_account and total_excise != 0:
        update_or_create_tax_row(doc, excise_account, total_excise, position, 
                                 f"Excise Duty - {doc.company}", "Actual", "Add")
        position += 1
    
    # Update or create VAT row
    if vat_account and total_vat != 0:
        update_or_create_tax_row(doc, vat_account, total_vat, position,
                                 f"VAT - {doc.company}", "Actual", "Add")
        position += 1
    
    # Update or create TDS row (from CUSTOM Tax Withholding Category)
    if tds_account and total_tds != 0:
        custom_tax_category = getattr(doc, 'custom_tax_withholding_category_custom', '')
        update_or_create_tax_row(doc, tds_account, total_tds, position,
                                 f"TDS - {custom_tax_category}", "Actual", "Deduct")
        frappe.logger().info(
            f"✅ Created TDS tax row: Account={tds_account}, Amount={total_tds}, "
            f"Category={custom_tax_category}"
        )
        position += 1


def find_account_by_prefix(company, prefix):
    """Find account that starts with the given prefix"""
    accounts = frappe.get_all("Account", filters={
        "company": company,
        "name": ["like", f"{prefix}%"]
    }, fields=["name"], limit=1)
    
    return accounts[0].name if accounts else None


def update_or_create_tax_row(doc, account_head, tax_amount, position, 
                             description, charge_type="Actual", add_deduct="Add"):
    """Update existing tax row or create new one"""
    tax_amount = flt(tax_amount, 5)
    
    existing_row = None
    existing_index = -1
    
    for idx, tax_row in enumerate(doc.taxes or []):
        if tax_row.account_head == account_head and tax_row.charge_type == charge_type:
            existing_row = tax_row
            existing_index = idx
            break
    
    if existing_row:
        existing_row.tax_amount = tax_amount
        existing_row.base_tax_amount = tax_amount
        existing_row.add_deduct_tax = add_deduct
        existing_row.category = "Total"
        existing_row.included_in_print_rate = 0
        
        frappe.logger().debug(
            f"Updated tax row: {account_head} = {tax_amount} ({add_deduct})"
        )
        
        if existing_index != position:
            move_tax_row_to_position(doc, existing_index, position)
    else:
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
        
        new_index = len(doc.taxes) - 1
        if new_index != position and position < len(doc.taxes):
            move_tax_row_to_position(doc, new_index, position)


def move_tax_row_to_position(doc, from_index, to_index):
    """Move a tax row from one position to another"""
    if not doc.taxes or from_index == to_index:
        return
    
    if from_index >= len(doc.taxes) or to_index >= len(doc.taxes):
        return
    
    row = doc.taxes.pop(from_index)
    doc.taxes.insert(to_index, row)
    
    for idx, tax_row in enumerate(doc.taxes):
        tax_row.idx = idx + 1


def validate_purchaseinvoice(doc, method=None):
    """Validation hook"""
    validate_custom_fields(doc)


def validate_custom_fields(doc):
    """Validate and set default values"""
    for item in doc.items:
        if not hasattr(item, 'custom_excise_duty'):
            item.custom_excise_duty = 0
        
        if not hasattr(item, 'custom_tds_rate'):
            item.custom_tds_rate = 0
        
        if not hasattr(item, 'custom_vat_apply_on') or not item.custom_vat_apply_on:
            item.custom_vat_apply_on = 'Percentage (%)'

        if not hasattr(item, 'custom_tds_apply_on') or not item.custom_tds_apply_on:
            item.custom_tds_apply_on = 'Percentage (%)'


@frappe.whitelist()
def populate_item_custom_fields(item_code):
    """Fetch custom fields from Item master"""
    if not item_code:
        return {
            "custom_excise_duty": 0,
            "custom_vat_rate": 0,
            "custom_tds_rate": 0
        }
    
    item = frappe.get_doc("Item", item_code)
    
    custom_excise_duty = flt(item.custom_excise_duty) if hasattr(item, 'custom_excise_duty') else 0
    custom_tds_rate = flt(item.custom_tds_rate) if hasattr(item, 'custom_tds_rate') else 0
    custom_vat_rate = 0
    
    if hasattr(item, 'taxes') and item.taxes:
        custom_vat_rate = flt(item.taxes[0].maximum_net_rate) if item.taxes[0].maximum_net_rate else 0
    
    return {
        "custom_excise_duty": custom_excise_duty,
        "custom_vat_rate": custom_vat_rate,
        "custom_tds_rate": custom_tds_rate
    }