// Configuration for supported doctypes
const PURCHASE_DOCTYPES = [
    "Purchase Invoice",
    "Purchase Order",
    "Purchase Receipt",
    "Supplier Quotation"
];

const ITEM_DOCTYPES = {
    "Purchase Invoice": "Purchase Invoice Item",
    "Purchase Order": "Purchase Order Item",
    "Purchase Receipt": "Purchase Receipt Item",
    "Supplier Quotation": "Supplier Quotation Item"
};

// Doctypes that have taxes table
const DOCTYPES_WITH_TAXES = ["Purchase Invoice", "Purchase Receipt", "Purchase Order", "Supplier Quotation"];
// Doctypes that should default VAT Apply On to VAT 13%
const VAT_DEFAULT_DOCTYPES = ["Purchase Invoice", "Purchase Order", "Purchase Receipt", "Supplier Quotation"];

// Account → subtype (vehicle) list cache for the Purchase Invoice subtype filter
let pi_account_subtype_cache = {};

// Item fields to map between documents
const ITEM_FIELDS_TO_MAP = [
    "custom_excise_value",
    "custom_total",
    "custom_vat_apply_on",
    "custom_vat_rate",
    "custom_vat_amount",
    "custom_tds_apply_on",
    "custom_tds_rate",
    "custom_tds_amount",
    "apply_tds"
];

// Document-level fields to map
const DOC_FIELDS_TO_MAP = [
    "custom_total_amount_including_excise",
    "custom_total_excise_amount",
    "custom_total_vat_amount",
    "custom_total_tds_amount",
    "custom_tax_withholding_category_custom",
    "custom_excise"
];

// Initialize handlers for all supported doctypes
PURCHASE_DOCTYPES.forEach(function(doctype) {
    // Parent doctype handlers
    frappe.ui.form.on(doctype, {
        onload: function(frm) {
            purchase_taxes_onload(frm);
        },

        refresh: function(frm) {
            purchase_taxes_refresh(frm);
        },

        base_total_taxes_and_charges: function(frm) {
            calculate_total(frm);
        },

        base_grand_total: function(frm) {
            calculate_total(frm);
        },

        taxes_and_charges: function(frm) {
            setTimeout(() => {
                if (DOCTYPES_WITH_TAXES.includes(frm.doc.doctype)) {
                    calculate_vat_total(frm);
                    calculate_tds_total(frm);
                }
                calculate_total(frm);
            }, 500);
        },

        total_advance: function(frm) {
            calculate_total(frm);
        },

        custom_tax_withholding_category_custom: function(frm) {
            if (frm.doc.custom_tax_withholding_category_custom) {
                populate_tds_rate_from_custom_category(frm);
            }
            calculate_tds_total(frm);
        },

        items_add: function(frm, cdt, cdn) {
            const row = locals[cdt][cdn];

            // Purchase Invoice: new rows start with an empty (no-match) Subtype
            // filter until an item provides an expense account to filter by
            if (frm.doc.doctype === "Purchase Invoice") {
                set_initial_subtype_filter(frm, cdn, 0);
            }

            if (should_apply_vat_default(frm) && row && !row.custom_vat_apply_on) {
                frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'VAT 13%').then(() => {
                    toggle_vat_fields(frm, cdt, cdn);
                    frm.refresh_field('items');
                });
            }

            frappe.model.set_value(cdt, cdn, 'custom_tds_apply_on', 'Percentage (%)').then(() => {
                toggle_tds_fields(frm, cdt, cdn);
                frm.refresh_field('items');
            });
        }
    });

    // Item child table handlers
    const item_doctype = ITEM_DOCTYPES[doctype];
    frappe.ui.form.on(item_doctype, {
        item_code: async function(frm, cdt, cdn) {
            await handle_item_code_change(frm, cdt, cdn);
        },

        qty: function(frm, cdt, cdn) {
            setTimeout(() => calculate_item_custom_total(frm, cdt, cdn), 300);
            setTimeout(() => apply_return_signs(frm, cdt, cdn), 350);
            frm.refresh_field('items');
        },

        rate: function(frm, cdt, cdn) {
            setTimeout(() => calculate_item_custom_total(frm, cdt, cdn), 300);
            frm.refresh_field('items');
        },

        base_net_amount: function(frm, cdt, cdn) {
            calculate_item_custom_total(frm, cdt, cdn);
            frm.refresh_field('items');
        },

        base_net_rate: function(frm, cdt, cdn) {
            calculate_item_custom_total(frm, cdt, cdn);
            frm.refresh_field('items');
        },

        custom_excise_value: function(frm, cdt, cdn) {
            calculate_item_custom_total(frm, cdt, cdn);
            frm.refresh_field('items');
        },

        custom_excise_duty: function(frm, cdt, cdn) {
            frm.refresh_field('items');
        },

        custom_vat_apply_on: async function(frm, cdt, cdn) {
            await handle_vat_apply_on_change(frm, cdt, cdn);
            calculate_item_vat_amount(frm, cdt, cdn);
        },

        custom_vat_rate: function(frm, cdt, cdn) {
            frm.refresh_field('items');
        },

        custom_vat_amount: function(frm, cdt, cdn) {
            // In Amount mode: recalculate header total when user edits this field
            calculate_vat_total(frm);
            apply_return_signs(frm, cdt, cdn);
            frm.refresh_field('items');
        },

        custom_tds_apply_on: async function(frm, cdt, cdn) {
            await handle_tds_apply_on_change(frm, cdt, cdn);
        },

        custom_tds_rate: function(frm, cdt, cdn) {
            frm.refresh_field('items');
        },

        custom_tds_amount: function(frm, cdt, cdn) {
            frm.refresh_field('items');
        },

        apply_tds: function(frm, cdt, cdn) {
            handle_apply_tds_change(frm, cdt, cdn);
        },

        custom_total: function(frm, cdt, cdn) {
            calculate_total_amount_including_excise(frm);
            calculate_item_vat_amount(frm, cdt, cdn);
            apply_return_signs(frm, cdt, cdn);
            frm.refresh_field('items');
        },

        items_remove: function(frm) {
            calculate_total(frm);
            calculate_total_amount_including_excise(frm);
            calculate_vat_total(frm);
            frm.refresh_field('items');
        }
    });
});

