// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Material In Out Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			reqd: 1,
			// No on_change here on purpose: Frappe skips its own refresh for any
			// filter that defines one, and Price List holds category names
			// (Bulk, Dealer) that stay valid across companies, so there is
			// nothing to clear.
			get_data: function (txt) {
				return frappe.db.get_link_options("Company", txt);
			},
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
			fieldname: "price_list",
			label: __("Price List"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const companies = frappe.query_report.get_filter_value("company") || [];
				if (!companies.length) return [];

				return frappe
					.call({
						method:
							"avinashgroup_app.avinash_group_app.report.material_in_out_report.material_in_out_report.get_company_price_lists",
						args: { company: companies, txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "fit_columns",
			label: __("Fit Columns"),
			fieldtype: "Check",
			default: 1,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
	],

	get_datatable_options(options) {
		return Object.assign(options, { serialNoColumn: false, layout: "fixed" });
	},

	onload: function (report) {
		// Show the "please select filters" message where the empty-state
		// graphic would otherwise say "Nothing to show", instead of as a
		// separate banner above the report.
		report.show_status = function (status_message) {
			this._filter_status_message = status_message;
		};
		// Frappe calls hide_status() at the start of every response, before it
		// decides whether to show a new one — clear here so a stale message from
		// the previous run does not survive into a run that returned none.
		const hide_status = report.hide_status.bind(report);
		report.hide_status = function () {
			this._filter_status_message = null;
			hide_status();
		};
		report.get_no_result_message = function () {
			const message = this._filter_status_message || __("Nothing to show");
			return `<div class="msg-box no-border"><p>${message}</p></div>`;
		};
	},

	after_datatable_render: function (dt) {
		const fit = frappe.query_report.get_filter_value("fit_columns");
		if (fit) {
			setTimeout(() => this.autoFitColumns(dt), 100);
		}
	},

	autoFitColumns: function (dt) {
		const datatableWrapper = dt.datatableWrapper;
		if (!datatableWrapper) return;

		const columns = dt.datamanager.getColumns(true);
		if (!columns.length) return;

		columns.forEach((col) => {
			let maxWidth = 90;

			const headerCell = datatableWrapper.querySelector(
				`.dt-cell__content--header-${col.colIndex}`
			);
			if (headerCell) {
				maxWidth = Math.max(maxWidth, headerCell.scrollWidth + 20);
			}

			const dataCells = datatableWrapper.querySelectorAll(
				`.dt-cell__content--col-${col.colIndex}`
			);
			const sampleSize = Math.min(100, dataCells.length);
			for (let i = 0; i < sampleSize; i++) {
				maxWidth = Math.max(maxWidth, dataCells[i].scrollWidth + 20);
			}

			const finalWidth = Math.min(maxWidth, 400);
			dt.datamanager.updateColumn(col.colIndex, { width: finalWidth });
			dt.columnmanager.setColumnHeaderWidth(col.colIndex);
			dt.columnmanager.setColumnWidth(col.colIndex);
		});
	},

	formatter: function (value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);

		value = default_formatter(value, row, column, data);
		if (data.bold) {
			value = `<strong>${value}</strong>`;
		}
		return value;
	},
};
