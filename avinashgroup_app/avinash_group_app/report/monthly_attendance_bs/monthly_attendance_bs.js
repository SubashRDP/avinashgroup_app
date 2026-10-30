

const REPORT_MODULE =
	"avinashgroup_app.avinash_group_app.report.monthly_attendance_bs.monthly_attendance_bs";

// Server side of the First IN / Last OUT correction. The roles mirror its
// CORRECTION_ROLES; the server checks them again, this only hides the pencil.
const CORRECT_DAY_METHOD = "avinashgroup_app.hr.punch_correction.correct_day";
const CORRECTION_ROLES = ["HR Manager", "System Manager"];
// Late Excused from the grid (hr/late_excuse.py); the Attendance enforces the rules.
const LATE_EXCUSE_METHOD = "avinashgroup_app.hr.late_excuse.set_late_excuse";

frappe.query_reports["Monthly Attendance BS"] = {
	onload: async function (report) {
		_apply_theme(report);
		_bind_punch_correction(report);
		_bind_late_excuse(report);
		report.page.add_inner_button(__("Correction Log"), () => _open_correction_log());
		if (frappe.user.has_role(CORRECTION_ROLES)) {
			report.page.add_inner_button(__("Give Leave"), () => _open_give_leave_dialog());
		}
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
			description: __("Filled from the BS Month. Edit to use an AD range instead."),
		},
		{
			fieldname: "to_date",
			label: __("To Date (AD)"),
			fieldtype: "Date",
		},
		{
			fieldname: "shift",
			label: __("Shift"),
			fieldtype: "Link",
			options: "Shift Type",
			get_query: function () {
				const company = frappe.query_report.get_filter_value("company");
				return company ? { filters: { custom_company: company } } : {};
			},
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

		// Name over ID in one clickable cell — see NepalHR.employeeCell.
		if (f === "employee") {
			const cell = window.NepalHR && window.NepalHR.employeeCell(data);
			if (cell) return cell;
		}

		// --- shared: a zero in an exception column is good news, so mute it ---
		const muteZero = (v) =>
			`<span style="color: var(--text-lighter)">—</span>`;

		// --- Detail view -------------------------------------------------
		if (f === "status") {
			if (data.leave_note) {
				// Leave HR gave from this report, set apart from leave applied for.
				return `<span title="${frappe.utils.escape_html(data.leave_note)}"
					style="${EDITED_CELL_STYLE}">${_chip(data.status)}
					<span style="color:#A07A1C;margin-left:4px;font-size:.8em">✎ ${__("given")}</span></span>`;
			}
			return _chip(data.status);
		}

		if (f === "late_minutes" || f === "before_office_minutes") {
			const n = cint(data[f]);
			if (!n) return muteZero();
			// 15 minutes is the grace period on every shift; past it, it counts.
			const tone = n > 15 ? "#A64E5B" : "#96662A";
			return `<span style="color:${tone};font-weight:600">${n}</span>`;
		}

		if (f === "late_excused") {
			return _late_excuse_cell(data);
		}

		if (f === "working_hours") {
			if (!data.working_hours || data.working_hours === "00:00") return muteZero();
			return `<span style="font-weight:600">${data.working_hours}</span>`;
		}

		if (f === "in_time" || f === "out_time") {
			return _punch_cell(f, value, data);
		}

		if (f === "shift") {
			return _shift_cell(value, data);
		}

		if (f === "work_in_holiday" && cint(data.work_in_holiday)) {
			return `<span style="color:#70569C;font-weight:600">${__("Holiday")}</span>`;
		}

		if (f === "remarks" && data.remarks) {
			// Status, hours and late minutes come from an attendance that left a
			// punch out; say so in the warning colour, not the muted one.
			const color = cint(data.marked_off_punches) ? "#A64E5B" : "var(--text-muted)";
			return `<span style="color:${color};font-size:.9em" title="${frappe.utils.escape_html(data.remarks)}">${data.remarks}</span>`;
		}

		// --- Summary view ------------------------------------------------
		if (f === "ot_hours") {
			const n = flt(data.ot_hours);
			if (!n) return muteZero();
			// Four decimals, as the column and the salary statement: overtime is
			// exact to the second, and hours × rate must reproduce the amount.
			return `<span style="color:#3E7290;font-weight:600">${format_number(n, null, 4)}</span>`;
		}

		if (f === "present_days") {
			const n = flt(data.present_days);
			// A quiet proportional bar behind the number: the column becomes
			// scannable without anyone having to read every figure.
			const pct = Math.max(0, Math.min(100, (n / 31) * 100));
			return `
				<div style="position:relative">
					<div style="position:absolute;inset:0;width:${pct}%;
						background:#DCEAE0;border-radius:3px"></div>
					<span style="position:relative;font-weight:600">${format_number(n, null, 1)}</span>
				</div>`;
		}

		if (f === "worked_on_holiday") {
			const n = cint(data.worked_on_holiday);
			if (!n) return muteZero();
			return `<span style="color:#70569C;font-weight:600">${n}</span>`;
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
			// Roomier than the stock 28px. This grid is read across for minutes
			// a row, not skimmed, and the extra height is what makes that
			// bearable at 15px type.
			cellHeight: 42,
		});
	},

	after_datatable_render(datatable) {
		// The datatable is still settling its column widths when this fires —
		// measuring now reads the pre-layout numbers and the frozen block ends
		// up offset from the body on the first render, then corrects itself on
		// any later one. Measure after the browser has laid the grid out, and
		// again once more in case a web font or scrollbar shifts it.
		requestAnimationFrame(() => {
			_freeze_leading_columns(datatable);
			setTimeout(() => _freeze_leading_columns(datatable), 120);
		});
		_bind_arrow_key_scrolling(datatable);
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
	// BS month and AD range are two views of the same period, not two modes.
	// Picking a BS month used to CLEAR the AD dates and hide both fields, so
	// there was no way to see which English dates a Nepali month covered.
	// Now the BS pair fills the AD dates in and leaves them visible; typing an
	// AD date instead clears the BS pair, so whichever was touched last wins.
	//
	// The dates come from the server's own resolver rather than being derived
	// here, so the filters show exactly what the report will use — including a
	// Nepal BS Period company override, which can move a month boundary off
	// the calendar one.
	//
	// Echo detection, not a busy flag: filter changes arrive through a 100ms
	// debounce, so a synchronous "we are writing" flag is already false by the
	// time our own write comes back — and the handler then read the autofilled
	// date as a hand-typed one and cleared the month the user had just picked.
	// Remembering what we wrote survives the gap; a flag cannot.
	let written = { from_date: null, to_date: null };

	const value = (fn) => frappe.query_report.get_filter_value(fn);

	const fillDatesFromBS = () => {
		const fiscal_year = value("fiscal_year");
		const bs_month = value("bs_month");
		if (!fiscal_year || !bs_month) return;

		frappe.call({
			method: REPORT_MODULE + ".get_ad_range",
			args: { fiscal_year, bs_month, company: value("company") },
			callback: (r) => {
				if (!r.message) return;
				// Still the same month by the time the call came back?
				if (value("fiscal_year") !== fiscal_year || value("bs_month") !== bs_month) return;

				written = { from_date: r.message.from_date, to_date: r.message.to_date };
				// One object, one refresh — set_filter_value suppresses the
				// reload until the last key, so the report does not run twice.
				frappe.query_report.set_filter_value(written);
			},
		});
	};

	const onFilterChange = (changed) => {
		if (changed === "fiscal_year" || changed === "bs_month" || changed === "company") {
			fillDatesFromBS();
			return;
		}

		if (changed === "from_date" || changed === "to_date") {
			// Our own autofill echoing back — leave the BS pair alone.
			if (value(changed) === written[changed]) return;

			// A hand-typed AD date means an explicit range: drop the BS pair,
			// which the server checks first and would otherwise prefer.
			written = { from_date: null, to_date: null };
			["fiscal_year", "bs_month"].forEach((fn) => {
				if (value(fn)) frappe.query_report.set_filter_value(fn, "");
			});
		}
	};

	fillDatesFromBS();

	frappe.query_report.page.wrapper.on(
		"change",
		".report-filters input, .report-filters select",
		(e) => {
			const changed = $(e.target).closest(".frappe-control").attr("data-fieldname");
			setTimeout(() => onFilterChange(changed), 100);
		}
	);
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


// ---------------------------------------------------------------------------
// First IN / Last OUT correction
// ---------------------------------------------------------------------------
//
// HR fixes a missed or wrong punch from the cell it shows up in. The server
// (hr/punch_correction.py) moves or adds the punches and re-marks the day's
// attendance in one transaction; this side only collects the two times and a
// reason, and refreshes the grid so the new hours, status and allowances show.
//
// A corrected time is never allowed to look like a device reading: its cell
// is tinted amber with a pencil mark, and the tooltip says what the device
// read, who changed it, when and why. The marker lives on the punch, so it
// survives a refresh and any later rebuild of the attendance.

const EDITED_CELL_STYLE =
	"background:#FCF3DC;box-shadow:inset 3px 0 0 #C9A227;border-radius:3px;padding:2px 6px;";

function _can_correct(data) {
	if (!data || !data.employee || !data.ad_date) return false;
	if (!frappe.user.has_role(CORRECTION_ROLES)) return false;
	// Today's attendance is still being marked; the server refuses it too.
	return String(data.ad_date) < frappe.datetime.get_today();
}

function _punch_cell(f, value, data) {
	const note = f === "in_time" ? data.in_edit_note : data.out_edit_note;
	const editable = _can_correct(data);
	const attrs = editable
		? `class="mab-punch-edit" data-employee="${frappe.utils.escape_html(data.employee)}"
			data-date="${data.ad_date}" style="cursor:pointer"`
		: "";
	const pencil = editable
		? `<span class="mab-pencil" style="color:var(--text-light);margin-left:6px;font-size:.8em">✎</span>`
		: "";

	if (!data[f]) {
		// A missing OUT is the single most common data fault — name it.
		const hint = editable ? __("No punch recorded. Click to add it.") : __("No punch recorded");
		return `<span ${attrs} title="${hint}"><span style="color:#A64E5B">— —</span>${pencil}</span>`;
	}
	if (note) {
		return `<span ${attrs} title="${frappe.utils.escape_html(note)}"
			style="${EDITED_CELL_STYLE}${editable ? "cursor:pointer;" : ""}"
			><span style="font-weight:600;color:#7A5B12">${value}</span>
			<span style="color:#A07A1C;margin-left:4px;font-size:.8em">✎ ${__("edited")}</span></span>`;
	}
	return editable
		? `<span ${attrs} title="${__("Click to correct First IN / Last OUT")}">${value}${pencil}</span>`
		: value;
}

function _shift_cell(value, data) {
	const editable = _can_correct(data);
	const attrs = editable
		? `class="mab-punch-edit" data-employee="${frappe.utils.escape_html(data.employee)}"
			data-date="${data.ad_date}"`
		: "";
	const label = frappe.utils.escape_html(data.shift || "");
	if (data.shift_edit_note) {
		return `<span ${attrs} title="${frappe.utils.escape_html(data.shift_edit_note)}"
			style="${EDITED_CELL_STYLE}${editable ? "cursor:pointer;" : ""}"
			><span style="font-weight:600;color:#7A5B12">${label}</span>
			<span style="color:#A07A1C;margin-left:4px;font-size:.8em">✎ ${__("changed")}</span></span>`;
	}
	if (!editable) return value;
	return `<span ${attrs} style="cursor:pointer" title="${__("Click to correct this day's shift")}">${label || "—"}<span
		style="color:var(--text-light);margin-left:6px;font-size:.8em">✎</span></span>`;
}

// ---------------------------------------------------------------------------
// Give Leave — approved Leave Applications for chosen days (hr/leave_from_report)
// ---------------------------------------------------------------------------
//
// For leave nobody applied for: HR picks the employee, the days and the type,
// sees the balance and what HRMS will deduct, and gives it. The server files
// one approved Leave Application per run of consecutive days, so balance,
// ledger and payroll follow HRMS's own rules.

const LEAVE_METHOD = "avinashgroup_app.hr.leave_from_report";
// A month and a bit: enough for a long absence, short enough to tick through.
const MAX_LEAVE_RANGE_DAYS = 62;

function _open_give_leave_dialog() {
	const filter = (fn) => frappe.query_report.get_filter_value(fn);
	let types = [];

	const d = new frappe.ui.Dialog({
		title: __("Give Leave"),
		size: "large",
		fields: [
			{
				fieldtype: "Link",
				fieldname: "employee",
				label: __("Employee"),
				options: "Employee",
				reqd: 1,
				default: filter("employee") || "",
				get_query: () => {
					const company = filter("company");
					return company ? { filters: { company, status: "Active" } } : {};
				},
				onchange: () => loadTypes(),
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Select",
				fieldname: "leave_type",
				label: __("Leave Type"),
				reqd: 1,
				options: [],
				onchange: () => refreshPreview(),
			},
			{ fieldtype: "Section Break" },
			{ fieldtype: "Date", fieldname: "from_date", label: __("From"), reqd: 1, onchange: () => buildDays() },
			{ fieldtype: "Column Break" },
			{ fieldtype: "Date", fieldname: "to_date", label: __("To"), reqd: 1, onchange: () => buildDays() },
			{ fieldtype: "Section Break", label: __("Days") },
			{
				fieldtype: "MultiCheck",
				fieldname: "days",
				columns: 4,
				options: [],
				on_change: () => refreshPreview(),
			},
			{ fieldtype: "Section Break" },
			{ fieldtype: "Check", fieldname: "half_day", label: __("Half Day"), onchange: () => refreshPreview() },
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Date",
				fieldname: "half_day_date",
				label: __("Half Day Date"),
				depends_on: "half_day",
				onchange: () => refreshPreview(),
			},
			{ fieldtype: "Section Break" },
			{ fieldtype: "HTML", fieldname: "preview" },
			{
				fieldtype: "Small Text",
				fieldname: "reason",
				label: __("Reason"),
				reqd: 1,
				description: __("Required. Kept on the leave and in the Attendance Correction Log."),
			},
		],
		primary_action_label: __("Give Leave"),
		primary_action(values) {
			const days = chosenDays();
			if (!days.length) {
				frappe.msgprint(__("Choose at least one day."));
				return;
			}
			d.disable_primary_action();
			frappe
				.call({
					method: `${LEAVE_METHOD}.give_leave`,
					type: "POST",
					args: {
						employee: values.employee,
						leave_type: values.leave_type,
						dates: JSON.stringify(days),
						half_day_date: values.half_day ? values.half_day_date : null,
						reason: values.reason,
					},
					freeze: true,
					freeze_message: __("Giving leave..."),
				})
				.then((r) => {
					d.hide();
					const m = r.message || {};
					const lines = (m.made || []).map(
						(x) =>
							`${frappe.utils.get_form_link("Leave Application", x.leave_application, true)}: ${x.from}${
								x.to !== x.from ? " → " + x.to : ""
							}, ${x.days} ${__("day(s)")} (${__("was")} ${x.was})`
					);
					(m.warnings || []).forEach((w) => lines.push(`<span style="color:#96662A">⚠ ${w}</span>`));
					frappe.msgprint({ title: __("Leave Given"), message: lines.join("<br>"), indicator: "green" });
					frappe.query_report.refresh();
				})
				.always(() => d.enable_primary_action());
		},
	});

	const chosenDays = () => d.fields_dict.days.get_checked_options();

	function buildDays() {
		const from = d.get_value("from_date");
		const to = d.get_value("to_date");
		let options = [];
		if (from && to && to >= from) {
			const span = frappe.datetime.get_day_diff(to, from) + 1;
			if (span > MAX_LEAVE_RANGE_DAYS) {
				frappe.msgprint(__("Choose at most {0} days at a time.", [MAX_LEAVE_RANGE_DAYS]));
			} else {
				for (let i = 0; i < span; i++) {
					const day = frappe.datetime.add_days(from, i);
					const weekday = moment(day).format("ddd");
					options.push({ label: `${day} ${weekday}`, value: day, checked: 1 });
				}
			}
		}
		d.fields_dict.days.df.options = options;
		d.fields_dict.days.refresh();
		loadTypes();
	}

	function loadTypes() {
		const employee = d.get_value("employee");
		const from = d.get_value("from_date");
		if (!employee || !from) return refreshPreview();
		frappe.call({
			method: `${LEAVE_METHOD}.leave_types_for`,
			args: { employee, on_date: from },
			callback: (r) => {
				types = r.message || [];
				const current = d.get_value("leave_type");
				d.set_df_property("leave_type", "options", types.map((t) => t.leave_type));
				if (current && types.some((t) => t.leave_type === current)) d.set_value("leave_type", current);
				refreshPreview();
			},
		});
	}

	function refreshPreview() {
		const wrapper = d.fields_dict.preview.$wrapper;
		const employee = d.get_value("employee");
		const leave_type = d.get_value("leave_type");
		const days = chosenDays();
		if (!employee || !leave_type || !days.length) {
			wrapper.html(`<div class="text-muted">${__("Pick the employee, leave type and days to see the balance.")}</div>`);
			return;
		}
		frappe.call({
			method: `${LEAVE_METHOD}.preview`,
			args: {
				employee,
				leave_type,
				dates: JSON.stringify(days),
				half_day_date: d.get_value("half_day") ? d.get_value("half_day_date") : null,
			},
			callback: (r) => {
				const p = r.message || {};
				const balance = p.is_lwp ? __("no balance needed (Leave Without Pay)") : `${p.balance}`;
				const holidays = p.include_holiday
					? __("holidays inside the days count as leave")
					: __("holidays inside the days are not counted");
				const after = p.is_lwp ? "" : ` · ${__("after")}: <b>${(p.balance - p.deduct).toFixed(2)}</b>`;
				const runs = (p.runs || []).map((x) => (x.from === x.to ? x.from : `${x.from} → ${x.to}`)).join(", ");
				const warn = p.deduct <= 0 ? `<li>${__("Every chosen day is a holiday for this type, so HRMS will refuse it.")}</li>` : "";
				wrapper.html(`
					<div style="padding:8px 10px;background:#FAF6EC;border-left:3px solid #C9A227;margin-bottom:10px">
						<div>${__("Balance")}: <b>${balance}</b> · ${__("this uses")}: <b>${p.deduct}</b> ${__("day(s)")}${after}</div>
						<div class="text-muted" style="font-size:.9em">${holidays}. ${__("One Leave Application per run")}: ${runs}</div>
						<ul style="margin:6px 0 0 16px;color:#96662A">${warn}${(p.notes || []).map((n) => `<li>${n}</li>`).join("")}</ul>
					</div>`);
			},
		});
	}

	d.show();
	refreshPreview();
}

