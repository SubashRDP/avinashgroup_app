// // // PROPERLY HANDLES NEGATIVE QUANTITIES FOR RETURN INVOICES
// // // OVERRIDES base_total and total with sum of custom_total from items

// // frappe.ui.form.on("Sales Invoice", {
// //     is_return: function(frm) {
// //         // console.log("IS RETURN")
// //         set_naming_series_based_on_return(frm);
// //     },
// //     refresh: function(frm) {
// //         console.log("Sales Invoice Form Refreshed!");
// //         if (frm.doc.is_return) {
// //             console.log("IS RETURN")
// //             set_naming_series_based_on_return(frm);
// //         }
        
// //         // Add custom button to manually resync calculation table
// //         if (frm.doc.docstatus === 0) {
// //             frm.add_custom_button(__('Resync Calculation Table'), function() {
// //                 frappe.show_alert({
// //                     message: __('Resyncing calculation table...'),
// //                     indicator: 'blue'
// //                 });
// //                 sync_calculation_rows(frm);
// //             });
// //         }
                
// //         // When form loads with is_return=1, sync after delay
// //         // This ensures ERPNext finishes setting negative quantities first
// //         // Use flag to prevent multiple syncs
// //         if (frm.doc.is_return === 1 && !frm._return_synced) {
// //             console.log("Return invoice detected, syncing after delay...");
// //             frm._return_synced = true;
// //             setTimeout(() => {
// //                 sync_calculation_rows(frm);
// //             }, 500);
// //         }
        
// //         // Override base_total and total on refresh
// //         override_totals(frm);
// //     },
    
// //     onload: function(frm) {
// //         // When new return invoice is created via button, sync after longer delay
// //         if (frm.doc.is_return === 1 && frm.is_new() && !frm._return_synced) {
// //             console.log("New return invoice, waiting for negative qty to be set...");
// //             frm._return_synced = true;
// //             setTimeout(() => {
// //                 sync_calculation_rows(frm);
// //             }, 1000);
// //         }
// //     },
    
// //     items_on_form_rendered: function(frm) {
// //         // Only sync if not already synced for return invoices
// //         if (frm.doc.is_return === 1) {
// //             if (!frm._items_rendered_synced) {
// //                 frm._items_rendered_synced = true;
// //                 setTimeout(() => sync_calculation_rows(frm), 500);
// //             }
// //         } else {
// //             sync_calculation_rows(frm);
// //         }
// //     },
    
// //     is_return: function(frm) {
// //         // When is_return checkbox is toggled, re-sync
// //         console.log("is_return changed to:", frm.doc.is_return);
// //         frm._return_synced = false;
// //         frm._items_rendered_synced = false;
// //         setTimeout(() => {
// //             sync_calculation_rows(frm);
// //         }, 500);
// //     },
    
// //     // Trigger when price list changes
// //     selling_price_list: function(frm) {
// //         refresh_all_calculation_prices(frm);
// //     },
    
// //     // Recalculate when base_total changes
// //     base_total: function(frm) {
// //         override_totals(frm);
// //         calculate_total(frm);
// //     },
    
// //     total: function(frm) {
// //         override_totals(frm);
// //     },
    
// //     base_total_taxes_and_charges: function(frm) {
// //         calculate_total(frm);
// //     },
    
// //     base_grand_total: function(frm) {
// //         console.log("Base Grand Total changed");
// //         calculate_total(frm);
// //     },
    
// //     taxes_and_charges: function(frm) {
// //         console.log("Taxes and Charges changed");
// //         calculate_total(frm);
// //     },
    
// //     total_advance: function(frm) {
// //         console.log("Total Advance changed");
// //         calculate_total(frm);
// //     },
    
// //     outstanding_amount: function(frm) {
// //         console.log("Outstanding Amount changed");
// //         update_payment_schedule(frm);
// //     },
    
// //     before_save: function(frm) {
// //         // Override totals before saving
// //         override_totals(frm);
// //     },
// //     // validate: function(frm) {
// //     //     override_totals(frm);
// //     // }
// // });

// // frappe.ui.form.on("Sales Invoice Item", {
// //     item_code: async function(frm, cdt, cdn) {
// //         let row = locals[cdt][cdn];
// //         if (row && row.item_code) {
// //             try {
// //                 const item_check = await frappe.call({
// //                     method: "frappe.client.get_value",
// //                     args: {
// //                         doctype: "Item",
// //                         filters: { name: row.item_code },
// //                         fieldname: "item_name"
// //                     }
// //                 });
                
// //                 if (!item_check.message) {
// //                     return;
// //                 }
                
// //                 let custom_excise_duty = 0;
// //                 try {
// //                     const item_r = await frappe.call({
// //                         method: "frappe.client.get_value",
// //                         args: {
// //                             doctype: "Item",
// //                             filters: { name: row.item_code },
// //                             fieldname: "custom_excise_duty"
// //                         }
// //                     });
// //                     custom_excise_duty = item_r.message ? flt(item_r.message.custom_excise_duty || 0) : 0;
// //                     console.log(`Excise duty for ${row.item_code}: ${custom_excise_duty}`);
// //                 } catch(e) {
// //                     console.error("Error fetching item details:", e);
// //                 }

// //                 await frappe.model.set_value(cdt, cdn, 'custom_excise_duty', custom_excise_duty);
                
// //                 // Wait for ERPNext to finish processing then update values
// //                 setTimeout(() => {
// //                     update_item_values(frm, cdt, cdn);
// //                 }, 500);
                
// //             } catch(e) {
// //                 const errorMsg = e.message || JSON.stringify(e) || 'Unknown error';
// //                 console.error(`Error for ${row.item_code}:`, errorMsg);
// //                 console.error("Error in item_code handler:", e);
// //             }
// //         }
        
// //         // Delay to ensure ERPNext finishes its processing
// //         setTimeout(() => {
// //             sync_calculation_rows(frm);
// //             override_totals(frm);
// //         }, 800);
// //     },

// //     qty: function(frm, cdt, cdn) {
// //         // Update excise calculations when qty changes
// //         setTimeout(() => {
// //             update_item_values(frm, cdt, cdn);
// //             override_totals(frm);
// //             sync_calculation_rows(frm);
// //         }, 300);
// //     },
    
// //     amount: function(frm, cdt, cdn) {
// //         // Update excise calculations when amount changes
// //         setTimeout(() => {
// //             update_item_values(frm, cdt, cdn);
// //             override_totals(frm);
// //         }, 300);
// //     },
    
// //     rate: function(frm, cdt, cdn) {
// //         // Update excise calculations when rate changes
// //         setTimeout(() => {
// //             update_item_values(frm, cdt, cdn);
// //             override_totals(frm);
// //         }, 300);
// //     },
    
