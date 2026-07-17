// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

(() => {
	const today = frappe.datetime.get_today();
	// [name, year_start_date, year_end_date] of the fiscal year covering today;
	// guarded so a site with no running Fiscal Year doesn't error on report open.
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
			},
			{
				fieldname: "fiscal_year",
				label: __("Fiscal Year"),
				fieldtype: "Link",
				options: "Fiscal Year",
				default: fy[0],
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
				// Dates default to month-to-date, NOT the fiscal year range: this
				// report parses every Sales Invoice Version in range, and a full
				// year takes minutes. Picking a Fiscal Year fills the full range.
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
})();
