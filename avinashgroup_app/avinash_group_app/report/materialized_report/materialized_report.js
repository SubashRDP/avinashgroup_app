// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

(() => {
	const today = frappe.datetime.get_today();
	// Name of the fiscal year covering today, used only to default the Fiscal
	// Year filter; guarded so a site with no running Fiscal Year doesn't error.
	// The From/To date window is derived server-side from this fiscal year — see
	// get_conditions() in materialized_report.py — so there are no date filters here.
	const fy = erpnext.utils.get_fiscal_year(today, false, true)
		? erpnext.utils.get_fiscal_year(today, true)
		: [];

	frappe.query_reports["Materialized Report"] = {
		onload(report) {
			// The built-in Export produces a bare table; replace it with a
			// server-built Excel that carries the company letterhead and a totals
			// row. Instance-level override only — other reports are unaffected.
			report.export_report = function () {
				const filters = frappe.query_report.get_filter_values(true);
				const url =
					"/api/method/avinashgroup_app.avinash_group_app.report.materialized_report.materialized_report.export_xlsx" +
					"?filters=" + encodeURIComponent(JSON.stringify(filters));
				window.open(url);
			};
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
				fieldname: "fiscal_year",
				label: __("Fiscal Year"),
				fieldtype: "Link",
				options: "Fiscal Year",
				default: fy[0],
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
