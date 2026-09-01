// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.query_reports["Custom Ledger"] = {
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
			// The four legacy print-outs are one engine on two axes, so the
			// design is a filter like any other.
			fieldname: "report_format",
			label: __("Format"),
			fieldtype: "Select",
			reqd: 1,
			options: [
				"General Ledger - Summary",
				"Normal Sub Ledger - Summary",
				"General Ledger - Posting Detail",
				"Normal Sub Ledger - Detail",
			].join("\n"),
			default: "Normal Sub Ledger - Summary",
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
			// One control decides how the period is chosen. Each choice reveals
			// only the fields it needs: "Fiscal Year" shows the year picker,
			// "Custom Dates" shows From/To, everything else computes both.
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
			default: "Fiscal Year",
			on_change: function () {
				frappe.query_reports["Custom Ledger"].apply_period(frappe.query_report);
			},
		},
		{
			// Shown only when Period is "Fiscal Year". Defaults to the running
			// year, so the report opens on the current books.
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			on_change: function () {
				const report = frappe.query_report;
				if (report.get_filter_value("period_preset") !== "Fiscal Year") return;
				const fiscal_year = report.get_filter_value("fiscal_year");
				if (!fiscal_year) return;
				frappe.model.with_doc("Fiscal Year", fiscal_year, function () {
					const fy = frappe.model.get_doc("Fiscal Year", fiscal_year);
					report.set_filter_value({
						from_date: fy.year_start_date,
						to_date: fy.year_end_date,
					});
				});
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[2],
		},
		{
			// Legacy "General Ledger Type" radio. Picking one narrows the
			// General Ledgers list AND the report itself, which is how the
			// legacy operator selects a whole class of accounts at once.
			fieldname: "ledger_type",
			label: __("General Ledger Type"),
			fieldtype: "Select",
			options: ["Both", "Profit & Loss", "Balance Sheet"].join("\n"),
			default: "Both",
			on_change: function () {
				// The account list depends on this, so clear a now-invalid pick.
				// An explicit pick overrides the type server-side, so dropping it
				// here keeps what is shown and what is applied in step.
				frappe.query_report.set_filter_value("general_ledger", []);
				frappe.query_report.refresh();
			},
		},
		{
			// The legacy footer's own account picker: "General Ledgers : 19 of 225".
			// Leave blank for every account in the company.
			//
			// frappe.db.get_link_options caps at ten results, which cannot show
			// the ~395 accounts a company has here, so this goes to the report's
			// own endpoint for the full list.
			fieldname: "general_ledger",
			label: __("General Ledgers"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const company = frappe.query_report.get_filter_value("company");
				if (!company) return [];
				return frappe
					.call({
						method:
							"avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger.get_general_ledgers",
						args: {
							company: company,
							txt: txt,
							ledger_type: frappe.query_report.get_filter_value("ledger_type"),
						},
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "include_cash_bank",
			label: __("Include Cash / Bank Code"),
			fieldtype: "Check",
			default: 0,
		},
		{
			// Legacy "Suppress Zero Transaction General Ledger", inverted so the
			// checkbox reads positively.
			fieldname: "show_zero_values",
			label: __("Show Zero Transaction Ledgers"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "show_grand_total",
			label: __("Show Grand Total"),
			fieldtype: "Check",
			default: 1,
		},
		{
			// Legacy "Remarks" — the narration carried on each posting.
			fieldname: "remarks",
			label: __("Remarks"),
			fieldtype: "Check",
			default: 1,
		},
		{
			// Legacy "Month Total" — a subtotal at each BS month boundary.
			// Detail formats only.
			fieldname: "month_total",
			label: __("Month Total"),
			fieldtype: "Check",
			default: 0,
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
			const fiscal_year =
				report.get_filter_value("fiscal_year") ||
				erpnext.utils.get_fiscal_year(frappe.datetime.get_today());
			frappe.model.with_doc("Fiscal Year", fiscal_year, function () {
				const fy = frappe.model.get_doc("Fiscal Year", fiscal_year);
				if (!fy) return;
				report.set_filter_value({
					fiscal_year: fiscal_year,
					from_date: fy.year_start_date,
					to_date: fy.year_end_date,
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
		// Open on the current fiscal year with only the year picker showing.
		frappe.query_reports["Custom Ledger"].apply_period(report);

		// Print-out matching the legacy layout: same header block, Nepali digit
		// grouping, and the "Report Parameters" footer.
		report.page.add_inner_button(__("Download PDF"), function () {
			const filters = report.get_values();
			if (!filters.company) {
				frappe.msgprint(__("Please select a Company."));
				return;
			}
			const url =
				"/api/method/avinashgroup_app.avinash_group_app.report.custom_ledger.custom_ledger.download_pdf" +
				"?filters=" + encodeURIComponent(JSON.stringify(filters)) +
				"&orientation=Portrait";
			window.open(url);
		});
	},

	formatter: function (value, row, column, data, default_formatter) {
		// Account header, and (in the detail formats) the sub ledger header:
		// blank every other cell so empty numerics don't render as 0.00.
		if (data && (data._section || data._subsection)) {
			if (column.fieldname === "description") {
				const indent = data._subsection ? "padding-left:14px;" : "";
				return `<b style="display:block;text-align:left;${indent}">${frappe.utils.escape_html(
					data.description || ""
				)}</b>`;
			}
			if (column.fieldname === "code" || column.fieldname === "voucher_no") {
				return `<b>${frappe.utils.escape_html(data.code || data.voucher_no || "")}</b>`;
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
