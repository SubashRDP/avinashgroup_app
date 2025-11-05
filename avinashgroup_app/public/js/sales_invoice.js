
frappe.ui.form.on("Sales Invoice", {
    is_return: function(frm) {
        set_naming_series_based_on_return(frm);
    },
    
    refresh: function(frm) {
        console.log("Sales Invoice Form Refreshed!");
        if (frm.doc.is_return) {
            console.log("IS RETURN")
            set_naming_series_based_on_return(frm);
        }
        //ROUNDING
        // Add custom button to manually resync calculation table
        // if (frm.doc.docstatus === 0) {
        //     frm.add_custom_button(__('Resync Calculation Table'), function() {
        //         frappe.show_alert({
        //             message: __('Resyncing calculation table...'),
        //             indicator: 'blue'
        //         });
        //         sync_calculation_rows(frm);
        //     });
        // }
        //ROUNDING    
        // When form loads with is_return=1, sync after delay
        // if (frm.doc.is_return === 1 && !frm._return_synced) {
        //     console.log("Return invoice detected, syncing after delay...");
        //     frm._return_synced = true;
        //     setTimeout(() => {
        //         sync_calculation_rows(frm);
        //     }, 500);
        // }
    },
    
    onload: function(frm) {
        //ROUNDING
        // When new return invoice is created via button, sync after longer delay
        // if (frm.doc.is_return === 1 && frm.is_new() && !frm._return_synced) {
        //     console.log("New return invoice, waiting for negative qty to be set...");
        //     frm._return_synced = true;
        //     setTimeout(() => {
        //         sync_calculation_rows(frm);
        //     }, 1000);
        // }
    },
    //ROUNFING
    // items_on_form_rendered: function(frm) {
    //     // Only sync if not already synced for return invoices
    //     if (frm.doc.is_return === 1) {
    //         if (!frm._items_rendered_synced) {
    //             frm._items_rendered_synced = true;
    //             setTimeout(() => sync_calculation_rows(frm), 500);
    //         }
    //     } else {
    //         sync_calculation_rows(frm);
    //     }
    // },
    
    // Trigger when price list changes

    //ROUNDING
    // selling_price_list: function(frm) {
    //     refresh_all_calculation_prices(frm);
    // },
    
    // Recalculate when totals change
    base_total_taxes_and_charges: function(frm) {
        calculate_total(frm);
    },
    
    base_grand_total: function(frm) {
        console.log("Base Grand Total changed");
        calculate_total(frm);
    },
    taxes_and_charges: function(frm) {
        console.log("Taxes and Charges template changed");
        setTimeout(() => {
            calculate_vat_total(frm);
            calculate_total(frm);
        }, 500);
    },
    
    // taxes_and_charges: function(frm) {
    //     console.log("Taxes and Charges changed");
    //     calculate_total(frm);
    //     calculate_vat_total(frm);
        
    // },
    //taxes
    
    
    total_advance: function(frm) {
        console.log("Total Advance changed");
        calculate_total(frm);
    },
    
    outstanding_amount: function(frm) {
        console.log("Outstanding Amount changed");

        //ROUNDING
        // update_payment_schedule(frm);
    }
});

