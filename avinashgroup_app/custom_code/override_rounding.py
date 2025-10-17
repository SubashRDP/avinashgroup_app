import frappe
from frappe import _
from frappe.utils import flt, cint, money_in_words


def recalculate_taxes_on_custom_total(doc):
    """
    Recalculate taxes based on the new base_total (which includes excise duty)
    This ensures taxes are calculated on (item amount + excise duty) instead of just item amount
    """
    if not doc.taxes:
        doc.base_total_taxes_and_charges = 0
        doc.total_taxes_and_charges = 0
        return
    
    # Get the new base_total (sum of custom_total which includes excise)
    sum_custom_total = sum(flt(item.custom_total) for item in doc.items)
    
    # Update base_net_total to match our custom total
    doc.base_net_total = flt(sum_custom_total, doc.precision("base_net_total"))
    doc.net_total = flt(sum_custom_total / flt(doc.conversion_rate or 1), doc.precision("net_total"))
    
    # Recalculate each tax line based on the new base_total
    cumulative_tax = 0
    cumulative_total = sum_custom_total
    
    for tax in doc.taxes:
        if tax.charge_type == "On Net Total":
            # Recalculate tax on the new base_total (custom_total)
            tax_rate = flt(tax.rate)
            tax_amount = flt(sum_custom_total * tax_rate / 100, doc.precision("tax_amount", tax))
            
            tax.base_tax_amount = tax_amount
            tax.base_tax_amount_after_discount_amount = tax_amount
            cumulative_tax += tax_amount
            cumulative_total += tax_amount
            tax.base_total = flt(cumulative_total, doc.precision("base_total", tax))
            
            # Update transaction currency values
            if doc.conversion_rate:
                tax.tax_amount = flt(tax_amount / doc.conversion_rate, doc.precision("tax_amount", tax))
                tax.tax_amount_after_discount_amount = tax.tax_amount
                tax.total = flt(cumulative_total / doc.conversion_rate, doc.precision("total", tax))
            else:
                tax.tax_amount = tax_amount
                tax.tax_amount_after_discount_amount = tax_amount
                tax.total = cumulative_total
            
            frappe.logger().info(f"Recalculated tax {tax.description}: Rate={tax_rate}%, Amount={tax_amount}, Cumulative Total={cumulative_total}")
        
        elif tax.charge_type == "Actual":
            # Keep actual tax as is
            tax_amount = flt(tax.base_tax_amount)
            cumulative_tax += tax_amount
            cumulative_total += tax_amount
            tax.base_total = flt(cumulative_total, doc.precision("base_total", tax))
            
            if doc.conversion_rate:
                tax.total = flt(cumulative_total / doc.conversion_rate, doc.precision("total", tax))
            else:
                tax.total = cumulative_total
        
        elif tax.charge_type in ["On Previous Row Total", "On Previous Row Amount"]:
            # Handle taxes based on previous rows
            if tax.row_id and int(tax.row_id) > 0:
                # Get previous row
                prev_row_idx = int(tax.row_id) - 1
                if prev_row_idx < len(doc.taxes):
                    prev_tax = doc.taxes[prev_row_idx]
                    
                    if tax.charge_type == "On Previous Row Total":
                        base_amount = flt(prev_tax.base_total)
                    else:  # On Previous Row Amount
                        base_amount = flt(prev_tax.base_tax_amount)
                    
                    tax_rate = flt(tax.rate)
                    tax_amount = flt(base_amount * tax_rate / 100, doc.precision("tax_amount", tax))
                    
                    tax.base_tax_amount = tax_amount
                    tax.base_tax_amount_after_discount_amount = tax_amount
                    cumulative_tax += tax_amount
                    cumulative_total += tax_amount
                    tax.base_total = flt(cumulative_total, doc.precision("base_total", tax))
                    
                    if doc.conversion_rate:
                        tax.tax_amount = flt(tax_amount / doc.conversion_rate, doc.precision("tax_amount", tax))
                        tax.tax_amount_after_discount_amount = tax.tax_amount
                        tax.total = flt(cumulative_total / doc.conversion_rate, doc.precision("total", tax))
                    else:
                        tax.tax_amount = tax_amount
                        tax.tax_amount_after_discount_amount = tax_amount
                        tax.total = cumulative_total
    
    # Update total taxes and charges
    doc.base_total_taxes_and_charges = flt(cumulative_tax, doc.precision("base_total_taxes_and_charges"))
    if doc.conversion_rate:
        doc.total_taxes_and_charges = flt(cumulative_tax / doc.conversion_rate, doc.precision("total_taxes_and_charges"))
    else:
        doc.total_taxes_and_charges = cumulative_tax
    
    frappe.logger().info(f"Total taxes recalculated: Base={doc.base_total_taxes_and_charges}, Currency={doc.total_taxes_and_charges}")


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

        # Update payment schedule with outstanding amount
        update_payment_schedule(doc)
        
        # Log for debugging (optional)
        frappe.logger().debug(
            f"Sales Invoice {doc.name}: Custom Difference Adjustment = {doc.custom_difference_adjustment}, "
            f"Base Rounding Adjustment = {doc.base_rounding_adjustment}, "
            f"Grand Total = {doc.grand_total}, "
            f"Outstanding Amount = {doc.outstanding_amount}"
        )
        
    else:
        # If custom_difference_adjustment is 0 or empty, clear rounding adjustment
        # This ensures standard ERPNext rounding logic takes over
        doc.base_rounding_adjustment = 0
        doc.rounding_adjustment = 0


def update_payment_schedule(doc):
    """
    Update payment_amount and base_payment_amount in Payment Schedule table
    to match the outstanding_amount
    """
    if not hasattr(doc, 'payment_schedule') or not doc.payment_schedule:
        return
    
    outstanding = flt(doc.outstanding_amount, doc.precision("outstanding_amount"))
    
    # If there's only one payment schedule row, set it to outstanding amount
    if len(doc.payment_schedule) == 1:
        doc.payment_schedule[0].payment_amount = flt(
            outstanding / doc.conversion_rate if doc.conversion_rate else outstanding,
            doc.precision("payment_amount", "payment_schedule")
        )
        doc.payment_schedule[0].base_payment_amount = flt(
            outstanding,
            doc.precision("base_payment_amount", "payment_schedule")
        )
    
    # If multiple payment schedules, distribute proportionally or update all
    elif len(doc.payment_schedule) > 1:
        # Option 1: Update first row only
        doc.payment_schedule[0].payment_amount = flt(
            outstanding / doc.conversion_rate if doc.conversion_rate else outstanding,
            doc.precision("payment_amount", "payment_schedule")
        )
        doc.payment_schedule[0].base_payment_amount = flt(
            outstanding,
            doc.precision("base_payment_amount", "payment_schedule")
        )
        
        # Option 2: Distribute equally across all rows (uncomment if needed)
        # per_row_amount = outstanding / len(doc.payment_schedule)
        # for row in doc.payment_schedule:
        #     row.payment_amount = flt(
        #         per_row_amount / doc.conversion_rate if doc.conversion_rate else per_row_amount,
        #         doc.precision("payment_amount", "payment_schedule")
        #     )
        #     row.base_payment_amount = flt(
        #         per_row_amount,
        #         doc.precision("base_payment_amount", "payment_schedule")
        #     )
    
    frappe.logger().debug(
        f"Payment Schedule updated for {doc.name}: Outstanding = {outstanding}"
    )


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
def get_custom_amount(customer, price_list, item_code, qty, uom):
    """Fetch custom_total_vat_inclusive from Item Price"""
    try:
        # Get Item Price
        filters = {
            'item_code': item_code,
            'price_list': price_list,
            'uom': uom
        }
        
        item_price = frappe.get_all(
            'Item Price',
            filters=filters,
            fields=['custom_total_vat_inclusive', 'price_list_rate'],
            limit=1
        )
        
        if item_price and len(item_price) > 0:
            price = flt(item_price[0].get('custom_total_vat_inclusive', 0))
            if price == 0:
                price = flt(item_price[0].get('price_list_rate', 0))
            return {'price': price}
        
        return {'price': 0}
        
    except Exception as e:
        frappe.log_error(f"Error in get_custom_amount: {str(e)}")
        return {'price': 0}


