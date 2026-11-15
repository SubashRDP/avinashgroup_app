// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

// Ageing Report Summary: the Ageing Report, one row per party. The filters are
// the Ageing Report's — keep the two lists the same (Accounts Receivable and
// its Summary repeat theirs the same way).
// Debtors + Advance accounts of the company (Party Ledger's default Account
// filter), so cylinder deposits and other Receivable-type accounts stay out.
// Only for Customer; Supplier starts on every Payable account.
function ageing_set_default_accounts() {
	const company = frappe.query_report.get_filter_value("company");
	const party_type = frappe.query_report.get_filter_value("party_type");
	frappe.query_report.set_filter_value("account", []);
	if (!company || party_type !== "Customer") return;
	frappe
		.call({
			method: "avinashgroup_app.avinash_group_app.report.party_ledger.party_ledger.get_default_ledger_accounts",
			args: { company },
		})
		.then((r) => {
			if (r.message && r.message.length) frappe.query_report.set_filter_value("account", r.message);
		});
}

frappe.query_reports["Ageing Report Summary"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
			on_change: function () {
				frappe.query_report.set_filter_value("party", []);
				ageing_set_default_accounts();
			},
		},
		{
			fieldname: "report_date",
			label: __("As on Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Select",
			options: "Customer\nSupplier",
			default: "Customer",
			reqd: 1,
			on_change: function () {
				frappe.query_report.set_filter_value({ party: [], customer_group: [], supplier_group: [] });
				ageing_set_default_accounts();
			},
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "MultiSelectList",
			// Same company-scoped list as Party Ledger's Party filter.
			get_data: function (txt) {
				if (!frappe.query_report.filters) return;
				const party_type = frappe.query_report.get_filter_value("party_type") || "Customer";
				const company = frappe.query_report.get_filter_value("company");
				if (!company) return frappe.db.get_link_options(party_type, txt);
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.party_ledger.party_ledger.get_company_parties",
						args: { party_type, company, txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "customer_group",
			label: __("Customer Group"),
			fieldtype: "MultiSelectList",
			depends_on: 'eval:doc.party_type == "Customer"',
			get_data: function (txt) {
				return frappe.db.get_link_options("Customer Group", txt);
			},
		},
		{
			fieldname: "supplier_group",
			label: __("Supplier Group"),
			fieldtype: "MultiSelectList",
			depends_on: 'eval:doc.party_type == "Supplier"',
			get_data: function (txt) {
				return frappe.db.get_link_options("Supplier Group", txt);
			},
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "MultiSelectList",
			// The company's Receivable (Customer) or Payable (Supplier) accounts.
			get_data: function (txt) {
				if (!frappe.query_report.filters) return;
				const company = frappe.query_report.get_filter_value("company");
				const party_type = frappe.query_report.get_filter_value("party_type") || "Customer";
				return frappe.db.get_link_options("Account", txt, {
					company: company,
					is_group: 0,
					account_type: party_type === "Supplier" ? "Payable" : "Receivable",
				});
			},
		},
		{
			fieldname: "range",
			label: __("Ageing Range"),
			fieldtype: "Data",
			default: "30, 60, 90, 120",
			description: __("Days, separated by commas, as in Accounts Receivable"),
		},
		{
			fieldname: "merged",
			label: __("Merged"),
			fieldtype: "Check",
			default: 0,
		},
	],

	onload: function (report) {
		ageing_set_default_accounts();
		// Jump to the bill-wise report with the same filters, as Accounts
		// Receivable Summary does for Accounts Receivable.
		report.page.add_inner_button(__("Ageing Report"), function () {
			frappe.set_route("query-report", "Ageing Report", report.get_filter_values());
		});
	},

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.bold) value = `<b>${value}</b>`;
		return value;
	},
};
