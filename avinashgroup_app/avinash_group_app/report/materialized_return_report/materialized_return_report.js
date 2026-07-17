// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

(() => {
	const today = frappe.datetime.get_today();
	// [name, year_start_date, year_end_date] of the fiscal year covering today;
	// guarded so a site with no running Fiscal Year doesn't error on report open.
	const fy = erpnext.utils.get_fiscal_year(today, false, true)
		? erpnext.utils.get_fiscal_year(today, true)
		: [];

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
				fieldtype: "Link",
				options: "Fiscal Year",
				default: fy[0],
				on_change: function (query_report) {
					const fiscal_year = query_report.get_filter_value("fiscal_year");
					if (!fiscal_year) {
						// FY is a server-side condition here; a custom on_change
						// suppresses the auto-refresh, so refresh on clear too.
						query_report.refresh();
						return;
					}
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
				default: fy[1],
			},
			{
				fieldname: "to_date",
				label: __("To Date"),
				fieldtype: "Date",
				default: fy[2],
			},
			{
				fieldname: "sync_status",
				label: __("Sync Status"),
				fieldtype: "Select",
				options: ["", "Pending", "Synced", "Failed"],
			},
		],
	};
})();