def override_totals_before_validate(doc, method=None):
    """
    FIRST HOOK: Calculate excise duty values
    This runs before ERPNext's validation
    """
    if not doc.items:
        return
    
    # Calculate excise duty for each item
    for item in doc.items:
        qty = flt(item.qty)
        amount = flt(item.amount)
        excise_duty = flt(item.custom_excise_duty)
        
        # Calculate excise value and custom total
        excise_value = flt(excise_duty * qty, 2)
        custom_total = flt(amount + excise_value, 2)
        
        # Set values
        item.custom_excise_value = excise_value
        item.custom_total = custom_total
    
    # Calculate sum of custom_total
    sum_custom_total = sum(flt(item.custom_total) for item in doc.items)
    
    # Override base_total and total
    doc.base_total = flt(sum_custom_total, 2)
    doc.total = flt(sum_custom_total / flt(doc.conversion_rate or 1), 2)
    
    frappe.logger().info(f"Before Validate - Sum of custom_total: {sum_custom_total}")


def override_totals_validate(doc, method=None):
    """
    SECOND HOOK: Re-override after ERPNext validation AND recalculate taxes
    This ensures our values persist after ERPNext recalculates
    """
    if not doc.items:
        return
    
    # Recalculate sum of custom_total (in case ERPNext changed amounts)
    sum_custom_total = 0
    for item in doc.items:
        qty = flt(item.qty)
        amount = flt(item.amount)
        excise_duty = flt(item.custom_excise_duty)
        
        excise_value = flt(excise_duty * qty, 2)
        custom_total = flt(amount + excise_value, 2)
        
        item.custom_excise_value = excise_value
        item.custom_total = custom_total
        sum_custom_total += custom_total
    
    # Override base_total and total
    old_base_total = doc.base_total
    doc.base_total = flt(sum_custom_total, 2)
    doc.total = flt(sum_custom_total / flt(doc.conversion_rate or 1), 2)
    
    frappe.logger().info(f"Base total changed from {old_base_total} to {doc.base_total}")

    # **KEY CHANGE**: Recalculate taxes based on new base_total
    recalculate_taxes_on_custom_total(doc)

    # Recalculate grand total with new taxes
    base_taxes = flt(doc.base_total_taxes_and_charges)
    doc.base_grand_total = flt(doc.base_total + base_taxes, 2)
    doc.grand_total = flt(doc.base_grand_total / flt(doc.conversion_rate or 1), 2)
    
    frappe.logger().info(f"Validate - Base Total: {doc.base_total}, Base Taxes: {base_taxes}, Base Grand Total: {doc.base_grand_total}")
    set_custom_rounding_adjustment(doc, method)



def override_totals_before_save(doc, method=None):
    """
    THIRD HOOK: Final override before saving
    Calculate rounding adjustment from custom_difference_calculation_table
    """
    if not doc.items:
        return
    
    # Recalculate custom totals one more time
    sum_custom_total = sum(flt(item.custom_total) for item in doc.items)
    doc.base_total = flt(sum_custom_total, 2)
    doc.total = flt(sum_custom_total / flt(doc.conversion_rate or 1), 2)
    
    # Recalculate taxes on custom total
    recalculate_taxes_on_custom_total(doc)
    
    # Recalculate grand total
    base_taxes = flt(doc.base_total_taxes_and_charges)
    doc.base_grand_total = flt(doc.base_total + base_taxes, 2)
    doc.grand_total = flt(doc.base_grand_total / flt(doc.conversion_rate or 1), 2)
    
    # Calculate rounding adjustment from custom_difference_calculation_table
    if doc.custom_difference_calculation_table:
        custom_total_amount = sum(flt(row.total_amount) for row in doc.custom_difference_calculation_table)
        custom_total_amount = flt(custom_total_amount, 2)
        
        # Set custom_total_amount
        doc.custom_total_amount = custom_total_amount
        
        # Calculate difference
        difference = flt(custom_total_amount - doc.base_grand_total, 2)
        doc.custom_difference_adjustment = difference
        
        # Calculate rounded total
        rounded_total = flt(doc.base_grand_total + difference, 2)
        doc.rounded_total = rounded_total
        doc.base_rounded_total = rounded_total
        
        # Calculate outstanding
        total_advance = flt(doc.total_advance)
        doc.outstanding_amount = flt(rounded_total - total_advance, 2)
        
        # Convert to words
        currency = doc.currency or frappe.defaults.get_default("currency")
        doc.base_in_words = money_in_words(rounded_total, currency)
        doc.in_words = money_in_words(flt(rounded_total / flt(doc.conversion_rate or 1), 2), currency)
        
        frappe.logger().info(f"Rounding - Custom Total: {custom_total_amount}, Base Grand Total: {doc.base_grand_total}, Difference: {difference}, Rounded Total: {rounded_total}")
    
    # Update payment schedule
    if doc.payment_schedule and len(doc.payment_schedule) > 0:
        outstanding = flt(doc.outstanding_amount)
        conversion_rate = flt(doc.conversion_rate or 1)
        
        # Update first payment schedule row
        doc.payment_schedule[0].base_payment_amount = outstanding
        doc.payment_schedule[0].payment_amount = flt(outstanding / conversion_rate, 2)


def update_item_net_amounts(doc):
    """
    Update item-level net_amount and base_net_amount to include excise duty
    This is CRITICAL for GL entries to match
    """
    for item in doc.items:
        # Use custom_total (which includes excise) as the net amount
        item.base_net_amount = flt(item.custom_total, item.precision("base_net_amount"))
        item.net_amount = flt(item.custom_total / flt(doc.conversion_rate or 1), item.precision("net_amount"))
        
        # Also update base_amount to match (for consistency)
        item.base_amount = item.base_net_amount
        
        frappe.logger().info(f"Item {item.item_code}: base_net_amount updated to {item.base_net_amount}")


def override_totals_on_submit(doc, method=None):
    """
    CRITICAL: Hook that runs ON submit (after validation but before GL posting)
    This is our last chance to fix totals before GL entries are created
    """
    frappe.logger().info(f"=== ON SUBMIT: Final override for {doc.name} ===")
    
    if not doc.items:
        return
    
    # Recalculate everything one more time
    sum_custom_total = 0
    for item in doc.items:
        qty = flt(item.qty)
        amount = flt(item.amount)
        excise_duty = flt(item.custom_excise_duty)
        
        excise_value = flt(excise_duty * qty, 2)
        custom_total = flt(amount + excise_value, 2)
        
        item.custom_excise_value = excise_value
        item.custom_total = custom_total
        sum_custom_total += custom_total
    
    # CRITICAL: Update item-level net amounts for GL entries
    update_item_net_amounts(doc)
    
    # Override totals
    doc.base_total = flt(sum_custom_total, 2)
    doc.total = flt(sum_custom_total / flt(doc.conversion_rate or 1), 2)
    doc.base_net_total = doc.base_total
    doc.net_total = doc.total
    
    # Recalculate taxes
    recalculate_taxes_on_custom_total(doc)
    
    # Recalculate grand total
    base_taxes = flt(doc.base_total_taxes_and_charges)
    doc.base_grand_total = flt(doc.base_total + base_taxes, 2)
    doc.grand_total = flt(doc.base_grand_total / flt(doc.conversion_rate or 1), 2)
    
    # Apply rounding if exists
    if doc.custom_difference_calculation_table:
        custom_total_amount = sum(flt(row.total_amount) for row in doc.custom_difference_calculation_table)
        custom_total_amount = flt(custom_total_amount, 2)
        
        doc.custom_total_amount = custom_total_amount
        difference = flt(custom_total_amount - doc.base_grand_total, 2)
        doc.custom_difference_adjustment = difference
        doc.base_rounding_adjustment = difference
        doc.rounding_adjustment = flt(difference / flt(doc.conversion_rate or 1), 2)
        
        doc.base_rounded_total = flt(doc.base_grand_total + difference, 2)
        doc.rounded_total = flt(doc.base_rounded_total / flt(doc.conversion_rate or 1), 2)
    else:
        doc.base_rounding_adjustment = 0
        doc.rounding_adjustment = 0
        doc.base_rounded_total = doc.base_grand_total
        doc.rounded_total = doc.grand_total
    
    # Update outstanding
    doc.outstanding_amount = flt(doc.base_rounded_total - flt(doc.total_advance), 2)
    
    # Update payment schedule
    if doc.payment_schedule and len(doc.payment_schedule) > 0:
        outstanding = flt(doc.outstanding_amount)
        conversion_rate = flt(doc.conversion_rate or 1)
        doc.payment_schedule[0].base_payment_amount = outstanding
        doc.payment_schedule[0].payment_amount = flt(outstanding / conversion_rate, 2)
    
    frappe.logger().info(f"ON SUBMIT Complete: Base Total={doc.base_total}, Taxes={doc.base_total_taxes_and_charges}, Grand Total={doc.base_grand_total}, Rounded={doc.base_rounded_total}")


