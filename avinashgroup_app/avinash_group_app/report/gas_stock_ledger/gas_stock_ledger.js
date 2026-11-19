// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

const GAS_STOCK_LEDGER = "Gas Stock Ledger";
const GSL_METHOD =
	"avinashgroup_app.avinash_group_app.report.gas_stock_ledger.gas_stock_ledger.";

// Text colour per movement type, so a long ledger scans by eye.
const GSL_TYPE_COLOURS = {
	purchase: "var(--green-600)",
	purchase_return: "var(--orange-600)",
	sale: "var(--blue-600)",
	sale_return: "var(--orange-600)",
	other: "var(--gray-600)",
};

frappe.query_reports[GAS_STOCK_LEDGER] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
			on_change: function (report) {
				// item and warehouses belong to a company; carry-overs would empty the report
				report.set_filter_value("warehouse", []);
				frappe.query_reports[GAS_STOCK_LEDGER].set_default_item(report, true);
			},
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			reqd: 1,
			get_query: function () {
				return {
					filters: {
						is_stock_item: 1,
						disabled: 0,
						custom_company: frappe.query_report.get_filter_value("company"),
					},
				};
			},
		},
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			reqd: 1,
			options: [
				"Detail",
				"Daily Summary",
				"Monthly Summary (BS)",
				"Stock Book (मौज्दात खाता)",
			].join("\n"),
			default: "Detail",
		},
		{
			fieldname: "unit",
			label: __("Show Quantity In"),
			fieldtype: "Select",
			options: "MT\nKg",
			default: "MT",
		},
		{
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
			on_change: function (report) {
				frappe.query_reports[GAS_STOCK_LEDGER].apply_period(report);
			},
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			on_change: function (report) {
				if (report.get_filter_value("period_preset") === "Fiscal Year") {
					frappe.query_reports[GAS_STOCK_LEDGER].apply_period(report);
				}
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
			default: frappe.datetime.get_today(),
		},
		{
			// Purchases and sales live in two warehouses that never transfer,
			// so the company's gas only makes sense as one pool.
			fieldname: "warehouse_mode",
			label: __("Warehouses"),
			fieldtype: "Select",
			options: "Pooled (Company)\nBy Warehouse",
			default: "Pooled (Company)",
		},
		{
			fieldname: "warehouse",
			label: __("Only Warehouses"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Warehouse", txt, {
					company: frappe.query_report.get_filter_value("company"),
					is_group: 0,
				});
			},
		},
		{
			// display filters: they choose the rows shown, the Balance stays the true stock
			fieldname: "voucher_category",
			label: __("Movement"),
			fieldtype: "Select",
			options: [
				"",
				"Purchase",
				"Purchase Return",
				"Sale",
				"Sale Return",
				"Transfer / Adjustment",
			].join("\n"),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
		},
		{
			fieldname: "show_cylinders",
			label: __("Cylinder Columns"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "show_value",
			label: __("Show Value"),
			fieldtype: "Check",
			default: 1,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (data.is_heading) {
			return `<b style="color: var(--heading-color)">${value}</b>`;
		}
		if (column.fieldname === "type" && data.category && value) {
			value = `<span style="color:${GSL_TYPE_COLOURS[data.category]};font-weight:500">${value}</span>`;
		}
		if (
			["balance_qty", "closing_qty", "opening_qty", "balance_value", "closing_value"].includes(
				column.fieldname
			) &&
			data[column.fieldname] < 0
		) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		if (data.bold) {
			value = `<b>${value}</b>`;
		}
		return value;
	},

	// Show only the date fields the chosen Period needs, and resolve its dates
	// (BS month and quarter boundaries, same presets as Custom Ledger).
	apply_period: function (report) {
		const preset = report.get_filter_value("period_preset") || "This Month";
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

	// Open on the company's LP Gas item -- it is what everyone asks about.
	set_default_item: function (report, replace) {
		const company = report.get_filter_value("company");
		if (!company || (!replace && report.get_filter_value("item_code"))) return;
		frappe
			.call({ method: GSL_METHOD + "get_default_item", args: { company: company } })
			.then((r) => report.set_filter_value("item_code", r.message || ""));
	},

	onload: function (report) {
		frappe.query_reports[GAS_STOCK_LEDGER].apply_period(report);
		frappe.query_reports[GAS_STOCK_LEDGER].set_default_item(report, false);
	},
};
