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
 * Also, list views (bottom of file): "+ Add" on a filtered list opens a blank
 * form; a Company filter narrows every other Link filter's dropdown and drops
 * filters that point at another company's record; filter dropdowns also offer
 * disabled / inactive records so their old transactions can be found.
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


// ── List filters follow the Company filter ────────────────────────────────────
// On a list filtered to Company = X (whichever Link-to-Company field the list
// has, company or custom_company), every other Link filter's dropdown —
// Customer, Item, Warehouse… in the filter bar and in the Filter popover —
// only offers X's records. Same company-field resolution as the form filters
// (avinash.filter_engine._resolve_filter_key in company_filter.js), so it
// needs no Company Filter Config rows: a linked doctype with a company or
// custom_company field is narrowed, anything else (UOM, Territory…) is left
// alone. Dropdown only — it never changes which rows the list shows.
// The same dropdowns also offer inactive records (disabled Customer/Supplier,
// Left Employee), tagged and listed after the active ones; see _can_go_inactive.
function _list_company(list_view) {
    if (!list_view || !list_view.filter_area) return null;
    const hit = list_view.filter_area.get().find(function (f) {
        if (f[2] !== "=" || !f[3] || typeof f[3] !== "string") return false;
        const df = frappe.meta.get_docfield(f[0], f[1]);
        return df && df.fieldtype === "Link" && df.options === "Company";
    });
    return hit ? hit[3] : null;
}

// Doctypes whose records can go inactive: a disabled/enabled check, or
// Employee's status. Stock search hides inactive records, but a list filter
// must still find them (old bills of a disabled customer), so these go
// through search_link_for_list_filter in globalfilter.py.
function _can_go_inactive(linked_doctype) {
    if (linked_doctype === "Employee") return true;
    const meta = frappe.get_meta(linked_doctype);
    return !!(meta && meta.fields.some(function (df) {
        return df.fieldtype === "Check" && (df.fieldname === "disabled" || df.fieldname === "enabled");
    }));
}

function _company_scoped_query(list_view, linked_doctype) {
    if (!linked_doctype || linked_doctype === "Company") return null;
    // _resolve_filter_key and _can_go_inactive read the linked doctype's meta
    // synchronously; load it now so it is there by the time the user types.
    frappe.model.with_doctype(linked_doctype);
    return function () {
        const company = _list_company(list_view);
        const key = company && avinash.filter_engine._resolve_filter_key(linked_doctype);
        const filters = key ? { [key]: company } : {};
        if (_can_go_inactive(linked_doctype)) {
            return {
                query: "avinashgroup_app.custom_code.globalfilter.globalfilter.search_link_for_list_filter",
                filters: filters
            };
        }
        return { filters: filters };
    };
}

// Filter bar: the standard filters are page fields built by FilterArea.
if (frappe.views.BaseList) {
    const _setup_filter_area = frappe.views.BaseList.prototype.setup_filter_area;
    frappe.views.BaseList.prototype.setup_filter_area = function () {
        const out = _setup_filter_area.apply(this, arguments);
        const list_view = this;
        $.each((this.page && this.page.fields_dict) || {}, function (_, control) {
            if (control.df.fieldtype !== "Link") return;
            const query = _company_scoped_query(list_view, control.df.options);
            if (query) control.get_query = query;
        });
        return out;
    };
}

// Filter popover: each row builds its value control in Filter.make_field from
// a copy of the docfield. filter_list is the ListView when the popover is on a
// list; on dashboards and query reports it is the FilterGroup, and nothing changes.
if (frappe.ui.Filter) {
    const _make_field = frappe.ui.Filter.prototype.make_field;
    frappe.ui.Filter.prototype.make_field = function (df) {
        if (df && df.fieldtype === "Link" && this.filter_list instanceof frappe.views.BaseList) {
            const query = _company_scoped_query(this.filter_list, df.options);
            if (query) df.get_query = query;
        }
        return _make_field.apply(this, arguments);
    };
}

// Company filter changed: drop the other Link filters that point at another
// company's record (Customer = a GLMI customer after switching to NGI), same
// rule as validate_and_clear on the forms. A record with no company set, or a
// doctype with no company field, is kept. on_filter_change is BaseList's
// empty "filters were added or removed" hook; Kanban overrides it, so Kanban
// boards are not covered.
if (frappe.views.BaseList) {
    const _on_filter_change = frappe.views.BaseList.prototype.on_filter_change;
    frappe.views.BaseList.prototype.on_filter_change = function () {
        const out = _on_filter_change.apply(this, arguments);
        _drop_other_company_filters(this);
        return out;
    };
}

function _drop_other_company_filters(list_view) {
    const company = _list_company(list_view);
    if (company === list_view._avinash_filter_company) return;
    list_view._avinash_filter_company = company;
    if (!company) return;

    list_view.filter_area.get().forEach(function (f) {
        const fieldname = f[1], value = f[3];
        if (f[2] !== "=" || !value || typeof value !== "string") return;
        const df = frappe.meta.get_docfield(f[0], fieldname);
        if (!df || df.fieldtype !== "Link" || df.options === "Company") return;

        frappe.model.with_doctype(df.options, function () {
            const key = avinash.filter_engine._resolve_filter_key(df.options);
            if (!key) return;
            frappe.db.get_value(df.options, value, key, function (r) {
                if (!r || !r[key] || r[key] === company) return;
                list_view.filter_area.remove(fieldname);
                frappe.show_alert({
                    message: __("{0} filter '{1}' removed: it belongs to {2}, not {3}.",
                        [__(df.label || fieldname), value, r[key], company]),
                    indicator: "orange"
                }, 6);
            });
        });
    });
}