frappe.ui.form.on("Sales Invoice Item", {
    item_code: async function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row && row.item_code) {
            try {
                const item_check = await frappe.call({
                    method: "frappe.client.get_value",
                    args: {
                        doctype: "Item",
                        filters: { name: row.item_code },
                        fieldname: "item_name"
                    }
                });
                
                if (!item_check.message) {
                    return;
                }
                
                let custom_excise_duty = 0;
                try {
                    const item_r = await frappe.call({
                        method: "frappe.client.get_value",
                        args: {
                            doctype: "Item",
                            filters: { name: row.item_code },
                            fieldname: "custom_excise_duty"
                        }
                    });
                    custom_excise_duty = item_r.message ? flt(item_r.message.custom_excise_duty || 0) : 0;
                    console.log(`Excise duty for ${row.item_code}: ${custom_excise_duty}`);
                } catch(e) {
                    console.error("Error fetching excise duty:", e);
                }

                let custom_vat=0;
                try{
                    const item_doc= await frappe.call({
                        method: "frappe.client.get",
                        args: {
                            doctype: "Item",
                            name: row.item_code
                        }
                    });
                    console.log("Fetched item doc for VAT:", item_doc);

                    if(item_doc.message && item_doc.message.taxes && item_doc.message.taxes.length >0){


                        custom_vat = flt(item_doc.message.taxes[0].maximum_net_rate || 0);
                        console.log(`VAT for ${row.item_code}: ${custom_vat}`);
                    }
                }catch(e){
                    console.error("Error fetching VAT:", e);
                }

                await frappe.model.set_value(cdt, cdn, 'custom_excise_duty', custom_excise_duty);
                await frappe.model.set_value(cdt, cdn, 'custom_vat', custom_vat);

                setTimeout(() => {
                    update_item_values(frm, cdt, cdn);
                    calculate_vat_amount(frm, cdt, cdn);

                    //ROUNDING
                    // sync_calculation_rows(frm);
                }, 800);
                
            } catch(e) {
                console.error("Error in item_code handler:", e);
            }
        }
    },

    qty: function(frm, cdt, cdn) {
        setTimeout(() => {
            update_item_values(frm, cdt, cdn);
            calculate_vat_amount(frm, cdt, cdn);

            //ROUNDING
            // sync_calculation_rows(frm);
        }, 300);
    },
    
    amount: function(frm, cdt, cdn) {
        setTimeout(() => {
            update_item_values(frm, cdt, cdn);
            calculate_vat_amount(frm, cdt, cdn);
        }, 300);
    },
    
    rate: function(frm, cdt, cdn) {
        setTimeout(() => {
            update_item_values(frm, cdt, cdn);
            calculate_vat_amount(frm, cdt, cdn);
        }, 300);
    },
    
    custom_excise_duty: function(frm, cdt, cdn) {
        setTimeout(() => {
            update_item_values(frm, cdt, cdn);
            calculate_vat_amount(frm, cdt, cdn);
        }, 300);
    },

    custom_vat: function(frm, cdt, cdn) {
        setTimeout(() => {
            update_item_values(frm, cdt, cdn);
            calculate_vat_amount(frm, cdt, cdn);
        }, 300);
    },

    custom_total: function(frm, cdt, cdn) {
        setTimeout(() => {
            calculate_vat_amount(frm, cdt, cdn);
        }, 300);
    },
    
    uom: function(frm, cdt, cdn) {
        setTimeout(() => {
            //ROUNDING
            // sync_calculation_rows(frm);
        }, 300);
    },

    items_remove: function(frm) {
        console.log("Item Removed");
        //ROUNDING
        // sync_calculation_rows_remove(frm);
    },
    
    items_add: function(frm) {
        console.log("Item Added");
        setTimeout(() => {
            //ROUNDING
            // sync_calculation_rows(frm);
        }, 300);
    }
});



// Function to calculate VAT amount = (VAT * custom_total_including_excise) /100
function calculate_vat_amount(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    
    if (row) {
        let custom_total = flt(row.custom_total || 0);
        let custom_vat = flt(row.custom_vat || 0);
        
        // Calculate custom_vat_amount = custom_total * custom_vat / 100
        // Assuming custom_vat is a percentage (e.g., 13 for 13%)
        let custom_vat_amount = (custom_total * custom_vat) / 100;
        
        // Set the calculated value
        frappe.model.set_value(cdt, cdn, 'custom_vat_amount', custom_vat_amount);
        
        console.log(`VAT Amount calculated for row ${cdn}: ${custom_vat_amount} (Total: ${custom_total}, VAT: ${custom_vat}%)`);
        setTimeout(() => {
            calculate_total_vat_amount(frm);
        }, 100);
    }
}


//Function to calculate VAT amount into the total VAT Amount field
function calculate_total_vat_amount(frm){
    let total_vat_amount =0;
    if(frm.doc.items && frm.doc.items.length >0){
        frm.doc.items.forEach(function(row){
            let vat_amount = flt(row.custom_vat_amount || 0);
            total_vat_amount += vat_amount;
          
        });
    }
    frm.set_value('custom_total_vat_amount', total_vat_amount);
    // frm.set_value('custom_excise_value',total_excise_amount);
    setTimeout(() => {
       update_vat_in_taxes(frm, total_vat_amount);
       calculate_total(frm);
    }, 100);

   
}

//Function to update VAT in taxes table

