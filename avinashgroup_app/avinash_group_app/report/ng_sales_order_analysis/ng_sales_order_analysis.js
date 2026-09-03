// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

// [name, year_start_date, year_end_date] of the fiscal year covering today;
// guarded so a site with no running Fiscal Year doesn't error on report open.
var ngsoa_fy = erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), false, true)
	? erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)
	: [];

var NGSOA_METHOD = "avinashgroup_app.avinash_group_app.report.ng_sales_order_analysis.ng_sales_order_analysis";

frappe.query_reports["NG Sales Order Analysis"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			reqd: 1,
			get_data: function (txt) {
				return frappe.db.get_link_options("Company", txt);
			},
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: ngsoa_fy[0],
			// Picking a year fills the dates; they stay editable, so a shorter
			// range inside the year is still possible.
			on_change: function (query_report) {
				const fiscal_year = query_report.get_filter_value("fiscal_year");
				if (!fiscal_year) return;
				frappe.model.with_doc("Fiscal Year", fiscal_year, function () {
					const fy_doc = frappe.model.get_doc("Fiscal Year", fiscal_year);
					query_report.set_filter_value({
						from_date: fy_doc.year_start_date,
						to_date: fy_doc.year_end_date,
					});
				});
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: ngsoa_fy[1] || frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: ngsoa_fy[2] || frappe.datetime.now_date(),
			reqd: 1,
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.call({
					method: NGSOA_METHOD + ".get_company_customers",
					args: {
						company: frappe.query_report.get_filter_value("company"),
						txt: txt,
					},
				}).then((r) => r.message || []);
			},
		},
		{
			fieldname: "sales_order",
			label: __("Sales Order"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.call({
					method: NGSOA_METHOD + ".get_company_sales_orders",
					args: {
						company: frappe.query_report.get_filter_value("company"),
						customer: frappe.query_report.get_filter_value("customer"),
						from_date: frappe.query_report.get_filter_value("from_date"),
						to_date: frappe.query_report.get_filter_value("to_date"),
						txt: txt,
					},
				}).then((r) => r.message || []);
			},
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "MultiSelectList",
			// Sales Order.billing_status verbatim — a fixed list, not company-wise.
			get_data: function () {
				return ["Not Billed", "Partly Billed", "Fully Billed", "Closed"].map((s) => ({
					value: s,
					label: __(s),
					description: "",
				}));
			},
		},
	],
};