# def override_totals_on_update_after_submit(doc, method=None):
#     """Hook for updates after submission"""
#     override_totals_before_save(doc, method)
#     set_custom_rounding_adjustment(doc, method)


def override_totals_before_submit(doc, method=None):
    """
    CRITICAL HOOK: Final calculations before GL entries are created
    This ensures all totals are correct before General Ledger posting
    """
    if not doc.items:
        return
    
    frappe.logger().info(f"=== BEFORE SUBMIT: Starting final calculations for {doc.name} ===")
    
    # 1. Recalculate custom totals
    sum_custom_total = 0
    for item in doc.items:
        qty = flt(item.qty)
        amount = flt(item.amount)
        excise_duty = flt(item.custom_excise_duty)
        
        excise_value = flt(excise_duty * qty, 2)
        custom_total = flt(amount + excise_value, 2)
        
        item.custom_excise_value = excise_value
        item.custom_total = custom_total
        sum_custom_total += custom_total
    
    # CRITICAL: Update item-level net amounts
    update_item_net_amounts(doc)
    
    # 2. Override base_total and net_total
    doc.base_total = flt(sum_custom_total, 2)
    doc.total = flt(sum_custom_total / flt(doc.conversion_rate or 1), 2)
    doc.base_net_total = doc.base_total
    doc.net_total = doc.total
    
    frappe.logger().info(f"Base Total (with excise): {doc.base_total}")
    
    # 3. Recalculate ALL taxes based on custom total
    recalculate_taxes_on_custom_total(doc)
    
    # 4. Recalculate grand total
    base_taxes = flt(doc.base_total_taxes_and_charges)
    doc.base_grand_total = flt(doc.base_total + base_taxes, 2)
    doc.grand_total = flt(doc.base_grand_total / flt(doc.conversion_rate or 1), 2)
    
    frappe.logger().info(f"Base Taxes: {base_taxes}, Base Grand Total: {doc.base_grand_total}")
    
    # 5. Calculate rounding adjustment from custom_difference_calculation_table
    if doc.custom_difference_calculation_table:
        custom_total_amount = sum(flt(row.total_amount) for row in doc.custom_difference_calculation_table)
        custom_total_amount = flt(custom_total_amount, 2)
        
        doc.custom_total_amount = custom_total_amount
        difference = flt(custom_total_amount - doc.base_grand_total, 2)
        doc.custom_difference_adjustment = difference
        
        # Apply rounding adjustment
        doc.base_rounding_adjustment = difference
        doc.rounding_adjustment = flt(difference / flt(doc.conversion_rate or 1), 2)
        
        # Recalculate rounded totals
        rounded_total = flt(doc.base_grand_total + difference, 2)
        doc.rounded_total = flt(rounded_total / flt(doc.conversion_rate or 1), 2)
        doc.base_rounded_total = rounded_total
        
        frappe.logger().info(f"Custom Total Amount: {custom_total_amount}, Difference: {difference}, Rounded Total: {rounded_total}")
    else:
        # No custom rounding
        doc.base_rounding_adjustment = 0
        doc.rounding_adjustment = 0
        doc.rounded_total = doc.grand_total
        doc.base_rounded_total = doc.base_grand_total
    
    # 6. Calculate outstanding
    total_advance = flt(doc.total_advance)
    doc.outstanding_amount = flt(doc.base_rounded_total - total_advance, 2)
    
    # 7. Convert to words
    currency = doc.currency or frappe.defaults.get_default("currency")
    doc.base_in_words = money_in_words(doc.base_rounded_total, currency)
    doc.in_words = money_in_words(doc.rounded_total, currency)
    
    # 8. Update payment schedule
    if doc.payment_schedule and len(doc.payment_schedule) > 0:
        outstanding = flt(doc.outstanding_amount)
        conversion_rate = flt(doc.conversion_rate or 1)
        doc.payment_schedule[0].base_payment_amount = outstanding
        doc.payment_schedule[0].payment_amount = flt(outstanding / conversion_rate, 2)
    
    frappe.logger().info(f"=== BEFORE SUBMIT COMPLETE: Outstanding={doc.outstanding_amount}, GL Ready ===")


##latest
# import frappe
# from frappe import _
# from frappe.utils import flt, cint, money_in_words


# def set_custom_rounding_adjustment(doc, method=None):
#     """
#     Override base_rounding_adjustment with custom_difference_adjustment value
#     This function is called during validate/before_submit event of Sales Invoice
    
#     """
    
#     # Check if custom_difference_adjustment field exists and has a value
#     if hasattr(doc, 'custom_difference_adjustment') and doc.custom_difference_adjustment:
        
#         # Set base_rounding_adjustment from custom_difference_adjustment
#         doc.base_rounding_adjustment = flt(
#             doc.custom_difference_adjustment, 
#             doc.precision("base_rounding_adjustment")
#         )
        
#         # Recalculate base_grand_total with the custom adjustment
#         # Formula: Base Grand Total = Base Net Total + Base Total Taxes + Custom Adjustment
#         doc.base_grand_total = flt(
#             doc.base_net_total + doc.base_total_taxes_and_charges,
#             doc.precision("base_grand_total")
#         )
#         doc.custom_difference_adjustment = flt(doc.custom_total_amount - doc.base_grand_total, 2)

#         # Also set rounding_adjustment for company currency
#         doc.rounding_adjustment = flt(
#             doc.custom_difference_adjustment, 
#             doc.precision("rounding_adjustment")
#         )
        
#         # Calculate grand total in transaction currency
#         if doc.conversion_rate and doc.conversion_rate != 0:
#             doc.grand_total = flt(
#                 doc.base_grand_total / doc.conversion_rate,
#                 doc.precision("grand_total")
#             )
#         else:
#             doc.grand_total = doc.base_grand_total
        
#         # Update rounded totals
#         doc.base_rounded_total = flt(doc.base_grand_total + doc.base_rounding_adjustment)
#         doc.rounded_total = flt(doc.grand_total + doc.rounding_adjustment)
        
#         # Convert rounded total to words
#         doc.base_in_words = money_in_words(doc.base_rounded_total, doc.currency)
#         doc.in_words = money_in_words(doc.rounded_total, doc.currency)
        
#         doc.outstanding_amount = flt(
#             doc.base_rounded_total - doc.total_advance,
#             doc.precision("outstanding_amount")
#         )

#         # Update payment schedule with outstanding amount
#         update_payment_schedule(doc)
        
#         # Log for debugging (optional)
#         frappe.logger().debug(
#             f"Sales Invoice {doc.name}: Custom Difference Adjustment = {doc.custom_difference_adjustment}, "
#             f"Base Rounding Adjustment = {doc.base_rounding_adjustment}, "
#             f"Grand Total = {doc.grand_total}, "
#             f"Outstanding Amount = {doc.outstanding_amount}"
#         )
        
#     else:
#         # If custom_difference_adjustment is 0 or empty, clear rounding adjustment
#         # This ensures standard ERPNext rounding logic takes over
#         doc.base_rounding_adjustment = 0
#         doc.rounding_adjustment = 0


# def update_payment_schedule(doc):
#     """
#     Update payment_amount and base_payment_amount in Payment Schedule table
#     to match the outstanding_amount
#     """
#     if not hasattr(doc, 'payment_schedule') or not doc.payment_schedule:
#         return
    
#     outstanding = flt(doc.outstanding_amount, doc.precision("outstanding_amount"))
    
