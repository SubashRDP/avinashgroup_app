// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["One Lakh Above Transactions"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			reqd: 1,
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
			fieldname: "fit_columns",
			label: __("Fit Columns"),
			fieldtype: "Check",
			default: 1,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
	],

	// Standalone-HTML print/PDF (matches the grid, cleanly paginated) — the raw
	// datatable doesn't survive browser Ctrl+P, so Print opens the rendered page.
	onload: function (report) {
		const PDF_METHOD =
			"/api/method/avinashgroup_app.avinash_group_app.report.one_lakh_above_transactions.one_lakh_above_transactions.download_pdf";
		const requireFilters = function (filters) {
			if (!filters.company || !filters.from_date || !filters.to_date) {
				frappe.msgprint(__("Please set Company, From Date and To Date"));
				return false;
			}
			return true;
		};

		report.page.add_inner_button(__("Download PDF"), function () {
			const filters = frappe.query_report.get_filter_values(true);
			if (!requireFilters(filters)) return;
			window.open(
				PDF_METHOD +
					"?filters=" + encodeURIComponent(JSON.stringify(filters)) +
					"&orientation=Portrait"
			);
		});

		report.print_report = function (print_settings) {
			const filters = frappe.query_report.get_filter_values(true);
			if (!requireFilters(filters)) return;
			const orientation = (print_settings && print_settings.orientation) || "Portrait";
			window.open(
				PDF_METHOD +
					"?filters=" + encodeURIComponent(JSON.stringify(filters)) +
					"&orientation=" + encodeURIComponent(orientation) +
					"&view=1"
			);
		};
	},

	get_datatable_options(options) {
		return Object.assign(options, { serialNoColumn: false, layout: "fixed" });
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
			let maxWidth = Math.max(col.width || 60, 60);

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
};
