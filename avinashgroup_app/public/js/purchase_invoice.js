frappe.ui.form.on("Purchase Invoice", {
    
    onload: function(frm) {
        // Apply field visibility for all existing rows on load
        if (frm.doc.items) {
            frm.doc.items.forEach(function(item) {
                toggle_vat_fields(frm, item.doctype, item.name);
            });
        }
    },
    
    refresh: function(frm) {
        // Apply field visibility on refresh
        if (frm.doc.items) {
            frm.doc.items.forEach(function(item) {
                toggle_vat_fields(frm, item.doctype, item.name);
            });
        }
    },
    
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
            calculate_tds_total(frm);
            calculate_total(frm);
        }, 500);
    },
    
    total_advance: function(frm) {
        console.log("Total Advance changed");
        calculate_total(frm);
    },
    
    // When custom_tax_withholding_category_custom changes, recalculate
    // NO need to check apply_tds at invoice level
    custom_tax_withholding_category_custom: function(frm) {
        console.log("Custom Tax Withholding Category changed");
        
        // Fetch TDS rate from CUSTOM Tax Withholding Category and populate in items
        if (frm.doc.custom_tax_withholding_category_custom) {
            populate_tds_rate_from_custom_category(frm);
        }
        
        calculate_tds_total(frm);
    },
    
});

