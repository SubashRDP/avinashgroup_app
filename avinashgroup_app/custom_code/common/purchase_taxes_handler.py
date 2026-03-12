import frappe
from frappe import _
from frappe.utils import flt

"""
Common TDS, Excise, and VAT calculation handler for Purchase documents.
Supports: Purchase Invoice, Purchase Order, Purchase Receipt, Supplier Quotation
"""

# Doctype configuration - defines which doctypes have taxes table
DOCTYPES_WITH_TAXES_TABLE = ["Purchase Invoice", "Purchase Receipt", "Purchase Order", "Supplier Quotation"]


def before_save_purchase_document(doc, method=None):
    """
    Main hook that runs before saving any Purchase document.
    Works with Purchase Invoice, Purchase Order, Purchase Receipt, Supplier Quotation.
    """
    # 0. Ensure Apply On defaults are set
    ensure_apply_on_defaults(doc)

    # 1. Calculate item-level totals (respects manual excise)
    calculate_custom_total(doc)

    # 2. Calculate total amount including excise
    calculate_total_amount_including_excise(doc)

    # 3. VAT calculation
    calculate_item_vat_amounts(doc)
    calculate_total_vat_amount(doc)

    # 4. TDS calculation (using CUSTOM field)
    calculate_item_tds_amounts(doc)
    calculate_total_tds_amount(doc)

    # 5. Excise totals
    calculate_total_excise_amount(doc)

    # 6. Update taxes table (only for doctypes that have it)
    if doc.doctype in DOCTYPES_WITH_TAXES_TABLE:
        update_taxes_table(doc)

    # 7. Let ERPNext calculate standard totals
    if hasattr(doc, 'calculate_taxes_and_totals'):
        doc.calculate_taxes_and_totals()


def validate_purchase_document(doc, method=None):
    """Validation hook for purchase documents"""
    validate_custom_fields(doc)


def ensure_apply_on_defaults(doc):
    """Ensure all items have custom_vat_apply_on and custom_tds_apply_on set to default"""
    for item in doc.items:
        if not getattr(item, 'custom_vat_apply_on', None):
            item.custom_vat_apply_on = 'Percentage (%)'

        if not getattr(item, 'custom_tds_apply_on', None):
            item.custom_tds_apply_on = 'Percentage (%)'


def calculate_custom_total(doc):
    """Calculate custom_total = base_net_amount + custom_excise_value"""
    for item in doc.items:
        base_net_amount = flt(item.base_net_amount) or 0
        excise_value = flt(getattr(item, 'custom_excise_value', 0)) or 0
        item.custom_total = flt(base_net_amount + excise_value, 5)


def calculate_total_amount_including_excise(doc):
    """Sum all custom_total from items"""
    total_including_excise = sum(flt(getattr(item, 'custom_total', 0)) or 0 for item in doc.items)
    doc.custom_total_amount_including_excise = flt(total_including_excise, 5)


def calculate_total_excise_amount(doc):
    """Sum all custom_excise_value from items"""
    total_excise = sum(flt(getattr(item, 'custom_excise_value', 0)) or 0 for item in doc.items)
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
            custom_total = flt(getattr(item, 'custom_total', 0)) or 0
            custom_vat_rate = flt(getattr(item, 'custom_vat_rate', 0)) or 0
            item.custom_vat_amount = flt((custom_total * custom_vat_rate) / 100, 5)
        elif vat_apply_on == 'Amount':
            item.custom_vat_rate = 0


def calculate_total_vat_amount(doc):
    """Sum all custom_vat_amount from items"""
    total_vat = sum(flt(getattr(item, 'custom_vat_amount', 0)) or 0 for item in doc.items)
    doc.custom_total_vat_amount = flt(total_vat, 5)


def calculate_item_tds_amounts(doc):
    """
    Calculate TDS amount for each item based on Percentage or Amount mode.

    Conditions:
    1. custom_tax_withholding_category_custom has a value (at document level)
    2. apply_tds is checked at line item level
    """
    invoice_tax_category_custom = getattr(doc, 'custom_tax_withholding_category_custom', None)
    tds_rate_from_category = get_tds_rate_from_custom_tax_withholding(doc)

    for item in doc.items:
        item_apply_tds = getattr(item, 'apply_tds', False)

        if not (invoice_tax_category_custom and item_apply_tds):
            item.custom_tds_amount = 0
            item.custom_tds_rate = 0
            continue

        tds_apply_on = getattr(item, 'custom_tds_apply_on', 'Percentage (%)')

        if not tds_apply_on:
            item.custom_tds_apply_on = 'Percentage (%)'
            tds_apply_on = 'Percentage (%)'

        if tds_apply_on == 'Percentage (%)':
            if tds_rate_from_category and not getattr(item, 'custom_tds_rate', 0):
                item.custom_tds_rate = tds_rate_from_category

            custom_tds_rate = flt(getattr(item, 'custom_tds_rate', 0)) or 0

            if custom_tds_rate > 0:
                custom_total = flt(getattr(item, 'custom_total', 0)) or 0
                item.custom_tds_amount = flt((custom_total * custom_tds_rate) / 100, 5)
            else:
                item.custom_tds_amount = 0

        elif tds_apply_on == 'Amount':
            item.custom_tds_rate = 0


def calculate_total_tds_amount(doc):
    """Sum all custom_tds_amount from items where apply_tds is checked"""
    invoice_tax_category_custom = getattr(doc, 'custom_tax_withholding_category_custom', None)

    if not invoice_tax_category_custom:
        doc.custom_total_tds_amount = 0
        return

    total_tds = 0
    for item in doc.items:
        item_apply_tds = getattr(item, 'apply_tds', False)
        if item_apply_tds:
            total_tds += flt(getattr(item, 'custom_tds_amount', 0)) or 0

    doc.custom_total_tds_amount = flt(total_tds, 5)