// //     custom_excise_duty: function(frm, cdt, cdn) {
// //         // Update when excise duty changes
// //         setTimeout(() => {
// //             update_item_values(frm, cdt, cdn);
// //             override_totals(frm);
// //         }, 300);
// //     },
    
// //     custom_total: function(frm, cdt, cdn) {
// //         // Override totals when custom_total changes
// //         setTimeout(() => {
// //             override_totals(frm);
// //         }, 300);
// //     },
    
// //     uom: function(frm, cdt, cdn) {
// //         setTimeout(() => {
// //             sync_calculation_rows(frm);
// //             override_totals(frm);
// //         }, 300);
// //     },

// //     items_remove: function(frm) {
// //         console.log("Item Removed");
// //         sync_calculation_rows_remove(frm);
// //         setTimeout(() => {
// //             override_totals(frm);
// //         }, 300);
// //     },
    
// //     items_add: function(frm) {
// //         console.log("Item Added");
// //         setTimeout(() => {
// //             sync_calculation_rows(frm);
// //             override_totals(frm);
// //         }, 300);
// //     }
// // });

// // /**
// //  * Override base_total and total with sum of custom_total from items
// //  */
// // function override_totals(frm) {
// //     if (!frm || !frm.doc || !frm.doc.items) {
// //         return;
// //     }
    
// //     let sum_custom_total = 0;
// //     let conversion_rate = flt(frm.doc.conversion_rate) || 1;
    
// //     // Calculate sum of custom_total from all items
// //     frm.doc.items.forEach(function(item) {
// //         let custom_total = flt(item.custom_total) || 0;
// //         sum_custom_total += custom_total;
// //     });
    
// //     // Round to 2 decimal places
// //     sum_custom_total = flt(sum_custom_total, 2);
    
// //     // Calculate total in foreign currency
// //     let total = flt(sum_custom_total / conversion_rate, 2);
    
// //     console.log(`Overriding Totals - Sum of custom_total: ${sum_custom_total}, Conversion Rate: ${conversion_rate}, Total: ${total}`);
    
// //     // Set base_total and total
// //     frm.doc.base_total = sum_custom_total;
// //     frm.doc.total = total;
    
// //     // Refresh the fields to show updated values
// //     frm.refresh_field('base_total');
// //     frm.refresh_field('total');
    
// //     // Trigger recalculation of grand total
// //     setTimeout(() => {
// //         frm.trigger('calculate_taxes_and_totals');
// //     }, 100);
// // }

// // function update_item_values(frm, cdt, cdn) {
// //     let row = locals[cdt][cdn];
    
// //     if (!row) {
// //         console.log("Row not found in update_item_values");
// //         return;
// //     }
    
// //     let qty = flt(row.qty) || 0;
// //     let amount = flt(row.amount) || 0;
// //     const custom_excise_duty = flt(row.custom_excise_duty) || 0;

// //     let custom_excise_value = flt(custom_excise_duty * qty, 2);
// //     let custom_total = flt(amount + custom_excise_value, 2);

// //     console.log(`Calculating for ${row.item_code}: qty=${qty}, amount=${amount}, excise_duty=${custom_excise_duty}`);
// //     console.log(`Results: excise_value=${custom_excise_value}, total=${custom_total}`);

// //     // Use frappe.model.set_value for child table fields
// //     frappe.model.set_value(cdt, cdn, 'custom_excise_value', custom_excise_value)
// //         .then(() => {
// //             return frappe.model.set_value(cdt, cdn, 'custom_total', custom_total);
// //         })
// //         .then(() => {
// //             console.log(`Updated values for ${row.item_code}: Excise Value=${custom_excise_value}, Total=${custom_total}`);
// //             frm.refresh_field('items');
// //             // Override totals after updating item values
// //             setTimeout(() => {
// //                 override_totals(frm);
// //             }, 200);
// //         })
// //         .catch((err) => {
// //             console.error("Error setting values:", err);
// //         });
// // }

// // frappe.ui.form.on("Amount Calculation for sales invoice", {
// //     item_code: function(frm, cdt, cdn) {
// //         fetch_custom_item_price(frm, cdt, cdn);
// //     },
    
// //     uom: function(frm, cdt, cdn) {
// //         fetch_custom_item_price(frm, cdt, cdn);
// //     },
    
// //     qty: function(frm, cdt, cdn) {
// //         // Recalculate amount when qty changes (supports negative qty)
// //         calculate_amount(cdt, cdn);
// //     },
    
// //     custom_total_vat_inclusive: function(frm, cdt, cdn) {
// //         // Recalculate amount when price changes
// //         calculate_amount(cdt, cdn);
// //     },
    
// //     custom_difference_calculation_table_add: function(frm, cdt, cdn) {
// //         console.log("Manual row added");
// //     },
    
// //     custom_difference_calculation_table_remove: function(frm) {
// //         console.log("Removed Rows!!!");
// //         calculate_total(frm);
// //     }
// // });

// // /**
// //  * Sync calculation rows with Sales Invoice Items
// //  * PROPERLY PRESERVES NEGATIVE QUANTITIES AND PREVENTS DUPLICATES
// //  */
// // function sync_calculation_rows(frm) {
// //     const items = frm.doc.items || [];
    
// //     if (items.length === 0) {
// //         frm.clear_table("custom_difference_calculation_table");
// //         frm.refresh_field("custom_difference_calculation_table");
// //         calculate_total(frm);
// //         return;
// //     }

// //     const calculation_table = frm.doc.custom_difference_calculation_table || [];
    
// //     // First, remove any rows that don't have a linked_item or have invalid linked_item
// //     const valid_item_names = items.map(i => i.name);
// //     const rows_to_remove = [];
    
// //     calculation_table.forEach(row => {
// //         if (!row.linked_item || !valid_item_names.includes(row.linked_item)) {
// //             rows_to_remove.push(row);
// //         }
// //     });
    
// //     // Remove invalid rows
// //     rows_to_remove.forEach(row => {
// //         const idx = frm.doc.custom_difference_calculation_table.indexOf(row);
// //         if (idx > -1) {
// //             frm.doc.custom_difference_calculation_table.splice(idx, 1);
// //         }
// //     });
    
// //     // Now sync valid items
// //     items.forEach((item, index) => {
// //         let calc_row = frm.doc.custom_difference_calculation_table.find(r => r.linked_item === item.name);
        
// //         if (!calc_row) {
// //             calc_row = frm.add_child("custom_difference_calculation_table");
// //             calc_row.linked_item = item.name;
// //         }
        
// //         // Get fresh data from locals - CRITICAL for return invoices
// //         let item_data = locals['Sales Invoice Item'][item.name];
        
