frappe.ui.form.on("Sales Invoice", {

    onload: function(frm) {
        install_custom_totals_hook();
        lock_posting_fields(frm);
        // Apply field visibility for all existing rows on load
        if (frm.doc.items) {
            frm.doc.items.forEach(function(item) {
                toggle_vat_fields(frm, item.doctype, item.name);
            });
        }
    },

    refresh: function(frm) {
        install_custom_totals_hook();
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
        // Draft-only: a doc opened already sitting on Grishma/Anamnagar (e.g. loaded
        // with those defaults pre-filled, without company/custom_branch ever firing
        // their change event) still needs rounding forced on / POS scope enforced.
        // Never touch a submitted document from a passive refresh.
        if (frm.doc.docstatus === 0) {
            sync_pos_rounding(frm);
            enforce_pos_scope(frm);
        }
        sync_custom_totals(frm);
        restore_return_vat(frm);
        fetch_credit_banner(frm);
    },

    before_save: function(frm) {
        sync_custom_totals(frm);
        return force_all_si_warehouses(frm);
    },

    // When set_warehouse changes, ERPNext propagates it to all item rows.
    // Re-apply custom_selling_warehouse immediately after to override it.
    set_warehouse: function(frm) {
        setTimeout(() => force_all_si_warehouses(frm), 300);
    },

    base_total_taxes_and_charges: function(frm) {
        sync_custom_totals(frm);
    },

    base_grand_total: function(frm) {
        sync_custom_totals(frm);
    },

    taxes_and_charges: function(frm) {
        setTimeout(() => sync_custom_totals(frm), 500);
    },

    // Ticking "Include Payment (POS)" fills the default payment row via an
    // async server round-trip (core's set_pos_data -> set_missing_values),
    // so its own set_default_payment() runs after this handler and overwrites
    // the row with the pre-VAT grand_total. Re-sync once that round-trip has
    // settled, same delay convention as taxes_and_charges above.
    is_pos: function(frm) {
        sync_pos_rounding(frm);
        setTimeout(() => sync_custom_totals(frm), 500);
    },

    company: function(frm) {
        enforce_pos_scope(frm);
        sync_pos_rounding(frm);
    },

    custom_branch: function(frm) {
        enforce_pos_scope(frm);
        sync_pos_rounding(frm);
    },

    total_advance: function(frm) {
        sync_custom_totals(frm);
    },

    customer: function(frm) {
        // Run after core handlers so our custom due date wins
        setTimeout(() => set_due_date_from_customer(frm), 0);
        fetch_credit_banner(frm);
    },

    grand_total: function(frm) {
        // Re-render from the cached position so the "with this invoice"
        // figures track the amount being entered — no server call.
        render_credit_banner(frm);
    },

    posting_date: function(frm) {
        // Run after core handlers so our custom due date wins
        setTimeout(() => set_due_date_from_customer(frm), 0);
        // The days check is measured from posting_date on the server, so the
        // banner has to be re-read whenever the date moves.
        fetch_credit_banner(frm);
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

// Direct Item Price lookup for the row's exact UOM. Fallback for servers where
// the get_item_details pipeline returns/leaves 0 for per-UOM prices even though
// a matching Item Price row exists.
async function fetch_uom_price(frm, row) {
    const res = await frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Item Price",
            filters: {
                item_code: row.item_code,
                price_list: frm.doc.selling_price_list,
                uom: row.uom,
                selling: 1,
            },
            fields: ["price_list_rate"],
            order_by: "valid_from desc",
            limit_page_length: 1,
        },
    });
    const hit = res && res.message && res.message[0];
    return hit ? flt(hit.price_list_rate) : 0;
}

// If every earlier writer left the rate at 0 (or a near-zero rounding
// artifact, e.g. -0.00115, from a core pricing computation gone wrong) but an
// Item Price exists for the row's exact UOM, apply it. Never touches a real
// (non-negligible) rate.
const RATE_NEGLIGIBLE_THRESHOLD = 0.01;
function is_rate_negligible(rate) {
    return Math.abs(flt(rate)) <= RATE_NEGLIGIBLE_THRESHOLD;
}

