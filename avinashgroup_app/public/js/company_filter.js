// ─────────────────────────────────────────────────────────────
//  COMPANY FILTER CONFIG
//  Populated at runtime from the "Company Filter Config" DocType
//  via get_filter_config(). Do not add entries here — use the
//  DocType UI instead. The seed data lives in:
//  patches/seed_company_filter_config.py
// ─────────────────────────────────────────────────────────────
const COMPANY_FILTER_CONFIG = {};
// Pre-resolved server-side: linked_doctype → company field name (or "" if none)
const FILTER_KEYS = {};

frappe.provide("avinash.filter_engine");

avinash.filter_engine = {

    // Returns the field name used to filter by company on linked_doctype:
    //   "name"           → linked_doctype is Company
    //   "company"        → standard company field
    //   "custom_company" → custom company field
    //   null             → no company field found → caller skips filter
    _resolve_filter_key: function(linked_doctype) {
        if (!linked_doctype) return null;
        if (linked_doctype === "Company") return "name";
        // 1. Explicit config (master doctypes that use custom_company)
        const config = COMPANY_FILTER_CONFIG[linked_doctype];
        if (config) return config.company_field || "company";
        // 2. Server-pre-resolved keys (e.g. Item Tax Template, Warehouse)
        if (linked_doctype in FILTER_KEYS) return FILTER_KEYS[linked_doctype] || null;
        // 3. Client meta fallback (for metas already loaded)
        const meta = frappe.get_meta(linked_doctype);
        if (!meta) return null;
        if (meta.fields.find(f => f.fieldname === "company")) return "company";
        if (meta.fields.find(f => f.fieldname === "custom_company")) return "custom_company";
        return null;
    },


    setup: function(frm) {
        const config = COMPANY_FILTER_CONFIG[frm.doctype];
        if (!config) {
            console.log("[company_filter] setup: no config for", frm.doctype);
            return;
        }
        const cf  = config.company_field || "company";
        const self = avinash.filter_engine;

        // top-level fields
        (config.fields || []).forEach(function(fieldname) {
            if (!frm.fields_dict[fieldname]) return;
            const linked_dt = frappe.meta.get_docfield(frm.doctype, fieldname)?.options;
            if (!linked_dt) return;
            frm.set_query(fieldname, function() {
                const company = frm.doc[cf];
                if (!company) return {};
                const filter_key = self._resolve_filter_key(linked_dt);
                return filter_key ? { filters: { [filter_key]: company } } : {};
            });
        });

        // child table fields
        $.each(config.child_tables || {}, function(table, fields) {
            console.log("[company_filter] child_table loop:", table, fields);
            if (!frm.fields_dict[table]) { console.warn("[company_filter] fields_dict missing:", table); return; }
            const child_doctype = frappe.meta.get_docfield(frm.doctype, table)?.options;
            console.log("[company_filter] child_doctype for", table, "→", child_doctype);
            if (!child_doctype) return;

            fields.forEach(function(fieldname) {
                const linked_dt = frappe.meta.get_docfield(child_doctype, fieldname)?.options;
                console.log("[company_filter] child field", table, ".", fieldname, "→ linked_dt:", linked_dt);
                if (!linked_dt) return;
                frm.set_query(fieldname, table, function() {
                    const company = frm.doc[cf];
                    if (!company) return {};
                    const filter_key = self._resolve_filter_key(linked_dt);
                    console.log("[company_filter] set_query callback", table, ".", fieldname, "company:", company, "filter_key:", filter_key);
                    return filter_key ? { filters: { [filter_key]: company } } : {};
                });
            });
        });
    },

    validate_and_clear: function(frm) {
        const config = COMPANY_FILTER_CONFIG[frm.doctype];
        if (!config) return;
        const cf      = config.company_field || "company";
        const company = frm.doc[cf];
        if (!company) return;

        (config.fields || []).forEach(function(fieldname) {
            avinash.filter_engine._check_field(frm, fieldname, company);
        });

        $.each(config.child_tables || {}, function(table, fields) {
            avinash.filter_engine._check_child_table(frm, table, fields, company);
        });
    },

    _check_field: function(frm, fieldname, company) {
        const value = frm.doc[fieldname];
        if (!value) return;
        const df = frappe.meta.get_docfield(frm.doctype, fieldname);
        if (!df || df.fieldtype !== "Link") return;
        const filter_key = avinash.filter_engine._resolve_filter_key(df.options);
        if (!filter_key) return;

        frappe.db.get_value(df.options, value, filter_key, function(r) {
            if (r && r[filter_key] && r[filter_key] !== company) {
                frappe.show_alert({
                    message: __("{0} '{1}' does not belong to {2}. Field cleared.",
                        [df.label || fieldname, value, company]),
                    indicator: "orange"
                }, 6);
                frm.set_value(fieldname, "");
            }
        });
    },

    _check_child_table: function(frm, table, fields, company) {
        if (!frm.doc[table] || !frm.doc[table].length) return;
        const tdf = frappe.meta.get_docfield(frm.doctype, table);
        if (!tdf) return;
        const child_doctype = tdf.options;
        const self = avinash.filter_engine;

        fields.forEach(function(fieldname) {
            const cdf = frappe.meta.get_docfield(child_doctype, fieldname);
            if (!cdf || cdf.fieldtype !== "Link") return;
            const filter_key = self._resolve_filter_key(cdf.options);
            if (!filter_key) return;

            const values = [...new Set(
                frm.doc[table].filter(r => r[fieldname]).map(r => r[fieldname])
            )];
            if (!values.length) return;

            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: cdf.options,
                    filters: { name: ["in", values] },
                    fields: ["name", filter_key]
                },
                callback: function(res) {
                    if (!res || !res.message) return;
                    const mismatch = new Set(
                        res.message
                            .filter(d => d[filter_key] && d[filter_key] !== company)
                            .map(d => d.name)
                    );
                    if (!mismatch.size) return;

                    let removed = 0;
                    frm.doc[table] = frm.doc[table].filter(function(row) {
                        if (row[fieldname] && mismatch.has(row[fieldname])) {
                            frappe.model.clear_doc(row.doctype, row.name);
                            removed++;
                            return false;
                        }
                        return true;
                    });

                    if (removed) {
                        frappe.show_alert({
                            message: __("Removed {0} row(s) in '{1}' — {2} mismatch with {3}.",
                                [removed, table, fieldname, company]),
                            indicator: "orange"
                        }, 6);
                        frm.refresh_field(table);
                        frm.dirty();
                    }
                }
            });
        });
    }
};


