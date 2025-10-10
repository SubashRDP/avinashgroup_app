// File: Sales Invoice Client Script - Complete Corrected Version

frappe.ui.form.on("Sales Invoice", {
    refresh: function(frm) {
        console.log("Sales Invoice Form Refreshed");
    },
    
    items_on_form_rendered: function(frm) {
        sync_calculation_rows(frm);
    },
    
    // Trigger when price list changes
    selling_price_list: function(frm) {
        refresh_all_calculation_prices(frm);
    },
    // Recalculate when base_total changes
    base_total: function(frm) {
        calculate_total(frm);
    },
    base_total_taxes_and_charges: function(frm) {
        calculate_total(frm);
    },
    base_grand_total: function(frm) {
        console.log("Base Grand Total changed");
        calculate_total(frm);
    },
    taxes_and_charges: function(frm) {
        console.log("Taxes and Charges changed");
        calculate_total(frm);
    }
});

frappe.ui.form.on("Sales Invoice Item", {
    item_code: function(frm, cdt, cdn) {
        sync_calculation_rows(frm);
    },

    qty: function(frm, cdt, cdn) {
        sync_calculation_rows(frm);
    },
    
    uom: function(frm, cdt, cdn) {
        sync_calculation_rows(frm);
    },

    items_remove: function(frm) {
        console.log("Item Removed");
        sync_calculation_rows_remove(frm);
    },
    
    items_add: function(frm) {
        console.log("Item Added");
        sync_calculation_rows(frm);
    }
});

frappe.ui.form.on("Amount Calculation for sales invoice", {
    item_code: function(frm, cdt, cdn) {
        fetch_custom_item_price(frm, cdt, cdn);
    },
    
    uom: function(frm, cdt, cdn) {
        fetch_custom_item_price(frm, cdt, cdn);
    },
    
    qty: function(frm, cdt, cdn) {
        // Recalculate amount when qty changes
        calculate_amount(cdt, cdn);
    },
    
    custom_total_vat_inclusive: function(frm, cdt, cdn) {
        // Recalculate amount when price changes
        calculate_amount(cdt, cdn);
    },
    
    custom_difference_calculation_table_add: function(frm, cdt, cdn) {
        console.log("Manual row added");
    },
    
    custom_difference_calculation_table_remove: function(frm) {
        console.log("Removed Rows!!!");
        calculate_total(frm);
    }
});

/**
 * Sync calculation rows with Sales Invoice Items
 */
function sync_calculation_rows(frm) {
    const items = frm.doc.items || [];
    
    if (items.length === 0) {
        frm.clear_table("custom_difference_calculation_table");
        frm.refresh_field("custom_difference_calculation_table");
        calculate_total(frm);
        return;
    }

    const calculation_table = frm.doc.custom_difference_calculation_table || [];
    const linked_items = new Set(calculation_table.map(r => r.linked_item).filter(Boolean));
    
    items.forEach((item, index) => {
        let calc_row = calculation_table.find(r => r.linked_item === item.name);
        
        if (!calc_row) {
            calc_row = frm.add_child("custom_difference_calculation_table");
            calc_row.linked_item = item.name;
        }
        
        calc_row.item_code = item.item_code;
        calc_row.qty = item.qty;
        calc_row.uom = item.uom;
        calc_row.idx = index + 1;
        
        linked_items.add(item.name);
    });

    frm.refresh_field("custom_difference_calculation_table");
    fetch_all_calculation_prices(frm);
    calculate_total(frm);
}

/**
 * Remove calculation rows when items are removed
 */
function sync_calculation_rows_remove(frm) {
    const items = frm.doc.items || [];
    const calculation_rows = frm.doc.custom_difference_calculation_table || [];
    const valid_item_names = items.map(i => i.name);

    calculation_rows.slice().reverse().forEach(row => {
        if (row.linked_item && !valid_item_names.includes(row.linked_item)) {
            const grid = frm.get_field("custom_difference_calculation_table").grid;
            const row_obj = grid.grid_rows_by_docname[row.name];
            
            if (row_obj) {
                row_obj.remove();
            } else {
                const idx = frm.doc.custom_difference_calculation_table.indexOf(row);
                if (idx > -1) {
                    frm.doc.custom_difference_calculation_table.splice(idx, 1);
                }
            }
        }
    });

    sync_calculation_rows(frm);
    frm.refresh_field("custom_difference_calculation_table");
    calculate_total(frm);
}

/**
 * Fetch custom_total_vat_inclusive from Item Price
 */
