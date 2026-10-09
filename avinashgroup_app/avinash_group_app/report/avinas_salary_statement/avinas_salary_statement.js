// The salary sheet, from the slips (see avinas_salary_statement.py). The month
// is chosen as on the Payroll Entry: Fiscal Year + BS Month, defaulting to the
// last finished month (hr/bs_calendar.py).

const SALARY_SHEET_MONTHS = [
	"04 - Shrawan", "05 - Bhadra", "06 - Ashwin", "07 - Kartik", "08 - Mangsir", "09 - Poush",
	"10 - Magh", "11 - Falgun", "12 - Chaitra", "01 - Baisakh", "02 - Jestha", "03 - Ashadh",
];

frappe.query_reports["Avinas Salary Statement"] = {
	onload(report) {
		_make_full_width(report);
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

function _make_full_width(report) {
	if (!$("#nepal-hrms-fullwidth-style").length) {
		$(
			'<style id="nepal-hrms-fullwidth-style">' +
			".page-container, .page-content, .page-form, .page-body," +
			" .layout-main, .layout-main-section, .layout-main-section-wrapper," +
			" .container, .container-fluid, .container-xl, .container-lg, .container-md" +
			" { max-width: 100% !important; width: 100% !important; padding-left: 12px !important; padding-right: 12px !important; }" +
			".dt-scrollable, .datatable, .datatable-wrapper, .report-wrapper, .query-report-container" +
			" { width: 100% !important; max-width: 100% !important; }" +
			"</style>"
		).appendTo("head");
	}
	const $page = report && report.page ? report.page.wrapper : $(document.body);
	$page.find(".container, .layout-main-section, .layout-main-section-wrapper, .page-content").css({
		"max-width": "100%",
		width: "100%",
	});
}
