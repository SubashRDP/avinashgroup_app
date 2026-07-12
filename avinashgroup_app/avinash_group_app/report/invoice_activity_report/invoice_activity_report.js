// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Invoice Activity Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
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
			fieldname: "operation",
			label: __("Operation"),
			fieldtype: "Select",
			options: "All\nAdd\nPrinted\nModified\nDeleted",
			default: "All",
		},
		{
			fieldname: "sales_invoice",
			label: __("Sales Invoice"),
			fieldtype: "Link",
			options: "Sales Invoice",
		},
	],
};
