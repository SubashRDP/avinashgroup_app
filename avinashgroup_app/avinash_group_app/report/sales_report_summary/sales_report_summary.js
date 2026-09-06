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
			fieldname: "date_filter_type",
			label: __("Filter By"),
			fieldtype: "Select",
			options: ["Date Range", "Fiscal Year"],
			default: "Date Range",
			reqd: 1,
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
		},
		{
			// The shared rdp_common_app hook (report_nepali_date.js) auto-attaches a BS
			// (Miti) twin to every Date filter and the "📅 Select Month" picker, which
			// fills these AD dates.
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			depends_on: "eval:doc.date_filter_type=='Date Range'",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			depends_on: "eval:doc.date_filter_type=='Date Range'",
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

	// Select every company on first open. A report opened from a saved link or with the
	// filter already set keeps what it was given.
	onload: function (report) {
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
				.srs-company-banner {
					position: absolute; left: 0; right: 0; text-align: center;
					font-weight: bold; white-space: nowrap; z-index: 10;
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
