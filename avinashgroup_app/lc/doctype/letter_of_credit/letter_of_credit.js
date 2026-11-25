// Letter of Credit: the draft is filled like any form; once submitted, every
// money step is a button that opens a dialog and calls lc/lifecycle.py
// run_action. The shipment dates and goods rows stay editable (Update).

const LC_API = "avinashgroup_app.lc.lifecycle";

frappe.ui.form.on("Letter of Credit", {
	setup(frm) {
		frm.set_query("bank_account", () => ({
			filters: { company: frm.doc.company, is_company_account: 1 },
		}));
		frm.set_query("set_warehouse", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("warehouse", "items", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("cost_type", "costs", () => ({ filters: { disabled: 0 } }));
		frm.set_query("paid_from", "costs", () => ({
			filters: { company: frm.doc.company, account_type: ["in", ["Bank", "Cash"]], is_group: 0 },
		}));
		frm.set_query("item_code", "items", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			const filters = { disabled: 0 };
			if (row.item_group) filters.item_group = row.item_group;
			filters[row.transfer_to === "Fixed Asset" ? "is_fixed_asset" : "is_stock_item"] = 1;
			return { filters };
		});
	},

	refresh(frm) {
		lc_summary_headline(frm);
		lc_lock_posted_costs(frm);
		if (frm.doc.docstatus !== 1) return;
		const status = frm.doc.status;
		if (["Closed", "Cancelled"].includes(status)) {
			lc_view_buttons(frm);
			return;
		}
		const goods = __("Goods");

		frm.add_custom_button(__("Deposit Margin"), () => lc_margin(frm), __("LC"));

		if (frm.doc.drafts_at === "Usance") {
			if (frm.doc.goods_pending_fc > 0) {
				frm.add_custom_button(__("Accept Bill"), () => lc_accept(frm), goods);
			}
			if (open_bills(frm).length) {
				frm.add_custom_button(__("Pay at Maturity"), () => lc_pay_maturity(frm), goods);
			}
		} else if (frm.doc.goods_pending_fc > 0) {
			frm.add_custom_button(__("Pay Goods"), () => lc_pay_goods(frm), goods);
		}
		if (!frm.doc.transferred_on) {
			frm.add_custom_button(__("Transfer to Stock / Asset"), () => lc_transfer(frm), goods);
		}
		if (frm.doc.transferred_on || !(frm.doc.items || []).length) {
			frm.add_custom_button(__("Close LC"), () => lc_close(frm), __("LC"));
		}
		if ((frm.doc.events || []).length > 1) {
			frm.add_custom_button(__("Undo Last Step"), () => {
				const last = frm.doc.events[frm.doc.events.length - 1];
				frappe.confirm(
					__("Undo {0}? Its Journal Entry (and any Stock Entry or draft Asset it made) is cancelled.", [
						`<b>${frappe.utils.escape_html(last.event)}</b>`,
					]),
					() => frappe.call({ method: `${LC_API}.undo`, args: { name: frm.doc.name }, freeze: true })
						.then(() => frm.reload_doc())
				);
			}, __("LC"));
		}
		lc_view_buttons(frm);
	},

	company(frm) {
		frm.set_value("bank_account", null);
		frm.set_value("set_warehouse", null);
	},
	drafts_at(frm) {
		if (frm.doc.drafts_at === "Sight") frm.set_value("usance_days", 0);
	},
	exchange_rate: (frm) => lc_totals(frm),
	lc_amount: (frm) => lc_totals(frm),
	margin_percent: (frm) => lc_totals(frm),
});

frappe.ui.form.on("LC Item", {
	qty: (frm, cdt, cdn) => lc_row_amount(frm, cdt, cdn),
	rate: (frm, cdt, cdn) => lc_row_amount(frm, cdt, cdn),
	items_remove: (frm) => lc_totals(frm),
	items_add(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		row.transfer_to = row.transfer_to || "Stock";
		if (frm.doc.set_warehouse) row.warehouse = frm.doc.set_warehouse;
	},
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;
		frappe.db.get_value("Item", row.item_code, ["item_name", "item_group", "stock_uom", "description", "asset_category"])
			.then(({ message: item }) => {
				if (!item) return;
				frappe.model.set_value(cdt, cdn, {
					item_group: row.item_group || item.item_group,
					uom: row.uom || item.stock_uom,
					description: row.description || item.item_name,
					asset_category: row.asset_category || item.asset_category,
				});
			});
	},
});

