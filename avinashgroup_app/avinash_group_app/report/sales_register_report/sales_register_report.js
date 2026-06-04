// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Register Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			get_data: function(txt) {
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
			get_data: function(txt) {
				return frappe.db.get_link_options("Customer", txt);
			},
		},
		{
			fieldname: "is_return",
			label: __("Is Return"),
			fieldtype: "Check",
			default: 0,
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
		return Object.assign(options, { serialNoColumn: false, freezeColumnsTo: 3, layout: "fixed" });
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
			let maxWidth = 120;

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
		// Resolve which columns the PRINT pdf should show, matching the report:
		//  1) if "Pick Columns" was used in the print dialog, use those;
		//  2) otherwise use whatever columns are still visible in the datatable
		//     (so removing a column via the datatable menu reflects in the print).
		// Returns [] when all columns are visible => template shows all.
		// NOTE: used by print_report only; the Download PDF button stays "show all".
		const sr_selected_columns = function (print_settings) {
			const cols = frappe.query_report.columns || [];
			const report_fields = new Set(cols.map(c => c.fieldname));

			if (print_settings && print_settings.pick_columns && print_settings.columns && print_settings.columns.length) {
				const by_label = {};
				cols.forEach(c => { by_label[c.label] = c.fieldname; });
				return print_settings.columns
					.map(v => (report_fields.has(v) ? v : by_label[v]))
					.filter(Boolean);
			}

			const dt = frappe.query_report.datatable;
			if (!dt || !dt.datamanager) return [];
			const visible = dt.datamanager.getColumns()
				.map(c => c.fieldname || c.id)
				.filter(fn => report_fields.has(fn));
			// nothing removed -> [] so the template just shows all
			return visible.length === report_fields.size ? [] : visible;
		};

		_report.page.add_inner_button(__('Download PDF'), function () {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.from_date || !filters.to_date) {
				frappe.msgprint(__('Please set From Date and To Date'));
				return;
			}
			const url = '/api/method/avinashgroup_app.avinash_group_app.report.sales_register_report.sales_register_report.download_pdf'
				+ '?filters=' + encodeURIComponent(JSON.stringify(filters));
			window.open(url);
		});

		_report.print_report = function (print_settings) {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.from_date || !filters.to_date) {
				frappe.msgprint(__('Please set From Date and To Date'));
				return;
			}
			// Print opens the SAME wkhtmltopdf PDF the Download button produces (orientation
			// from the print dialog). Print and Download are now identical, and printing or
			// saving from the PDF viewer is exact — no browser re-pagination.
			const orientation = (print_settings && print_settings.orientation) || 'Landscape';
			const url = '/api/method/avinashgroup_app.avinash_group_app.report.sales_register_report.sales_register_report.download_pdf'
				+ '?filters=' + encodeURIComponent(JSON.stringify(filters))
				+ '&orientation=' + encodeURIComponent(orientation)
				+ '&selected_columns=' + encodeURIComponent(JSON.stringify(sr_selected_columns(print_settings)));
			window.open(url);
		};

		if (!frappe.ui.get_print_settings._pick_columns_patched) {
			const _orig = frappe.ui.get_print_settings;
			const _our_reports = ['Sales Register Report', 'Purchase Register Report'];
			const _patched = function (pdf, callback, letter_head, pick_columns, has_filters) {
				const report_name = frappe.query_report && frappe.query_report.report_name;
				if (_our_reports.indexOf(report_name) === -1) {
					return _orig(pdf, callback, letter_head, pick_columns, has_filters);
				}
				const _wrappedCb = function (data) {
					if (data.pick_columns && !(data.columns && data.columns.length)) {
						frappe.msgprint({ message: __('Please choose the columns you want to include'), indicator: 'orange' });
						setTimeout(function () {
							frappe.ui.get_print_settings(pdf, callback, letter_head, pick_columns, has_filters);
						}, 150);
						return;
					}
					callback(data);
				};
				const d = _orig(pdf, _wrappedCb, letter_head, pick_columns, has_filters);
				if (d && pick_columns && pick_columns.length) {
					setTimeout(function () { d.set_value('pick_columns', 1); }, 100);
				}
				return d;
			};
			_patched._pick_columns_patched = true;
			frappe.ui.get_print_settings = _patched;
		}
	},

	formatter: function (value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);

		if (column.fieldname === "bill_no" && value && !data.bold) {
			value = `<a href="/app/sales-invoice/${value}" target="_blank">${value}</a>`;
			return value;
		}

		value = default_formatter(value, row, column, data);
		if (data.bold) {
			value = `<strong>${value}</strong>`;
		}
		return value;
	},
};