// function update_vat_in_taxes(frm, total_vat_amount){
//     if(frm.doc.company !== "Nepal Gas Udhyog (Karnali) Pvt. Ltd."){
//         return;
//     }
//     let vat_row_found = false;
//     let vat_row=null;

//     if(frm.doc.taxes && frm.doc.taxes.length >0){

//         frm.doc.taxes.forEach((tax_row,idx)=> {
//             if(tax_row.charge_type === "Actual" && tax_row.account_head && tax_row.account_head === "VAT - NGK"){
//                 vat_row= tax_row
//                 vat_row_found = true;

//     }
// });
//     }
//      if (vat_row_found && vat_row) {
//         // Update existing VAT row
//         frappe.model.set_value(vat_row.doctype, vat_row.name, 'tax_amount', total_vat_amount);
//         console.log(`Updated existing VAT row with amount: ${total_vat_amount}`);
//     } else {
//         // Create new VAT row
//         let new_row = frm.add_child('taxes');
//         frappe.model.set_value(new_row.doctype, new_row.name, 'charge_type', 'Actual');
//         frappe.model.set_value(new_row.doctype, new_row.name, 'account_head', 'VAT - NGK');
//         frappe.model.set_value(new_row.doctype, new_row.name, 'description', 'VAT - NGK');
//         frappe.model.set_value(new_row.doctype, new_row.name, 'tax_amount', total_vat_amount);
//         console.log(`Created new VAT row with amount: ${total_vat_amount}`);
//     }
    
//     // Refresh the taxes table display
//     frm.refresh_field('taxes');
// }

function update_vat_in_taxes(frm, total_vat_amount){
    if(frm.doc.company !== "Nepal Gas Udhyog (Karnali) Pvt. Ltd."){
        return;
    }
    
    let vat_row_found = false;
    let vat_row = null;
    let vat_row_index = -1;

    if(frm.doc.taxes && frm.doc.taxes.length > 0){
        frm.doc.taxes.forEach((tax_row, idx) => {
            if(tax_row.charge_type === "Actual" && 
               tax_row.account_head && 
               tax_row.account_head === "VAT - GLMI"){
                vat_row = tax_row;
                vat_row_found = true;
                vat_row_index = idx;
            }
        });
    }
    
    if (vat_row_found && vat_row) {
        // Update existing VAT row
        frappe.model.set_value(vat_row.doctype, vat_row.name, 'tax_amount', total_vat_amount);
        console.log(`Updated existing VAT row at index ${vat_row_index} with amount: ${total_vat_amount}`);
        
        // Ensure it's at index 1 (second position, after excise)
        if (vat_row_index !== 1) {
            move_tax_row_to_position(frm, vat_row_index, 1);
        }
    } else {
        // Create new VAT row
        let new_row = frm.add_child('taxes', {
            charge_type: 'Actual',
            account_head: 'VAT - GLMI',
            description: 'VAT - GLMI',
            tax_amount: total_vat_amount
        });
        
        console.log(`Created new VAT row with amount: ${total_vat_amount}`);
        
        // Move to second position (index 1)
        let new_row_index = frm.doc.taxes.length - 1;
        if (new_row_index !== 1) {
            move_tax_row_to_position(frm, new_row_index, 1);
        }
    }
    
    frm.refresh_field('taxes');
}

// Helper function to move a tax row to a specific position
function move_tax_row_to_position(frm, from_index, to_index) {
    if (!frm.doc.taxes || from_index === to_index) {
        return;
    }
    
    // Remove the row from its current position
    let row = frm.doc.taxes.splice(from_index, 1)[0];
    
    // Insert it at the new position
    frm.doc.taxes.splice(to_index, 0, row);
    
    // Update idx for all rows
    frm.doc.taxes.forEach((tax_row, idx) => {
        tax_row.idx = idx + 1;
    });
    
    console.log(`Moved tax row from position ${from_index} to ${to_index}`);
}