// //         // Try multiple sources to get the correct qty
// //         let item_qty;
// //         if (item_data && item_data.qty !== undefined) {
// //             item_qty = item_data.qty;
// //         } else if (item.qty !== undefined) {
// //             item_qty = item.qty;
// //         } else {
// //             item_qty = 0;
// //         }
        
// //         // For return invoices, ensure qty is negative
// //         if (frm.doc.is_return === 1 && item_qty > 0) {
// //             console.warn(`Return invoice but qty is positive for ${item.item_code}, making it negative`);
// //             item_qty = -Math.abs(item_qty);
// //         }
        
// //         console.log(`Syncing ${item.item_code}: qty=${item_qty}, is_return=${frm.doc.is_return}, linked=${item.name}`);
        
// //         // Set basic fields
// //         calc_row.item_code = item.item_code;
// //         calc_row.uom = item.uom;
// //         calc_row.idx = index + 1;
        
// //         // Set qty without any transformation
// //         // Direct assignment to locals to preserve negative sign
// //         let calc_row_data = locals['Amount Calculation for sales invoice'][calc_row.name];
// //         if (calc_row_data) {
// //             calc_row_data.qty = item_qty;
// //         } else {
// //             // Fallback if locals not ready yet
// //             calc_row.qty = item_qty;
// //         }
// //     });

// //     // Ensure we only have one row per item
// //     const seen_items = new Set();
// //     const final_rows = [];
    
// //     frm.doc.custom_difference_calculation_table.forEach(row => {
// //         if (row.linked_item && !seen_items.has(row.linked_item)) {
// //             seen_items.add(row.linked_item);
// //             final_rows.push(row);
// //         }
// //     });
    
// //     // Replace the table with deduplicated rows
// //     frm.doc.custom_difference_calculation_table = final_rows;
// //     frm.refresh_field("custom_difference_calculation_table");
    
// //     // Fetch prices and calculate after a delay
// //     setTimeout(() => {
// //         fetch_all_calculation_prices(frm);
// //     }, 200);
// // }

// // /**
// //  * Remove calculation rows when items are removed
// //  */
// // function sync_calculation_rows_remove(frm) {
// //     const items = frm.doc.items || [];
// //     const calculation_rows = frm.doc.custom_difference_calculation_table || [];
// //     const valid_item_names = items.map(i => i.name);

// //     calculation_rows.slice().reverse().forEach(row => {
// //         if (row.linked_item && !valid_item_names.includes(row.linked_item)) {
// //             const grid = frm.get_field("custom_difference_calculation_table").grid;
// //             const row_obj = grid.grid_rows_by_docname[row.name];
            
// //             if (row_obj) {
// //                 row_obj.remove();
// //             } else {
// //                 const idx = frm.doc.custom_difference_calculation_table.indexOf(row);
// //                 if (idx > -1) {
// //                     frm.doc.custom_difference_calculation_table.splice(idx, 1);
// //                 }
// //             }
// //         }
// //     });

// //     sync_calculation_rows(frm);
// //     frm.refresh_field("custom_difference_calculation_table");
// //     calculate_total(frm);
// // }

// // /**
// //  * Fetch custom_total_vat_inclusive from Item Price
// //  */
// // function fetch_custom_item_price(frm, cdt, cdn) {
// //     const row = locals[cdt][cdn];
    
// //     if (!row.item_code) {
// //         console.log("No item_code, skipping price fetch");
// //         return;
// //     }
    
// //     const uom = row.uom;
// //     const price_list = frm.doc.selling_price_list;
    
// //     if (!price_list) {
// //         frappe.msgprint(__('Please select a Price List first'), 'Warning');
// //         return;
// //     }
    
// //     // Use absolute value of qty for price lookup (prices are always positive)
// //     const qty_for_lookup = Math.abs(row.qty || 1);
    
// //     frappe.call({
// //         method: 'avinashgroup_app.custom_code.override_rounding.get_custom_amount',
// //         args: {
// //             customer: frm.doc.customer || '',
// //             price_list: price_list,
// //             item_code: row.item_code,
// //             qty: qty_for_lookup,
// //             uom: uom
// //         },
// //         callback: function(r) {
// //             if (r.message && r.message.price !== undefined) {
// //                 // Set price using direct assignment to avoid validation issues
// //                 let row_data = locals[cdt][cdn];
// //                 row_data.custom_total_vat_inclusive = r.message.price;
// //                 row_data.base_custom_total_vat_inclusive = r.message.price;
                
// //                 console.log(`Fetched price for ${row.item_code} (${row.uom}): ${r.message.price}`);
                
// //                 frm.refresh_field("custom_difference_calculation_table");
                
// //                 // Calculate amount after price is set
// //                 setTimeout(function() {
// //                     calculate_amount(cdt, cdn);
// //                 }, 100);
// //             } else {
// //                 let row_data = locals[cdt][cdn];
// //                 row_data.custom_total_vat_inclusive = 0;
// //                 row_data.base_custom_total_vat_inclusive = 0;
// //                 frm.refresh_field("custom_difference_calculation_table");
// //             }
// //         },
// //         error: function(r) {
// //             let row_data = locals[cdt][cdn];
// //             row_data.custom_total_vat_inclusive = 0;
// //             frappe.msgprint(__('Error fetching price for item {0}', [row.item_code]), 'Error');
// //         }
// //     });
// // }

// // /**
// //  * Fetch prices for all calculation rows
// //  */
// // function fetch_all_calculation_prices(frm) {
// //     const calculation_rows = frm.doc.custom_difference_calculation_table || [];
    
// //     if (calculation_rows.length === 0) {
// //         return;
// //     }
    
// //     const price_list = frm.doc.selling_price_list;
    
// //     if (!price_list) {
// //         console.log("No price list selected");
// //         return;
// //     }
    
// //     calculation_rows.forEach(row => {
// //         if (row.item_code) {
// //             fetch_custom_item_price(frm, row.doctype, row.name);
// //         }
// //     });
// // }

// // /**
// //  * Refresh prices when price list changes
// //  */
// // function refresh_all_calculation_prices(frm) {
// //     const calculation_rows = frm.doc.custom_difference_calculation_table || [];
    
// //     if (calculation_rows.length === 0) {
// //         return;
// //     }
    
// //     frappe.confirm(
// //         __('Do you want to refresh prices for all items based on the new Price List?'),
// //         function() {
// //             fetch_all_calculation_prices(frm);
// //         },
// //         function() {
// //             console.log("Price refresh cancelled");
// //         }
// //     );
// // }

// // /**
// //  * Calculate total amount for a single row
// //  * Formula: total_amount = qty * custom_total_vat_inclusive
// //  * PRESERVES NEGATIVE VALUES FOR RETURNS
// //  */
// // function calculate_amount(cdt, cdn) {
// //     console.log("Calculating amount for row");
    
