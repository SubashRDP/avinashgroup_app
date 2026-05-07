// Common VAT + Excise handler for selling documents (Quotation, Sales Order, Delivery Note).
// Sales Invoice has its own handler in sales_invoice.js — do NOT merge.

const SELLING_TAX_DOCTYPES = ["Quotation", "Sales Order", "Delivery Note"];

const SELLING_TAX_ITEM_DOCTYPES = {
    "Quotation": "Quotation Item",
    "Sales Order": "Sales Order Item",
    "Delivery Note": "Delivery Note Item"
};

// Doctypes where is_return can be true
const SELLING_TAX_RETURN_DOCTYPES = ["Delivery Note"];

// Register parent-level handlers for all 3 doctypes
SELLING_TAX_DOCTYPES.forEach(function(doctype) {
    frappe.ui.form.on(doctype, {

        onload: function(frm) {
            selling_taxes_onload(frm);
        },

        refresh: function(frm) {
            selling_taxes_refresh(frm);
        },

        base_total_taxes_and_charges: function(frm) {
            selling_calculate_total(frm);
        },

        base_grand_total: function(frm) {
            selling_calculate_total(frm);
        },

        taxes_and_charges: function(frm) {
            setTimeout(() => {
                selling_calculate_vat_total(frm);
                selling_calculate_total(frm);
            }, 500);
        },

        total_advance: function(frm) {
            selling_calculate_total(frm);
        }
    });

    // Register item-level handlers
    frappe.ui.form.on(SELLING_TAX_ITEM_DOCTYPES[doctype], {

        item_code: function(frm, cdt, cdn) {
            const row = locals[cdt][cdn];
            if (!row || !row.item_code) return;

            frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'VAT 13%').then(() => {
                frappe.model.set_value(cdt, cdn, 'custom_vat_rate', 13);
                frappe.after_ajax(() => selling_toggle_vat_fields(frm, cdt, cdn));
                frm.refresh_field('items');
            });
        },

        qty: function(frm, cdt, cdn) {
            setTimeout(() => selling_calculate_item_custom_total(frm, cdt, cdn), 300);
            setTimeout(() => selling_apply_return_signs(frm, cdt, cdn), 350);
            frm.refresh_field('items');
        },

        rate: function(frm, cdt, cdn) {
            setTimeout(() => selling_calculate_item_custom_total(frm, cdt, cdn), 300);
            frm.refresh_field('items');
        },

        base_net_amount: function(frm, cdt, cdn) {
            selling_calculate_item_custom_total(frm, cdt, cdn);
            frm.refresh_field('items');
        },

        custom_excise_value: function(frm, cdt, cdn) {
            selling_calculate_item_custom_total(frm, cdt, cdn);
            frm.refresh_field('items');
        },

        custom_vat_apply_on: async function(frm, cdt, cdn) {
            const row = locals[cdt][cdn];

            if (row.custom_vat_apply_on === 'VAT 13%') {
                await frappe.model.set_value(cdt, cdn, 'custom_vat_rate', 13);
            } else {
                await frappe.model.set_value(cdt, cdn, 'custom_vat_rate', 0);
            }

            selling_calculate_item_vat_amount(frm, cdt, cdn);
            frappe.after_ajax(() => selling_toggle_vat_fields(frm, cdt, cdn));
        },

        custom_vat_rate: function(frm, cdt, cdn) {
            frm.refresh_field('items');
        },

        custom_vat_amount: function(frm, cdt, cdn) {
            selling_calculate_vat_total(frm);
            selling_apply_return_signs(frm, cdt, cdn);
            frm.refresh_field('items');
        },

        custom_total: function(frm, cdt, cdn) {
            selling_calculate_total_amount_including_excise(frm);
            selling_calculate_item_vat_amount(frm, cdt, cdn);
            selling_apply_return_signs(frm, cdt, cdn);
            frm.refresh_field('items');
        },

        items_remove: function(frm) {
            selling_calculate_total(frm);
            selling_calculate_total_amount_including_excise(frm);
            selling_calculate_vat_total(frm);
            frm.refresh_field('items');
        },

        items_add: function(frm, cdt, cdn) {
            frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'VAT 13%').then(() => {
                frappe.after_ajax(() => selling_toggle_vat_fields(frm, cdt, cdn));
            });
        }
    });
});

// Also register taxes table handlers for all 3
SELLING_TAX_DOCTYPES.forEach(function(doctype) {
    frappe.ui.form.on("Sales Taxes and Charges", {
        tax_amount: function(frm) {
            if (SELLING_TAX_DOCTYPES.includes(frm.doctype)) {
                selling_calculate_vat_total(frm);
            }
        },
        taxes_add: function(frm) {
            if (SELLING_TAX_DOCTYPES.includes(frm.doctype)) {
                selling_calculate_vat_total(frm);
            }
        },
        taxes_remove: function(frm) {
            if (SELLING_TAX_DOCTYPES.includes(frm.doctype)) {
                selling_calculate_vat_total(frm);
            }
        }
    });
});


// ---------------------------------------------------------------------------
// Onload / refresh
// ---------------------------------------------------------------------------

function selling_taxes_onload(frm) {
    if (frm.doc.items) {
        frm.doc.items.forEach(function(item) {
            const cdt = SELLING_TAX_ITEM_DOCTYPES[frm.doc.doctype];
            selling_toggle_vat_fields(frm, cdt, item.name);
        });
    }
}

