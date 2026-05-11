import frappe
from frappe.utils import flt

"""
Common VAT and Excise calculation handler for selling documents.
Supports: Quotation, Sales Order, Delivery Note

"""

DOCTYPES_WITH_TAXES_TABLE = ["Quotation", "Sales Order", "Delivery Note"]

# Only Delivery Note supports returns (is_return)
RETURN_DOCTYPES = ["Delivery Note"]


def before_save_selling_document(doc, method=None):
    """

    Calculation rules:
    1. custom_excise_value  → always manual (never recalculated)
    2. custom_total         → base_net_amount + custom_excise_value
    3. VAT 13%              → always recalculated from custom_total × 13 / 100
    4. VAT 0%               → always 0
    5. Amount               → manual, never touched
    """
    ensure_vat_apply_on_defaults(doc)
    calculate_custom_total(doc)
    calculate_total_amount_including_excise(doc)
    calculate_item_vat_amounts(doc)
    calculate_total_vat_amount(doc)
    calculate_total_excise_amount(doc)
    calculate_custom_total_amount(doc)

    if doc.doctype in DOCTYPES_WITH_TAXES_TABLE:
        update_taxes_table(doc)

    if hasattr(doc, 'calculate_taxes_and_totals'):
        doc.calculate_taxes_and_totals()

    apply_return_vat_sign(doc)


def validate_selling_document(doc, method=None):
    validate_custom_fields(doc)


def before_validate_selling_document(doc, method=None):
    apply_return_qty_sign(doc)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def ensure_vat_apply_on_defaults(doc):
    for item in doc.items:
        if not getattr(item, 'custom_vat_apply_on', None):
            item.custom_vat_apply_on = 'VAT 13%'


# ---------------------------------------------------------------------------
# Item-level calculations
# ---------------------------------------------------------------------------

def calculate_custom_total(doc):
    """custom_total = base_net_amount + custom_excise_value"""
    for item in doc.items:
        base_net_amount = flt(item.base_net_amount) or 0
        excise_value = flt(getattr(item, 'custom_excise_value', 0)) or 0
        item.custom_total = flt(base_net_amount + excise_value, 5)


def calculate_item_vat_amounts(doc):
    """
    VAT 13% → rate = 13, amount = custom_total × 13 / 100  (always recalculated)
    VAT 0%  → rate = 0,  amount = 0
    Amount  → rate = 0,  amount left as manual
    """
    for item in doc.items:
        vat_apply_on = getattr(item, 'custom_vat_apply_on', 'VAT 13%') or 'VAT 13%'

        if vat_apply_on == 'VAT 13%':
            item.custom_vat_rate = 13
            item.custom_vat_amount = flt((flt(item.custom_total) * 13) / 100, 5)
        elif vat_apply_on == 'VAT 0%':
            item.custom_vat_rate = 0
            item.custom_vat_amount = 0
        elif vat_apply_on == 'Amount':
            item.custom_vat_rate = 0
            # custom_vat_amount preserved as manual


# ---------------------------------------------------------------------------
# Document-level totals
# ---------------------------------------------------------------------------

def calculate_total_amount_including_excise(doc):
    doc.custom_total_amount_including_excise = flt(
        sum(flt(getattr(item, 'custom_total', 0)) for item in doc.items), 5
    )


def calculate_total_excise_amount(doc):
    total_excise = flt(
        sum(flt(getattr(item, 'custom_excise_value', 0)) for item in doc.items), 5
    )
    doc.custom_total_excise_amount = total_excise
    doc.custom_excise = total_excise


def calculate_total_vat_amount(doc):
    doc.custom_total_vat_amount = flt(
        sum(flt(getattr(item, 'custom_vat_amount', 0)) for item in doc.items), 5
    )


def calculate_custom_total_amount(doc):
    """Sum of base_net_amount only (excludes excise)."""
    doc.custom_total_amount = flt(
        sum(flt(item.base_net_amount) for item in doc.items), 5
    )


# ---------------------------------------------------------------------------
# Return sign (Delivery Note only)
# ---------------------------------------------------------------------------

def apply_return_vat_sign(doc):
    """For return Delivery Notes, force custom_vat_amount negative on each item."""
    if not (getattr(doc, 'is_return', 0) and doc.doctype in RETURN_DOCTYPES):
        return
    for item in doc.items:
        item.custom_vat_amount = -abs(flt(getattr(item, 'custom_vat_amount', 0)) or 0)


def apply_return_qty_sign(doc):
    """For return Delivery Notes, force qty negative before core validation."""
    if not (getattr(doc, 'is_return', 0) and doc.doctype in RETURN_DOCTYPES):
        return
    for item in doc.items:
        item.qty = -abs(flt(getattr(item, 'qty', 0)) or 0)


# ---------------------------------------------------------------------------
# Taxes table
# ---------------------------------------------------------------------------

def update_taxes_table(doc):
    """
    Write Excise (account prefix 348204) at position 0
    and VAT (account prefix VAT) at position 1.
    """
    total_excise = flt(getattr(doc, 'custom_total_excise_amount', 0), 5)
    total_vat = flt(getattr(doc, 'custom_total_vat_amount', 0), 5)

    excise_account = find_account_by_prefix(doc.company, "348204")
    vat_account = find_account_by_prefix(doc.company, "VAT")

    position = 0

    if excise_account and total_excise != 0:
        update_or_create_tax_row(doc, excise_account, total_excise, position,
                                 f"Excise Duty - {doc.company}", "Actual", "Add")
        position += 1

    if vat_account and total_vat != 0:
        update_or_create_tax_row(doc, vat_account, total_vat, position,
                                 f"VAT - {doc.company}", "Actual", "Add")


def find_account_by_prefix(company, prefix):
    accounts = frappe.get_all(
        "Account",
        filters={"company": company, "name": ["like", f"{prefix}%"]},
        fields=["name"],
        limit=1
    )
    return accounts[0].name if accounts else None


def update_or_create_tax_row(doc, account_head, tax_amount, position,
                              description, charge_type="Actual", add_deduct="Add"):
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
    if not doc.taxes or from_index == to_index:
        return
    if from_index >= len(doc.taxes) or to_index >= len(doc.taxes):
        return
    row = doc.taxes.pop(from_index)
    doc.taxes.insert(to_index, row)
    for idx, tax_row in enumerate(doc.taxes):
        tax_row.idx = idx + 1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_custom_fields(doc):
    for item in doc.items:
        if not getattr(item, 'custom_vat_apply_on', None):
            item.custom_vat_apply_on = 'VAT 13%'
        if not hasattr(item, 'custom_vat_rate'):
            item.custom_vat_rate = 0


# ---------------------------------------------------------------------------
# Per-doctype wrappers (for hooks.py)
# ---------------------------------------------------------------------------

def before_save_quotation(doc, method=None):
    before_save_selling_document(doc, method)


def before_validate_quotation(doc, method=None):
    before_validate_selling_document(doc, method)


def validate_quotation(doc, method=None):
    validate_selling_document(doc, method)


def before_save_sales_order(doc, method=None):
    before_save_selling_document(doc, method)


def before_validate_sales_order(doc, method=None):
    before_validate_selling_document(doc, method)


def validate_sales_order(doc, method=None):
    validate_selling_document(doc, method)


def before_save_delivery_note(doc, method=None):
    before_save_selling_document(doc, method)


def before_validate_delivery_note(doc, method=None):
    before_validate_selling_document(doc, method)


def validate_delivery_note(doc, method=None):
    validate_selling_document(doc, method)