// //     let row = locals[cdt][cdn];
    
// //     if (!row) {
// //         console.log("Row not found");
// //         return;
// //     }
    
// //     // Get qty preserving its sign (negative for returns)
// //     let qty = parseFloat(row.qty) || 0;
// //     let price = parseFloat(row.custom_total_vat_inclusive) || 0;
    
// //     // Calculate total (will be negative if qty is negative)
// //     let total_amount = qty * price;
    
// //     console.log(`Row ${row.idx}: Qty=${qty}, Price=${price}, Total=${total_amount}`);
    
// //     // Direct assignment to avoid validation
// //     row.total_amount = total_amount;
// //     row.base_total_amount = total_amount;
    
// //     // Recalculate grand total
// //     setTimeout(function() {
// //         calculate_total(cur_frm);
// //     }, 100);
// // }

// // /**
// //  * Calculate totals and update outstanding amount
// //  */
// // function calculate_total(frm) {
// //     if (!frm || !frm.doc) {
// //         console.log("Form not available");
// //         return;
// //     }
    
// //     let custom_total_amount = 0;
// //     let base_total = flt(frm.doc.base_total) || 0;
// //     let base_grand_total = flt(frm.doc.base_grand_total) || 0;
// //     let rounded_total = flt(frm.doc.rounded_total) || 0;
// //     let total_advance = flt(frm.doc.total_advance) || 0;

// //     // Sum up all row totals (including negative for returns)
// //     if (frm.doc.custom_difference_calculation_table) {
// //         frm.doc.custom_difference_calculation_table.forEach(function(row) {
// //             let row_total = parseFloat(row.total_amount) || 0;
// //             custom_total_amount += row_total;
// //             console.log(`  Row ${row.idx}: ${row.item_code} = ${row_total}`);
// //         });
// //     }
    
// //     // Round to 2 decimal places
// //     custom_total_amount = flt(custom_total_amount, 2);
    
// //     // Calculate difference: custom_total_amount - base_grand_total
// //     let difference = flt(custom_total_amount - base_grand_total, 2);
    
// //     // Calculate outstanding: rounded_total - total_advance
// //     let outstanding = flt(rounded_total - total_advance, 2);
    
// //     console.log(`Totals - Custom: ${custom_total_amount}, Base Grand: ${base_grand_total}, Difference: ${difference}, Outstanding: ${outstanding}`);
    
// //     // Set values without triggering events
// //     frm.doc.custom_total_amount = custom_total_amount;
// //     frm.doc.custom_difference_adjustment = difference;
// //     frm.doc.outstanding_amount = outstanding;
    
// //     // Refresh fields
// //     frm.refresh_field('custom_total_amount');
// //     frm.refresh_field('custom_difference_adjustment');
// //     frm.refresh_field('outstanding_amount');
    
// //     // Update payment schedule with outstanding amount
// //     update_payment_schedule(frm);
    
// //     // Convert rounded total to words via server call
// //     convert_rounded_total_to_words(frm);
// // }

// // /**
// //  * Update payment schedule with outstanding amount
// //  */
// // function update_payment_schedule(frm) {
// //     if (!frm || !frm.doc || !frm.doc.payment_schedule || frm.doc.payment_schedule.length === 0) {
// //         console.log("No payment schedule to update");
// //         return;
// //     }
    
// //     let outstanding = flt(frm.doc.outstanding_amount) || 0;
// //     let conversion_rate = flt(frm.doc.conversion_rate) || 1;
    
// //     console.log(`Updating payment schedule with outstanding: ${outstanding}`);
    
// //     // Update the first payment schedule row (or all rows based on your requirement)
// //     if (frm.doc.payment_schedule.length === 1) {
// //         // Single payment schedule - set to outstanding amount
// //         let row = frm.doc.payment_schedule[0];
// //         frappe.model.set_value(row.doctype, row.name, 'base_payment_amount', outstanding);
// //         frappe.model.set_value(row.doctype, row.name, 'payment_amount', flt(outstanding / conversion_rate, 2));
// //     } else if (frm.doc.payment_schedule.length > 1) {
// //         // Multiple payment schedules - update first row
// //         let row = frm.doc.payment_schedule[0];
// //         frappe.model.set_value(row.doctype, row.name, 'base_payment_amount', outstanding);
// //         frappe.model.set_value(row.doctype, row.name, 'payment_amount', flt(outstanding / conversion_rate, 2));
// //     }
    
// //     frm.refresh_field('payment_schedule');
// //     console.log("Payment schedule updated successfully");
// // }

// // /**
// //  * Convert rounded total (base_grand_total + base_rounding_adjustment) to words
// //  */
// // function convert_rounded_total_to_words(frm) {
// //     if (!frm || !frm.doc) {
// //         return;
// //     }
    
// //     // Calculate rounded total
// //     let base_grand_total = flt(frm.doc.base_grand_total) || 0;
// //     let base_rounding_adjustment = flt(frm.doc.custom_difference_adjustment) || 0;
// //     let rounded_total = base_grand_total + base_rounding_adjustment;
    
// //     // Get currency from the document
// //     let currency = frm.doc.currency || frappe.defaults.get_default("currency");
    
// //     // Call server method to convert to words
// //     frappe.call({
// //         method: 'avinashgroup_app.custom_code.override_rounding.convert_amount_to_words',
// //         args: {
// //             amount: rounded_total,
// //             currency: currency
// //         },
// //         callback: function(r) {
// //             if (r.message) {
// //                 frm.set_value('base_in_words', r.message);
// //                 frm.refresh_field('base_in_words');
// //                 console.log(`Converted ${rounded_total} to words: ${r.message}`);
// //             }
// //         },
// //         error: function(r) {
// //             console.log("Error converting amount to words");
// //         }
// //     });
// // }

// // // RETURN CASE 
// // function set_naming_series_based_on_return(frm) {
// //     if (frm.doc.is_return == 1) {
// //         // Set the return naming series
// //         frm.set_value('naming_series', 'ACC-SINV-RET-.{custom_company_abbr}.-.YYYY.-');
// //     } else {
// //         // Set the normal naming series
// //         frm.set_value('naming_series', 'ACC-SINV-.{custom_company_abbr}.-.YYYY.-');
// //     }
// // }
// // // PROPERLY HANDLES NEGATIVE QUANTITIES FOR RETURN INVOICES

// frappe.ui.form.on("Sales Invoice", {
//      is_return: function(frm) {
//         // console.log("IS RETURN")
//         set_naming_series_based_on_return(frm);
//     },
//     refresh: function(frm) {
//         console.log("Sales Invoice Form Refreshed!");
//         if (frm.doc.is_return) {
//             console.log("IS RETURN")
//             set_naming_series_based_on_return(frm);
//         }
        
