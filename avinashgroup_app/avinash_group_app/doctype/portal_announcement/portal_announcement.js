// Copyright (c) 2026, Avinash Group and contributors
// For license information, please see license.txt

frappe.ui.form.on("Portal Announcement", {
	refresh(frm) {
		frm.dashboard.clear_comment();
		if (frm.doc.custom_html) {
			frm.dashboard.add_comment(
				__("Custom HTML is set — it replaces the Message. The Image, if set, still shows above it."),
				"blue",
				true
			);
		}
	},
});