frappe.ui.form.on("Purchase Invoice Item", {
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
                
                // Always set VAT Apply On to Percentage (%) by default FIRST
                await frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'Percentage (%)');
                
                // Fetch item custom fields
                const item_data = await frappe.call({
                    method: "avinashgroup_app.custom_code.purchase_invoice.purchase_invoice_taxes_tds.populate_item_custom_fields",
                    args: {
                        item_code: row.item_code
                    }
                });
                
                if (item_data.message) {
                    // Set excise duty (optional, user can override)
                    if (!row.custom_excise_duty && item_data.message.custom_excise_duty) {
                        await frappe.model.set_value(cdt, cdn, 'custom_excise_duty', item_data.message.custom_excise_duty);
                    }
                    
                    // Set VAT Rate (since we're in Percentage mode by default)
                    if (item_data.message.custom_vat_rate) {
                        await frappe.model.set_value(cdt, cdn, 'custom_vat_rate', item_data.message.custom_vat_rate);
                    }
                    
                    // Set TDS Rate (no longer setting account from item)
                    if (!row.custom_tds_rate && item_data.message.custom_tds_rate) {
                        await frappe.model.set_value(cdt, cdn, 'custom_tds_rate', item_data.message.custom_tds_rate);
                    }
                }
                
                // Apply field visibility
                frappe.after_ajax(() => {
                    toggle_vat_fields(frm, cdt, cdn);
                });
                frm.refresh_field('items');
                
            } catch(e) {
                console.error("Error in item_code handler:", e);
            }
        }
    },

    qty: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log(`Qty changed for ${row.item_code}: ${row.qty}`);
        
        // In Percentage mode, backend will recalculate VAT on save
        // Just refresh the field to show updated values
        frm.refresh_field('items');
    },
    
    base_net_amount: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log(`Base Net Amount changed for ${row.item_code}: ${row.base_net_amount}`);
        
        // Backend will recalculate custom_total and VAT
        frm.refresh_field('items');
    },
    
    base_net_rate: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log(`Base Net Rate changed for ${row.item_code}: ${row.base_net_rate}`);
        
        // Backend will recalculate base_net_amount, custom_total and VAT
        frm.refresh_field('items');
    },
    
    custom_excise_value: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log(`Manual excise value set for ${row.item_code}: ${row.custom_excise_value}`);
        frm.refresh_field('items');
    },
    
    custom_excise_duty: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log(`Excise duty changed for ${row.item_code}: ${row.custom_excise_duty}`);
        frm.refresh_field('items');
    },

    custom_vat_apply_on: async function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        if (row.custom_vat_apply_on === "Percentage (%)") {
            // Clear manual amount
            await frappe.model.set_value(cdt, cdn, "custom_vat_amount", 0);
            
            // Re-fetch VAT rate from Item Tax Template if item exists
            if (row.item_code) {
                try {
                    const item_data = await frappe.call({
                        method: "avinashgroup_app.custom_code.purchase_invoice.purchase_invoice_taxes_tds.populate_item_custom_fields",
                        args: {
                            item_code: row.item_code
                        }
                    });
                    
                    if (item_data.message && item_data.message.custom_vat_rate) {
                        await frappe.model.set_value(cdt, cdn, 'custom_vat_rate', item_data.message.custom_vat_rate);
                        console.log(`Re-fetched VAT rate for ${row.item_code}: ${item_data.message.custom_vat_rate}%`);
                    }
                } catch(e) {
                    console.error("Error re-fetching VAT rate:", e);
                }
            }
        }

        if (row.custom_vat_apply_on === "Amount") {
            // Clear rate when switching to Amount mode
            frappe.model.set_value(cdt, cdn, "custom_vat_rate", 0);
        }

        frappe.after_ajax(() => {
            toggle_vat_fields(frm, cdt, cdn);
        });
    },

    custom_vat_rate: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row && row.custom_vat_apply_on === 'Percentage (%)') {
            console.log(`VAT rate changed for ${row.item_code}: ${row.custom_vat_rate}%`);
            // Backend will recalculate VAT amount on save
        }
        frm.refresh_field('items');
    },
    
    custom_vat_amount: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row && row.custom_vat_apply_on === 'Amount') {
            console.log(`Manual VAT amount set for ${row.item_code}: ${row.custom_vat_amount}`);
        }
        frm.refresh_field('items');
    },
    
    custom_tds_rate: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log(`TDS rate changed for ${row.item_code}: ${row.custom_tds_rate}%`);
        frm.refresh_field('items');
    },
    
    custom_tds_amount: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log(`Manual TDS amount set for ${row.item_code}: ${row.custom_tds_amount}`);
        frm.refresh_field('items');
    },
    
    apply_tds: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log(`Item apply_tds changed for ${row.item_code}: ${row.apply_tds}`);
        
        // If unchecked, clear TDS amount
        if (!row.apply_tds) {
            frappe.model.set_value(cdt, cdn, 'custom_tds_amount', 0);
        }
        
        frm.refresh_field('items');
        
        // Recalculate TDS total
        setTimeout(() => {
            calculate_tds_total(frm);
        }, 300);
    },

    custom_total: function(frm, cdt, cdn) {
        frm.refresh_field('items');
        // Recalculate total amount including excise when custom_total changes
        calculate_total_amount_including_excise(frm);
    },

    items_remove: function(frm) {
        console.log("Item Removed");
        calculate_total(frm);
        calculate_total_amount_including_excise(frm);
        frm.refresh_field('items');
    },
    
    items_add: function(frm, cdt, cdn) {
        console.log("Item Added");
        
        // ALWAYS set default VAT Apply On to Percentage (%) for new rows
        frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'Percentage (%)').then(() => {
            frappe.after_ajax(() => {
                toggle_vat_fields(frm, cdt, cdn);
            });
        });
    }
});

frappe.ui.form.on("Purchase Taxes and Charges", {
    account_head: function(frm, cdt, cdn) {
        console.log("Tax account head changed");
        setTimeout(() => {
            calculate_vat_total(frm);
            calculate_tds_total(frm);
            calculate_total(frm);
        }, 500);
    },
    
    tax_amount: function(frm, cdt, cdn) {
        calculate_vat_total(frm);
        calculate_tds_total(frm);
    },
    
    taxes_add: function(frm) {
        calculate_vat_total(frm);
        calculate_tds_total(frm);
    },
    
    taxes_remove: function(frm) {
        calculate_vat_total(frm);
        calculate_tds_total(frm);
    }
});