frappe.ui.form.on("LC Cost", {
	costs_add(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, {
			posting_date: frappe.datetime.get_today(), paid_via: "Bank", paid_from: frm.doc.bank_gl_account,
		});
	},
	cost_type(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.cost_type) return;
		frappe.db.get_value("LC Cost Type", row.cost_type, ["cost_group", "default_paid_via"]).then(({ message: t }) => {
			if (!t) return;
			const values = { cost_group: t.cost_group };
			if (t.default_paid_via && !row.journal_entry) values.paid_via = t.default_paid_via;
			frappe.model.set_value(cdt, cdn, values);
		});
	},
	paid_via(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.paid_via === "Bank" && !row.paid_from) frappe.model.set_value(cdt, cdn, "paid_from", frm.doc.bank_gl_account);
		if (row.paid_via === "Party") frappe.model.set_value(cdt, cdn, "paid_from", null);
	},
	form_render(frm, cdt, cdn) {
		lc_lock_posted_costs(frm);
	},
});

// A posted cost (it has its Journal Entry) or a goods row is history: only its
// bill no. and remarks may change. Delete the row to reverse a posted cost.
const LC_COST_INPUTS = ["posting_date", "cost_type", "amount", "vat_amount", "paid_via", "paid_from", "party"];
function lc_lock_posted_costs(frm) {
	const grid = frm.fields_dict.costs && frm.fields_dict.costs.grid;
	if (!grid) return;
	(frm.doc.costs || []).forEach((row) => {
		const grid_row = grid.grid_rows_by_docname[row.name];
		if (!grid_row) return;
		const locked = !!row.journal_entry || row.cost_group === "Goods";
		LC_COST_INPUTS.forEach((f) => grid_row.toggle_editable(f, !locked));
	});
}

function lc_row_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
	lc_totals(frm);
}

function lc_totals(frm) {
	if (frm.doc.docstatus !== 0) return;
	let total = 0, qty = 0;
	(frm.doc.items || []).forEach((r) => { total += flt(r.qty) * flt(r.rate); qty += flt(r.qty); });
	frm.set_value("items_total", total);
	frm.set_value("total_qty", qty);
	if (total && !frm.doc.lc_amount) frm.set_value("lc_amount", total);
	const base = flt(frm.doc.lc_amount) * flt(frm.doc.exchange_rate);
	frm.set_value("base_lc_amount", base);
	frm.set_value("required_margin", base * flt(frm.doc.margin_percent) / 100);
}

function lc_summary_headline(frm) {
	if (frm.doc.docstatus !== 1) return;
	const cur = frm.doc.company_currency;
	const parts = [
		`${__("Landed cost so far")}: <b>${format_currency(frm.doc.total_cost, cur)}</b>`,
	];
	if (frm.doc.goods_pending_fc > 0) {
		parts.push(`${__("Goods still to pay")}: <b>${format_currency(frm.doc.goods_pending_fc, frm.doc.currency)}</b>`);
	}
	if (frm.doc.margin_balance > 0) {
		parts.push(`${__("Margin held")}: ${format_currency(frm.doc.margin_balance, cur)}`);
	}
	frm.dashboard.set_headline(parts.join(" &nbsp;·&nbsp; "), frm.doc.transferred_on ? "green" : "blue");
}

function lc_view_buttons(frm) {
	frm.add_custom_button(__("Cost Sheet"), () =>
		frappe.set_route("query-report", "LC Cost Sheet", { letter_of_credit: frm.doc.name }), __("View"));
	frm.add_custom_button(__("Journal Entries"), () =>
		frappe.set_route("List", "Journal Entry", { letter_of_credit: frm.doc.name }), __("View"));
}

function open_bills(frm) {
	return (frm.doc.costs || []).filter((c) => c.paid_via === "Acceptance" && !c.paid_on);
}

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

const bank_field = (frm, extra) => Object.assign({
	fieldname: "bank_account", label: __("Paid From (Bank / Cash Ledger)"), fieldtype: "Link", options: "Account",
	default: frm.doc.bank_gl_account,
	get_query: () => ({ filters: { company: frm.doc.company, account_type: ["in", ["Bank", "Cash"]], is_group: 0 } }),
}, extra || {});

const date_field = (label) => ({
	fieldname: "posting_date", label: label || __("Date"), fieldtype: "Date", reqd: 1,
	default: frappe.datetime.get_today(),
});

function lc_dialog(frm, title, fields, action, primary, prepare) {
	const d = new frappe.ui.Dialog({
		title, fields,
		primary_action_label: primary || __("Save"),
		primary_action: (values) => lc_run(frm, action, prepare ? prepare(values) : values, d),
	});
	d.show();
	return d;
}

function lc_margin(frm) {
	lc_dialog(frm, __("Deposit Margin"), [
		date_field(),
		{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1 },
		bank_field(frm),
	], "deposit_margin", __("Deposit"));
}