// A 100% discount nobody entered. ERPNext's `rate` handler (transaction.js:31-33)
// creates it whenever a rate of 0 is written against a populated price_list_rate:
//     discount_percentage = (1 - 0/price_list_rate) * 100 = 100
//     discount_amount     = price_list_rate - 0
// It then STICKS — apply_pricing_rule_on_item (taxes_and_totals.js:30) re-subtracts
// discount_amount on every later recompute, so correcting `rate` alone is undone on
// the next pass. The discount has to be cleared, not the rate.
//
// discount_amount carries no precision override (currency precision 2) while
// price_list_rate is precision 5, which is why the leftover shows up as a tiny
// residue like 0.00124 (= 1774.22124 - 1774.22) rather than a clean zero.
async function clear_bogus_full_discount(frm, cdt, cdn) {
    const row = locals[cdt] && locals[cdt][cdn];
    if (!row || row.is_free_item) return false;
    const plr = flt(row.price_list_rate);
    if (!plr || !is_rate_negligible(row.rate)) return false;
    // Compare at the coarser of the two precisions — discount_amount is stored
    // rounded to 2 while price_list_rate keeps 5.
    const full_discount = flt(row.discount_percentage) >= 99.999
        || Math.abs(flt(row.discount_amount) - plr) < 0.01;
    if (!full_discount) return false;
    console.log(`[avinashgroup] clearing unintended 100% discount: ${row.item_code} / ${row.uom} -> ${plr}`);
    await frappe.model.set_value(cdt, cdn, "discount_percentage", 0);
    await frappe.model.set_value(cdt, cdn, "discount_amount", 0);
    await frappe.model.set_value(cdt, cdn, "rate", plr);
    frm.refresh_field("items");
    return true;
}

async function ensure_rate_from_item_price(frm, cdt, cdn) {
    const row = locals[cdt] && locals[cdt][cdn];
    if (!row || !row.item_code || !row.uom || !is_rate_negligible(row.rate)) return;
    // The row already knows its price — it is only being cancelled out by a
    // phantom discount. Fix that in place; no Item Price lookup needed.
    if (await clear_bogus_full_discount(frm, cdt, cdn)) return;
    const direct = await fetch_uom_price(frm, row);
    // Re-read the row: the rate may have been filled while we were fetching.
    const fresh = locals[cdt] && locals[cdt][cdn];
    if (direct && fresh && is_rate_negligible(fresh.rate)) {
        console.log(`[avinashgroup] rate fallback: ${fresh.item_code} / ${fresh.uom} -> ${direct}`);
        await frappe.model.set_value(cdt, cdn, "price_list_rate", direct);
        await frappe.model.set_value(cdt, cdn, "rate", direct);
        frm.refresh_field("items");
    }
}

// The zero-writer can land at unpredictable times (slow servers stretch the
// get_item_details roundtrips), so a single delayed check can run too early —
// while the doomed first rate is still on the row — and wrongly conclude all is
// well. Check repeatedly instead; each pass is a no-op once a rate is set.
function schedule_rate_checks(frm, cdt, cdn) {
    [800, 2000, 3500, 5500].forEach((ms) =>
        setTimeout(() => ensure_rate_from_item_price(frm, cdt, cdn), ms)
    );
}

// Rows waiting on their own get_item_details response, keyed by child docname.
// The warehouse lookup resolves INTO the entry, so the interceptor never awaits.
const pending_item_details = {};

function register_item_details_interception(cdn, item_code, wh_promise) {
    const entry = { item_code: item_code, warehouse: "", promise: wh_promise };
    pending_item_details[cdn] = entry;
    wh_promise.then((wh) => { entry.warehouse = wh || ""; }).catch(() => { entry.warehouse = ""; });
    // Never leak an entry if get_item_details is never called for this row.
    setTimeout(() => { if (pending_item_details[cdn] === entry) delete pending_item_details[cdn]; }, 15000);
    return entry;
}

