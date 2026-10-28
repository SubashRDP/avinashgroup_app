// Letter of Credit: one button group per stage, each a dialog that calls
// lc/lifecycle.py run_action. The form itself is only edited as a draft.

const LC_API = "avinashgroup_app.lc.lifecycle";
const OPEN = ["Opened", "Partly Settled", "Settled"];

frappe.ui.form.on("Letter of Credit", {
	setup(frm) {
		frm.set_query("bank_account", () => ({
			filters: { company: frm.doc.company, is_company_account: 1 },
		}));
		frm.set_query("purchase_order", "purchase_orders", () => ({
			filters: {
				company: frm.doc.company,
				supplier: frm.doc.supplier,
				currency: frm.doc.currency,
				docstatus: 1,
			},
		}));
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		const status = frm.doc.status;
		const group = __("LC");
		const ship = __("Shipment");

		if (status === "Applied") {
			frm.add_custom_button(__("Mark Opened by Bank"), () => lc_open(frm), group);
		}
		if (status === "Applied" || OPEN.includes(status)) {
			frm.add_custom_button(__("Add Bank Charge"), () => lc_charge(frm), group);
		}
		if (OPEN.includes(status)) {
			frm.add_custom_button(__("Deposit Margin"), () => lc_margin(frm), group);
			frm.add_custom_button(__("Amend"), () => lc_amend(frm), group);
			frm.add_custom_button(__("Close"), () => lc_close(frm), group);

			if (status !== "Settled") {
				frm.add_custom_button(__("Add Shipment"), () => lc_add_shipment(frm), ship);
			}
			const by_status = (s) => (frm.doc.shipments || []).filter((r) => s.includes(r.status));
			if (by_status(["Shipped"]).length) {
				frm.add_custom_button(__("Documents Received"), () => lc_docs(frm), ship);
			}
			if (frm.doc.drafts_at === "Usance" && by_status(["Docs Received"]).length) {
				frm.add_custom_button(__("Accept"), () => lc_accept(frm), ship);
			}
			if (by_status([frm.doc.drafts_at === "Usance" ? "Accepted" : "Docs Received"]).length) {
				frm.add_custom_button(__("Settle"), () => lc_settle(frm), ship);
			}
			if (by_status(["Shipped", "Docs Received", "Accepted"]).length) {
				frm.add_custom_button(__("Link Receipt / Invoice"), () => lc_link(frm), ship);
			}
		}
		if ((frm.doc.shipments || []).some((r) => r.status === "Settled")) {
			frm.add_custom_button(__("Customs Proof"), () => lc_customs(frm), ship);
		}
		if (frm.doc.charges_total > 0) {
			frm.add_custom_button(__("Landed Cost Voucher"), () => {
				frappe.call({
					method: "avinashgroup_app.lc.accounting.make_landed_cost_voucher",
					args: { name: frm.doc.name },
					freeze: true,
					callback: (r) => {
						const doc = frappe.model.sync(r.message)[0];
						frappe.set_route("Form", doc.doctype, doc.name);
					},
				});
			}, __("Create"));
		}
		if ((frm.doc.events || []).length > 1 && frm.doc.status !== "Cancelled") {
			frm.add_custom_button(__("Undo Last Step"), () => {
				const last = frm.doc.events[frm.doc.events.length - 1];
				frappe.confirm(
					__("Undo {0}{1}? Its Journal Entry, if any, is cancelled.", [
						last.event,
						last.shipment_no ? ` (${__("shipment")} ${last.shipment_no})` : "",
					]),
					() => frappe.call({ method: `${LC_API}.undo`, args: { name: frm.doc.name }, freeze: true })
						.then(() => frm.reload_doc())
				);
			}, group);
		}
		frm.add_custom_button(__("Journal Entries"), () =>
			frappe.set_route("List", "Journal Entry", { letter_of_credit: frm.doc.name }), __("View"));
	},

	company(frm) {
		frm.set_value("bank_account", null);
	},
});

function lc_run(frm, action, values, dialog) {
	return frappe.call({
		method: `${LC_API}.run_action`,
		args: Object.assign({ name: frm.doc.name, action }, values),
		freeze: true,
		callback: () => {
			dialog && dialog.hide();
			frm.reload_doc();
		},
	});
}