/**
 * Toggle VAT field visibility based on custom_vat_apply_on selection
 * 
 * Percentage mode (default):
 *   - VAT Rate: Readonly (from Item Tax Template or 0)
 *   - VAT Amount: Hidden
 * 
 * Amount mode:
 *   - VAT Rate: Hidden and set to 0
 *   - VAT Amount: Editable
 */
function toggle_vat_fields(frm, cdt, cdn) {
    if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
        frappe.after_ajax(() => toggle_vat_fields(frm, cdt, cdn));
        return;
    }

    const grid = frm.fields_dict.items.grid;
    const grid_row = grid.grid_rows_by_docname?.[cdn];

    if (!grid_row) {
        frappe.after_ajax(() => toggle_vat_fields(frm, cdt, cdn));
        return;
    }

    const row = locals[cdt][cdn];
    if (!row) return;

    // ALWAYS default to Percentage if not set
    if (!row.custom_vat_apply_on) {
        frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'Percentage (%)');
        row.custom_vat_apply_on = 'Percentage (%)';
    }

    if (row.custom_vat_apply_on === "Percentage (%)") {
        // Percentage Mode: VAT Rate readonly, VAT Amount hidden
        grid_row.toggle_display("custom_vat_rate", true);
        grid_row.toggle_editable("custom_vat_rate", false);

        grid_row.toggle_display("custom_vat_amount", false);
        grid_row.toggle_editable("custom_vat_amount", false);
        
        console.log(`VAT Percentage mode for ${row.item_code}: Rate readonly (${row.custom_vat_rate || 0}%), Amount hidden`);
    }

    if (row.custom_vat_apply_on === "Amount") {
        // Amount Mode: VAT Rate hidden, VAT Amount editable
        grid_row.toggle_display("custom_vat_rate", false);
        grid_row.toggle_editable("custom_vat_rate", false);

        grid_row.toggle_display("custom_vat_amount", true);
        grid_row.toggle_editable("custom_vat_amount", true);
        
        console.log(`VAT Amount mode for ${row.item_code}: Rate hidden, Amount editable`);
    }
}

/**
 * Calculate total amount including excise from line items
 * This sums all custom_total values from items
 */
function calculate_total_amount_including_excise(frm) {
    if (!frm || !frm.doc) {
        console.log("Form not available");
        return;
    }
    
    let total_including_excise = 0;
    
    if (frm.doc.items && frm.doc.items.length > 0) {
        frm.doc.items.forEach(function(item) {
            let custom_total = flt(item.custom_total) || 0;
            total_including_excise += custom_total;
        });
    }
    
    total_including_excise = flt(total_including_excise, 2);
    console.log(`Total Amount Including Excise: ${total_including_excise}`);
    
    frm.set_value('custom_total_amount_including_excise', total_including_excise);
    frm.refresh_field('custom_total_amount_including_excise');
}

/**
 * Calculate total VAT from taxes table
 */
function calculate_vat_total(frm) {
    if (!frm || !frm.doc) {
        console.log("Form not available");
        return;
    }
    
    let vat_total = 0;
    
    if (frm.doc.taxes && frm.doc.taxes.length > 0) {
        frm.doc.taxes.forEach(function(tax_row) {
            let account_head = tax_row.account_head || '';
            let tax_amount = flt(tax_row.tax_amount) || 0;
            
            if (account_head.startsWith('VAT')) {
                vat_total += tax_amount;
                console.log(`VAT Row: ${account_head} = ${tax_amount}`);
            }
        });
    }
    
    vat_total = flt(vat_total, 2);
    console.log(`Total VAT: ${vat_total}`);
    
    frm.set_value('custom_total_vat_amount', vat_total);
    frm.refresh_field('custom_total_vat_amount');
}

/**
 * Calculate total TDS from taxes table
 * TDS is only calculated if:
 * 1. apply_tds is checked at invoice level
 * 2. tax_withholding_category is set at invoice level
 * 3. apply_tds is checked at line item level
 */