function lc_pay_goods(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Pay Goods (Bank Debit)"),
		fields: [
			date_field(__("Bank Debit Date")),
			{ fieldname: "fc_amount", label: __("Amount ({0})", [frm.doc.currency]), fieldtype: "Float", precision: 2,
				reqd: 1, default: frm.doc.goods_pending_fc,
				description: __("Still to pay: {0}", [format_currency(frm.doc.goods_pending_fc, frm.doc.currency)]) },
			{ fieldname: "exchange_rate", label: __("Bank Rate ({0} → {1})", [frm.doc.currency, frm.doc.company_currency]),
				fieldtype: "Float", precision: 6, reqd: 1, description: __("The rate on the bank's debit advice") },
			{ fieldname: "margin_used", label: __("Margin Used"), fieldtype: "Currency",
				description: __("Margin held: {0}", [format_currency(frm.doc.margin_balance, frm.doc.company_currency)]) },
			bank_field(frm),
			{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Data" },
			{ fieldname: "preview", fieldtype: "HTML" },
		],
		primary_action_label: __("Book Payment"),
		primary_action: (values) => { delete values.preview; lc_run(frm, "pay_goods", values, d); },
	});
	const suggest = () => {
		const fc = d.get_value("fc_amount");
		if (!fc) return;
		frappe.xcall(`${LC_API}.margin_suggestion`, { name: frm.doc.name, fc_amount: fc })
			.then((m) => d.set_value("margin_used", m));
	};
	const preview = () => {
		const v = d.get_values(true);
		const total = flt(v.fc_amount) * flt(v.exchange_rate);
		if (!total) return;
		const cur = frm.doc.company_currency;
		d.fields_dict.preview.$wrapper.html(`<table class="table table-sm small" style="margin-top:8px">
			<tr><td>${__("Goods in Transit (cost)")}</td><td class="text-right">${format_currency(total, cur)}</td></tr>
			<tr><td>${__("From margin")}</td><td class="text-right">${format_currency(v.margin_used, cur)}</td></tr>
			<tr><td>${__("From bank account")}</td><td class="text-right">${format_currency(total - flt(v.margin_used), cur)}</td></tr>
		</table>`);
	};
	d.fields_dict.fc_amount.df.onchange = () => { suggest(); preview(); };
	d.fields_dict.exchange_rate.df.onchange = preview;
	d.fields_dict.margin_used.df.onchange = preview;
	d.show();
	suggest();
}