#     # If there's only one payment schedule row, set it to outstanding amount
#     if len(doc.payment_schedule) == 1:
#         doc.payment_schedule[0].payment_amount = flt(
#             outstanding / doc.conversion_rate if doc.conversion_rate else outstanding,
#             doc.precision("payment_amount", "payment_schedule")
#         )
#         doc.payment_schedule[0].base_payment_amount = flt(
#             outstanding,
#             doc.precision("base_payment_amount", "payment_schedule")
#         )
    
#     # If multiple payment schedules, distribute proportionally or update all
#     elif len(doc.payment_schedule) > 1:
#         # Option 1: Update first row only
#         doc.payment_schedule[0].payment_amount = flt(
#             outstanding / doc.conversion_rate if doc.conversion_rate else outstanding,
#             doc.precision("payment_amount", "payment_schedule")
#         )
#         doc.payment_schedule[0].base_payment_amount = flt(
#             outstanding,
#             doc.precision("base_payment_amount", "payment_schedule")
#         )
        
#         # Option 2: Distribute equally across all rows (uncomment if needed)
#         # per_row_amount = outstanding / len(doc.payment_schedule)
#         # for row in doc.payment_schedule:
#         #     row.payment_amount = flt(
#         #         per_row_amount / doc.conversion_rate if doc.conversion_rate else per_row_amount,
#         #         doc.precision("payment_amount", "payment_schedule")
#         #     )
#         #     row.base_payment_amount = flt(
#         #         per_row_amount,
#         #         doc.precision("base_payment_amount", "payment_schedule")
#         #     )
    
#     frappe.logger().debug(
#         f"Payment Schedule updated for {doc.name}: Outstanding = {outstanding}"
#     )


# @frappe.whitelist()
# def convert_amount_to_words(amount, currency):
   
#     try:
#         amount = flt(amount)
#         amount_in_words = money_in_words(amount, currency)
#         return amount_in_words
#     except Exception as e:
#         frappe.log_error(
#             message=frappe.get_traceback(),
#             title=f"Error converting amount to words: {amount}"
#         )
#         return ""


# ###ITEM Price 

# import frappe
# from frappe import _
# from frappe.utils import flt, money_in_words

# @frappe.whitelist()
# def get_custom_amount(customer, price_list, item_code, qty, uom):
#     """Fetch custom_total_vat_inclusive from Item Price"""
#     try:
#         # Get Item Price
#         filters = {
#             'item_code': item_code,
#             'price_list': price_list,
#             'uom': uom
#         }
        
#         item_price = frappe.get_all(
#             'Item Price',
#             filters=filters,
#             fields=['custom_total_vat_inclusive', 'price_list_rate'],
#             limit=1
#         )
        
#         if item_price and len(item_price) > 0:
#             price = flt(item_price[0].get('custom_total_vat_inclusive', 0))
#             if price == 0:
#                 price = flt(item_price[0].get('price_list_rate', 0))
#             return {'price': price}
        
#         return {'price': 0}
        
#     except Exception as e:
#         frappe.log_error(f"Error in get_custom_amount: {str(e)}")
#         return {'price': 0}


# @frappe.whitelist()
# def convert_amount_to_words(amount, currency):
#     """Convert amount to words"""
#     try:
#         amount = flt(amount)
#         words = money_in_words(amount, currency)
#         return words
#     except Exception as e:
#         frappe.log_error(f"Error converting to words: {str(e)}")
#         return ""


# def override_totals_before_validate(doc, method=None):
#     """
#     FIRST HOOK: Calculate excise duty values
#     This runs before ERPNext's validation
#     """
#     if not doc.items:
#         return
    
#     # Calculate excise duty for each item
#     for item in doc.items:
#         qty = flt(item.qty)
#         amount = flt(item.amount)
#         excise_duty = flt(item.custom_excise_duty)
        
#         # Calculate excise value and custom total
#         excise_value = flt(excise_duty * qty, 2)
#         custom_total = flt(amount + excise_value, 2)
        
#         # Set values
#         item.custom_excise_value = excise_value
#         item.custom_total = custom_total
    
#     # Calculate sum of custom_total
#     sum_custom_total = sum(flt(item.custom_total) for item in doc.items)
    
#     # Override base_total and total
#     doc.base_total = flt(sum_custom_total, 2)
#     doc.total = flt(sum_custom_total / flt(doc.conversion_rate or 1), 2)
    
#     frappe.logger().info(f"Before Validate - Sum of custom_total: {sum_custom_total}")


# def override_totals_validate(doc, method=None):
#     """
#     SECOND HOOK: Re-override after ERPNext validation
#     This ensures our values persist after ERPNext recalculates
#     """
#     if not doc.items:
#         return
    
#     # Recalculate sum of custom_total (in case ERPNext changed amounts)
#     sum_custom_total = 0
#     for item in doc.items:
#         qty = flt(item.qty)
#         amount = flt(item.amount)
#         excise_duty = flt(item.custom_excise_duty)
        
#         excise_value = flt(excise_duty * qty, 2)
#         custom_total = flt(amount + excise_value, 2)
        
#         item.custom_excise_value = excise_value
#         item.custom_total = custom_total
#         sum_custom_total += custom_total
    
#     # Override base_total and total again
#     doc.base_total = flt(sum_custom_total, 2)
#     doc.total = flt(sum_custom_total / flt(doc.conversion_rate or 1), 2)
    
#     # Calculate base_grand_total (base_total + base_total_taxes_and_charges)
    
    
#     old_base_total = doc.base_total
#     doc.base_total = flt(sum_custom_total, 2)
#     doc.total = flt(sum_custom_total / flt(doc.conversion_rate or 1), 2)
#     frappe.logger().info(f"Base total changed from {old_base_total} to {doc.base_total}")

#     # recalculate_taxes(doc)

#     base_taxes = flt(doc.base_total_taxes_and_charges)
#     doc.base_grand_total = flt(doc.base_total + base_taxes, 2)
#     doc.grand_total = flt(doc.base_grand_total / flt(doc.conversion_rate or 1), 2)
    
#     frappe.logger().info(f"Validate - Base Total: {doc.base_total}, Base Grand Total: {doc.base_grand_total}")


# def override_totals_before_save(doc, method=None):
#     """
#     THIRD HOOK: Final override before saving
#     Calculate rounding adjustment from custom_difference_calculation_table
#     """
#     if not doc.items:
#         return
    
#     # Recalculate custom totals one more time
#     sum_custom_total = sum(flt(item.custom_total) for item in doc.items)
#     doc.base_total = flt(sum_custom_total, 2)
#     doc.total = flt(sum_custom_total / flt(doc.conversion_rate or 1), 2)
    

#      # Final recalculation of custom totals
#     sum_custom_total = sum(flt(item.custom_total) for item in doc.items)
#     doc.base_total = flt(sum_custom_total, 2)
#     doc.total = flt(sum_custom_total / flt(doc.conversion_rate or 1), 2)

    
#     # Recalculate grand total
#     base_taxes = flt(doc.base_total_taxes_and_charges)
#     doc.base_grand_total = flt(doc.base_total + base_taxes, 2)
#     doc.grand_total = flt(doc.base_grand_total / flt(doc.conversion_rate or 1), 2)
    
#     # Calculate rounding adjustment from custom_difference_calculation_table
#     if doc.custom_difference_calculation_table:
#         custom_total_amount = sum(flt(row.total_amount) for row in doc.custom_difference_calculation_table)
#         custom_total_amount = flt(custom_total_amount, 2)
        
#         # Set custom_total_amount
#         doc.custom_total_amount = custom_total_amount
        
#         # Calculate difference
#         difference = flt(custom_total_amount - doc.base_grand_total, 2)
#         doc.custom_difference_adjustment = difference
        
#         # Calculate rounded total
#         rounded_total = flt(doc.base_grand_total + difference, 2)
#         doc.rounded_total = rounded_total
#         doc.base_rounded_total = rounded_total
        
#         # Calculate outstanding
#         total_advance = flt(doc.total_advance)
#         doc.outstanding_amount = flt(rounded_total - total_advance, 2)
        