// Register taxes table handlers only for doctypes that have it
DOCTYPES_WITH_TAXES.forEach(function(doctype) {
    frappe.ui.form.on("Purchase Taxes and Charges", {
        account_head: function(frm, cdt, cdn) {
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
});


/**
 * Common onload handler
 */
function purchase_taxes_onload(frm) {
    if (frm.doc.items) {
        frm.doc.items.forEach(function(item) {
            if (should_apply_vat_default(frm) && !item.custom_vat_apply_on) {
                item.custom_vat_apply_on = 'VAT 13%';
            }
            if (!item.custom_tds_apply_on) {
                item.custom_tds_apply_on = 'Percentage (%)';
            }
            toggle_vat_fields(frm, item.doctype, item.name);
            toggle_tds_fields(frm, item.doctype, item.name);
        });
    }
    frm.refresh_field('items');
}

/**
 * Common refresh handler
 */
function purchase_taxes_refresh(frm) {
    if (frm.doc.items) {
        frm.doc.items.forEach(function(item) {
            if (should_apply_vat_default(frm) && !item.custom_vat_apply_on) {
                item.custom_vat_apply_on = 'VAT 13%';
            }
            if (!item.custom_tds_apply_on) {
                item.custom_tds_apply_on = 'Percentage (%)';
            }
            toggle_vat_fields(frm, item.doctype, item.name);
            toggle_tds_fields(frm, item.doctype, item.name);
        });
    }
    frm.refresh_field('items');

    // Purchase Invoice: rebuild the account→subtype cache and re-apply
    // the Subtype dropdown filters for all existing rows
    if (frm.doc.doctype === "Purchase Invoice") {
        pi_account_subtype_cache = {};
        prefetch_account_subtypes(frm);
    }

    // Check and populate from source document for new docs created via buttons
    check_and_populate_from_source(frm);
}

/**
 * Handle item_code change
 */
function handle_item_code_change(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row) return;
    if (!row.item_code) {
        // Item cleared — reset the Subtype filter to match nothing
        if (frm.doc.doctype === "Purchase Invoice") {
            apply_subtype_filter(frm, cdn, []);
        }
        return;
    }

    // Start fetching our warehouse immediately (runs in background)
    const wh_promise = _fetch_buying_wh(row.item_code, frm.doc.custom_branch);

    // SYNCHRONOUSLY wrap frappe.call before any await.
    // When ERPNext's item_code handler calls get_item_details, we intercept the
    // response and inject our warehouse BEFORE ERPNext sets it on locals.
    const _orig = frappe.call;
    let _restored = false;
    const _restore = () => { if (!_restored) { frappe.call = _orig; _restored = true; } };
    frappe.call = function(opts) {
        if (opts && opts.method && opts.method.includes('get_item_details')) {
            const _cb = opts.callback;
            opts.callback = async function(r) {
                // Never let a failed warehouse lookup abort ERPNext's callback —
                // it applies uom/rate/description/conversion factor to the row.
                let our_wh = '';
                try { our_wh = await wh_promise; } catch (e) { our_wh = ''; }
                if (our_wh && r && r.message) r.message.warehouse = our_wh;
                _cb && _cb.apply(this, arguments);
                _restore();
            };
        }
        return _orig.apply(frappe, arguments);
    };
    setTimeout(_restore, 5000); // safety: restore if get_item_details is never called

    // Continue with VAT/TDS defaults (async, but wrapper is already in place)
    (async () => {
        try {
            const item_check = await frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Item",
                    filters: { name: row.item_code },
                    fieldname: "item_name"
                }
            });

            if (!item_check.message) { _restore(); return; }

            // Clear the custom_subtype field when item_code changes
            if (row.hasOwnProperty('custom_subtype')) {
                await frappe.model.set_value(cdt, cdn, 'custom_subtype', '');
            }

            // Fill the VAT mode only when the row has none — never overwrite
            // a value the user picked (VAT 0% / Amount must survive item changes).
            if (should_apply_vat_default(frm) && !row.custom_vat_apply_on) {
                await frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'VAT 13%');
                await frappe.model.set_value(cdt, cdn, 'custom_vat_rate', 13);
            }
            await frappe.model.set_value(cdt, cdn, 'custom_tds_apply_on', 'Percentage (%)');

            const item_data = await frappe.call({
                method: "avinashgroup_app.custom_code.common.purchase_taxes_handler.populate_item_custom_fields",
                args: { item_code: row.item_code }
            });

            if (item_data.message) {
                if (!row.custom_excise_duty && item_data.message.custom_excise_duty) {
                    await frappe.model.set_value(cdt, cdn, 'custom_excise_duty', item_data.message.custom_excise_duty);
                }
                if (!row.custom_tds_rate && item_data.message.custom_tds_rate) {
                    await frappe.model.set_value(cdt, cdn, 'custom_tds_rate', item_data.message.custom_tds_rate);
                }
            }

            // Purchase Invoice: filter the Subtype dropdown to the vehicles
            // configured on the item's default expense account
            if (frm.doc.doctype === "Purchase Invoice") {
                const expense_account = await get_expense_account_from_item(row.item_code);
                if (expense_account) {
                    const vehicles = await get_account_subtypes(expense_account);
                    apply_subtype_filter(frm, cdn, vehicles);
                } else {
                    apply_subtype_filter(frm, cdn, []);
                }
            }

            setTimeout(() => {
                toggle_vat_fields(frm, cdt, cdn);
                toggle_tds_fields(frm, cdt, cdn);
                frm.refresh_field('items');
            }, 100);

        } catch(e) {
            console.error("Error in item_code handler:", e);
            _restore();
        }
    })();
}

