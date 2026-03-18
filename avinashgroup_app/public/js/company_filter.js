// ─────────────────────────────────────────────────────────────
//  COMPANY FILTER CONFIG
//  company_field : field on the form holding the company value
//  fields        : top-level Link fields to filter & validate
//  child_tables  : { table_fieldname: [child link fields] }
//  custom        : true → handled by dedicated override block
// ─────────────────────────────────────────────────────────────
const COMPANY_FILTER_CONFIG = {

    "Asset": {
        company_field: "company",
        fields: ["item_code", "custodian", "purchase_receipt", "purchase_invoice"]
    },
    "Asset Category": {
        company_field: "custom_company",
        child_tables: { "accounts": ["company"] }
    },
    "Asset Movement": {
        company_field: "company",
        child_tables: { "assets": ["asset"] }
    },
    "Asset Maintenance": {
        company_field: "company",
        fields: ["maintenance_team"]
    },
    "Asset Maintenance Log": {
        company_field: "company",
        fields: ["asset_maintenance"]
    },
    "Asset Value Adjustment": {
        company_field: "company",
        fields: ["asset"]
    },
    "Asset Repair": {
        company_field: "company",
        fields: ["asset"]
    },
    "Asset Capitalization": {
        company_field: "company",
        fields: ["target_item_code"],
        child_tables: {
            "stock_items":   ["item_code"],
            "asset_items":   ["asset", "item_code"],
            "service_items": ["item_code"]
        }
    },

    "Item Group": {
        company_field: "custom_company",
        fields: ["parent_item_group"],
        child_tables: {
            "item_group_defaults": ["company"],
            "taxes":               ["item_tax_template"]
        }
    },
    "Supplier Group": {
        company_field: "custom_company",
        fields: ["parent_supplier_group"],
        child_tables: { "accounts": ["company"] }
    },
    "Customer Group": {
        company_field: "custom_company",
        fields: ["parent_customer_group", "default_price_list"],
        child_tables: { "credit_limits": ["company"] }
    },

    "Quotation": {
        company_field: "company",
        fields: ["party_name", "price_list", "sales_partner"],
        child_tables: {
            "items":            ["item_code", "warehouse"],
            "payment_schedule": ["payment_term"]
        }
    },
    "Sales Order": {
        company_field: "company",
        fields: ["customer", "price_list"],
        child_tables: {
            "items": ["item_code", "supplier", "material_request", "project"]
        }
    },
    "Delivery Note": {
        company_field: "company",
        fields: ["customer", "price_list"],
        child_tables: {
            "items": ["item_code", "batch_no", "project"]
        }
    },
    "Sales Invoice": {
        company_field: "company",
        fields: ["customer", "price_list"],
        child_tables: {
            "items":            ["item_code", "batch_no", "project"],
            "payment_schedule": ["payment_term"]
        }
    },

    "Material Request": {
        company_field: "company",
        fields: ["price_list"],
        child_tables: {
            "items": ["item_code", "manufacturer", "bom_no", "project"]
        }
    },
    "Request for Quotation": {
        company_field: "company",
        child_tables: {
            "suppliers": ["supplier"],
            "items":     ["item_code", "project"]
        }
    },
    "Supplier Quotation": {
        company_field: "company",
        fields: ["supplier", "price_list"],
        child_tables: {
            "items": ["item_code", "warehouse", "project"]
        }
    },
    "Purchase Order": {
        company_field: "company",
        fields: ["supplier", "price_list"],
        child_tables: {
            "items": ["item_code", "project"]
        }
    },
    "Purchase Receipt": {
        company_field: "company",
        fields: ["supplier", "price_list"],
        child_tables: {
            "items": ["item_code", "batch_no", "project"]
        }
    },
    "Purchase Invoice": {
        company_field: "company",
        fields: ["supplier"],
        child_tables: {
            "items":            ["item_code", "manufacturer", "project"],
            "payment_schedule": ["payment_term"]
        }
    },

    // custom: true → handled by dedicated override blocks below
    "Payment Entry": {
        company_field: "company",
        fields: ["bank_account"],
        custom: true
    },
    "Journal Entry": {
        company_field: "company",
        custom: true
    },
    "Bank Account": {
        company_field: "company",
        custom: true
    },
};

frappe.provide("avinash.filter_engine");