// Modified update_item_values to call excise first
function update_item_values(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    
    if (!row) {
        console.log("Row not found in update_item_values");
        return;
    }
    
    let qty = flt(row.qty) || 0;
    let amount = flt(row.amount) || 0;
    const custom_excise_duty = flt(row.custom_excise_duty) || 0;

    let custom_excise_value = flt(custom_excise_duty * qty, 2);
    let custom_total = flt(amount + custom_excise_value, 2);

    console.log(`Calculating for ${row.item_code}: qty=${qty}, amount=${amount}, excise_duty=${custom_excise_duty}`);
    console.log(`Results: excise_value=${custom_excise_value}, total=${custom_total}`);

    frappe.model.set_value(cdt, cdn, 'custom_excise_value', custom_excise_value)
        .then(() => {
            return frappe.model.set_value(cdt, cdn, 'custom_total', custom_total);
        })
        .then(() => {
            console.log(`Updated ${row.item_code}: Excise=${custom_excise_value}, Total=${custom_total}`);
            frm.refresh_field('items');
        })
        .catch((err) => {
            console.error("Error setting values:", err);
        });
    
    // Calculate excise total first
    setTimeout(() => {
        calculate_total_excise_value(frm);
    }, 200);
}
/**
 * Update excise values for a single item row
 * This function ONLY updates custom_excise_value and custom_total
 * It does NOT override base_total (Python hooks do that)
 */
//Exercise value calculation

function update_item_values(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    
    if (!row) {
        console.log("Row not found in update_item_values");
        return;
    }
    
    let qty = flt(row.qty) || 0;
    let amount = flt(row.amount) || 0;
    const custom_excise_duty = flt(row.custom_excise_duty) || 0;

    let custom_excise_value = flt(custom_excise_duty * qty, 2);
    let custom_total = flt(amount + custom_excise_value, 2);

    console.log(`Calculating for ${row.item_code}: qty=${qty}, amount=${amount}, excise_duty=${custom_excise_duty}`);
    console.log(`Results: excise_value=${custom_excise_value}, total=${custom_total}`);

    // Update values using frappe.model.set_value
    frappe.model.set_value(cdt, cdn, 'custom_excise_value', custom_excise_value)
        .then(() => {
            return frappe.model.set_value(cdt, cdn, 'custom_total', custom_total);
        })
        .then(() => {
            console.log(`Updated ${row.item_code}: Excise=${custom_excise_value}, Total=${custom_total}`);
            frm.refresh_field('items');
        })
        .catch((err) => {
            console.error("Error setting values:", err);
        });
    setTimeout(() => {
        calculate_total_excise_value(frm);
    }, 200);
}

function calculate_total_excise_value(frm){
    let total_excise_amount = 0;
    if(frm.doc.items && frm.doc.items.length > 0){
        frm.doc.items.forEach(function(row){
            total_excise_amount += flt(row.custom_excise_value || 0);
            // let custom_excise_value = flt(row.custom_excise_value || 0);
            // total_excise_amount += custom_excise_value;
            // let total_amount = flt(row.total || 0);
        });
    }
    frm.set_value('custom_total_excise_amount', total_excise_amount);
    // frm.set_value('custom_excise_value',total_excise_amount);
    setTimeout(() => {
       update_excise_in_taxes(frm, total_excise_amount);
       calculate_total(frm);
    }, 100);

}
function update_excise_in_taxes(frm, total_excise_amount){
    if(frm.doc.company !== "Grihalaxmi Metal Industries Pvt. Ltd."){

        return;
    }
    
    let excise_row_found = false;
    let excise_row = null;
    let excise_row_index = -1;

    if(frm.doc.taxes && frm.doc.taxes.length > 0){
        frm.doc.taxes.forEach((tax_row, idx) => {
            if(tax_row.charge_type === "Actual" && 
               tax_row.account_head && 
               tax_row.account_head === "347714 - Excise Duty - GLMI"){
                excise_row = tax_row;
                excise_row_found = true;
                excise_row_index = idx;
            }
        });
    }
    
    if (excise_row_found && excise_row) {
        // Update existing Excise row
        frappe.model.set_value(excise_row.doctype, excise_row.name, 'tax_amount', total_excise_amount);
        console.log(`Updated existing Excise Duty row at index ${excise_row_index} with amount: ${total_excise_amount}`);
        
        // Ensure it's at index 0 (first position)
        if (excise_row_index !== 0) {
            move_tax_row_to_position(frm, excise_row_index, 0);
        }
    } else {
        // Create new Excise row AT THE BEGINNING
        let new_row = frm.add_child('taxes', {
            charge_type: 'Actual',
            account_head: '347714 - Excise Duty - GLMI',
            description: 'Excise Duty - GLMI',
            tax_amount: total_excise_amount
        });
        
        console.log(`Created new Excise Duty row with amount: ${total_excise_amount}`);
        
        // Move to first position
        let new_row_index = frm.doc.taxes.length - 1;
        if (new_row_index > 0) {
            move_tax_row_to_position(frm, new_row_index, 0);
        }
    }
    
    frm.refresh_field('taxes');
}

