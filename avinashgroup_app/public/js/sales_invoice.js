frappe.ui.form.on("Sales Invoice", {

    
    onload: function(frm) {
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
            calculate_total(frm);
        }, 500);
    },
    
    total_advance: function(frm) {
        console.log("Total Advance changed");
        calculate_total(frm);
    },
    
    outstanding_amount: function(frm) {
        console.log("Outstanding Amount changed");
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
                
                // Only auto-populate if values are not manually set
                let should_fetch_excise = !row.custom_excise_value || row.custom_excise_value === 0;
                let should_fetch_vat = !row.custom_vat_amount || row.custom_vat_amount === 0;
                
                if (should_fetch_excise || should_fetch_vat || !row.custom_excise_duty || !row.custom_vat) {
                    // Fetch item custom fields
                    const item_data = await frappe.call({
                        method: "avinashgroup_app.custom_code.SalesInvoice.salesinvoice_taxes.populate_item_custom_fields",
                        args: {
                            item_code: row.item_code
                        }
                    });
                    
                    if (item_data.message) {
                        // Set excise duty and VAT percentage (these are templates)
                        if (!row.custom_excise_duty) {
                            await frappe.model.set_value(cdt, cdn, 'custom_excise_duty', item_data.message.custom_excise_duty);
                        }
                        if (!row.custom_vat) {
                            await frappe.model.set_value(cdt, cdn, 'custom_vat', item_data.message.custom_vat);
                        }
                    }
                }
                
                frm.refresh_field('items');
                
            } catch(e) {
                console.error("Error in item_code handler:", e);
            }
        }
    },

    qty: function(frm, cdt, cdn) {
        // Values will be calculated by backend
        frm.refresh_field('items');
    },
    
    amount: function(frm, cdt, cdn) {
        frm.refresh_field('items');
    },
    
    rate: function(frm, cdt, cdn) {
        frm.refresh_field('items');
    },
    
    custom_excise_duty: function(frm, cdt, cdn) {
        // Mark that excise duty changed, so backend will recalculate
        let row = locals[cdt][cdn];
        if (row) {
            // Clear custom_excise_value to trigger recalculation
            // Unless user manually set custom_excise_value
            console.log(`Excise duty changed for ${row.item_code}`);
        }
        frm.refresh_field('items');
    },

    custom_vat: function(frm, cdt, cdn) {
        // Mark that VAT percentage changed
        let row = locals[cdt][cdn];
        if (row) {
            console.log(`VAT percentage changed for ${row.item_code}`);
        }
        frm.refresh_field('items');
    },
    
    custom_excise_value: function(frm, cdt, cdn) {
        // User manually edited excise value
        let row = locals[cdt][cdn];
        console.log(`Manual excise value set for ${row.item_code}: ${row.custom_excise_value}`);
        frm.refresh_field('items');
    },
    
    custom_vat_amount: function(frm, cdt, cdn) {
        // User manually edited VAT amount
        let row = locals[cdt][cdn];
        console.log(`Manual VAT amount set for ${row.item_code}: ${row.custom_vat_amount}`);
        frm.refresh_field('items');
    },

    custom_total: function(frm, cdt, cdn) {
        frm.refresh_field('items');
    },

    items_remove: function(frm) {
        console.log("Item Removed");
        frm.refresh_field('items');
    },
    
    items_add: function(frm) {
        console.log("Item Added");
        frm.refresh_field('items');
    }
});

frappe.ui.form.on("Sales Taxes and Charges", {
    account_head: function(frm, cdt, cdn) {
        console.log("Tax account head changed");
        setTimeout(() => {
            calculate_vat_total(frm);
            calculate_total(frm);
        }, 500);
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
            
            // Check if account_head starts with "VAT"
            if (account_head.startsWith('VAT')) {
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

function calculate_total(frm) {
    if (!frm || !frm.doc) {
        console.log("Form not available");
        return;
    }
    
    let custom_total_excluding_excise = 0;
    let total_excise = 0;
    
    // Calculate totals from items
    if (frm.doc.items && frm.doc.items.length > 0) {
        frm.doc.items.forEach(function(item) {
            let amount = flt(item.amount) || 0;
            let excise_value = flt(item.custom_excise_value) || 0;
            
            custom_total_excluding_excise += amount;
            total_excise += excise_value;
        });
        
        // Display calculated values
        frm.doc.custom_total_amount = flt(custom_total_excluding_excise, 2);
        frm.doc.custom_excise = flt(total_excise, 2);

        frm.refresh_field('custom_total_amount');
        frm.refresh_field('custom_excise');
        
        console.log(`Total Excluding Excise: ${custom_total_excluding_excise}, Total Excise: ${total_excise}`);
    }
    
    // Calculate VAT total
    calculate_vat_total(frm);
}