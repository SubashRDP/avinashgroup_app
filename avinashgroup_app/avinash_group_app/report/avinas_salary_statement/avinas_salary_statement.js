// The salary sheet, from the slips (see avinas_salary_statement.py). The month
// is chosen as on the Payroll Entry: Fiscal Year + BS Month, defaulting to the
// last finished month (hr/bs_calendar.py).

const SALARY_SHEET_MONTHS = [
	"04 - Shrawan", "05 - Bhadra", "06 - Ashwin", "07 - Kartik", "08 - Mangsir", "09 - Poush",
	"10 - Magh", "11 - Falgun", "12 - Chaitra", "01 - Baisakh", "02 - Jestha", "03 - Ashadh",
];

frappe.query_reports["Avinas Salary Statement"] = {
	onload(report) {
		salary_sheet_full_width();
		frappe.call({
			method: "avinashgroup_app.hr.bs_calendar.get_default_month",
			args: { company: frappe.query_report.get_filter_value("company") },
			callback: (r) => {
				if (!r.message) return;
				if (!frappe.query_report.get_filter_value("fiscal_year")) {
					frappe.query_report.set_filter_value({
						fiscal_year: r.message.fiscal_year,
						bs_month: r.message.bs_month,
					});
				}
			},
		});
	},

	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
		},
		{
			fieldname: "bs_month",
			label: __("BS Month"),
			fieldtype: "Select",
			options: SALARY_SHEET_MONTHS.join("\n"),
		},
		{
			fieldname: "payroll_entry",
			label: __("Payroll Entry"),
			fieldtype: "Link",
			options: "Payroll Entry",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company"), docstatus: ["<", 2] },
			}),
		},
		{
			fieldname: "docstatus",
			label: __("Slips"),
			fieldtype: "Select",
			options: ["1 - Submitted", "0 - Draft"].join("\n"),
			default: "1 - Submitted",
			reqd: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.bold) value = `<strong>${value || ""}</strong>`;
		return value;
	},
};

// Full width for this report only: every rule is scoped to the page's route
// (Frappe sets body[data-route]), so it cannot leak onto the next page opened.
// A global !important style stayed on every page until a reload.
const SALARY_SHEET_ROUTE = 'body[data-route="query-report/Avinas Salary Statement"]';

function salary_sheet_full_width() {
	if ($("#avinas-salary-sheet-width").length) return;
	const scoped = (selectors) => selectors.map((sel) => `${SALARY_SHEET_ROUTE} ${sel}`).join(", ");
	$(
		`<style id="avinas-salary-sheet-width">
		${scoped([".page-container", ".page-content", ".page-body", ".layout-main", ".layout-main-section",
			".layout-main-section-wrapper", ".container", ".container-fluid"])}
		{ max-width: 100% !important; width: 100% !important; padding-left: 12px !important; padding-right: 12px !important; }
		</style>`
	).appendTo("head");
}