// Installed ONCE, globally. The previous version wrapped frappe.call afresh on every
// item change and restored it from inside a callback. That had three failure modes,
// all of them observed live on ng-group:
//
//   1. `method.includes('get_item_details')` matches the MODULE path, so it also caught
//      apply_price_list, get_conversion_factor, get_bin_details and 8 other methods in
//      erpnext.stock.get_item_details — 11 in total, where 1 was intended.
//   2. ERPNext's own callback was held behind `await wh_promise`. On a slow warehouse
//      lookup the grid re-rendered first, the child row left `locals`, and ERPNext's
//      price loop died with "can't access property price_list_rate, e is undefined"
//      (taxes_and_totals.js:10). That left the row holding a price_list_rate with no
//      rate — the state that makes ERPNext record a 100% discount.
//   3. Restoring from inside that callback fired on whichever of the 11 methods returned
//      first, so two overlapping item changes could reinstate a DEAD wrapper as the
//      global frappe.call — still closed over an old row's cdt/cdn, and writing one
//      row's response onto another. That is where conversion_factor=1 on a 14.2 KG row
//      came from.
//
// Matching the exact method plus child_docname removes all three: installed once, never
// removed, never delays a callback, and can only touch the row the response was for.
(function install_item_details_observer() {
    if (frappe.__avinashgroup_si_item_details_observer) return;
    frappe.__avinashgroup_si_item_details_observer = true;

    const _orig_call = frappe.call;
    frappe.call = function (opts) {
        const method = opts && opts.method;
        if (method === "erpnext.stock.get_item_details.get_item_details") {
            const call_args = (opts.args && opts.args.args) || {};
            const cdn = call_args.child_docname;
            const cdt = call_args.child_doctype;
            const entry = pending_item_details[cdn];
            if (entry && entry.item_code === call_args.item_code) {
                const _cb = opts.callback;
                opts.callback = function (r) {
                    delete pending_item_details[cdn];
                    if (entry.warehouse && r && r.message) r.message.warehouse = entry.warehouse;
                    // Synchronous: ERPNext's callback must run in the tick it would have
                    // run in without us. Delaying it is what let the row disappear.
                    _cb && _cb.apply(this, arguments);

                    const m = r && r.message;
                    const fresh = locals[cdt] && locals[cdt][cdn];
                    // Only this row, and only if it still holds the item we fetched for.
                    if (m && fresh && fresh.item_code === entry.item_code) {
                        // Re-apply item-derived fields for older ERPNext builds that leave
                        // the previous item's values on the row. rate / price_list_rate are
                        // deliberately absent: those are ERPNext's to compute, and writing
                        // the server's hardcoded 0 into rate is what produced the 100%
                        // discount (see clear_bogus_full_discount above).
                        ["item_name", "description", "uom", "stock_uom", "conversion_factor",
                         "income_account", "expense_account", "cost_center"].forEach((f) => {
                            if (m[f] !== undefined && m[f] !== null && m[f] !== "") {
                                frappe.model.set_value(cdt, cdn, f, m[f]);
                            }
                        });
                    }

                    // Warehouse still in flight: apply it when it lands rather than
                    // holding the callback for it.
                    if (!entry.warehouse) {
                        entry.promise.then((wh) => {
                            const row = locals[cdt] && locals[cdt][cdn];
                            if (wh && row && row.item_code === entry.item_code) {
                                frappe.model.set_value(cdt, cdn, "warehouse", wh);
                            }
                        }).catch(() => {});
                    }
                };
            }
        }
        return _orig_call.apply(frappe, arguments);
    };
})();

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

        // Register this row so the global observer (above) can inject our warehouse
        // into ERPNext's get_item_details response for THIS row only. No wrapping,
        // no restoring, no awaiting inside a callback.
        register_item_details_interception(cdn, row.item_code, wh_promise);

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

                if (!item_check.message) { delete pending_item_details[cdn]; return; }

                // Fill the VAT mode only when the row has none — never overwrite
                // a value the user picked (VAT 0% / Amount must survive item changes).
                if (!row.custom_vat_apply_on) {
                    await frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'VAT 13%');
                    await frappe.model.set_value(cdt, cdn, 'custom_vat_rate', 13);
                }

                frappe.after_ajax(() => toggle_vat_fields(frm, cdt, cdn));
                frm.refresh_field('items');

                schedule_rate_checks(frm, cdt, cdn);
            } catch(e) {
                console.error("Error in item_code handler:", e);
                delete pending_item_details[cdn];
            }
        })();
    },


    uom: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row || !row.item_code || !row.uom) return;

        // Re-fetch item pricing after a UOM change so the server recalculates
        // the rate for the selected sales UOM instead of keeping the old one.
        setTimeout(async () => {
            try {
                const response = await frappe.call({
                    method: "erpnext.stock.get_item_details.get_item_details",
                    args: {
                        doc: frm.doc,
                        args: {
                            item_code: row.item_code,
                            barcode: row.barcode,
                            serial_no: row.serial_no,
                            batch_no: row.batch_no,
                            set_warehouse: frm.doc.set_warehouse,
                            warehouse: row.warehouse,
                            customer: frm.doc.customer || frm.doc.party_name,
                            quotation_to: frm.doc.quotation_to,
                            supplier: frm.doc.supplier,
                            currency: frm.doc.currency,
                            is_internal_supplier: frm.doc.is_internal_supplier,
                            is_internal_customer: frm.doc.is_internal_customer,
                            update_stock: cint(frm.doc.update_stock),
                            conversion_rate: frm.doc.conversion_rate,
                            price_list: frm.doc.selling_price_list || frm.doc.buying_price_list,
                            price_list_currency: frm.doc.price_list_currency,
                            plc_conversion_rate: frm.doc.plc_conversion_rate,
                            company: frm.doc.company,
                            order_type: frm.doc.order_type,
                            is_pos: cint(frm.doc.is_pos),
                            is_return: cint(frm.doc.is_return),
                            is_subcontracted: frm.doc.is_subcontracted,
                            ignore_pricing_rule: frm.doc.ignore_pricing_rule,
                            doctype: frm.doc.doctype,
                            name: frm.doc.name,
                            project: row.project || frm.doc.project,
                            qty: row.qty || 1,
                            net_rate: row.rate,
                            base_net_rate: row.base_net_rate,
                            stock_qty: row.stock_qty,
                            conversion_factor: row.conversion_factor,
                            weight_per_unit: row.weight_per_unit,
                            uom: row.uom,
                            weight_uom: row.weight_uom,
                            manufacturer: row.manufacturer,
                            stock_uom: row.stock_uom,
                            pos_profile: cint(frm.doc.is_pos) ? frm.doc.pos_profile : "",
                            cost_center: row.cost_center,
                            tax_category: frm.doc.tax_category,
                            item_tax_template: row.item_tax_template,
                            child_doctype: row.doctype,
                            child_docname: row.name,
                            is_old_subcontracting_flow: frm.doc.is_old_subcontracting_flow,
                            use_serial_batch_fields: row.use_serial_batch_fields,
                            serial_and_batch_bundle: row.serial_and_batch_bundle,
                        },
                    },
                });

                if (response && response.message) {
                    const fields_to_update = [
                        "item_name",
                        "description",
                        "uom",
                        "stock_uom",
                        "conversion_factor",
                        "price_list_rate",
                        "base_price_list_rate",
                        "rate",
                        "base_rate",
                        "amount",
                        "base_amount",
                        "net_rate",
                        "net_amount",
                        "stock_qty",
                        "stock_uom_rate",
                        "income_account",
                        "expense_account",
                        "cost_center",
                    ];

                    // A zero in any of these is always "no data", never a real value.
                    // get_item_details seeds them to 0.0 in get_basic_details and only
                    // ever overwrites `rate` for Material Request (get_item_details.py:133),
                    // so on a Sales Invoice the server's `rate` is unconditionally 0.
                    //
                    // Writing that 0 is what produced the 100% discount: ERPNext's own
                    // `rate` handler (transaction.js:31-33) reads rate=0 against a populated
                    // price_list_rate and concludes the whole price is a discount —
                    //     discount_percentage = (1 - 0/1774.22124) * 100 = 100
                    //     discount_amount     = 1774.22124 - 0 = 1774.22124
                    // discount_amount has no precision override (currency precision 2 from
                    // number_format) while rate/price_list_rate are precision 5, so
                    // round_floats_in leaves 1774.22 against 1774.22124 and the next
                    // apply_pricing_rule_on_item yields rate = 0.00124.
                    //
                    // The earlier guard only skipped a zero when the row ALREADY held a
                    // non-zero rate, so a row whose price_list_rate trigger had not landed
                    // yet still took the 0. Skip zeros outright and let ERPNext derive
                    // rate/amount from price_list_rate, which is its job.
                    const zero_means_no_data = new Set([
                        "price_list_rate", "base_price_list_rate", "rate", "base_rate",
                        "amount", "base_amount", "net_rate", "net_amount", "stock_uom_rate",
                    ]);

                    for (const fieldname of fields_to_update) {
                        const incoming = response.message[fieldname];
                        if (incoming === undefined || incoming === null) continue;
                        if (zero_means_no_data.has(fieldname) && !flt(incoming)) continue;
                        await frappe.model.set_value(cdt, cdn, fieldname, incoming);
                    }
                }

                frm.refresh_field("items");
            } catch (e) {
                console.error("Error in Sales Invoice UOM handler:", e);
            }
            // Outside the try: must run even when the roundtrip above failed.
            schedule_rate_checks(frm, cdt, cdn);
        }, 0);
    },

    // qty and rate need no total handling of their own: ERPNext recalculates
    // base_net_amount and install_custom_totals_hook() re-derives every custom
    // total off the back of that same call, with no timer in between.
    qty: function(frm, cdt, cdn) {
        apply_return_signs(frm, cdt, cdn);
    },
    base_net_amount: function(frm, cdt, cdn) {
        sync_custom_totals(frm);
    },
    custom_excise_value: function(frm, cdt, cdn) {
        sync_custom_totals(frm);
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

        sync_custom_totals(frm);

        frappe.after_ajax(() => {
            toggle_vat_fields(frm, cdt, cdn);
        });
    },

    custom_vat_rate: function(frm, cdt, cdn) {
        frm.refresh_field('items');
    },

    custom_vat_amount: function(frm, cdt, cdn) {
        // In Amount mode: recalculate header total when user edits this field
        sync_custom_totals(frm);
    },

    custom_total: function(frm, cdt, cdn) {
        // Total is derived, never authoritative: re-derive it (and the VAT that
        // hangs off it) exactly as the server does on save.
        sync_custom_totals(frm);
    },

    items_remove: function(frm) {
        sync_custom_totals(frm);
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
        setTimeout(() => sync_custom_totals(frm), 500);
    },
    
    tax_amount: function(frm, cdt, cdn) {
        sync_custom_totals(frm);
    },
    
    taxes_add: function(frm) {
        sync_custom_totals(frm);
    },
    
    taxes_remove: function(frm) {
        sync_custom_totals(frm);
    }
});

