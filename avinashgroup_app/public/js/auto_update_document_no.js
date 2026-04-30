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

    frappe.call({
        method: "avinashgroup_app.custom_code.Override.naming_series.get_next_custom_document_no",
        args: frm.doc,
        callback: function(r) {
            if (r && r.message) {
                frm.set_value("custom_document_no", r.message);
            }
        }
    });
}

Object.keys(AUTO_NUMBER_CONFIG).forEach(function(doctype) {
    const cfg = AUTO_NUMBER_CONFIG[doctype];
    const type_field = cfg.type_field;

    const handlers = {
        onload: function(frm) {
            maybe_set_auto_document_no(frm);
        },
        refresh: function(frm) {
            maybe_set_auto_document_no(frm);
        },
        custom_p_type_code: function(frm) {
            maybe_set_auto_document_no(frm, true);
        }
    };

    if (type_field) {
        handlers[type_field] = function(frm) {
            maybe_set_auto_document_no(frm, true);
        };
    }

    frappe.ui.form.on(doctype, handlers);
});