// The Attendance Correction Log, narrowed to what the report shows.
function _open_correction_log(employee, date) {
	const value = (fn) => frappe.query_report.get_filter_value(fn);
	const filters = {};
	const who = employee || value("employee");
	if (who) filters.employee = who;
	if (date) {
		filters.attendance_date = date;
	} else if (value("from_date") && value("to_date")) {
		filters.attendance_date = ["between", [value("from_date"), value("to_date")]];
	}
	frappe.set_route("List", "Attendance Correction Log", filters);
}

function _bind_punch_correction(report) {
	// Delegated, so it outlives every datatable rebuild without re-binding.
	report.page.wrapper.off("click.mab-punch").on("click.mab-punch", ".mab-punch-edit", (e) => {
		const $cell = $(e.currentTarget);
		const employee = $cell.attr("data-employee");
		const date = $cell.attr("data-date");
		const row = (frappe.query_report.data || []).find(
			(r) => r.employee === employee && String(r.ad_date) === date
		);
		if (row) _open_correction_dialog(row);
	});
}

function _open_correction_dialog(row) {
	const name = row.employee_name || row.employee;
	const shown = (v) => v || __("none");
	const d = new frappe.ui.Dialog({
		title: __("Correct Attendance"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "intro",
				options: `<div style="margin-bottom:10px">
					<div style="font-weight:600">${frappe.utils.escape_html(name)} · ${row.bs_date} (${row.ad_date})</div>
					<div class="text-muted" style="margin-top:4px">
						${__("Now")}: ${__("IN")} ${shown(row.in_time)}, ${__("OUT")} ${shown(row.out_time)},
						${frappe.utils.escape_html(row.status || "")}
					</div>
					<div style="margin-top:8px;padding:8px 10px;background:#FAF6EC;border-left:3px solid #C9A227;font-size:.92em">
						${__("Change the punch times, the shift, or both. Saving moves the day's first and last punch (or adds a missing one) and/or puts the day on the chosen shift, then re-marks the attendance and any approved overtime. Every change is recorded with your reason in the Attendance Correction Log, and the cells stay highlighted.")}
						<a href="#" class="mab-log-link" style="margin-left:4px">${__("View this day's log")}</a>
					</div>
				</div>`,
			},
			{ fieldtype: "Section Break", label: __("Punches") },
			{
				fieldtype: "Time",
				fieldname: "in_time",
				label: __("First IN"),
				default: row.in_time || "",
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Time",
				fieldname: "out_time",
				label: __("Last OUT"),
				default: row.out_time || "",
			},
			{ fieldtype: "Section Break", label: __("Shift") },
			{
				fieldtype: "Link",
				fieldname: "shift",
				label: __("Shift"),
				options: "Shift Type",
				default: row.shift || "",
				get_query: () => {
					const company = frappe.query_report.get_filter_value("company");
					return company ? { filters: { custom_company: company } } : {};
				},
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Date",
				fieldname: "shift_to_date",
				label: __("Same Shift Until"),
				default: row.ad_date,
				description: __("Leave as this day for one day; up to 31 days."),
			},
			{ fieldtype: "Section Break" },
			{
				fieldtype: "Small Text",
				fieldname: "reason",
				label: __("Reason"),
				reqd: 1,
				description: __("Required. Kept in the Attendance Correction Log, e.g. Forgot to punch out; confirmed by supervisor."),
			},
		],
		primary_action_label: __("Save Correction"),
		primary_action(values) {
			// Only what was changed is sent: an untouched IN/OUT on a day with one
			// punch must not block a shift-only correction.
			const punchesChanged =
				(values.in_time || "") !== (row.in_time || "") ||
				(values.out_time || "") !== (row.out_time || "");
			const shiftChanged =
				values.shift && (values.shift !== row.shift || values.shift_to_date !== String(row.ad_date));
			if (punchesChanged) {
				if (!values.in_time || !values.out_time) {
					frappe.msgprint(__("Enter both First IN and Last OUT."));
					return;
				}
				if (values.out_time <= values.in_time) {
					frappe.msgprint(__("Last OUT must be after First IN."));
					return;
				}
			}
			if (shiftChanged && values.shift_to_date < String(row.ad_date)) {
				frappe.msgprint(__("Same Shift Until cannot be before this day."));
				return;
			}
			d.disable_primary_action();
			frappe
				.call({
					method: CORRECT_DAY_METHOD,
					type: "POST",
					args: {
						employee: row.employee,
						attendance_date: row.ad_date,
						in_time: punchesChanged ? values.in_time : null,
						out_time: punchesChanged ? values.out_time : null,
						shift: shiftChanged ? values.shift : null,
						shift_to_date: shiftChanged ? values.shift_to_date : null,
						reason: values.reason,
					},
					freeze: true,
					freeze_message: __("Correcting punches and re-marking attendance..."),
				})
				.then((r) => {
					d.hide();
					const m = r.message || {};
					const lines = [
						`<b>${__("Attendance")}:</b> ${m.attendance ? frappe.utils.get_form_link("Attendance", m.attendance, true) : __("none")} — ${m.status}, ${m.in_time} → ${m.out_time}`,
						`<b>${__("Changed")}:</b> ${(m.changes || []).join("; ")}`,
					];
					(m.other_days || []).forEach((l) => lines.push(`<b>${__("Also re-marked")}:</b> ${l}`));
					(m.overtime || []).forEach((l) => lines.push(`<b>${__("Overtime")}:</b> ${l}`));
					(m.warnings || []).forEach((l) => lines.push(`<span style="color:#96662A">⚠ ${l}</span>`));
					frappe.msgprint({ title: __("Day Corrected"), message: lines.join("<br>"), indicator: "green" });
					frappe.query_report.refresh();
				})
				.always(() => d.enable_primary_action());
		},
	});
	d.$wrapper.find(".mab-log-link").on("click", (e) => {
		e.preventDefault();
		d.hide();
		_open_correction_log(row.employee, String(row.ad_date));
	});
	d.show();
}


