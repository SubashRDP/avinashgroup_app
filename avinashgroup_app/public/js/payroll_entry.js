// Payroll Entry: choose the month on a BS month calendar; the dates follow.
// The calendar sets Fiscal Year + Month (BS), the server fills the rest on
// save (payroll/payroll_month.py); this shows the
// month's dates as soon as it is picked, from the same calendar
// (hr/bs_calendar.py, Nepal BS Period first), and locks the English date
// fields so a typed date cannot move the payroll into another month.

const BS_CALENDAR = "avinashgroup_app.hr.bs_calendar";
const BS_LOCKED_FIELDS = ["posting_date", "start_date", "end_date", "payroll_frequency"];

function lock_bs_dates(frm) {
	const locked = !!(frm.doc.custom_fiscal_year && frm.doc.custom_bs_month);
	BS_LOCKED_FIELDS.forEach((f) => frm.set_df_property(f, "read_only", locked ? 1 : 0));
}

function show_bs_month(frm) {
	const { custom_fiscal_year: fiscal_year, custom_bs_month: bs_month, company } = frm.doc;
	lock_bs_dates(frm);
	fill_company_defaults(frm);
	if (frm.doc.docstatus !== 0 || !fiscal_year || !bs_month) return;
	frappe.call({
		method: `${BS_CALENDAR}.get_month`,
		args: { fiscal_year, bs_month, company },
		callback: (r) => {
			const p = r.message;
			// A newer pick may have come in while this call was out.
			if (!p || frm.doc.custom_fiscal_year !== fiscal_year || frm.doc.custom_bs_month !== bs_month) return;
			// Set on the doc directly: HRMS's own start/end/posting handlers
			// would otherwise recompute the dates from the AD calendar.
			Object.assign(frm.doc, {
				start_date: p.start_date,
				end_date: p.end_date,
				posting_date: p.end_date,
				payroll_frequency: "Monthly",
				custom_start_miti: p.start_miti,
				custom_end_miti: p.end_miti,
				custom_posting_miti: p.end_miti,
			});
			frm.refresh_fields();
			lock_bs_dates(frm);
		},
	});
}

// HRMS fills the payable account, cost centre and currency only when the
// company is *changed*; a new entry that opens with the default company has
// them blank, and the form refuses Save on the mandatory account before the
// server (payroll_month.py) could fill it. Blanks only: a deliberate choice
// is kept.
function fill_company_defaults(frm) {
	if (frm.doc.docstatus !== 0 || !frm.doc.company) return;
	if (frm.doc.payroll_payable_account && frm.doc.cost_center && frm.doc.currency) return;
	const company = frm.doc.company;
	frappe.db
		.get_value("Company", company, ["default_payroll_payable_account", "cost_center", "default_currency"])
		.then(({ message: c }) => {
			if (!c || frm.doc.company !== company) return;
			if (!frm.doc.payroll_payable_account && c.default_payroll_payable_account) {
				frm.set_value("payroll_payable_account", c.default_payroll_payable_account);
			}
			if (!frm.doc.cost_center && c.cost_center) frm.set_value("cost_center", c.cost_center);
			if (!frm.doc.currency && c.default_currency) frm.set_value("currency", c.default_currency);
		});
}

const MONTH_CALENDAR_API = "avinashgroup_app.payroll.payroll_month.month_calendar";
const NEPALI_MONTH = {
	1: "बैशाख", 2: "जेठ", 3: "असार", 4: "साउन", 5: "भदौ", 6: "असोज",
	7: "कात्तिक", 8: "मंसिर", 9: "पुस", 10: "माघ", 11: "फागुन", 12: "चैत",
};
const MONTH_NAME = {
	1: "Baisakh", 2: "Jestha", 3: "Ashadh", 4: "Shrawan", 5: "Bhadra", 6: "Ashwin",
	7: "Kartik", 8: "Mangsir", 9: "Poush", 10: "Magh", 11: "Falgun", 12: "Chaitra",
};

function short_date(d) {
	return moment(d).format("D MMM");
}

// The month calendar: a fiscal year's twelve months in fiscal order, each with
// its English dates and any payroll already made for it. Clicking a month sets
// Fiscal Year + Month (BS); everything else follows from them.
// The calendar is how Fiscal Year + Month are set; the plain fields would only
// repeat it. Hidden on the form at once (not after the calendar loads), and
// kept as real fields for the list view, filters and imports.
function hide_month_fields(frm) {
	frm.toggle_display(["custom_fiscal_year", "custom_bs_month"], false);
}