/**
 * Single source of truth for every custom total on the form. Mirrors the server
 * (salesinvoice_taxes.before_save_salesinvoice) field for field:
 *
 *     item.custom_total      = base_net_amount + custom_excise_value
 *     item.custom_vat_amount = custom_total x 13%          (VAT 13%)
 *                            = 0                           (VAT 0%)
 *                            = whatever the user typed     (Amount)
 *     Amount before VAT      = sum(custom_total)
 *
 * Values are assigned directly rather than through frappe.model.set_value: it
 * must be safe to run during form load (no dirtying a clean document) and from
 * inside ERPNext's own recalculation (no re-entering the trigger that called
 * us). The grid is only refreshed when a figure actually moved.
 */
function sync_custom_totals(frm) {
    if (!frm || !frm.doc || frm.doc.doctype !== "Sales Invoice") return;

    const is_return = !!frm.doc.is_return;
    let total_including_excise = 0;
    let vat_total = 0;
    let net_total = 0;
    let excise_total = 0;
    let changed = false;

    (frm.doc.items || []).forEach(function(item) {
        const base_net_amount = flt(item.base_net_amount);
        const excise = flt(item.custom_excise_value);
        const total = flt(base_net_amount + excise, 5);

        const mode = item.custom_vat_apply_on || "VAT 13%";
        let vat_rate;
        let vat;

        if (mode === "VAT 13%") {
            vat_rate = 13;
            vat = flt((total * 13) / 100, 5);
        } else if (mode === "VAT 0%") {
            vat_rate = 0;
            vat = 0;
        } else {
            // Amount: manual entry, never recalculated
            vat_rate = 0;
            vat = flt(item.custom_vat_amount, 5);
        }

        if (is_return && vat > 0) vat = -Math.abs(vat);

        if (flt(item.custom_total, 5) !== total) { item.custom_total = total; changed = true; }
        if (flt(item.custom_vat_rate) !== vat_rate) { item.custom_vat_rate = vat_rate; changed = true; }
        if (flt(item.custom_vat_amount, 5) !== vat) { item.custom_vat_amount = vat; changed = true; }

        total_including_excise += total;
        vat_total += vat;
        net_total += base_net_amount;
        excise_total += excise;
    });

    frm.doc.custom_total_amount_including_excise = flt(total_including_excise, 5);
    frm.doc.custom_total_vat_amount = flt(vat_total, 5);
    frm.doc.custom_total_amount = flt(net_total, 5);
    frm.doc.custom_excise = flt(excise_total, 5);

    if (changed) frm.refresh_field("items");
    frm.refresh_field("custom_total_amount_including_excise");
    frm.refresh_field("custom_total_vat_amount");
    frm.refresh_field("custom_total_amount");
    frm.refresh_field("custom_excise");
    update_total_amount_preview(frm);
}