// function update_excise_in_taxes(frm, total_excise_amount){
//     if(frm.doc.company !== "Nepal Gas Udhyog (Karnali) Pvt. Ltd."){
//         return;
//     }
//     let vat_row_found = false;
//     let vat_row=null;

//     if(frm.doc.taxes && frm.doc.taxes.length >0){

//         frm.doc.taxes.forEach((tax_row,idx)=> {
//             if(tax_row.charge_type === "Actual" && tax_row.account_head && tax_row.account_head === "347714 - Excise Duty - NGK"){

//                 vat_row= tax_row
//                 vat_row_found = true;

//     }
// });
//     }
//      if (vat_row_found && vat_row) {
//         // Update existing VAT row
//         frappe.model.set_value(vat_row.doctype, vat_row.name, 'tax_amount', total_excise_amount);
//         console.log(`Updated existing VAT row with amount: ${total_excise_amount}`);
//     } else {
//         // Create new VAT row
//         let new_row = frm.add_child('taxes');
//         frappe.model.set_value(new_row.doctype, new_row.name, 'charge_type', 'Actual');
//         frappe.model.set_value(new_row.doctype, new_row.name, 'account_head', '347714 - Excise Duty - NGK');
//         frappe.model.set_value(new_row.doctype, new_row.name, 'description', 'Excise Duty - NGK');
//         frappe.model.set_value(new_row.doctype, new_row.name, 'tax_amount', total_excise_amount);
//         console.log(`Created new Excise Duty row with amount: ${total_excise_amount}`);
//     }
    
//     // Refresh the taxes table display
//     frm.refresh_field('taxes');
// }
// //ROUNDING

// frappe.ui.form.on("Amount Calculation for sales invoice", {
//     item_code: function(frm, cdt, cdn) {
//         fetch_custom_item_price(frm, cdt, cdn);
//     },
    
//     uom: function(frm, cdt, cdn) {
//         fetch_custom_item_price(frm, cdt, cdn);
//     },
    
//     qty: function(frm, cdt, cdn) {
//         calculate_amount(cdt, cdn);
//     },
    
//     custom_total_vat_inclusive: function(frm, cdt, cdn) {
//         calculate_amount(cdt, cdn);
//     },
    
//     custom_difference_calculation_table_add: function(frm, cdt, cdn) {
//         console.log("Manual row added");
//     },
    
//     custom_difference_calculation_table_remove: function(frm) {
//         console.log("Removed Rows!!!");
//         calculate_total(frm);
//     }
// });

frappe.ui.form.on("Sales Taxes and Charges", {
    account_head: function(frm, cdt, cdn) {
        console.log("TTax account head changed");
         setTimeout(() => {
            calculate_vat_total(frm);
            calculate_total(frm);
        }, 500);
        // calculate_vat_total(frm);

    },
    
    tax_amount: function(frm, cdt, cdn) {
        calculate_vat_total(frm);
    },
    
    taxes_add: function(frm) {
        calculate_vat_total(frm);
    },
    
    taxes_remove: function(frm) {
        calculate_vat_total(frm);
    }
});
/**
 * Calculate total VAT from taxes table
 * Sums all tax amounts where account_head starts with "VAT -"
 */
