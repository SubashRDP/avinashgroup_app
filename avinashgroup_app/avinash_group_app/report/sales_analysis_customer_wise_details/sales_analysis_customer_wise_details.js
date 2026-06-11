// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Analysis Customer wise Details"] = {
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
				// Scope customers to those with invoices in the selected company(ies).
				const company = frappe.query_report.get_filter_value("company");
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.sales_analysis_customer_wise_details.sales_analysis_customer_wise_details.get_company_customers",
						args: { company: company, txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "item_code",
			label: __("Product"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				// Items are global in ERPNext, so scope the list to items sold in the
				// selected company(ies) instead of listing every item.
				const company = frappe.query_report.get_filter_value("company");
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.sales_analysis_customer_wise_details.sales_analysis_customer_wise_details.get_company_items",
						args: { company: company, txt: txt },
					})
					.then((r) => r.message || []);
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
		// No divider rules drawn on screen — they sometimes landed on the wrong rows in the
		// datatable. The PDF/print template still draws the section rules via CSS.
		const fit = frappe.query_report.get_filter_value("fit_columns");
		if (fit) {
			setTimeout(() => {
				this.autoFitColumns(dt);
			}, 100);
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

	onload: function (_report) {
		_report.page.add_inner_button(__("Download PDF"), function () {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.from_date || !filters.to_date) {
				frappe.msgprint(__("Please set From Date and To Date"));
				return;
			}
			const url =
				"/api/method/avinashgroup_app.avinash_group_app.report.sales_analysis_customer_wise_details.sales_analysis_customer_wise_details.download_pdf" +
				"?filters=" + encodeURIComponent(JSON.stringify(filters));
			window.open(url);
		});

		_report.print_report = function (print_settings) {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.from_date || !filters.to_date) {
				frappe.msgprint(__("Please set From Date and To Date"));
				return;
			}
			const orientation = (print_settings && print_settings.orientation) || "Portrait";
			const url =
				"/api/method/avinashgroup_app.avinash_group_app.report.sales_analysis_customer_wise_details.sales_analysis_customer_wise_details.download_pdf" +
				"?filters=" + encodeURIComponent(JSON.stringify(filters)) +
				"&orientation=" + encodeURIComponent(orientation) +
				"&view=1";
			window.open(url);
		};
	},

	formatter: function (value, row, column, data, default_formatter) {
		// Customer/Product header rows carry no amounts — leave the numeric columns blank
		// instead of rendering 0.000 / Rs 0.00. Summary rows still show genuine zeros.
		const numeric = ["qty", "value", "vat", "total_incl_vat"];
		if (data && (data.is_customer_header || data.is_product_header)) {
			if (numeric.includes(column.fieldname)) {
				return "";
			}
		}

		value = default_formatter(value, row, column, data);
		if (!data) return value;

		// Bold the customer/product names and every summary label + its figures.
		if (data.is_customer_header || data.is_product_header) {
			value = `<strong>${value}</strong>`;
		}
		if (data.summary_kind === "cust" || data.summary_kind === "grand") {
			value = `<strong>${value}</strong>`;
		}
		return value;
	},
};
