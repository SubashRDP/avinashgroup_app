// Auto-set custom_document_no for new docs configured in AUTO_NUMBER_CONFIG from naming_series.py

const AUTO_NUMBER_CONFIG = {
    "Purchase Receipt": {
        type_field: "custom_receipt_type"
    },
    "Purchase Invoice": {
        type_field: "custom_purchase_type"
    },
    "Payment Entry": {
        type_field: "custom_p_type"
    },
    "Journal Entry": {
        type_field: "custom_p_type"
    }
};

function should_auto_number(frm) {
    return !!AUTO_NUMBER_CONFIG[frm.doc.doctype] && frm.is_new();
}

function maybe_set_auto_document_no(frm, force = false) {
    if (!should_auto_number(frm)) return;
    if (!force && frm.doc.custom_document_no) return;

    // On force, clear the value in the payload so the server falls through
    // to the max+1 branch instead of running the duplicate-check + return.
    const payload = Object.assign({}, frm.doc);
    if (force) payload.custom_document_no = null;

    frappe.call({
        method: "avinashgroup_app.custom_code.Override.naming_series.get_next_custom_document_no",
        args: payload,
        callback: function(r) {
            if (r && r.message) {
                frm.set_value("custom_document_no", r.message);
            }
        }
    });
}

// Fields that scope the document_no series on the server (set_auto_document_no):
//   - custom_p_type_code → prefix
//   - company            → company abbr
//   - posting_date       → fiscal year (when custom_fiscal_year is empty)
//   - custom_fiscal_year → fiscal year (direct override)
// Changing any of these on a new doc must recompute the next number.
const SERIES_DEPS = [
    "custom_p_type_code",
    "company",
    "posting_date",
    "custom_fiscal_year"
];

Object.keys(AUTO_NUMBER_CONFIG).forEach(function(doctype) {
    const cfg = AUTO_NUMBER_CONFIG[doctype];
    const type_field = cfg.type_field;

    const handlers = {
        onload: function(frm) {
            maybe_set_auto_document_no(frm);
        },
        refresh: function(frm) {
            maybe_set_auto_document_no(frm);
        }
    };

    // Per-doctype discriminator (custom_purchase_type / custom_receipt_type / custom_p_type)
    if (type_field) {
        handlers[type_field] = function(frm) {
            maybe_set_auto_document_no(frm, true);
        };
    }

    // Shared series-scope dependencies
    SERIES_DEPS.forEach(function(field) {
        if (!handlers[field]) {
            handlers[field] = function(frm) {
                maybe_set_auto_document_no(frm, true);
            };
        }
    });

    frappe.ui.form.on(doctype, handlers);
});
