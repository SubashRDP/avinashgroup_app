// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Materialized Return Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Select",
			options: [""],
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
			fieldname: "sync_status",
			label: __("Sync Status"),
			fieldtype: "Select",
			options: ["", "Pending", "Synced", "Failed"],
		},
	],

	onload(report) {
		frappe
			.call({
				method: "avinashgroup_app.avinash_group_app.report.materialized_return_report.materialized_return_report.get_fiscal_years",
			})
			.then((r) => {
				const filter = report.get_filter("fiscal_year");
				filter.df.options = [""].concat(r.message || []);
				filter.refresh();
			});
	},
};
