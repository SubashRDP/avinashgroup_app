// Cache: item_code → [vehicle names]
const item_vehicle_cache = {};

frappe.ui.form.on('Purchase Invoice', {
    onload: function(frm) {
        // setTimeout so we win the race against company_filter.js (which also uses setTimeout 0)
        setTimeout(() => setup_vehicle_query(frm), 50);

        // Covers returns created via the "Return / Debit Note" button (is_return
        // is already 1 when the mapped doc opens, so the field trigger never fires)
        if (frm.is_new()) {
            set_purchase_type_for_return(frm);
        }
    },

    refresh: function(frm) {
        setTimeout(() => setup_vehicle_query(frm), 50);
        prefetch_vehicles_for_existing_rows(frm);
    },

    is_return: function(frm) {
        set_purchase_type_for_return(frm);
    },

    items_on_form_rendered: function(frm) {
        bind_open_row_query(frm);
    }
});

frappe.ui.form.on('Purchase Invoice Item', {
    item_code: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        frappe.model.set_value(cdt, cdn, 'custom_subtype', '');

        if (!row.item_code) return;

        if (item_vehicle_cache[row.item_code] !== undefined) return;

        get_vehicles_for_item(row.item_code).then(vehicles => {
            item_vehicle_cache[row.item_code] = vehicles;
        });
    }
});

// ── Purchase Type for returns ─────────────────────────────────
function set_purchase_type_for_return(frm) {
    if (frm.doc.is_return) {
        if (frm.doc.custom_purchase_type !== 'Purchase Return') {
            frm.set_value('custom_purchase_type', 'Purchase Return');
        }
    } else if (frm.doc.custom_purchase_type === 'Purchase Return') {
        frm.set_value('custom_purchase_type', '');
    }
}

// ── Inline grid rows ──────────────────────────────────────────
function setup_vehicle_query(frm) {
    frm.set_query('custom_subtype', 'items', function(doc, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row || !row.item_code) {
            return { filters: { name: ['in', ['__no_match__']] } };
        }
        const vehicles = item_vehicle_cache[row.item_code];
        if (vehicles === undefined) {
            get_vehicles_for_item(row.item_code).then(v => {
                item_vehicle_cache[row.item_code] = v;
            });
            return {};
        }
        if (vehicles.length === 0) {
            return { filters: { name: ['in', ['__no_match__']] } };
        }
        return { filters: { name: ['in', vehicles] } };
    });
}

// ── Expanded dialog rows ──────────────────────────────────────
function bind_open_row_query(frm) {
    const grid_row = frm.cur_grid;
    const grid_form = grid_row && grid_row.grid_form;
    if (!grid_form || !grid_form.fields_dict || !grid_form.fields_dict.custom_subtype) return;

    const get_query = function() {
        const row_doc = grid_row.doc;
        if (!row_doc || !row_doc.item_code) {
            return { filters: { name: ['in', ['__no_match__']] } };
        }
        const vehicles = item_vehicle_cache[row_doc.item_code];
        if (vehicles === undefined) {
            get_vehicles_for_item(row_doc.item_code).then(v => {
                item_vehicle_cache[row_doc.item_code] = v;
            });
            return {};
        }
        if (vehicles.length === 0) {
            return { filters: { name: ['in', ['__no_match__']] } };
        }
        return { filters: { name: ['in', vehicles] } };
    };

    // Only set on the control instance — NEVER on df.get_query
    // (df is shared with the inline grid; polluting it breaks the inline filter)
    grid_form.fields_dict.custom_subtype.get_query = get_query;
}

function prefetch_vehicles_for_existing_rows(frm) {
    if (!frm.doc.items || !frm.doc.items.length) return;

    const unique_items = [...new Set(
        frm.doc.items.map(r => r.item_code).filter(Boolean)
    )];

    unique_items.forEach(item_code => {
        if (item_vehicle_cache[item_code] !== undefined) return;
        get_vehicles_for_item(item_code).then(vehicles => {
            item_vehicle_cache[item_code] = vehicles;
        });
    });
}

function get_vehicles_for_item(item_code) {
    return frappe.db.get_doc('Item', item_code).then(item_doc => {
        let expense_account = null;
        for (const d of (item_doc.item_defaults || [])) {
            if (d.expense_account) { expense_account = d.expense_account; break; }
        }
        if (!expense_account) return [];

        return frappe.db.get_doc('Account', expense_account).then(account_doc => {
            return (account_doc.custom_sub_type_list || []).map(r => r.vehicle_list).filter(Boolean);
        });
    }).catch(() => []);
}
