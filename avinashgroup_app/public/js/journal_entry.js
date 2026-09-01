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
        keep_minimum_account_rows(frm);
    },

    accounts_on_form_rendered: function(frm) {
        bind_open_row_query(frm);
    }
});

frappe.ui.form.on('Journal Entry Account', {
    // GridRow.remove fires `<fieldname>_remove` against the CHILD doctype, not
    // the parent -- registering this on 'Journal Entry' looks right and never
    // runs. It fires after the row is gone, so doc.accounts is already the
    // post-delete list.
    accounts_remove: function(frm) {
        keep_minimum_account_rows(frm, { announce: true });
    },

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

// ── Always at least two account rows ───────────────────────────
// A journal is double-entry, so the table is kept topped up to two rows: on a
// blank new entry, and again if someone deletes their way below two.
//
// This deliberately replaces the earlier seed-once behaviour, which added two
// rows to a new entry and then stood by if they were deleted. Requested so the
// form always presents a debit line and a credit line.
//
// Amended, duplicated and mapped-from-another-doc entries arrive with their
// table already filled, so they are past the minimum and nothing is added.
// Draft only -- a submitted or cancelled entry is never touched.
function keep_minimum_account_rows(frm, { announce = false } = {}) {
    if (frm.doc.docstatus !== 0) return;

    const count = (frm.doc.accounts || []).length;
    if (count >= DEFAULT_ACCOUNT_ROWS) return;

    for (let i = count; i < DEFAULT_ACCOUNT_ROWS; i++) {
        frm.add_child('accounts');
    }
    frm.refresh_field('accounts');

    // Only when a deletion caused it -- otherwise every refresh of a blank
    // entry would pop a message for rows the user never asked about.
    if (announce) {
        frappe.show_alert({
            message: __('An entry needs at least {0} account rows', [DEFAULT_ACCOUNT_ROWS]),
            indicator: 'orange',
        });
    }
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
