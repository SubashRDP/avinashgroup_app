// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

// Which pending Sales Orders the customer's credit limits let through today.
// The figures are worked out in sales_order_billing_capacity.py.
//
// Laid out as a tree: a bold row per customer (their credit position and their
// orders added up) with that customer's orders under it.
//
// Each order row has Make Invoice: a new Sales Invoice filled from the order,
// the same path as the pending-orders drawer (avinash.make_invoice_from_order,
// public/js/sales_invoice_pending_orders.js). On a Blocked order it is a plain
// button rather than the blue one — the save will still refuse it until the
// customer pays, but the clerk may know they just have.

// Verdict pills. Each carries a symbol as well as a colour, so the verdict
// never rests on colour alone.
const SOBC_VERDICTS = {
	Ready: { colour: "green", symbol: "✓" },
	Partly: { colour: "orange", symbol: "◐" },
	Blocked: { colour: "red", symbol: "✕" },
	"Qty Billed": { colour: "gray", symbol: "–" },
};

// Credit Used bar: status colours (good / warning / critical) by how much of
// the amount limit is used. The % is always written beside the bar.
const SOBC_METER_WARN_PCT = 75;
const SOBC_METER = { good: "#0ca30c", warning: "#fab219", critical: "#d03b3b" };

const SOBC_QTY_FIELDS = ["order_qty", "billed_qty", "pending_qty", "qty_can_bill", "last_invoice_qty"];

frappe.query_reports["Sales Order Billing Capacity"] = {
	tree: true,
	name_field: "label",
	// Customer rows open, so every order shows; Collapse All folds them.
	initial_depth: 1,

	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			get_data: (txt) => frappe.db.get_link_options("Company", txt),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "MultiSelectList",
			// Same company-scoped customer list as NG Sales Order Analysis.
			get_data: (txt) =>
				frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.ng_sales_order_analysis.ng_sales_order_analysis.get_company_customers",
						args: { company: frappe.query_report.get_filter_value("company"), txt },
					})
					.then((r) => r.message || []),
		},
		{
			fieldname: "verdict",
			label: __("Verdict"),
			fieldtype: "Select",
			options: ["", "Ready", "Partly", "Blocked", "Qty Billed"],
		},
		{ fieldname: "from_date", label: __("Order From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("Order To"), fieldtype: "Date" },
	],

	formatter(value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);
		const is_customer = !data.indent;

		if (column.fieldname === "credit_meter") {
			return is_customer ? sobc_meter(data._meter) : "";
		}
		if (column.fieldname === "label") {
			return sobc_label(data, is_customer);
		}
		if (column.fieldname === "action") {
			return is_customer ? "" : sobc_invoice_button(data);
		}
		// A rate belongs to one order line; a customer row adds up several.
		if (is_customer && ["today_rate", "order_rate"].includes(column.fieldname)) {
			return "";
		}

		if (SOBC_QTY_FIELDS.includes(column.fieldname) && value != null && Number.isInteger(value)) {
			// 10, not 10.000 — cylinders are counted whole; a part qty keeps its decimals.
			value = format_number(value, null, 0);
			column = Object.assign({}, column, { fieldtype: "Data" });
		}
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "verdict" && SOBC_VERDICTS[data.verdict]) {
			const v = SOBC_VERDICTS[data.verdict];
			return `<span class="indicator-pill no-indicator-dot ${v.colour}" style="font-weight:600">${v.symbol} ${__(data.verdict)}</span>`;
		}
		if (["can_bill", "qty_can_bill"].includes(column.fieldname) && data[column.fieldname] > 0) {
			return `<span style="color: var(--green-600); font-weight: 600">${value}</span>`;
		}
		if (column.fieldname === "short_by") {
			return data.short_by > 0
				? `<span style="color: var(--red-600); font-weight: 600">${value}</span>`
				: `<div class="text-muted" style="text-align:right">–</div>`;
		}
		// Today's rate differs from the order's: the invoice will not bill at the order price.
		if (
			column.fieldname === "today_rate" &&
			data.order_rate != null &&
			Math.abs(data.today_rate - data.order_rate) >= 0.01
		) {
			const arrow = data.today_rate > data.order_rate ? "▲" : "▼";
			const tip = __("Order rate {0}", [format_currency(data.order_rate)]);
			return `<div title="${tip}" style="text-align:right;white-space:nowrap;color:var(--orange-600);font-weight:600">${arrow} ${format_currency(data.today_rate)}</div>`;
		}
		if (column.fieldname === "reason" && !is_customer && data.verdict === "Ready") {
			return `<span class="text-muted">${value}</span>`;
		}
		return value;
	},
};

