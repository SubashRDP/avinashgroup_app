// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.ui.form.on("CBMS Bill Return", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.sync_status === "Synced") return;

		frm.add_custom_button(__("Sync Now"), () => {
			frappe.call({
				method: "avinashgroup_app.custom_code.CBMS.api_client.sync_now",
				args: { cbms_doctype: frm.doc.doctype, name: frm.doc.name },
				freeze: true,
				freeze_message: __("Sending to CBMS/IRD..."),
			}).then((r) => {
				const m = r.message || {};
				frm.reload_doc();
				if (m.ok) {
					frappe.show_alert({ message: __("Synced with CBMS"), indicator: "green" });
				} else if (m.held) {
					frappe.msgprint({
						title: __("Held"),
						indicator: "orange",
						message: __(
							"The original invoice's CBMS Bill is not Synced yet — sync that bill first; this return will also be retried automatically."
						),
					});
				} else {
					frappe.msgprint({
						title: __("Not Synced"),
						indicator: "red",
						message: m.sync_response
							? __("CBMS rejected the request: {0}", [m.sync_response])
							: __("Sync did not complete — see the CBMS Activity Report for details."),
					});
				}
			});
		}).addClass("btn-primary");
	},
});
