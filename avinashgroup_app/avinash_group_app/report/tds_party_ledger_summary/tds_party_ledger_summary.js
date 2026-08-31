// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["TDS Party Ledger Summary"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			on_change: function (query_report) {
				const fiscal_year = frappe.query_report.get_filter_value("fiscal_year");
				if (!fiscal_year) return;
				frappe.model.with_doc("Fiscal Year", fiscal_year, function () {
					const fy = frappe.model.get_doc("Fiscal Year", fiscal_year);
					frappe.query_report.set_filter_value({
						from_date: fy.year_start_date,
						to_date: fy.year_end_date,
					});
				});
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[2],
		},
		{
			// Both sides of TDS in one ledger — the whole point of this report.
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "MultiSelectList",
			default: ["Supplier", "Customer"],
			get_data: function (txt) {
				return frappe.db.get_link_options("Party Type", txt);
			},
		},
		{
			// Leave blank to pick up every TDS account in the company.
			fieldname: "account",
			label: __("TDS Account"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Account", txt, {
					company: frappe.query_report.get_filter_value("company"),
				});
			},
		},
		{
			fieldname: "include_no_subledger",
			label: __("Include No Subledger"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "show_zero_values",
			label: __("Show zero values"),
			fieldtype: "Check",
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		// Account header row: the account label spans from the description
		// column; every other cell stays blank so it doesn't render as 0.00.
		if (data && data._section) {
			if (column.fieldname === "party_name") {
				return `<b style="display:block;text-align:left;">${frappe.utils.escape_html(
					data.party_name || ""
				)}</b>`;
			}
			return "";
		}

		value = default_formatter(value, row, column, data);
		if (data && data._bold) {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
