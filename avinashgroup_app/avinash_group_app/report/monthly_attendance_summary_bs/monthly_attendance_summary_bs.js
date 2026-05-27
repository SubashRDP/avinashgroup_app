// Monthly Attendance Summary BS — filters mirror Monthly Attendance BS
// (BS Year + BS Month wins over AD range; AD range only used if BS is cleared).

frappe.query_reports["Monthly Attendance Summary BS"] = {
	onload: async function (report) {
		_make_full_width(report);
		_setup_bs_defaults(report);
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
			fieldname: "bs_year",
			label: __("BS Year"),
			fieldtype: "Int",
			description: __("e.g. 2082"),
		},
		{
			fieldname: "bs_month",
			label: __("BS Month"),
			fieldtype: "Select",
			options: [
				"",
				"01 - Baisakh",
				"02 - Jestha",
				"03 - Ashadh",
				"04 - Shrawan",
				"05 - Bhadra",
				"06 - Ashwin",
				"07 - Kartik",
				"08 - Mangsir",
				"09 - Poush",
				"10 - Magh",
				"11 - Falgun",
				"12 - Chaitra",
			].join("\n"),
		},
		{
			fieldname: "from_date",
			label: __("From Date (AD)"),
			fieldtype: "Date",
			description: __("Only used when BS Year + BS Month are cleared"),
		},
		{
			fieldname: "to_date",
			label: __("To Date (AD)"),
			fieldtype: "Date",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
			get_query: function () {
				const company = frappe.query_report.get_filter_value("company");
				return company ? { filters: { company: company } } : {};
			},
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
		},
		{
			fieldname: "designation",
			label: __("Designation"),
			fieldtype: "Link",
			options: "Designation",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
			get_query: function () {
				const company = frappe.query_report.get_filter_value("company");
				return company ? { filters: { company: company, status: "Active" } } : {};
			},
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["Active", "Inactive", "Suspended", "Left"].join("\n"),
			default: "Active",
		},
	],
};

function _make_full_width(report) {
	if (!$("#nepal-hrms-fullwidth-style").length) {
		$(
			'<style id="nepal-hrms-fullwidth-style">' +
			'.page-container, .page-content, .page-form, .page-body,' +
			' .layout-main, .layout-main-section, .layout-main-section-wrapper,' +
			' .container, .container-fluid, .container-xl, .container-lg, .container-md' +
			' { max-width: 100% !important; width: 100% !important; padding-left: 12px !important; padding-right: 12px !important; }' +
			'.dt-scrollable, .datatable, .datatable-wrapper, .report-wrapper, .query-report-container' +
			' { width: 100% !important; max-width: 100% !important; }' +
			'</style>'
		).appendTo("head");
	}
	const $page = report && report.page ? report.page.wrapper : $(document.body);
	$page.find(".container, .layout-main-section, .layout-main-section-wrapper, .page-content").css({
		"max-width": "100%",
		"width": "100%",
	});
}

function _setup_bs_defaults(report) {
	const nepaliMonths = [
		"Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
		"Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"
	];

	if (typeof window.NepaliFunctions === "undefined") {
		console.warn("⚠️ NepaliFunctions not loaded");
		return;
	}

	const today = new Date();
	const bsDate = window.NepaliFunctions.AD2BS({
		year: today.getFullYear(),
		month: today.getMonth() + 1,
		day: today.getDate()
	});

	const bsYear = Number(bsDate.year);
	const bsMonth = Number(bsDate.month);
	const bsMonthName = nepaliMonths[bsMonth - 1];
	const bsMonthFormatted = `${String(bsMonth).padStart(2, "0")} - ${bsMonthName}`;

	frappe.query_report.set_filter_value("bs_year", bsYear);
	frappe.query_report.set_filter_value("bs_month", bsMonthFormatted);
}
