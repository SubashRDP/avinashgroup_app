frappe.ui.form.on("Purchase Invoice", {
    
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
            calculate_tds_total(frm);
            calculate_total(frm);
        }, 500);
    },
    
    total_advance: function(frm) {
        console.log("Total Advance changed");
        calculate_total(frm);
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
                
                // Only auto-populate if values are not manually set
                let should_fetch_excise = !row.custom_excise_value || row.custom_excise_value === 0;
                let should_fetch_vat = !row.custom_vat_amount || row.custom_vat_amount === 0;
                let should_fetch_tds = !row.custom_tds_amount || row.custom_tds_amount === 0;
                
                if (should_fetch_excise || should_fetch_vat || should_fetch_tds || !row.custom_excise_duty || !row.custom_vat_rate || !row.custom_tds_rate || !row.custom_account) {
                    // Fetch item custom fields
                    const item_data = await frappe.call({
                        method: "avinashgroup_app.custom_code.purchase_invoice.purchase_invoice_taxes_tds.populate_item_custom_fields",
                        args: {
                            item_code: row.item_code
                        }
                    });
                    
                    if (item_data.message) {
                        // Set excise duty
                        if (!row.custom_excise_duty) {
                            await frappe.model.set_value(cdt, cdn, 'custom_excise_duty', item_data.message.custom_excise_duty);
                        }
                        
                        // Set VAT Apply On (default to Percentage)
                        if (!row.custom_vat_apply_on) {
                            await frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'Percentage (%)');
                        }
                        
                        // Set VAT Rate only if VAT Apply On is Percentage
                        if (!row.custom_vat_rate && row.custom_vat_apply_on === 'Percentage (%)') {
                            await frappe.model.set_value(cdt, cdn, 'custom_vat_rate', item_data.message.custom_vat_rate);
                        }
                        
                        // Set TDS Rate and Account
                        if (!row.custom_tds_rate) {
                            await frappe.model.set_value(cdt, cdn, 'custom_tds_rate', item_data.message.custom_tds_rate);
                        }
                        if (!row.custom_account) {
                            await frappe.model.set_value(cdt, cdn, 'custom_account', item_data.message.custom_account);
                        }
                    }
                }
                
                // Apply field visibility based on VAT Apply On
                toggle_vat_fields(frm, cdt, cdn);
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
        let row = locals[cdt][cdn];
        if (row) {
            console.log(`Excise duty changed for ${row.item_code}`);
        }
        frm.refresh_field('items');
    },

    custom_vat_apply_on: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row) {
            console.log(`VAT Apply On changed for ${row.item_code}: ${row.custom_vat_apply_on}`);
            
            // When switching modes, clear the opposite field
            if (row.custom_vat_apply_on === 'Percentage (%)') {
                // Clear manual VAT amount
                frappe.model.set_value(cdt, cdn, 'custom_vat_amount', 0);
            } else if (row.custom_vat_apply_on === 'Amount') {
                // Clear VAT rate percentage
                frappe.model.set_value(cdt, cdn, 'custom_vat_rate', 0);
            }
            
            // Toggle field visibility
            toggle_vat_fields(frm, cdt, cdn);
        }
        frm.refresh_field('items');
    },

    custom_vat_rate: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row) {
            console.log(`VAT rate changed for ${row.item_code}: ${row.custom_vat_rate}%`);
        }
        frm.refresh_field('items');
    },
    
    custom_tds_rate: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row) {
            console.log(`TDS rate changed for ${row.item_code}`);
        }
        frm.refresh_field('items');
    },
    
    custom_account: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row) {
            console.log(`TDS account changed for ${row.item_code}`);
        }
        frm.refresh_field('items');
    },
    
    custom_excise_value: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log(`Manual excise value set for ${row.item_code}: ${row.custom_excise_value}`);
        frm.refresh_field('items');
    },
    
    custom_vat_amount: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log(`Manual VAT amount set for ${row.item_code}: ${row.custom_vat_amount}`);
        frm.refresh_field('items');
    },
    
    custom_tds_amount: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log(`Manual TDS amount set for ${row.item_code}: ${row.custom_tds_amount}`);
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
 */
function toggle_vat_fields(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    if (!row) return;
    
    let grid = frm.fields_dict.items.grid;
    let grid_row = grid.grid_rows_by_docname[cdn];
    
    if (!grid_row) return;
    
    if (row.custom_vat_apply_on === 'Percentage (%)') {
        // Show VAT Rate, hide VAT Amount (make it read-only)
        grid_row.toggle_editable('custom_vat_rate', true);
        grid_row.toggle_display('custom_vat_rate', true);
        grid_row.toggle_editable('custom_vat_amount', false);
        grid_row.toggle_display('custom_vat_amount', true);  // Show but read-only
    } else if (row.custom_vat_apply_on === 'Amount') {
        // Hide VAT Rate (set to 0), show VAT Amount as editable
        grid_row.toggle_editable('custom_vat_rate', false);
        grid_row.toggle_display('custom_vat_rate', false);
        grid_row.toggle_editable('custom_vat_amount', true);
        grid_row.toggle_display('custom_vat_amount', true);
    }
}

/**
 * Calculate total VAT from taxes table
 * Sums all tax amounts where account_head starts with "VAT"
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
 */
function calculate_tds_total(frm) {
    if (!frm || !frm.doc) {
        console.log("Form not available");
        return;
    }
    
    let tds_accounts = new Set();
    if (frm.doc.items && frm.doc.items.length > 0) {
        frm.doc.items.forEach(function(item) {
            if (item.custom_account) {
                tds_accounts.add(item.custom_account);
            }
        });
    }
    
    let tds_total = 0;
    
    if (frm.doc.taxes && frm.doc.taxes.length > 0) {
        frm.doc.taxes.forEach(function(tax_row) {
            let account_head = tax_row.account_head || '';
            let tax_amount = flt(tax_row.tax_amount) || 0;
            
            if (tds_accounts.has(account_head)) {
                tds_total += tax_amount;
                console.log(`TDS Row: ${account_head} = ${tax_amount}`);
            }
        });
    }
    
    tds_total = flt(tds_total, 2);
    
    console.log(`Total TDS: ${tds_total}`);
    
    if (frm.doc.hasOwnProperty('custom_total_tds_amount')) {
        frm.set_value('custom_total_tds_amount', tds_total);
        frm.refresh_field('custom_total_tds_amount');
    }
}

function calculate_total(frm) {
    if (!frm || !frm.doc) {
        console.log("Form not available");
        return;
    }
    
    let custom_total_excluding_excise = 0;
    let total_excise = 0;
    
    if (frm.doc.items && frm.doc.items.length > 0) {
        frm.doc.items.forEach(function(item) {
            let amount = flt(item.amount) || 0;
            let excise_value = flt(item.custom_excise_value) || 0;
            
            custom_total_excluding_excise += amount;
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
}