/**
 * Handle VAT apply_on change
 */
async function handle_vat_apply_on_change(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (row.custom_vat_apply_on === "VAT 13%") {
        await frappe.model.set_value(cdt, cdn, "custom_vat_rate", 13);
        await frappe.model.set_value(cdt, cdn, "custom_vat_amount", 0);
    } else if (row.custom_vat_apply_on === "VAT 0%") {
        await frappe.model.set_value(cdt, cdn, "custom_vat_rate", 0);
        await frappe.model.set_value(cdt, cdn, "custom_vat_amount", 0);
    } else if (row.custom_vat_apply_on === "Amount") {
        await frappe.model.set_value(cdt, cdn, "custom_vat_rate", 0);
    }

    setTimeout(() => {
        toggle_vat_fields(frm, cdt, cdn);
        frm.refresh_field('items');
    }, 100);
}

/**
 * Handle TDS apply_on change
 */
async function handle_tds_apply_on_change(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (row.custom_tds_apply_on === "Percentage (%)") {
        await frappe.model.set_value(cdt, cdn, "custom_tds_amount", 0);

        if (frm.doc.custom_tax_withholding_category_custom) {
            try {
                const category_data = await frappe.call({
                    method: "frappe.client.get",
                    args: {
                        doctype: "Tax Withholding Category",
                        name: frm.doc.custom_tax_withholding_category_custom
                    }
                });

                if (category_data.message && category_data.message.rates && category_data.message.rates.length > 0) {
                    const tds_rate = flt(category_data.message.rates[0].tax_withholding_rate) || 0;
                    await frappe.model.set_value(cdt, cdn, 'custom_tds_rate', tds_rate);
                }
            } catch(e) {
                console.error("Error re-fetching TDS rate:", e);
            }
        }
    }

    if (row.custom_tds_apply_on === "Amount") {
        await frappe.model.set_value(cdt, cdn, "custom_tds_rate", 0);
    }

    setTimeout(() => {
        toggle_tds_fields(frm, cdt, cdn);
        frm.refresh_field('items');
    }, 100);
}