/**
 * ERPNext writes item.base_net_amount straight onto the row object inside
 * _calculate_taxes_and_totals, bypassing frappe.model.set_value — so the
 * base_net_amount trigger never fires. The custom totals used to be derived by
 * a 300 ms timer racing that write, and a qty change could leave custom_total
 * (and the VAT computed from it) one edit behind: a row whose Amount had gone
 * to 27,345.13 still showed Total 18,230.09 and VAT 2,369.91 instead of
 * 3,554.87. Chain onto the recalculation itself instead, so we always derive
 * from the base_net_amount ERPNext has just finalised. Idempotent.
 */
function install_custom_totals_hook() {
    const cls = window.erpnext && erpnext.taxes_and_totals;
    if (!cls || cls.prototype.__agi_custom_totals_hook) return;

    const core_calculate = cls.prototype._calculate_taxes_and_totals;
    cls.prototype._calculate_taxes_and_totals = function() {
        const result = core_calculate.apply(this, arguments);
        try {
            sync_custom_totals(this.frm);
        } catch (e) {
            console.error("Error deriving Sales Invoice custom totals:", e);
        }
        return result;
    };
    cls.prototype.__agi_custom_totals_hook = true;
}

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

    sync_pos_payment_amount(frm);
}

/**
 * Core's set_default_payment() (taxes_and_totals.js) fills the default POS
 * payment row's Amount from grand_total, but VAT/excise taxes are only
 * appended server-side on save (see sync_custom_totals above) — before save,
 * grand_total (and anything derived from it, incl. rounded_total) is
 * understated by the tax amount. custom_expected_grand_total already includes
 * VAT+excise, so it is the correct pre-save total to round.
 *
 * The payment row is paid in the ROUNDED figure (not the raw total): ERPNext's
 * own outstanding-amount formula is `(rounded_total or grand_total) - paid`,
 * and it prefers rounded_total whenever rounding is enabled (see
 * sync_pos_rounding, which forces it on for POS-eligible invoices). Paying the
 * unrounded total would leave the rounding paisa sitting in Outstanding as a
 * fake "still owed" balance even though the customer paid in full — so this
 * must round the same way core would (round_based_on_smallest_currency
 * _fraction, a Frappe framework global), not just truncate to 2 decimals.
 */
function sync_pos_payment_amount(frm) {
    if (!frm.doc.is_pos) return;

    const rows = frm.doc.payments || [];
    // The row pulled in from the POS Profile is flagged default=1, but a row
    // added by hand (Add Row) never gets that flag — with only one row on the
    // table there is no ambiguity about which one is "the" payment, so fall
    // back to it instead of silently doing nothing.
    const default_row = rows.find(function(p) { return p.default; })
        || (rows.length === 1 ? rows[0] : null);
    if (!default_row) return;

    const raw_total = flt(frm.doc.custom_expected_grand_total);
    const rounded_total = frm.doc.disable_rounded_total
        ? raw_total
        : round_based_on_smallest_currency_fraction(
            raw_total, frm.doc.currency, precision('grand_total'));

    const amount = flt(rounded_total, precision('amount', default_row));
    if (flt(default_row.amount, precision('amount', default_row)) === amount) return;

    frappe.model.set_value(default_row.doctype, default_row.name, 'amount', amount);
    if (frm.cscript && frm.cscript.calculate_paid_amount) {
        frm.cscript.calculate_paid_amount();
    }
}