function selling_taxes_refresh(frm) {
    if (frm.doc.items) {
        frm.doc.items.forEach(function(item) {
            const cdt = SELLING_TAX_ITEM_DOCTYPES[frm.doc.doctype];
            selling_toggle_vat_fields(frm, cdt, item.name);
        });
    }
}


// ---------------------------------------------------------------------------
// Field visibility
// ---------------------------------------------------------------------------

function selling_toggle_vat_fields(frm, cdt, cdn) {
    if (!frm.fields_dict.items || !frm.fields_dict.items.grid) {
        frappe.after_ajax(() => selling_toggle_vat_fields(frm, cdt, cdn));
        return;
    }

    const grid = frm.fields_dict.items.grid;
    const grid_row = grid.grid_rows_by_docname?.[cdn];

    if (!grid_row) {
        frappe.after_ajax(() => selling_toggle_vat_fields(frm, cdt, cdn));
        return;
    }

    const row = locals[cdt][cdn];
    if (!row) return;

    if (!row.custom_vat_apply_on) {
        frappe.model.set_value(cdt, cdn, 'custom_vat_apply_on', 'VAT 13%');
        row.custom_vat_apply_on = 'VAT 13%';
    }

    if (row.custom_vat_apply_on === 'VAT 13%' || row.custom_vat_apply_on === 'VAT 0%') {
        grid_row.toggle_display('custom_vat_rate', true);
        grid_row.toggle_editable('custom_vat_rate', false);
        grid_row.toggle_display('custom_vat_amount', true);
        grid_row.toggle_editable('custom_vat_amount', false);
    } else if (row.custom_vat_apply_on === 'Amount') {
        grid_row.toggle_display('custom_vat_rate', false);
        grid_row.toggle_editable('custom_vat_rate', false);
        grid_row.toggle_display('custom_vat_amount', true);
        grid_row.toggle_editable('custom_vat_amount', true);
    }
}


// ---------------------------------------------------------------------------
// Item-level calculations
// ---------------------------------------------------------------------------

function selling_calculate_item_custom_total(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row) return;
    const custom_total = flt(flt(row.base_net_amount) + flt(row.custom_excise_value), 5);
    frappe.model.set_value(cdt, cdn, 'custom_total', custom_total);
    // VAT recalculates via custom_total change handler
}

function selling_calculate_item_vat_amount(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row) return;

    const vat_apply_on = row.custom_vat_apply_on || 'VAT 13%';
    const custom_total = flt(row.base_net_amount) + flt(row.custom_excise_value);

    if (vat_apply_on === 'VAT 13%') {
        frappe.model.set_value(cdt, cdn, 'custom_vat_amount', flt((custom_total * 13) / 100, 5));
    } else if (vat_apply_on === 'VAT 0%') {
        frappe.model.set_value(cdt, cdn, 'custom_vat_amount', 0);
    }
    // Amount mode: preserve manual entry

    setTimeout(() => selling_calculate_vat_total(frm), 50);
    selling_apply_return_signs(frm, cdt, cdn);
}


// ---------------------------------------------------------------------------
// Document-level totals
// ---------------------------------------------------------------------------

function selling_calculate_total_amount_including_excise(frm) {
    if (!frm || !frm.doc) return;
    let total = 0;
    (frm.doc.items || []).forEach(item => { total += flt(item.custom_total) || 0; });
    frm.set_value('custom_total_amount_including_excise', flt(total, 5));
    frm.refresh_field('custom_total_amount_including_excise');
}

function selling_calculate_vat_total(frm) {
    if (!frm || !frm.doc) return;
    let vat_total = 0;
    (frm.doc.items || []).forEach(item => { vat_total += flt(item.custom_vat_amount) || 0; });
    frm.set_value('custom_total_vat_amount', flt(vat_total, 5));
    frm.refresh_field('custom_total_vat_amount');
}

function selling_calculate_total(frm) {
    if (!frm || !frm.doc) return;
    let total_excl_excise = 0;
    let total_excise = 0;
    (frm.doc.items || []).forEach(item => {
        total_excl_excise += flt(item.base_net_amount) || 0;
        total_excise += flt(item.custom_excise_value) || 0;
    });
    frm.doc.custom_total_amount = flt(total_excl_excise, 5);
    frm.doc.custom_excise = flt(total_excise, 5);
    frm.refresh_field('custom_total_amount');
    frm.refresh_field('custom_excise');
    selling_calculate_vat_total(frm);
    selling_calculate_total_amount_including_excise(frm);
}


// ---------------------------------------------------------------------------
// Return sign (Delivery Note only)
// ---------------------------------------------------------------------------

function selling_is_return(frm) {
    return frm && frm.doc && frm.doc.is_return && SELLING_TAX_RETURN_DOCTYPES.includes(frm.doc.doctype);
}

function selling_apply_return_signs(frm, cdt, cdn) {
    if (!selling_is_return(frm)) return;
    const row = locals[cdt][cdn];
    if (!row) return;

    if (flt(row.qty) > 0) {
        frappe.model.set_value(cdt, cdn, 'qty', -Math.abs(flt(row.qty)));
    }
    if (flt(row.custom_vat_amount) > 0) {
        frappe.model.set_value(cdt, cdn, 'custom_vat_amount', -Math.abs(flt(row.custom_vat_amount)));
    }
}