#         # Convert to words
#         currency = doc.currency or frappe.defaults.get_default("currency")
#         doc.base_in_words = money_in_words(rounded_total, currency)
#         doc.in_words = money_in_words(flt(rounded_total / flt(doc.conversion_rate or 1), 2), currency)
        
#         frappe.logger().info(f"Rounding - Custom Total: {custom_total_amount}, Difference: {difference}, Rounded Total: {rounded_total}")
    
#     # Update payment schedule
#     if doc.payment_schedule and len(doc.payment_schedule) > 0:
#         outstanding = flt(doc.outstanding_amount)
#         conversion_rate = flt(doc.conversion_rate or 1)
        
#         # Update first payment schedule row
#         doc.payment_schedule[0].base_payment_amount = outstanding
#         doc.payment_schedule[0].payment_amount = flt(outstanding / conversion_rate, 2)


# def override_totals_on_update_after_submit(doc, method=None):
#     """Hook for updates after submission"""
#     override_totals_before_save(doc, method)
#     set_custom_rounding_adjustment(doc, method)


# def set_custom_rounding_adjustment(doc, method=None):
#     """
#     LEGACY FUNCTION: Calculate rounding adjustment
#     Kept for backwards compatibility
#     """
#     if not doc.custom_difference_calculation_table:
#         return
    
#     # Calculate custom_total_amount from calculation table
#     custom_total_amount = sum(flt(row.total_amount) for row in doc.custom_difference_calculation_table)
#     custom_total_amount = flt(custom_total_amount, 2)
    
#     # Set custom_total_amount
#     doc.custom_total_amount = custom_total_amount
    
#     # Calculate difference
#     base_grand_total = flt(doc.base_grand_total)
#     difference = flt(custom_total_amount - base_grand_total, 2)
#     doc.custom_difference_adjustment = difference
    
#     # Calculate rounded total
#     rounded_total = flt(base_grand_total + difference, 2)
#     doc.rounded_total = rounded_total
#     doc.base_rounded_total = rounded_total
    
#     # Calculate outstanding
#     total_advance = flt(doc.total_advance)
#     doc.outstanding_amount = flt(rounded_total - total_advance, 2)
    
#     # Convert to words
#     currency = doc.currency or frappe.defaults.get_default("currency")
#     doc.base_in_words = money_in_words(rounded_total, currency)
#     doc.in_words = money_in_words(flt(rounded_total / flt(doc.conversion_rate or 1), 2), currency)
    
#     # Update payment schedule
#     if doc.payment_schedule and len(doc.payment_schedule) > 0:
#         outstanding = flt(doc.outstanding_amount)
#         conversion_rate = flt(doc.conversion_rate or 1)
#         doc.payment_schedule[0].base_payment_amount = outstanding
#         doc.payment_schedule[0].payment_amount = flt(outstanding / conversion_rate, 2)



###old
# @frappe.whitelist()
# def get_custom_amount(customer, price_list, item_code, qty, uom=''):
#     """
#     Fetch custom_total_vat_inclusive from Item Price based on:
#     - item_code
#     - price_list (selling_price_list from Sales Invoice)
#     - uom
    
#     Args:
#         customer: Customer name (optional, for future use)
#         price_list: Price List name (e.g., "Standard Selling", "Bulk")
#         item_code: Item Code
#         qty: Quantity (for future tiered pricing)
#         uom: Unit of Measurement
        
#     Returns:
#         dict: {"price": custom_total_vat_inclusive value}
#     """
    
#     try:
#         # Build filters for Item Price
#         filters = {
#             "item_code": item_code,
#             "price_list": price_list,
#             "selling": 1  # For sales transactions
            
#         }
        
#         # Add UOM filter if provided
#         if uom:
#             filters["uom"] = uom
        
#         # Optional: Add customer-specific pricing (higher priority)
#         if customer:
#             customer_filters = filters.copy()
#             customer_filters["customer"] = customer
            
#             # Try to get customer-specific price first
#             item_price = frappe.db.get_value(
#                 "Item Price",
#                 filters=customer_filters,
#                 fieldname=["custom_total_vat_inclusive", "price_list_rate", "name"],
#                 as_dict=True
#             )
            
#             if item_price and item_price.custom_total_vat_inclusive:
#                 return {
#                     "price": flt(item_price.custom_total_vat_inclusive),
#                     "price_list_rate": flt(item_price.price_list_rate),
#                     "item_price_name": item_price.name
#                 }
        
#         # If no customer-specific price, get general price
#         item_price = frappe.db.get_value(
#             "Item Price",
#             filters=filters,
#             fieldname=["custom_total_vat_inclusive", "price_list_rate", "name"],
#             as_dict=True,
#             order_by="valid_from DESC"  # Get latest price if multiple exist
#         )
        
#         if item_price:
#             # Return custom_total_vat_inclusive if available
#             if item_price.custom_total_vat_inclusive:
#                 return {
#                     "price": flt(item_price.custom_total_vat_inclusive),
#                     "price_list_rate": flt(item_price.price_list_rate),
#                     "item_price_name": item_price.name
#                 }
#             else:
#                 # Fallback to price_list_rate if custom field is empty
#                 frappe.msgprint(
#                     _("Custom Total VAT Inclusive not found for Item {0} in Price List {1}. Using Price List Rate.").format(
#                         item_code, price_list
#                     ),
#                     indicator="orange",
#                     alert=True
#                 )
#                 return {
#                     "price": flt(item_price.price_list_rate),
#                     "price_list_rate": flt(item_price.price_list_rate),
#                     "item_price_name": item_price.name
#                 }
#         else:
#             # No Item Price found
#             frappe.msgprint(
#                 _("No Item Price found for Item {0} in Price List {1}").format(
#                     item_code, price_list
#                 ),
#                 indicator="red",
#                 alert=True
#             )
#             return {"price": 0, "price_list_rate": 0, "item_price_name": None}
            
#     except Exception as e:
#         frappe.log_error(
#             message=frappe.get_traceback(),
#             title=f"Error fetching custom amount for {item_code}"
#         )
#         frappe.throw(_("Error fetching price: {0}").format(str(e)))
#         return {"price": 0, "price_list_rate": 0, "item_price_name": None}


# @frappe.whitelist()
# def get_custom_amount_bulk(items, price_list):
#     """
#     Fetch prices for multiple items at once (performance optimization)
    
#     Args:
#         items: List of dicts with item_code, uom, qty
#         price_list: Price List name
        
#     Returns:
#         dict: {item_code: price_data}
#     """
    
#     try:
#         import json
#         if isinstance(items, str):
#             items = json.loads(items)
        
#         result = {}
        
#         for item in items:
#             item_code = item.get("item_code")
#             uom = item.get("uom")
#             qty = item.get("qty", 1)
            
#             if item_code:
#                 price_data = get_custom_amount(
#                     customer=None,
#                     price_list=price_list,
#                     item_code=item_code,
#                     qty=qty,
#                     uom=uom
#                 )
#                 result[item_code] = price_data
        
#         return result
        
#     except Exception as e:
#         frappe.log_error(
#             message=frappe.get_traceback(),
#             title="Error in bulk price fetch"
#         )
#         return {}
    




# # Add this to your override_rounding.py file
# # Path: avinashgroup_app/avinashgroup_app/custom_code/override_rounding.py

# # import frappe
# # from frappe import _
# # from frappe.utils import flt

# # def override_totals_before_save(doc, method=None):
# #     """Override totals with sum of custom_total - runs before save"""
# #     calculate_custom_totals(doc)

# # def override_totals_validate(doc, method=None):
# #     """Override totals during validation"""
# #     calculate_custom_totals(doc)

# # def override_totals_on_update_after_submit(doc, method=None):
# #     """Override totals after submit for amendments"""
# #     calculate_custom_totals(doc)

# # def calculate_custom_totals(doc):
# #     """
# #     Calculate base_total and total from custom_total field
# #     Then recalculate grand_total based on the new base_total
# #     """
# #     # Step 1: Calculate base_total from custom_total
# #     base_total = 0.0
    
# #     for item in doc.items:
# #         custom_total = flt(item.custom_total or 0)
# #         base_total += custom_total
    
# #     # Round to document precision
# #     base_total = flt(base_total, doc.precision("base_total"))
# #     total = flt(base_total / doc.conversion_rate, doc.precision("total"))
    
