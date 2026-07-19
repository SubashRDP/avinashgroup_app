

frappe.ui.form.on("Sales Invoice", {

    onload: function(frm) {
        lock_posting_fields(frm);
        // Apply field visibility for all existing rows on load
        if (frm.doc.items) {
            frm.doc.items.forEach(function(item) {
                toggle_vat_fields(frm, item.doctype, item.name);
            });
        }
    },

    refresh: function(frm) {
        lock_posting_fields(frm);
        // Apply field visibility on refresh
        if (frm.doc.items) {
            frm.doc.items.forEach(function(item) {
                toggle_vat_fields(frm, item.doctype, item.name);
            });
        }
        if (frm.is_new()) {
            set_due_date_from_customer(frm);
        }
        update_total_amount_preview(frm);
        restore_return_vat(frm);

        suppress_cancel_delete(frm);
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

    // ERPNext's stock_controller re-opens posting_date/posting_time whenever
    // "Edit Posting Date and Time" is ticked. Re-lock after its handler.
    set_posting_time: function(frm) {
        lock_posting_fields(frm);
    },

    set_posting_date_and_time_read_only: function(frm) {
        lock_posting_fields(frm);
    },

});

// Posting Date and Invoice Miti are never editable on the form, for anyone.
// The posting date is whatever the invoice was raised on, and the BS miti is
// derived from it server-side (custom_code/SalesInvoice/posting_miti.py), so
// neither can be typed over. Deferred a tick so it lands after the ERPNext
// controller handlers that toggle posting_date read_only.
function lock_posting_fields(frm) {
    setTimeout(() => {
        frm.set_df_property('posting_date', 'read_only', 1);
        frm.set_df_property('custom_invoice_miti', 'read_only', 1);
    }, 0);
}

frappe.ui.form.on("Sales Invoice Item", {
    item_code: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row || !row.item_code) return;



        
        // Standalone force-refresh of the item-master fields, independent of whether
        // the server's ERPNext calls get_item_details on item change. Guarantees UOM /
        // name / description follow the NEW item even on demo/older builds where the
        // core handler leaves the previous item's values behind. (Accounts still come
        // from the get_item_details interception below.)
        frappe.db.get_value("Item", row.item_code,
            ["sales_uom", "stock_uom", "item_name", "description"]).then(res => {
                const it = (res && res.message) || {};
                const new_uom = it.sales_uom || it.stock_uom;
                if (new_uom && new_uom !== row.uom) frappe.model.set_value(cdt, cdn, "uom", new_uom);
                if (it.item_name) frappe.model.set_value(cdt, cdn, "item_name", it.item_name);
                if (it.description) frappe.model.set_value(cdt, cdn, "description", it.description);
            });

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
                    // Inject our warehouse if resolved, but NEVER let a failed
                    // warehouse lookup abort ERPNext's callback — that callback is
                    // what applies uom, rate, description, conversion_factor, etc.
                    // to the row. A rejected wh_promise here used to throw before
                    // _cb ran, leaving all item fields unchanged on item change.
                    let our_wh = '';
                    try { our_wh = await wh_promise; } catch (e) { our_wh = ''; }
                    if (our_wh && r && r.message) r.message.warehouse = our_wh;
                    _cb && _cb.apply(this, arguments);
                    // Force item-derived fields to refresh on EVERY item change, even on
                    // servers whose ERPNext build doesn't blank/re-apply them (older
                    // transaction.js leaves the previous item's UOM/accounts on the row).
                    // We re-apply straight from the get_item_details response we just got.
                    // Rate is intentionally left to ERPNext's price-list/pricing-rule flow.
                    if (r && r.message) {
                        const m = r.message;
                        ["item_name", "description", "uom", "stock_uom", "conversion_factor",
                         "income_account", "expense_account", "cost_center"].forEach(f => {
                            if (m[f] !== undefined && m[f] !== null && m[f] !== "") {
                                frappe.model.set_value(cdt, cdn, f, m[f]);
                            }
                        });
                    }
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

                // Fill the VAT mode only when the row has none — never overwrite
                // a value the user picked (VAT 0% / Amount must survive item changes).
                if (!row.custom_vat_apply_on) {
                    await frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'VAT 13%');
                    await frappe.model.set_value(cdt, cdn, 'custom_vat_rate', 13);
                }

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
        const row = locals[cdt][cdn];
        if (row && !row.custom_vat_apply_on) {
            frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'VAT 13%').then(() => {
                frappe.after_ajax(() => {
                    toggle_vat_fields(frm, cdt, cdn);
                });
            });
        } else {
            frappe.after_ajax(() => toggle_vat_fields(frm, cdt, cdn));
        }
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
    update_total_amount_preview(frm);
}