/**
 * Handle apply_tds checkbox change
 */
function handle_apply_tds_change(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (!row.apply_tds) {
        frappe.model.set_value(cdt, cdn, 'custom_tds_amount', 0);
    }

    frm.refresh_field('items');

    setTimeout(() => {
        calculate_tds_total(frm);
    }, 300);
}

/**
 * Toggle VAT fields visibility based on mode
 */
function toggle_vat_fields(frm, cdt, cdn) {
    if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
        setTimeout(() => toggle_vat_fields(frm, cdt, cdn), 100);
        return;
    }

    const grid = frm.fields_dict.items.grid;
    const grid_row = grid.grid_rows_by_docname?.[cdn];

    if (!grid_row) {
        setTimeout(() => toggle_vat_fields(frm, cdt, cdn), 100);
        return;
    }

    const row = locals[cdt][cdn];
    if (!row) return;

    if (should_apply_vat_default(frm) && !row.custom_vat_apply_on) {
        frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'VAT 13%');
        row.custom_vat_apply_on = 'VAT 13%';
    }

    if (row.custom_vat_apply_on === "VAT 13%" || row.custom_vat_apply_on === "VAT 0%") {
        grid_row.toggle_display("custom_vat_rate", true);
        grid_row.toggle_editable("custom_vat_rate", false);
        grid_row.toggle_display("custom_vat_amount", true);
        grid_row.toggle_editable("custom_vat_amount", false);  // read-only, auto-calculated
    } else if (row.custom_vat_apply_on === "Amount") {
        grid_row.toggle_display("custom_vat_rate", false);
        grid_row.toggle_editable("custom_vat_rate", false);
        grid_row.toggle_display("custom_vat_amount", true);
        grid_row.toggle_editable("custom_vat_amount", true);   // editable, manual entry
    }

    grid_row.refresh();
}

function should_apply_vat_default(frm) {
    return VAT_DEFAULT_DOCTYPES.includes(frm.doc.doctype);
}

/**
 * Toggle TDS fields visibility based on mode
 */
function toggle_tds_fields(frm, cdt, cdn) {
    if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
        setTimeout(() => toggle_tds_fields(frm, cdt, cdn), 100);
        return;
    }

    const grid = frm.fields_dict.items.grid;
    const grid_row = grid.grid_rows_by_docname?.[cdn];

    if (!grid_row) {
        setTimeout(() => toggle_tds_fields(frm, cdt, cdn), 100);
        return;
    }

    const row = locals[cdt][cdn];
    if (!row) return;

    if (!row.custom_tds_apply_on) {
        frappe.model.set_value(cdt, cdn, 'custom_tds_apply_on', 'Percentage (%)');
        row.custom_tds_apply_on = 'Percentage (%)';
    }

    if (row.custom_tds_apply_on === "Percentage (%)") {
        grid_row.toggle_display("custom_tds_rate", true);
        grid_row.toggle_editable("custom_tds_rate", false);
        grid_row.toggle_display("custom_tds_amount", false);
        grid_row.toggle_editable("custom_tds_amount", false);
    }
    else if (row.custom_tds_apply_on === "Amount") {
        grid_row.toggle_display("custom_tds_rate", false);
        grid_row.toggle_editable("custom_tds_rate", false);
        grid_row.toggle_display("custom_tds_amount", true);
        grid_row.toggle_editable("custom_tds_amount", true);
    }

    grid_row.refresh();
}

/**
 * Calculate total amount including excise from line items
 */
function calculate_total_amount_including_excise(frm) {
    if (!frm || !frm.doc) return;

    let total_including_excise = 0;

    if (frm.doc.items && frm.doc.items.length > 0) {
        frm.doc.items.forEach(function(item) {
            let custom_total = flt(item.custom_total) || 0;
            total_including_excise += custom_total;
        });
    }

    total_including_excise = flt(total_including_excise, 5);

    frm.set_value('custom_total_amount_including_excise', total_including_excise);
    frm.refresh_field('custom_total_amount_including_excise');
}