# #     # Set the totals
# #     doc.base_total = base_total
# #     doc.total = total
# #     doc.base_net_total = base_total
# #     doc.net_total = total
    
# #     frappe.logger().info(f"Custom totals calculated - base_total: {base_total}, total: {total}")
    
# #     # Step 2: Recalculate grand_total from the new base_total
# #     calculate_grand_total_from_custom_base(doc)

# # def calculate_grand_total_from_custom_base(doc):
# #     """
# #     Recalculate grand_total based on custom base_total
# #     Formula: grand_total = base_total + taxes - discounts
# #     """
# #     # Get taxes total
# #     base_tax_total = flt(doc.base_total_taxes_and_charges or 0)
    
# #     # Get discount
# #     base_discount = flt(doc.base_discount_amount or 0)
    
# #     # Calculate base_grand_total
# #     base_grand_total = doc.base_total + base_tax_total - base_discount
# #     base_grand_total = flt(base_grand_total, doc.precision("base_grand_total"))
    
# #     # Calculate grand_total in foreign currency
# #     grand_total = flt(base_grand_total / doc.conversion_rate, doc.precision("grand_total"))
    
# #     # Set grand totals
# #     doc.base_grand_total = base_grand_total
# #     doc.grand_total = grand_total
    
# #     # Calculate rounded totals
# #     rounding_adjustment = flt(doc.rounding_adjustment or 0)
# #     base_rounding_adjustment = flt(doc.base_rounding_adjustment or 0)
    
# #     doc.rounded_total = flt(grand_total + rounding_adjustment, doc.precision("rounded_total"))
# #     doc.base_rounded_total = flt(base_grand_total + base_rounding_adjustment, doc.precision("base_rounded_total"))
    
# #     # Calculate outstanding amount
# #     total_advance = flt(doc.total_advance or 0)
# #     doc.outstanding_amount = flt(doc.rounded_total - total_advance, doc.precision("outstanding_amount"))
    
# #     frappe.logger().info(f"Grand totals recalculated - base_grand_total: {base_grand_total}, grand_total: {grand_total}, outstanding: {doc.outstanding_amount}")


# # # CRITICAL: Monkey patch ERPNext's calculate_totals method
# # def patch_sales_invoice_calculations():
# #     """
# #     Monkey patch the Sales Invoice to use custom_total instead of amount
# #     This ensures ERPNext ALWAYS calculates totals from custom_total
# #     """
# #     try:
# #         from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
        
# #         # Store original calculate_totals method
# #         original_calculate_totals = SalesInvoice.calculate_totals
        
# #         def custom_calculate_totals(self):
# #             """Override to calculate from custom_total first, then call original"""
            
# #             # Calculate base_total and total from custom_total
# #             self.base_net_total = 0.0
            
# #             for item in self.items:
# #                 # Use custom_total if available, otherwise use amount
# #                 if hasattr(item, 'custom_total') and item.custom_total:
# #                     self.base_net_total += flt(item.custom_total)
# #                 else:
# #                     self.base_net_total += flt(item.base_amount or item.amount or 0)
            
# #             # Calculate net_total in foreign currency
# #             self.net_total = flt(self.base_net_total / self.conversion_rate, self.precision("net_total"))
            
# #             # Set base_total and total (these are usually same as net totals before discounts)
# #             self.base_total = self.base_net_total
# #             self.total = self.net_total
            
# #             frappe.logger().debug(f"Custom totals calculated: base_total={self.base_total}, total={self.total}")
            
# #             # Now call the original method to calculate taxes and grand total
# #             # But our base_total is already set correctly
# #             original_calculate_totals(self)
        
# #         # Replace the method
# #         SalesInvoice.calculate_totals = custom_calculate_totals
        
# #         frappe.logger().info("✓ Sales Invoice calculate_totals method patched to use custom_total")
# #         return True
        
# #     except Exception as e:
# #         frappe.logger().error(f"✗ Error patching Sales Invoice: {str(e)}")
# #         import traceback
# #         frappe.logger().error(traceback.format_exc())
# #         return False


# # # For debugging - call this from bench console to verify calculations
# # def debug_sales_invoice_totals(invoice_name):
# #     """Debug helper to check total calculations"""
# #     doc = frappe.get_doc("Sales Invoice", invoice_name)
    
# #     print("\n=== ITEM TOTALS ===")
# #     for item in doc.items:
# #         print(f"{item.item_code}: amount={item.amount}, custom_total={item.custom_total}")
    
# #     print("\n=== CALCULATED TOTALS ===")
# #     calculate_custom_totals(doc)
    
# #     print(f"base_total: {doc.base_total}")
# #     print(f"total: {doc.total}")
# #     print(f"base_grand_total: {doc.base_grand_total}")
# #     print(f"grand_total: {doc.grand_total}")
# #     print(f"outstanding_amount: {doc.outstanding_amount}")


# # Add this to your override_rounding.py file
# # Path: avinashgroup_app/avinashgroup_app/custom_code/override_rounding.py

# # import frappe
# # from frappe import _
# # from frappe.utils import flt

# # def override_totals_before_save(doc, method=None):
# #     """Override totals with sum of custom_total - runs before save"""
# #     calculate_custom_totals(doc)

# # def override_totals_validate(doc, method=None):
# #     """Override totals during validation - THIS IS THE KEY ONE"""
# #     calculate_custom_totals(doc)

# # def override_totals_on_update_after_submit(doc, method=None):
# #     """Override totals after submit for amendments"""
# #     calculate_custom_totals(doc)

# # def calculate_custom_totals(doc):
# #     """
# #     Calculate base_total and total from custom_total field
# #     Then recalculate grand_total based on the new base_total
# #     """
# #     # Step 1: Calculate base_total from custom_total
# #     base_total = 0.0
    
# #     for item in doc.items:
# #         custom_total = flt(item.custom_total or 0)
# #         base_total += custom_total
    
# #     # Round to document precision
# #     base_total = flt(base_total, doc.precision("base_total"))
# #     total = flt(base_total / doc.conversion_rate, doc.precision("total"))
    
# #     # Set the totals
# #     doc.base_total = base_total
# #     doc.total = total
# #     doc.base_net_total = base_total
# #     doc.net_total = total
    
# #     frappe.logger().info(f"Custom totals calculated - base_total: {base_total}, total: {total}")
    
# #     # Step 2: Recalculate grand_total from the new base_total
# #     calculate_grand_total_from_custom_base(doc)

# # def calculate_grand_total_from_custom_base(doc):
# #     """
# #     Recalculate grand_total based on custom base_total
# #     Formula: grand_total = base_total + taxes - discounts
# #     """
# #     # Get taxes total
# #     base_tax_total = flt(doc.base_total_taxes_and_charges or 0)
    
# #     # Get discount
# #     base_discount = flt(doc.base_discount_amount or 0)
    
# #     # Calculate base_grand_total
# #     base_grand_total = doc.base_total + base_tax_total - base_discount
# #     base_grand_total = flt(base_grand_total, doc.precision("base_grand_total"))
    
# #     # Calculate grand_total in foreign currency
# #     grand_total = flt(base_grand_total / doc.conversion_rate, doc.precision("grand_total"))
    
# #     # Set grand totals
# #     doc.base_grand_total = base_grand_total
# #     doc.grand_total = grand_total
    
# #     # Calculate rounded totals
# #     rounding_adjustment = flt(doc.rounding_adjustment or 0)
# #     base_rounding_adjustment = flt(doc.base_rounding_adjustment or 0)
    
# #     doc.rounded_total = flt(grand_total + rounding_adjustment, doc.precision("rounded_total"))
# #     doc.base_rounded_total = flt(base_grand_total + base_rounding_adjustment, doc.precision("base_rounded_total"))
    
# #     # Calculate outstanding amount
# #     total_advance = flt(doc.total_advance or 0)
# #     doc.outstanding_amount = flt(doc.rounded_total - total_advance, doc.precision("outstanding_amount"))
    
# #     frappe.logger().info(f"Grand totals recalculated - base_grand_total: {base_grand_total}, grand_total: {grand_total}, outstanding: {doc.outstanding_amount}")