/**
 * Fill the virtual custom_expected_grand_total field ("Total Amount"):
 *
 *   Total Amount = Total Amount Including Excise + Total VAT Amount
 *
 * The real VAT/excise tax rows are only appended to the taxes table on the
 * SERVER (salesinvoice_taxes.update_taxes_table), so before save the form's
 * grand_total shows only the net amount. This field previews what grand_total
 * will become after save. Display only: the field is virtual (no DB column)
 * and grand_total is never written client-side. Direct assignment (not
 * set_value) so the preview never marks the form dirty.
 */
function update_total_amount_preview(frm) {
    if (!frm || !frm.doc) return;

    const total = flt(frm.doc.custom_total_amount_including_excise)
                + flt(frm.doc.custom_total_vat_amount);

    frm.doc.custom_expected_grand_total = flt(total, 5);
    frm.refresh_field('custom_expected_grand_total');
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
 * On a Sales Invoice return, custom_vat_amount is no_copy so the return mapper
 * delivers it as 0. 'VAT 13%' rows self-heal (13% of the negative net amount),
 * but manual 'Amount' rows do not, so the form shows VAT 0 until save. Mirror
 * the server (restore_return_item_taxes): fetch the original row's VAT, scale
 * to the returned qty (partial returns), apply the return sign — so the VAT
 * shows in the UI *before* save. Already-filled rows are skipped (idempotent).
 */
async function restore_return_vat(frm) {
    if (!is_sales_return(frm)) return;
    const items = frm.doc.items || [];
    let changed = false;
    let need_source = false;

    // Pass 1 — 'VAT 13%' rows: 13% of the (negative) net amount. No server call.
    for (const item of items) {
        if (flt(item.custom_vat_amount)) continue;             // already filled -> skip
        if (item.custom_vat_apply_on === "VAT 13%") {
            const base = flt(item.base_net_amount) + flt(item.custom_excise_value);
            const val = flt((base * 13) / 100, 5);
            if (val) {
                await frappe.model.set_value(item.doctype, item.name, "custom_vat_amount", val);
                changed = true;
            }
        } else if (item.custom_vat_apply_on === "Amount" && item.sales_invoice_item) {
            need_source = true;
        }
    }

    // Pass 2 — manual 'Amount' rows: restore from the ORIGINAL invoice.
    // Read the parent Sales Invoice (permitted) instead of the child row directly
    // (frappe.db.get_value on a child table throws "Not permitted").
    if (need_source && frm.doc.return_against) {
        let original = null;
        try {
            original = await frappe.db.get_doc("Sales Invoice", frm.doc.return_against);
        } catch (e) {
            original = null;
        }
        if (original) {
            const src_by_name = {};
            (original.items || []).forEach((it) => { src_by_name[it.name] = it; });
            for (const item of items) {
                if (flt(item.custom_vat_amount)) continue;
                if (item.custom_vat_apply_on !== "Amount" || !item.sales_invoice_item) continue;
                const src = src_by_name[item.sales_invoice_item];
                if (!src || !flt(src.qty)) continue;
                if (src.custom_vat_apply_on === "Amount" && flt(src.custom_vat_amount)) {
                    const ratio = Math.abs(flt(item.qty)) / Math.abs(flt(src.qty));
                    const val = flt(-Math.abs(flt(src.custom_vat_amount) * ratio), 5);
                    await frappe.model.set_value(item.doctype, item.name, "custom_vat_amount", val);
                    changed = true;
                }
            }
        }
    }

    if (changed) calculate_vat_total(frm);
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
    update_total_amount_preview(frm);
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


// _fetch_selling_wh() is defined in sales_warehouse_common.js, which is loaded
// globally via app_include_js (before this per-form file). Single source of
// truth — do not redefine it here.

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


/**
 * Whether Cancel/Delete should be hidden for the CURRENT user.
 *
 * Administrator keeps both, so there is always a way to cancel or delete a
 * Sales Invoice without a code change — log in as Administrator. Every other
 * user (including System Managers) has the controls hidden.
 *
 * Evaluated at call time, not at file-load time: the list-view patch below is
 * installed once during boot, and reading the session there would bake in
 * whatever frappe.session held at that moment.
 */
function hide_cancel_delete_for_user() {
    return !frappe.session || frappe.session.user !== "Administrator";
}


/**
 * Hide Cancel and Delete on the Sales Invoice FORM for everyone except
 * Administrator. Server-side CBMS before_cancel/on_trash throws remain the
 * real enforcement — this only removes the desk controls.
 *
 * Both entries are blocked at creation rather than deleted after render:
 *
 *  - Delete is a Menu item added by toolbar.js make_menu_items() together with
 *    a Shift+Ctrl+D shortcut. Removing the <li> afterwards leaves that shortcut
 *    live, so the invoice is still deletable from the keyboard.
 *  - Cancel is the page SECONDARY action (toolbar.js set_page_actions). When the
 *    doctype has a workflow it is attached only after an async
 *    can_cancel_document xcall, so a fixed-delay prune can run too early and
 *    the button comes back.
 *
 * Blocking also survives every later toolbar rebuild (save, submit, workflow
 * transition), which a one-shot removal does not.
 */
function suppress_cancel_delete(frm) {
    const page = frm.page;
    if (!page) return;

    // Install once per page. frappe.views.formview keeps one page object per
    // doctype (formview.js), so these patches only ever affect Sales Invoice.
    if (!page.__agp_no_cancel_delete) {
        page.__agp_no_cancel_delete = true;

        const _add_menu_item = page.add_menu_item.bind(page);
        page.add_menu_item = function (label) {
            if (label === __("Delete") && hide_cancel_delete_for_user()) return;
            return _add_menu_item.apply(page, arguments);
        };

        const _set_secondary_action = page.set_secondary_action.bind(page);
        page.set_secondary_action = function (label) {
            if (label === __("Cancel") && hide_cancel_delete_for_user()) return page.btn_secondary;
            return _set_secondary_action.apply(page, arguments);
        };
    }

    if (!hide_cancel_delete_for_user()) return;

    // The guards stop future additions; clear whatever a render that happened
    // before they were installed already put on screen.
    const del_label = __("Delete");
    page.menu
        .find(".menu-item-label")
        .filter((i, el) => $(el).text().trim() === del_label)
        .closest("li")
        .remove();
    if (page.btn_secondary.attr("data-label") === __("Cancel")) {
        page.clear_secondary_action();
    }
}


// ---------------------------------------------------------------------------
// List view: hide Cancel and Delete from the bulk "Actions" menu (Sales Invoice
// ONLY). The form toolbar is handled in refresh() above; the list-view Actions
// dropdown is built by a separate path (list_view.js get_actions_menu_items ->
// set_actions_menu_items -> page.actions). Server-side enforcement is
// unchanged — this only removes the UI entries.
//
// This deliberately does NOT go through frappe.listview_settings. ERPNext's own
// sales_invoice_list.js does a wholesale
//     frappe.listview_settings["Sales Invoice"] = { ... }
// and it loads AFTER app_include_js, so anything merged into that object here
// is silently replaced — verified on the running desk, where our onload was
// simply gone. Patching get_actions_menu_items instead is immune to load order:
// it filters the items before they are ever turned into menu entries, so there
// is nothing to prune and nothing for a later assignment to clobber.
// ---------------------------------------------------------------------------
(function () {
    function install() {
        const LV = frappe.views && frappe.views.ListView;
        if (!LV || typeof LV.prototype.get_actions_menu_items !== "function") return false;
        if (LV.prototype.__agp_no_cancel_delete) return true;
        LV.prototype.__agp_no_cancel_delete = true;

        const _get_actions_menu_items = LV.prototype.get_actions_menu_items;
        LV.prototype.get_actions_menu_items = function () {
            const items = _get_actions_menu_items.apply(this, arguments) || [];
            // Sales Invoice only — every other doctype keeps its bulk actions.
            if (this.doctype !== "Sales Invoice") return items;
            // Administrator keeps Cancel/Delete.
            if (!hide_cancel_delete_for_user()) return items;
            // Same label + context strings list_view.js builds them with.
            const blocked = [
                __("Cancel", null, "Button in list view actions menu"),
                __("Delete", null, "Button in list view actions menu"),
            ];
            return items.filter((item) => !blocked.includes(item.label));
        };
        return true;
    }

    // ListView is normally defined by the time app_include_js runs; the retry
    // covers a boot order where the list bundle has not landed yet. Must be
    // installed before the first Sales Invoice list is constructed, because
    // Frappe caches list views (frappe.views.list_view[route]) and only builds
    // the Actions menu once per page object.
    if (!install()) {
        const timer = setInterval(() => { if (install()) clearInterval(timer); }, 100);
        setTimeout(() => clearInterval(timer), 15000);
        $(document).on("app_ready", install);
    }
})();