/**
 * Calculate custom_total for a single line item client-side.
 * custom_total = base_net_amount + custom_excise_value
 * Must be called before calculate_item_vat_amount so VAT uses the fresh total.
 */
function calculate_item_custom_total(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row) return;

    const custom_total = flt(flt(row.base_net_amount) + flt(row.custom_excise_value), 5);
    frappe.model.set_value(cdt, cdn, 'custom_total', custom_total);
    // VAT recalculates via the custom_total change handler below
}

/**
 * Calculate VAT amount for a single line item and update the header total.
 * Always derives custom_total fresh from base_net_amount + custom_excise_value
 * so it is never stale from a previous save.
 * VAT 13%  → custom_vat_amount = custom_total × 13%  (read-only)
 * VAT 0%   → custom_vat_amount = 0                    (read-only)
 * Amount   → keep whatever the user entered           (editable)
 */
function calculate_item_vat_amount(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row) return;

    const vat_apply_on = row.custom_vat_apply_on || 'VAT 13%';
    // Always compute fresh — never trust row.custom_total (may be stale from last save)
    const custom_total = flt(row.base_net_amount) + flt(row.custom_excise_value);

    if (vat_apply_on === 'VAT 13%') {
        frappe.model.set_value(cdt, cdn, 'custom_vat_amount', flt((custom_total * 13) / 100, 5));
    } else if (vat_apply_on === 'VAT 0%') {
        frappe.model.set_value(cdt, cdn, 'custom_vat_amount', 0);
    }
    // Amount mode: do nothing — user's manual entry is preserved

    setTimeout(() => calculate_vat_total(frm), 50);
    apply_return_signs(frm, cdt, cdn);
}

/**
 * Ensure negative qty and VAT amount for Purchase Invoice returns on the client
 * so it reflects immediately after the user edits a row.
 */
function apply_return_signs(frm, cdt, cdn) {
    if (!is_purchase_return(frm)) return;

    const row = locals[cdt][cdn];
    if (!row) return;

    const qty = flt(row.qty) || 0;
    if (qty > 0) {
        frappe.model.set_value(cdt, cdn, "qty", -Math.abs(qty));
    }

    const vat_amount = flt(row.custom_vat_amount) || 0;
    if (vat_amount > 0) {
        frappe.model.set_value(cdt, cdn, "custom_vat_amount", -Math.abs(vat_amount));
    }
}

function is_purchase_return(frm) {
    return (
        frm &&
        frm.doc &&
        frm.doc.doctype === "Purchase Invoice" &&
        frm.doc.is_return
    );
}

/**
 * Calculate total VAT by summing custom_vat_amount from all line items
 */
function calculate_vat_total(frm) {
    if (!frm || !frm.doc) return;

    let vat_total = 0;
    (frm.doc.items || []).forEach(function(item) {
        vat_total += flt(item.custom_vat_amount) || 0;
    });

    vat_total = flt(vat_total, 5);
    frm.set_value('custom_total_vat_amount', vat_total);
    frm.refresh_field('custom_total_vat_amount');
}

/**
 * Calculate total TDS
 */
function calculate_tds_total(frm) {
    if (!frm || !frm.doc) return;

    let tds_total = 0;

    // Sum TDS from items where apply_tds is checked
    if (frm.doc.custom_tax_withholding_category_custom) {
        if (frm.doc.items && frm.doc.items.length > 0) {
            frm.doc.items.forEach(function(item) {
                if (item.apply_tds) {
                    let tds_amount = flt(item.custom_tds_amount) || 0;
                    tds_total += tds_amount;
                }
            });
        }
    }

    tds_total = flt(tds_total, 5);

    if (frm.doc.hasOwnProperty('custom_total_tds_amount')) {
        frm.set_value('custom_total_tds_amount', tds_total);
        frm.refresh_field('custom_total_tds_amount');
    }
}

/**
 * Calculate totals
 */
function calculate_total(frm) {
    if (!frm || !frm.doc) return;

    let custom_total_excluding_excise = 0;
    let total_excise = 0;

    if (frm.doc.items && frm.doc.items.length > 0) {
        frm.doc.items.forEach(function(item) {
            let base_net_amount = flt(item.base_net_amount) || 0;
            let excise_value = flt(item.custom_excise_value) || 0;

            custom_total_excluding_excise += base_net_amount;
            total_excise += excise_value;
        });

        frm.doc.custom_total_amount = flt(custom_total_excluding_excise, 5);
        frm.doc.custom_excise = flt(total_excise, 5);

        frm.refresh_field('custom_total_amount');
        frm.refresh_field('custom_excise');
    }

    if (DOCTYPES_WITH_TAXES.includes(frm.doc.doctype)) {
        calculate_vat_total(frm);
        calculate_tds_total(frm);
    }
    calculate_total_amount_including_excise(frm);
}

