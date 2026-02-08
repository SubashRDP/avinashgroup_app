import frappe
from frappe import _

"""
Field mapping for TDS, Excise, and VAT when creating documents from other documents.
Handles:
- Supplier Quotation → Purchase Order
- Purchase Order → Purchase Receipt
- Purchase Order → Purchase Invoice
- Purchase Invoice → Purchase Receipt
"""

# Item-level fields to map
ITEM_FIELDS_TO_MAP = [
    "custom_excise_value",
    "custom_total",
    "custom_vat_apply_on",
    "custom_vat_rate",
    "custom_vat_amount",
    "custom_tds_apply_on",
    "custom_tds_rate",
    "custom_tds_amount",
    "apply_tds"
]

# Document-level fields to map
DOC_FIELDS_TO_MAP = [
    "custom_total_amount_including_excise",
    "custom_total_excise_amount",
    "custom_total_vat_amount",
    "custom_total_tds_amount",
    "custom_tax_withholding_category_custom",
    "custom_excise"
]


def map_taxes_fields_to_target(source_doc, target_doc, source_item=None, target_item=None):
    """
    Map tax fields from source to target document/item.
    Can be used for both document-level and item-level mapping.
    """
    if source_item and target_item:
        # Item-level mapping
        for field in ITEM_FIELDS_TO_MAP:
            if hasattr(source_item, field) and hasattr(target_item, field):
                value = getattr(source_item, field, None)
                if value is not None:
                    setattr(target_item, field, value)
    else:
        # Document-level mapping
        for field in DOC_FIELDS_TO_MAP:
            if hasattr(source_doc, field) and hasattr(target_doc, field):
                value = getattr(source_doc, field, None)
                if value is not None:
                    setattr(target_doc, field, value)


def after_mapping_supplier_quotation_to_purchase_order(source_doc, target_doc, source_parent=None):
    """Called after mapping Supplier Quotation to Purchase Order"""
    # Map document-level fields
    for field in DOC_FIELDS_TO_MAP:
        if hasattr(source_doc, field):
            value = getattr(source_doc, field, None)
            if value is not None and hasattr(target_doc, field):
                target_doc.set(field, value)

    # Map item-level fields
    if source_doc.items and target_doc.items:
        # Create a mapping of item_code to source item for lookup
        source_items_map = {}
        for item in source_doc.items:
            key = (item.item_code, item.idx)
            source_items_map[key] = item

        for target_item in target_doc.items:
            # Try to find matching source item
            source_item = None

            # First try by supplier_quotation_item reference
            if hasattr(target_item, 'supplier_quotation_item') and target_item.supplier_quotation_item:
                for src_item in source_doc.items:
                    if src_item.name == target_item.supplier_quotation_item:
                        source_item = src_item
                        break

            # Fallback to item_code matching
            if not source_item:
                for src_item in source_doc.items:
                    if src_item.item_code == target_item.item_code:
                        source_item = src_item
                        break

            if source_item:
                for field in ITEM_FIELDS_TO_MAP:
                    if hasattr(source_item, field):
                        value = getattr(source_item, field, None)
                        if value is not None and hasattr(target_item, field):
                            target_item.set(field, value)


def after_mapping_purchase_order_to_purchase_receipt(source_doc, target_doc, source_parent=None):
    """Called after mapping Purchase Order to Purchase Receipt"""
    # Map document-level fields
    for field in DOC_FIELDS_TO_MAP:
        if hasattr(source_doc, field):
            value = getattr(source_doc, field, None)
            if value is not None and hasattr(target_doc, field):
                target_doc.set(field, value)

    # Map item-level fields
    if source_doc.items and target_doc.items:
        for target_item in target_doc.items:
            source_item = None

            # Try by purchase_order_item reference
            if hasattr(target_item, 'purchase_order_item') and target_item.purchase_order_item:
                for src_item in source_doc.items:
                    if src_item.name == target_item.purchase_order_item:
                        source_item = src_item
                        break

            # Fallback to item_code matching
            if not source_item:
                for src_item in source_doc.items:
                    if src_item.item_code == target_item.item_code:
                        source_item = src_item
                        break

            if source_item:
                for field in ITEM_FIELDS_TO_MAP:
                    if hasattr(source_item, field):
                        value = getattr(source_item, field, None)
                        if value is not None and hasattr(target_item, field):
                            target_item.set(field, value)


def after_mapping_purchase_order_to_purchase_invoice(source_doc, target_doc, source_parent=None):
    """Called after mapping Purchase Order to Purchase Invoice"""
    # Map document-level fields
    for field in DOC_FIELDS_TO_MAP:
        if hasattr(source_doc, field):
            value = getattr(source_doc, field, None)
            if value is not None and hasattr(target_doc, field):
                target_doc.set(field, value)

    # Map item-level fields
    if source_doc.items and target_doc.items:
        for target_item in target_doc.items:
            source_item = None

            # Try by purchase_order_item reference
            if hasattr(target_item, 'purchase_order_item') and target_item.purchase_order_item:
                for src_item in source_doc.items:
                    if src_item.name == target_item.purchase_order_item:
                        source_item = src_item
                        break

            # Fallback to item_code matching
            if not source_item:
                for src_item in source_doc.items:
                    if src_item.item_code == target_item.item_code:
                        source_item = src_item
                        break

            if source_item:
                for field in ITEM_FIELDS_TO_MAP:
                    if hasattr(source_item, field):
                        value = getattr(source_item, field, None)
                        if value is not None and hasattr(target_item, field):
                            target_item.set(field, value)


def after_mapping_purchase_invoice_to_purchase_receipt(source_doc, target_doc, source_parent=None):
    """Called after mapping Purchase Invoice to Purchase Receipt"""
    # Map document-level fields
    for field in DOC_FIELDS_TO_MAP:
        if hasattr(source_doc, field):
            value = getattr(source_doc, field, None)
            if value is not None and hasattr(target_doc, field):
                target_doc.set(field, value)

    # Map item-level fields
    if source_doc.items and target_doc.items:
        for target_item in target_doc.items:
            source_item = None

            # Try by purchase_invoice_item reference
            if hasattr(target_item, 'purchase_invoice_item') and target_item.purchase_invoice_item:
                for src_item in source_doc.items:
                    if src_item.name == target_item.purchase_invoice_item:
                        source_item = src_item
                        break

            # Fallback to item_code matching
            if not source_item:
                for src_item in source_doc.items:
                    if src_item.item_code == target_item.item_code:
                        source_item = src_item
                        break

            if source_item:
                for field in ITEM_FIELDS_TO_MAP:
                    if hasattr(source_item, field):
                        value = getattr(source_item, field, None)
                        if value is not None and hasattr(target_item, field):
                            target_item.set(field, value)


# Whitelisted method to get tax fields from source document
@frappe.whitelist()
def get_taxes_from_source(source_doctype, source_name, target_doctype):
    """
    Get tax field values from source document to populate in target.
    Called via JavaScript when creating documents from buttons.
    """
    source_doc = frappe.get_doc(source_doctype, source_name)

    result = {
        "doc_fields": {},
        "items": []
    }

    # Document-level fields
    for field in DOC_FIELDS_TO_MAP:
        if hasattr(source_doc, field):
            result["doc_fields"][field] = getattr(source_doc, field, None)

    # Item-level fields
    for item in source_doc.items:
        item_data = {"item_code": item.item_code, "idx": item.idx, "name": item.name}
        for field in ITEM_FIELDS_TO_MAP:
            if hasattr(item, field):
                item_data[field] = getattr(item, field, None)
        result["items"].append(item_data)

    return result
