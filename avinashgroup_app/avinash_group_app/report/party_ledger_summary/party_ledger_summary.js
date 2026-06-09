// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Party Ledger Summary"] = {
	filters: [
		{
			fieldname: "report_type",
			label: __("Report Type"),
			fieldtype: "Select",
			options: "Super Summary\nGroup Wise",
			default: "Super Summary",
			reqd: 1,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Select",
			options: "Customer\nSupplier",
			default: "Customer",
			reqd: 1,
			on_change: function () {
				// Reset dependent filters when the party type changes.
				frappe.query_report.set_filter_value("party_group", []);
				frappe.query_report.set_filter_value("party", []);
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "party_group",
			label: __("Party Group"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const party_type = frappe.query_report.get_filter_value("party_type") || "Customer";
				const company = frappe.query_report.get_filter_value("company");
				// No company yet → fall back to all groups; otherwise scope to groups whose
				// parties transact in the selected company.
				if (!company) {
					const doctype = party_type === "Customer" ? "Customer Group" : "Supplier Group";
					return frappe.db.get_link_options(doctype, txt);
				}
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.party_ledger_summary.party_ledger_summary.get_company_party_groups",
						args: { party_type, company, txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				if (!frappe.query_report.filters) return;
				const party_type = frappe.query_report.get_filter_value("party_type") || "Customer";
				const company = frappe.query_report.get_filter_value("company");
				if (!company) {
					return frappe.db.get_link_options(party_type, txt);
				}
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.party_ledger_summary.party_ledger_summary.get_company_parties",
						args: { party_type, company, txt },
					})
					.then((r) => r.message || []);
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
			fieldname: "show_zero_balance",
			label: __("Show Zero Balance"),
			fieldtype: "Check",
			default: 0,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "fit_columns",
			label: __("Fit Columns"),
			fieldtype: "Check",
			default: 0,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
	],

	get_datatable_options(options) {
		// serialNoColumn: true adds a leading "Sr No" column so Customer Code is no longer
		// the first column — its inline filter binds correctly only when not at index 0.
		return Object.assign(options, { layout: "fixed", serialNoColumn: true });
	},

	after_datatable_render: function (dt) {
		const fit = frappe.query_report.get_filter_value("fit_columns");
		if (fit) {
			setTimeout(() => this.autoFitColumns(dt), 100);
		}
		this._placeMonthPickerNextToFit();
		// Reveal the datatable's inline filter row (hidden by default) so the per-column
		// search boxes — incl. Customer Code — are visible without pressing Ctrl+Shift+F.
		if (dt && dt.columnmanager && !dt.columnmanager.isFilterShown) {
			dt.columnmanager.toggleFilter(true);
		}
		// Constrain the scroll area to the viewport so the horizontal scrollbar stays
		// visible and fixed at the bottom (even after Fit Columns widens the table) —
		// otherwise it sits below all the rows and you must scroll down to reach it.
		if (dt && dt.bodyScrollable) {
			dt.bodyScrollable.style.maxHeight = "calc(100vh - 230px)";
			dt.bodyScrollable.style.overflow = "auto";
		}
	},

	// The shared rdp_common_app appends its "Select Month" picker to the end of the
	// filter area (far right). Move it to sit right after the Fit Columns control.
	// Scoped to this report only — the shared app is untouched.
	_placeMonthPickerNextToFit: function () {
		let tries = 0;
		const move = () => {
			const picker = document.querySelector(".month-picker-wrapper");
			const fit = document.querySelector('.frappe-control[data-fieldname="fit_columns"]');
			if (picker && fit && fit.parentNode) {
				if (fit.nextSibling !== picker) {
					fit.parentNode.insertBefore(picker, fit.nextSibling);
				}
				return;
			}
			if (tries++ < 12) setTimeout(move, 200);
		};
		move();
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

			let finalWidth = Math.min(maxWidth, 400);
			if (col.id === "party")      finalWidth = Math.max(finalWidth, 200);
			if (col.id === "party_name") finalWidth = Math.max(finalWidth, 240);
			dt.datamanager.updateColumn(col.colIndex, { width: finalWidth });
			dt.columnmanager.setColumnHeaderWidth(col.colIndex);
			dt.columnmanager.setColumnWidth(col.colIndex);
		});
	},

	onload: function (_report) {
		// Override the built-in Export menu: produce a custom Excel where Opening and
		// Closing each show the magnitude followed by a Dr/Cr column. The on-screen report
		// is unchanged. Instance-level override only — does not affect other reports.
		_report.export_report = function () {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.company) {
				frappe.msgprint(__("Please set Company"));
				return;
			}
			const url =
				"/api/method/avinashgroup_app.avinash_group_app.report.party_ledger_summary.party_ledger_summary.export_xlsx" +
				"?filters=" + encodeURIComponent(JSON.stringify(filters));
			window.open(url);
		};

		// Resolve which columns the PRINT pdf should show:
		//  1) "Pick Columns" in the print dialog, else
		//  2) whatever columns are still visible in the datatable (after removals).
		// Returns [] when all columns are visible => template shows all.
		const summary_selected_columns = function (print_settings) {
			const cols = frappe.query_report.columns || [];
			const report_fields = new Set(cols.map((c) => c.fieldname));

			if (print_settings && print_settings.pick_columns && print_settings.columns && print_settings.columns.length) {
				const by_label = {};
				cols.forEach((c) => { by_label[c.label] = c.fieldname; });
				return print_settings.columns
					.map((v) => (report_fields.has(v) ? v : by_label[v]))
					.filter(Boolean);
			}

			const dt = frappe.query_report.datatable;
			if (!dt || !dt.datamanager) return [];
			const visible = dt.datamanager.getColumns()
				.map((c) => c.fieldname || c.id)
				.filter((fn) => report_fields.has(fn));
			return visible.length === report_fields.size ? [] : visible;
		};

		_report.page.add_inner_button(__("Download PDF"), function () {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.company || !filters.from_date || !filters.to_date) {
				frappe.msgprint(__("Please set Company, From Date and To Date"));
				return;
			}
			const url =
				"/api/method/avinashgroup_app.avinash_group_app.report.party_ledger_summary.party_ledger_summary.download_pdf" +
				"?filters=" + encodeURIComponent(JSON.stringify(filters));
			window.open(url);
		});

		// Native Print produces the same wkhtmltopdf PDF as Download (orientation from
		// the print dialog), so Print and Download are identical.
		_report.print_report = function (print_settings) {
			const filters = frappe.query_report.get_filter_values(true);
			if (!filters.company || !filters.from_date || !filters.to_date) {
				frappe.msgprint(__("Please set Company, From Date and To Date"));
				return;
			}
			const orientation = (print_settings && print_settings.orientation) || "Portrait";
			// view=1 → open the same PDF inline in a new tab (view only, no download).
			const url =
				"/api/method/avinashgroup_app.avinash_group_app.report.party_ledger_summary.party_ledger_summary.download_pdf" +
				"?filters=" + encodeURIComponent(JSON.stringify(filters)) +
				"&orientation=" + encodeURIComponent(orientation) +
				"&selected_columns=" + encodeURIComponent(JSON.stringify(summary_selected_columns(print_settings))) +
				"&view=1";
			window.open(url);
		};
	},

	formatter: function (value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);

		const fn = column.fieldname;
		const is_total = data.is_group_total || data.is_grand_total;
		const is_header = data.is_group_header;

		// Party code column: group-header / total rows are labels, not real parties —
		// render plain text, keep bold.
		if (fn === "party" && (is_total || is_header)) {
			return value ? `<b>${value}</b>` : "";
		}
		// Normal party rows: clickable link to the Customer/Supplier master.
		if (fn === "party" && value) {
			const pt = frappe.query_report.get_filter_value("party_type") || "Customer";
			return `<a href="/app/${pt.toLowerCase()}/${encodeURIComponent(value)}">${value}</a>`;
		}

		// Opening / Closing: show absolute amount with DB/CR suffix.
		if (fn === "opening" || fn === "closing") {
			if (value === null || value === undefined || value === "") return "";
			const n = flt(value);
			const suffix = n >= 0 ? "DB" : "CR";
			let out = format_number(Math.abs(n), null, 2) + " " + suffix;
			if (data.bold) out = `<b>${out}</b>`;
			return out;
		}

		// Debit / Credit: show 0.00 when empty; bold on total rows.
		if (fn === "debit" || fn === "credit") {
			const n = flt(value);
			let out = format_number(n, null, 2);
			if (data.bold) out = `<b>${out}</b>`;
			return out;
		}

		// Group header / total labels and party code/name: bold where flagged.
		let out = default_formatter(value, row, column, data);
		if ((is_total || is_header) && value) out = `<b>${out}</b>`;
		return out;
	},
};