/**
 * Populate TDS rate from CUSTOM Tax Withholding Category
 */
async function populate_tds_rate_from_custom_category(frm) {
    if (!frm.doc.custom_tax_withholding_category_custom) return;

    try {
        const category_data = await frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "Tax Withholding Category",
                name: frm.doc.custom_tax_withholding_category_custom
            }
        });

        if (category_data.message && category_data.message.rates && category_data.message.rates.length > 0) {
            const tds_rate = flt(category_data.message.rates[0].tax_withholding_rate) || 0;

            if (frm.doc.items && frm.doc.items.length > 0) {
                for (let i = 0; i < frm.doc.items.length; i++) {
                    let item = frm.doc.items[i];

                    if (item.apply_tds) {
                        await frappe.model.set_value(item.doctype, item.name, 'custom_tds_rate', tds_rate);
                    }
                }

                frm.refresh_field('items');
            }
        }

    } catch(e) {
        console.error("Error fetching TDS rate from Custom Tax Withholding Category:", e);
    }
}

/**
 * Populate tax fields from source document when creating via button
 * This function is called after the document is mapped
 */
async function populate_taxes_from_source(frm, source_doctype, source_name) {
    if (!source_name) return;

    try {
        const result = await frappe.call({
            method: "avinashgroup_app.custom_code.common.purchase_taxes_mapper.get_taxes_from_source",
            args: {
                source_doctype: source_doctype,
                source_name: source_name,
                target_doctype: frm.doc.doctype
            }
        });

        if (result.message) {
            const data = result.message;

            // Set document-level fields
            if (data.doc_fields) {
                for (const [field, value] of Object.entries(data.doc_fields)) {
                    if (value !== null && value !== undefined && frm.fields_dict[field]) {
                        frm.set_value(field, value);
                    }
                }
            }

            // Set item-level fields
            if (data.items && data.items.length > 0 && frm.doc.items) {
                for (let i = 0; i < frm.doc.items.length; i++) {
                    const target_item = frm.doc.items[i];
                    let source_item = null;

                    // Find matching source item by reference field or item_code
                    for (const src of data.items) {
                        // Check by reference fields
                        if (
                            (target_item.supplier_quotation_item && target_item.supplier_quotation_item === src.name) ||
                            (target_item.purchase_order_item && target_item.purchase_order_item === src.name) ||
                            (target_item.purchase_invoice_item && target_item.purchase_invoice_item === src.name) ||
                            (target_item.item_code === src.item_code)
                        ) {
                            source_item = src;
                            break;
                        }
                    }

                    if (source_item) {
                        for (const field of ITEM_FIELDS_TO_MAP) {
                            if (source_item[field] !== null && source_item[field] !== undefined) {
                                await frappe.model.set_value(target_item.doctype, target_item.name, field, source_item[field]);
                            }
                        }
                    }
                }

                frm.refresh_field('items');

                // Apply field visibility toggles
                frm.doc.items.forEach(function(item) {
                    toggle_vat_fields(frm, item.doctype, item.name);
                    toggle_tds_fields(frm, item.doctype, item.name);
                });
            }

            console.log(`Tax fields populated from ${source_doctype}: ${source_name}`);
        }
    } catch (e) {
        console.error("Error populating tax fields from source:", e);
    }
}

/**
 * Detect source document and populate tax fields
 * Called on refresh for new documents created from other documents
 */
function check_and_populate_from_source(frm) {
    if (!frm.is_new()) return;
    if (!frm.doc.items || frm.doc.items.length === 0) return;

    // Check for source document references
    let source_doctype = null;
    let source_name = null;

    const first_item = frm.doc.items[0];

    // Purchase Order created from Supplier Quotation
    if (frm.doc.doctype === "Purchase Order") {
        if (first_item.supplier_quotation) {
            source_doctype = "Supplier Quotation";
            source_name = first_item.supplier_quotation;
        }
    }

    // Purchase Receipt created from Purchase Order
    if (frm.doc.doctype === "Purchase Receipt") {
        if (first_item.purchase_order) {
            source_doctype = "Purchase Order";
            source_name = first_item.purchase_order;
        } else if (first_item.purchase_invoice) {
            source_doctype = "Purchase Invoice";
            source_name = first_item.purchase_invoice;
        }
    }
  //
    // Purchase Invoice created from Purchase Order or Purchase Receipt
    if (frm.doc.doctype === "Purchase Invoice") {
        if (first_item.purchase_order) {
            source_doctype = "Purchase Order";
            source_name = first_item.purchase_order;
        } else if (first_item.purchase_receipt) {
            source_doctype = "Purchase Receipt";
            source_name = first_item.purchase_receipt;
        }
    }

    if (source_doctype && source_name) {
        // Small delay to ensure the form is fully loaded
        setTimeout(() => {
            populate_taxes_from_source(frm, source_doctype, source_name);
        }, 500);
    }
}

