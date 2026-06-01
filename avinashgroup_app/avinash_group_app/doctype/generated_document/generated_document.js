// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.ui.form.on("Generated Document", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Edit in Generator"), () => {
				frappe.route_options = { generated_document: frm.doc.name };
				frappe.set_route("document-generator");
			});
		}
	},
});