function lc_accept(frm) {
	lc_dialog(frm, __("Accept Bill (Usance)"), [
		date_field(__("Accepted On")),
		{ fieldname: "fc_amount", label: __("Bill Amount ({0})", [frm.doc.currency]), fieldtype: "Float", precision: 2,
			reqd: 1, default: frm.doc.goods_pending_fc },
		{ fieldname: "exchange_rate", label: __("Rate on Acceptance ({0} → {1})", [frm.doc.currency, frm.doc.company_currency]),
			fieldtype: "Float", precision: 6, reqd: 1, default: frm.doc.exchange_rate,
			description: __("The goods are valued at this rate; the difference at maturity goes to exchange gain / loss") },
		{ fieldname: "maturity_date", label: __("Maturity Date"), fieldtype: "Date", reqd: 1, default: frm.doc.maturity_date },
		{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Data" },
	], "accept_bill", __("Accept"));
}

function lc_pay_maturity(frm) {
	const bills = open_bills(frm);
	const d = new frappe.ui.Dialog({
		title: __("Pay Bill at Maturity"),
		fields: [
			{ fieldname: "cost_row", label: __("Bill"), fieldtype: "Select", reqd: 1,
				options: bills.map((b) => ({
					value: b.name,
					label: `${format_currency(b.fc_amount, frm.doc.currency)} · ${__("matures")} ${frappe.datetime.str_to_user(b.maturity_date)}`,
				})),
				default: bills.length ? bills[0].name : null },
			date_field(__("Bank Debit Date")),
			{ fieldname: "exchange_rate", label: __("Bank Rate ({0} → {1})", [frm.doc.currency, frm.doc.company_currency]),
				fieldtype: "Float", precision: 6, reqd: 1 },
			{ fieldname: "margin_used", label: __("Margin Used"), fieldtype: "Currency",
				description: __("Margin held: {0}. Blank: this bill's share", [format_currency(frm.doc.margin_balance, frm.doc.company_currency)]) },
			bank_field(frm),
			{ fieldname: "preview", fieldtype: "HTML" },
		],
		primary_action_label: __("Pay"),
		primary_action: (values) => { delete values.preview; lc_run(frm, "pay_maturity", values, d); },
	});
	const preview = () => {
		const v = d.get_values(true);
		if (!v.cost_row || !v.exchange_rate) return;
		frappe.xcall(`${LC_API}.maturity_preview`, {
			name: frm.doc.name, cost_row: v.cost_row, exchange_rate: v.exchange_rate, margin_used: v.margin_used,
		}).then((p) => {
			const cur = frm.doc.company_currency, diff = p.exchange_difference;
			d.fields_dict.preview.$wrapper.html(`<table class="table table-sm small" style="margin-top:8px">
				<tr><td>${__("Bank debit")}</td><td class="text-right">${format_currency(p.bank_total, cur)}</td></tr>
				<tr><td>${__("From margin")}</td><td class="text-right">${format_currency(p.margin_used, cur)}</td></tr>
				<tr><td>${__("Supplier cleared at acceptance rate {0}", [p.booked_rate])}</td><td class="text-right">${format_currency(p.booked, cur)}</td></tr>
				<tr><td><b>${diff >= 0 ? __("Exchange loss") : __("Exchange gain")}</b></td>
					<td class="text-right"><b>${format_currency(Math.abs(diff), cur)}</b></td></tr></table>`);
		});
	};
	["cost_row", "exchange_rate", "margin_used"].forEach((f) => { d.fields_dict[f].df.onchange = preview; });
	d.show();
}

function lc_transfer(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the form first."));
		return;
	}
	frappe.xcall("avinashgroup_app.lc.transfer.transfer_preview", { name: frm.doc.name }).then((p) => {
		const cur = frm.doc.company_currency;
		const esc = frappe.utils.escape_html;
		const rows = p.rows.map((r) => `<tr>
			<td>${r.idx}</td><td>${esc(r.item_code || "")}<div class="text-muted">${esc(r.description || "")}</div></td>
			<td class="text-right">${format_number(r.qty)} ${esc(r.uom || "")}</td>
			<td>${__(r.transfer_to)}<div class="text-muted">${esc(r.target || "")}</div></td>
			<td class="text-right">${format_currency(r.allocated_cost, cur)}</td>
			<td class="text-right">${format_currency(r.landed_rate, cur)}</td></tr>`).join("");
		const notes = [
			...p.problems.map((m) => `<div class="text-danger">• ${m}</div>`),
			...p.warnings.map((m) => `<div class="text-warning">• ${m}</div>`),
		].join("");
		const d = new frappe.ui.Dialog({
			title: __("Transfer to Stock / Fixed Asset"),
			size: "large",
			fields: [
				date_field(__("Transfer Date")),
				{ fieldname: "info", fieldtype: "HTML", options: `
					<p>${__("Landed cost in transit")}: <b>${format_currency(p.balance, cur)}</b>,
					${__("shared by")} ${__(frm.doc.allocate_by === "Quantity" ? "quantity" : "value")}.</p>
					<table class="table table-sm small"><tr><th>#</th><th>${__("Item")}</th><th class="text-right">${__("Qty")}</th>
					<th>${__("To")}</th><th class="text-right">${__("Landed Cost")}</th><th class="text-right">${__("Per Unit")}</th></tr>${rows}</table>
					${notes}
					<p class="small text-muted">${__("Stock rows become one Material Receipt. Fixed-asset rows post one Journal Entry to the asset account and a draft Asset each, for you to complete and submit.")}</p>` },
			],
			primary_action_label: __("Transfer"),
			primary_action: (values) => lc_run(frm, "transfer", { posting_date: values.posting_date }, d),
		});
		if (p.problems.length) d.get_primary_btn().prop("disabled", true);
		d.set_value("posting_date", frm.doc.arrival_date || frappe.datetime.get_today());
		d.show();
	});
}

function lc_close(frm) {
	lc_dialog(frm, __("Close LC"), [
		date_field(__("Closing Date")),
		{ fieldname: "info", fieldtype: "HTML", options: `<p class="small text-muted">${
			frm.doc.margin_balance > 0
				? __("Margin of {0} still held is released back to the bank account below.", [format_currency(frm.doc.margin_balance, frm.doc.company_currency)])
				: __("No margin is held.")}</p>` },
		bank_field(frm, { label: __("Margin Back To (Bank Ledger)") }),
		{ fieldname: "residual_account", label: __("Clear Anything Left in Transit To"), fieldtype: "Link", options: "Account",
			get_query: () => ({ filters: { company: frm.doc.company, is_group: 0 } }),
			description: __("Only needed when a cost was booked after the transfer (or a few paisa of rounding)") },
		{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Data" },
	], "close", __("Close LC"), (v) => { delete v.info; return v; });
}