//         // Add custom button to manually resync calculation table
//         if (frm.doc.docstatus === 0) {
//             frm.add_custom_button(__('Resync Calculation Table'), function() {
//                 frappe.show_alert({
//                     message: __('Resyncing calculation table...'),
//                     indicator: 'blue'
//                 });
//                 sync_calculation_rows(frm);
//             });
//         }
                
//         // When form loads with is_return=1, sync after delay
//         // This ensures ERPNext finishes setting negative quantities first
//         // Use flag to prevent multiple syncs
//         if (frm.doc.is_return === 1 && !frm._return_synced) {
//             console.log("Return invoice detected, syncing after delay...");
//             frm._return_synced = true;
//             setTimeout(() => {
//                 sync_calculation_rows(frm);
//             }, 500);
//         }
//     },
    
//     onload: function(frm) {
//         // When new return invoice is created via button, sync after longer delay
//         if (frm.doc.is_return === 1 && frm.is_new() && !frm._return_synced) {
//             console.log("New return invoice, waiting for negative qty to be set...");
//             frm._return_synced = true;
//             setTimeout(() => {
//                 sync_calculation_rows(frm);
//             }, 1000);
//         }
//     },
    
//     items_on_form_rendered: function(frm) {
//         // Only sync if not already synced for return invoices
//         if (frm.doc.is_return === 1) {
//             if (!frm._items_rendered_synced) {
//                 frm._items_rendered_synced = true;
//                 setTimeout(() => sync_calculation_rows(frm), 500);
//             }
//         } else {
//             sync_calculation_rows(frm);
//         }
//     },
    
//     is_return: function(frm) {
//         // When is_return checkbox is toggled, re-sync
//         console.log("is_return changed to:", frm.doc.is_return);
//         frm._return_synced = false;
//         frm._items_rendered_synced = false;
//         setTimeout(() => {
//             sync_calculation_rows(frm);
//         }, 500);
//     },
    
//     // Trigger when price list changes
//     selling_price_list: function(frm) {
//         refresh_all_calculation_prices(frm);
//     },
    
//     // Recalculate when base_total changes
//     base_total: function(frm) {
//         calculate_total(frm);
//     },
    
//     base_total_taxes_and_charges: function(frm) {
//         calculate_total(frm);
//     },
    
//     base_grand_total: function(frm) {
//         console.log("Base Grand Total changed");
//         calculate_total(frm);
//     },
    
//     taxes_and_charges: function(frm) {
//         console.log("Taxes and Charges changed");
//         calculate_total(frm);
//     },
    
//     total_advance: function(frm) {
//         console.log("Total Advance changed");
//         calculate_total(frm);
//     },
    
//     outstanding_amount: function(frm) {
//         console.log("Outstanding Amount changed");
//         update_payment_schedule(frm);
//     }
// });

// frappe.ui.form.on("Sales Invoice Item", {
//     item_code: async function(frm, cdt, cdn) {
//         // Delay to ensure ERPNext finishes its processing
//         setTimeout(() => sync_calculation_rows(frm), 300);
//         let row = locals[cdt][cdn];
//         if (row && row.item_code) {
//           try{
//             const item_check = await frappe.call({
//                     method: "frappe.client.get_value",
//                     args: {
//                         doctype: "Item",
//                         filters: { name: row.item_code },
//                         fieldname: "item_name"
//                     }
//                 });
//                 if (!item_check.message) {
//                     return;
//                 }
//                 let custom_excise_duty = 0
//                 try{
//                     const item_r=await frappe.call({
//                         method: "frappe.client.get_value",
//                         args: {
//                             doctype: "Item",
//                             filters: { name: row.item_code },
//                             fieldname: "custom_excise_duty"
//                         }
//                     });
//                     excise_duty = item_r.message ? flt(item_r.message.custom_excise_duty || 0) : 0;
//                     console.log(`Excise duty for ${row.item_code}: ${excise_duty}`);

//                 }catch(e){
//                     console.error("Error fetching item details:", e);
//                 }
//                 // await frappe.model.set_value(cdt, cdn, "custom_excise_duty", custom_excise_duty);
               

//                 await frappe.model.set_value(cdt, cdn, 'custom_excise_duty', excise_duty);
//                 // await frappe.model.set_value(cdt, cdn, 'custom_excise_value',  * row.qty);
//                 // await frappe.model.set_value(cdt, cdn, 'custom_total', row.amount + (custom_excise_duty * row.qty));
                
//                 //calculate values of total 
//                 await update_item_values(frm, cdt, cdn);
//           }catch(e){
//             const errorMsg = e.message || JSON.stringify(e) || 'Unknown error';
//             console.error(`Error for ${row.item_code}:`, errorMsg);
//             await update_item_values(frm, cdt, cdn);
//             console.error("Error in item_code handler:", e);
//           }
//         }
//     },

//     qty: function(frm, cdt, cdn) {
//         // Delay to ensure qty is fully updated
//         setTimeout(() => sync_calculation_rows(frm), 300);
//     },
    
//     uom: function(frm, cdt, cdn) {
//         setTimeout(() => sync_calculation_rows(frm), 300);
//     },

//     items_remove: function(frm) {
//         console.log("Item Removed");
//         sync_calculation_rows_remove(frm);
//     },
    
//     items_add: function(frm) {
//         console.log("Item Added");
//         setTimeout(() => sync_calculation_rows(frm), 300);
//     }
// });

// function update_item_values(frm, cdt, cdn) {
//     let row = locals[cdt][cdn];
//     let qty = flt(row.qty) || 0;
//     let amount = flt(row.amount) || 0;
//     const custom_excise_duty = flt(row.custom_excise_duty) || 1;

//     let custom_excise_value = flt(custom_excise_duty * qty);
//     let custom_total = flt(amount + custom_excise_value);

//     // FIXED: Use frappe.model.set_value for child table fields
//     frappe.model.set_value(cdt, cdn, 'custom_excise_value', custom_excise_value);
//     frappe.model.set_value(cdt, cdn, 'custom_total', custom_total);
//     console.log(`Updated values for ${row.item_code}: Excise Value=${custom_excise_value}, Total=${custom_total}`);
// }

// frappe.ui.form.on("Amount Calculation for sales invoice", {
//     item_code: function(frm, cdt, cdn) {
//         fetch_custom_item_price(frm, cdt, cdn);
//     },
    
//     uom: function(frm, cdt, cdn) {
//         fetch_custom_item_price(frm, cdt, cdn);
//     },
    
//     qty: function(frm, cdt, cdn) {
//         // Recalculate amount when qty changes (supports negative qty)
//         calculate_amount(cdt, cdn);
//     },
    
