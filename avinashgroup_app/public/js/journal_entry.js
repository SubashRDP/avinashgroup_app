// Cache: account → [vehicle names]
const je_account_vehicle_cache = {};

frappe.ui.form.on('Journal Entry', {
    onload: function(frm) {
        setup_vehicle_query(frm);
    },

    refresh: function(frm) {
        setup_vehicle_query(frm);
        prefetch_vehicles_for_existing_rows(frm);
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

function setup_vehicle_query(frm) {
    frm.set_query('custom_subtype', 'accounts', function(doc, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row || !row.account) {
            return { filters: { name: ['in', ['__no_match__']] } };
        }
        const vehicles = je_account_vehicle_cache[row.account];
        if (!vehicles || vehicles.length === 0) {
            return { filters: { name: ['in', ['__no_match__']] } };
        }
        return { filters: { name: ['in', vehicles] } };
    });
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
        return (account_doc.custom_sub_type_list || []).map(r => r.sub_type_list).filter(Boolean);
    }).catch(() => []);
}
