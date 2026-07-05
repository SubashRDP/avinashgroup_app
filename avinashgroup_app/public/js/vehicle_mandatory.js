// Per-row mandatory Vehicle (custom_subtype) check for vehicle-expense accounts.
// Deliberately NOT done via a mandatory_depends_on property setter: Frappe's grid
// mutates the shared docfield (grid_row.js set_dependant_property → df.reqd = 1)
// once any row matches, which flags the Vehicle column on every row. This checks
// each row itself and only blocks the offending ones. Server-side counterpart:
// avinashgroup_app/custom_code/vehicle_mandatory.py (patterns must stay in sync).
(() => {
    const VEHICLE_ACCOUNT_PATTERNS = [
        'Fuel Expenses',
        'R & M - Vehicles',
        'Other Vehicle Expenses',
    ];

    const requires_vehicle = (account) =>
        !!account && VEHICLE_ACCOUNT_PATTERNS.some((p) => account.includes(p));

    function check_vehicle_rows(frm, table_field, account_field) {
        const missing = (frm.doc[table_field] || []).filter(
            (row) => requires_vehicle(row[account_field]) && !row.custom_subtype
        );
        if (!missing.length) return;

        const lines = missing.map((row) =>
            __('Row #{0}: Vehicle is mandatory for account {1}', [
                row.idx,
                frappe.bold(row[account_field]),
            ])
        );
        frappe.throw({
            title: __('Vehicle Required'),
            message: lines.join('<br>'),
        });
    }

    frappe.ui.form.on('Journal Entry', {
        validate(frm) {
            check_vehicle_rows(frm, 'accounts', 'account');
        },
    });

    frappe.ui.form.on('Purchase Invoice', {
        validate(frm) {
            check_vehicle_rows(frm, 'items', 'expense_account');
        },
    });
})();