//     custom_total_vat_inclusive: function(frm, cdt, cdn) {
//         // Recalculate amount when price changes
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

// /**
//  * Sync calculation rows with Sales Invoice Items
//  * PROPERLY PRESERVES NEGATIVE QUANTITIES AND PREVENTS DUPLICATES
//  */

// function sync_calculation_rows(frm) {
//     const items = frm.doc.items || [];
    
//     if (items.length === 0) {
//         frm.clear_table("custom_difference_calculation_table");
//         frm.refresh_field("custom_difference_calculation_table");
//         calculate_total(frm);
//         return;
//     }

//     const calculation_table = frm.doc.custom_difference_calculation_table || [];
    
//     // First, remove any rows that don't have a linked_item or have invalid linked_item
//     const valid_item_names = items.map(i => i.name);
//     const rows_to_remove = [];
    
//     calculation_table.forEach(row => {
//         if (!row.linked_item || !valid_item_names.includes(row.linked_item)) {
//             rows_to_remove.push(row);
//         }
//     });
    
//     // Remove invalid rows
//     rows_to_remove.forEach(row => {
//         const idx = frm.doc.custom_difference_calculation_table.indexOf(row);
//         if (idx > -1) {
//             frm.doc.custom_difference_calculation_table.splice(idx, 1);
//         }
//     });
    
//     // Now sync valid items
//     items.forEach((item, index) => {
//         let calc_row = frm.doc.custom_difference_calculation_table.find(r => r.linked_item === item.name);
        
//         if (!calc_row) {
//             calc_row = frm.add_child("custom_difference_calculation_table");
//             calc_row.linked_item = item.name;
//         }
        
//         // Get fresh data from locals - CRITICAL for return invoices
//         let item_data = locals['Sales Invoice Item'][item.name];
        
//         // Try multiple sources to get the correct qty
//         let item_qty;
//         if (item_data && item_data.qty !== undefined) {
//             item_qty = item_data.qty;
//         } else if (item.qty !== undefined) {
//             item_qty = item.qty;
//         } else {
//             item_qty = 0;
//         }
        
//         // For return invoices, ensure qty is negative
//         if (frm.doc.is_return === 1 && item_qty > 0) {
//             console.warn(`Return invoice but qty is positive for ${item.item_code}, making it negative`);
//             item_qty = -Math.abs(item_qty);
//         }
        
//         console.log(`Syncing ${item.item_code}: qty=${item_qty}, is_return=${frm.doc.is_return}, linked=${item.name}`);
        
//         // Set basic fields
//         calc_row.item_code = item.item_code;
//         calc_row.uom = item.uom;
//         calc_row.idx = index + 1;
        
//         // Set qty without any transformation
//         // Direct assignment to locals to preserve negative sign
//         let calc_row_data = locals['Amount Calculation for sales invoice'][calc_row.name]; // locals[cdt][cdn]
//         if (calc_row_data) {
//             calc_row_data.qty = item_qty;
//         } else {
//             // Fallback if locals not ready yet
//             calc_row.qty = item_qty;
//         }
//     });

//     // Ensure we only have one row per item
//     const seen_items = new Set();
//     const final_rows = [];
    
//     frm.doc.custom_difference_calculation_table.forEach(row => {
//         if (row.linked_item && !seen_items.has(row.linked_item)) {
//             seen_items.add(row.linked_item);
//             final_rows.push(row);
//         }
//     });
    
//     // Replace the table with deduplicated rows
//     frm.doc.custom_difference_calculation_table = final_rows;
//     frm.refresh_field("custom_difference_calculation_table");
    
//     // Fetch prices and calculate after a delay
//     setTimeout(() => {
//         fetch_all_calculation_prices(frm);
//     }, 200);
// }

// /**
//  * Remove calculation rows when items are removed
//  */
// function sync_calculation_rows_remove(frm) {
//     const items = frm.doc.items || [];
//     const calculation_rows = frm.doc.custom_difference_calculation_table || [];
//     const valid_item_names = items.map(i => i.name);

//     calculation_rows.slice().reverse().forEach(row => {
//         if (row.linked_item && !valid_item_names.includes(row.linked_item)) {
//             const grid = frm.get_field("custom_difference_calculation_table").grid;
//             const row_obj = grid.grid_rows_by_docname[row.name];
            
//             if (row_obj) {
//                 row_obj.remove();
//             } else {
//                 const idx = frm.doc.custom_difference_calculation_table.indexOf(row);
//                 if (idx > -1) {
//                     frm.doc.custom_difference_calculation_table.splice(idx, 1);
//                 }
//             }
//         }
//     });

//     sync_calculation_rows(frm);
//     frm.refresh_field("custom_difference_calculation_table");
//     calculate_total(frm);
// }

// /**
//  * Fetch custom_total_vat_inclusive from Item Price
//  */
// function fetch_custom_item_price(frm, cdt, cdn) {
//     const row = locals[cdt][cdn];
    
//     if (!row.item_code) {
//         console.log("No item_code, skipping price fetch");
//         return;
//     }
    
//     const uom = row.uom;
//     const price_list = frm.doc.selling_price_list;
    
//     if (!price_list) {
//         frappe.msgprint(__('Please select a Price List first'), 'Warning');
//         return;
//     }
    
//     // Use absolute value of qty for price lookup (prices are always positive)
//     const qty_for_lookup = Math.abs(row.qty || 1);
    
//     frappe.call({
//         method: 'avinashgroup_app.custom_code.override_rounding.get_custom_amount',
//         args: {
//             customer: frm.doc.customer || '',
//             price_list: price_list,
//             item_code: row.item_code,
//             qty: qty_for_lookup,
//             uom: uom
//         },
//         callback: function(r) {
//             if (r.message && r.message.price !== undefined) {
//                 // Set price using direct assignment to avoid validation issues
//                 let row_data = locals[cdt][cdn];
//                 row_data.custom_total_vat_inclusive = r.message.price;
//                 row_data.base_custom_total_vat_inclusive = r.message.price;
                
//                 console.log(`Fetched price for ${row.item_code} (${row.uom}): ${r.message.price}`);
                
//                 frm.refresh_field("custom_difference_calculation_table");
                
//                 // Calculate amount after price is set
//                 setTimeout(function() {
//                     calculate_amount(cdt, cdn);
//                 }, 100);
//             } else {
//                 let row_data = locals[cdt][cdn];
//                 row_data.custom_total_vat_inclusive = 0;
//                 row_data.base_custom_total_vat_inclusive = 0;
//                 frm.refresh_field("custom_difference_calculation_table");
//             }
//         },
//         error: function(r) {
//             let row_data = locals[cdt][cdn];
//             row_data.custom_total_vat_inclusive = 0;
//             frappe.msgprint(__('Error fetching price for item {0}', [row.item_code]), 'Error');
//         }
//     });
// }

