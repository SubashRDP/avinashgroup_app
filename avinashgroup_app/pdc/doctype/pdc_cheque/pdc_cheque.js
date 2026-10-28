// PDC Cheque form: filters, "Get Outstanding Invoices", and one button per
// lifecycle step. Steps run server-side in pdc/lifecycle.py (run_action).

const PDC_API = "avinashgroup_app.pdc.lifecycle";

frappe.ui.form.on("PDC Cheque", {
	setup(frm) {
		frm.set_query("party_type", () => ({ filters: { name: ["in", ["Customer", "Supplier"]] } }));
		frm.set_query("party_account", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				account_type: frm.doc.party_type === "Supplier" ? "Payable" : "Receivable",
			},
		}));
		frm.set_query("bank_account", () => ({
			filters: { company: frm.doc.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] },
		}));
		frm.set_query("cost_center", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("reference_doctype", "references", () => ({
			filters: { name: frm.doc.party_type === "Supplier" ? "Purchase Invoice" : "Sales Invoice" },
		}));
		frm.set_query("reference_name", "references", () => ({
			filters: {
				company: frm.doc.company,
				docstatus: 1,
				outstanding_amount: [">", 0],
				[frm.doc.party_type === "Supplier" ? "supplier" : "customer"]: frm.doc.party,
			},
		}));
	},

	cheque_type(frm) {
		frm.set_value("party_type", frm.doc.cheque_type === "Issued" ? "Supplier" : "Customer");
	},

	party_type(frm) {
		frm.set_value("party", null);
	},

	party(frm) {
		["party_name", "party_account", "mobile_no"].forEach((f) => frm.set_value(f, null));
		frm.clear_table("references");
		frm.refresh_field("references");
		if (!frm.doc.party || !frm.doc.company) return;
		frappe.call({
			method: "erpnext.accounts.party.get_party_account",
			args: { party_type: frm.doc.party_type, party: frm.doc.party, company: frm.doc.company },
			callback: (r) => r.message && frm.set_value("party_account", r.message),
		});
	},

	get_outstanding_invoices(frm) {
		if (!frm.doc.party) {
			frappe.msgprint(__("Choose the party first."));
			return;
		}
		frappe.call({
			method: `${PDC_API}.get_outstanding_invoices`,
			args: {
				company: frm.doc.company,
				party_type: frm.doc.party_type,
				party: frm.doc.party,
				amount: frm.doc.amount,
			},
			callback: (r) => {
				frm.clear_table("references");
				(r.message || []).forEach((row) => {
					if (row.allocated_amount > 0) frm.add_child("references", row);
				});
				frm.refresh_field("references");
				frm.trigger("set_totals");
				if (!(r.message || []).length) frappe.show_alert(__("No outstanding invoices"));
			},
		});
	},

	amount(frm) {
		frm.trigger("set_totals");
	},

	set_totals(frm) {
		const total = (frm.doc.references || []).reduce((s, r) => s + flt(r.allocated_amount), 0);
		frm.set_value("total_allocated", total);
		frm.set_value("unallocated_amount", flt(frm.doc.amount) - total);
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		const s = frm.doc.status;
		const received = frm.doc.cheque_type === "Received";
		const add = (label, fn, group) => frm.add_custom_button(__(label), fn, group && __(group));

		if (received && s === "In Hand") add("Deposit", () => step_dialog(frm, "deposit"), "Actions");
		if (received && ["In Hand", "Deposited"].includes(s)) add("Clear", () => step_dialog(frm, "clear"), "Actions");
		if (!received && s === "Issued") add("Clear", () => step_dialog(frm, "clear"), "Actions");
		if ((received && ["Deposited", "Cleared"].includes(s)) || (!received && ["Issued", "Cleared"].includes(s)))
			add("Bounce", () => bounce_dialog(frm), "Actions");
		const from_pe = !!frm.doc.payment_entry;
		if (received && s === "Bounced" && !from_pe) add("Re-deposit", () => step_dialog(frm, "redeposit"), "Actions");
		if (from_pe && s === "Bounced") add("Re-present", () => step_dialog(frm, "represent"), "Actions");
		if ((received && ["In Hand", "Bounced"].includes(s)) || (!received && s === "Issued"))
			add(received ? "Return to Party" : "Stop / Take Back", () => step_dialog(frm, "return"), "Actions");
		if (["Bounced", "Returned"].includes(s)) {
			add("Replace With New Payment", () => replace_with_payment(frm), "Actions");
			add("Replace With PDC Cheque", () => replace(frm), "Actions");
		}
		if (from_pe) add("Payment Entry", () => frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry));
		if ((frm.doc.events || []).length > 1 && s !== "Replaced" && frappe.user.has_role(["Accounts Manager", "System Manager"]))
			add("Undo Last Step", () => undo(frm), "Actions");

		if (received && frm.doc.deposit_date)
			add("Deposit Slip", () => frappe.set_route("print", "PDC Cheque", frm.doc.name, { format: "PDC Deposit Slip" }));

		add("Journal Entries", () =>
			frappe.set_route("List", "Journal Entry", { pdc_cheque: frm.doc.name })
		);

		const colour = { Cleared: "green", Bounced: "red", Returned: "grey", Replaced: "grey", Deposited: "blue" }[s] || "orange";
		frm.page.set_indicator(__(s), colour);
	},
});

