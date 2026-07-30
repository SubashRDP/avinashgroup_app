// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sparrow SMS Settings", {
	send_test_sms: function (frm) {
		if (!frm.doc.test_mobile_no) {
			frappe.msgprint(__("Set a Test Mobile No first."));
			return;
		}
		frappe.call({
			method:
				"avinashgroup_app.sparrow_sms.doctype.sparrow_sms_settings.sparrow_sms_settings.send_test_sms",
			freeze: true,
			freeze_message: __("Sending test SMS..."),
		});
	},
});
