// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

// docstatus value behind each status column, for the drill-down links.
const STATUS_DOCSTATUS = { draft: 0, submitted: 1, cancelled: 2 };

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

	// Turn each status count into a link that opens the documents behind it: docs
	// the selected user created on the day, filtered to that docstatus.
	formatter: function (value, row, column, data, default_formatter) {
		const fieldname = column.fieldname;
		if (fieldname in STATUS_DOCSTATUS && data && data.document_type && value) {
			const slug = frappe.router.slug(data.document_type);
			const user = frappe.query_report.get_filter_value("user");
			const date = frappe.query_report.get_filter_value("date");
			const range = [date + " 00:00:00", date + " 23:59:59"];
			const filters = {
				owner: user,
				creation: ["between", range],
				docstatus: STATUS_DOCSTATUS[fieldname],
			};

			// Scalar equality values (owner / docstatus) must go in raw — JSON
			// stringifying them adds literal quotes (owner="x"), which the list
			// view treats as part of the value and matches nothing. Only the
			// operator filters (["between", ...]) need JSON encoding.
			const params = Object.entries(filters)
				.map(([k, v]) => `${k}=${encodeURIComponent(Array.isArray(v) ? JSON.stringify(v) : v)}`)
				.join("&");
			const href = `/app/${slug}/view/list?${params}`;
			return `<a href="${href}">${value}</a>`;
		}
		return default_formatter(value, row, column, data);
	},
};