/**
 * The "Include Payment (POS)" checkbox (is_pos) is only shown, via a Customize
 * Form depends_on Property Setter, when Company is Grishma Enterprises and
 * Branch is Anamnagar (GEPL-Branch-00001) — that Property Setter condition is
 * mirrored here. depends_on only ever hides/shows a field; it never clears its
 * value. So switching Branch away from Anamnagar hides the is_pos checkbox but
 * leaves is_pos=1 sitting in the document, which in turn keeps pos_profile
 * visible (it depends on is_pos's value, not on branch) with a stale profile
 * and a stale POS payment row still attached to an invoice that is no longer
 * eligible for POS at all.
 *
 * Call this whenever Company or Branch changes: if the combination no longer
 * qualifies for POS, explicitly turn is_pos off and drop the payment rows core
 * never clears on its own (core's is_pos handler only calls set_pos_data() when
 * is_pos is truthy — see sales_invoice.js Controller.set_pos_data — turning it
 * off just triggers a plain refresh, payments included).
 */
function is_pos_eligible(frm) {
    return frm.doc.company === "Grishma Enterprises Pvt. Ltd."
        && frm.doc.custom_branch === "GEPL-Branch-00001";
}

function enforce_pos_scope(frm) {
    if (is_pos_eligible(frm) || !frm.doc.is_pos) return;

    frm.set_value("is_pos", 0);
    frm.set_value("pos_profile", "");
    frm.clear_table("payments");
    frm.refresh_field("payments");
}

/**
 * Rounding is skipped by default (disable_rounded_total defaults to 1 on a new
 * invoice), which leaves rounded_total blank/unused. Force rounding ON only
 * when ALL three hold: Company + Branch (Grishma Enterprises — Anamnagar) AND
 * is_pos=1 — so the POS payment row (sync_pos_payment_amount) is always paid
 * in the rounded figure and ERPNext's own outstanding-amount formula — which
 * prefers rounded_total whenever it's populated — never shows the rounding
 * paisa as a leftover "still owed" balance.
 *
 * Runs both directions: forces rounding ON while all three hold, and back OFF
 * the moment any one of them stops holding (Company/Branch changes away, or
 * is_pos gets unticked) — same self-correcting pattern as enforce_pos_scope.
 */
function sync_pos_rounding(frm) {
    const want_disabled = (is_pos_eligible(frm) && cint(frm.doc.is_pos)) ? 0 : 1;
    if (cint(frm.doc.disable_rounded_total) !== want_disabled) {
        frm.set_value("disable_rounded_total", want_disabled);
    }
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

    if (changed) sync_custom_totals(frm);
}

