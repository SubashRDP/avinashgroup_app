// Exact record names from the "Payment - Receipt Type" master (same on all sites)
const P_TYPE_TO_PAYMENT_TYPE = {
	"Bank Customers Receipt": "Receive",
	"Vendor Receipt": "Receive",
	"Customers/Suppliers Receipt": "Receive",
	"NOC Payment": "Pay",
	"Vendor Payment": "Pay",
	"Contra Voucher- cash to bank": "Internal Transfer",
};

frappe.ui.form.on("Payment Entry", {
	custom_p_type: function (frm) {
		const payment_type = P_TYPE_TO_PAYMENT_TYPE[frm.doc.custom_p_type];
		if (payment_type && frm.doc.payment_type !== payment_type) {
			frm.set_value("payment_type", payment_type);
		}
	},
	setup_party_query: function (frm) {
		if (!frm.fields_dict.party) return;
		frm.set_query("party", function () {
			const party_type = frm.doc.party_type;
			const company = frm.doc.company;
			if (!party_type || !company) {
				return {};
			}
			return {
				query: "avinashgroup_app.custom_code.globalfilter.globalfilter.search_party",
				filters: {
					party_type: party_type,
					company: company,
				},
			};
		});
	},
	onload: function (frm) {
		frm.trigger("setup_party_query");
	},
	refresh: function (frm) {
		frm.trigger("setup_party_query");
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
	company: function (frm) {
		frm.trigger("setup_party_query");
	},
	party_type: function (frm) {
		frm.trigger("setup_party_query");
	},
});
