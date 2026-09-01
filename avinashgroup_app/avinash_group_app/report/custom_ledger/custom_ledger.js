// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Custom Ledger"] = {
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
			// The four legacy print-outs are one engine on two axes, so the
			// design is a filter like any other.
			fieldname: "report_format",
			label: __("Format"),
			fieldtype: "Select",
			reqd: 1,
			options: [
				"General Ledger - Summary",
				"Normal Sub Ledger - Summary",
				"General Ledger - Posting Detail",
				"Normal Sub Ledger - Detail",
			].join("\n"),
			default: "Normal Sub Ledger - Summary",
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			on_change: function () {
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
			// The legacy footer's own account picker: "General Ledgers : 19 of 225".
			// Leave blank for every account in the company.
			fieldname: "general_ledger",
			label: __("General Ledgers"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Account", txt, {
					company: frappe.query_report.get_filter_value("company"),
					is_group: 0,
				});
			},
		},
		{
			fieldname: "include_cash_bank",
			label: __("Include Cash / Bank Code"),
			fieldtype: "Check",
			default: 0,
		},
		{
			// The legacy Summary prints accounts with no movement at all.
			fieldname: "show_zero_values",
			label: __("Show zero values"),
			fieldtype: "Check",
			default: 0,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		// Account header, and (in the detail formats) the sub ledger header:
		// blank every other cell so empty numerics don't render as 0.00.
		if (data && (data._section || data._subsection)) {
			if (column.fieldname === "description") {
				const indent = data._subsection ? "padding-left:14px;" : "";
				return `<b style="display:block;text-align:left;${indent}">${frappe.utils.escape_html(
					data.description || ""
				)}</b>`;
			}
			if (column.fieldname === "code" || column.fieldname === "voucher_no") {
				return `<b>${frappe.utils.escape_html(data.code || data.voucher_no || "")}</b>`;
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
