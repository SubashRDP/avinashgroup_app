// Bulk Payment Reconciliation — the Parties table starts empty. Rows can be
// added by hand, or the "Get Parties" button replaces the table with every
// party from bulk_payment_reconciliation.get_parties.
// The account / date fields on the main form are copied into every row: when a
// row is added, when Get Parties fills the table, and when a main field changes.
// Submitting creates one Process Payment Reconciliation per row (server side, on_submit).

// Main-form fields that have a field of the same name in each party row.
const ACCOUNT_FIELDS = ["receivable_payable_account", "default_advance_account"];
const OTHER_FIELDS = [
	"from_invoice_date",
	"to_invoice_date",
	"from_payment_date",
	"to_payment_date",
	"bank_cash_account",
];

frappe.ui.form.on("Bulk Payment Reconciliation", {
	setup(frm) {
		frm.set_query("party_type", () => ({
			filters: { name: ["in", ["Customer", "Supplier"]] },
		}));

		// same account filters as the Process Payment Reconciliation form,
		// used for the main-form field and the row field of the same name
		const receivable_payable_query = (doc) => ({
			filters: {
				company: doc.company,
				is_group: 0,
				account_type: doc.party_type == "Customer" ? "Receivable" : "Payable",
			},
		});
		const advance_query = (doc) => ({
			filters: {
				company: doc.company,
				is_group: 0,
				account_type: doc.party_type == "Customer" ? "Receivable" : "Payable",
				root_type: doc.party_type == "Customer" ? "Liability" : "Asset",
			},
		});
		const bank_cash_query = (doc) => ({
			filters: [
				["Account", "company", "=", doc.company],
				["Account", "is_group", "=", 0],
				["Account", "account_type", "in", ["Bank", "Cash"]],
			],
		});

		frm.set_query("receivable_payable_account", receivable_payable_query);
		frm.set_query("default_advance_account", advance_query);
		frm.set_query("bank_cash_account", bank_cash_query);

		frm.set_query("receivable_payable_account", "parties", receivable_payable_query);
		frm.set_query("default_advance_account", "parties", advance_query);
		frm.set_query("bank_cash_account", "parties", bank_cash_query);
		frm.set_query("cost_center", "parties", (doc) => ({
			filters: { company: doc.company, is_group: 0 },
		}));
		frm.set_query("party", "parties", (doc) => ({
			filters: { custom_company: doc.company, disabled: 0 },
		}));
	},

	refresh(frm) {
		set_party_type_on_rows(frm);
		set_party_link_titles(frm);
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Parties"), () => frm.events.fill_parties(frm));
		}
	},

	party_type(frm) {
		set_party_type_on_rows(frm);
	},

	// Replaces the whole Parties table (rows added by hand are removed too).
	fill_parties(frm) {
		if (frm.doc.docstatus !== 0) return;
		if (!frm.doc.company || !frm.doc.party_type) {
			frappe.msgprint(__("Select Company and Party Type first"));
			return;
		}

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
					// main-form values win; a blank main account keeps the party's own account
					frm.add_child("parties", {
						...row,
						...main_form_values(frm),
						party_type: frm.doc.party_type,
					});
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

// Changing a main-form field copies the new value into every row.
// A cleared main account is not copied, so rows keep the account they have.
ACCOUNT_FIELDS.forEach((fieldname) => {
	frappe.ui.form.on("Bulk Payment Reconciliation", fieldname, (frm) => {
		if (frm.doc[fieldname]) copy_to_rows(frm, fieldname);
	});
});
OTHER_FIELDS.forEach((fieldname) => {
	frappe.ui.form.on("Bulk Payment Reconciliation", fieldname, (frm) => {
		copy_to_rows(frm, fieldname);
	});
});

// The row's Party field is a Dynamic Link on party_type, so a row without
// party_type shows no Party dropdown. The blank row Frappe adds to a new form
// does not go through parties_add, so it is set here too.
function set_party_type_on_rows(frm) {
	if (frm.doc.docstatus !== 0) return;
	(frm.doc.parties || []).forEach((row) => {
		row.party_type = frm.doc.party_type;
	});
	frm.refresh_field("parties");
}

function copy_to_rows(frm, fieldname) {
	(frm.doc.parties || []).forEach((row) => {
		row[fieldname] = frm.doc[fieldname] || null;
	});
	frm.refresh_field("parties");
	frm.dirty();
}

// Main-form values to put in a row: all date / bank fields, and the account
// fields only when they are set.
function main_form_values(frm) {
	const values = {};
	ACCOUNT_FIELDS.forEach((fieldname) => {
		if (frm.doc[fieldname]) values[fieldname] = frm.doc[fieldname];
	});
	OTHER_FIELDS.forEach((fieldname) => {
		values[fieldname] = frm.doc[fieldname] || null;
	});
	return values;
}

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
	// a row added by hand starts with the main-form values
	parties_add(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		Object.assign(row, main_form_values(frm), { party_type: frm.doc.party_type });
		frm.refresh_field("parties");
	},
});