function draw_month_calendar(frm, fiscal_year) {
	hide_month_fields(frm);
	const field = frm.get_field("custom_month_calendar");
	if (!field || !frm.doc.company) {
		field && field.$wrapper.html(`<div class="text-muted small">${__("Choose the company first.")}</div>`);
		return;
	}
	frm.__calendar_year = fiscal_year || frm.__calendar_year || frm.doc.custom_fiscal_year;
	frappe.call({
		method: MONTH_CALENDAR_API,
		args: {
			company: frm.doc.company,
			fiscal_year: frm.__calendar_year,
			exclude: frm.is_new() ? null : frm.doc.name,
		},
		callback: (r) => r.message && render_month_calendar(frm, r.message),
	});
}

function render_month_calendar(frm, cal) {
	frm.__calendar_year = cal.fiscal_year;
	const editable = frm.doc.docstatus === 0;
	const chosen = frm.doc.custom_fiscal_year === cal.fiscal_year ? frm.doc.custom_bs_month : null;

	const tiles = cal.months
		.map((m) => {
			const paid = m.entries.filter((e) => e.docstatus === 1);
			const drafts = m.entries.filter((e) => e.docstatus === 0);
			let badge = "";
			if (paid.length) badge = `<span class="pmc-badge pmc-paid">${__("Paid")}</span>`;
			else if (drafts.length) badge = `<span class="pmc-badge pmc-draft">${__("Draft")}</span>`;
			else if (m.state === "running") badge = `<span class="pmc-badge pmc-running">${__("Running")}</span>`;
			const links = m.entries
				.map((e) => `<a class="pmc-link" href="/app/payroll-entry/${encodeURIComponent(e.name)}">${frappe.utils.escape_html(e.name)}</a>`)
				.join("");
			const classes = ["pmc-tile"];
			if (m.option === chosen) classes.push("pmc-chosen");
			if (m.state === "future") classes.push("pmc-future");
			if (!editable || m.state === "future") classes.push("pmc-locked");
			const title =
				m.state === "future"
					? __("Not started yet")
					: m.source === "Nepal BS Period"
					? __("Dates from Nepal BS Period")
					: __("Dates from the Nepali calendar");
			return `<div class="${classes.join(" ")}" data-option="${m.option}" title="${title}">
				<div class="pmc-head"><b>${MONTH_NAME[m.bs_month]}</b>${badge}</div>
				<div class="pmc-ne">${NEPALI_MONTH[m.bs_month]} ${m.bs_year}</div>
				<div class="pmc-dates">${short_date(m.start_date)} – ${short_date(m.end_date)}</div>
				${links}
			</div>`;
		})
		.join("");

	const $w = frm.get_field("custom_month_calendar").$wrapper;
	$w.html(`
		<style>
			.pmc { border: 1px solid var(--border-color); border-radius: var(--border-radius-md); padding: 12px; background: var(--card-bg); }
			.pmc-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; gap: 8px; }
			.pmc-bar .pmc-title { font-weight: 600; text-align: center; }
			.pmc-bar .pmc-title small { display: block; font-weight: normal; color: var(--text-muted); }
			.pmc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px; }
			.pmc-tile { border: 1px solid var(--border-color); border-radius: var(--border-radius); padding: 8px 10px; cursor: pointer; background: var(--fg-color); }
			.pmc-tile:hover { border-color: var(--primary); }
			.pmc-tile.pmc-chosen { border: 2px solid var(--primary); background: var(--control-bg); }
			.pmc-tile.pmc-locked { cursor: default; }
			.pmc-tile.pmc-locked:hover { border-color: var(--border-color); }
			.pmc-tile.pmc-chosen.pmc-locked:hover { border-color: var(--primary); }
			.pmc-tile.pmc-future { opacity: 0.45; }
			.pmc-head { display: flex; justify-content: space-between; align-items: center; gap: 4px; }
			.pmc-ne, .pmc-dates { font-size: var(--text-sm); color: var(--text-muted); }
			.pmc-dates { font-variant-numeric: tabular-nums; }
			.pmc-badge { font-size: 10px; padding: 1px 6px; border-radius: 8px; white-space: nowrap; }
			.pmc-paid { background: var(--green-100); color: var(--green-700); }
			.pmc-draft { background: var(--orange-100); color: var(--orange-700); }
			.pmc-running { background: var(--blue-100); color: var(--blue-700); }
			.pmc-link { display: block; font-size: 11px; margin-top: 2px; }
		</style>
		<div class="pmc">
			<div class="pmc-bar">
				<button class="btn btn-xs btn-default pmc-prev" ${cal.previous ? "" : "disabled"}>‹ ${cal.previous || ""}</button>
				<div class="pmc-title">${__("Fiscal Year")} ${cal.fiscal_year}
					<small>${__("Choose the month to pay")}</small></div>
				<button class="btn btn-xs btn-default pmc-next" ${cal.next ? "" : "disabled"}>${cal.next || ""} ›</button>
			</div>
			<div class="pmc-grid">${tiles}</div>
		</div>`);

	$w.find(".pmc-prev").on("click", () => draw_month_calendar(frm, cal.previous));
	$w.find(".pmc-next").on("click", () => draw_month_calendar(frm, cal.next));
	$w.find(".pmc-link").on("click", (e) => e.stopPropagation());
	if (!editable) return;
	$w.find(".pmc-tile:not(.pmc-locked)").on("click", function () {
		const option = $(this).attr("data-option");
		const month = cal.months.find((m) => m.option === option);
		const pick = () => {
			frm.doc.custom_fiscal_year = cal.fiscal_year;
			frm.doc.custom_bs_month = option;
			frm.refresh_field("custom_fiscal_year");
			frm.refresh_field("custom_bs_month");
			frm.dirty();
			render_month_calendar(frm, cal);
			show_bs_month(frm);
		};
		if (month.entries.length) {
			frappe.confirm(
				__("{0} {1} already has payroll entry {2}. Make another one for it?", [
					MONTH_NAME[month.bs_month],
					month.bs_year,
					month.entries.map((e) => e.name).join(", "),
				]),
				pick
			);
		} else {
			pick();
		}
	});
}