// /**
//  * Fetch prices for all calculation rows
//  */
// function fetch_all_calculation_prices(frm) {
//     const calculation_rows = frm.doc.custom_difference_calculation_table || [];
    
//     if (calculation_rows.length === 0) {
//         return;
//     }
    
//     const price_list = frm.doc.selling_price_list;
    
//     if (!price_list) {
//         console.log("No price list selected");
//         return;
//     }
    
//     calculation_rows.forEach(row => {
//         if (row.item_code) {
//             fetch_custom_item_price(frm, row.doctype, row.name);
//         }
//     });
// }

// /**
//  * Refresh prices when price list changes
//  */
// function refresh_all_calculation_prices(frm) {
//     const calculation_rows = frm.doc.custom_difference_calculation_table || [];
    
//     if (calculation_rows.length === 0) {
//         return;
//     }
    
//     frappe.confirm(
//         __('Do you want to refresh prices for all items based on the new Price List?'),
//         function() {
//             fetch_all_calculation_prices(frm);
//         },
//         function() {
//             console.log("Price refresh cancelled");
//         }
//     );
// }

// /**
//  * Calculate total amount for a single row
//  * Formula: total_amount = qty * custom_total_vat_inclusive
//  * PRESERVES NEGATIVE VALUES FOR RETURNS
//  */
// function calculate_amount(cdt, cdn) {
//     console.log("Calculating amount for row");
    
//     let row = locals[cdt][cdn];
    
//     if (!row) {
//         console.log("Row not found");
//         return;
//     }
    
//     // Get qty preserving its sign (negative for returns)
//     let qty = parseFloat(row.qty) || 0;
//     let price = parseFloat(row.custom_total_vat_inclusive) || 0;
    
//     // Calculate total (will be negative if qty is negative)
//     let total_amount = qty * price;
    
//     console.log(`Row ${row.idx}: Qty=${qty}, Price=${price}, Total=${total_amount}`);
    
//     // Direct assignment to avoid validation
//     row.total_amount = total_amount;
//     row.base_total_amount = total_amount;
    
//     // Recalculate grand total
//     setTimeout(function() {
//         calculate_total(cur_frm);
//     }, 100);
// }

// /**
//  * Calculate totals and update outstanding amount
//  */
// function calculate_total(frm) {
//     if (!frm || !frm.doc) {
//         console.log("Form not available");
//         return;
//     }
    
//     let custom_total_amount = 0;
//     let base_total = flt(frm.doc.base_total) || 0;
//     let base_grand_total = flt(frm.doc.base_grand_total) || 0;
//     let rounded_total = flt(frm.doc.rounded_total) || 0;
//     let total_advance = flt(frm.doc.total_advance) || 0;

//     // Sum up all row totals (including negative for returns)
//     if (frm.doc.custom_difference_calculation_table) {
//         frm.doc.custom_difference_calculation_table.forEach(function(row) {
//             let row_total = parseFloat(row.total_amount) || 0;
//             custom_total_amount += row_total;
//             console.log(`  Row ${row.idx}: ${row.item_code} = ${row_total}`);
//         });
//     }
    
//     // Round to 2 decimal places
//     custom_total_amount = flt(custom_total_amount, 2);
    
//     // Calculate difference: custom_total_amount - base_grand_total
//     let difference = flt(custom_total_amount - base_grand_total, 2);
    
//     // Calculate outstanding: rounded_total - total_advance
//     let outstanding = flt(rounded_total - total_advance, 2);
    
//     console.log(`Totals - Custom: ${custom_total_amount}, Base Grand: ${base_grand_total}, Difference: ${difference}, Outstanding: ${outstanding}`);
    
//     // Set values without triggering events
//     frm.doc.custom_total_amount = custom_total_amount;
//     frm.doc.custom_difference_adjustment = difference;
//     frm.doc.outstanding_amount = outstanding;
    
//     // Refresh fields
//     frm.refresh_field('custom_total_amount');
//     frm.refresh_field('custom_difference_adjustment');
//     frm.refresh_field('outstanding_amount');
    
//     // Update payment schedule with outstanding amount
//     update_payment_schedule(frm);
    
//     // Convert rounded total to words via server call
//     convert_rounded_total_to_words(frm);
// }

// /**
//  * Update payment schedule with outstanding amount
//  */
// function update_payment_schedule(frm) {
//     if (!frm || !frm.doc || !frm.doc.payment_schedule || frm.doc.payment_schedule.length === 0) {
//         console.log("No payment schedule to update");
//         return;
//     }
    
//     let outstanding = flt(frm.doc.outstanding_amount) || 0;
//     let conversion_rate = flt(frm.doc.conversion_rate) || 1;
    
//     console.log(`Updating payment schedule with outstanding: ${outstanding}`);
    
//     // Update the first payment schedule row (or all rows based on your requirement)
//     if (frm.doc.payment_schedule.length === 1) {
//         // Single payment schedule - set to outstanding amount
//         let row = frm.doc.payment_schedule[0];
//         frappe.model.set_value(row.doctype, row.name, 'base_payment_amount', outstanding);
//         frappe.model.set_value(row.doctype, row.name, 'payment_amount', flt(outstanding / conversion_rate, 2));
//     } else if (frm.doc.payment_schedule.length > 1) {
//         // Multiple payment schedules - update first row
//         let row = frm.doc.payment_schedule[0];
//         frappe.model.set_value(row.doctype, row.name, 'base_payment_amount', outstanding);
//         frappe.model.set_value(row.doctype, row.name, 'payment_amount', flt(outstanding / conversion_rate, 2));
//     }
    
//     frm.refresh_field('payment_schedule');
//     console.log("Payment schedule updated successfully");
// }

// /**
//  * Convert rounded total (base_grand_total + base_rounding_adjustment) to words
//  */
// function convert_rounded_total_to_words(frm) {
//     if (!frm || !frm.doc) {
//         return;
//     }
    
//     // Calculate rounded total
//     let base_grand_total = flt(frm.doc.base_grand_total) || 0;
//     let base_rounding_adjustment = flt(frm.doc.custom_difference_adjustment) || 0;
//     let rounded_total = base_grand_total + base_rounding_adjustment;
    
//     // Get currency from the document
//     let currency = frm.doc.currency || frappe.defaults.get_default("currency");
    
//     // Call server method to convert to words
//     frappe.call({
//         method: 'avinashgroup_app.custom_code.override_rounding.convert_amount_to_words',
//         args: {
//             amount: rounded_total,
//             currency: currency
//         },
//         callback: function(r) {
//             if (r.message) {
//                 frm.set_value('base_in_words', r.message);
//                 frm.refresh_field('base_in_words');
//                 console.log(`Converted ${rounded_total} to words: ${r.message}`);
//             }
//         },
//         error: function(r) {
//             console.log("Error converting amount to words");
//         }
//     });
// }
// //RETURN CASE 

