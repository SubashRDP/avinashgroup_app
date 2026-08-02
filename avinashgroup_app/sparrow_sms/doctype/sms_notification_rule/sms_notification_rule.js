// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.ui.form.on("SMS Notification Rule", {
	document_type: function (frm) {
		frm.trigger("load_recipient_field_options");
	},

	refresh: function (frm) {
		frm.trigger("load_recipient_field_options");
	},

	load_recipient_field_options: function (frm) {
		if (!frm.doc.document_type) {
			return;
		}

		frappe.call({
			method: "avinashgroup_app.sparrow_sms.doctype.sms_notification_rule.sms_notification_rule.get_recipient_field_options",
			args: { document_type: frm.doc.document_type },
			callback: function (r) {
				const options = (r.message || []).map((o) => ({
					value: o.value,
					label: o.label,
				}));

				frm.fields_dict.recipients.grid.update_docfield_property(
					"recipient_field",
					"options",
					[""].concat(options)
				);
			},
		});
	},
});
