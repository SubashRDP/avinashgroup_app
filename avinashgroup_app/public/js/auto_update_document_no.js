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

// A non-empty value that WE did not put there belongs to the user. cint() so
// Data-typed custom_document_no ("5") and our numeric preview (5) compare equal.
function user_owns_value(frm) {
    const v = frm.doc.custom_document_no;
    return !!v && cint(v) !== cint(frm._auto_docno_value);
}

// Do not auto-preview over a number the user controls — via the manual flag, or
// (even when the flag field isn't deployed yet) via a value we didn't write.
function auto_locked(frm) {
    return is_manual(frm) || user_owns_value(frm);
}

function update_hint(frm, preview) {
    if (!frm.get_field || !frm.get_field("custom_document_no")) return;
    let msg = "";
    if (should_auto_number(frm)) {
        if (auto_locked(frm)) {
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
    if (!should_auto_number(frm) || auto_locked(frm)) {
        update_hint(frm, frm.doc.custom_document_no);
        return;
    }

    // Monotonic token so an older, slower response can't paint over a newer one.
    const token = (frm._docno_req = (frm._docno_req || 0) + 1);
    frappe.call({
        method: "avinashgroup_app.custom_code.Override.naming_series.get_next_custom_document_no",
        args: { doc: frm.doc },
        callback: function(r) {
            if (token !== frm._docno_req) return;            // superseded
            // The user may have taken over / the form moved on while in flight.
            if (!should_auto_number(frm) || auto_locked(frm)) return;
            const next = r && r.message;
            if (next && cint(frm.doc.custom_document_no) !== cint(next)) {
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

// Manual number typed: ask the server whether it is already used in this
// scope and warn IMMEDIATELY (before save) with the next free number.
function warn_if_taken(frm) {
    const v = frm.doc.custom_document_no;
    if (!v) return;
    const token = (frm._docno_check_req = (frm._docno_check_req || 0) + 1);
    frappe.call({
        method: "avinashgroup_app.custom_code.Override.naming_series.check_document_no_availability",
        args: { doc: frm.doc },
        callback: function (r) {
            if (token !== frm._docno_check_req) return;          // superseded
            if (cint(frm.doc.custom_document_no) !== cint(v)) return; // value moved on
            const res = r && r.message;
            if (!res || !res.taken) return;
            const msg = res.next
                ? __("Document No. {0} is already used by {1}. Next available is {2}.", [v, res.used_by, res.next])
                : __("Document No. {0} is already used by {1}.", [v, res.used_by]);
            frappe.show_alert({ message: msg, indicator: "orange" }, 8);
            frm.set_df_property("custom_document_no", "description", "⚠ " + msg);
        }
    });
}

function schedule_taken_check(frm) {
    clearTimeout(frm._docno_check_timer);
    frm._docno_check_timer = setTimeout(() => warn_if_taken(frm), DEBOUNCE_MS);
}

// Another user just consumed a number in this doctype: any live auto preview
// may now be stale — re-fetch it so two open forms never show the same number.
// Registered once per page load; the server publishes after commit only.
if (frappe.realtime && frappe.realtime.on) {
    frappe.realtime.on("docno_assigned", function (data) {
        const frm = window.cur_frm;
        if (!frm || !data || frm.doc.doctype !== data.doctype) return;
        if (!should_auto_number(frm) || auto_locked(frm)) return;
        schedule_preview(frm);
    });
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
            // our own preview fill (value matches what set_auto_value stored);
            // cint() so a Data-typed "5" equals our numeric 5.
            if (v && cint(v) === cint(frm._auto_docno_value)) return;
            if (v) {
                // a value we did not set -> user typed it -> it's now theirs
                if (has_manual_flag(frm)) frm.set_value("custom_document_no_manual", 1);
                update_hint(frm, null);
                schedule_taken_check(frm);   // instant duplicate warning
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
