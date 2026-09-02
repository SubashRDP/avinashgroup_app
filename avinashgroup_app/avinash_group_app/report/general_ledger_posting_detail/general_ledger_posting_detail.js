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
			fieldname: "remarks",
			label: __("Show Narration"),
			fieldtype: "Check",
			default: 1,
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
	},

	formatter: function (value, row, column, data, default_formatter) {
		// The narration is its own row under the posting. A datatable cell clips
		// at its column width and there is no colspan, so it goes in the widest
		// column (Party Name/Description) with the full text on hover. Absolute
		// positioning was tried to span the row and froze the renderer on a
		// thousand rows, so it is deliberately not used.
		if (data && data._narration) {
			if (column.fieldname === "party_name") {
				const full = data.narration_full || data.narration || "";
				return `<span style="color:#6b7280;font-style:italic;" title="${frappe.utils.escape_html(
					full
				)}">${frappe.utils.escape_html(full)}</span>`;
			}
			return "";
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