// Force warehouse from Item's custom_buying_warehouse for all buying doctypes
PURCHASE_DOCTYPES.forEach(function(doctype) {
    frappe.ui.form.on(doctype, {
        before_save: function(frm) {
            return force_all_pi_warehouses(frm);
        }
    });
});

// Warehouse-only handlers for Material Request and Request for Quotation
// Set immediately on item_code change AND again at delays to beat ERPNext's Item Defaults
["Material Request Item", "Request for Quotation Item"].forEach(function(child_doctype) {
    frappe.ui.form.on(child_doctype, {
        item_code: function(frm, cdt, cdn) {
            const row = locals[cdt][cdn];
            if (!row || !row.item_code) return;

            // Fetch our warehouse in the background
            const wh_promise = _fetch_buying_wh(row.item_code, frm.doc.custom_branch);

            // SYNCHRONOUSLY wrap frappe.call to inject warehouse into get_item_details response
            const _orig = frappe.call;
            let _restored = false;
            const _restore = () => { if (!_restored) { frappe.call = _orig; _restored = true; } };
            frappe.call = function(opts) {
                if (opts && opts.method && (
                    opts.method.includes('get_item_details') ||
                    opts.method.includes('get_item_data')
                )) {
                    const _cb = opts.callback;
                    opts.callback = async function(r) {
                        // Never let a failed warehouse lookup abort ERPNext's
                        // callback — it applies uom/rate/description/conversion
                        // factor to the row.
                        let our_wh = '';
                        try { our_wh = await wh_promise; } catch (e) { our_wh = ''; }
                        if (our_wh && r && r.message) r.message.warehouse = our_wh;
                        _cb && _cb.apply(this, arguments);
                        _restore();
                    };
                }
                return _orig.apply(frappe, arguments);
            };
            setTimeout(_restore, 5000);
        }
    });
});

["Material Request", "Request for Quotation"].forEach(function(doctype) {
    frappe.ui.form.on(doctype, {
        before_save: function(frm) {
            return force_all_pi_warehouses(frm);
        }
    });
});

// Auto-set due_date for Purchase Invoice based on supplier's custom_payment_term_days
frappe.ui.form.on("Purchase Invoice", {
    refresh: function(frm) {
        if (frm.is_new()) {
            set_pi_due_date_from_supplier(frm);
        }
    },
    supplier: function(frm) {
        // Run after core handlers so our custom due date wins
        setTimeout(() => set_pi_due_date_from_supplier(frm), 0);
    },
    posting_date: function(frm) {
        // Run after core handlers so our custom due date wins
        setTimeout(() => set_pi_due_date_from_supplier(frm), 0);
    }
});

function set_pi_due_date_from_supplier(frm) {
    if (!frm.doc.supplier || !frm.doc.posting_date) return;
    const posting_date = frm.doc.posting_date;
    frappe.db.get_value('Supplier', frm.doc.supplier, 'custom_payment_term_days', function(data) {
        const days = (data && data.custom_payment_term_days) ? data.custom_payment_term_days : 0;
        frm.set_value('due_date', frappe.datetime.add_days(posting_date, days));
    });
}

/**
 * Fetch custom_buying_warehouse for an item, respecting branch-wise config.
 * Returns "" if not configured — caller decides whether to set or leave.
 */
async function _fetch_buying_wh(item_code, custom_branch) {
    // Must never reject: awaited inside the get_item_details callback wrapper,
    // where a rejection would stop item details (uom, rate, description,
    // conversion factor) from being applied to the row.
    try {
        let wh = '';
        if (custom_branch) {
            const item_doc = await frappe.db.get_doc('Item', item_code);
            const brow = (item_doc.custom_branch_wise_warehouse || [])
                .find(r => r.custom_branch === custom_branch);
            if (brow) wh = brow.custom_buying_warehouse || '';
        }
        if (!wh) {
            const res = await frappe.db.get_value('Item', item_code, 'custom_buying_warehouse');
            wh = (res && res.message && res.message.custom_buying_warehouse) || '';
        }
        return wh;
    } catch (e) {
        console.warn('buying warehouse lookup failed for', item_code, e);
        return '';
    }
}