function calculate_vat_total(frm) {
    if (!frm || !frm.doc) {
        console.log("Form not available");
        return;
    }
    
    let vat_total = 0;
    
    // Loop through all tax rows
    if (frm.doc.taxes && frm.doc.taxes.length > 0) {
        frm.doc.taxes.forEach(function(tax_row) {
            let account_head = tax_row.account_head || '';
            let tax_amount = flt(tax_row.tax_amount) || 0;
            
            // Check if account_head starts with "VAT -"
            if (account_head.startsWith('VAT -')) {
                vat_total += tax_amount;
                console.log(`VAT Row: ${account_head} = ${tax_amount}`);
            }
        });
    }
    
    vat_total = flt(vat_total, 2);
    
    console.log(`Total VAT: ${vat_total}`);
    
    // Set the custom_vat field
    frm.set_value('custom_total_vat_amount', vat_total);
    frm.refresh_field('custom_total_vat_amount');
}

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
    
    // Remove invalid rows
    const valid_item_names = items.map(i => i.name);
    const rows_to_remove = [];
    
    calculation_table.forEach(row => {
        if (!row.linked_item || !valid_item_names.includes(row.linked_item)) {
            rows_to_remove.push(row);
        }
    });
    
    rows_to_remove.forEach(row => {
        const idx = frm.doc.custom_difference_calculation_table.indexOf(row);
        if (idx > -1) {
            frm.doc.custom_difference_calculation_table.splice(idx, 1);
        }
    });
    
    // Sync valid items
    items.forEach((item, index) => {
        let calc_row = frm.doc.custom_difference_calculation_table.find(r => r.linked_item === item.name);
        
        if (!calc_row) {
            calc_row = frm.add_child("custom_difference_calculation_table");
            calc_row.linked_item = item.name;
        }
        
        // Get quantity from locals
        let item_data = locals['Sales Invoice Item'][item.name];
        let item_qty = item_data?.qty ?? item.qty ?? 0;
        
        // For return invoices, ensure qty is negative
        if (frm.doc.is_return === 1 && item_qty > 0) {
            console.warn(`Return invoice but qty is positive for ${item.item_code}, making it negative`);
            item_qty = -Math.abs(item_qty);
        }
        
        console.log(`Syncing ${item.item_code}: qty=${item_qty}, is_return=${frm.doc.is_return}`);
        
        // Set fields
        calc_row.item_code = item.item_code;
        calc_row.uom = item.uom;
        calc_row.idx = index + 1;
        
        // Set qty directly in locals
        let calc_row_data = locals['Amount Calculation for sales invoice'][calc_row.name];
        if (calc_row_data) {
            calc_row_data.qty = item_qty;
        } else {
            calc_row.qty = item_qty;
        }
    });

    // Deduplicate rows
    const seen_items = new Set();
    const final_rows = [];
    
    frm.doc.custom_difference_calculation_table.forEach(row => {
        if (row.linked_item && !seen_items.has(row.linked_item)) {
            seen_items.add(row.linked_item);
            final_rows.push(row);
        }
    });
    
    frm.doc.custom_difference_calculation_table = final_rows;
    frm.refresh_field("custom_difference_calculation_table");
    
    // Fetch prices
    setTimeout(() => {
        fetch_all_calculation_prices(frm);
    }, 200);
}

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
    
    const qty_for_lookup = Math.abs(row.qty || 1);
    
    frappe.call({
        method: 'avinashgroup_app.custom_code.override_rounding.get_custom_amount',
        args: {
            customer: frm.doc.customer || '',
            price_list: price_list,
            item_code: row.item_code,
            qty: qty_for_lookup,
            uom: uom
        },
        callback: function(r) {
            if (r.message && r.message.price !== undefined) {
                let row_data = locals[cdt][cdn];
                row_data.custom_total_vat_inclusive = r.message.price;
                row_data.base_custom_total_vat_inclusive = r.message.price;
                
                console.log(`Fetched price for ${row.item_code} (${row.uom}): ${r.message.price}`);
                
                frm.refresh_field("custom_difference_calculation_table");
                
                setTimeout(function() {
                    calculate_amount(cdt, cdn);
                }, 100);
            } else {
                let row_data = locals[cdt][cdn];
                row_data.custom_total_vat_inclusive = 0;
                row_data.base_custom_total_vat_inclusive = 0;
                frm.refresh_field("custom_difference_calculation_table");
            }
        },
        error: function(r) {
            let row_data = locals[cdt][cdn];
            row_data.custom_total_vat_inclusive = 0;
            frappe.msgprint(__('Error fetching price for item {0}', [row.item_code]), 'Error');
        }
    });
}

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