// Status as a chip rather than coloured text: at a glance the eye picks out
// the blocks of colour, not the words.
// --- Late Excused cell ---------------------------------------------------
// Shows the tick and, as its tooltip, the reason. HR Manager can click a day
// with an Attendance and some late time (or one already excused) to change it.

function _late_excuse_cell(data) {
	const late = cint(data.late_minutes) + cint(data.before_office_minutes);
	const editable = data.attendance && frappe.user.has_role(CORRECTION_ROLES) && (late || data.late_excused);
	const attrs = editable
		? `class="mab-late-excuse" data-attendance="${frappe.utils.escape_html(data.attendance)}" style="cursor:pointer"`
		: "";
	if (data.late_excused) {
		const reason = frappe.utils.escape_html(data.late_excuse_reason || "");
		return `<span ${attrs} title="${__("Excused")}: ${reason}"
			style="background:#E6F2EA;color:#2E6B45;border-radius:3px;padding:2px 6px;font-weight:600">
			✓ ${__("Excused")}</span>`;
	}
	if (editable) {
		return `<span ${attrs} title="${__("Click to excuse this day's late time")}"
			style="color:var(--text-light)">${__("Excuse")} ✎</span>`;
	}
	return `<span style="color: var(--text-lighter)">—</span>`;
}