# # # CRITICAL: Monkey patch ERPNext's calculate_totals method
# # def patch_sales_invoice_calculations():
# #     """
# #     Monkey patch the Sales Invoice to use custom_total instead of amount
# #     This ensures ERPNext ALWAYS calculates totals from custom_total
# #     """
# #     try:
# #         from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
        
# #         # Check if calculate_totals exists
# #         if not hasattr(SalesInvoice, 'calculate_totals'):
# #             frappe.logger().warning("SalesInvoice.calculate_totals not found, trying calculate_taxes_and_totals")
            
# #             # Try calculate_taxes_and_totals instead
# #             if hasattr(SalesInvoice, 'calculate_taxes_and_totals'):
# #                 original_method = SalesInvoice.calculate_taxes_and_totals
                
# #                 def custom_calculate_taxes_and_totals(self):
# #                     """Override to set totals from custom_total first"""
# #                     # Calculate from custom_total
# #                     calculate_custom_totals(self)
# #                     # Then call original for taxes
# #                     original_method(self)
# #                     # Re-apply custom totals (in case original overwrote them)
# #                     calculate_custom_totals(self)
                
# #                 SalesInvoice.calculate_taxes_and_totals = custom_calculate_taxes_and_totals
# #                 frappe.logger().info("✓ Patched calculate_taxes_and_totals")
# #                 return True
# #             else:
# #                 frappe.logger().error("No calculation method found to patch!")
# #                 return False
        
# #         # Store original calculate_totals method
# #         original_calculate_totals = SalesInvoice.calculate_totals
        
# #         def custom_calculate_totals(self):
# #             """Override to calculate from custom_total first, then call original"""
            
# #             # Calculate base_total and total from custom_total
# #             self.base_net_total = 0.0
            
# #             for item in self.items:
# #                 # Use custom_total if available, otherwise use amount
# #                 if hasattr(item, 'custom_total') and item.custom_total:
# #                     self.base_net_total += flt(item.custom_total)
# #                 else:
# #                     self.base_net_total += flt(item.base_amount or item.amount or 0)
            
# #             # Calculate net_total in foreign currency
# #             self.net_total = flt(self.base_net_total / self.conversion_rate, self.precision("net_total"))
            
# #             # Set base_total and total (these are usually same as net totals before discounts)
# #             self.base_total = self.base_net_total
# #             self.total = self.net_total
            
# #             frappe.logger().debug(f"Custom totals calculated: base_total={self.base_total}, total={self.total}")
            
# #             # Now call the original method to calculate taxes and grand total
# #             # But our base_total is already set correctly
# #             original_calculate_totals(self)
        
# #         # Replace the method
# #         SalesInvoice.calculate_totals = custom_calculate_totals
        
# #         frappe.logger().info("✓ Sales Invoice calculate_totals method patched to use custom_total")
# #         return True
        
# #     except Exception as e:
# #         frappe.logger().error(f"✗ Error patching Sales Invoice: {str(e)}")
# #         import traceback
# #         frappe.logger().error(traceback.format_exc())
# #         return False


# # # For debugging - call this from bench console to verify calculations
# # def debug_sales_invoice_totals(invoice_name):
# #     """Debug helper to check total calculations"""
# #     doc = frappe.get_doc("Sales Invoice", invoice_name)
    
# #     print("\n=== ITEM TOTALS ===")
# #     for item in doc.items:
# #         print(f"{item.item_code}: amount={item.amount}, custom_total={item.custom_total}")
    
# #     print("\n=== CALCULATED TOTALS ===")
# #     calculate_custom_totals(doc)
    
# #     print(f"base_total: {doc.base_total}")
# #     print(f"total: {doc.total}")
# #     print(f"base_grand_total: {doc.base_grand_total}")
# #     print(f"grand_total: {doc.grand_total}")
# #     print(f"outstanding_amount: {doc.outstanding_amount}")



# import frappe
# from frappe import _
# from frappe.utils import flt, cint, money_in_words


# # CRITICAL: Flag to prevent ERPNext from recalculating after we set values
# CUSTOM_CALCULATION_FLAG = "_custom_totals_applied"


# def override_totals_before_validate(doc, method=None):
#     """First pass - before ERPNext validation"""
#     calculate_custom_totals(doc)
#     setattr(doc, CUSTOM_CALCULATION_FLAG, True)


# def override_totals_validate(doc, method=None):
#     """Second pass - during validation"""
#     calculate_custom_totals(doc)
#     setattr(doc, CUSTOM_CALCULATION_FLAG, True)


# def override_totals_before_save(doc, method=None):
#     """Third pass - before save (most important)"""
#     calculate_custom_totals(doc)
#     setattr(doc, CUSTOM_CALCULATION_FLAG, True)


# def override_totals_final(doc, method=None):
#     """Final pass - catches any last-minute overwrites"""
#     calculate_custom_totals(doc)
#     setattr(doc, CUSTOM_CALCULATION_FLAG, True)


# def override_totals_on_update_after_submit(doc, method=None):
#     """For amendments"""
#     calculate_custom_totals(doc)
#     setattr(doc, CUSTOM_CALCULATION_FLAG, True)


# def calculate_custom_totals(doc):
#     """
#     Calculate base_total and total from custom_total field
#     Sets a flag to prevent ERPNext from recalculating
#     """
#     if not doc.items:
#         return
    
#     # Step 1: Calculate base_total from custom_total
#     base_total = 0.0
#     base_net_total = 0.0
    
#     for item in doc.items:
#         custom_total = flt(item.custom_total or 0)
#         base_total += custom_total
#         base_net_total += custom_total
    
#     # Round to document precision
#     base_total = flt(base_total, doc.precision("base_total"))
#     base_net_total = flt(base_net_total, doc.precision("base_net_total"))
#     total = flt(base_total / (doc.conversion_rate or 1), doc.precision("total"))
#     net_total = flt(base_net_total / (doc.conversion_rate or 1), doc.precision("net_total"))
    
#     # CRITICAL: Set totals AND net totals
#     doc.base_total = base_total
#     doc.total = total
#     doc.base_net_total = base_net_total
#     doc.net_total = net_total
    
#     frappe.logger().info(f"Custom totals set - base_total: {base_total}, total: {total}")
    
#     # Step 2: Recalculate grand_total from the new base_total
#     calculate_grand_total_from_custom_base(doc)
    
#     # Step 3: Set the flag to indicate custom calculation is done
#     doc.flags.ignore_validate_update_after_submit = False
#     doc.flags.custom_totals_set = True


# def calculate_grand_total_from_custom_base(doc):
#     """
#     Recalculate grand_total based on custom base_total
#     Formula: grand_total = base_total + taxes - discounts
#     """
#     # Get taxes total
#     base_tax_total = flt(doc.base_total_taxes_and_charges or 0)
    
#     # Get discount
#     base_discount = flt(doc.base_discount_amount or 0)
    
#     # Calculate base_grand_total
#     base_grand_total = doc.base_total + base_tax_total - base_discount
#     base_grand_total = flt(base_grand_total, doc.precision("base_grand_total"))
    
#     # Calculate grand_total in foreign currency
#     grand_total = flt(base_grand_total / (doc.conversion_rate or 1), doc.precision("grand_total"))
    
#     # Set grand totals
#     doc.base_grand_total = base_grand_total
#     doc.grand_total = grand_total
    
#     # Handle custom difference adjustment if present
#     if hasattr(doc, 'custom_difference_adjustment') and doc.custom_difference_adjustment:
#         doc.base_rounding_adjustment = flt(doc.custom_difference_adjustment, doc.precision("base_rounding_adjustment"))
#         doc.rounding_adjustment = flt(doc.custom_difference_adjustment / (doc.conversion_rate or 1), doc.precision("rounding_adjustment"))
#     else:
#         rounding_adjustment = flt(doc.rounding_adjustment or 0)
#         base_rounding_adjustment = flt(doc.base_rounding_adjustment or 0)
    
#     # Calculate rounded totals
#     doc.rounded_total = flt(doc.grand_total + doc.rounding_adjustment, doc.precision("rounded_total"))
#     doc.base_rounded_total = flt(doc.base_grand_total + doc.base_rounding_adjustment, doc.precision("base_rounded_total"))
    
