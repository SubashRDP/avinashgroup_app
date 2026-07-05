

frappe.ui.form.on("Sales Invoice", {

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
        if (frm.is_new()) {
            set_due_date_from_customer(frm);
        }
        setup_print_count_watch(frm);
        if (frm.__sync_print_count) {
            frm.__sync_print_count();   // reconcile when returning to the form
        }
    },

    before_save: function(frm) {
        return force_all_si_warehouses(frm);
    },

    // When set_warehouse changes, ERPNext propagates it to all item rows.
    // Re-apply custom_selling_warehouse immediately after to override it.
    set_warehouse: function(frm) {
        setTimeout(() => force_all_si_warehouses(frm), 300);
    },

    base_total_taxes_and_charges: function(frm) {
        calculate_total(frm);
    },

    base_grand_total: function(frm) {
        calculate_total(frm);
    },

    taxes_and_charges: function(frm) {
        setTimeout(() => {
            calculate_vat_total(frm);
            calculate_total(frm);
        }, 500);
    },

    total_advance: function(frm) {
        calculate_total(frm);
    },

    customer: function(frm) {
        // Run after core handlers so our custom due date wins
        setTimeout(() => set_due_date_from_customer(frm), 0);
    },

    posting_date: function(frm) {
        // Run after core handlers so our custom due date wins
        setTimeout(() => set_due_date_from_customer(frm), 0);
    },

});

// Printing an invoice bumps custom_print_count server-side, but that happens
// in a separate print/PDF window — the open form never hears about it. When the
// user switches back to the invoice tab, re-read just that one field so the
// count (and IRD copy title logic) reflects the print that just happened.
function setup_print_count_watch(frm) {
    if (frm.__print_count_watch) {
        return;                       // listeners are added once per form object
    }
    frm.__print_count_watch = true;

    const sync = frappe.utils.debounce(function() {
        const cur = frm.doc;
        if (!cur || cur.__islocal || frm.is_dirty()) {
            return;                   // don't touch new or unsaved-edited forms
        }
        const name = cur.name;
        frappe.db.get_value("Sales Invoice", name, "custom_print_count").then(function(r) {
            const v = r && r.message ? r.message.custom_print_count : undefined;
            // ignore if the user navigated to another doc while the call was in flight
            if (v === undefined || !frm.doc || frm.doc.name !== name) {
                return;
            }
            if (cint(v) !== cint(frm.doc.custom_print_count)) {
                frm.doc.custom_print_count = cint(v);
                frm.refresh_field("custom_print_count");
            }
        });
    }, 300);

    frm.__sync_print_count = sync;    // let refresh re-run it on return to the form

    document.addEventListener("visibilitychange", function() {
        if (document.visibilityState === "visible") {
            sync();
        }
    });
    window.addEventListener("focus", sync);
}

frappe.ui.form.on("Sales Invoice Item", {
    item_code: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row || !row.item_code) return;

        // Start fetching our warehouse immediately (runs in background)
        const wh_promise = _fetch_selling_wh(row.item_code, frm.doc.custom_branch);

        // SYNCHRONOUSLY wrap frappe.call before any await.
        // When ERPNext's item_code handler calls get_item_details, we intercept the
        // response and inject our warehouse BEFORE ERPNext sets it on locals.
        // This eliminates the race condition that setTimeout-based approaches had.
        const _orig = frappe.call;
        let _restored = false;
        const _restore = () => { if (!_restored) { frappe.call = _orig; _restored = true; } };
        frappe.call = function(opts) {
            if (opts && opts.method && opts.method.includes('get_item_details')) {
                const _cb = opts.callback;
                opts.callback = async function(r) {
                    const our_wh = await wh_promise;
                    if (r && r.message) r.message.warehouse = our_wh;
                    _cb && _cb.apply(this, arguments);
                    _restore();
                };
            }
            return _orig.apply(frappe, arguments);
        };
        setTimeout(_restore, 5000); // safety: restore if get_item_details is never called

        // Continue with VAT defaults and visibility (async, but wrapper is already in place)
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

                await frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'VAT 13%');
                await frappe.model.set_value(cdt, cdn, 'custom_vat_rate', 13);

                frappe.after_ajax(() => toggle_vat_fields(frm, cdt, cdn));
                frm.refresh_field('items');
            } catch(e) {
                console.error("Error in item_code handler:", e);
                _restore();
            }
        })();
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
    custom_excise_value: function(frm, cdt, cdn) {
        calculate_item_custom_total(frm, cdt, cdn);
        frm.refresh_field('items');
    },

    custom_vat_apply_on: async function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        if (row.custom_vat_apply_on === "VAT 13%") {
            await frappe.model.set_value(cdt, cdn, "custom_vat_rate", 13);
        } else if (row.custom_vat_apply_on === "VAT 0%") {
            await frappe.model.set_value(cdt, cdn, "custom_vat_rate", 0);
        } else if (row.custom_vat_apply_on === "Amount") {
            await frappe.model.set_value(cdt, cdn, "custom_vat_rate", 0);
        }

        calculate_item_vat_amount(frm, cdt, cdn);

        frappe.after_ajax(() => {
            toggle_vat_fields(frm, cdt, cdn);
        });
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
    },
    
    items_add: function(frm, cdt, cdn) {
        frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'VAT 13%').then(() => {
            frappe.after_ajax(() => {
                toggle_vat_fields(frm, cdt, cdn);
            });
        });
    }
});

