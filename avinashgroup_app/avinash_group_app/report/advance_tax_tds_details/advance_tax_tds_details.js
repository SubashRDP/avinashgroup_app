// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Advance Tax TDS Details"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.now_date(),
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

	// Keep "Fit Columns" (a view toggle) out of the printed "Include filters" block.
	onload: function (report) {
		report.get_filters_html_for_print = function () {
			const applied = report.get_filter_values();
			return Object.keys(applied)
				.filter((fieldname) => fieldname !== "fit_columns")
				.map((fieldname) => {
					const filter = report.get_filter(fieldname);
					if (!filter || filter.df.hidden_due_to_dependency) return null;
					const df = filter.df;
					return `<div class="filter-row"><b>${__(df.label, null, df.parent)}:</b> ${frappe.format(
						applied[fieldname],
						df
					)}</div>`;
				})
				.filter(Boolean)
				.join("");
		};
	},

	get_datatable_options(options) {
		return Object.assign(options, { serialNoColumn: false, layout: "fixed" });
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

	// Signature block shown ONLY on the printed page / PDF (not the live grid).
	// Picked up by avinashgroup report_print_orientation.js via window.__rdpPrintFooter.
	after_datatable_render: function (dt) {
		const fit = frappe.query_report.get_filter_value("fit_columns");
		if (fit) {
			setTimeout(() => this.autoFitColumns(dt), 100);
		}
		window.__rdpPrintFooter = {
			report: "Advance Tax TDS Details",
			html:
				// hide the print template's built-in "#" column (we have our own क्र.सं.)
				"<style>.print-format table th:first-child,.print-format table td:first-child{display:none !important;}</style>" +
				'<div style="margin-top:55px;display:flex;justify-content:space-between;padding:0 30px;">' +
				'<div style="border-top:1px solid #000;padding-top:4px;min-width:150px;">Prepared By:</div>' +
				'<div style="border-top:1px solid #000;padding-top:4px;min-width:150px;">Checked By:</div>' +
				'<div style="border-top:1px solid #000;padding-top:4px;min-width:150px;">Verified By:</div>' +
				"</div>",
		};
	},

	formatter: function (value, row, column, data, default_formatter) {
		// Section-header row: show the category title in the कारोबार रकम column,
		// the account no in खाता नं, and leave every other cell blank (no 0.00).
		if (data && data._section) {
			if (column.fieldname === "turnover") {
				return `<b style="display:block;text-align:left;">${data.section_title || ""}</b>`;
			}
			if (column.fieldname === "account_no") {
				return `<b>${data.account_no || ""}</b>`;
			}
			return "";
		}

		// Blank numeric cells that carry no real value (spacer rows) so they
		// don't render as 0.00.
		if (
			(column.fieldname === "turnover" || column.fieldname === "tds_amount") &&
			(value === undefined || value === null || value === "")
		) {
			return "";
		}

		value = default_formatter(value, row, column, data);
		if (data && data._bold) {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