function calculate_tds_total(frm) {
    if (!frm || !frm.doc) {
        console.log("Form not available");
        return;
    }
    
    let tds_total = 0;
    
    // Check invoice-level conditions
    if (frm.doc.apply_tds && frm.doc.tax_withholding_category) {
        // Sum TDS from items where apply_tds is checked
        if (frm.doc.items && frm.doc.items.length > 0) {
            frm.doc.items.forEach(function(item) {
                // Only include items with apply_tds checked
                if (item.apply_tds) {
                    let tds_amount = flt(item.custom_tds_amount) || 0;
                    tds_total += tds_amount;
                    console.log(`TDS from ${item.item_code} (apply_tds=true): ${tds_amount}`);
                }
            });
        }
        
        // Also check taxes table for TDS rows
        if (frm.doc.taxes && frm.doc.taxes.length > 0) {
            frm.doc.taxes.forEach(function(tax_row) {
                // TDS rows have add_deduct_tax = "Deduct"
                if (tax_row.add_deduct_tax === "Deduct") {
                    console.log(`TDS Row in taxes: ${tax_row.account_head} = ${tax_row.tax_amount}`);
                }
            });
        }
    } else {
        console.log("TDS not applicable (invoice apply_tds or tax_withholding_category not set)");
    }
    
    tds_total = flt(tds_total, 2);
    console.log(`Total TDS: ${tds_total}`);
    
    if (frm.doc.hasOwnProperty('custom_total_tds_amount')) {
        frm.set_value('custom_total_tds_amount', tds_total);
        frm.refresh_field('custom_total_tds_amount');
    }
}

/**
 * Calculate totals
 */
function calculate_total(frm) {
    if (!frm || !frm.doc) {
        console.log("Form not available");
        return;
    }
    
    let custom_total_excluding_excise = 0;
    let total_excise = 0;
    
    if (frm.doc.items && frm.doc.items.length > 0) {
        frm.doc.items.forEach(function(item) {
            let base_net_amount = flt(item.base_net_amount) || 0;
            let excise_value = flt(item.custom_excise_value) || 0;
            
            custom_total_excluding_excise += base_net_amount;
            total_excise += excise_value;
        });
        
        frm.doc.custom_total_amount = flt(custom_total_excluding_excise, 2);
        frm.doc.custom_excise = flt(total_excise, 2);

        frm.refresh_field('custom_total_amount');
        frm.refresh_field('custom_excise');
        
        console.log(`Total Excluding Excise: ${custom_total_excluding_excise}, Total Excise: ${total_excise}`);
    }
    
    calculate_vat_total(frm);
    calculate_tds_total(frm);
    calculate_total_amount_including_excise(frm);
}

/**
 * Populate TDS rate from Tax Withholding Category to all items where apply_tds is checked
 */
async function populate_tds_rate_from_category(frm) {
    if (!frm.doc.tax_withholding_category) {
        console.log("No Tax Withholding Category selected");
        return;
    }
    
    try {
        // Fetch Tax Withholding Category document
        const category_data = await frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Tax Withholding Category",
                name: frm.doc.tax_withholding_category
            }
        });
        
        if (category_data.message && category_data.message.rates && category_data.message.rates.length > 0) {
            // Get the TDS rate from the first rate row
            const tds_rate = flt(category_data.message.rates[0].tax_withholding_rate) || 0;
            
            console.log(`TDS Rate from Tax Withholding Category: ${tds_rate}%`);
            
            // Set TDS rate in all items where apply_tds is checked
            if (frm.doc.items && frm.doc.items.length > 0) {
                for (let i = 0; i < frm.doc.items.length; i++) {
                    let item = frm.doc.items[i];
                    
                    if (item.apply_tds) {
                        await frappe.model.set_value(item.doctype, item.name, 'custom_tds_rate', tds_rate);
                        console.log(`Set TDS rate ${tds_rate}% for ${item.item_code}`);
                    }
                }
                
                frm.refresh_field('items');
            }
        } else {
            console.log("No rates found in Tax Withholding Category");
        }
        
    } catch(e) {
        console.error("Error fetching TDS rate from Tax Withholding Category:", e);
    }
}