// Sales Invoice > Get Items From > Sales Order — picker with useful columns.
//
// Stock ERPNext lists only the order ID and customer link, so open orders of
// one customer look alike. This replaces the button's handler (frm.cscript.
// sales_order_btn, which ERPNext's refresh calls) with the same picker plus
// these columns: Miti · Sales Order ID · Customer Name · Qty · Amount.
//
// Rows come from avinashgroup_app...sales_order_picker.search_open_sales_orders,
// which computes Miti and applies the exact filters ERPNext sends. Selecting,
// "Select Sales Order Item" and mapping onto the invoice are all stock.
//
// Loaded from app_include_js (like sales_invoice.js), not doctype_js.

(function () {
	const QUERY = "avinashgroup_app.custom_code.SalesInvoice.sales_order_picker.search_open_sales_orders";

	// fieldname → [label, right-aligned?, column width (flex-grow), formatter]
	// The ID gets the widest share so "NGK-SO-83/84-00001" is never cut off.
	const COLUMNS = [
		["miti", __("Sales Order Miti"), false, 1, (v) => v || ""],
		["name", __("Sales Order ID"), false, 1.5, null],
		["customer_name", __("Customer Name"), false, 1.5, (v) => v || ""],
		["total_qty", __("Qty"), true, 0.6, (v) => format_number(v || 0, null, 2)],
		["grand_total", __("Amount"), true, 1, (v, r) => format_currency(v || 0, r.currency)],
	];

	// Same row markup as MultiSelectDialog.make_list_row, with our own labels
	// and formatting instead of unscrubbed fieldnames and raw values.
	function make_list_row(result = {}) {
		const head = Object.keys(result).length === 0;
		const cells = COLUMNS.map(([field, label, right, grow, fmt]) => {
			// list-item__content is a flex box, so alignment is justify-content.
			const style = ` style="flex: ${grow} 1 0; min-width: 0;${right ? " justify-content: flex-end;" : ""}"`;
			let inner;
			if (head) {
				inner = `<span class="ellipsis text-muted" title="${label}">${label}</span>`;
			} else if (field === "name") {
				const name = frappe.utils.escape_html(result.name || "");
				inner = `<a href="/app/sales-order/${encodeURIComponent(result.name || "")}"
					class="list-id ellipsis" title="${name}">${name}</a>`;
			} else {
				const text = frappe.utils.escape_html(String(fmt(result[field], result)));
				inner = `<span class="ellipsis result-row" title="${text}">${text}</span>`;
			}
			return `<div class="list-item__content ellipsis"${style}>${inner}</div>`;
		}).join("");

		let $row = $(`<div class="list-item">
			<div class="list-item__content" style="flex: 0 0 10px;">
				<input type="checkbox" class="list-row-check" data-item-name="${result.name || ""}"
					${result.checked ? "checked" : ""}>
			</div>
			${cells}
		</div>`);

		return head
			? $row.addClass("list-item--head")
			: $(`<div class="list-item-container" data-item-name="${result.name}"></div>`).append($row);
	}

	function sales_order_btn() {
		const frm = this.frm;
		this.$sales_order_btn = frm.add_custom_button(
			__("Sales Order"),
			function () {
				// Options are ERPNext's own sales_order_btn, plus our query.
				const picker = erpnext.utils.map_current_doc({
					method: "erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice",
					source_doctype: "Sales Order",
					target: frm,
					setters: {
						customer: frm.doc.customer || undefined,
					},
					get_query_filters: {
						docstatus: 1,
						status: ["not in", ["Closed", "On Hold"]],
						per_billed: ["<", 99.99],
						company: frm.doc.company,
					},
					get_query_method: QUERY,
					allow_child_item_selection: true,
					child_fieldname: "items",
					child_columns: ["item_code", "item_name", "qty", "amount", "billed_amt"],
					size: "large",
				});
				if (!picker) return;

				// The dialog already drew its header and ran its first search
				// with the stock columns; swap the renderer and draw again.
				picker.make_list_row = make_list_row;
				picker.$results.find(".list-item--head").replaceWith(make_list_row());
				picker.get_results();
			},
			__("Get Items From")
		);
	}

	frappe.ui.form.on("Sales Invoice", {
		// Form handlers run before the controller's refresh, which is what calls
		// sales_order_btn — so the swap is in place by the time it is used.
		refresh(frm) {
			if (frm.cscript && frm.cscript.sales_order_btn !== sales_order_btn) {
				frm.cscript.sales_order_btn = sales_order_btn;
			}
		},
	});
})();
