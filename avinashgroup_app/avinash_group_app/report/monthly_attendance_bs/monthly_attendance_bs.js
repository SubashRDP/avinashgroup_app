

frappe.query_reports["Monthly Attendance BS"] = {
	onload: async function (report) {
		_make_full_width(report);
		_setup_fiscal_year_visibility(report);
		await _init_default_fiscal_year(report);
	},

	filters: [
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: ["Detail", "Summary"].join("\n"),
			default: "Detail",
			reqd: 1,
		},
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

		const f = column.fieldname;

		// --- shared: a zero in an exception column is good news, so mute it ---
		const muteZero = (v) =>
			`<span style="color: var(--text-lighter)">—</span>`;

		// --- Detail view -------------------------------------------------
		if (f === "status") {
			return _chip(data.status);
		}

		if (f === "late_minutes" || f === "before_office_minutes") {
			const n = cint(data[f]);
			if (!n) return muteZero();
			// 15 minutes is the grace period on every shift; past it, it counts.
			const tone = n > 15 ? "var(--red-600)" : "var(--orange-600)";
			return `<span style="color:${tone};font-weight:600">${n}</span>`;
		}

		if (f === "working_hours") {
			if (!data.working_hours || data.working_hours === "00:00") return muteZero();
			return `<span style="font-weight:600">${data.working_hours}</span>`;
		}

		if (f === "in_time" || f === "out_time") {
			if (!data[f]) {
				// A missing OUT is the single most common data fault — name it.
				return `<span style="color:var(--red-500)" title="${__("No punch recorded")}">— —</span>`;
			}
			return value;
		}

		if (f === "work_in_holiday" && cint(data.work_in_holiday)) {
			return `<span style="color:var(--purple-600);font-weight:600">${__("Holiday")}</span>`;
		}

		if (f === "remarks" && data.remarks) {
			return `<span style="color:var(--text-muted);font-size:.9em">${data.remarks}</span>`;
		}

		// --- Summary view ------------------------------------------------
		if (f === "ot_hours") {
			const n = flt(data.ot_hours);
			if (!n) return muteZero();
			return `<span style="color:var(--blue-600);font-weight:600">${format_number(n, null, 2)}</span>`;
		}

		if (f === "present_days") {
			const n = flt(data.present_days);
			// A quiet proportional bar behind the number: the column becomes
			// scannable without anyone having to read every figure.
			const pct = Math.max(0, Math.min(100, (n / 31) * 100));
			return `
				<div style="position:relative">
					<div style="position:absolute;inset:0;width:${pct}%;
						background:var(--green-100);border-radius:2px"></div>
					<span style="position:relative;font-weight:600">${format_number(n, null, 1)}</span>
				</div>`;
		}

		if (f === "worked_on_holiday") {
			const n = cint(data.worked_on_holiday);
			if (!n) return muteZero();
			return `<span style="color:var(--purple-600);font-weight:600">${n}</span>`;
		}

		if (f === "leave_current" || f === "leave_previous" || f === "leave_upto") {
			if (!flt(data[f])) return muteZero();
			return value;
		}

		return value;
	},

	get_datatable_options(options) {
		return Object.assign(options, {
			checkboxColumn: false,
			cellHeight: 34,
		});
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


// Status as a chip rather than coloured text: at a glance the eye picks out
// the blocks of colour, not the words.
function _chip(status) {
	if (!status) return "";
	const tones = {
		Present: ["var(--green-600)", "var(--green-50)"],
		"Work From Home": ["var(--green-600)", "var(--green-50)"],
		"Half Day": ["var(--orange-700)", "var(--orange-50)"],
		"On Leave": ["var(--blue-600)", "var(--blue-50)"],
		Absent: ["var(--red-600)", "var(--red-50)"],
		Holiday: ["var(--purple-600)", "var(--purple-50)"],
	};
	const [fg, bg] = tones[status] || ["var(--text-muted)", "var(--bg-light-gray)"];
	const italic = status === "Not Marked" ? "font-style:italic;" : "";
	return `<span style="color:${fg};background:${bg};${italic}
		padding:2px 8px;border-radius:10px;font-size:.85em;font-weight:600;
		white-space:nowrap">${status}</span>`;
}
