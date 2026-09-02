// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["General Ledger Posting Detail"] = {
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
						args: {
							voucher_types: frappe.query_report.get_filter_value("voucher_type"),
							txt: txt,
						},
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
						args: {
							party_types: frappe.query_report.get_filter_value("party_type"),
							txt: txt,
						},
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
		// The whole narration sits in the Party Name/Description cell and spills
		// right across the empty Debit/Credit/Balance cells — the datatable has
		// no colspan, so overflow is the only way to an unbroken line. It goes
		// in a middle column, not the first: Fit Columns measures cell content,
		// and a narration in column one stretched it until Debit, Credit and
		// Balance were pushed off the page.
		if (data && data._narration) {
			if (column.fieldname === "party_name") {
				return `<span style="color:#6b7280;font-style:italic;">${frappe.utils.escape_html(
					data.party_name || ""
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

		// A ledger states a balance as a figure plus the side it falls on, not
		// as a signed number: 1,09,45,494.08 Cr, never -1,09,45,494.08. The
		// stored value stays signed so the running total and exports are
		// arithmetic; only the display carries the indicator.
		if (column.fieldname === "balance" && typeof value === "number" && value !== 0) {
			const side = value > 0 ? "Dr" : "Cr";
			const shown = default_formatter(Math.abs(value), row, column, data);
			const html = `${shown}&thinsp;<small style="color:#6b7280;">${side}</small>`;
			return data && data._bold ? `<b>${html}</b>` : html;
		}

		value = default_formatter(value, row, column, data);
		if (data && data._bold) {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
