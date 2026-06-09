

frappe.query_reports["Monthly Attendance BS"] = {
	onload: async function (report) {
		_make_full_width(report);
		_setup_fiscal_year_visibility(report);
		await _init_default_fiscal_year(report);
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
			description: __("BS fiscal year, e.g. 82/83 covering Shrawan 2082 to Ashad 2083."),
		},
		{
			fieldname: "bs_month",
			label: __("BS Month"),
			fieldtype: "Select",
			options: [
				"",
				"04 - Shrawan",
				"05 - Bhadra",
				"06 - Ashwin",
				"07 - Kartik",
				"08 - Mangsir",
				"09 - Poush",
				"10 - Magh",
				"11 - Falgun",
				"12 - Chaitra",
				"01 - Baisakh",
				"02 - Jestha",
				"03 - Ashadh",
			].join("\n"),
			default: _default_bs_month(),
			description: __("Listed in fiscal-year order: Shrawan → Ashadh."),
		},
		{
			fieldname: "from_date",
			label: __("From Date (AD)"),
			fieldtype: "Date",
			description: __("Only used when Fiscal Year + BS Month are cleared"),
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

async function _init_default_fiscal_year(report) {
	if (typeof window.FiscalYearCache === "undefined") {
		console.warn("⚠️ FiscalYearCache not loaded");
		return;
	}

	const fy = await window.FiscalYearCache.getDefaultFiscalYear();
	if (fy) {
		frappe.query_report.set_filter_value("fiscal_year", fy);
		frappe.query_report.set_filter_value("bs_month", _default_bs_month());
	}
}

function _setup_fiscal_year_visibility(report) {
	// BS mode (fiscal_year + bs_month) and AD mode (from_date + to_date) are
	// mutually exclusive — populating one mode nulls out the other.
	let _syncing = false;

	const clearFilters = (fieldnames) => {
		fieldnames.forEach((fn) => {
			if (frappe.query_report.get_filter_value(fn)) {
				frappe.query_report.set_filter_value(fn, "");
			}
		});
	};

	const enforceExclusivity = (changedField) => {
		if (_syncing) return;
		_syncing = true;
		try {
			if (changedField === "fiscal_year" || changedField === "bs_month") {
				// Picking a BS field clears the AD date range.
				if (frappe.query_report.get_filter_value(changedField)) {
					clearFilters(["from_date", "to_date"]);
				}
			} else if (changedField === "from_date" || changedField === "to_date") {
				// Picking an AD date clears the BS fiscal year + month.
				if (frappe.query_report.get_filter_value(changedField)) {
					clearFilters(["fiscal_year", "bs_month"]);
				}
			}
		} finally {
			_syncing = false;
		}
	};

	const updateADVisibility = () => {
		const hasFY = frappe.query_report.get_filter_value("fiscal_year");
		const hasBSMonth = frappe.query_report.get_filter_value("bs_month");
		const useAD = !hasFY || !hasBSMonth;

		const $fromDate = $(`.frappe-control[data-fieldname="from_date"]`);
		const $toDate = $(`.frappe-control[data-fieldname="to_date"]`);

		if (useAD) {
			$fromDate.show().removeClass("hide");
			$toDate.show().removeClass("hide");
		} else {
			$fromDate.hide().addClass("hide");
			$toDate.hide().addClass("hide");
		}
	};

	updateADVisibility();

	frappe.query_report.page.wrapper.on("change", ".report-filters input, .report-filters select", (e) => {
		const changedField = $(e.target).closest(".frappe-control").attr("data-fieldname");
		setTimeout(() => {
			enforceExclusivity(changedField);
			updateADVisibility();
		}, 100);
	});
}

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

function _default_bs_month() {
	// Current BS month, derived from today's AD date via the accurate
	// NepaliFunctions.AD2BS converter (same one the BS month picker uses).
	// UI default only.
	if (typeof window.NepaliFunctions === "undefined") {
		console.warn("⚠️ NepaliFunctions not loaded — leaving BS Month blank");
		return "";
	}

	const today = new Date();
	const bsDate = window.NepaliFunctions.AD2BS({
		year: today.getFullYear(),
		month: today.getMonth() + 1,
		day: today.getDate(),
	});

	const bs = Number(bsDate.month);
	const names = [
		"Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
		"Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
	];
	return `${String(bs).padStart(2, "0")} - ${names[bs - 1]}`;
}
