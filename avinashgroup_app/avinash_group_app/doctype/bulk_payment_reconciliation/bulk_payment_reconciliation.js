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
		set_party_link_titles(frm);
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
				(r.message || []).forEach(({ party_title, ...row }) => {
					add_party_link_title(frm.doc.party_type, row.party, party_title);
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

function add_party_link_title(party_type, party, title) {
	if (party_type && party && title) {
		frappe.utils.add_link_title(party_type, party, title);
	}
}

function set_party_link_titles(frm) {
	const parties = [...new Set((frm.doc.parties || []).map((row) => row.party).filter(Boolean))];
	if (!frm.doc.party_type || !parties.length) return;

	frappe.call({
		method: "avinashgroup_app.avinash_group_app.doctype.bulk_payment_reconciliation.bulk_payment_reconciliation.get_party_titles",
		args: { party_type: frm.doc.party_type, parties },
		callback: (r) => {
			Object.entries(r.message || {}).forEach(([party, title]) => {
				add_party_link_title(frm.doc.party_type, party, title);
			});
			frm.refresh_field("parties");
		},
	});
}

frappe.ui.form.on("Bulk Payment Reconciliation Party", {
	parties_add(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "party_type", frm.doc.party_type);
	},
});