// ─────────────────────────────────────────────────────────────
//  ATTACH HOOKS — driven entirely by Company Filter Config DocType
// ─────────────────────────────────────────────────────────────
$(document).on("app_ready", function() {

    frappe.call({
        method: "avinashgroup_app.custom_code.globalfilter.globalfilter.get_filter_config",
        callback: function(r) {
            if (!r || !r.message) {
                console.warn("[company_filter] get_filter_config returned empty");
                return;
            }

            // Extract pre-resolved filter keys, then remove from config dict
            Object.assign(FILTER_KEYS, r.message.__filter_keys__ || {});
            delete r.message.__filter_keys__;

            console.log("[company_filter] config loaded, doctypes:", Object.keys(r.message));

            // Populate the runtime config so filter_engine.setup / _resolve_filter_key work
            Object.assign(COMPANY_FILTER_CONFIG, r.message);

            // Register hooks for every doctype returned from the DB
            Object.keys(r.message).forEach(function(doctype) {
                const config = r.message[doctype];
                const cf     = config.company_field || "company";

                const events = {
                    setup:   function(frm) { avinash.filter_engine.setup(frm); },
                    refresh: function(frm) { avinash.filter_engine.setup(frm); }
                };

                events[cf] = function(frm) {
                    avinash.filter_engine.setup(frm);
                    avinash.filter_engine.validate_and_clear(frm);
                };

                frappe.ui.form.on(doctype, events);
            });

            // If a configured form is already open (race condition: form loaded
            // before this callback returned), apply setup immediately
            if (cur_frm && r.message[cur_frm.doctype]) {
                avinash.filter_engine.setup(cur_frm);
            }

            // Special blocks registered after config is loaded
            _register_special_blocks();
        }
    });


    function _register_special_blocks() {

        // ── PAYMENT ENTRY: party filtered by party_type ──────
        frappe.ui.form.on("Payment Entry", {
            setup:      function(frm) { avinash.filter_engine.setup(frm); _pe_party(frm); },
            refresh:    function(frm) { avinash.filter_engine.setup(frm); _pe_party(frm); },
            company:    function(frm) {
                avinash.filter_engine.setup(frm);
                avinash.filter_engine.validate_and_clear(frm);
                _pe_party(frm);
            },
            party_type: function(frm) { _pe_party(frm); }
        });

        // ── JOURNAL ENTRY: per-row party filtered by party_type
        frappe.ui.form.on("Journal Entry", {
            setup:   function(frm) { _je_filters(frm); },
            refresh: function(frm) { _je_filters(frm); },
            company: function(frm) { _je_filters(frm); }
        });
        frappe.ui.form.on("Journal Entry Account", {
            party_type: function(frm) { _je_filters(frm); }
        });

        // ── BANK ACCOUNT: party filtered by party_type ───────
        frappe.ui.form.on("Bank Account", {
            setup:      function(frm) { _ba_party(frm); },
            refresh:    function(frm) { _ba_party(frm); },
            company:    function(frm) { _ba_party(frm); },
            party_type: function(frm) { _ba_party(frm); }
        });
    }


    function _pe_party(frm) {
        if (!frm.doc.party_type || !frm.fields_dict.party) return;
        const company = frm.doc.company;
        const filter_key = avinash.filter_engine._resolve_filter_key(frm.doc.party_type);
        frm.set_query("party", function() {
            return company && filter_key ? { filters: { [filter_key]: company } } : {};
        });
    }

    function _je_filters(frm) {
        const company = frm.doc.company;

        frm.set_query("bank_account", "accounts", function() {
            return company ? { filters: { company: company } } : {};
        });

        frm.set_query("project", "accounts", function() {
            const filter_key = avinash.filter_engine._resolve_filter_key("Project");
            return company && filter_key ? { filters: { [filter_key]: company } } : {};
        });

        frm.set_query("party", "accounts", function(_doc, cdt, cdn) {
            const row = locals[cdt][cdn];
            if (!row.party_type || !company) return {};
            const filter_key = avinash.filter_engine._resolve_filter_key(row.party_type);
            return filter_key ? { filters: { [filter_key]: company } } : {};
        });
    }

    function _ba_party(frm) {
        if (!frm.doc.party_type || !frm.fields_dict.party) return;
        const company = frm.doc.company;
        const filter_key = avinash.filter_engine._resolve_filter_key(frm.doc.party_type);
        frm.set_query("party", function() {
            return company && filter_key ? { filters: { [filter_key]: company } } : {};
        });
    }

});
