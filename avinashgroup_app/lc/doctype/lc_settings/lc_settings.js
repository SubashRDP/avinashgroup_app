// LC Settings: account filters per company row, and "Create Missing Accounts".

frappe.ui.form.on("LC Settings", {
	setup(frm) {
		const assets = (doc, cdt, cdn) => ({
			filters: { company: locals[cdt][cdn].company, is_group: 0, root_type: "Asset" },
		});
		frm.set_query("margin_account", "company_accounts", assets);
		frm.set_query("charges_account", "company_accounts", assets);
	},

	create_missing_accounts(frm) {
		frappe.confirm(
			__("Create LC Margin and LC Charges Clearing accounts for every company that has no row yet?"),
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
