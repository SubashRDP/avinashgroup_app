// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Loan Summary"] = {
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
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			reqd: 1,
		},
		{
			fieldname: "show_details",
			label: __("Show Details"),
			fieldtype: "Check",
			default: 0,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
	],

	// When "Include filters" is ticked on print and no Company is selected,
	// show the group name instead of a blank Company line. Overridden on this
	// report instance only — no change to other reports.
	onload: function (report) {
		const GROUP_NAME = "Nepal Gas Group";
		report.get_filters_html_for_print = function () {
			return (report.filters || [])
				.map((filter) => {
					const df = filter.df;
					if (df.hidden || df.hidden_due_to_dependency) return null;
					// "Show Details" is a view toggle, not a real filter — keep it out of print
					if (df.fieldname === "show_details") return null;
					const value = filter.get_value ? filter.get_value() : null;
					const is_empty =
						value == null ||
						value === "" ||
						(Array.isArray(value) && value.length === 0);
					let formatted;
					if (df.fieldname === "company") {
						formatted = is_empty
							? GROUP_NAME
							: Array.isArray(value)
								? value.join(", ")
								: frappe.format(value, df);
					} else {
						if (is_empty) return null;
						formatted = frappe.format(value, df);
					}
					return `<div class="filter-row"><b>${__(df.label, null, df.parent)}:</b> ${formatted}</div>`;
				})
				.filter(Boolean)
				.join("");
		};
	},

	get_datatable_options(options) {
		return Object.assign(options, { serialNoColumn: false, layout: "fixed" });
	},

	// Bold the subtotal / total / ratio rows, and indent the per-account detail
	// rows (shown when "Show Details" is ticked) under their loan type.
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data._bold) {
			value = `<b>${value}</b>`;
		}
		if (data && data._detail && column.fieldname === "loan_type") {
			value = `<span style="padding-left:18px;color:#6b7280;">${value}</span>`;
		}
		return value;
	},
};
