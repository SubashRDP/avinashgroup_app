// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Gas Dispatch (Quota)"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Company", txt);
			},
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				// Scope customers to the selected company(ies).
				const company = frappe.query_report.get_filter_value("company");
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.gas_dispatch_(quota).gas_dispatch_(quota).get_company_customers",
						args: { company: company, txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "percentage",
			label: __("Percentage"),
			fieldtype: "Float",
			description: __("Adds a column with the Quota raised or lowered by this percentage, e.g. 10 or -10. Leave blank to hide it."),
		},
	],
};