function set_due_date_from_customer(frm) {
    if (!frm.doc.customer || !frm.doc.posting_date) return;
    const posting_date = frm.doc.posting_date;
    frappe.db.get_value('Customer', frm.doc.customer, 'custom_days_limit', function(data) {
        const days = (data && data.custom_days_limit) ? data.custom_days_limit : 0;
        frm.set_value('due_date', frappe.datetime.add_days(posting_date, days));

    });
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

// ── Credit position banner ─────────────────────────────────────────────────────
// Persistent strip under the title bar showing the customer's credit limits vs
// current usage, visible while the invoice is being filled. Display only — the
// server-side validate hook is what actually enforces the limits.

// Stands in for a figure we do not have yet.
const CREDIT_DASH = "—";

// ---------------------------------------------------------------------------
// The people who read this strip all day are counter staff, many of them thirty
// years in the company. It used to be one dense line of pipe-separated
// fragments with the arithmetic buried in brackets -- readable only if you
// already knew what it said. It is now a row of tiles: one fact each, a plain
// label above and a large number below, with the verdict spelled out in words
// on the line above rather than signalled by colour alone.
//
// Rules for anything added here:
//   * one fact per tile, never two joined by a separator;
//   * the number is the biggest thing in the tile;
//   * say what is wrong in words -- colour is the second signal, never the only
//     one, and red on grey is the first thing tired eyes lose;
//   * colours come from Frappe's CSS variables so dark mode still works.
// ---------------------------------------------------------------------------

// One tile. `sub` is the small print under the number -- the limit it is tested
// against, or the working behind it. `breached` tints the whole tile, so a
// customer over two limits shows two red tiles even though the server throws on
// only the first.
function credit_tile(label, value, sub, breached) {
    const tint = breached ? "var(--red-50, rgba(220,38,38,.08))" : "transparent";
    const edge = breached ? "var(--red-500)" : "var(--gray-300)";
    const num  = breached ? "var(--red-600, var(--red-500))" : "var(--text-color)";
    return `
        <div style="flex:1 1 150px;min-width:135px;padding:6px 12px;border-left:3px solid ${edge};background:${tint};border-radius:0 3px 3px 0;">
            <div style="font-size:.7rem;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted);white-space:nowrap;">${label}</div>
            <div style="font-size:1.35rem;font-weight:700;line-height:1.25;color:${num};">${value}</div>
            <div style="font-size:.75rem;color:var(--text-muted);min-height:1.05em;">${sub || ""}</div>
        </div>`;
}

// The tiles drawn when there is nothing to show yet. Same shape and the same
// height as the real thing, because injecting the strip after the round trip
// lands pushes the whole form down a row -- and that happens mid-keystroke for
// anyone typing quickly.
function credit_placeholder_tiles() {
    return [
        credit_tile("Customer owes", CREDIT_DASH, "", false),
        credit_tile("Can still bill", CREDIT_DASH, "", false),
        credit_tile("Unpaid bills", CREDIT_DASH, "", false),
        credit_tile("Oldest unpaid bill", CREDIT_DASH, "", false)
    ].join("");
}

// `status` is the sentence on the top line -- it must say what is wrong, not
// just that something is. `tone` is "ok", "blocked" or "muted"; muted is for
// the states where there are no figures to judge yet.
function set_credit_banner(frm, status, tone, tiles) {
    const edge = tone === "blocked" ? "var(--red-500)"
               : tone === "ok"      ? "var(--green-500)"
               : "var(--gray-300)";
    const status_colour = tone === "blocked" ? "var(--red-600, var(--red-500))"
                        : tone === "ok"      ? "var(--green-600, var(--green-500))"
                        : "var(--text-muted)";

    frm.dashboard.set_headline(
        `<div style="border-left:5px solid ${edge};background:var(--bg-light-gray);border-radius:4px;padding:8px 12px;color:var(--text-color);">
            <div style="font-size:.95rem;font-weight:700;color:${status_colour};margin-bottom:6px;">${status}</div>
            <div style="display:flex;flex-wrap:wrap;gap:4px 8px;align-items:stretch;">${tiles}</div>
        </div>`
    );
}

function fetch_credit_banner(frm) {
    // Cached figures belong to the customer they were fetched for. Keep them
    // across a posting_date change so the strip does not flicker, but drop
    // them the moment the customer changes or the numbers on screen would be
    // the previous customer's.
    if (frm.__credit_for !== frm.doc.customer) {
        frm.__credit_position = null;
        frm.__credit_for = frm.doc.customer;
    }

    if (!frm.doc.customer || frm.doc.docstatus !== 0 || frm.doc.is_return) {
        frm.__credit_position = null;
        render_credit_banner(frm);
        return;
    }

    // Draw immediately, before the call, so the layout is already settled when
    // the answer arrives — the callback only swaps text into a strip that is
    // there.
    render_credit_banner(frm);

    // customer and posting_date can both fire this within a few milliseconds.
    // Only the newest response may paint; an earlier one landing late would
    // otherwise overwrite it with figures for the wrong date.
    const seq = (frm.__credit_seq = (frm.__credit_seq || 0) + 1);

    frappe.call({
        method: "avinashgroup_app.custom_code.SalesInvoice.credit_control.get_credit_position",
        args: {
            customer: frm.doc.customer,
            // Same day the server will age the oldest bill from.
            posting_date: frm.doc.posting_date,
            invoice: frm.doc.name
        },
        callback: function(r) {
            if (seq !== frm.__credit_seq) return;
            frm.__credit_position = r.message || null;
            frm.__credit_for = frm.doc.customer;
            render_credit_banner(frm);
        }
    });
}

function render_credit_banner(frm) {
    // Clear before rendering so overlapping fetch_credit_banner calls
    // (customer + posting_date can both fire it in quick succession) never
    // stack multiple banner divs on top of each other.
    frm.dashboard.clear_headline();

    // A submitted or cancelled invoice is past the point the limits apply and
    // is not being edited, so there is no layout to protect — leave it bare.
    if (frm.doc.docstatus !== 0) return;

    // Every remaining path below draws SOMETHING. Nothing here may return
    // without a headline, or the form jumps again.
    if (frm.doc.is_return) {
        set_credit_banner(frm, "Credit limits do not apply to returns",
                          "muted", credit_placeholder_tiles());
        return;
    }
    if (!frm.doc.customer) {
        set_credit_banner(frm, "Select a customer to see their credit position",
                          "muted", credit_placeholder_tiles());
        return;
    }

    const p = frm.__credit_position;
    if (!p) {
        set_credit_banner(frm, "Checking this customer's credit…",
                          "muted", credit_placeholder_tiles());
        return;
    }
    if (!p.has_limits) {
        set_credit_banner(frm, "No credit limits set for this customer",
                          "muted", credit_placeholder_tiles());
        return;
    }

    const rs = v => format_currency(v, frm.doc.currency || "NPR");

    // p.exposure is outstanding MINUS whatever advance the bills did not use,
    // so it goes negative for a prepaid customer. The limit is headroom on top
    // of that, which is why available_credit can exceed the limit itself.
    const projected = flt(p.exposure) + flt(frm.doc.grand_total);

    // The server evaluates count and days on its own; only the amount check
    // depends on grand_total, so that one is recomputed here as the user types
    // rather than costing a round trip per keystroke. `>` matches the server —
    // landing exactly on the limit is allowed.
    const amount_exceeded = p.amount_limit && projected > flt(p.amount_limit);

    // Same precedence the server throws in — count, then days, then amount.
    let blocked_by = null;
    if (p.count_exceeded) blocked_by = "count";
    else if (p.days_exceeded) blocked_by = "days";
    else if (amount_exceeded) blocked_by = "amount";

    // Mark EVERY breached limit, not just the blocking one. The server throws
    // on the first by precedence, but a customer can be over two limits at
    // once and the banner should say so — showing days unmarked while it is
    // 2,000 days overdue, just because the bill count tripped first, is how
    // this was wrong before.
    const over = {
        count: !!p.count_exceeded,
        days: !!p.days_exceeded,
        amount: !!amount_exceeded
    };

    const tiles = [];

    // What the customer owes. p.exposure, not p.outstanding or
    // p.gross_outstanding: it is the exact quantity the amount limit is tested
    // against (see `projected`), and FIFO leaves leftover_advance at 0 whenever
    // any bill is uncovered, so it equals p.outstanding for everyone who
    // actually owes money. It only differs for a prepaid customer, where it
    // correctly goes negative.
    //
    // gross_outstanding would be wrong here: _unpaid_after_advance filters
    // is_return = 0, so it counts no credit notes and would tell a customer who
    // returned goods they owe more than they do.
    //
    // Floored at 0 rather than flipping to an "Advance balance" label: the tile
    // keeps the same heading on every invoice, so an operator scanning the row
    // reads one column and not two. A prepaid customer's advance is not lost
    // from the screen — it moves to the "Can still bill" tile's small print.
    const owed = Math.max(0, flt(p.exposure));
    tiles.push(credit_tile(
        "Customer owes", rs(owed),
        flt(p.je_debit) ? `includes ${rs(p.je_debit)} journal debit` : "",
        false));

    if (p.amount_limit) {
        const remaining = flt(p.amount_limit) - projected;
        // Spell out where the headroom comes from when the customer is prepaid,
        // so the figure on screen can be tied back to their ledger balance.
        const basis = flt(p.leftover_advance)
            ? `advance left ${rs(p.leftover_advance)} + limit ${rs(p.amount_limit)}`
            : `limit ${rs(p.amount_limit)}`;
        tiles.push(credit_tile(
            "Can still bill",
            remaining >= 0 ? rs(remaining) : `over by ${rs(-remaining)}`,
            basis, over.amount));
    }

    if (p.bill_limit) {
        // The server throws on >=, so the last permitted bill count is one
        // below the limit. Say that, rather than "N of N allowed" reading fine
        // at the exact point the save fails.
        tiles.push(credit_tile(
            "Unpaid bills", `${p.unpaid_count}`,
            `blocked at ${p.bill_limit}`, over.count));
    }

    // Drawn whenever there is an age to report OR a limit to report it against,
    // so a customer with no days limit keeps the bill age they could always see
    // here — it is useful on its own, it just cannot block anything.
    if (p.days_limit || p.oldest_date) {
        // p.days_used is the age of the oldest bill the customer's credits
        // could NOT cover, already floored to 0 by the server when the leftover
        // is too small to be worth ageing (DAYS_MATERIALITY_FLOOR).
        tiles.push(credit_tile(
            "Oldest unpaid bill",
            p.days_used ? `${p.days_used} days` : "none",
            p.days_limit ? `blocked at ${p.days_limit} days` : "no days limit set",
            over.days));
    }

    // The verdict, in words. "Blocked" alone leaves the operator hunting the
    // row for a red tile; naming the reason means they can act on it without
    // reading anything else.
    let status = "✓  Credit OK";
    let tone = "ok";
    if (blocked_by === "count") {
        status = `⛔  Sale blocked — ${p.unpaid_count} unpaid bills, limit is ${p.bill_limit}`;
        tone = "blocked";
    } else if (blocked_by === "days") {
        status = `⛔  Sale blocked — oldest unpaid bill is ${p.days_used} days old, limit is ${p.days_limit} days`;
        tone = "blocked";
    } else if (blocked_by === "amount") {
        const over_by = projected - flt(p.amount_limit);
        status = `⛔  Sale blocked — this invoice goes ${rs(over_by)} past the credit limit`;
        tone = "blocked";
    }

    set_credit_banner(frm, status, tone, tiles.join(""));
}
