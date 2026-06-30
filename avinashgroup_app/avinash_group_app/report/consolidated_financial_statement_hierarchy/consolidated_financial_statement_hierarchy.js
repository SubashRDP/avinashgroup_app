frappe.query_reports["Consolidated Financial Statement Hierarchy"] = {
	filters: [
		{
			fieldname: "companies",
			label: __("Companies"),
			fieldtype: "MultiSelectList",
			default: frappe.defaults.get_user_default("Company")
				? [frappe.defaults.get_user_default("Company")]
				: [],
			get_data: function (txt) {
				return frappe.db.get_link_options("Company", txt);
			},
			// Empty selection = all companies (consolidate everything).
		},
		{
			fieldname: "filter_based_on",
			label: __("Filter Based On"),
			fieldtype: "Select",
			options: ["Fiscal Year", "Date Range"],
			default: ["Fiscal Year"],
			reqd: 1,
			on_change: function () {
				let filter_based_on = frappe.query_report.get_filter_value("filter_based_on");
				frappe.query_report.toggle_filter_display(
					"from_fiscal_year",
					filter_based_on === "Date Range"
				);
				frappe.query_report.toggle_filter_display(
					"to_fiscal_year",
					filter_based_on === "Date Range"
				);
				frappe.query_report.toggle_filter_display(
					"period_start_date",
					filter_based_on === "Fiscal Year"
				);
				frappe.query_report.toggle_filter_display(
					"period_end_date",
					filter_based_on === "Fiscal Year"
				);
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "period_start_date",
			label: __("Start Date"),
			fieldtype: "Date",
			hidden: 1,
		},
		{
			fieldname: "period_end_date",
			label: __("End Date"),
			fieldtype: "Date",
			hidden: 1,
		},
		{
			fieldname: "from_fiscal_year",
			label: __("Start Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			reqd: 1,
			on_change: () => {
				frappe.model.with_doc(
					"Fiscal Year",
					frappe.query_report.get_filter_value("from_fiscal_year"),
					function () {
						let year_start_date = frappe.model.get_value(
							"Fiscal Year",
							frappe.query_report.get_filter_value("from_fiscal_year"),
							"year_start_date"
						);
						frappe.query_report.set_filter_value({ period_start_date: year_start_date });
					}
				);
			},
		},
		{
			fieldname: "to_fiscal_year",
			label: __("End Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			reqd: 1,
			on_change: () => {
				frappe.model.with_doc(
					"Fiscal Year",
					frappe.query_report.get_filter_value("to_fiscal_year"),
					function () {
						let year_end_date = frappe.model.get_value(
							"Fiscal Year",
							frappe.query_report.get_filter_value("to_fiscal_year"),
							"year_end_date"
						);
						frappe.query_report.set_filter_value({ period_end_date: year_end_date });
					}
				);
			},
		},
		{
			fieldname: "finance_book",
			label: __("Finance Book"),
			fieldtype: "Link",
			options: "Finance Book",
		},
		{
			fieldname: "report",
			label: __("Report"),
			fieldtype: "Select",
			options: ["Profit and Loss Statement", "Balance Sheet", "Cash Flow"],
			default: "Balance Sheet",
			reqd: 1,
		},
		{
			// Reference set for the shared-account collapse (P&L / Balance Sheet only):
			//   Selected Companies -> account must exist in every selected company (default)
			//   All Companies      -> account must exist in every company in the system
			fieldname: "common_accounts_scope",
			label: __("Common Accounts"),
			fieldtype: "Select",
			options: ["Selected Companies", "All Companies"],
			default: "Selected Companies",
			reqd: 1,
		},
		{
			fieldname: "presentation_currency",
			label: __("Currency"),
			fieldtype: "Select",
			options: erpnext.get_presentation_currency_list(),
			default: frappe.defaults.get_user_default("Currency"),
		},
		{
			fieldname: "accumulated_in_group_company",
			label: __("Accumulated Values in Group Company"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "include_default_book_entries",
			label: __("Include Default FB Entries"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "show_zero_values",
			label: __("Show zero values"),
			fieldtype: "Check",
		},
		{
			fieldname: "account_level",
			label: __("Account Hierarchy Level"),
			fieldtype: "Select",
			options: "",
			default: "",
			reqd: 0,
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		// Money columns (per-company columns + the Total column).
		// Applies to all three report types (P&L / Balance Sheet / Cash Flow).
		//   - zero / empty amounts are shown blank
		//   - negative amounts are shown as "<absolute amount> Cr"
		const is_value_col = column.fieldtype === "Currency";

		if (data && is_value_col) {
			const raw = data[column.fieldname];

			// don't show zero / empty values
			if (raw === null || raw === undefined || raw === "" || Math.abs(flt(raw)) < 0.005) {
				return "";
			}

			// resolve currency the same way erpnext does for company columns
			const currency = column.apply_currency_formatter
				? erpnext.get_currency(column.company_name)
				: data.currency;

			let text = format_currency(Math.abs(flt(raw)), currency);
			if (flt(raw) < 0) {
				// negative -> credit notation
				text = text + " Cr";
			}

			let $value = $(`<span>${text}</span>`);
			if (!data.parent_account && !data.parent_section) {
				$value = $value.css("font-weight", "bold");
			}
			return $value.wrap("<p></p>").parent().html();
		}

		// Account / section name column and anything else -> default rendering
		if (data && column.fieldname == "account") {
			value = data.account_name || value;
			column.link_onclick =
				"erpnext.financial_statements.open_general_ledger(" + JSON.stringify(data) + ")";
			column.is_tree = true;
		}
		value = default_formatter(value, row, column, data);
		if (data && !data.parent_account) {
			value = $(`<span>${value}</span>`);
			var $value = $(value).css("font-weight", "bold");
			value = $value.wrap("<p></p>").parent().html();
		}
		return value;
	},
	onload: function (report) {
		// Set date defaults from fiscal year
		let fiscal_year = erpnext.utils.get_fiscal_year(frappe.datetime.get_today());
		frappe.model.with_doc("Fiscal Year", fiscal_year, function () {
			var fy = frappe.model.get_doc("Fiscal Year", fiscal_year);
			frappe.query_report.set_filter_value({
				period_start_date: fy.year_start_date,
				period_end_date: fy.year_end_date,
			});
		});

		// Representative company for the depth lookup: first selected, else default.
		const get_depth_company = () => {
			const v = report.get_filter_value("companies");
			if (Array.isArray(v) && v.length) return v[0];
			return frappe.defaults.get_user_default("Company");
		};

		// Populate the Account Hierarchy Level dropdown with 1..max-depth.
		const set_level_options = (company, report_type) => {
			const f = report.get_filter("account_level");
			if (!company || report_type === "Cash Flow") {
				if (f) {
					f.df.options = "";
					f.refresh();
				}
				return;
			}

			frappe.call({
				method:
					"avinashgroup_app.avinash_group_app.report.consolidated_financial_statement_hierarchy.consolidated_financial_statement_hierarchy.get_max_account_depth",
				args: { company, report: report_type || "Balance Sheet" },
				callback: function (r) {
					const max_depth = r.message || 1;
					const levels = [];
					for (let i = 1; i <= max_depth; i++) levels.push(String(i));
					if (f) {
						f.df.options = ["", ...levels].join("\n");
						f.refresh();
					}
				},
			});
		};

		set_level_options(get_depth_company(), report.get_filter_value("report"));

		report.get_filter("report").$input.on("change", function () {
			set_level_options(get_depth_company(), report.get_filter_value("report"));
		});
	},
};
