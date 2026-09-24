/**
 * global_filter.js
 *
 * Row-level company validation only.
 * Fires when a user selects item_code / supplier in a child table row —
 * catches copy-paste that set_query cannot prevent.
 *
 * All link-field dropdown filtering is handled by company_filter.js
 * (config-driven via Company Filter Config DocType).
 *
 * Also: "+ Add" on a filtered list opens a blank form (see bottom of file).
 */

$(document).on("app_ready", function () {
    _setup_item_row_validation();
    _setup_supplier_row_validation();
});


// ── Validate item_code on selection in any child table ────────────────────────
function _setup_item_row_validation() {
    const ITEM_CHILD_DOCTYPES = [
        "Sales Invoice Item",
        "Purchase Order Item",
        "Purchase Invoice Item",
        "Sales Order Item",
        "Delivery Note Item",
        "Purchase Receipt Item",
        "Material Request Item",
        "Supplier Quotation Item",
        "Quotation Item",
        "Stock Entry Detail",
        "Request for Quotation Item",
        "Stock Reconciliation Item",
    ];

    ITEM_CHILD_DOCTYPES.forEach(function (child_doctype) {
        frappe.ui.form.on(child_doctype, {
            item_code: function (frm, cdt, cdn) {
                _validate_row_company(frm, cdt, cdn, "item_code", "Item");
            }
        });
    });
}


// ── Validate supplier on selection in RFQ supplier rows ──────────────────────
function _setup_supplier_row_validation() {
    frappe.ui.form.on("Request for Quotation Supplier", {
        supplier: function (frm, cdt, cdn) {
            _validate_row_company(frm, cdt, cdn, "supplier", "Supplier");
        }
    });
}


/**
 * Generic row-level company validator.
 * Uses _resolve_filter_key from company_filter.js engine so it works
 * correctly for both 'company' and 'custom_company' doctypes.
 */
function _validate_row_company(frm, cdt, cdn, fieldname, linked_doctype) {
    const row = locals[cdt][cdn];
    if (!row || !row[fieldname]) return;

    const parent_company = frm.doc.custom_company || frm.doc.company;
    if (!parent_company) return;

    frappe.model.with_doctype(linked_doctype, function () {
        const filter_key = avinash.filter_engine._resolve_filter_key(linked_doctype);
        if (!filter_key) return;

        frappe.db.get_value(linked_doctype, row[fieldname], filter_key, function (r) {
            if (!r) return;
            const doc_company = r[filter_key];
            if (doc_company && doc_company !== parent_company) {
                const selected = row[fieldname];
                frappe.model.set_value(cdt, cdn, fieldname, "");
                frappe.msgprint({
                    title: __("Company Mismatch"),
                    message: __("{0} <b>{1}</b> does not belong to <b>{2}</b>.",
                        [linked_doctype, selected, parent_company]),
                    indicator: "red"
                });
            }
        });
    });
}


// ── "+ Add" on a filtered list opens a blank form ─────────────────────────────
// Stock Frappe (list_view.js, ListView.make_new_doc) copies every "=" list
// filter into the new document: filter Sales Invoice by Customer = ABC, press
// + Add, and the new invoice already says ABC. Clerks filter to LOOK UP a
// document, not to add to that group, so the next bill was pre-filled with
// the previous customer. Applies to every doctype (Report view, Kanban and
// Ctrl+B go through the same method); the user's default Company and field
// defaults still apply, frappe.new_doc sets those itself.
// Patched on the prototype, not listview_settings: ERPNext list scripts
// replace the whole settings object, so a settings hook would be clobbered.
frappe.provide("frappe.views");
if (frappe.views.ListView) {
    frappe.views.ListView.prototype.make_new_doc = function () {
        frappe.new_doc(this.doctype);
    };
}
