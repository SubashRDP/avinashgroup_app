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
		onload(report) {
			// Dates come from the backend, not the browser: default to
			// month-to-date via get_default_dates() in invoice_activity_report.py.
			// (Month-to-date, NOT the fiscal year range — this report parses every
			// Sales Invoice Version in range and a full year takes minutes.)
			frappe
				.call(
					"avinashgroup_app.avinash_group_app.report.invoice_activity_report.invoice_activity_report.get_default_dates"
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
				fieldname: "fiscal_year",
				label: __("Fiscal Year"),
				fieldtype: "Link",
				options: "Fiscal Year",
				default: fy[0],
				on_change: function (query_report) {
					const fiscal_year = query_report.get_filter_value("fiscal_year");
					if (!fiscal_year) return;
					// Fiscal-year date span resolved on the server (Fiscal Year
					// record), never from a client-side doc read.
					frappe
						.call({
							method: "avinashgroup_app.custom_code.CBMS.utils.get_fiscal_year_dates",
							args: { fiscal_year },
						})
						.then((r) => {
							if (r.message) query_report.set_filter_value(r.message);
						});
				},
			},
			{
				fieldname: "from_date",
				label: __("From Date"),
				fieldtype: "Date",
				reqd: 1,
			},
			{
				fieldname: "to_date",
				label: __("To Date"),
				fieldtype: "Date",
				reqd: 1,
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
