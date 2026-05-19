

frappe.query_reports["Monthly Attendance BS"] = {
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
			fieldname: "bs_year",
			label: __("BS Year"),
			fieldtype: "Int",
			default: _default_bs_year(),
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
			default: _default_bs_month(),
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

	onload: function (report) {
		_make_full_width(report);
	},

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data, { css: {} });
		if (!data) return value;

		if (column.fieldname === "status") {
			if (data.status === "Absent") {
				value = `<span style="color: var(--red-600); font-weight: 600;">${data.status}</span>`;
			} else if (data.status === "Half Day") {
				value = `<span style="color: var(--orange-600); font-weight: 600;">${data.status}</span>`;
			} else if (data.status === "Not Marked") {
				value = `<span style="color: var(--gray-500); font-style: italic;">${data.status}</span>`;
			} else if (data.status === "Present") {
				value = `<span style="color: var(--green-600);">${data.status}</span>`;
			}
		}

		if (column.fieldname === "remarks" && data.remarks) {
			value = `<span style="color: var(--text-muted); font-size: 0.9em;">${data.remarks}</span>`;
		}

		return value;
	},
};

function _make_full_width(report) {
	// Stretch every Frappe v15 layout wrapper so the wide grid uses the full viewport.
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
	// Also apply inline override on the current page in case CSS specificity is beaten.
	const $page = report && report.page ? report.page.wrapper : $(document.body);
	$page.find(".container, .layout-main-section, .layout-main-section-wrapper, .page-content").css({
		"max-width": "100%",
		"width": "100%",
	});
}

function _default_bs_year() {
	// Best-effort: current BS year from today's AD date.
	// Crude approximation — fine as a UI default; Python uses authoritative converter.
	const today = new Date();
	const year = today.getFullYear();
	const month = today.getMonth() + 1; // 1-12
	// Nepali new year falls in mid-April; before that, BS year = AD + 56, after = AD + 57
	return month < 4 || (month === 4 && today.getDate() < 14)
		? year + 56
		: year + 57;
}

function _default_bs_month() {
	// Approximate current BS month index. UI default only.
	const today = new Date();
	const m = today.getMonth() + 1;
	const d = today.getDate();
	// rough mapping AD → BS (mid-month transitions)
	const table = [
		[1, 9],   // Jan → Poush
		[2, 10],  // Feb → Magh
		[3, 11],  // Mar → Falgun
		[4, 12],  // Apr early → Chaitra; mid → Baisakh
		[5, 1],   // May → Baisakh/Jestha
		[6, 2],   // Jun → Jestha/Ashadh
		[7, 3],   // Jul → Ashadh/Shrawan
		[8, 4],   // Aug → Shrawan/Bhadra
		[9, 5],   // Sep → Bhadra/Ashwin
		[10, 6],  // Oct → Ashwin/Kartik
		[11, 7],  // Nov → Kartik/Mangsir
		[12, 8],  // Dec → Mangsir/Poush
	];
	const [, base] = table[m - 1];
	const bs = d > 15 ? (base % 12) + 1 : base;
	const names = [
		"Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
		"Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
	];
	return `${String(bs).padStart(2, "0")} - ${names[bs - 1]}`;
}
