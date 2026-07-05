// Live PREVIEW of custom_document_no for new docs configured in
// AUTO_NUMBER_CONFIG (naming_series.py).
//
// The value shown while filling a draft is only a preview. The authoritative,
// collision-free number is assigned on the server at save time
// (naming_series.apply_document_no) by drawing max+1 under a per-scope lock, so
// two users on the same scope never receive the same number.
//
// Manual override: if the user types a number, custom_document_no_manual is set
// to 1 and auto-preview backs off; the server keeps and only uniqueness-checks
// that value. Clearing the field returns it to auto.

const AUTO_NUMBER_CONFIG = {
    "Purchase Receipt": { type_field: "custom_receipt_type" },
    "Purchase Invoice": { type_field: "custom_purchase_type" },
    "Payment Entry": { type_field: "custom_p_type" },
    "Journal Entry": { type_field: "custom_p_type" }
};

// Fields that scope the document_no series on the server (_docno_scope):
//   custom_p_type_code → prefix code, company → company abbr,
//   posting_date → fiscal year, custom_fiscal_year → direct override.
const SERIES_DEPS = ["custom_p_type_code", "company", "posting_date", "custom_fiscal_year"];

const DEBOUNCE_MS = 400;

function should_auto_number(frm) {
    return !!AUTO_NUMBER_CONFIG[frm.doc.doctype] && frm.is_new();
}

function has_manual_flag(frm) {
    return !!frm.fields_dict["custom_document_no_manual"];
}

function is_manual(frm) {
    return has_manual_flag(frm) && !!cint(frm.doc.custom_document_no_manual);
}

function update_hint(frm, preview) {
    if (!frm.get_field || !frm.get_field("custom_document_no")) return;
    let msg = "";
    if (should_auto_number(frm)) {
        if (is_manual(frm)) {
            msg = __("Manually entered. Clear the field to auto-number.");
        } else if (preview) {
            msg = __("Auto — assigned on save (preview: {0}).", [preview]);
        } else {
            msg = __("Set Type, Company and Date to auto-number, or type a number.");
        }
    }
    frm.set_df_property("custom_document_no", "description", msg);
}

function set_auto_value(frm, value) {
    // Remember the value WE put in, so the field's change handler can tell our
    // own preview fill from a real user edit. A value-compare is used instead
    // of a synchronous flag because set_value may trigger the handler async.
    frm._auto_docno_value = value;
    frm.set_value("custom_document_no", value);
    if (has_manual_flag(frm)) frm.set_value("custom_document_no_manual", 0);
}

function fetch_preview(frm) {
    if (!should_auto_number(frm) || is_manual(frm)) {
        update_hint(frm, frm.doc.custom_document_no);
        return;
    }

    frappe.call({
        method: "avinashgroup_app.custom_code.Override.naming_series.get_next_custom_document_no",
        args: { doc: frm.doc },
        callback: function(r) {
            // Ignore stale responses: the user may have edited or the form may
            // have moved on while this request was in flight.
            if (!should_auto_number(frm) || is_manual(frm)) return;
            const next = r && r.message;
            if (next && frm.doc.custom_document_no !== next) {
                set_auto_value(frm, next);
            }
            update_hint(frm, next);
        }
    });
}

function schedule_preview(frm) {
    clearTimeout(frm._docno_timer);
    frm._docno_timer = setTimeout(() => fetch_preview(frm), DEBOUNCE_MS);
}

Object.keys(AUTO_NUMBER_CONFIG).forEach(function(doctype) {
    const cfg = AUTO_NUMBER_CONFIG[doctype];

    const handlers = {
        onload_post_render: function(frm) {
            if (frm.is_new()) schedule_preview(frm);
        },
        refresh: function(frm) {
            if (frm.is_new()) update_hint(frm, frm.doc.custom_document_no);
        },
        custom_document_no: function(frm) {
            const v = frm.doc.custom_document_no;
            // our own preview fill (value matches what set_auto_value stored)
            if (v && v === frm._auto_docno_value) return;
            if (v) {
                // a value we did not set -> user typed it -> it's now theirs
                if (has_manual_flag(frm)) frm.set_value("custom_document_no_manual", 1);
                update_hint(frm, null);
            } else {
                // user cleared it -> back to auto
                frm._auto_docno_value = null;
                if (has_manual_flag(frm)) frm.set_value("custom_document_no_manual", 0);
                schedule_preview(frm);
            }
        }
    };

    // Per-doctype type discriminator (custom_p_type / custom_purchase_type / ...)
    if (cfg.type_field) {
        handlers[cfg.type_field] = schedule_preview;
    }

    // Shared series-scope dependencies
    SERIES_DEPS.forEach(function(field) {
        if (!handlers[field]) handlers[field] = schedule_preview;
    });

    frappe.ui.form.on(doctype, handlers);
});
