// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

// Which pending Sales Orders the customer's credit limits let through today.
// The figures are worked out in sales_order_billing_capacity.py.

const SOBC_VERDICT_COLOURS = { Ready: "green", Partly: "orange", Blocked: "red", "Qty Billed": "gray" };

frappe.query_reports["Sales Order Billing Capacity"] = {
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
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "verdict" && SOBC_VERDICT_COLOURS[data.verdict]) {
			return `<span class="indicator-pill ${SOBC_VERDICT_COLOURS[data.verdict]}">${value}</span>`;
		}
		if (["can_bill", "qty_can_bill"].includes(column.fieldname) && data[column.fieldname] > 0) {
			return `<span style="color: var(--green-600); font-weight: 600">${value}</span>`;
		}
		if (column.fieldname === "short_by" && data.short_by > 0) {
			return `<span style="color: var(--red-600)">${value}</span>`;
		}
		// Today's rate differs from the order's: the invoice will not bill at the order price.
		if (column.fieldname === "today_rate" && data.order_rate != null
			&& Math.abs(data.today_rate - data.order_rate) >= 0.01) {
			return `<span style="color: var(--orange-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
