// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.ui.form.on("Company Print Template", {
	setup(frm) {
		frm.set_query("document_type", () => ({
			filters: { istable: 0 },
		}));
		const format_query = () => ({
			filters: { doc_type: frm.doc.document_type || "" },
		});
		frm.set_query("print_format", "companies", format_query);
		frm.set_query("return_print_format", "companies", format_query);
	},

	document_type(frm) {
		// Formats chosen for the previous doctype are never valid for the new one.
		(frm.doc.companies || []).forEach((row) => {
			if (row.print_format) {
				frappe.model.set_value(row.doctype, row.name, "print_format", "");
			}
			if (row.return_print_format) {
				frappe.model.set_value(row.doctype, row.name, "return_print_format", "");
			}
		});
	},
});
