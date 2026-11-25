// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt
// Columns and formulas: docs/inventory-report-standard.md

const INVENTORY_STATUS_COLORS = {
	"Negative Stock": "red",
	"Out of Stock": "red",
	"Dead Stock": "orange",
	Reorder: "orange",
	Overstock: "blue",
	OK: "green",
};

frappe.query_reports["Inventory Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			reqd: 1,
			get_data: (txt) => frappe.db.get_link_options("Company", txt),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.now_date(), -29),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			reqd: 1,
		},
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: ["Item", "Warehouse"],
			default: "Item",
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const companies = frappe.query_report.get_filter_value("company") || [];
				if (!companies.length) return [];
				return frappe
					.call({
						method:
							"avinashgroup_app.avinash_group_app.report.material_in_out_report.material_in_out_report.get_company_items",
						args: { company: companies, txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const companies = frappe.query_report.get_filter_value("company") || [];
				const filters = { is_group: 0 };
				if (companies.length) filters.company = ["in", companies];
				return frappe.db.get_link_options("Warehouse", txt, filters);
			},
		},
		{
			fieldname: "forecast_days",
			label: __("Forecast Days"),
			fieldtype: "Int",
			default: 30,
		},
		{
			fieldname: "slow_days",
			label: __("Non-moving After (Days)"),
			fieldtype: "Int",
			default: 90,
		},
		{
			fieldname: "show_zero",
			label: __("Show Zero Rows"),
			fieldtype: "Check",
			default: 0,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "status" && data.status) {
			const color = INVENTORY_STATUS_COLORS[data.status] || "gray";
			value = `<span class="indicator-pill ${color}">${value}</span>`;
		}
		if (column.fieldname === "closing_qty" && data.closing_qty < 0) {
			value = `<span style="color: var(--red-500)">${value}</span>`;
		}
		if (data.bold) value = `<strong>${value}</strong>`;
		return value;
	},
};
