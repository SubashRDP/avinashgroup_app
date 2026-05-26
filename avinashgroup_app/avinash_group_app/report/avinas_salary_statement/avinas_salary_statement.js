frappe.query_reports["Avinas Salary Statement"] = {
	onload: function(report) {
		_make_full_width(report);
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
			default: _default_bs_year(),
			description: __("e.g. 2082"),
			reqd: 1,
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
			reqd: 1,
		},
		{
			fieldname: "docstatus",
			label: __("Status"),
			fieldtype: "Select",
			options: ["1 - Submitted", "0 - Draft"].join("\n"),
			default: "1 - Submitted",
			reqd: 1,
		},
	],

	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data, { css: {} });
		if (data && data.bold) {
			value = `<strong>${value || ""}</strong>`;
		}
		return value;
	},
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

function _default_bs_year() {
	const today = new Date();
	const year = today.getFullYear();
	const month = today.getMonth() + 1;
	return month < 4 || (month === 4 && today.getDate() < 14)
		? year + 56
		: year + 57;
}

function _default_bs_month() {
	const today = new Date();
	const m = today.getMonth() + 1;
	const d = today.getDate();
	const table = [
		[1, 9], [2, 10], [3, 11], [4, 12],
		[5, 1], [6, 2], [7, 3], [8, 4],
		[9, 5], [10, 6], [11, 7], [12, 8],
	];
	const [, base] = table[m - 1];
	const bs = d > 15 ? (base % 12) + 1 : base;
	const names = [
		"Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
		"Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
	];
	return `${String(bs).padStart(2, "0")} - ${names[bs - 1]}`;
}
