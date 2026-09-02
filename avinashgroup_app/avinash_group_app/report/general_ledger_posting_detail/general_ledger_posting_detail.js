// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["General Ledger Posting Detail"] = {
	// The pickers below are scoped to the company and the period, so a filter
	// only ever offers values that can actually appear in the report. Kept in
	// one place because all of them need the same three arguments.
	scope_args: function () {
		const report = frappe.query_report;
		return {
			company: report.get_filter_value("company"),
			from_date: report.get_filter_value("from_date"),
			to_date: report.get_filter_value("to_date"),
		};
	},

	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
			// Only the companies this user is permitted to see, and all of
			// them -- the stock Link search pages ten at a time and ignores
			// nothing, so it offered companies the user has no business in.
			get_query: function () {
				return {
					query:
						"avinashgroup_app.avinash_group_app.report.general_ledger_posting_detail." +
						"general_ledger_posting_detail.company_query",
				};
			},
			on_change: function () {
				// Party, subtype and account all belong to a company; a
				// selection carried over from the previous one would filter
				// the report down to nothing.
				const report = frappe.query_report;
				report.set_filter_value("party", []);
				report.set_filter_value("voucher_subtype", []);
				report.set_filter_value("account", []);
				report.refresh();
			},
		},
		{
			// Account / Party / Both — what each block of postings is headed by.
			fieldname: "categorized_by",
			label: __("Group By"),
			fieldtype: "Select",
			reqd: 1,
			options: ["Account", "Party", "Both"].join("\n"),
			default: "Account",
		},
		{
			// Same Period control as Custom Ledger: one choice decides how the
			// dates are set, and reveals only the fields it needs.
			fieldname: "period_preset",
			label: __("Period"),
			fieldtype: "Select",
			reqd: 1,
			options: [
				"Fiscal Year",
				"Last Fiscal Year",
				"This Fiscal Quarter",
				"Last Fiscal Quarter",
				"This Month",
				"Last Month",
				"Today",
				"Yesterday",
				"Custom Dates",
			].join("\n"),
			default: "This Month",
			on_change: function () {
				frappe.query_reports["General Ledger Posting Detail"].apply_period(
					frappe.query_report
				);
			},
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			on_change: function () {
				const report = frappe.query_report;
				if (report.get_filter_value("period_preset") !== "Fiscal Year") return;
				const fy = report.get_filter_value("fiscal_year");
				if (!fy) return;
				frappe.model.with_doc("Fiscal Year", fy, function () {
					const doc = frappe.model.get_doc("Fiscal Year", fy);
					report.set_filter_value({
						from_date: doc.year_start_date,
						to_date: doc.year_end_date,
					});
				});
			},
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
			default: frappe.datetime.month_end(),
		},
		{
			fieldname: "voucher_type",
			label: __("Voucher Type"),
			fieldtype: "MultiSelectList",
			get_data: function () {
				return [
					"Sales Invoice",
					"Purchase Invoice",
					"Payment Entry",
					"Journal Entry",
					"Purchase Receipt",
					"Stock Entry",
					"Stock Reconciliation",
				].map((v) => ({ value: v, description: "" }));
			},
			on_change: function () {
				// subtypes belong to a voucher type, so a changed type invalidates them
				frappe.query_report.set_filter_value("voucher_subtype", []);
				frappe.query_report.refresh();
			},
		},
		{
			// Lives in a different field on every doctype, so the options are
			// gathered server-side from whichever types are selected.
			fieldname: "voucher_subtype",
			label: __("Voucher Subtype"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe
					.call({
						method:
							"avinashgroup_app.avinash_group_app.report.general_ledger_posting_detail." +
							"general_ledger_posting_detail.get_subtypes",
						args: Object.assign(
							{
								voucher_types:
									frappe.query_report.get_filter_value("voucher_type"),
								txt: txt,
							},
							frappe.query_reports["General Ledger Posting Detail"].scope_args()
						),
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "MultiSelectList",
			get_data: function () {
				return ["Supplier", "Customer", "Employee"].map((v) => ({
					value: v,
					description: "",
				}));
			},
			on_change: function () {
				frappe.query_report.set_filter_value("party", []);
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe
					.call({
						method:
							"avinashgroup_app.avinash_group_app.report.general_ledger_posting_detail." +
							"general_ledger_posting_detail.get_parties",
						args: Object.assign(
							{
								party_types: frappe.query_report.get_filter_value("party_type"),
								txt: txt,
							},
							frappe.query_reports["General Ledger Posting Detail"].scope_args()
						),
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const company = frappe.query_report.get_filter_value("company");
				if (!company) return [];
				return frappe
					.call({
						method:
							"avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger." +
							"get_general_ledgers",
						args: { company: company, txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
		{
			// Matches the printed number, not the Frappe name.
			fieldname: "voucher_no",
			label: __("Voucher No."),
			fieldtype: "Data",
		},
		{
			// One switch for both screen and print-out. On screen it is instant:
			// a filter with its own on_change is responsible for refreshing
			// (query_report.js), so this one hides or shows the rows already
			// loaded rather than re-running a five-second query to drop them.
			// The print-out reads the same value server-side.
			fieldname: "remarks",
			label: __("Show Narration"),
			fieldtype: "Check",
			default: 1,
			on_change: function () {
				frappe.query_reports["General Ledger Posting Detail"].applyNarrationVisibility(
					frappe.query_report
				);
			},
		},
	],

	// Show only the fields the chosen Period needs, and resolve its dates.
	apply_period: function (report) {
		const preset = report.get_filter_value("period_preset") || "Fiscal Year";
		const by_year = preset === "Fiscal Year";
		const custom = preset === "Custom Dates";

		report.get_filter("fiscal_year").toggle(by_year);
		report.get_filter("from_date").toggle(custom);
		report.get_filter("to_date").toggle(custom);

		if (custom) {
			report.refresh();
			return;
		}

		if (by_year) {
			const fy =
				report.get_filter_value("fiscal_year") ||
				erpnext.utils.get_fiscal_year(frappe.datetime.get_today());
			frappe.model.with_doc("Fiscal Year", fy, function () {
				const doc = frappe.model.get_doc("Fiscal Year", fy);
				if (!doc) return;
				report.set_filter_value({
					fiscal_year: fy,
					from_date: doc.year_start_date,
					to_date: doc.year_end_date,
				});
			});
			return;
		}

		frappe
			.call({
				method:
					"avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger.get_period",
				args: { preset: preset, company: report.get_filter_value("company") },
			})
			.then((r) => {
				if (r.message && r.message.from_date) {
					report.set_filter_value(r.message);
				}
			});
	},

	onload: function (report) {
		frappe.query_reports["General Ledger Posting Detail"].apply_period(report);

		// Let a narration cell spill across the row. frappe-datatable has no
		// colspan (checked: zero occurrences in the library), and every cell is
		// overflow:hidden with 0.5rem padding, so a full-width line is only
		// possible by lifting overflow on the row. Same approach as Receipt
		// Register's remarks sub-line.
		if (!document.getElementById("glpd-narration-style")) {
			const style = document.createElement("style");
			style.id = "glpd-narration-style";
			style.textContent = `
				.glpd-narration-row .dt-cell { overflow: visible !important; }
				/* position:relative gives the absolutely-positioned narration
				   span something to anchor to; overflow:visible lets it run
				   past the cell edge across the empty cells to its right. */
				.glpd-narration-row .dt-cell__content {
					overflow: visible !important;
					white-space: nowrap;
					position: relative;
					z-index: 5;
				}
			`;
			document.head.appendChild(style);
		}

		report.page.add_inner_button(__("Download PDF"), function () {
			const filters = report.get_values();
			if (!filters.company) {
				frappe.msgprint(__("Please select a Company."));
				return;
			}
			window.open(
				"/api/method/avinashgroup_app.avinash_group_app.report." +
					"general_ledger_posting_detail.general_ledger_posting_detail.download_pdf" +
					"?filters=" + encodeURIComponent(JSON.stringify(filters)) +
					"&orientation=Landscape"
			);
		});
	},

	// Show or hide the narration rows the server already sent, without a
	// round-trip. showRows re-renders just the indices given; showAllRows
	// restores everything. Indices are positions in report.data, which is
	// also what the .dt-row-N classes are keyed on, so tagging still lines up.
	applyNarrationVisibility: function (report) {
		const dt = report.datatable;
		const data = report.data || [];
		if (!dt || !dt.rowmanager || !data.length) return;

		const show = !!report.get_filter_value("remarks");
		if (show) {
			dt.rowmanager.showAllRows();
		} else {
			const keep = [];
			data.forEach(function (row, i) {
				if (!row || !row._narration) keep.push(i);
			});
			dt.rowmanager.showRows(keep);
		}
		frappe.query_reports["General Ledger Posting Detail"].tagNarrationRows(dt);
	},

	// rdp_common_app's shared Fit Columns sizes every column by its cells'
	// scrollWidth, and a narration cell overflows by design -- so whichever
	// column carried the narration was stretched to its 600px cap, pushing
	// Credit and Balance off the right edge.
	//
	// Defining autoFitColumns makes that shared control stand aside
	// (report_fit_columns.js: reportHasOwnFit) and use this instead. Same
	// measurement, with narration rows left out of it: they are meant to
	// overflow, so their width is not a column's width.
	autoFitColumns: function (dt) {
		const wrapper = dt && dt.datatableWrapper;
		if (!wrapper) return;

		const columns = dt.datamanager.getColumns(true) || [];
		const data = frappe.query_report.data || [];
		const narrationRows = new Set();
		data.forEach(function (row, i) {
			if (row && row._narration) narrationRows.add(i);
		});

		columns.forEach(function (col) {
			let width = 90;

			const header = wrapper.querySelector(".dt-cell__content--header-" + col.colIndex);
			if (header) width = Math.max(width, header.scrollWidth + 20);

			const cells = wrapper.querySelectorAll(".dt-cell__content--col-" + col.colIndex);
			const sample = Math.min(100, cells.length);
			for (let i = 0; i < sample; i++) {
				const cell = cells[i];
				const rowEl = cell.closest("[class*='dt-row-']");
				if (rowEl) {
					const match = /dt-row-(\d+)/.exec(rowEl.className);
					if (match && narrationRows.has(parseInt(match[1], 10))) continue;
				}
				width = Math.max(width, cell.scrollWidth + 20);
			}

			dt.datamanager.updateColumn(col.colIndex, { width: Math.min(width, 340) });
			dt.columnmanager.setColumnHeaderWidth(col.colIndex);
			dt.columnmanager.setColumnWidth(col.colIndex);
		});
	},

	// Tag the narration rows so the CSS above can apply to them.
	tagNarrationRows: function (dt) {
		const data = frappe.query_report.data || [];
		const container = dt && dt.bodyScrollable;
		if (!container) return;
		data.forEach(function (row, i) {
			if (!row || !row._narration) return;
			const rowEl = container.querySelector(".dt-row-" + i);
			if (rowEl) rowEl.classList.add("glpd-narration-row");
		});
	},

	after_datatable_render: function (dt) {
		const me = frappe.query_reports["General Ledger Posting Detail"];
		// a fresh render arrives with every row; apply the checkbox to it
		me.applyNarrationVisibility(frappe.query_report);
		// re-fit once the narration rows are tagged, so they are excluded
		setTimeout(function () {
			me.autoFitColumns(dt);
		}, 60);

		// frappe-datatable virtualises rows: only those near the viewport exist
		// in the DOM, and scrolling destroys and recreates them, wiping the
		// class off every row but the first few. Re-tag on scroll.
		const container = dt && dt.bodyScrollable;
		if (!container || container._glpdScanBound) return;
		container._glpdScanBound = true;
		let scheduled = false;
		container.addEventListener("scroll", function () {
			if (scheduled) return;
			scheduled = true;
			window.requestAnimationFrame(function () {
				scheduled = false;
				me.tagNarrationRows(dt);
			});
		});
	},

	formatter: function (value, row, column, data, default_formatter) {
		// The whole narration sits in the Voucher Type cell and spills right
		// across Voucher No. and Party Name, which are empty on this row — the
		// datatable has no colspan, so overflow is the only route to an
		// unbroken line. Voucher Type is chosen because Fit Columns sizes a
		// column to its widest cell: in Party Name the narration was the widest
		// cell in the table and pushed Balance off the right edge, while
		// Voucher Type's own width is set by short values like "Journal Entry".
		if (data && data._narration) {
			if (column.fieldname === "voucher_type") {
				// Absolutely positioned so it is out of flow: Fit Columns sizes
				// each column by its cells' scrollWidth, and an in-flow
				// narration made whichever column held it the widest in the
				// table — it stretched to ~600px and pushed Balance off screen.
				// Out of flow it contributes nothing to scrollWidth, so the
				// column keeps its natural width and the text still runs the
				// full width of the row.
				return `<span style="position:absolute;left:8px;top:50%;
					transform:translateY(-50%);white-space:nowrap;color:#6b7280;
					font-style:italic;pointer-events:none;">${frappe.utils.escape_html(
						data.voucher_type || ""
					)}</span>`;
			}
			return "";
		}

		// A blank line between sections carries nothing at all.
		if (data && data._spacer) {
			return "";
		}

		// Opening / Period Total / Closing carry only the figures that mean
		// something on that line: a balance band has no movement, and Period
		// Total is a movement with no balance. A Currency cell renders a missing
		// value as 0.00, which reads as a real zero — so blank them instead.
		if (data && data._band) {
			const value = data[column.fieldname];
			if (
				(value === undefined || value === null) &&
				["debit", "credit", "balance"].includes(column.fieldname)
			) {
				return "";
			}
		}

		if (data && data._section) {
			if (column.fieldname === "party_name") {
				return `<b>${frappe.utils.escape_html(data.party_name || "")}</b>`;
			}
			return "";
		}

		value = default_formatter(value, row, column, data);
		if (data && data._bold) {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
