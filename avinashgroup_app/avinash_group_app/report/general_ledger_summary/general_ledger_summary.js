// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

const GLS_METHOD_BASE =
	"avinashgroup_app.avinash_group_app.report.general_ledger_summary.general_ledger_summary";
const GLS_PDF_METHOD = "/api/method/" + GLS_METHOD_BASE + ".download_pdf";

// Open the server-rendered PDF (full content + header). `extra` appends query args
// such as "&view=1" (open inline instead of download).
function gls_open_pdf(extra) {
	const filters = frappe.query_report.get_filter_values(true);
	if (!filters.company) {
		frappe.msgprint(__("Please set Company"));
		return;
	}
	window.open(
		GLS_PDF_METHOD +
			"?filters=" + encodeURIComponent(JSON.stringify(filters)) +
			(extra || "")
	);
}

// Frappe wipes the report's inner toolbar whenever it re-runs (filter change,
// prepared-report cycle) and only re-runs `onload` on a full page load, so the
// button vanishes "after a while". Re-add it on every datatable render; the
// "Actions" group + label de-dupe keep it from stacking.
function gls_ensure_pdf_button() {
	const page = frappe.query_report && frappe.query_report.page;
	if (!page) return;
	page.add_inner_button(
		__("Download PDF"),
		function () {
			gls_open_pdf("&orientation=Landscape");
		},
		__("Actions")
	);
}

// Fill the From/To Date boxes with the selected Fiscal Year's start/end dates,
// resolved on the server from the Fiscal Year record (never computed in the browser).
function gls_apply_fiscal_year_dates() {
	const fy = frappe.query_report.get_filter_value("fiscal_year");
	if (!fy) {
		frappe.query_report.set_filter_value({ from_date: "", to_date: "" });
		return;
	}
	return frappe
		.call({
			method: "avinashgroup_app.custom_code.CBMS.utils.get_fiscal_year_dates",
			args: { fiscal_year: fy },
		})
		.then((r) => {
			const d = r.message || {};
			frappe.query_report.set_filter_value({
				from_date: d.from_date || "",
				to_date: d.to_date || "",
			});
			frappe.query_report.refresh();
		});
}

frappe.query_reports["General Ledger Summary"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
			on_change: function () {
				// Account options are company-scoped — drop the old selection.
				frappe.query_report.set_filter_value("account", []);
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: frappe.defaults.get_user_default("fiscal_year"),
			reqd: 1,
			on_change: function () {
				// Re-fill From/To Date with the newly selected Fiscal Year's bounds.
				gls_apply_fiscal_year_dates();
			},
		},
		{
			// Optional. Blank -> Fiscal Year start. Always clamped inside the FY (backend).
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			// Optional. Blank -> Fiscal Year end. Always clamped inside the FY (backend).
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
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
						method: GLS_METHOD_BASE + ".get_company_accounts",
						args: { txt, filters: { company } },
					})
					.then((r) => r.message || []);
			},
		},
	],

	get_datatable_options(options) {
		return Object.assign(options, { layout: "fixed", serialNoColumn: true });
	},

	onload: function () {
		// The ⋮ Print / PDF menu actions are routed to download_pdf by the global
		// report_print_orientation.js (prototype patch, so it works regardless of
		// this onload). Here we only add the toolbar button and prefill dates.
		gls_ensure_pdf_button();

		// On first open, populate the date boxes from the preselected Fiscal Year
		// unless the user (or a saved report) already set explicit dates.
		if (
			frappe.query_report.get_filter_value("fiscal_year") &&
			!frappe.query_report.get_filter_value("from_date") &&
			!frappe.query_report.get_filter_value("to_date")
		) {
			gls_apply_fiscal_year_dates();
		}
	},

	after_datatable_render: function () {
		// The inner toolbar is rebuilt on every report re-run; keep the button alive.
		gls_ensure_pdf_button();
	},

	formatter: function (value, row, column, data, default_formatter) {
		let out = default_formatter(value, row, column, data);
		if (data && data.bold) {
			out = `<b>${out}</b>`;
		}
		return out;
	},
};
