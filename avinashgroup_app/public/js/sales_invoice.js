
frappe.ui.form.on("Sales Invoice", {
    refresh: function(frm) {
        console.log("Sales Invoice Form Refreshed");
    },
    
    items_on_form_rendered: function(frm) {
        sync_calculation_rows(frm);
    },

    
    // Trigger when price list changes
    selling_price_list: function(frm) {
        // Refresh prices for all calculation rows
        refresh_all_calculation_prices(frm);
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
        // Fetch price when item_code changes in calculation table
        fetch_custom_item_price(frm, cdt, cdn);
    },
    
    uom: function(frm, cdt, cdn) {
        // Fetch price when UOM changes
        fetch_custom_item_price(frm, cdt, cdn);
    },
    
    qty: function(frm, cdt, cdn) {
        // Optionally fetch price when qty changes (for tiered pricing)
        fetch_custom_item_price(frm, cdt, cdn);
    },
    
    custom_difference_calculation_table_add: function(frm, cdt, cdn) {
        console.log("Manual row added");
    },
    
    custom_difference_calculation_table_remove: function(frm) {
        console.log("Removed Rows!!!");
    }
});

/**
 * Sync calculation rows with Sales Invoice Items
 * Creates/updates one calculation row for each item row
 */
function sync_calculation_rows(frm) {
    const items = frm.doc.items || [];
    
    if (items.length === 0) {
        frm.clear_table("custom_difference_calculation_table");
        frm.refresh_field("custom_difference_calculation_table");
        return;
    }

    const calculation_table = frm.doc.custom_difference_calculation_table || [];
    const linked_items = new Set(calculation_table.map(r => r.linked_item).filter(Boolean));
    
    // For each item, ensure there's a corresponding calculation row
    items.forEach((item, index) => {
        let calc_row = calculation_table.find(r => r.linked_item === item.name);
        
        if (!calc_row) {
            // Create new row if it doesn't exist
            calc_row = frm.add_child("custom_difference_calculation_table");
            calc_row.linked_item = item.name;
        }
        
        // Sync fields from item to calculation row
        calc_row.item_code = item.item_code;
        calc_row.qty = item.qty;
        calc_row.uom = item.uom;
        calc_row.idx = index + 1;
        
        linked_items.add(item.name);
    });

    frm.refresh_field("custom_difference_calculation_table");
    
    // Fetch prices for all calculation rows
    fetch_all_calculation_prices(frm);
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
}

/**
 * Fetch custom_total_vat_inclusive from Item Price for a single row
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
    
    // Show loading indicator
    frappe.model.set_value(cdt, cdn, 'custom_total_vat_inclusive', 'Loading...');
    
    frappe.call({
        method: 'avinashgroup_app.custom_code.override_rounding.get_custom_amount',
        args: {
            customer: frm.doc.customer ,
            price_list: price_list,
            item_code: row.item_code,
            qty: row.qty || 1,
            uom: uom
        },
        callback: function(r) {
            if (r.message && r.message.price !== undefined) {
                // Set the custom_total_vat_inclusive field
                frappe.model.set_value(cdt, cdn, 'custom_total_vat_inclusive', r.message.price);
                
                // Optionally set other fields
                if (r.message.price_list_rate) {
                    console.log(`Fetched price for ${row.item_code} and ${row.uom}: ${r.message.price}`);
                }
            } else {
                frappe.model.set_value(cdt, cdn, 'custom_total_vat_inclusive', 0);
                frappe.msgprint(__('No price found for item {0}', [row.item_code]), 'Warning');
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
 * Fetch prices for all calculation rows at once
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
    
    // Fetch prices for each row
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
            // Yes - refresh all prices
            fetch_all_calculation_prices(frm);
        },
        function() {
            // No - do nothing
            console.log("Price refresh cancelled");
        }
    );
}
// frappe.ui.form.on("Sales Invoice", {

//     refresh: function(frm){
//         console.log("Sales Invoice Form Refreshed@@");
//     },
    
//     items_on_form_rendered: function(frm) {
//         sync_calculation_rows(frm);
//     },

//     posting_date: function(frm) {
//         sync_calculation_rows(frm);
//     },
// });

// frappe.ui.form.on("Sales Invoice Item", {
//     item_code: function(frm, cdt, cdn) {
//         sync_calculation_rows(frm);
//     },

//     qty: function(frm, cdt, cdn) {
//         sync_calculation_rows(frm);
//     },
    
//     uom: function(frm, cdt, cdn) {
//         sync_calculation_rows(frm);
//     },

//     items_remove: function(frm) {
//         console.log("Item Removed");
//         sync_calculation_rows_remove(frm);
//     },
    
//     items_add: function(frm) {
//         console.log("Item Added");
//         sync_calculation_rows(frm);
//     }
// });

// frappe.ui.form.on("Amount Calculation for sales invoice", {
//     custom_difference_calculation_table_add: function (frm, cdt, cdn) {
//         // When manually adding a row, don't do anything
//         // sync_calculation_rows will handle it
//         console.log("Manual row added");
//     },
    
//     custom_difference_calculation_table_remove: function (frm) {
//         console.log("Removed Rows!!!");
//     }
// });

// /**
//  * Sync calculation rows with Sales Invoice Items
//  * Creates/updates one calculation row for each item row
//  */
// function sync_calculation_rows(frm) {
//     const items = frm.doc.items || [];
    