function sobc_invoice_button(data) {
	if (!data.sales_order || data.verdict === "Qty Billed") return "";
	const style = data.verdict === "Blocked" ? "btn-default" : "btn-primary";
	return `<button class="btn btn-xs ${style} sobc-make-invoice"
		data-order="${frappe.utils.escape_html(data.sales_order)}"
		data-company="${frappe.utils.escape_html(data.sales_order_company || "")}">${__("Make Invoice")}</button>`;
}

// One delegated handler for every row. Namespaced and unbound first: the
// report script can be evaluated again in the same session, and a second
// handler would open two invoices per click. Block body, so it never returns
// false to jQuery (which would cancel the click for everything else).
$(document).off("click.sobc").on("click.sobc", ".sobc-make-invoice", function (e) {
	e.stopPropagation();
	const order = { name: this.dataset.order, company: this.dataset.company };
	if (window.avinash && avinash.make_invoice_from_order) {
		avinash.make_invoice_from_order(order);
	} else {
		frappe.model.open_mapped_doc({
			method: "erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice",
			source_name: order.name,
		});
	}
});

// Customer name links to the Customer, an order number to the Sales Order.
function sobc_label(data, is_customer) {
	const text = frappe.utils.escape_html(data.label || "");
	const href = is_customer
		? frappe.utils.get_form_link("Customer", data.customer)
		: frappe.utils.get_form_link("Sales Order", data.sales_order);
	const style = is_customer ? "font-weight:700" : "";
	return `<a href="${href}" style="${style}" title="${text}">${text}</a>`;
}

function sobc_meter(meter) {
	if (!meter) return "";
	if (meter.kind === "none") {
		return `<span class="text-muted">${__("No amount limit")}</span>`;
	}
	if (meter.kind === "advance") {
		const left =
			meter.leftover > 0
				? __("{0} advance left", [format_currency(meter.leftover)])
				: __("no advance left");
		return `<span class="text-muted">${__("Advance only")} · </span><span>${left}</span>`;
	}

	// Solid: used today. Paler, after it: what the orders that fit would add.
	const pct = meter.used_pct || 0;
	const after = Math.max(meter.after_pct || 0, pct);
	const status = pct >= 100 ? "critical" : pct >= SOBC_METER_WARN_PCT ? "warning" : "good";
	const after_status = after >= 100 ? "critical" : after >= SOBC_METER_WARN_PCT ? "warning" : "good";
	const now_w = Math.min(pct, 100);
	const add_w = Math.max(Math.min(after, 100) - now_w, 0);
	const label =
		after > pct
			? `${Math.round(pct)}% → ${Math.round(after)}%`
			: pct >= 100
			? __("{0}% · over", [Math.round(pct)])
			: __("{0}% used", [Math.round(pct)]);
	const room = meter.leftover > 0
		? __("limit {0} + advance {1}", [format_currency(meter.limit), format_currency(meter.leftover)])
		: __("limit {0}", [format_currency(meter.limit)]);
	const tip = __("{0}% of the room to bill ({1}) used today; {2}% after billing the orders that fit", [
		Math.round(pct),
		room,
		Math.round(after),
	]);
	return `<div title="${tip}" style="display:flex;align-items:center;gap:8px;height:100%">
		<div style="flex:1;min-width:50px;height:6px;border-radius:4px;background:var(--gray-200);overflow:hidden;display:flex">
			<div style="width:${now_w}%;height:100%;background:${SOBC_METER[status]}"></div>
			<div style="width:${add_w}%;height:100%;background:${SOBC_METER[after_status]};opacity:.45"></div>
		</div>
		<span style="font-size:var(--text-xs);white-space:nowrap;font-weight:600">${label}</span>
	</div>`;
}