function fetch_custom_item_price(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    
    if (!row.item_code) {
        console.log("No item_code, skipping price fetch");
        return;
    }
    
    const uom = row.uom;
    const price_list = frm.doc.selling_price_list;
    
    if (!price_list) {
        frappe.msgprint(__('Please select a Price List first'), 'Warning');
        return;
    }
    
    frappe.call({
        method: 'avinashgroup_app.custom_code.override_rounding.get_custom_amount',
        args: {
            customer: frm.doc.customer || '',
            price_list: price_list,
            item_code: row.item_code,
            qty: row.qty || 1,
            uom: uom
        },
        callback: function(r) {
            if (r.message && r.message.price !== undefined) {
                frappe.model.set_value(cdt, cdn, 'custom_total_vat_inclusive', r.message.price);
                frappe.model.set_value(cdt, cdn, 'base_custom_total_vat_inclusive',r.message.price);
                
                if (r.message.price_list_rate) {
                    console.log(`Fetched price for ${row.item_code} (${row.uom}): ${r.message.price}`);
                }
                
                // Calculate amount after price is set
                setTimeout(function() {
                    calculate_amount(cdt, cdn);
                }, 100);
            } else {
                frappe.model.set_value(cdt, cdn, 'custom_total_vat_inclusive', 0);
                 frappe.model.set_value(cdt, cdn, 'base_custom_total_vat_inclusive', 0);
            }
            
            frm.refresh_field("custom_difference_calculation_table");
        },
        error: function(r) {
            frappe.model.set_value(cdt, cdn, 'custom_total_vat_inclusive', 0);
            frappe.msgprint(__('Error fetching price for item {0}', [row.item_code]), 'Error');
        }
    });
}

/**
 * Fetch prices for all calculation rows
 */
function fetch_all_calculation_prices(frm) {
    const calculation_rows = frm.doc.custom_difference_calculation_table || [];
    
    if (calculation_rows.length === 0) {
        return;
    }
    
    const price_list = frm.doc.selling_price_list;
    
    if (!price_list) {
        console.log("No price list selected");
        return;
    }
    
    calculation_rows.forEach(row => {
        if (row.item_code) {
            fetch_custom_item_price(frm, row.doctype, row.name);
        }
    });
}

/**
 * Refresh prices when price list changes
 */
function refresh_all_calculation_prices(frm) {
    const calculation_rows = frm.doc.custom_difference_calculation_table || [];
    
    if (calculation_rows.length === 0) {
        return;
    }
    
    frappe.confirm(
        __('Do you want to refresh prices for all items based on the new Price List?'),
        function() {
            fetch_all_calculation_prices(frm);
        },
        function() {
            console.log("Price refresh cancelled");
        }
    );
}

/**
 * Calculate total amount for a single row
 * Formula: total_amount = qty * custom_total_vat_inclusive
 */
function calculate_amount(cdt, cdn) {
    console.log("Calculating amount for row");
    
    let row = locals[cdt][cdn];
    
    if (!row) {
        console.log("Row not found");
        return;
    }
    
    // Calculate row total: qty * price
    let qty = flt(row.qty) || 0;
    let price = flt(row.custom_total_vat_inclusive) || 0;
    let total_amount = qty * price;
    
    console.log(`Row ${row.idx}: Qty=${qty}, Price=${price}, Total=${total_amount}`);
    
    // Set the total amount for this row
    frappe.model.set_value(cdt, cdn, "total_amount", total_amount);
    frappe.model.set_value(cdt,cdn, "base_total_amount", total_amount);
    
    // Recalculate grand total after a brief delay
    setTimeout(function() {
        calculate_total(cur_frm);
    }, 100);
}

function calculate_total(frm) {
    if (!frm || !frm.doc) {
        console.log("Form not available");
        return;
    }
    
    let custom_total_amount = 0;
    let base_total = flt(frm.doc.base_total) || 0;
    let base_grand_total = flt(frm.doc.base_grand_total) || 0;
    
    // Sum up all row totals
    if (frm.doc.custom_difference_calculation_table) {
        frm.doc.custom_difference_calculation_table.forEach(function(row) {
            custom_total_amount += flt(row.total_amount) || 0;
        });
    }
    
    // Round to 2 decimal places
    custom_total_amount = flt(custom_total_amount, 2);
    
    // Calculate difference: base_total - custom_total_amount
    let difference = flt(custom_total_amount - base_grand_total, 2);
    
    console.log(`Totals - Custom: ${custom_total_amount}, Base: ${base_total}, Difference: ${difference}`);
    
    // Set values without triggering events
    frm.doc.custom_total_amount = custom_total_amount;
    frm.doc.custom_difference_adjustment = difference;
    
    // Refresh fields
    frm.refresh_field('custom_total_amount');
    frm.refresh_field('custom_difference_adjustment');
    
    // Convert rounded total to words via server call
    convert_rounded_total_to_words(frm);
}

/**
 * Convert rounded total (base_grand_total + base_rounding_adjustment) to words
 */
function convert_rounded_total_to_words(frm) {
    if (!frm || !frm.doc) {
        return;
    }
    
    // Calculate rounded total
    let base_grand_total = flt(frm.doc.base_grand_total) || 0;
    let base_rounding_adjustment = flt(frm.doc.custom_difference_adjustment) || 0;
    let rounded_total = base_grand_total + base_rounding_adjustment;
    
    // Get currency from the document
    let currency = frm.doc.currency || frappe.defaults.get_default("currency");
    
    // Call server method to convert to words
    frappe.call({
        method: 'avinashgroup_app.custom_code.override_rounding.convert_amount_to_words',
        args: {
            amount: rounded_total,
            currency: currency
        },
        callback: function(r) {
            if (r.message) {
                frm.set_value('base_in_words', r.message);
                frm.refresh_field('base_in_words');
                console.log(`Converted ${rounded_total} to words: ${r.message}`);
            }
        },
        error: function(r) {
            console.log("Error converting amount to words");
        }
    });
}