frappe.ui.form.on("Payroll Entry", {
	setup: hide_month_fields,
	onload(frm) {
		hide_month_fields(frm);
		if (!frm.is_new() || frm.doc.custom_bs_month) return;
		frappe.call({
			// The month after the company's last payroll (payroll_month.default_month).
			method: "avinashgroup_app.payroll.payroll_month.default_month",
			args: { company: frm.doc.company },
			callback: (r) => {
				if (!r.message || frm.doc.custom_bs_month) return;
				frm.doc.custom_fiscal_year = r.message.fiscal_year;
				frm.doc.custom_bs_month = r.message.bs_month;
				show_bs_month(frm);
				draw_month_calendar(frm, r.message.fiscal_year);
			},
		});
	},
	custom_fiscal_year(frm) {
		show_bs_month(frm);
		draw_month_calendar(frm, frm.doc.custom_fiscal_year);
	},
	custom_bs_month(frm) {
		show_bs_month(frm);
		draw_month_calendar(frm);
	},
	company(frm) {
		show_bs_month(frm);
		draw_month_calendar(frm);
	},

	refresh(frm) {
		lock_bs_dates(frm);
		draw_month_calendar(frm, frm.doc.custom_fiscal_year);
		if (frm.doc.docstatus === 2) return;

		frm.add_custom_button(
			__("Prepare Payroll Inputs"),
			() => {
				frappe.confirm(
					__(
						"Work out this month's tea, meals, overtime and late fines from attendance, and take this month's advance instalments? Anything this button posted before for the month is replaced."
					),
					() => {
						frappe.dom.freeze(__("Preparing payroll inputs..."));
						frappe
							.call({
								method: "avinashgroup_app.payroll.attendance_allowance.trigger_for_payroll_entry",
								args: { payroll_entry: frm.doc.name },
							})
							.then((r) => {
								frappe.dom.unfreeze();
								if (!r || !r.message) return;
								const created = r.message.created || 0;
								const skipped = r.message.skipped || 0;
								const recovered = r.message.advance_recoveries || 0;
								const refreshed = r.message.slips_refreshed || 0;
								let msg = __("{0} allowance and fine records, {1} advance instalments.", [created, recovered]);
								if (refreshed) {
									msg += " " + __("{0} draft salary slips updated.", [refreshed]);
								}
								if (skipped) {
									msg += " " + __("{0} skipped — see Error Log.", [skipped]);
								}
								frm.reload_doc();
								frappe.show_alert({
									message: msg,
									indicator: skipped ? "orange" : created ? "green" : "orange",
								});
							})
							.catch(() => frappe.dom.unfreeze());
					}
				);
			},
			__("Nepal HRMS")
		);
	},
});
