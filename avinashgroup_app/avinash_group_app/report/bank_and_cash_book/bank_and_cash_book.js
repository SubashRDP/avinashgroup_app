// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Bank and Cash Book"] = {
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
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "MultiSelectList",
			// Empty -> all cash/bank ledgers of the company. Options are the leaf
			// accounts under "Cash and Cash Equivalent" for the chosen company.
			get_data: function (txt) {
				return frappe.call({
					method: "avinashgroup_app.avinash_group_app.report.bank_and_cash_book.bank_and_cash_book.get_cash_bank_accounts",
					args: { company: frappe.query_report.get_filter_value("company"), txt: txt },
				}).then((r) => r.message || []);
			},
		},
		{
			fieldname: "show_narration",
			label: __("Show Narration"),
			fieldtype: "Check",
			default: 1,
		},
	],

	onload: function (report) {
		const pdf_url = (view) => {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.company || !filters.from_date || !filters.to_date) {
				frappe.msgprint(__("Please set Company, From Date and To Date"));
				return null;
			}
			return (
				"/api/method/avinashgroup_app.avinash_group_app.report.bank_and_cash_book.bank_and_cash_book.download_pdf" +
				"?filters=" + encodeURIComponent(JSON.stringify(filters)) +
				(view ? "&view=1" : "")
			);
		};

		report.page.add_inner_button(__("Download PDF"), () => {
			const url = pdf_url(0);
			if (url) window.open(url);
		});

		// Native Print opens the same portrait PDF inline.
		report.print_report = () => {
			const url = pdf_url(1);
			if (url) window.open(url);
		};
	},

	formatter: function (value, row, column, data, default_formatter) {
		// Blank the amount columns on structural rows so they don't show 0.00.
		if (data && (data.is_account_header || data.is_opening || data.is_closing)) {
			if (["receipt", "payment"].includes(column.fieldname)) return "";
		}
		if (data && column.fieldname === "balance" && data.is_account_header) return "";
		value = default_formatter(value, row, column, data);
		if (data && data.bold) value = `<b>${value}</b>`;
		return value;
	},
};
