// PDC Settings: account filters per company row, and "Create Missing Accounts".

frappe.ui.form.on("PDC Settings", {
	setup(frm) {
		const by_company = (root_type) => (doc, cdt, cdn) => ({
			filters: { company: locals[cdt][cdn].company, is_group: 0, root_type },
		});
		frm.set_query("cheques_in_hand_account", "company_accounts", by_company("Asset"));
		frm.set_query("cheques_issued_account", "company_accounts", by_company("Liability"));
		frm.set_query("bounce_charges_account", "company_accounts", by_company("Expense"));
	},

	create_missing_accounts(frm) {
		frappe.confirm(
			__("Create Cheques in Hand, Cheques Issued and Cheque Bounce Charges accounts for every company that has no row yet?"),
			() =>
				frappe.call({
					method: "avinashgroup_app.pdc.doctype.pdc_settings.pdc_settings.create_missing_accounts",
					freeze: true,
					callback: (r) => {
						frappe.msgprint(
							(r.message || []).length
								? __("Added: {0}", [r.message.join(", ")])
								: __("Every company already has a row.")
						);
						frm.reload_doc();
					},
				})
		);
	},
});
