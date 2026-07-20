// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

// No From/To Date filters — the date window is resolved entirely in the backend
// (see _apply_date_window() in invoice_activity_report.py): it is fixed to the
// current fiscal year's start..end, and a picked Fiscal Year overrides with that
// year's span.
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
