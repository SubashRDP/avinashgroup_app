// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Analysis Product wise Invoice Details"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
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
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Customer", txt);
			},
		},
		{
			fieldname: "item_code",
			label: __("Product"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Item", txt);
			},
		},
		{
			fieldname: "include_return",
			label: __("Include Return"),
			fieldtype: "Check",
			default: 1,
			on_change: function () {
				frappe.query_report.refresh();
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
		return Object.assign(options, { serialNoColumn: false, freezeColumnsTo: 0, layout: "fixed" });
	},

	after_datatable_render: function (dt) {
		const fit = frappe.query_report.get_filter_value("fit_columns");
		if (fit) {
			setTimeout(() => {
				this.autoFitColumns(dt);
				this.applyGrandDivider(dt);
			}, 100);
		} else {
			this.applyGrandDivider(dt);
		}
	},

	// One continuous bold line above the grand-total block. Drawn as a top border on
	// every CELL of that row (cells are adjacent → the borders join into one full-width
	// line with no gaps), not on the cell content (which boxed the text before).
	applyGrandDivider: function (dt) {
		const container = (dt && dt.bodyScrollable) || document;
		const data = frappe.query_report.data || [];
		data.forEach((row, i) => {
			if (row && row.grand_start) {
				const cells = container.querySelectorAll(".dt-cell--row-" + i);
				cells.forEach((c) => {
					c.style.borderTop = "2px solid #000";
				});
			}
		});
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

	onload: function (_report) {
		_report.page.add_inner_button(__("Download PDF"), function () {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.from_date || !filters.to_date) {
				frappe.msgprint(__("Please set From Date and To Date"));
				return;
			}
			const url =
				"/api/method/avinashgroup_app.avinash_group_app.report.sales_analysis_product_wise_invoice_details.sales_analysis_product_wise_invoice_details.download_pdf" +
				"?filters=" + encodeURIComponent(JSON.stringify(filters));
			window.open(url);
		});

		_report.print_report = function (print_settings) {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.from_date || !filters.to_date) {
				frappe.msgprint(__("Please set From Date and To Date"));
				return;
			}
			const orientation = (print_settings && print_settings.orientation) || "Landscape";
			const url =
				"/api/method/avinashgroup_app.avinash_group_app.report.sales_analysis_product_wise_invoice_details.sales_analysis_product_wise_invoice_details.download_pdf" +
				"?filters=" + encodeURIComponent(JSON.stringify(filters)) +
				"&orientation=" + encodeURIComponent(orientation) +
				"&view=1";
			window.open(url);
		};
	},

	formatter: function (value, row, column, data, default_formatter) {
		// Title/header rows (product, customer, section) carry no amounts — leave the
		// numeric columns blank instead of rendering 0.000 / Rs 0.00. Real amount rows
		// (invoices, subtotals) still show 0 when the value is genuinely zero.
		const numeric = ["qty", "value", "vat", "total_incl_vat"];
		if (data && (data.is_product_header || data.is_customer_header || data.is_section || data.is_agent_group)) {
			if (numeric.includes(column.fieldname)) {
				return "";
			}
		}

		value = default_formatter(value, row, column, data);
		if (!data) return value;

		// Summary-row labels live in the invoice_no column; bold them.
		if (data.bold) {
			value = `<strong>${value}</strong>`;
		}
		if (data.is_product_header || data.is_customer_header) {
			value = `<strong>${value}</strong>`;
		}
		// Note: the divider line above the grand-total block is drawn on the row element
		// in applyGrandDivider() (continuous, full-width), not here on the cell content.
		return value;
	},
};