function calculate_amount(cdt, cdn) {
    console.log("Calculating amount for row");
    
    let row = locals[cdt][cdn];
    
    if (!row) {
        console.log("Row not found");
        return;
    }
    
    let qty = parseFloat(row.qty) || 0;
    let price = parseFloat(row.custom_total_vat_inclusive) || 0;
    let total_amount = qty * price;
    
    console.log(`Row ${row.idx}: Qty=${qty}, Price=${price}, Total=${total_amount}`);
    
    row.total_amount = total_amount;
    row.base_total_amount = total_amount;
    
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
    let base_grand_total = flt(frm.doc.base_grand_total) || 0;
    let total_advance = flt(frm.doc.total_advance) || 0;
    let custom_total_excluding_excise = 0;  // Reset to 0
    let total_excise = 0;  // Track total excise separately


     


    //Rounding

    // // Sum calculation table totals
    // if (frm.doc.custom_difference_calculation_table) {
    //     frm.doc.custom_difference_calculation_table.forEach(function(row) {
    //         let row_total = parseFloat(row.total_amount) || 0;
    //         custom_total_amount += row_total;
    //     });
    // }

    // Calculate total excluding excise (sum of all item amounts which is qty * rate)
    if (frm.doc.items && frm.doc.items.length > 0) {
        frm.doc.items.forEach(function(item) {
            let amount = flt(item.amount) || 0;  // This is qty * rate
            let excise_value = flt(item.custom_excise_value) || 0;
            
            custom_total_excluding_excise += amount;
            total_excise += excise_value;
        });
        
        // Set the calculated values
        frm.doc.custom_total_amount = flt(custom_total_excluding_excise, 2);
        frm.doc.custom_excise = flt(total_excise, 2);

        frm.refresh_field('custom_total_amount');
        frm.refresh_field('custom_excise');
        
        console.log(`Total Excluding Excise: ${custom_total_excluding_excise}, Total Excise: ${total_excise}`);
    }
    
    custom_total_amount = flt(custom_total_amount, 2);


    //ROUNDING
    
    // Calculate difference
    // let difference = flt(custom_total_amount - base_grand_total, 2);
    
    // Calculate rounded total
    // let rounded_total = flt(base_grand_total + difference, 2);
    
    // Calculate outstanding
    // let outstanding = flt(rounded_total - total_advance, 2);
    
    // console.log(`Totals - Custom: ${custom_total_amount}, Difference: ${difference}, Rounded: ${rounded_total}, Outstanding: ${outstanding}`);
    
    // // Set values (Python hooks will finalize these on save)
    // frm.doc.custom_total_amount = custom_total_amount;
    // frm.doc.custom_difference_adjustment = difference;
    // frm.doc.rounded_total = rounded_total;
    // frm.doc.outstanding_amount = outstanding;
    
    frm.refresh_field('custom_total_amount');

    //ROUNDING

    // frm.refresh_field('custom_difference_adjustment');
    // frm.refresh_field('rounded_total');
    // frm.refresh_field('outstanding_amount');

      // Calculate VAT total
    calculate_vat_total(frm);
    
    //ROUNDING
    // update_payment_schedule(frm);
    // convert_rounded_total_to_words(frm);
}
function update_payment_schedule(frm) {
    if (!frm || !frm.doc || !frm.doc.payment_schedule || frm.doc.payment_schedule.length === 0) {
        return;
    }
    
    let outstanding = flt(frm.doc.outstanding_amount) || 0;
    let conversion_rate = flt(frm.doc.conversion_rate) || 1;
    
    let row = frm.doc.payment_schedule[0];
    frappe.model.set_value(row.doctype, row.name, 'base_payment_amount', outstanding);
    frappe.model.set_value(row.doctype, row.name, 'payment_amount', flt(outstanding / conversion_rate, 2));
    
    frm.refresh_field('payment_schedule');
}

function convert_rounded_total_to_words(frm) {
    if (!frm || !frm.doc) {
        return;
    }
    
    let base_grand_total = flt(frm.doc.base_grand_total) || 0;
    let base_rounding_adjustment = flt(frm.doc.custom_difference_adjustment) || 0;
    let rounded_total = base_grand_total + base_rounding_adjustment;
    let currency = frm.doc.currency || frappe.defaults.get_default("currency");
    
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
        }
    });
}

function set_naming_series_based_on_return(frm) {
    if (frm.doc.is_return == 1) {
        frm.set_value('naming_series', '{custom_abbr}.-RET-SB-.####');
    } else {
        frm.set_value('naming_series', '{custom_abbr}.-SB-.####');
    }
}




