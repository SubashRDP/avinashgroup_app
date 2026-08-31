

const REPORT_MODULE =
	"avinashgroup_app.avinash_group_app.report.monthly_attendance_bs.monthly_attendance_bs";

frappe.query_reports["Monthly Attendance BS"] = {
	onload: async function (report) {
		_apply_theme(report);
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
			return _chip(data.status);
		}

		if (f === "late_minutes" || f === "before_office_minutes") {
			const n = cint(data[f]);
			if (!n) return muteZero();
			// 15 minutes is the grace period on every shift; past it, it counts.
			const tone = n > 15 ? "#A64E5B" : "#96662A";
			return `<span style="color:${tone};font-weight:600">${n}</span>`;
		}

		if (f === "working_hours") {
			if (!data.working_hours || data.working_hours === "00:00") return muteZero();
			return `<span style="font-weight:600">${data.working_hours}</span>`;
		}

		if (f === "in_time" || f === "out_time") {
			if (!data[f]) {
				// A missing OUT is the single most common data fault — name it.
				return `<span style="color:#A64E5B" title="${__("No punch recorded")}">— —</span>`;
			}
			return value;
		}

		if (f === "work_in_holiday" && cint(data.work_in_holiday)) {
			return `<span style="color:#70569C;font-weight:600">${__("Holiday")}</span>`;
		}

		if (f === "remarks" && data.remarks) {
			return `<span style="color:var(--text-muted);font-size:.9em">${data.remarks}</span>`;
		}

		// --- Summary view ------------------------------------------------
		if (f === "ot_hours") {
			const n = flt(data.ot_hours);
			if (!n) return muteZero();
			return `<span style="color:#3E7290;font-weight:600">${format_number(n, null, 2)}</span>`;
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


// Status as a chip rather than coloured text: at a glance the eye picks out
// the blocks of colour, not the words.
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
	const [fg, bg] = tones[status] || ["var(--text-muted)", "var(--bg-light-gray)"];
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
