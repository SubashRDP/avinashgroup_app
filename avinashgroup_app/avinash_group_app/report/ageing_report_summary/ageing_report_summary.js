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

// A MultiSelectList filter shows a chosen item by its label only while that
// item is in the dropdown's loaded list; otherwise it shows the id
// (NGI-CUS-01203). This looks up the chosen items' names and puts them back,
// so the filter shows "Rasmi Store" / the group's name.
const AGEING_NAME_SOURCES = {
	customer_group: ["Customer Group", "customer_group_name"],
	supplier_group: ["Supplier Group", "supplier_group_name"],
	party: null, // Customer or Supplier, from the Party Type filter
};

function ageing_show_names(fieldname) {
	const filter = frappe.query_report.get_filter(fieldname);
	const values = (filter && filter.get_value()) || [];
	if (!values.length) return;
	let source = AGEING_NAME_SOURCES[fieldname];
	if (!source) {
		const party_type = frappe.query_report.get_filter_value("party_type") || "Customer";
		source = [party_type, party_type === "Supplier" ? "supplier_name" : "customer_name"];
	}
	const [doctype, name_field] = source;
	frappe.db
		.get_list(doctype, { filters: { name: ["in", values] }, fields: ["name", name_field], limit: values.length })
		.then((rows) => {
			const names = Object.fromEntries(rows.map((r) => [r.name, r[name_field] || r.name]));
			const named = values.map((v) => ({ value: v, label: names[v] || v, description: v }));
			filter._options = named.concat((filter._options || []).filter((o) => !values.includes(o.value)));
			filter._selected_values = named;
			filter.update_status();
		});
}

// Make each name filter look the names up whenever its shown text is
// refreshed with an id it has no name for — whatever set the value (a click,
// the URL, a saved Prepared Report, the Summary / Ageing Report button).
function ageing_patch_name_filters(report) {
	Object.keys(AGEING_NAME_SOURCES).forEach((fieldname) => {
		const filter = report.get_filter(fieldname);
		if (!filter || filter._ageing_names_patched) return;
		filter._ageing_names_patched = true;
		const frappe_update_status = filter.update_status.bind(filter);
		filter.update_status = function () {
			frappe_update_status();
			const known = (this._options || []).map((o) => o.value);
			if ((this.values || []).some((v) => !known.includes(v))) ageing_show_names(fieldname);
		};
		ageing_show_names(fieldname); // a value set before this ran
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
				frappe.query_report.set_filter_value({ party: [], customer_group: [], supplier_group: [] });
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
			fieldname: "customer_group",
			label: __("Customer Group"),
			fieldtype: "MultiSelectList",
			depends_on: 'eval:doc.party_type == "Customer"',
			// Only the selected company's groups.
			get_data: function (txt) {
				const company = frappe.query_report.get_filter_value("company");
				if (!company) return [];
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.ageing_report.ageing_report.get_company_groups",
						args: { party_type: "Customer", company, txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "supplier_group",
			label: __("Supplier Group"),
			fieldtype: "MultiSelectList",
			depends_on: 'eval:doc.party_type == "Supplier"',
			// Only the selected company's groups.
			get_data: function (txt) {
				const company = frappe.query_report.get_filter_value("company");
				if (!company) return [];
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.ageing_report.ageing_report.get_company_groups",
						args: { party_type: "Supplier", company, txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "MultiSelectList",
			// Same company-scoped list as Party Ledger's Party filter.
			// The company's parties, narrowed to the chosen Customer / Supplier Groups.
			get_data: function (txt) {
				if (!frappe.query_report.filters) return;
				const party_type = frappe.query_report.get_filter_value("party_type") || "Customer";
				const company = frappe.query_report.get_filter_value("company");
				if (!company) return frappe.db.get_link_options(party_type, txt);
				const groups = frappe.query_report.get_filter_value(party_type === "Supplier" ? "supplier_group" : "customer_group") || [];
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.ageing_report.ageing_report.get_group_parties",
						args: { party_type, company, groups, txt },
					})
					.then((r) => r.message || []);
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
		ageing_patch_name_filters(report);
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