frappe.ui.form.on("PDC Cheque Reference", {
	allocated_amount(frm) {
		frm.trigger("set_totals");
	},
	references_remove(frm) {
		frm.trigger("set_totals");
	},
	reference_name(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.reference_name) return;
		frappe.db
			.get_value(row.reference_doctype, row.reference_name, ["due_date", "grand_total", "outstanding_amount"])
			.then(({ message: v }) => {
				frappe.model.set_value(cdt, cdn, {
					due_date: v.due_date,
					grand_total: v.grand_total,
					outstanding_amount: v.outstanding_amount,
					allocated_amount: v.outstanding_amount,
				});
			});
	},
});

const STEP_TITLES = {
	deposit: "Deposit Cheque",
	clear: "Mark Cleared",
	redeposit: "Re-deposit Bounced Cheque",
	return: "Return / Stop Cheque",
	represent: "Present Cheque Again",
};

function run_step(frm, action, args) {
	return frappe.call({
		method: `${PDC_API}.run_action`,
		args: Object.assign({ name: frm.doc.name, action }, args),
		freeze: true,
		callback: () => frm.reload_doc(),
	});
}

function bank_field(frm, reqd) {
	return {
		fieldname: "bank_account",
		fieldtype: "Link",
		options: "Account",
		label: __("Bank Account"),
		reqd: reqd ? 1 : 0,
		default: frm.doc.deposit_account || frm.doc.bank_account,
		get_query: () => ({
			filters: { company: frm.doc.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] },
		}),
	};
}

function step_dialog(frm, action) {
	const fields = [
		{ fieldname: "posting_date", fieldtype: "Date", label: __("Date"), reqd: 1, default: frappe.datetime.get_today() },
	];
	if (["deposit", "redeposit"].includes(action) || (action === "clear" && frm.doc.cheque_type === "Received"))
		fields.push(bank_field(frm, 1));
	if (action === "return") fields.push({ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") });

	const d = new frappe.ui.Dialog({
		title: __(STEP_TITLES[action]),
		fields,
		primary_action_label: __("Confirm"),
		primary_action(values) {
			d.hide();
			run_step(frm, action, values);
		},
	});
	d.show();
}

function bounce_dialog(frm) {
	const received = frm.doc.cheque_type === "Received";
	const d = new frappe.ui.Dialog({
		title: __("Cheque Bounced"),
		fields: [
			{ fieldname: "posting_date", fieldtype: "Date", label: __("Bounce Date"), reqd: 1, default: frappe.datetime.get_today() },
			{
				fieldname: "reason",
				fieldtype: "Select",
				label: __("Reason"),
				reqd: 1,
				options: frappe.meta.get_docfield("PDC Cheque", "bounce_reason").options,
			},
			{ fieldname: "charges", fieldtype: "Currency", label: __("Bank Charges"), default: 0 },
			{
				fieldname: "jv_type",
				fieldtype: "Link",
				options: "JV Type",
				label: __("Journal Type"),
				reqd: 1,
				description: __("Numbering series of the bounce Journal Entry"),
			},
			{
				fieldname: "recover_charges",
				fieldtype: "Check",
				label: __("Recover Charges From Party"),
				hidden: received ? 0 : 1,
				description: __("Debit the customer for the charge instead of booking it as an expense"),
			},
		],
		primary_action_label: __("Record Bounce"),
		primary_action(values) {
			d.hide();
			run_step(frm, "bounce", values);
		},
	});
	d.show();
	// Journal Type defaults to PDC Settings → JV Type; the user may pick another.
	frappe.db.get_single_value("PDC Settings", "jv_type").then((v) => v && d.set_value("jv_type", v));
}

function replace(frm) {
	frappe.call({
		method: `${PDC_API}.make_replacement`,
		args: { name: frm.doc.name },
		callback: (r) => {
			const doc = frappe.model.sync(r.message)[0];
			frappe.set_route("Form", doc.doctype, doc.name);
		},
	});
}

function replace_with_payment(frm) {
	frappe.call({
		method: "avinashgroup_app.pdc.payment_entry_bounce.make_replacement_payment_entry",
		args: { name: frm.doc.name },
		callback: (r) => {
			const doc = frappe.model.sync(r.message)[0];
			frappe.set_route("Form", doc.doctype, doc.name);
		},
	});
}

function undo(frm) {
	const last = frm.doc.events[frm.doc.events.length - 1];
	frappe.confirm(
		__("Undo <b>{0}</b> of {1}? Its Journal Entry {2} will be cancelled.", [
			last.event,
			frappe.datetime.str_to_user(last.event_date),
			last.journal_entry || __("(none)"),
		]),
		() =>
			frappe.call({
				method: `${PDC_API}.undo`,
				args: { name: frm.doc.name },
				freeze: true,
				callback: () => frm.reload_doc(),
			})
	);
}
