// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sparrow SMS Log", {
	refresh: function (frm) {
		if (frm.is_new()) {
			return;
		}

		// The whole record is read-only, so the only thing the form can do is
		// push the message at the gateway again.
		const label = frm.doc.status === "Sent" ? __("Send Again") : __("Resend");
		frm.add_custom_button(label, () => resend(frm));

		if (frm.doc.status === "Failed") {
			frm.page.set_indicator(__("Failed"), "red");
		} else if (frm.doc.status === "Sent") {
			frm.page.set_indicator(__("Sent"), "green");
		} else {
			frm.page.set_indicator(__("Queued"), "orange");
		}
	},
});

function resend(frm) {
	const number = frm.doc.mobile_no || frm.doc.raw_mobile_no;
	const asks = number
		? __("Send this message to <b>{0}</b> again?", [frappe.utils.escape_html(number)])
		: __("This log has no number. Read it off {0} again and send?", [
				frappe.utils.escape_html(frm.doc.reference_name || __("the reference document")),
		  ]);

	frappe.confirm(asks, () => {
		frappe.call({
			method: "avinashgroup_app.sparrow_sms.doctype.sparrow_sms_log.sparrow_sms_log.resend",
			args: { log: frm.doc.name },
			freeze: true,
			freeze_message: __("Sending..."),
			callback: (r) => {
				const ok = r.message && r.message.ok;
				frappe.show_alert({
					message: ok
						? __("Sent to {0}", [r.message.receiver])
						: __("Failed — a new log row records why"),
					indicator: ok ? "green" : "red",
				});
			},
		});
	});
}