avinash.filter_engine = {

    // Returns 'company' if meta has standard company field, else 'custom_company'
    // NOTE: Only reliable after frappe.model.with_doctype() has been called for linked_doctype
    _resolve_filter_key: function(linked_doctype) {
        try {
            const meta = frappe.get_meta(linked_doctype);
            if (meta && meta.fields.some(f => f.fieldname === "company")) {
                return "company";
            }
        } catch(e) {}
        return "custom_company";
    },


    setup: function(frm) {
        const config = COMPANY_FILTER_CONFIG[frm.doctype];
        if (!config) return;
        const cf  = config.company_field || "company";
        const self = avinash.filter_engine;

        // top-level fields
        // Use frappe.model.with_doctype to guarantee linked doctype meta is loaded
        // before resolving the filter key (company vs custom_company)
        (config.fields || []).forEach(function(fieldname) {
            if (!frm.fields_dict[fieldname]) return;
            const df = frappe.meta.get_docfield(frm.doctype, fieldname);
            if (!df || df.fieldtype !== "Link") return;
            const linked_dt = df.options;

            frappe.model.with_doctype(linked_dt, function() {
                const filter_key = self._resolve_filter_key(linked_dt);
                frm.set_query(fieldname, function() {
                    const company = frm.doc[cf];
                    return company
                        ? { filters: { [filter_key]: company } }
                        : {};
                });
            });
        });

        // child table fields
        $.each(config.child_tables || {}, function(table, fields) {
            if (!frm.fields_dict[table]) return;
            const tdf = frappe.meta.get_docfield(frm.doctype, table);
            if (!tdf) return;
            const child_doctype = tdf.options;

            fields.forEach(function(fieldname) {
                const cdf = frappe.meta.get_docfield(child_doctype, fieldname);
                if (!cdf || cdf.fieldtype !== "Link") return;
                const linked_dt = cdf.options;

                frappe.model.with_doctype(linked_dt, function() {
                    const filter_key = self._resolve_filter_key(linked_dt);
                    frm.set_query(fieldname, table, function() {
                        const company = frm.doc[cf];
                        return company
                            ? { filters: { [filter_key]: company } }
                            : {};
                    });
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
        const linked_dt = df.options;

        frappe.model.with_doctype(linked_dt, function() {
            const filter_key = avinash.filter_engine._resolve_filter_key(linked_dt);
            frappe.db.get_value(linked_dt, value, filter_key, function(r) {
                if (r && r[filter_key] && r[filter_key] !== company) {
                    frappe.show_alert({
                        message: __("{0} '{1}' does not belong to {2}. Field cleared.",
                            [df.label || fieldname, value, company]),
                        indicator: "orange"
                    }, 6);
                    frm.set_value(fieldname, "");
                }
            });
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
            const linked_dt = cdf.options;

            const values = [...new Set(
                frm.doc[table].filter(r => r[fieldname]).map(r => r[fieldname])
            )];
            if (!values.length) return;

            // ensure meta is loaded so _resolve_filter_key works correctly
            frappe.model.with_doctype(linked_dt, function() {
                const filter_key = self._resolve_filter_key(linked_dt);

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
        });
    }
};


// ─────────────────────────────────────────────────────────────
//  ATTACH HOOKS TO ALL CONFIGURED DOCTYPES
// ─────────────────────────────────────────────────────────────
$(document).on("app_ready", function() {

    Object.keys(COMPANY_FILTER_CONFIG).forEach(function(doctype) {
        const config = COMPANY_FILTER_CONFIG[doctype];
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


    // ── PAYMENT ENTRY: party filtered by party_type ──────────
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

    function _pe_party(frm) {
        if (!frm.doc.party_type || !frm.fields_dict.party) return;
        const company = frm.doc.company;
        frm.set_query("party", function() {
            return company
                ? { filters: { custom_company: company, disabled: 0 } }
                : { filters: { disabled: 0 } };
        });
    }


    // ── JOURNAL ENTRY: per-row party filtered by party_type ──
    frappe.ui.form.on("Journal Entry", {
        setup:   function(frm) { _je_filters(frm); },
        refresh: function(frm) { _je_filters(frm); },
        company: function(frm) { _je_filters(frm); }
    });
    frappe.ui.form.on("Journal Entry Account", {
        party_type: function(frm) { _je_filters(frm); }
    });

    function _je_filters(frm) {
        const company = frm.doc.company;
        frm.set_query("bank_account", "accounts", function() {
            return company ? { filters: { company: company } } : {};
        });
        frm.set_query("project", "accounts", function() {
            return company ? { filters: { custom_company: company } } : {};
        });
        frm.set_query("party", "accounts", function(doc, cdt, cdn) {
            const row = locals[cdt][cdn];
            if (!row.party_type) return {};
            return company
                ? { filters: { custom_company: company, disabled: 0 } }
                : { filters: { disabled: 0 } };
        });
    }


    // ── BANK ACCOUNT: party filtered by party_type ───────────
    frappe.ui.form.on("Bank Account", {
        setup:      function(frm) { _ba_party(frm); },
        refresh:    function(frm) { _ba_party(frm); },
        company:    function(frm) { _ba_party(frm); },
        party_type: function(frm) { _ba_party(frm); }
    });

    function _ba_party(frm) {
        if (!frm.doc.party_type || !frm.fields_dict.party) return;
        const company = frm.doc.company;
        frm.set_query("party", function() {
            return company
                ? { filters: { custom_company: company, disabled: 0 } }
                : { filters: { disabled: 0 } };
        });
    }

});
