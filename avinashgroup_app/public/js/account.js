// After a NEW Account of type "Bank" is saved, ask for Bank + Account Number
// and create a Bank Account linked to it.
// Only in the Account form, not the Chart of Accounts tree.
// Server side: custom_code/bank_account_from_account.py

frappe.ui.form.on("Account", {
	validate(frm) {
		// validate runs before save, so is_new() is still true here
		frm._was_new_account = frm.is_new();
	},

	after_save(frm) {
		const was_new = frm._was_new_account;
		frm._was_new_account = false;

		if (!was_new) return;
		if (frm.doc.account_type !== "Bank" || frm.doc.is_group) return;

		frappe
			.call({
				method: "avinashgroup_app.custom_code.bank_account_from_account.has_bank_account",
				args: { account: frm.doc.name },
			})
			.then((r) => {
				if (!r.message) show_bank_account_dialog(frm);
			});
	},
});

function show_bank_account_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Create Bank Account"),
		fields: [
			{
				fieldname: "bank",
				fieldtype: "Link",
				label: __("Bank"),
				options: "Bank",
				reqd: 1,
			},
			{
				fieldname: "bank_account_no",
				fieldtype: "Data",
				label: __("Account Number"),
				reqd: 1,
			},
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			frappe
				.call({
					method: "avinashgroup_app.custom_code.bank_account_from_account.create_bank_account",
					args: {
						account: frm.doc.name,
						bank: values.bank,
						bank_account_no: values.bank_account_no,
					},
					freeze: true,
				})
				.then((r) => {
					dialog.hide();
					frappe.show_alert({
						message: __("Bank Account {0} created", [r.message]),
						indicator: "green",
					});
				});
		},
	});
	dialog.add_custom_action(__("Edit Full Form"), () => {
		const values = dialog.get_values();
		if (!values) return;

		dialog.hide();
		frappe.new_doc("Bank Account", {
			account_name: frm.doc.account_name,
			bank: values.bank,
			bank_account_no: values.bank_account_no,
			is_company_account: 1,
			company: frm.doc.company,
			account: frm.doc.name,
		});
	});
	dialog.show();
}
