// Bulk Payment Reconciliation — choosing Company / Party Type fills the Parties
// table from bulk_payment_reconciliation.get_parties. Submitting creates one
// Process Payment Reconciliation per row (server side, on_submit).
frappe.ui.form.on("Bulk Payment Reconciliation", {
	setup(frm) {
		frm.set_query("party_type", () => ({
			filters: { name: ["in", ["Customer", "Supplier"]] },
		}));
		// same account filters as the Process Payment Reconciliation form
		frm.set_query("receivable_payable_account", "parties", (doc) => ({
			filters: {
				company: doc.company,
				is_group: 0,
				account_type: doc.party_type == "Customer" ? "Receivable" : "Payable",
			},
		}));
		frm.set_query("default_advance_account", "parties", (doc) => ({
			filters: {
				company: doc.company,
				is_group: 0,
				account_type: doc.party_type == "Customer" ? "Receivable" : "Payable",
				root_type: doc.party_type == "Customer" ? "Liability" : "Asset",
			},
		}));
		frm.set_query("cost_center", "parties", (doc) => ({
			filters: { company: doc.company, is_group: 0 },
		}));
		frm.set_query("bank_cash_account", "parties", (doc) => ({
			filters: [
				["Account", "company", "=", doc.company],
				["Account", "is_group", "=", 0],
				["Account", "account_type", "in", ["Bank", "Cash"]],
			],
		}));
		frm.set_query("party", "parties", (doc) => ({
			filters: { custom_company: doc.company, disabled: 0 },
		}));
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Parties"), () => frm.events.fill_parties(frm));
		}
	},

	company(frm) {
		frm.events.fill_parties(frm);
	},

	party_type(frm) {
		frm.events.fill_parties(frm);
	},

	only_with_open_items(frm) {
		frm.events.fill_parties(frm);
	},

	fill_parties(frm) {
		if (!frm.doc.company || !frm.doc.party_type || frm.doc.docstatus !== 0) return;

		frappe.call({
			method: "avinashgroup_app.avinash_group_app.doctype.bulk_payment_reconciliation.bulk_payment_reconciliation.get_parties",
			args: {
				company: frm.doc.company,
				party_type: frm.doc.party_type,
				only_with_open_items: frm.doc.only_with_open_items,
			},
			freeze: true,
			freeze_message: __("Getting parties..."),
			callback: (r) => {
				frm.clear_table("parties");
				(r.message || []).forEach((row) => {
					frm.add_child("parties", { ...row, party_type: frm.doc.party_type });
				});
				frm.refresh_field("parties");
				frappe.show_alert({
					message: __("{0} parties added", [(r.message || []).length]),
					indicator: "green",
				});
			},
		});
	},
});

frappe.ui.form.on("Bulk Payment Reconciliation Party", {
	parties_add(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "party_type", frm.doc.party_type);
	},

	// a party picked by hand shows its name straight away (save sets it too)
	party(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.party) return frappe.model.set_value(cdt, cdn, "party_name", "");
		const name_field = frm.doc.party_type == "Supplier" ? "supplier_name" : "customer_name";
		frappe.db.get_value(frm.doc.party_type, row.party, name_field).then((r) => {
			frappe.model.set_value(cdt, cdn, "party_name", (r.message || {})[name_field]);
		});
	},
});