#     # Calculate outstanding amount
#     total_advance = flt(doc.total_advance or 0)
#     doc.outstanding_amount = flt(doc.base_rounded_total - total_advance, doc.precision("outstanding_amount"))
    
#     # Update payment schedule
#     update_payment_schedule(doc)
    
#     # Convert to words
#     doc.base_in_words = money_in_words(doc.base_rounded_total, doc.currency)
#     doc.in_words = money_in_words(doc.rounded_total, doc.currency)
    
#     frappe.logger().info(f"Grand totals set - base_grand_total: {base_grand_total}, outstanding: {doc.outstanding_amount}")


# def set_custom_rounding_adjustment(doc, method=None):
#     """
#     Override base_rounding_adjustment with custom_difference_adjustment value
#     This function is called during validate/before_submit event of Sales Invoice
#     """
    
#     # Check if custom_difference_adjustment field exists and has a value
#     if hasattr(doc, 'custom_difference_adjustment') and doc.custom_difference_adjustment:
        
#         # Set base_rounding_adjustment from custom_difference_adjustment
#         doc.base_rounding_adjustment = flt(
#             doc.custom_difference_adjustment, 
#             doc.precision("base_rounding_adjustment")
#         )
        
#         # Recalculate base_grand_total with the custom adjustment
#         doc.base_grand_total = flt(
#             doc.base_net_total + doc.base_total_taxes_and_charges,
#             doc.precision("base_grand_total")
#         )
#         doc.custom_difference_adjustment = flt(doc.custom_total_amount - doc.base_grand_total, 2)

#         # Also set rounding_adjustment for company currency
#         doc.rounding_adjustment = flt(
#             doc.custom_difference_adjustment, 
#             doc.precision("rounding_adjustment")
#         )
        
#         # Calculate grand total in transaction currency
#         if doc.conversion_rate and doc.conversion_rate != 0:
#             doc.grand_total = flt(
#                 doc.base_grand_total / doc.conversion_rate,
#                 doc.precision("grand_total")
#             )
#         else:
#             doc.grand_total = doc.base_grand_total
        
#         # Update rounded totals
#         doc.base_rounded_total = flt(doc.base_grand_total + doc.base_rounding_adjustment)
#         doc.rounded_total = flt(doc.grand_total + doc.rounding_adjustment)
        
#         # Convert rounded total to words
#         doc.base_in_words = money_in_words(doc.base_rounded_total, doc.currency)
#         doc.in_words = money_in_words(doc.rounded_total, doc.currency)
        
#         doc.outstanding_amount = flt(
#             doc.base_rounded_total - doc.total_advance,
#             doc.precision("outstanding_amount")
#         )

#         # Update payment schedule with outstanding amount
#         update_payment_schedule(doc)
        
#         frappe.logger().debug(
#             f"Sales Invoice {doc.name}: Custom Difference Adjustment = {doc.custom_difference_adjustment}, "
#             f"Base Rounding Adjustment = {doc.base_rounding_adjustment}, "
#             f"Grand Total = {doc.grand_total}, "
#             f"Outstanding Amount = {doc.outstanding_amount}"
#         )
#     else:
#         doc.base_rounding_adjustment = 0
#         doc.rounding_adjustment = 0


# def update_payment_schedule(doc):
#     """Update payment_amount and base_payment_amount in Payment Schedule table"""
#     if not hasattr(doc, 'payment_schedule') or not doc.payment_schedule:
#         return
    
#     outstanding = flt(doc.outstanding_amount, doc.precision("outstanding_amount"))
    
#     if len(doc.payment_schedule) >= 1:
#         doc.payment_schedule[0].payment_amount = flt(
#             outstanding / (doc.conversion_rate or 1),
#             doc.precision("payment_amount", "payment_schedule")
#         )
#         doc.payment_schedule[0].base_payment_amount = flt(
#             outstanding,
#             doc.precision("base_payment_amount", "payment_schedule")
#         )
    
#     frappe.logger().debug(f"Payment Schedule updated: Outstanding = {outstanding}")


# @frappe.whitelist()
# def convert_amount_to_words(amount, currency):
#     try:
#         amount = flt(amount)
#         amount_in_words = money_in_words(amount, currency)
#         return amount_in_words
#     except Exception as e:
#         frappe.log_error(
#             message=frappe.get_traceback(),
#             title=f"Error converting amount to words: {amount}"
#         )
#         return ""


# @frappe.whitelist()
# def get_custom_amount(customer, price_list, item_code, qty, uom=''):
#     """Fetch custom_total_vat_inclusive from Item Price"""
#     try:
#         filters = {
#             "item_code": item_code,
#             "price_list": price_list,
#             "selling": 1
#         }
        
#         if uom:
#             filters["uom"] = uom
        
#         if customer:
#             customer_filters = filters.copy()
#             customer_filters["customer"] = customer
            
#             item_price = frappe.db.get_value(
#                 "Item Price",
#                 filters=customer_filters,
#                 fieldname=["custom_total_vat_inclusive", "price_list_rate", "name"],
#                 as_dict=True
#             )
            
#             if item_price and item_price.custom_total_vat_inclusive:
#                 return {
#                     "price": flt(item_price.custom_total_vat_inclusive),
#                     "price_list_rate": flt(item_price.price_list_rate),
#                     "item_price_name": item_price.name
#                 }
        
#         item_price = frappe.db.get_value(
#             "Item Price",
#             filters=filters,
#             fieldname=["custom_total_vat_inclusive", "price_list_rate", "name"],
#             as_dict=True,
#             order_by="valid_from DESC"
#         )
        
#         if item_price:
#             if item_price.custom_total_vat_inclusive:
#                 return {
#                     "price": flt(item_price.custom_total_vat_inclusive),
#                     "price_list_rate": flt(item_price.price_list_rate),
#                     "item_price_name": item_price.name
#                 }
#             else:
#                 return {
#                     "price": flt(item_price.price_list_rate),
#                     "price_list_rate": flt(item_price.price_list_rate),
#                     "item_price_name": item_price.name
#                 }
#         else:
#             return {"price": 0, "price_list_rate": 0, "item_price_name": None}
            
#     except Exception as e:
#         frappe.log_error(
#             message=frappe.get_traceback(),
#             title=f"Error fetching custom amount for {item_code}"
#         )
#         return {"price": 0, "price_list_rate": 0, "item_price_name": None}


# # CRITICAL: Monkey patch to prevent ERPNext from recalculating
# def patch_sales_invoice_calculations():
#     """
#     Monkey patch Sales Invoice to respect custom_total calculations
#     """
#     try:
#         from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
        
#         # Patch calculate_taxes_and_totals
#         if hasattr(SalesInvoice, 'calculate_taxes_and_totals'):
#             original_calc = SalesInvoice.calculate_taxes_and_totals
            
#             def custom_calculate_taxes_and_totals(self):
#                 # Check if custom totals were already set
#                 if getattr(self, 'flags', {}).get('custom_totals_set'):
#                     frappe.logger().info("Custom totals already set, skipping ERPNext calculation")
#                     # Only calculate taxes, not totals
#                     if hasattr(self, 'calculate_taxes'):
#                         self.calculate_taxes()
#                     return
                
#                 # Otherwise, run normal calculation
#                 original_calc(self)
            
#             SalesInvoice.calculate_taxes_and_totals = custom_calculate_taxes_and_totals
#             frappe.logger().info("✓ Patched calculate_taxes_and_totals")
        
#         # Patch calculate_totals if it exists
#         if hasattr(SalesInvoice, 'calculate_totals'):
#             original_totals = SalesInvoice.calculate_totals
            
#             def custom_calculate_totals(self):
#                 if getattr(self, 'flags', {}).get('custom_totals_set'):
#                     frappe.logger().info("Custom totals already set, skipping calculate_totals")
#                     return
#                 original_totals(self)
            
#             SalesInvoice.calculate_totals = custom_calculate_totals
#             frappe.logger().info("✓ Patched calculate_totals")
        
#         return True
        
#     except Exception as e:
#         frappe.logger().error(f"✗ Error patching Sales Invoice: {str(e)}")
#         import traceback
#         frappe.logger().error(traceback.format_exc())
#         return False