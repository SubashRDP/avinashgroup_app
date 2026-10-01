// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

const BS_MONTHS = [
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
];

// Which filters belong to which view.
const CUSTOMER_WISE_FILTERS = ["company", "as_on_date"];
const MONTHLY_FILTERS = ["bs_year", "bs_month", "compare_date", "with_date"];

frappe.query_reports["Debtors Summary"] = {
	onload: function (report) {
		toggle_filters();
		attach_bs_picker("compare_date");
		attach_bs_picker("with_date");

		// Download PDF and Print both open the same server-rendered PDF, so a
		// printed copy matches the downloaded one page for page. The app's
		// report_print_orientation.js adds the Portrait / Landscape choice to
		// Download PDF; Print takes it from the print dialog.
		report.page.add_inner_button(__("Download PDF"), function () {
			const url = pdf_url();
			if (url) window.open(url);
		});

		report.print_report = function (print_settings) {
			const orientation = (print_settings && print_settings.orientation) || "Landscape";
			const url = pdf_url();
			if (url) window.open(url + "&orientation=" + encodeURIComponent(orientation) + "&view=1");
		};

		// BS year/month can't be derived in the browser, so the server supplies them.
		frappe.call({
			method: "avinashgroup_app.avinash_group_app.report.debtors_summary.debtors_summary.get_current_bs_period",
		}).then((r) => {
			if (!r.message) return;
			if (frappe.query_report.get_filter_value("bs_year")) return;
			frappe.query_report.set_filter_value("bs_year", r.message.bs_year);
			frappe.query_report.set_filter_value("bs_month", BS_MONTHS[r.message.bs_month - 1]);
		});
	},

	filters: [
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: ["Customer Wise", "Monthly"].join("\n"),
			default: "Customer Wise",
			reqd: 1,
			on_change: function () {
				toggle_filters();
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "as_on_date",
			label: __("As On Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
		},
		{
			fieldname: "bs_year",
			label: __("BS Year"),
			fieldtype: "Int",
			description: __("Bikram Sambat year, e.g. 2083."),
		},
		{
			fieldname: "bs_month",
			label: __("BS Month"),
			fieldtype: "Select",
			options: BS_MONTHS.join("\n"),
		},
		// The comparison block's two dates, as BS dates — picked from the Nepali
		// calendar (see attach_bs_picker) or typed. Blank = the month's latest day
		// compared with the day before it.
		{
			fieldname: "compare_date",
			label: __("Compare Date"),
			fieldtype: "Data",
			description: __("Recent BS date, e.g. 2083-03-11"),
		},
		{
			fieldname: "with_date",
			label: __("With Date"),
			fieldtype: "Data",
			description: __("BS date to compare with, e.g. 2083-03-10"),
		},
	],

	// The report carries its own SN column (so print and Excel keep the reference
	// sheet's row numbers), so the datatable's built-in row-number column is
	// dropped — otherwise the screen shows two serial columns side by side.
	get_datatable_options: function (options) {
		return Object.assign(options, { serialNoColumn: false });
	},

	after_datatable_render: function (datatable) {
		setup_group_header(datatable);
	},

	formatter: function (value, row, column, data, default_formatter) {
		// The comparison block's Up/Down row holds ▲ / ▼ / – in the money columns.
		if (data && data.up_down && column.fieldname !== "date") {
			const colour = value === "▲" ? "var(--green-600)" : value === "▼" ? "var(--red-600)" : "inherit";
			return value ? `<div style="text-align:right; color:${colour}; font-weight:600;">${value}</div>` : "";
		}
		// The blocks are different lengths, so a row can have no entry for a block —
		// leave those cells blank instead of printing "Rs 0.00". Real zeros (the
		// totals row of an empty block) still show, since their value is present.
		if (column.fieldtype === "Currency" && (value == null || value === "")) {
			return "";
		}
		value = default_formatter(value, row, column, data);
		if ((data && data.bold) || column.fieldname === "grand_total") {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};

// Show only the filters the selected view uses. Frappe has no built-in
// depends_on for report filters, so they're toggled by hand.
function toggle_filters() {
	const is_monthly = frappe.query_report.get_filter_value("view") === "Monthly";
	const show = is_monthly ? MONTHLY_FILTERS : CUSTOMER_WISE_FILTERS;
	const hide = is_monthly ? CUSTOMER_WISE_FILTERS : MONTHLY_FILTERS;

	show.forEach((fieldname) => set_filter_visible(fieldname, true));
	hide.forEach((fieldname) => set_filter_visible(fieldname, false));
}

// The PDF endpoint for the current filters, or null (with a message) when the
// selected view is missing a filter it needs.
function pdf_url() {
	const filters = frappe.query_report.get_filter_values(true);
	if (filters.view === "Monthly" ? !(filters.bs_year && filters.bs_month) : !filters.company) {
		frappe.msgprint(
			filters.view === "Monthly"
				? __("Please set BS Year and BS Month")
				: __("Please set the Company")
		);
		return null;
	}
	return (
		"/api/method/avinashgroup_app.avinash_group_app.report.debtors_summary.debtors_summary.download_pdf" +
		"?filters=" + encodeURIComponent(JSON.stringify(filters))
	);
}

// ── Two-row column heading ─────────────────────────────────────────────────
//
// The datatable has a single header row, so each column's `group` (a company in
// Monthly, a customer block in Customer Wise) is drawn as an extra row inside
// its .dt-header. Living inside .dt-header means the row moves
// with the datatable's own horizontal scroll. Each group cell takes the summed
// pixel width of the header cells beneath it, and is redrawn whenever those
// widths change (column resize) or the header is rebuilt (refresh, column
// removed). Columns without a `group` (Date, SN) get a blank cell above them.

const GROUP_ROW_CLASS = "ds-group-row";

function setup_group_header(datatable) {
	add_group_header_style();

	// Show only the part under the company name, e.g. "Gas Customers".
	let relabelled = false;
	datatable.getColumns().forEach((column) => {
		if (column.sub_label && column.content !== column.sub_label) {
			column.content = column.sub_label;
			relabelled = true;
		}
	});
	if (relabelled) datatable.columnmanager.refreshHeader();

	// One set of observers per datatable; later renders only redraw.
	if (!datatable._ds_group_header) {
		const redraw = () => draw_group_header(datatable);
		datatable._ds_group_header = {
			resize_observer: new ResizeObserver(redraw),
			mutation_observer: new MutationObserver(redraw),
			signature: "",
		};
		datatable._ds_group_header.mutation_observer.observe(datatable.header, {
			childList: true,
			subtree: true,
		});
	}
	draw_group_header(datatable);
}

function draw_group_header(datatable) {
	const state = datatable._ds_group_header;
	const header = datatable.header;
	const cells = Array.from(header.querySelectorAll(".dt-row-header .dt-cell--header"));

	// Group the header cells into runs of the same `group`.
	const runs = [];
	cells.forEach((cell) => {
		const column = datatable.getColumn(cell.getAttribute("data-col-index"));
		const group = (column && column.group) || "";
		const width = cell.getBoundingClientRect().width;
		const last = runs[runs.length - 1];
		if (last && last.group === group) {
			last.width += width;
		} else {
			runs.push({ group, width });
		}
	});

	const has_groups = runs.some((run) => run.group);
	const existing = header.querySelector("." + GROUP_ROW_CLASS);

	// The observers fire on our own insertion too; skip when nothing has changed.
	const signature = has_groups ? runs.map((run) => `${run.group}:${run.width}`).join("|") : "";
	if (signature === state.signature && !!existing === has_groups) return;
	state.signature = signature;

	if (existing) existing.remove();
	state.resize_observer.disconnect();
	if (!has_groups) return;

	const $row = $(`<div class="${GROUP_ROW_CLASS}">`);
	let shade = 0;
	runs.forEach((run) => {
		const $cell = $('<div class="ds-group-cell">').css("width", run.width + "px").appendTo($row);
		if (run.group) {
			$cell.text(run.group).addClass(shade++ % 2 ? "ds-shade-b" : "ds-shade-a");
		}
	});
	header.insertBefore($row[0], header.firstChild);

	cells.forEach((cell) => state.resize_observer.observe(cell));
}

function add_group_header_style() {
	if (document.getElementById("ds-group-header-style")) return;
	$(`<style id="ds-group-header-style">
		.${GROUP_ROW_CLASS} { display: flex; }
		.${GROUP_ROW_CLASS} .ds-group-cell {
			flex: none;
			box-sizing: border-box;
			padding: 6px 8px;
			text-align: center;
			font-weight: 600;
			white-space: nowrap;
			overflow: hidden;
			text-overflow: ellipsis;
			border-right: 1px solid var(--border-color);
			border-bottom: 1px solid var(--border-color);
		}
		/* Neighbouring companies alternate shades so each one's columns read as a block. */
		.${GROUP_ROW_CLASS} .ds-shade-a { background: var(--subtle-fg); }
		.${GROUP_ROW_CLASS} .ds-shade-b { background: var(--gray-200); }
	</style>`).appendTo("head");
}

// Opens the Nepali (BS) calendar on a Data filter. The picker library is loaded
// on every desk page by rdp_common_app. It writes the date as YYYY-MM-DD into
// the input without telling Frappe, so the picked value is pushed into the
// filter by hand, which also re-runs the report.
function attach_bs_picker(fieldname) {
	const filter = frappe.query_report.get_filter(fieldname);
	const input = filter && filter.$input && filter.$input[0];
	if (!input || typeof input.NepaliDatePicker !== "function") return;

	input.NepaliDatePicker({
		ndpYear: true,
		ndpMonth: true,
		dateFormat: "YYYY-MM-DD",
		onSelect: function () {
			frappe.query_report.set_filter_value(fieldname, input.value);
		},
	});
}

function set_filter_visible(fieldname, visible) {
	const filter = frappe.query_report.get_filter(fieldname);
	if (!filter) return;
	filter.df.hidden = visible ? 0 : 1;
	filter.refresh();
	filter.$wrapper.toggle(visible);
}
