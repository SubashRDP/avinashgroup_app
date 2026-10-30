// Customer Group filter for ERPNext's stock "Trial Balance for Party".
//
// Added to the end of the stock report script by query_report.get_script, so it
// runs right after ERPNext defines the report. The filtering itself is done
// server-side in trial_balance_party_customer_group.py.
//
// Options are limited to the selected company, using the same method as the
// Sales Analysis reports.
(function () {
	const report = frappe.query_reports["Trial Balance for Party"];
	if (!report || report.filters.some((f) => f.fieldname === "customer_group")) return;

	const party_at = report.filters.findIndex((f) => f.fieldname === "party");
	report.filters.splice(party_at + 1, 0, {
		fieldname: "customer_group",
		label: __("Customer Group"),
		fieldtype: "MultiSelectList",
		depends_on: "eval:doc.party_type == 'Customer'",
		get_data: function (txt) {
			return frappe
				.call({
					method: "avinashgroup_app.avinash_group_app.report.sales_analysis_customer_wise_summary.sales_analysis_customer_wise_summary.get_company_customer_groups",
					args: { company: frappe.query_report.get_filter_value("company"), txt: txt },
				})
				.then((r) => r.message || []);
		},
	});
})();
