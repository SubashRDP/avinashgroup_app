// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["User Audit Trail"] = {
	filters: [
		{
			fieldname: "user",
			label: __("User"),
			fieldtype: "Link",
			options: "User",
			reqd: 1,
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
			fieldname: "document_type",
			label: __("Document Type"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.user_audit_trail.user_audit_trail.get_audited_doctypes",
						args: { txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "action",
			label: __("Action"),
			fieldtype: "Select",
			options: "All\nCreated\nModified",
			default: "All",
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		if (column.fieldname === "document_name" && data && data.document_type && value) {
			const dt = frappe.router.slug(data.document_type);
			return `<a href="/app/${dt}/${encodeURIComponent(value)}">${value}</a>`;
		}
		return default_formatter(value, row, column, data);
	},
};
