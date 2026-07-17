// Cache: account → [vehicle names]
const je_account_vehicle_cache = {};

// An entry needs at least one debit and one credit line to balance.
const DEFAULT_ACCOUNT_ROWS = 2;

frappe.ui.form.on('Journal Entry', {
    onload: function(frm) {
        setTimeout(() => setup_vehicle_query(frm), 50);
    },

    refresh: function(frm) {
        setTimeout(() => setup_vehicle_query(frm), 50);
        prefetch_vehicles_for_existing_rows(frm);
        add_default_account_rows(frm);
    },

    accounts_on_form_rendered: function(frm) {
        bind_open_row_query(frm);
    }
});

frappe.ui.form.on('Journal Entry Account', {
    account: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        frappe.model.set_value(cdt, cdn, 'custom_subtype', '');

        if (!row.account) return;

        if (je_account_vehicle_cache[row.account] !== undefined) return;

        get_vehicles_for_account(row.account).then(vehicles => {
            je_account_vehicle_cache[row.account] = vehicles;
        });
    }
});

// ── Default rows on a blank entry ──────────────────────────────
// Only for an empty new doc: amended, duplicated, mapped-from-another-doc and
// template-driven entries arrive with their accounts table already filled, and
// picking a Journal Entry Template later clears the table anyway (core
// update_jv_details), so the blank rows never survive to duplicate template rows.
function add_default_account_rows(frm) {
    if (!frm.is_new()) return;
    // Run once per new doc: refresh fires repeatedly, and after the user
    // deletes the seeded rows we must not keep re-adding them.
    if (frm.__default_rows_added) return;
    if ((frm.doc.accounts || []).length) return;

    frm.__default_rows_added = true;
    for (let i = 0; i < DEFAULT_ACCOUNT_ROWS; i++) {
        frm.add_child('accounts');
    }
    frm.refresh_field('accounts');
}

// ── Inline grid rows ──────────────────────────────────────────
function setup_vehicle_query(frm) {
    frm.set_query('custom_subtype', 'accounts', function(doc, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row || !row.account) {
            return { filters: { name: ['in', ['__no_match__']] } };
        }
        const vehicles = je_account_vehicle_cache[row.account];
        if (vehicles === undefined) {
            get_vehicles_for_account(row.account).then(v => {
                je_account_vehicle_cache[row.account] = v;
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
        if (!row_doc || !row_doc.account) {
            return { filters: { name: ['in', ['__no_match__']] } };
        }
        const vehicles = je_account_vehicle_cache[row_doc.account];
        if (vehicles === undefined) {
            get_vehicles_for_account(row_doc.account).then(v => {
                je_account_vehicle_cache[row_doc.account] = v;
            });
            return {};
        }
        if (vehicles.length === 0) {
            return { filters: { name: ['in', ['__no_match__']] } };
        }
        return { filters: { name: ['in', vehicles] } };
    };

    // Only set on control instance — don't pollute the shared df.get_query
    grid_form.fields_dict.custom_subtype.get_query = get_query;
}

function prefetch_vehicles_for_existing_rows(frm) {
    if (!frm.doc.accounts || !frm.doc.accounts.length) return;

    const unique_accounts = [...new Set(
        frm.doc.accounts.map(r => r.account).filter(Boolean)
    )];

    unique_accounts.forEach(account => {
        if (je_account_vehicle_cache[account] !== undefined) return;
        get_vehicles_for_account(account).then(vehicles => {
            je_account_vehicle_cache[account] = vehicles;
        });
    });
}

function get_vehicles_for_account(account) {
    return frappe.db.get_doc('Account', account).then(account_doc => {
        return (account_doc.custom_sub_type_list || []).map(r => r.vehicle_list).filter(Boolean);
    }).catch(() => []);
}