const bank_field = (frm) => ({
	fieldname: "bank_account", label: __("Bank Account (Ledger)"), fieldtype: "Link", options: "Account",
	default: frm.doc.bank_gl_account,
	get_query: () => ({ filters: { company: frm.doc.company, account_type: ["in", ["Bank", "Cash"]], is_group: 0 } }),
});

function shipment_field(frm, statuses, label) {
	const rows = (frm.doc.shipments || []).filter((r) => !statuses || statuses.includes(r.status));
	return {
		fieldname: "shipment_no", label: label || __("Shipment"), fieldtype: "Select", reqd: 1,
		options: rows.map((r) => ({
			value: String(r.shipment_no),
			label: `${r.shipment_no}: ${r.transport_doc_no} · ${frm.doc.currency} ${format_number(r.amount, null, 2)} · ${__(r.status)}`,
		})),
		default: rows.length ? String(rows[0].shipment_no) : null,
	};
}

function lc_dialog(frm, title, fields, action, primary, prepare) {
	const d = new frappe.ui.Dialog({
		title, fields,
		primary_action_label: primary || __("Save"),
		primary_action: (values) => lc_run(frm, action, prepare ? prepare(values) : values, d),
	});
	d.show();
	return d;
}

function lc_open(frm) {
	lc_dialog(frm, __("LC Opened by Bank"), [
		{ fieldname: "lc_no", label: __("Bank LC Number"), fieldtype: "Data", reqd: 1 },
		{ fieldname: "issue_date", label: __("Issue Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "margin", label: __("Margin Blocked by the Bank"), fieldtype: "Currency",
			default: frm.doc.required_margin,
			description: __("Posts Dr LC Margin / Cr Bank. 0 if the bank took none") },
		bank_field(frm),
	], "open", __("Mark Opened"));
}

function lc_margin(frm) {
	lc_dialog(frm, __("Deposit Margin"), [
		{ fieldname: "posting_date", label: __("Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1 },
		bank_field(frm),
	], "deposit_margin", __("Deposit"));
}

function lc_charge(frm) {
	lc_dialog(frm, __("Bank Charge on the LC"), [
		{ fieldname: "charge_type", label: __("Charge"), fieldtype: "Select", reqd: 1,
			options: "LC Opening Commission\nAmendment Charge\nSWIFT Charge\nAcceptance Commission\nConfirmation Charge\nDiscrepancy Fee\nInsurance\nOther",
			default: frm.doc.status === "Applied" ? "LC Opening Commission" : "SWIFT Charge" },
		{ fieldname: "posting_date", label: __("Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1 },
		bank_field(frm),
		{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Data" },
	], "add_charge", __("Book Charge"));
}

function lc_amend(frm) {
	const fields = [
		{ fieldname: "posting_date", label: __("Amendment Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "beneficiary_accepted", label: __("Beneficiary Accepted"), fieldtype: "Check", default: 1 },
		{ fieldtype: "Section Break", label: __("New Terms (leave unchanged ones as they are)") },
		{ fieldname: "lc_amount", label: __("LC Amount"), fieldtype: "Float", default: frm.doc.lc_amount },
		{ fieldname: "tolerance_plus", label: __("Tolerance + %"), fieldtype: "Percent", default: frm.doc.tolerance_plus },
		{ fieldname: "tolerance_minus", label: __("Tolerance − %"), fieldtype: "Percent", default: frm.doc.tolerance_minus },
		{ fieldname: "usance_days", label: __("Usance Days"), fieldtype: "Int", default: frm.doc.usance_days,
			hidden: frm.doc.drafts_at !== "Usance" },
		{ fieldtype: "Column Break" },
		{ fieldname: "expiry_date", label: __("Expiry Date"), fieldtype: "Date", default: frm.doc.expiry_date },
		{ fieldname: "latest_shipment_date", label: __("Latest Shipment Date"), fieldtype: "Date", default: frm.doc.latest_shipment_date },
		{ fieldname: "presentation_days", label: __("Presentation Period (Days)"), fieldtype: "Int", default: frm.doc.presentation_days },
		{ fieldname: "partial_shipment", label: __("Partial Shipment"), fieldtype: "Select", options: "Allowed\nNot Allowed", default: frm.doc.partial_shipment },
		{ fieldname: "transhipment", label: __("Transhipment"), fieldtype: "Select", options: "Allowed\nNot Allowed", default: frm.doc.transhipment },
		{ fieldtype: "Section Break" },
		{ fieldname: "port_of_loading", label: __("Port / Place of Loading"), fieldtype: "Data", default: frm.doc.port_of_loading },
		{ fieldname: "port_of_discharge", label: __("Port of Discharge"), fieldtype: "Data", default: frm.doc.port_of_discharge },
		{ fieldname: "customs_point", label: __("Nepal Customs Point"), fieldtype: "Data", default: frm.doc.customs_point },
		{ fieldtype: "Section Break", label: __("Amendment Charge") },
		{ fieldname: "charge", label: __("Charge"), fieldtype: "Currency" },
		bank_field(frm),
		{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Data" },
	];
	const terms = ["lc_amount", "tolerance_plus", "tolerance_minus", "usance_days", "expiry_date",
		"latest_shipment_date", "presentation_days", "partial_shipment", "transhipment",
		"port_of_loading", "port_of_discharge", "customs_point"];
	lc_dialog(frm, __("Amend LC"), fields, "amend", __("Record Amendment"), (v) => {
		const changes = {};
		terms.forEach((t) => { changes[t] = v[t]; });
		return {
			posting_date: v.posting_date, beneficiary_accepted: v.beneficiary_accepted ? 1 : 0,
			charge: v.charge || 0, bank_account: v.bank_account, remarks: v.remarks,
			changes: JSON.stringify(changes),
		};
	});
}

function lc_add_shipment(frm) {
	const doc_filter = () => ({
		filters: { company: frm.doc.company, supplier: frm.doc.supplier, currency: frm.doc.currency, docstatus: 1 },
	});
	lc_dialog(frm, __("Add Shipment"), [
		{ fieldname: "transport_doc_no", label: __("B/L / AWB / Consignment Note No."), fieldtype: "Data", reqd: 1 },
		{ fieldname: "transport_doc_date", label: __("Shipment Date"), fieldtype: "Date", reqd: 1,
			description: __("Must be on or before {0}", [frappe.datetime.str_to_user(frm.doc.latest_shipment_date)]) },
		{ fieldname: "amount", label: __("Amount ({0})", [frm.doc.currency]), fieldtype: "Float", reqd: 1,
			default: frm.doc.available_amount,
			description: __("Available: {0} {1}", [frm.doc.currency, format_number(frm.doc.available_amount, null, 2)]) },
		{ fieldtype: "Column Break" },
		{ fieldname: "invoice_no", label: __("Supplier Invoice No."), fieldtype: "Data" },
		{ fieldname: "invoice_date", label: __("Invoice Date"), fieldtype: "Date" },
		{ fieldname: "purchase_receipt", label: __("Purchase Receipt"), fieldtype: "Link", options: "Purchase Receipt", get_query: doc_filter },
		{ fieldname: "purchase_invoice", label: __("Purchase Invoice"), fieldtype: "Link", options: "Purchase Invoice", get_query: doc_filter },
	], "add_shipment", __("Add"));
}

function lc_link(frm) {
	const doc_filter = () => ({
		filters: { company: frm.doc.company, supplier: frm.doc.supplier, currency: frm.doc.currency, docstatus: 1 },
	});
	lc_dialog(frm, __("Link Purchase Receipt / Invoice"), [
		shipment_field(frm, ["Shipped", "Docs Received", "Accepted"]),
		{ fieldname: "purchase_receipt", label: __("Purchase Receipt"), fieldtype: "Link", options: "Purchase Receipt", get_query: doc_filter },
		{ fieldname: "purchase_invoice", label: __("Purchase Invoice"), fieldtype: "Link", options: "Purchase Invoice", get_query: doc_filter,
			description: __("The settlement clears this invoice at its own exchange rate") },
	], "link_documents", __("Link"));
}

function lc_docs(frm) {
	lc_dialog(frm, __("Shipping Documents Received"), [
		shipment_field(frm, ["Shipped"]),
		{ fieldname: "posting_date", label: __("Received On"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "discrepancies", label: __("Discrepancies"), fieldtype: "Small Text",
			description: __("As the bank's discrepancy notice lists them. Late presentation is added automatically") },
	], "docs_received", __("Save"));
}

function lc_accept(frm) {
	lc_dialog(frm, __("Accept Documents (Usance)"), [
		shipment_field(frm, ["Docs Received"]),
		{ fieldname: "posting_date", label: __("Accepted On"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "maturity_date", label: __("Maturity Date"), fieldtype: "Date",
			description: __("Blank: {0} days from the {1}", [frm.doc.usance_days, frm.doc.usance_basis]) },
	], "accept", __("Accept"));
}

function lc_settle(frm) {
	const status = frm.doc.drafts_at === "Usance" ? "Accepted" : "Docs Received";
	const d = new frappe.ui.Dialog({
		title: __("Settle Shipment"),
		fields: [
			shipment_field(frm, [status]),
			{ fieldname: "posting_date", label: __("Bank Debit Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
			{ fieldname: "exchange_rate", label: __("Bank Rate ({0} → {1})", [frm.doc.currency, frm.doc.company_currency]),
				fieldtype: "Float", precision: 6, reqd: 1, description: __("The rate on the bank's debit advice") },
			{ fieldname: "margin_applied", label: __("Margin Used"), fieldtype: "Currency",
				description: __("Margin held: {0}. Blank: this shipment's share", [format_currency(frm.doc.margin_balance, frm.doc.company_currency)]) },
			bank_field(frm),
			{ fieldname: "preview", fieldtype: "HTML" },
		],
		primary_action_label: __("Settle"),
		primary_action: (values) => {
			delete values.preview;
			lc_run(frm, "settle", values, d);
		},
	});
	const preview = () => {
		const v = d.get_values(true);
		if (!v.shipment_no || !v.exchange_rate) return;
		frappe.call({
			method: `${LC_API}.settlement_preview`,
			args: { name: frm.doc.name, shipment_no: v.shipment_no, exchange_rate: v.exchange_rate,
				margin_applied: v.margin_applied },
			callback: (r) => {
				const p = r.message, cur = frm.doc.company_currency;
				const diff = p.exchange_difference;
				d.fields_dict.preview.$wrapper.html(`<table class="table table-sm small" style="margin-top:8px">
					<tr><td>${__("Bank debit (incl. margin)")}</td><td class="text-right">${format_currency(p.bank_total, cur)}</td></tr>
					<tr><td>${__("From margin")}</td><td class="text-right">${format_currency(p.margin_applied, cur)}</td></tr>
					<tr><td>${__("From bank account")}</td><td class="text-right">${format_currency(p.bank_paid, cur)}</td></tr>
					<tr><td>${__("Supplier cleared at booked rate {0}", [p.booked_rate])}${p.invoice ? ` (${p.invoice})` : ` (${__("advance")})`}</td>
						<td class="text-right">${format_currency(p.supplier_company_amount, cur)}</td></tr>
					<tr><td><b>${diff >= 0 ? __("Exchange loss") : __("Exchange gain")}</b></td>
						<td class="text-right"><b>${format_currency(Math.abs(diff), cur)}</b></td></tr></table>`);
			},
		});
	};
	["shipment_no", "exchange_rate", "margin_applied"].forEach((f) => {
		d.fields_dict[f].df.onchange = preview;
	});
	d.show();
}

function lc_customs(frm) {
	lc_dialog(frm, __("Customs Proof to the Bank"), [
		shipment_field(frm, ["Settled"]),
		{ fieldname: "customs_declaration_no", label: __("Customs Declaration (Pragyapan) No."), fieldtype: "Data", reqd: 1 },
		{ fieldname: "customs_date", label: __("Customs Clearance Date"), fieldtype: "Date", reqd: 1 },
		{ fieldname: "submitted_on", label: __("Given to Bank On"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
	], "customs_proof", __("Save"));
}

function lc_close(frm) {
	lc_dialog(frm, __("Close LC"), [
		{ fieldname: "posting_date", label: __("Closing Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "info", fieldtype: "HTML", options: `<p class="small text-muted">${
			frm.doc.margin_balance > 0
				? __("Margin of {0} still held is released back to the bank account below.", [format_currency(frm.doc.margin_balance, frm.doc.company_currency)])
				: __("No margin is held.")}</p>` },
		bank_field(frm),
		{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Data" },
	], "close", __("Close LC"), (v) => { delete v.info; return v; });
}
