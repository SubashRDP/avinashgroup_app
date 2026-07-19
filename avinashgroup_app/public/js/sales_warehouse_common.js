// Warehouse auto-fetch for selling hierarchy: Quotation, Sales Order, Delivery Note
const SELLING_WAREHOUSE_DOCTYPES = ["Quotation", "Sales Order", "Delivery Note"];

const SELLING_ITEM_DOCTYPES = {
    "Quotation": "Quotation Item",
    "Sales Order": "Sales Order Item",
    "Delivery Note": "Delivery Note Item"
};

// Register item_code and before_save handlers for all selling hierarchy doctypes
SELLING_WAREHOUSE_DOCTYPES.forEach(function(doctype) {
    const item_doctype = SELLING_ITEM_DOCTYPES[doctype];

    frappe.ui.form.on(item_doctype, {
        item_code: function(frm, cdt, cdn) {
            const row = locals[cdt][cdn];
            if (!row || !row.item_code) return;

            // Fetch our warehouse in the background
            const wh_promise = _fetch_selling_wh(row.item_code, frm.doc.custom_branch);

            // SYNCHRONOUSLY wrap frappe.call to inject warehouse into get_item_details response
            const _orig = frappe.call;
            let _restored = false;
            const _restore = () => { if (!_restored) { frappe.call = _orig; _restored = true; } };
            frappe.call = function(opts) {
                if (opts && opts.method && opts.method.includes('get_item_details')) {
                    const _cb = opts.callback;
                    opts.callback = async function(r) {
                        // Never let a failed warehouse lookup abort ERPNext's
                        // callback — it applies uom/rate/description/conversion
                        // factor to the row. See sales_invoice.js for details.
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

    frappe.ui.form.on(doctype, {
        before_save: function(frm) {
            return force_all_selling_warehouses(frm);
        }
    });
});


/**
 * Resolve the selling warehouse for an item, preferring a branch-specific
 * override (Item.custom_branch_wise_warehouse) then falling back to the item's
 * custom_selling_warehouse.
 *
 * Single source of truth: this file is loaded globally via app_include_js, so
 * every selling doctype (Quotation, Sales Order, Delivery Note) AND sales_invoice.js
 * (loaded per-form after this file) can rely on it. Do NOT redefine it elsewhere.
 */
async function _fetch_selling_wh(item_code, custom_branch) {
    // Must never reject: this promise is awaited inside the get_item_details
    // callback wrapper, and a rejection there would stop item details (uom,
    // rate, description, conversion factor) from being applied to the row.
    try {
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
    } catch (e) {
        console.warn('selling warehouse lookup failed for', item_code, e);
        return '';
    }
}


/**
 * Before save: sweep all item rows and force warehouse = custom_selling_warehouse.
 * Only overrides if custom_selling_warehouse is set — preserves manual user selection.
 */
async function force_all_selling_warehouses(frm) {
    if (!frm.doc.items || !frm.doc.items.length) return;

    const custom_branch = frm.doc.custom_branch;
    const item_codes = [...new Set(frm.doc.items.map(r => r.item_code).filter(Boolean))];
    const warehouse_map = {};

    await Promise.all(item_codes.map(async (item_code) => {
        warehouse_map[item_code] = await _fetch_selling_wh(item_code, custom_branch);
    }));

    for (const item of frm.doc.items) {
        const warehouse = item.item_code ? (warehouse_map[item.item_code] || '') : '';
        // On save: only override if custom_selling_warehouse is set — preserves manual selection
        if (warehouse && item.warehouse !== warehouse) {
            await frappe.model.set_value(item.doctype, item.name, 'warehouse', warehouse);
        }
    }
    frm.refresh_field('items');
}