// function set_naming_series_based_on_return(frm) {
//     if (frm.doc.is_return == 1) {
//         // Set the return naming series
//         frm.set_value('naming_series', 'ACC-SINV-RET-.{custom_company_abbr}.-.YYYY.-');
//     } else {
//         // Set the normal naming series
//         frm.set_value('naming_series', 'ACC-SINV-.{custom_company_abbr}.-.YYYY.-');
//     }
// }



// PROPERLY HANDLES NEGATIVE QUANTITIES FOR RETURN INVOICES
// OVERRIDES base_total with sum of custom_total from items
// PROPERLY CALCULATES EXCISE DUTY AND ROUNDING ADJUSTMENT

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
        
        // Add custom button to manually resync calculation table
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Resync Calculation Table'), function() {
                frappe.show_alert({
                    message: __('Resyncing calculation table...'),
                    indicator: 'blue'
                });
                sync_calculation_rows(frm);
            });
        }
                
        // When form loads with is_return=1, sync after delay
        if (frm.doc.is_return === 1 && !frm._return_synced) {
            console.log("Return invoice detected, syncing after delay...");
            frm._return_synced = true;
            setTimeout(() => {
                sync_calculation_rows(frm);
            }, 500);
        }
    },
    
    onload: function(frm) {
        // When new return invoice is created via button, sync after longer delay
        if (frm.doc.is_return === 1 && frm.is_new() && !frm._return_synced) {
            console.log("New return invoice, waiting for negative qty to be set...");
            frm._return_synced = true;
            setTimeout(() => {
                sync_calculation_rows(frm);
            }, 1000);
        }
    },
    
    items_on_form_rendered: function(frm) {
        // Only sync if not already synced for return invoices
        if (frm.doc.is_return === 1) {
            if (!frm._items_rendered_synced) {
                frm._items_rendered_synced = true;
                setTimeout(() => sync_calculation_rows(frm), 500);
            }
        } else {
            sync_calculation_rows(frm);
        }
    },
    
    // Trigger when price list changes
    selling_price_list: function(frm) {
        refresh_all_calculation_prices(frm);
    },
    
    // Recalculate when totals change
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
    },
    
    total_advance: function(frm) {
        console.log("Total Advance changed");
        calculate_total(frm);
    },
    
    outstanding_amount: function(frm) {
        console.log("Outstanding Amount changed");
        update_payment_schedule(frm);
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

                await frappe.model.set_value(cdt, cdn, 'custom_excise_duty', custom_excise_duty);
                
                // Wait for ERPNext to finish processing
                setTimeout(() => {
                    update_item_values(frm, cdt, cdn);
                    sync_calculation_rows(frm);
                }, 800);
                
            } catch(e) {
                console.error("Error in item_code handler:", e);
            }
        }
    },

    qty: function(frm, cdt, cdn) {
        setTimeout(() => {
            update_item_values(frm, cdt, cdn);
            sync_calculation_rows(frm);
        }, 300);
    },
    
    amount: function(frm, cdt, cdn) {
        setTimeout(() => {
            update_item_values(frm, cdt, cdn);
        }, 300);
    },
    
    rate: function(frm, cdt, cdn) {
        setTimeout(() => {
            update_item_values(frm, cdt, cdn);
        }, 300);
    },
    
    custom_excise_duty: function(frm, cdt, cdn) {
        setTimeout(() => {
            update_item_values(frm, cdt, cdn);
        }, 300);
    },
    
    uom: function(frm, cdt, cdn) {
        setTimeout(() => {
            sync_calculation_rows(frm);
        }, 300);
    },

    items_remove: function(frm) {
        console.log("Item Removed");
        sync_calculation_rows_remove(frm);
    },
    
    items_add: function(frm) {
        console.log("Item Added");
        setTimeout(() => {
            sync_calculation_rows(frm);
        }, 300);
    }
});

/**
 * Update excise values for a single item row
 * This function ONLY updates custom_excise_value and custom_total
 * It does NOT override base_total (Python hooks do that)
 */
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
}

frappe.ui.form.on("Amount Calculation for sales invoice", {
    item_code: function(frm, cdt, cdn) {
        fetch_custom_item_price(frm, cdt, cdn);
    },
    
    uom: function(frm, cdt, cdn) {
        fetch_custom_item_price(frm, cdt, cdn);
    },
    
    qty: function(frm, cdt, cdn) {
        calculate_amount(cdt, cdn);
    },
    
    custom_total_vat_inclusive: function(frm, cdt, cdn) {
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

/**
 * Calculate totals and rounding adjustment
 * This displays the values - actual saving is done by Python hooks
 */
function calculate_total(frm) {
    if (!frm || !frm.doc) {
        console.log("Form not available");
        return;
    }
    
    let custom_total_amount = 0;
    let base_grand_total = flt(frm.doc.base_grand_total) || 0;
    let total_advance = flt(frm.doc.total_advance) || 0;

    // Sum calculation table totals
    if (frm.doc.custom_difference_calculation_table) {
        frm.doc.custom_difference_calculation_table.forEach(function(row) {
            let row_total = parseFloat(row.total_amount) || 0;
            custom_total_amount += row_total;
        });
    }
    
    custom_total_amount = flt(custom_total_amount, 2);
    
    // Calculate difference
    let difference = flt(custom_total_amount - base_grand_total, 2);
    
    // Calculate rounded total
    let rounded_total = flt(base_grand_total + difference, 2);
    
    // Calculate outstanding
    let outstanding = flt(rounded_total - total_advance, 2);
    
    console.log(`Totals - Custom: ${custom_total_amount}, Difference: ${difference}, Rounded: ${rounded_total}, Outstanding: ${outstanding}`);
    
    // Set values (Python hooks will finalize these on save)
    frm.doc.custom_total_amount = custom_total_amount;
    frm.doc.custom_difference_adjustment = difference;
    frm.doc.rounded_total = rounded_total;
    frm.doc.outstanding_amount = outstanding;
    
    frm.refresh_field('custom_total_amount');
    frm.refresh_field('custom_difference_adjustment');
    frm.refresh_field('rounded_total');
    frm.refresh_field('outstanding_amount');
    
    update_payment_schedule(frm);
    convert_rounded_total_to_words(frm);
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
        frm.set_value('naming_series', 'ACC-SINV-RET-.{custom_company_abbr}.-.YYYY.-');
    } else {
        frm.set_value('naming_series', 'ACC-SINV-.{custom_company_abbr}.-.YYYY.-');
    }
}