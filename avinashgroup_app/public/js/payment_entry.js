frappe.ui.form.on("Payment Entry", {
	refresh: function (frm) {
		if (frm.doc.custom_cheque_bounce === "Cheque Bounced") {
			frm.page.set_indicator(__("Cheque Bounced"), "red");
		}

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("Cheque Bounce"),
				function () {
					frappe.confirm(
						__(
							"Are you sure you want to mark this as a Cheque Bounce? Reversed GL entries will be posted for <b>{0}</b>.",
							[frm.doc.name]
						),
						function () {
							frappe.call({
								method: "avinashgroup_app.custom_code.payment_entry.cheque_bounce.make_cheque_bounce_entry",
								args: { payment_entry_name: frm.doc.name },
								freeze: true,
								freeze_message: __("Posting Cheque Bounce GL Entries..."),
								callback: function (r) {
									if (!r.exc) {
										frm.reload_doc();
									}
								},
							});
						}
					);
				},
				__("Actions")
			);
		}
	},
});
