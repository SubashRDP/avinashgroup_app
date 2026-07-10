// Document No. (custom_document_no) field behaviour — driven entirely by the
// server, never guessed in the browser.
//
// The number itself is assigned authoritatively on the server at save
// (naming_series.apply_document_no: atomic max+1 under a per-scope lock). The
// form does NOT re-run the rule logic to predict it. It only asks the server for
// the current STATUS of the draft and reflects it:
//
//   * auto   -> the field is HIDDEN while the doc is new: the number does not
//               exist until the server assigns it at save, so nothing is shown
//               that could differ from the saved value. After save the field
//               appears read-only with the real number.
//   * manual -> the field is REQUIRED; the user types it and gets an instant
//               duplicate warning.
//
// This replaces the old live-preview machinery (per-rule field watching +
// realtime re-fetch + manual/preview tug-of-war) that showed a wrong or blank
// number whenever a client change event didn't fire.

// Forms that carry the custom_document_no field. The AUTO vs MANUAL decision is
// NOT here — the server decides that per Numbering Configuration rule; this list
// only says which forms have the field to manage.
const DOCNO_DOCTYPES = ["Payment Entry", "Journal Entry", "Purchase Invoice", "Purchase Receipt"];

// Fields that can change whether/what number applies (server scope inputs).
const SCOPE_FIELDS = [
    "custom_p_type", "custom_purchase_type", "custom_receipt_type",
    "custom_p_type_code", "company", "custom_branch", "is_return",
    "posting_date", "transaction_date", "custom_fiscal_year",
];

const DEBOUNCE_MS = 400;

function has_docno_field(frm) {
    return !!(frm.fields_dict && frm.fields_dict["custom_document_no"]);
}

function has_manual_flag(frm) {
    return !!frm.fields_dict["custom_document_no_manual"];
}

function was_auto_drawn(frm) {
    // Stored docs record how their number was obtained in the manual flag:
    // 0 (or absent value) = server-drawn -> the user must not edit it.
    return has_manual_flag(frm) && !cint(frm.doc.custom_document_no_manual);
}

function is_readonly(frm) {
    const f = frm.get_field && frm.get_field("custom_document_no");
    return !!(f && f.df && f.df.read_only);
}

// Ask the server for the draft's Document No. status and reflect it on the
// field — and on the rule's locked group-by fields (any docstatus-0 doc).
function fetch_status(frm) {
    if (!has_docno_field(frm)) return;

    const token = (frm._docno_req = (frm._docno_req || 0) + 1);
    frappe.call({
        method: "avinashgroup_app.custom_code.Override.naming_series.get_document_no_status",
        args: { doc: frm.doc },
        callback: function (r) {
            if (token !== frm._docno_req) return;          // superseded by a newer call
            const st = (r && r.message) || {};
            if (frm.is_new()) {
                // Amendment: the number is pinned to the cancelled original by
                // the server — the field itself just locks.
                apply_status(frm, frm.doc.amended_from ? { amended: true } : st);
            }
            apply_locked_fields(frm, st.locked_fields);
        }
    });
}

// "Group Document No. By" fields marked Lock After Numbering: once the doc
// holds a number, the server rejects any change to them — so don't even offer
// the edit. Unnumbered/new docs keep the field's own base read_only.
function base_read_only(frm, fieldname) {
    const base = (frappe.meta.docfield_map[frm.doc.doctype] || {})[fieldname];
    return base && base.read_only ? 1 : 0;
}

function apply_locked_fields(frm, locked) {
    locked = locked || [];
    const numbered = !frm.is_new() && !!frm.doc.custom_document_no
        && frm.doc.docstatus === 0;
    // fields locked earlier but no longer in the list go back to their base
    (frm._docno_locked_fields || []).forEach(function (f) {
        if (!locked.includes(f) && frm.fields_dict[f]) {
            frm.set_df_property(f, "read_only", base_read_only(frm, f));
        }
    });
    locked.forEach(function (f) {
        if (frm.fields_dict[f]) {
            frm.set_df_property(f, "read_only", numbered ? 1 : base_read_only(frm, f));
        }
    });
    frm._docno_locked_fields = locked;
}

// The field's own mandatory_depends_on (e.g. "every company except Grihalaxmi")
// OVERRIDES reqd in frappe's mandatory check — so hiding the field must also
// neutralize it, and manual mode must restore it. The BASE docfield map holds
// the pristine expression (set_df_property only ever writes the per-doc copy).
function base_mandatory_expr(frm) {
    const base = (frappe.meta.docfield_map[frm.doc.doctype] || {})["custom_document_no"];
    return (base && base.mandatory_depends_on) || "";
}

