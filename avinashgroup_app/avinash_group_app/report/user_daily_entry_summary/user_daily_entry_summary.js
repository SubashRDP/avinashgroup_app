// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["User Daily Entry Summary"] = {
	// Always run fresh — never serve a previously generated/cached (prepared) report.
	onload: function (report) {
		report.ignore_prepared_report = true;
	},

	filters: [
		{
			fieldname: "user",
			label: __("User"),
			fieldtype: "Link",
			options: "User",
			reqd: 1,
		},
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			reqd: 1,
		},
		{
			fieldname: "action",
			label: __("Action"),
			fieldtype: "Select",
			options: "Both\nCreated\nModified",
			default: "Both",
		},
		{
			fieldname: "document_type",
			label: __("Document Type"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.user_daily_entry_summary.user_daily_entry_summary.get_tracked_doctypes",
						args: { txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
	],

	// Turn the Created / Modified counts into links that open the documents behind
	// the number in the target doctype's list view, using the same standard
	// owner/creation and modified_by/modified columns the report counts on.
	formatter: function (value, row, column, data, default_formatter) {
		const fieldname = column.fieldname;
		if ((fieldname === "created" || fieldname === "modified") && data && data.document_type && value) {
			const slug = frappe.router.slug(data.document_type);
			const user = frappe.query_report.get_filter_value("user");
			const date = frappe.query_report.get_filter_value("date");
			const range = [date + " 00:00:00", date + " 23:59:59"];
			let filters;

			if (fieldname === "created") {
				filters = {
					owner: user,
					creation: ["between", range],
				};
			} else {
				filters = {
					modified_by: user,
					modified: ["between", range],
				};
			}

			const params = Object.entries(filters)
				.map(([k, v]) => `${k}=${encodeURIComponent(JSON.stringify(v))}`)
				.join("&");
			const href = `/app/${slug}/view/list?${params}`;
			return `<a href="${href}">${value}</a>`;
		}
		return default_formatter(value, row, column, data);
	},
};
