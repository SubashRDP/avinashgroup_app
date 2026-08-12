// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

// No From/To Date filters — the date window is resolved entirely in the backend
// (see _apply_date_window() in invoice_activity_report.py): it is fixed to the
// current fiscal year's start..end, and a picked Fiscal Year overrides with that
// year's span.
(() => {
	const today = frappe.datetime.get_today();
	// Name of the fiscal year covering today (server-resolved via
	// erpnext.utils.get_fiscal_year) — used only to default the Fiscal Year
	// filter; guarded so a site with no running Fiscal Year doesn't error.
	const fy = erpnext.utils.get_fiscal_year(today, false, true)
		? erpnext.utils.get_fiscal_year(today, true)
		: [];

	frappe.query_reports["Invoice Activity Report"] = {
		filters: [
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Link",
				options: "Company",
				default: frappe.defaults.get_user_default("Company"),
				// Required, because blank does not mean "no filter" here — it
				// means every company the user may see, which for an
				// unrestricted user is all of them. The report is read
				// per-company, so an empty filter silently mixes companies
				// together.
				reqd: 1,
			},
			{
				fieldname: "fiscal_year",
				label: __("Fiscal Year"),
				fieldtype: "Link",
				options: "Fiscal Year",
				default: fy[0],
			},
			{
				fieldname: "operation",
				label: __("Operation"),
				fieldtype: "Select",
				options: "All\nAdd\nPrinted\nModified",
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
})();
