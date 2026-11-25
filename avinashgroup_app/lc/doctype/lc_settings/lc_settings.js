// LC Settings: account filters per company row, and "Create Missing Accounts".

frappe.ui.form.on("LC Settings", {
	setup(frm) {
		const of_company = (root_type) => (doc, cdt, cdn) => ({
			filters: Object.assign({ company: locals[cdt][cdn].company, is_group: 0 }, root_type ? { root_type } : {}),
		});
		frm.set_query("margin_account", "company_accounts", of_company("Asset"));
		frm.set_query("transit_account", "company_accounts", of_company("Asset"));
		frm.set_query("vat_account", "company_accounts", of_company());
	},

	create_missing_accounts(frm) {
		frappe.confirm(
			__("Create the LC Margin and LC Goods in Transit accounts (and pick the VAT account) for every company that has no row yet?"),
			() =>
				frappe.call({
					method: "avinashgroup_app.lc.doctype.lc_settings.lc_settings.create_missing_accounts",
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
