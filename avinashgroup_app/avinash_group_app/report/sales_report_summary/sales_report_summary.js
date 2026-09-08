// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

const METHOD_PATH =
	"avinashgroup_app.avinash_group_app.report.sales_report_summary.sales_report_summary";

frappe.query_reports["Sales Report Summary"] = {
	filters: [
		{
			fieldname: "report_type",
			label: __("Report Type"),
			fieldtype: "Select",
			options: [
				"Sales Report Summary",
				"Sales Report Summary Branch Wise",
				"Sales Report Summary Company-wise Comparison",
			],
			default: "Sales Report Summary",
			reqd: 1,
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			// Only the comparison view has a measure to choose: it decides what the
			// per-company columns hold.
			fieldname: "comparison_measure",
			label: __("Compare By"),
			fieldtype: "MultiSelectList",
			default: ["Qty Wise"],
			depends_on: "eval:doc.report_type=='Sales Report Summary Company-wise Comparison'",
			get_data: function (txt) {
				return frappe
					.call({
						method: `${METHOD_PATH}.get_comparison_measures`,
						args: { txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			// Defaults to every company, filled in on load (see onload) — the option list
			// is not available at the time this default would be evaluated.
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			reqd: 1,
			get_data: function (txt) {
				return frappe.db.get_link_options("Company", txt);
			},
		},
		{
			// On This Month and Fiscal Year the server resolves the window and fills the
			// From/To Date boxes, which stay visible in every mode (see syncResolvedDates).
			fieldname: "date_filter_type",
			label: __("Filter By"),
			fieldtype: "Select",
			options: ["Date Range", "This Month", "Fiscal Year"],
			default: "Date Range",
			reqd: 1,
			on_change: function () {
				frappe.query_reports["Sales Report Summary"].syncResolvedDates();
			},
		},
		{
			// The fiscal year's start/end dates are resolved on the server from the
			// Fiscal Year record, never computed here.
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: frappe.defaults.get_user_default("fiscal_year"),
			depends_on: "eval:doc.date_filter_type=='Fiscal Year'",
			on_change: function () {
				frappe.query_reports["Sales Report Summary"].syncResolvedDates();
			},
		},
		{
			// No depends_on: From/To Date stay on screen whatever the Filter By choice,
			// so the dates in play are always readable, and stay editable in every mode.
			// This Month and Fiscal Year prefill them (see syncResolvedDates).
			// The shared rdp_common_app hook (report_nepali_date.js) auto-attaches a BS
			// (Miti) twin to every Date filter, so the BS dates appear beside these.
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
		},
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe
					.call({
						method: `${METHOD_PATH}.get_company_items`,
						args: {
							company: frappe.query_report.get_filter_value("company"),
							txt: txt,
						},
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe
					.call({
						method: `${METHOD_PATH}.get_company_branches`,
						args: {
							company: frappe.query_report.get_filter_value("company"),
							txt: txt,
						},
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "price_list",
			label: __("Price List"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe
					.call({
						method: `${METHOD_PATH}.get_company_price_lists`,
						args: {
							company: frappe.query_report.get_filter_value("company"),
							txt: txt,
						},
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "include_return",
			label: __("Include Return"),
			fieldtype: "Check",
			default: 0,
		},
	],

	// Keep the report's own print template (sales_report_summary.html) even when the
	// print dialog's "Pick Columns" is used.
	//
	// Frappe chooses the template as `print_settings.columns ? "print_grid" : custom_format`,
	// so ticking Pick Columns drops this report back to the stock grid — which brings back
	// the Rs symbol and the leading "#" column. The picked columns are honoured here
	// instead: the report's own column list is narrowed to the chosen fieldnames and the
	// flag is cleared, so Frappe renders the custom template with only those columns.
	// Both methods are async, so the originals are restored once the render settles.
	// Patched on the instance, not the prototype, so no other report is affected.
	keepCustomFormatOnPickColumns: function (report) {
		["print_report", "pdf_report"].forEach(function (method) {
			const original = report[method];
			if (typeof original !== "function" || report["_srs_" + method]) return;
			report["_srs_" + method] = true;

			report[method] = function (print_settings) {
				const picked = print_settings && print_settings.columns;
				if (!picked || !picked.length) {
					return original.apply(this, arguments);
				}

				const saved_columns = this.columns;
				this.columns = (this.columns || []).filter((col) =>
					picked.includes(col.fieldname)
				);
				print_settings.columns = null;

				const restore = () => {
					this.columns = saved_columns;
					print_settings.columns = picked;
				};

				try {
					return Promise.resolve(original.apply(this, arguments)).finally(restore);
				} catch (e) {
					restore();
					throw e;
				}
			};
		});
	},

	// Fill and lock the From/To Date boxes for the modes that derive their own window.
	//
	// The dates are always on screen and always editable. This Month and Fiscal Year do
	// not lock them: they prefill them — the server resolves the Nepali month, or the
	// Fiscal Year record's own start/end, and writes the pair into the two boxes. The
	// boxes are then what the query runs on (see _period), so a date typed over the top
	// is honoured rather than silently recomputed.
	// Only ever written when the value actually differs, so setting them cannot feed
	// back into another refresh.
	syncResolvedDates: function () {
		const report = frappe.query_report;
		if (!report) return;

		const filter_type = report.get_filter_value("date_filter_type");
		const derived = ["This Month", "Fiscal Year"].includes(filter_type);

		// Switching back to Date Range hands the boxes back to the user, and they start
		// at today rather than keeping the month or fiscal year that was resolved into
		// them. Only a real switch resets them: the previous choice is remembered so a
		// report opened on Date Range — from a saved link carrying its own dates, say —
		// keeps the dates it was given.
		const switched_to_range =
			!derived && this._last_filter_type && this._last_filter_type !== filter_type;
		this._last_filter_type = filter_type;

		if (!derived) {
			if (switched_to_range) {
				const today = frappe.datetime.now_date();
				if (
					report.get_filter_value("from_date") !== today ||
					report.get_filter_value("to_date") !== today
				) {
					report.set_filter_value({ from_date: today, to_date: today });
				}
			}
			return;
		}

		frappe
			.call({
				method: `${METHOD_PATH}.get_period`,
				args: { filters: report.get_filter_values() },
			})
			.then(function (r) {
				const period = r.message;
				if (!period) return;
				if (
					report.get_filter_value("from_date") === period.from_date &&
					report.get_filter_value("to_date") === period.to_date
				) {
					return;
				}
				report.set_filter_value({
					from_date: period.from_date,
					to_date: period.to_date,
				});
			});
	},

	// Select every company on first open. A report opened from a saved link or with the
	// filter already set keeps what it was given.
	onload: function (report) {
		this.keepCustomFormatOnPickColumns(report);
		this.syncResolvedDates();

		// The company heading is drawn as a full-width banner. frappe-datatable has no
		// colspan, so the name is allowed to spill out of its cell (overflow: visible)
		// across the empty, uniformly shaded cells to its right — the same approach the
		// Receipt Register uses for its customer banner. Positioning it against the row
		// rather than the cell is what centres it across the whole width.
		if (!document.getElementById("srs-company-header-style")) {
			const style = document.createElement("style");
			style.id = "srs-company-header-style";
			style.textContent = `
				.srs-company-row { position: relative; }
				.srs-company-row .dt-cell { background: #f2f2f2 !important; overflow: visible !important; position: static !important; }
				.srs-company-row .dt-cell__content { overflow: visible !important; }
				/* No z-index. Being absolutely positioned already paints the banner over
				   the plain cells beside it, while a positive z-index would also paint it
				   over the filter dropdowns — Awesomplete's list is only z-index 1, so a
				   banner at 10 showed through the open Fiscal Year list. */
				.srs-company-banner {
					position: absolute; left: 0; right: 0; text-align: center;
					font-weight: bold; white-space: nowrap;
				}
			`;
			document.head.appendChild(style);
		}

		if ((report.get_filter_value("company") || []).length) return;

		frappe
			.call({ method: `${METHOD_PATH}.get_all_companies` })
			.then((r) => {
				const companies = r.message || [];
				if (companies.length) {
					report.set_filter_value("company", companies);
				}
			});
	},

	after_datatable_render: function (dt) {
		const me = this;
		setTimeout(function () {
			me.tagCompanyRows(dt);
			me.bindCompanyRescan(dt);
		}, 100);
	},


	tagCompanyRows: function (dt) {
		const data = frappe.query_report.data || [];
		const container = dt && dt.bodyScrollable;
		if (!container) return;
		data.forEach(function (row, i) {
			if (!row || !row._section) return;
			const rowEl = container.querySelector(".dt-row-" + i);
			if (rowEl) rowEl.classList.add("srs-company-row");
		});
	},

	bindCompanyRescan: function (dt) {
		// frappe-datatable virtualizes rows: only those near the viewport exist in the
		// DOM, and scrolling destroys and recreates them — wiping the banner class off
		// every company row but the first few. Re-tag on scroll so the banner follows
		// each company heading down the report.
		const me = this;
		const container = dt && dt.bodyScrollable;
		if (!container || container._srsCompanyScanBound) return;
		container._srsCompanyScanBound = true;
		let scheduled = false;
		container.addEventListener("scroll", function () {
			if (scheduled) return;
			scheduled = true;
			window.requestAnimationFrame(function () {
				scheduled = false;
				me.tagCompanyRows(dt);
			});
		});
	},

	formatter: function (value, row, column, data, default_formatter) {
		// The company name goes in the first cell and the CSS above stretches it across
		// the row. Every other cell stays empty rather than formatting its missing value
		// as 0.000. The name still lives in item_name, so an Excel export keeps it.
		if (data && data._section) {
			if (column.fieldname === "item_name") {
				return `<span class="srs-company-banner">${frappe.utils.escape_html(
					data.item_name || ""
				)}</span>`;
			}
			return "";
		}

		// Spacer rows between companies: nothing at all.
		if (data && !data.item_name && !data.uom && !data.price_list) {
			return "";
		}

		value = default_formatter(value, row, column, data);
		if (data && data.bold) {
			value = `<strong>${value}</strong>`;
		}
		return value;
	},
};
