// Copyright (c) 2026, Raindrop and contributors

frappe.query_reports["Net Position of Cash and Bank"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_end(),
			reqd: 1,
		},
		{
			fieldname: "cash_bank_codes",
			label: __("Cash / Bank Codes"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const company = frappe.query_report.get_filter_value("company");
				if (!company) return [];
				return frappe.db.get_link_options("Account", txt, {
					company: company,
					account_type: ["in", ["Cash", "Bank"]],
					is_group: 0,
					disabled: 0,
				});
			},
		},
		{
			fieldname: "suppress_local_currency_equivalents",
			label: __("Suppress Local Currency Equivalents"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "consider_post_dated_cheques",
			label: __("Consider Post Dated Cheques"),
			fieldtype: "Check",
			default: 0,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// Highlight the totals row for visual parity with the template.
		if (data && data.code === "" && data.description && data.description.includes(__("Totals"))) {
			value = `<span style="font-weight:600">${value}</span>`;
		}
		return value;
	},
};