//     if (items.length === 0) {
//         // If no items, clear calculation table
//         frm.clear_table("custom_difference_calculation_table");
//         frm.refresh_field("custom_difference_calculation_table");
//         return;
//     }

//     const calculation_table = frm.doc.custom_difference_calculation_table || [];
    
//     // Track which item names are linked
//     const linked_items = new Set(calculation_table.map(r => r.linked_item).filter(Boolean));
    
//     // For each item, ensure there's a corresponding calculation row
//     items.forEach((item, index) => {
//         let calc_row = calculation_table.find(r => r.linked_item === item.name);
        
//         if (!calc_row) {
//             // Create new row if it doesn't exist
//             calc_row = frm.add_child("custom_difference_calculation_table");
//             calc_row.linked_item = item.name;
//         }
        
//         // Sync fields from item to calculation row
//         calc_row.item_code = item.item_code;
//         calc_row.qty = item.qty;
//         calc_row.uom = item.uom;
        
//         // Set the idx to match item order
//         calc_row.idx = index + 1;
        
//         // Mark as synced
//         linked_items.add(item.name);
//     });

//     frm.refresh_field("custom_difference_calculation_table");
// }

// /**
//  * Remove calculation rows when items are removed
//  */
// function sync_calculation_rows_remove(frm) {
//     const items = frm.doc.items || [];
//     const calculation_rows = frm.doc.custom_difference_calculation_table || [];

//     // Get valid item names that still exist
//     const valid_item_names = items.map(i => i.name);

//     // Remove calculation rows that don't have a corresponding item
//     calculation_rows.slice().reverse().forEach(row => {
//         if (row.linked_item && !valid_item_names.includes(row.linked_item)) {
//             // Find and remove the row
//             const grid = frm.get_field("custom_difference_calculation_table").grid;
//             const row_obj = grid.grid_rows_by_docname[row.name];
            
//             if (row_obj) {
//                 row_obj.remove();
//             } else {
//                 // Fallback: remove from array directly
//                 const idx = frm.doc.custom_difference_calculation_table.indexOf(row);
//                 if (idx > -1) {
//                     frm.doc.custom_difference_calculation_table.splice(idx, 1);
//                 }
//             }
//         }
//     });

//     // Re-sync to ensure proper order
//     sync_calculation_rows(frm);
//     frm.refresh_field("custom_difference_calculation_table");
// }

// /**
//  * Optional: Fetch custom item price
//  */

// function fetch_custom_item_price(frm, cdt, cdn) {
//     const row = locals[cdt][cdn];
    
//     if (row.item_code) {
//         // const custom_location = frm.doc.custom_location || null;
//         // const custom_item_description = row.custom_item_description || '';
//         const uom = row.uom || '';
        
//         frappe.call({
//             method: 'avinashgroup_app.custom_code.item_price.get_custom_amount',
//             args: {
//                 customer: frm.doc.customer,
//                 price_list:frm.doc.price_list,
//                 item_code: row.item_code,
//                 qty: row.qty || 1,
//                 uom: uom,
//                 // custom_item_description: custom_item_description,
 
//                 // custom_location: custom_location,
//                 // doc_type: frm.doc.custom_type 
//             },
//             callback: function(r) {
//                 if (r.message && r.message.price) {
//                     frappe.model.set_value(cdt, cdn, 'custom_total_vat_inclusive', r.message.price);
//                     sync_calculation_rows(frm);
//                 } else {
//                     frappe.model.set_value(cdt, cdn, 'rate', 0);
//                 }
//             }
//         });
//     }
// }