frappe.ui.form.on("Sales Taxes and Charges", {
    account_head: function(frm, cdt, cdn) {
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

    if (!row.custom_vat_apply_on) {
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
}

/**
 * Calculate total amount including excise from line items
 * This sums all custom_total values from items
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
 * Ensure negative qty and VAT amount for Sales Invoice returns on the client
 * so it reflects immediately after the user edits a row.
 */
function apply_return_signs(frm, cdt, cdn) {
    if (!is_sales_return(frm)) return;

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

function is_sales_return(frm) {
    return (
        frm &&
        frm.doc &&
        frm.doc.doctype === "Sales Invoice" &&
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

function set_due_date_from_customer(frm) {
    if (!frm.doc.customer || !frm.doc.posting_date) return;
    const posting_date = frm.doc.posting_date;
    frappe.db.get_value('Customer', frm.doc.customer, 'custom_days_limit', function(data) {
        const days = (data && data.custom_days_limit) ? data.custom_days_limit : 0;
        frm.set_value('due_date', frappe.datetime.add_days(posting_date, days));

    });
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
    
    calculate_vat_total(frm);
    calculate_total_amount_including_excise(frm);
}


/**
 * Fetch custom_selling_warehouse for an item, respecting branch-wise config.
 * Returns "" if not configured — caller decides whether to set or leave.
 */
async function _fetch_selling_wh(item_code, custom_branch) {
    let wh = '';
    if (custom_branch) {
        const item_doc = await frappe.db.get_doc('Item', item_code);
        const brow = (item_doc.custom_branch_wise_warehouse || [])
            .find(r => r.custom_branch === custom_branch);
        if (brow) wh = brow.custom_selling_warehouse || '';
    }
    if (!wh) {
        const res = await frappe.db.get_value('Item', item_code, 'custom_selling_warehouse');
        wh = (res && res.message && res.message.custom_selling_warehouse) || '';
    }
    return wh;
}

/**
 * Before save: sweep all item rows and force warehouse = custom_selling_warehouse.
 * Overrides set_warehouse, Item Defaults, and any system fallback.
 */
async function force_all_si_warehouses(frm) {
    if (!frm.doc.items || !frm.doc.items.length) return;

    const custom_branch = frm.doc.custom_branch;
    const item_codes = [...new Set(frm.doc.items.map(r => r.item_code).filter(Boolean))];
    const warehouse_map = {};

    await Promise.all(item_codes.map(async (item_code) => {
        warehouse_map[item_code] = await _fetch_selling_wh(item_code, custom_branch);
    }));

    for (const item of frm.doc.items) {
        // On save: only override if custom_selling_warehouse is set — preserves manual selection
        const wh = item.item_code ? (warehouse_map[item.item_code] || '') : '';
        if (wh) {
            item.warehouse = wh;
        }
    }
    
    frm.refresh_field('items');
}
