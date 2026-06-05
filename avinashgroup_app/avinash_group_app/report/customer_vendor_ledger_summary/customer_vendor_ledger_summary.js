// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Customer Vendor Ledger Summary"] = {
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
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Select",
			options: "\nCustomer\nSupplier",
			default: "Customer",
			reqd: 1,
			on_change: function () {
				frappe.query_report.set_filter_value("party", []);
			},
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "MultiSelectList",
			options: "party_type",
			get_data: function (txt) {
				if (!frappe.query_report.filters) return;
				let party_type = frappe.query_report.get_filter_value("party_type") || "Customer";
				return frappe.db.get_link_options(party_type, txt);
			},
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "MultiSelectList",
			options: "Account",
			get_data: function (txt) {
				const company = frappe.query_report.get_filter_value("company");
				const filters = { is_group: 0 };
				if (company) filters.company = company;
				return frappe.db.get_link_options("Account", txt, filters);
			},
		},
		{
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
			fieldname: "hide_zero_balance",
			label: __("Hide Zero Balance Parties"),
			fieldtype: "Check",
			default: 1,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.is_total) {
			value = `<span style="font-weight:600">${value}</span>`;
		}
		// Drill down into the detailed Party Ledger for a clicked party.
		if (column.fieldname === "party" && data && data.party && !data.is_total) {
			const filters = {
				company: frappe.query_report.get_filter_value("company"),
				party_type: frappe.query_report.get_filter_value("party_type"),
				party: [data.party],
				from_date: frappe.query_report.get_filter_value("from_date"),
				to_date: frappe.query_report.get_filter_value("to_date"),
			};
			const url = `/app/query-report/Party Ledger?` +
				Object.entries(filters)
					.map(([k, v]) => `${k}=${encodeURIComponent(typeof v === "object" ? JSON.stringify(v) : v)}`)
					.join("&");
			return `<a href="${url}" target="_blank">${data.party}</a>`;
		}
		return value;
	},
};
