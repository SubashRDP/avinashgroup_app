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

    _normalize_field_entry: function(entry) {
        if (typeof entry === "string") {
            return {
                fieldname: entry,
                is_dynamic_link: false,
                dynamic_link_field: null
            };
        }
        return {
            fieldname: entry.fieldname,
            is_dynamic_link: !!entry.is_dynamic_link,
            dynamic_link_field: entry.dynamic_link_field || null
        };
    },

    _resolve_linked_doctype: function(doctype, fieldname, doc_or_row, dynamic_link_field) {
        const df = frappe.meta.get_docfield(doctype, fieldname);
        if (!df) return null;
        if (df.fieldtype === "Dynamic Link" || dynamic_link_field) {
            const dt_field = dynamic_link_field || df.options;
            if (!dt_field || !doc_or_row) return null;
            return doc_or_row[dt_field] || null;
        }
        if (df.fieldtype === "Link") return df.options;
        return null;
    },

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
        (config.fields || []).forEach(function(entry) {
            const f = self._normalize_field_entry(entry);
            if (!frm.fields_dict[f.fieldname]) return;
            frm.set_query(f.fieldname, function() {
                const company = frm.doc[cf];
                if (!company) return {};
                const linked_dt = self._resolve_linked_doctype(frm.doctype, f.fieldname, frm.doc, f.dynamic_link_field);
                if (!linked_dt) return {};
                if (f.is_dynamic_link) {
                    return {
                        query: "avinashgroup_app.custom_code.globalfilter.globalfilter.search_link_by_company",
                        filters: { linked_doctype: linked_dt, company: company }
                    };
                }
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

            fields.forEach(function(entry) {
                const f = self._normalize_field_entry(entry);
                frm.set_query(f.fieldname, table, function(doc, cdt, cdn) {
                    const company = frm.doc[cf];
                    if (!company) return {};
                    const row = locals[cdt][cdn];
                    const linked_dt = self._resolve_linked_doctype(child_doctype, f.fieldname, row, f.dynamic_link_field);
                    console.log("[company_filter] set_query callback", table, ".", f.fieldname, "company:", company, "linked_dt:", linked_dt);
                    if (!linked_dt) return {};
                    if (f.is_dynamic_link) {
                        return {
                            query: "avinashgroup_app.custom_code.globalfilter.globalfilter.search_link_by_company",
                            filters: { linked_doctype: linked_dt, company: company }
                        };
                    }
                    const filter_key = self._resolve_filter_key(linked_dt);
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

        (config.fields || []).forEach(function(entry) {
            avinash.filter_engine._check_field(frm, entry, company);
        });

        $.each(config.child_tables || {}, function(table, fields) {
            avinash.filter_engine._check_child_table(frm, table, fields, company);
        });
    },

    _check_field: function(frm, entry, company) {
        const f = avinash.filter_engine._normalize_field_entry(entry);
        const value = frm.doc[f.fieldname];
        if (!value) return;
        const df = frappe.meta.get_docfield(frm.doctype, f.fieldname);
        if (!df) return;
        const linked_dt = avinash.filter_engine._resolve_linked_doctype(frm.doctype, f.fieldname, frm.doc, f.dynamic_link_field);
        if (!linked_dt) return;
        const filter_key = avinash.filter_engine._resolve_filter_key(linked_dt);
        if (!filter_key) return;

        frappe.db.get_value(linked_dt, value, filter_key, function(r) {
            if (r && r[filter_key] && r[filter_key] !== company) {
                frappe.show_alert({
                    message: __("{0} '{1}' does not belong to {2}. Field cleared.",
                        [df.label || f.fieldname, value, company]),
                    indicator: "orange"
                }, 6);
                frm.set_value(f.fieldname, "");
            }
        });
    },

    _check_child_table: function(frm, table, fields, company) {
        if (!frm.doc[table] || !frm.doc[table].length) return;
        const tdf = frappe.meta.get_docfield(frm.doctype, table);
        if (!tdf) return;
        const child_doctype = tdf.options;
        const self = avinash.filter_engine;

        fields.forEach(function(entry) {
            const f = self._normalize_field_entry(entry);
            const cdf = frappe.meta.get_docfield(child_doctype, f.fieldname);
            if (!cdf) return;
            const values_by_dt = {};
            (frm.doc[table] || []).forEach(function(row) {
                const val = row[f.fieldname];
                if (!val) return;
                const linked_dt = self._resolve_linked_doctype(child_doctype, f.fieldname, row, f.dynamic_link_field);
                if (!linked_dt) return;
                if (!values_by_dt[linked_dt]) values_by_dt[linked_dt] = new Set();
                values_by_dt[linked_dt].add(val);
            });

            Object.keys(values_by_dt).forEach(function(linked_dt) {
                const filter_key = self._resolve_filter_key(linked_dt);
                if (!filter_key) return;
                const values = [...values_by_dt[linked_dt]];
                if (!values.length) return;

                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: linked_dt,
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
                            const row_dt = self._resolve_linked_doctype(child_doctype, f.fieldname, row, f.dynamic_link_field);
                            if (row_dt !== linked_dt) return true;
                            if (row[f.fieldname] && mismatch.has(row[f.fieldname])) {
                                frappe.model.clear_doc(row.doctype, row.name);
                                removed++;
                                return false;
                            }
                            return true;
                        });

                        if (removed) {
                            frappe.show_alert({
                                message: __("Removed {0} row(s) in '{1}' — {2} mismatch with {3}.",
                                    [removed, table, f.fieldname, company]),
                                indicator: "orange"
                            }, 6);
                            frm.refresh_field(table);
                            frm.dirty();
                        }
                    }
                });
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

                function _defer_setup(frm) {
                    setTimeout(function() { avinash.filter_engine.setup(frm); }, 0);
                }

                const events = {
                    setup:   function(frm) { avinash.filter_engine.setup(frm); },
                    refresh: function(frm) { avinash.filter_engine.setup(frm); }
                };

                events[cf] = function(frm) {
                    _defer_setup(frm);
                    avinash.filter_engine.validate_and_clear(frm);
                };

                // Re-apply queries when the dynamic link doctype selector changes
                (config.fields || []).forEach(function(entry) {
                    if (typeof entry !== "string" && entry.is_dynamic_link && entry.dynamic_link_field) {
                        events[entry.dynamic_link_field] = function(frm) { _defer_setup(frm); };
                    }
                });

                frappe.ui.form.on(doctype, events);
            });

            // If a configured form is already open (race condition: form loaded
            // before this callback returned), apply setup immediately
            if (cur_frm && r.message[cur_frm.doctype]) {
                avinash.filter_engine.setup(cur_frm);
            }

        }
    });
});