function apply_status(frm, st) {
    if (!has_docno_field(frm)) return;
    st = st || { auto: false, ambiguous: false };

    if (st.amended) {
        // Pinned to the cancelled original's number — visible but locked.
        set_field(frm, { hidden: 0, read_only: 1, reqd: 0, mandatory_depends_on: "eval:false",
            description: __("Amendment — keeps the Document No. of the original.") });
        return;
    }

    if (st.auto) {
        // The number does not exist until the server assigns it at save:
        // hide the field entirely so nothing provisional is ever shown. The
        // mandatory override matters: hidden fields still fail the client
        // mandatory check, and reqd alone is trumped by mandatory_depends_on.
        set_field(frm, { hidden: 1, reqd: 0, mandatory_depends_on: "eval:false", description: "" });
        if (st.ambiguous) {
            frappe.show_alert({
                message: __("Multiple numbering rules match this document equally — "
                    + "the Document No. rule is ambiguous. Ask an admin to make one rule more specific."),
                indicator: "orange"
            }, 10);
        }
    } else {
        // No rule numbers this doc: the user must enter it. Restore the field's
        // own mandatory expression (it may exempt some companies) — with reqd 1
        // as the fallback when there is none.
        set_field(frm, { hidden: 0, read_only: 0, reqd: 1,
            mandatory_depends_on: base_mandatory_expr(frm),
            description: __("Enter the Document No. (required).") });
    }
}

function set_field(frm, props) {
    Object.keys(props).forEach(function (k) {
        frm.set_df_property("custom_document_no", k, props[k]);
    });
}

function schedule_status(frm) {
    clearTimeout(frm._docno_timer);
    frm._docno_timer = setTimeout(function () { fetch_status(frm); }, DEBOUNCE_MS);
}

// Manual entry only: warn immediately if the typed number is already used, and
// show the next free one. No-op in auto mode (the field is read-only there).
function warn_if_taken(frm) {
    if (is_readonly(frm)) return;
    const v = frm.doc.custom_document_no;
    if (!v) return;
    const token = (frm._docno_check_req = (frm._docno_check_req || 0) + 1);
    frappe.call({
        method: "avinashgroup_app.custom_code.Override.naming_series.check_document_no_availability",
        args: { doc: frm.doc },
        callback: function (r) {
            if (token !== frm._docno_check_req) return;
            if (cint(frm.doc.custom_document_no) !== cint(v)) return;
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
    frm._docno_check_timer = setTimeout(function () { warn_if_taken(frm); }, DEBOUNCE_MS);
}

DOCNO_DOCTYPES.forEach(function (doctype) {
    const handlers = {
        onload_post_render: function (frm) {
            if (!frm.is_new()) return;
            // A DUPLICATED draft carries the source's number with the manual
            // flag cleared (the flag is no_copy) — that number belongs to the
            // ORIGINAL. Start blank: auto redraws at save anyway, manual must
            // be typed by the user. Amendments legitimately keep their number.
            if (frm.doc.custom_document_no && !frm.doc.amended_from
                && has_manual_flag(frm) && !cint(frm.doc.custom_document_no_manual)) {
                frm.set_value("custom_document_no", null);
            }
            fetch_status(frm);
        },
        refresh: function (frm) {
            if (frm.is_new()) { fetch_status(frm); return; }
            if (!has_docno_field(frm)) return;
            // SAVED doc: the number now exists — show it. Locked when the
            // server drew it; editable (draft) when the user typed it.
            set_field(frm, {
                hidden: 0, reqd: 0,
                read_only: was_auto_drawn(frm) ? 1 : 0,
                description: was_auto_drawn(frm) ? __("Assigned automatically.") : "",
            });
            // a numbered doc also renders its locked group fields read-only
            fetch_status(frm);
        },
        custom_document_no: function (frm) {
            // Only meaningful in manual mode (auto is hidden/read-only). A typed
            // value is the USER'S: record that in the manual flag — the server
            // keeps flagged values verbatim, but treats an unflagged value on a
            // desk save as a stale leftover and clears it (that would blank the
            // number the user just typed). Clearing the field returns it to auto.
            if (is_readonly(frm) || frm.doc.amended_from) return;
            if (frm.doc.custom_document_no) {
                if (has_manual_flag(frm) && !cint(frm.doc.custom_document_no_manual)) {
                    frm.set_value("custom_document_no_manual", 1);
                }
                schedule_taken_check(frm);
            } else if (has_manual_flag(frm) && cint(frm.doc.custom_document_no_manual)) {
                frm.set_value("custom_document_no_manual", 0);
            }
        }
    };

    // Any scope field changing can flip auto/manual or move the preview number.
    SCOPE_FIELDS.forEach(function (field) {
        if (!handlers[field]) handlers[field] = schedule_status;
    });

    frappe.ui.form.on(doctype, handlers);
});