def get_tds_rate_from_custom_tax_withholding(doc):
    """Get TDS rate from custom_tax_withholding_category_custom"""
    custom_tax_category = getattr(doc, 'custom_tax_withholding_category_custom', None)

    if not custom_tax_category:
        return None

    try:
        tax_category = frappe.get_doc("Tax Withholding Category", custom_tax_category)

        if hasattr(tax_category, 'rates') and tax_category.rates:
            for rate_row in tax_category.rates:
                if hasattr(rate_row, 'tax_withholding_rate'):
                    return flt(rate_row.tax_withholding_rate)

        return None

    except Exception as e:
        frappe.logger().error(f"Error fetching TDS rate: {str(e)}")
        return None


def get_tds_account_from_custom_tax_withholding(doc):
    """Get TDS account from custom_tax_withholding_category_custom"""
    custom_tax_category = getattr(doc, 'custom_tax_withholding_category_custom', None)

    if not custom_tax_category:
        return None

    try:
        tax_category = frappe.get_doc("Tax Withholding Category", custom_tax_category)

        tds_account = None
        if hasattr(tax_category, 'accounts') and tax_category.accounts:
            for account_row in tax_category.accounts:
                if account_row.company == doc.company:
                    tds_account = account_row.account
                    break

        return tds_account

    except Exception as e:
        frappe.logger().error(f"Error fetching TDS account: {str(e)}")
        return None


def update_taxes_table(doc):
    """Update or create tax rows for Excise, VAT, and TDS"""
    total_excise = flt(getattr(doc, 'custom_total_excise_amount', 0), 5)
    total_vat = flt(getattr(doc, 'custom_total_vat_amount', 0), 5)
    total_tds = flt(getattr(doc, 'custom_total_tds_amount', 0), 5)

    excise_account = find_account_by_prefix(doc.company, "348204")
    vat_account = find_account_by_prefix(doc.company, "VAT")
    tds_account = get_tds_account_from_custom_tax_withholding(doc)

    position = 0

    if excise_account and total_excise != 0:
        update_or_create_tax_row(doc, excise_account, total_excise, position,
                                 f"Excise Duty - {doc.company}", "Actual", "Add")
        position += 1

    if vat_account and total_vat != 0:
        update_or_create_tax_row(doc, vat_account, total_vat, position,
                                 f"VAT - {doc.company}", "Actual", "Add")
        position += 1

    if tds_account and total_tds != 0:
        custom_tax_category = getattr(doc, 'custom_tax_withholding_category_custom', '')
        update_or_create_tax_row(doc, tds_account, total_tds, position,
                                 f"TDS - {custom_tax_category}", "Actual", "Deduct")
        position += 1
    else:
        # Remove any stale TDS rows (total_tds is now 0 or no account found)
        remove_tds_tax_rows(doc)


def remove_tds_tax_rows(doc):
    """Remove all TDS tax rows (charge_type=Actual, add_deduct_tax=Deduct) from the taxes table"""
    if not doc.taxes:
        return

    rows_to_remove = [
        row for row in doc.taxes
        if row.charge_type == "Actual" and row.add_deduct_tax == "Deduct"
    ]

    for row in rows_to_remove:
        doc.taxes.remove(row)

    if rows_to_remove:
        for idx, tax_row in enumerate(doc.taxes):
            tax_row.idx = idx + 1


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


def validate_custom_fields(doc):
    """Validate and set default values"""
    for item in doc.items:
        if not hasattr(item, 'custom_excise_duty'):
            item.custom_excise_duty = 0

        if not hasattr(item, 'custom_tds_rate'):
            item.custom_tds_rate = 0

        if not getattr(item, 'custom_vat_apply_on', None):
            item.custom_vat_apply_on = 'Percentage (%)'

        if not getattr(item, 'custom_tds_apply_on', None):
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

    custom_excise_duty = flt(getattr(item, 'custom_excise_duty', 0))
    custom_tds_rate = flt(getattr(item, 'custom_tds_rate', 0))
    custom_vat_rate = 0

    if hasattr(item, 'taxes') and item.taxes:
        custom_vat_rate = flt(item.taxes[0].maximum_net_rate) if item.taxes[0].maximum_net_rate else 0

    return {
        "custom_excise_duty": custom_excise_duty,
        "custom_vat_rate": custom_vat_rate,
        "custom_tds_rate": custom_tds_rate
    }


# Wrapper functions for specific doctypes (for hooks.py)
def before_save_purchase_invoice(doc, method=None):
    """Wrapper for Purchase Invoice"""
    before_save_purchase_document(doc, method)


def validate_purchase_invoice(doc, method=None):
    """Wrapper for Purchase Invoice"""
    validate_purchase_document(doc, method)


def before_save_purchase_order(doc, method=None):
    """Wrapper for Purchase Order"""
    before_save_purchase_document(doc, method)


def validate_purchase_order(doc, method=None):
    """Wrapper for Purchase Order"""
    validate_purchase_document(doc, method)


def before_save_purchase_receipt(doc, method=None):
    """Wrapper for Purchase Receipt"""
    before_save_purchase_document(doc, method)


def validate_purchase_receipt(doc, method=None):
    """Wrapper for Purchase Receipt"""
    validate_purchase_document(doc, method)


def before_save_supplier_quotation(doc, method=None):
    """Wrapper for Supplier Quotation"""
    before_save_purchase_document(doc, method)


def validate_supplier_quotation(doc, method=None):
    """Wrapper for Supplier Quotation"""
    validate_purchase_document(doc, method)



