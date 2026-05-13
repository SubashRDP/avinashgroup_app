// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Purchase Register Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			get_data: function(txt) {
				return frappe.db.get_link_options("Company", txt);
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
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
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "MultiSelectList",
			get_data: function(txt) {
				return frappe.db.get_link_options("Supplier", txt);
			},
		},
		{
			fieldname: "purchase_type",
			label: __("Purchase Type"),
			fieldtype: "MultiSelectList",
			get_data: function(txt) {
				return frappe.db.get_link_options("Purchase Type", txt);
			},
		},
	],

	get_datatable_options(options) {
		return Object.assign(options, { serialNoColumn: false, freezeColumnsTo: 4 });
	},

	formatter: function (value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);

		if (column.fieldname === "voucher_no" && value && !data.bold) {
			value = `<a href="/app/purchase-invoice/${value}" target="_blank">${value}</a>`;
			return value;
		}

		value = default_formatter(value, row, column, data);
		if (data.bold) {
			value = `<strong>${value}</strong>`;
		}
		return value;
	},
};
