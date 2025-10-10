import frappe
from frappe import _
from frappe.utils import flt, cint, money_in_words


def set_custom_rounding_adjustment(doc, method=None):
    """
    Override base_rounding_adjustment with custom_difference_adjustment value
    This function is called during validate/before_submit event of Sales Invoice
    
    """
    
    # Check if custom_difference_adjustment field exists and has a value
    if hasattr(doc, 'custom_difference_adjustment') and doc.custom_difference_adjustment:
        
        # Set base_rounding_adjustment from custom_difference_adjustment
        doc.base_rounding_adjustment = flt(
            doc.custom_difference_adjustment, 
            doc.precision("base_rounding_adjustment")
        )
        
        # # Also set rounding_adjustment for company currency
        # doc.rounding_adjustment = flt(
        #     doc.custom_difference_adjustment, 
        #     doc.precision("rounding_adjustment")
        # )
        
        # Recalculate base_grand_total with the custom adjustment
        # Formula: Base Grand Total = Base Net Total + Base Total Taxes + Custom Adjustment
        doc.base_grand_total = flt(
            doc.base_net_total + doc.base_total_taxes_and_charges,
            doc.precision("base_grand_total")
        )
        doc.custom_difference_adjustment = flt(doc.custom_total_amount - doc.base_grand_total, 2)

        # Also set rounding_adjustment for company currency
        doc.rounding_adjustment = flt(
            doc.custom_difference_adjustment, 
            doc.precision("rounding_adjustment")
        )
        
        # Calculate grand total in transaction currency
        if doc.conversion_rate and doc.conversion_rate != 0:
            doc.grand_total = flt(
                doc.base_grand_total / doc.conversion_rate,
                doc.precision("grand_total")
            )
        else:
            doc.grand_total = doc.base_grand_total
        
        # Update rounded totals
        doc.base_rounded_total = flt(doc.base_grand_total + doc.base_rounding_adjustment)
        doc.rounded_total = flt(doc.grand_total + doc.rounding_adjustment)
        
        # Convert rounded total to words
        doc.base_in_words = money_in_words(doc.base_rounded_total, doc.currency)
        doc.in_words = money_in_words(doc.rounded_total, doc.currency)
        
        doc.outstanding_amount = flt(
            doc.base_rounded_total - doc.total_advance,
            doc.precision("outstanding_amount")
        )
        
        # Log for debugging (optional)
        frappe.logger().debug(
            f"Sales Invoice {doc.name}: Custom Difference Adjustment = {doc.custom_difference_adjustment}, "
            f"Base Rounding Adjustment = {doc.base_rounding_adjustment}, "
            f"Grand Total = {doc.grand_total}, "
            f"Base In Words = {doc.base_in_words}"
        )
        
    else:
        # If custom_difference_adjustment is 0 or empty, clear rounding adjustment
        # This ensures standard ERPNext rounding logic takes over
        doc.base_rounding_adjustment = 0
        doc.rounding_adjustment = 0


@frappe.whitelist()
def convert_amount_to_words(amount, currency):
   
    try:
        amount = flt(amount)
        amount_in_words = money_in_words(amount, currency)
        return amount_in_words
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Error converting amount to words: {amount}"
        )
        return ""


###ITEM Price 

@frappe.whitelist()
def get_custom_amount(customer, price_list, item_code, qty, uom=''):
    """
    Fetch custom_total_vat_inclusive from Item Price based on:
    - item_code
    - price_list (selling_price_list from Sales Invoice)
    - uom
    
    Args:
        customer: Customer name (optional, for future use)
        price_list: Price List name (e.g., "Standard Selling", "Bulk")
        item_code: Item Code
        qty: Quantity (for future tiered pricing)
        uom: Unit of Measurement
        
    Returns:
        dict: {"price": custom_total_vat_inclusive value}
    """
    
    try:
        # Build filters for Item Price
        filters = {
            "item_code": item_code,
            "price_list": price_list,
            "selling": 1  # For sales transactions
            
        }
        
        # Add UOM filter if provided
        if uom:
            filters["uom"] = uom
        
        # Optional: Add customer-specific pricing (higher priority)
        if customer:
            customer_filters = filters.copy()
            customer_filters["customer"] = customer
            
            # Try to get customer-specific price first
            item_price = frappe.db.get_value(
                "Item Price",
                filters=customer_filters,
                fieldname=["custom_total_vat_inclusive", "price_list_rate", "name"],
                as_dict=True
            )
            
            if item_price and item_price.custom_total_vat_inclusive:
                return {
                    "price": flt(item_price.custom_total_vat_inclusive),
                    "price_list_rate": flt(item_price.price_list_rate),
                    "item_price_name": item_price.name
                }
        
        # If no customer-specific price, get general price
        item_price = frappe.db.get_value(
            "Item Price",
            filters=filters,
            fieldname=["custom_total_vat_inclusive", "price_list_rate", "name"],
            as_dict=True,
            order_by="valid_from DESC"  # Get latest price if multiple exist
        )
        
        if item_price:
            # Return custom_total_vat_inclusive if available
            if item_price.custom_total_vat_inclusive:
                return {
                    "price": flt(item_price.custom_total_vat_inclusive),
                    "price_list_rate": flt(item_price.price_list_rate),
                    "item_price_name": item_price.name
                }
            else:
                # Fallback to price_list_rate if custom field is empty
                frappe.msgprint(
                    _("Custom Total VAT Inclusive not found for Item {0} in Price List {1}. Using Price List Rate.").format(
                        item_code, price_list
                    ),
                    indicator="orange",
                    alert=True
                )
                return {
                    "price": flt(item_price.price_list_rate),
                    "price_list_rate": flt(item_price.price_list_rate),
                    "item_price_name": item_price.name
                }
        else:
            # No Item Price found
            frappe.msgprint(
                _("No Item Price found for Item {0} in Price List {1}").format(
                    item_code, price_list
                ),
                indicator="red",
                alert=True
            )
            return {"price": 0, "price_list_rate": 0, "item_price_name": None}
            
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Error fetching custom amount for {item_code}"
        )
        frappe.throw(_("Error fetching price: {0}").format(str(e)))
        return {"price": 0, "price_list_rate": 0, "item_price_name": None}


@frappe.whitelist()
def get_custom_amount_bulk(items, price_list):
    """
    Fetch prices for multiple items at once (performance optimization)
    
    Args:
        items: List of dicts with item_code, uom, qty
        price_list: Price List name
        
    Returns:
        dict: {item_code: price_data}
    """
    
    try:
        import json
        if isinstance(items, str):
            items = json.loads(items)
        
        result = {}
        
        for item in items:
            item_code = item.get("item_code")
            uom = item.get("uom")
            qty = item.get("qty", 1)
            
            if item_code:
                price_data = get_custom_amount(
                    customer=None,
                    price_list=price_list,
                    item_code=item_code,
                    qty=qty,
                    uom=uom
                )
                result[item_code] = price_data
        
        return result
        
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Error in bulk price fetch"
        )
        return {}