function _bind_late_excuse(report) {
	report.page.wrapper.off("click.mab-excuse").on("click.mab-excuse", ".mab-late-excuse", (e) => {
		const attendance = $(e.currentTarget).attr("data-attendance");
		const row = (frappe.query_report.data || []).find((r) => r.attendance === attendance);
		if (row) _open_late_excuse_dialog(row);
	});
}

function _open_late_excuse_dialog(row) {
	const name = frappe.utils.escape_html(row.employee_name || row.employee);
	const late = cint(row.late_minutes) + cint(row.before_office_minutes);
	const d = new frappe.ui.Dialog({
		title: __("Late Excuse"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<div style="margin-bottom:8px">
					<div style="font-weight:600">${name} · ${row.bs_date} (${row.ad_date})</div>
					<div class="text-muted" style="margin-top:4px">
						${__("Late in")} ${cint(row.late_minutes)} ${__("min")}, ${__("left early")} ${cint(row.before_office_minutes)} ${__("min")} · ${frappe.utils.escape_html(row.status || "")}
					</div>
					<div style="margin-top:8px;padding:8px 10px;background:#FAF6EC;border-left:3px solid #C9A227;font-size:.92em">
						${__("An excused day keeps its {0} minutes on record, but they are not fined, and a half day caused only by lateness goes back to Present. Not possible once the month's salary slip is submitted.", [late])}
					</div>
				</div>`,
			},
			{ fieldtype: "Check", fieldname: "excused", label: __("Late Excused"), default: row.late_excused ? 1 : 0 },
			{
				fieldtype: "Small Text",
				fieldname: "reason",
				label: __("Reason for Excusing"),
				default: row.late_excuse_reason || "",
				depends_on: "eval:doc.excused",
				mandatory_depends_on: "eval:doc.excused",
			},
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			frappe.call({
				method: LATE_EXCUSE_METHOD,
				args: { attendance: row.attendance, excused: values.excused ? 1 : 0, reason: values.reason || "" },
				freeze: true,
				callback: (r) => {
					if (r.exc) return;
					d.hide();
					frappe.show_alert({
						message: values.excused
							? __("Excused. Day is now {0}.", [r.message.status])
							: __("Excuse removed. Day is now {0}.", [r.message.status]),
						indicator: "green",
					});
					frappe.query_report.refresh();
				},
			});
		},
	});
	d.show();
}

function _chip(status) {
	if (!status) return "";
	// Softened deliberately. The stock --red-600 / --green-600 pair is built to
	// alarm; a month of attendance is read for half an hour at a time, and a
	// grid of alarm colours is exhausting rather than informative. These keep
	// the same semantic separation at lower saturation.
	const tones = {
		Present: ["#3F6F52", "#E8F1EA"],
		"Work From Home": ["#3F6F52", "#E8F1EA"],
		"Half Day": ["#96662A", "#FAF0DE"],
		"On Leave": ["#456A9E", "#E8EFF8"],
		Absent: ["#A64E5B", "#FAEAEC"],
		Holiday: ["#70569C", "#F0EAF8"],
	};
	// "Worked on Holiday (DASHAIN)" and "Holiday (SATURDAY)" carry the holiday's name.
	const kind = status.startsWith("Worked on Holiday") ? "Present" : status.startsWith("Holiday") ? "Holiday" : status;
	const [fg, bg] = tones[kind] || ["var(--text-muted)", "var(--bg-light-gray)"];
	const italic = status === "Not Marked" ? "font-style:italic;" : "";
	return `<span style="color:${fg};background:${bg};${italic}
		padding:2px 8px;border-radius:10px;font-size:.85em;font-weight:600;
		white-space:nowrap">${status}</span>`;
}


// Legibility pass, scoped to this report only.
//
// The reader works through a full month of a full workforce in one sitting.
// Stock desk type is 13px on tight 28px rows, which is fine for glancing at a
// list and punishing for reading a grid. This raises the body to 15px, gives
// headers real weight and spacing, warms the rules off pure grey, and stripes
// the rows so the eye can track across twelve columns without losing its line.
function _apply_theme(report) {
	const id = "nepal-hrms-attendance-theme";
	if (document.getElementById(id)) return;

	$(`<style id="${id}">
		.nepal-attendance-report .dt-cell__content {
			font-size: 15px;
			line-height: 1.45;
			padding: 8px 12px;
			color: #2F3437;
		}
		.nepal-attendance-report .dt-row:nth-child(even) .dt-cell {
			background: #FBFAF9;
		}
		.nepal-attendance-report .dt-row:hover .dt-cell {
			background: #F3F1EE;
		}
		.nepal-attendance-report .dt-cell--header .dt-cell__content {
			font-size: 12px;
			font-weight: 600;
			letter-spacing: .045em;
			text-transform: uppercase;
			color: #6B6560;
			background: #F5F3F0;
		}
		.nepal-attendance-report .dt-cell { border-color: #EDE9E4; }

		/* Summary cards: give the numbers room and calm the labels down. */
		.nepal-attendance-report .report-summary .summary-value {
			font-size: 22px;
			font-weight: 600;
			color: #2F3437;
		}
		.nepal-attendance-report .report-summary .summary-label {
			font-size: 12px;
			letter-spacing: .04em;
			color: #857E77;
		}
		.nepal-attendance-report .chart-container { padding-top: 4px; }
	</style>`).appendTo("head");

	const wrapper = report && report.page ? report.page.wrapper : null;
	if (wrapper) $(wrapper).addClass("nepal-attendance-report");
}

// ---------------------------------------------------------------------------
// Frozen leading columns + keyboard scrolling
// ---------------------------------------------------------------------------
//
// This grid is much wider than any screen: 14 fixed columns plus one per
// attendance-driven Salary Component. Scrolling right used to carry the date
// and the employee's name off-screen, leaving a wall of numbers with nothing
// identifying the row.
//
// frappe-datatable 1.19.0 has no frozen-column option, so we add one:
//
//   body   — `position: sticky` on the leading cells. The scroll container
//            (.dt-scrollable) has no transformed ancestor, so sticky behaves.
//
//   header — sticky does NOT work there. The datatable scrolls its header by
//            putting `transform: translateX(-scrollLeft)` on .dt-header
//            (Style.js), and a transformed ancestor becomes the containing
//            block for sticky, so the cells would ride along with it. Instead
//            we counter-translate the frozen header cells by +scrollLeft on
//            every scroll frame, which cancels the parent's transform exactly.
//            .dt-footer (the total row) is translated the same way and gets
//            the same treatment.
//
// The frozen set must be CONTIGUOUS AND LEADING — sticky offsets are
// cumulative, and a gap in the middle renders as a floating island. The Python
// column order is arranged for this and says so in a comment; if the freeze
// silently stops working, a reordered column is the first thing to check.


// Fields that identify a row. Whichever of these the grid actually renders as a
// LEADING, CONTIGUOUS block get frozen.
//
// Derived from the rendered columns rather than from the View filter: the
// filter value flips before the datatable re-renders, so reading it here means
// asking for Detail's columns while Summary's are still on screen. The lookup
// then fails, the function bails, and the previous view's offsets and
// transforms are left behind — which is what made switching views unstable.
// Reading what is on screen cannot desync.
const ANCHOR_FIELDS = new Set([
	"bs_date", // Detail
	"sn", // Summary
	"employee", // both
]);

// The datatable prepends its own serial-number column (serialNoColumn defaults
// to on). It is always leftmost, so it freezes with the rest.
const SERIAL_COLUMN_ID = "_rowIndex";

const FREEZE_STYLE_ID = "nepal-attendance-freeze";

// Listeners this report owns. The datatable is refreshed or rebuilt on every
// run, so each render must replace its predecessor's handlers rather than stack
// another copy on top — otherwise one scroll fires N transform passes.
const state = { scroll: null, resize: null, keys: null };

function _teardown(off) {
	if (typeof off === "function") off();
}

function _scrollable(datatable) {
	return datatable && datatable.wrapper
		? datatable.wrapper.querySelector(".dt-scrollable")
		: null;
}

// Cells carry an inline transform from the counter-translate below. Anything
// left over from a previous render would hold a column visibly out of place, so
// every path through the freeze clears them before deciding what to pin.
function _clear_pinned_transforms(datatable) {
	if (!datatable || !datatable.wrapper) return;
	for (const cell of datatable.wrapper.querySelectorAll(
		".dt-header .dt-cell[style*='transform'], .dt-footer .dt-cell[style*='transform']"
	)) {
		cell.style.transform = "";
	}
}

function _leading_anchor_columns(datatable) {
	const columns = (datatable.datamanager && datatable.datamanager.columns) || [];
	const byIndex = [...columns].sort((a, b) => a.colIndex - b.colIndex);

	const frozen = [];
	for (const col of byIndex) {
		const key = col.id || col.fieldname;
		const isAnchor = key === SERIAL_COLUMN_ID || ANCHOR_FIELDS.has(key);
		// Stop at the first column that is not an anchor: the block has to be
		// contiguous from the left, because sticky offsets are cumulative and a
		// gap in the middle renders as a floating island.
		if (!isAnchor) break;
		frozen.push(col);
	}
	return frozen;
}

function _freeze_leading_columns(datatable) {
	if (!datatable || !datatable.wrapper) return;
	if (!document.body.contains(datatable.wrapper)) return;

	_clear_pinned_transforms(datatable);

	const frozen = _leading_anchor_columns(datatable);
	if (!frozen.length) {
		$(`#${FREEZE_STYLE_ID}`).remove();
		return;
	}

	// Measure the RENDERED header cell rather than trusting col.width: the
	// datatable runs layout:"fixed" and rescales declared widths to fill the
	// container, so the declared number is not what ends up on screen.
	const measure = (col) => {
		const cell = datatable.wrapper.querySelector(`.dt-header .dt-cell--col-${col.colIndex}`);
		return cell ? Math.round(cell.getBoundingClientRect().width) : col.width || 0;
	};

	const rules = [];
	let left = 0;

	frozen.forEach((col, i) => {
		const n = col.colIndex;
		const last = i === frozen.length - 1;

		rules.push(`
			.nepal-attendance-report .dt-cell--col-${n} {
				position: sticky;
				left: ${left}px;
				z-index: 2;
				background-color: var(--dt-cell-bg, #fff);
			}
			.nepal-attendance-report .dt-cell--header.dt-cell--col-${n} {
				z-index: 4;
				background-color: var(--dt-header-cell-bg, #fff);
			}
			.nepal-attendance-report .dt-row--highlight .dt-cell--col-${n} {
				background-color: var(--dt-selection-highlight-color, #fffce7);
			}
		`);

		// Body cells only for the stacked Employee cell. The header and the
		// inline-filter row share this column index, and stripping their padding
		// knocks the header label out of line with everything beside it.
		if ((col.id || col.fieldname) === "employee") {
			rules.push(`
				.nepal-attendance-report .dt-row .dt-cell--col-${n}:not(.dt-cell--header) .dt-cell__content {
					padding: 0;
					white-space: normal;
				}
			`);
		}

		if (last) {
			// One firm edge where the frozen block ends, and a shadow that only
			// appears once something has actually scrolled under it.
			rules.push(`
				.nepal-attendance-report .dt-cell--col-${n}::after {
					content: "";
					position: absolute;
					top: 0; right: -1px; bottom: 0;
					width: 1px;
					background: var(--dt-border-color, #d1d8dd);
				}
				.nepal-attendance-report.is-scrolled-x .dt-cell--col-${n} {
					box-shadow: 3px 0 6px -3px rgba(0, 0, 0, 0.18);
				}
			`);
		}

		left += measure(col);
	});

	$(`#${FREEZE_STYLE_ID}`).remove();
	$(`<style id="${FREEZE_STYLE_ID}">${rules.join("\n")}</style>`).appendTo("head");

	_sync_frozen_header(datatable, frozen);
	_watch_resize(datatable);
}

function _sync_frozen_header(datatable, frozen) {
	const scrollable = _scrollable(datatable);
	if (!scrollable) return;

	// Resolved per frame, NOT cached. datatable.refresh() rebuilds these nodes,
	// and a cached list from the previous render points at detached elements
	// that then never move — the header drifting away from the body.
	const selector = frozen
		.flatMap((col) => [
			`.dt-header .dt-cell--col-${col.colIndex}`,
			`.dt-footer .dt-cell--col-${col.colIndex}`,
		])
		.join(", ");

	const $wrapper = $(datatable.wrapper).closest(".nepal-attendance-report");
	let ticking = false;
	let wasScrolled = null;

	const apply = () => {
		ticking = false;
		if (!document.body.contains(scrollable)) return;

		const x = scrollable.scrollLeft;
		// Cancel .dt-header's translateX(-scrollLeft) so these cells hold still.
		for (const cell of datatable.wrapper.querySelectorAll(selector)) {
			cell.style.transform = `translateX(${x}px)`;
		}

		// Only touch the class when the state flips — this runs on every frame
		// while the scrollbar is being dragged.
		const isScrolled = x > 0;
		if (isScrolled !== wasScrolled) {
			$wrapper.toggleClass("is-scrolled-x", isScrolled);
			wasScrolled = isScrolled;
		}
	};

	_teardown(state.scroll);
	const onScroll = () => {
		if (ticking) return;
		ticking = true;
		requestAnimationFrame(apply);
	};
	scrollable.addEventListener("scroll", onScroll, { passive: true });
	state.scroll = () => scrollable.removeEventListener("scroll", onScroll);

	apply();
}

// layout:"fixed" rescales every column when the window changes size, which
// invalidates the offsets baked into the stylesheet. Recompute, debounced.
const RESIZE_DEBOUNCE_MS = 150;

function _watch_resize(datatable) {
	_teardown(state.resize);

	let timer;
	const onResize = () => {
		clearTimeout(timer);
		timer = setTimeout(() => _freeze_leading_columns(datatable), RESIZE_DEBOUNCE_MS);
	};
	window.addEventListener("resize", onResize);
	state.resize = () => {
		clearTimeout(timer);
		window.removeEventListener("resize", onResize);
	};
}

// --- keyboard -------------------------------------------------------------
//
// frappe-datatable binds the arrow keys, but only to move an already-focused
// cell. With nothing focused — the normal state after a report runs — they did
// nothing at all, and .dt-scrollable only answers the browser's own scrolling
// when it happens to be hovered or focused. So the grid was mouse-only. This
// scrolls it directly, in both axes.

// One horizontal press moves about one data column. The grid's data columns run
// 60-190px wide; 220px clears a whole one every time without overshooting so
// far that the eye loses its place.
const ARROW_STEP_PX = 220;

// A screenful, less a sliver of overlap so nothing is skipped between presses.
const ARROW_PAGE_FRACTION = 0.9;

// Fallback row height for the vertical step; the live value comes from the
// datatable's own cellHeight option, which this report raises to 42.
const DEFAULT_ROW_HEIGHT_PX = 42;

const EDITABLE = "input, textarea, select, [contenteditable='true']";

const ARROW_AXES = {
	ArrowLeft: ["left", -1],
	ArrowRight: ["left", 1],
	ArrowUp: ["top", -1],
	ArrowDown: ["top", 1],
};

function _bind_arrow_key_scrolling(datatable) {
	const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

	const handler = (e) => {
		const axis = ARROW_AXES[e.key];
		if (!axis) return;
		if (e.altKey || e.ctrlKey || e.metaKey) return;

		// Someone is typing, or a dialog is up.
		if (e.target.closest && e.target.closest(EDITABLE)) return;
		if (document.querySelector(".modal.show")) return;

		// Resolved per keypress, never captured: datatable.refresh() replaces
		// .dt-scrollable, and a handler holding the old node would scroll an
		// element that is no longer on the page — the arrow keys going dead
		// after a view switch.
		const scrollable = _scrollable(datatable);
		if (!scrollable || !document.body.contains(scrollable)) {
			_teardown(state.keys);
			state.keys = null;
			return;
		}

		// A focused cell means the datatable's own navigation is in play; it
		// scrolls the grid itself, and both of us moving would double the step.
		if (datatable.wrapper.querySelector(".dt-cell--focus")) return;

		const [edge, direction] = axis;
		const page = edge === "left" ? scrollable.clientWidth : scrollable.clientHeight;
		const stride = edge === "left" ? ARROW_STEP_PX : datatable.options?.cellHeight || DEFAULT_ROW_HEIGHT_PX;

		scrollable.scrollBy({
			[edge]: (e.shiftKey ? page * ARROW_PAGE_FRACTION : stride) * direction,
			behavior: smooth ? "smooth" : "auto",
		});
		e.preventDefault();
	};

	_teardown(state.keys);
	document.addEventListener("keydown", handler);
	state.keys = () => document.removeEventListener("keydown", handler);
}