/**
 * Before save: sweep all buying doctype item rows and force warehouse = custom_buying_warehouse.
 * Only overrides if custom_buying_warehouse is set — preserves manual user selection.
 */
async function force_all_pi_warehouses(frm) {
    if (!frm.doc.items || !frm.doc.items.length) return;

    const custom_branch = frm.doc.custom_branch;
    const item_codes = [...new Set(frm.doc.items.map(r => r.item_code).filter(Boolean))];
    const warehouse_map = {};

    await Promise.all(item_codes.map(async (item_code) => {
        warehouse_map[item_code] = await _fetch_buying_wh(item_code, custom_branch);
    }));

    for (const item of frm.doc.items) {
        const warehouse = item.item_code ? (warehouse_map[item.item_code] || '') : '';
        // On save: only override if custom_buying_warehouse is set — preserves manual selection
        if (warehouse && item.warehouse !== warehouse) {
            await frappe.model.set_value(item.doctype, item.name, 'warehouse', warehouse);
        }
    }
    frm.refresh_field('items');
    
}


// ---------------------------------------------------------------------------
// Purchase Invoice: Subtype (vehicle) dropdown filtering
// The Subtype link field on each item row is filtered to the vehicles listed
// on the item's default expense account (Account.custom_sub_type_list).
// Ported from the legacy "Purchase Invoice" Client Script (now disabled).
// ---------------------------------------------------------------------------

function set_initial_subtype_filter(frm, cdn, attempt) {
    const grid_row = frm.fields_dict['items'].grid.grid_rows_by_docname[cdn];
    if (grid_row) {
        grid_row.get_field('custom_subtype').get_query = function() {
            return { filters: { 'name': ['in', ['__no_match__']] } };
        };
    } else if (attempt < 5) {
        setTimeout(() => set_initial_subtype_filter(frm, cdn, attempt + 1), 200);
    }
}

/**
 * Get expense account from Item's item_defaults child table
 */
function get_expense_account_from_item(item_code) {
    return frappe.db.get_doc('Item', item_code).then(item_doc => {
        for (const default_entry of (item_doc.item_defaults || [])) {
            if (default_entry.expense_account) {
                return default_entry.expense_account;
            }
        }
        return null;
    });
}

/**
 * Pre-fetch subtype lists for all items' expense accounts and apply row filters
 */
function prefetch_account_subtypes(frm) {
    const unique_items = [...new Set(
        (frm.doc.items || []).map(row => row.item_code).filter(Boolean)
    )];
    if (!unique_items.length) return;

    Promise.all(unique_items.map(item_code => get_expense_account_from_item(item_code)))
        .then(expense_accounts => {
            const unique_accounts = [...new Set(expense_accounts.filter(Boolean))];
            if (!unique_accounts.length) return;

            return Promise.all(unique_accounts.map(account => get_account_subtypes(account)));
        })
        .then(() => {
            (frm.doc.items || []).forEach(row => {
                if (!row.item_code) return;
                get_expense_account_from_item(row.item_code).then(expense_account => {
                    if (expense_account && pi_account_subtype_cache[expense_account]) {
                        apply_subtype_filter(frm, row.name, pi_account_subtype_cache[expense_account]);
                    }
                });
            });
        })
        .catch(err => console.error('Error prefetching account subtypes:', err));
}

/**
 * Get an account's subtype (vehicle) list with caching
 */
function get_account_subtypes(account) {
    if (pi_account_subtype_cache[account] !== undefined) {
        return Promise.resolve(pi_account_subtype_cache[account]);
    }
    return frappe.db.get_doc('Account', account).then(account_doc => {
        const vehicles = (account_doc.custom_sub_type_list || [])
            .map(item => item.vehicle_list)
            .filter(Boolean);
        pi_account_subtype_cache[account] = vehicles;
        return vehicles;
    });
}

/**
 * Apply the Subtype link-field filter to a specific item row
 */
function apply_subtype_filter(frm, row_name, vehicles) {
    const grid_row = frm.fields_dict['items'].grid.grid_rows_by_docname[row_name];
    if (!grid_row) return;

    grid_row.get_field('custom_subtype').get_query = function() {
        return {
            filters: {
                'name': ['in', vehicles.length > 0 ? vehicles : ['__no_match__']]
            }
        };
    };
    grid_row.refresh_field('custom_subtype');
}
