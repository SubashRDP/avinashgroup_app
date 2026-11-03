// Shift Early Closure, many days at once — the month sheet.
//
// Every day of a BS month is already on the sheet (miti, weekday, AD date,
// holiday, closures already made, salary-paid days locked), so HR types only a
// closing time on the days that closed. One shift at a time — the way HR
// closes them: pick the shift at the top, and a day is locked only when THAT
// shift is already closed on it (another shift's closure shows as a note). The
// reason at the top covers every day left without its own. Download template
// gives the same month as .xlsx; Import file fills the sheet from an .xlsx /
// .csv and saves nothing until "Close n days" is pressed.
//
// The sheet must never open empty: with no company passed in it takes the
// user's default, else the first company they may read.
//
// Opened from Monthly Attendance BS ("Close Shift Early") and the Shift Early
// Closure list ("Close Many Days"): avinash.open_closure_sheet({company, date, on_done}).
// Server: hr/shift_early_closure_sheet.py.

(function () {
	const API = "avinashgroup_app.hr.shift_early_closure_sheet.";
	const esc = (v) => frappe.utils.escape_html(String(v == null ? "" : v));

	function add_style() {
		if (document.getElementById("sec-sheet-style")) return;
		$(`<style id="sec-sheet-style">
			.sec-bar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:10px; }
			.sec-bar .sec-month { font-weight:700; font-size:15px; min-width:150px; text-align:center; }
			.sec-bar .sec-spacer { flex:1; }
			.sec-wrap { max-height:58vh; overflow:auto; border:1px solid var(--border-color); border-radius:10px; }
			.sec-table { width:100%; border-collapse:separate; border-spacing:0; font-size:13px; }
			.sec-table th { position:sticky; top:0; z-index:1; background:var(--subtle-fg); color:var(--text-muted);
				font-weight:600; font-size:12px; padding:7px 10px; border-bottom:1px solid var(--border-color); text-align:left; }
			.sec-table td { padding:4px 10px; border-bottom:1px solid var(--border-color); vertical-align:middle; }
			.sec-table tr:last-child td { border-bottom:0; }
			.sec-table .sec-num { font-variant-numeric:tabular-nums; white-space:nowrap; }
			.sec-table input { width:100%; height:28px; padding:2px 8px; border-radius:6px;
				border:1px solid var(--border-color); background:var(--control-bg); color:var(--text-color); }
			.sec-table input.sec-time { width:120px; }
			.sec-table tr.is-filled td { background:var(--bg-blue); }
			.sec-table tr.is-holiday td.sec-note { color:var(--purple-600, #7c3aed); }
			.sec-table tr.is-holiday td:not(.sec-note) { color:var(--text-muted); }
			.sec-table tr.is-locked td { color:var(--text-muted); background:var(--subtle-fg); }
			.sec-table tr.is-missing input.sec-reason { border-color:var(--red-500); }
			.sec-table td.sec-note { font-size:12px; max-width:230px; }
			.sec-table .sec-ok { color:var(--green-600); font-weight:600; }
			.sec-table .sec-err { color:var(--red-600); font-size:12px; }
		</style>`).appendTo(document.head);
	}

	window.avinash = window.avinash || {};
	avinash.open_closure_sheet = avinash_open_closure_sheet;

	function avinash_open_closure_sheet({ company, date, on_done } = {}) {
		add_style();
		const state = { month: null };

		const d = new frappe.ui.Dialog({
			title: __("Close Shift Early"),
			size: "extra-large",
			fields: [
				{
					fieldtype: "HTML",
					options: `<div style="margin-bottom:6px;padding:8px 10px;background:var(--bg-yellow);border-radius:8px;font-size:.92em">
						${__("Type the closing time only on the days the company closed early. Everyone who came that day gets a full day: leaving at or after that time is not counted as early or fined. Late arrival still counts; absent stays absent.")}
					</div>`,
				},
				{
					fieldtype: "Link", fieldname: "company", label: __("Company"), options: "Company", reqd: 1,
					default: company || frappe.defaults.get_user_default("Company") || frappe.defaults.get_default("company"),
					change: () => load(state.month ? state.month.from_date : date),
				},
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Data", fieldname: "reason", label: __("Reason"),
					description: __("Used for every day without its own reason."),
					change: () => mark_missing(false),
				},
				{ fieldtype: "Column Break" },
				{
					fieldtype: "Link", fieldname: "shift", label: __("Shift"), options: "Shift Type", reqd: 1,
					description: __("The shift that closed early."),
					change: () => render(),
				},
				{ fieldtype: "Section Break" },
				{ fieldtype: "HTML", fieldname: "sheet" },
			],
			primary_action_label: __("Close Days"),
			primary_action: submit,
		});

		const $sheet = d.fields_dict.sheet.$wrapper;
		$sheet.html(`
			<div class="sec-bar">
				<button class="btn btn-default btn-sm" data-act="prev">‹</button>
				<div class="sec-month">…</div>
				<button class="btn btn-default btn-sm" data-act="next">›</button>
				<div class="sec-spacer"></div>
				<button class="btn btn-default btn-sm" data-act="template">${__("Download Template")}</button>
				<button class="btn btn-default btn-sm" data-act="import">${__("Import File")}</button>
			</div>
			<div class="sec-wrap"><table class="sec-table">
				<thead><tr>
					<th>${__("Miti")}</th><th>${__("Day")}</th><th>${__("Date")}</th><th>${__("Note")}</th>
					<th>${__("Closed At")}</th><th>${__("Reason (if different)")}</th><th></th>
				</tr></thead>
				<tbody></tbody>
			</table></div>`);
		const $body = $sheet.find("tbody");

		$sheet.on("click", "[data-act=prev]", () => state.month && load(frappe.datetime.add_days(state.month.from_date, -1)));
		$sheet.on("click", "[data-act=next]", () => state.month && load(frappe.datetime.add_days(state.month.to_date, 1)));
		$sheet.on("click", "[data-act=template]", download_template);
		$sheet.on("click", "[data-act=import]", import_file);
		$body.on("input change", "input", function () {
			$(this).closest("tr").toggleClass("is-filled", !!$(this).closest("tr").find(".sec-time").val());
			$(this).closest("tr").removeClass("is-missing");
			update_count();
		});
		// Enter jumps to the next day's time: a run of days without the mouse
		$body.on("keydown", ".sec-time", function (e) {
			if (e.key !== "Enter") return;
			e.preventDefault();
			$(this).closest("tr").nextAll("tr:not(.is-locked)").first().find(".sec-time").trigger("focus");
		});

		function load(on_date) {
			const co = d.get_value("company");
			if (!co) {
				$sheet.find(".sec-month").text("…");
				$body.html(`<tr><td colspan="7" class="text-muted" style="padding:24px;text-align:center">${__("Pick the company to list the month's days.")}</td></tr>`);
				return Promise.resolve();
			}
			return frappe.xcall(API + "month_sheet", { company: co, date: on_date || undefined }).then((m) => {
				state.month = m;
				$sheet.find(".sec-month").text(m.label);
				render(false);
			});
		}

		// Draw the month for the picked shift. keep: carry over what was typed
		// (the shift changed, the days did not).
		function render(keep = true) {
			if (!state.month) return;
			const typed = {};
			if (keep) {
				$body.find("tr[data-date]").each((i, tr) => {
					const t = $(tr).find(".sec-time").val();
					if (t) typed[$(tr).data("date")] = { t, why: $(tr).find(".sec-reason").val() };
				});
			}
			$body.html(state.month.rows.map(row_html).join(""));
			Object.entries(typed).forEach(([date, v]) => {
				const $tr = $body.find(`tr[data-date="${date}"]:not(.is-locked)`);
				$tr.find(".sec-time").val(v.t);
				$tr.find(".sec-reason").val(v.why);
				$tr.toggleClass("is-filled", !!$tr.length);
			});
			update_count();
		}

		// A closure naming no shift covers every shift.
		const covers = (c, shift) => !c.shifts.length || !shift || c.shifts.includes(shift);

		function row_html(r) {
			const shift = d.get_value("shift");
			const done = r.closures.find((c) => covers(c, shift));
			const others = r.closures.filter((c) => c !== done);
			const locked = !!done || r.paid;
			let note = esc(r.holiday);
			if (done) {
				note = `<a href="/app/shift-early-closure/${encodeURIComponent(done.name)}" target="_blank">${esc(done.name)}</a>
					· ${esc(done.close_at)} — ${esc(done.reason)}`;
			} else if (r.paid) {
				note = `🔒 ${__("Salary paid")}`;
			}
			if (!done && others.length) {
				note += `<div class="text-muted">${others.map((c) =>
					__("{0} closed at {1}", [esc(c.shifts.join(", ")), esc(c.close_at)])).join("<br>")}</div>`;
			}
			const cls = [locked ? "is-locked" : "", r.holiday && !locked ? "is-holiday" : ""].join(" ");
			return `<tr data-date="${esc(r.date)}" class="${cls}">
				<td class="sec-num">${esc(r.miti)}</td>
				<td>${esc(r.weekday)}</td>
				<td class="sec-num">${esc(frappe.datetime.str_to_user(r.date))}</td>
				<td class="sec-note">${note}</td>
				<td>${locked ? (done ? esc(done.close_at) : "") : `<input type="time" class="sec-time" step="60">`}</td>
				<td>${locked ? "" : `<input type="text" class="sec-reason" placeholder="${esc(__("same as above"))}">`}</td>
				<td class="sec-result"></td>
			</tr>`;
		}

		function filled_rows() {
			return $body.find("tr:not(.is-locked)").filter((i, tr) => !!$(tr).find(".sec-time").val());
		}

		function update_count() {
			const n = filled_rows().length;
			d.set_primary_action(n ? __("Close {0} Day(s)", [n]) : __("Close Days"), submit);
		}

		function mark_missing(show) {
			const top = (d.get_value("reason") || "").trim();
			let missing = 0;
			filled_rows().each((i, tr) => {
				const need = !top && !$(tr).find(".sec-reason").val().trim();
				$(tr).toggleClass("is-missing", show && need);
				missing += need ? 1 : 0;
			});
			return missing;
		}

		function submit() {
			const $rows = filled_rows();
			if (!$rows.length) {
				frappe.show_alert({ message: __("Type a closing time on at least one day."), indicator: "orange" });
				return;
			}
			if (!d.get_value("shift")) {
				frappe.msgprint(__("Pick the shift that closed early."));
				return;
			}
			if (mark_missing(true)) {
				frappe.msgprint(__("Give a reason at the top, or on each day marked in red."));
				return;
			}
			const rows = $rows.map((i, tr) => ({
				date: $(tr).data("date"),
				close_at: $(tr).find(".sec-time").val() + ":00",
				reason: $(tr).find(".sec-reason").val().trim(),
			})).get();

			frappe.call({
				method: API + "close_days",
				args: {
					company: d.get_value("company"),
					rows,
					reason: (d.get_value("reason") || "").trim(),
					shifts: [d.get_value("shift")],
				},
				freeze: true,
				freeze_message: __("Closing {0} day(s) ...", [rows.length]),
				callback(r) {
					if (r.exc) return;
					let ok = 0;
					(r.message || []).forEach((res) => {
						const $tr = $body.find(`tr[data-date="${res.date}"]`);
						if (res.name) {
							ok++;
							$tr.addClass("is-locked").removeClass("is-filled");
							$tr.find("input").prop("disabled", true);
							$tr.find(".sec-result").html(`<span class="sec-ok">✓</span>`);
							$tr.find(".sec-note").html(`<a href="/app/shift-early-closure/${encodeURIComponent(res.name)}" target="_blank">${esc(res.name)}</a>
								· ${__("{0} re-measured", [res.updated || 0])}`);
						} else {
							$tr.find(".sec-result").html(`<span class="sec-err">✕ ${esc(res.error)}</span>`);
						}
					});
					const failed = (r.message || []).length - ok;
					frappe.show_alert({
						message: failed
							? __("{0} day(s) closed, {1} not — see the red rows", [ok, failed])
							: __("{0} day(s) closed early", [ok]),
						indicator: failed ? "orange" : "green",
					});
					update_count();
					if (ok && on_done) on_done();
				},
			});
		}

		function download_template() {
			if (!state.month) return;
			const q = new URLSearchParams({ company: d.get_value("company"), date: state.month.from_date, shift: d.get_value("shift") || "" });
			window.open(`/api/method/${API}download_template?${q}`);
		}

		function import_file() {
			new frappe.ui.FileUploader({
				restrictions: { allowed_file_types: [".xlsx", ".csv"] },
				make_attachments_public: false,
				on_success(file) {
					frappe.xcall(API + "read_file", { file_url: file.file_url }).then(apply_import);
				},
			});
		}

		async function apply_import({ rows, errors }) {
			const problems = [...(errors || [])];
			if (!rows.length) {
				frappe.msgprint({ title: __("Nothing to import"), message: problems.join("<br>") || __("No row has a closing time.") });
				return;
			}
			// the file names its shift and none is picked yet: take it
			const named = rows.map((r) => (r.shifts || [])[0]).find(Boolean);
			if (named && !d.get_value("shift")) await d.set_value("shift", named);
			const shift = d.get_value("shift");
			// a file for another month: open that month first
			const in_month = (r) => state.month && r.date >= state.month.from_date && r.date <= state.month.to_date;
			if (!rows.some(in_month)) await load(rows[0].date);

			let filled = 0;
			rows.forEach((r) => {
				const $tr = $body.find(`tr[data-date="${r.date}"]`);
				const when = frappe.datetime.str_to_user(r.date);
				if (!$tr.length) return problems.push(__("{0}: not in {1}", [when, state.month.label]));
				const row_shift = (r.shifts || [])[0];
				if (row_shift && shift && row_shift !== shift) {
					return problems.push(__("{0}: for {1}, not {2} — import it with that shift picked", [when, row_shift, shift]));
				}
				if ($tr.hasClass("is-locked")) return problems.push(__("{0}: already closed or salary paid", [when]));
				$tr.find(".sec-time").val(r.close_at.slice(0, 5));
				if (r.reason) $tr.find(".sec-reason").val(r.reason);
				$tr.addClass("is-filled");
				filled++;
			});
			update_count();
			frappe.show_alert({ message: __("{0} day(s) filled from the file — check, then Close", [filled]), indicator: "blue" });
			if (problems.length) {
				frappe.msgprint({ title: __("Some rows were not filled"), message: problems.map(esc).join("<br>"), indicator: "orange" });
			}
		}

		d.show();
		if (d.get_value("company")) {
			load(date);
		} else {
			// no default company: the first one the user may read, so the days show at once
			frappe.db.get_list("Company", { fields: ["name"], limit: 1, order_by: "name asc" }).then((r) => {
				if (r && r.length) d.set_value("company", r[0].name); // its change handler loads
				else load(date);
			});
		}
		return d;
	}
})();
