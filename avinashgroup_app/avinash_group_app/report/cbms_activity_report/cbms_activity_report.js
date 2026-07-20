// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["CBMS Activity Report"] = {
	onload(report) {
		// The From/To date window is sourced from the backend (server clock),
		// not computed in the browser — see get_default_dates() in
		// cbms_activity_report.py.
		frappe
			.call(
				"avinashgroup_app.avinash_group_app.report.cbms_activity_report.cbms_activity_report.get_default_dates"
			)
			.then((r) => {
				if (r.message) report.set_filter_value(r.message);
			});
	},
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
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "sales_invoice",
			label: __("Sales Invoice"),
			fieldtype: "Link",
			options: "Sales Invoice",
		},
		{
			fieldname: "operation",
			label: __("Operation"),
			fieldtype: "Select",
			options: ["", "Queued", "Synced", "Failed", "Held"],
		},
	],
};
