// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Loan Summary"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Company", txt);
			},
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			reqd: 1,
		},
		{
			fieldname: "show_details",
			label: __("Show Details"),
			fieldtype: "Check",
			default: 0,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
	],

	get_datatable_options(options) {
		return Object.assign(options, { serialNoColumn: false, layout: "fixed" });
	},

	// Bold the subtotal / total / ratio rows, and indent the per-account detail
	// rows (shown when "Show Details" is ticked) under their loan type.
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data._bold) {
			value = `<b>${value}</b>`;
		}
		if (data && data._detail && column.fieldname === "loan_type") {
			value = `<span style="padding-left:18px;color:#6b7280;">${value}</span>`;
		}
		return value;
	},
};
