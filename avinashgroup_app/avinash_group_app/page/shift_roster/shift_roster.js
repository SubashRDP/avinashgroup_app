// Shift Roster — who works which rotational shift, month by month, and the
// place to change it.
//
// One row per employee, one column per BS month of the fiscal year. Pick a shift
// from the palette and paint cells: a painted cell means "on this shift from the
// first day of that month", carried to the next painted month or the year end.
// Apply sends each run of changed months as one bounded period
// (shift_rotation.set_periods), so a change already booked later is kept. Drag down a column to move many people at once;
// right-click a cell to alternate that person's shift month by month to the year
// end; a month header's ⇄ swaps everyone in that month. Nothing is saved until
// Apply. Every rule (rotational shifts only, one company, paid months locked,
// lived days re-marked) is enforced by avinashgroup_app.hr.shift_rotation —
// this page only stages and asks.
const ROSTER_API = "avinashgroup_app.hr.shift_roster.roster";
const PERIODS_API = "avinashgroup_app.hr.shift_rotation.set_periods";

frappe.pages["shift-roster"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Shift Roster"), single_column: true });
	wrapper.shift_roster = new ShiftRoster(page);
};

class ShiftRoster {
	constructor(page) {
		this.page = page;
		this.data = null;
		this.changes = new Map(); // "employee|monthIndex" -> shift name
		this.history = []; // snapshots of `changes`, for undo
		this.future = []; // for redo
		this.brush = null;
		this.painting = false;
		this.refusals = {}; // "employee|monthIndex" -> reason, from the last Apply
		this.inject_style();
		this.make_filters();
		this.$body = $(`<div class="sr-root"></div>`).appendTo(page.body);
		this.bind_keys();
		this.load();
	}

	// ── filters ────────────────────────────────────────────────────────────
	make_filters() {
		this.company = this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			change: () => this.load(),
		});
		this.fiscal_year = this.page.add_field({
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			change: () => this.load(),
		});
		this.search = this.page.add_field({
			fieldname: "search",
			label: __("Search name / department"),
			fieldtype: "Data",
			change: () => this.render(),
		});
		this.search.$input.on("input", frappe.utils.debounce(() => this.render(), 150));
		this.page.set_secondary_action(__("Reload"), () => this.load(), "refresh");
	}

	load() {
		const company = this.company.get_value();
		if (!company) {
			this.$body.html(`<div class="sr-empty">${__("Choose a company.")}</div>`);
			return;
		}
		if (this.changes.size && !this.loading_after_apply) {
			// Switching company or year would silently drop staged work.
			if (!window.confirm(__("Discard {0} unsaved change(s)?", [this.changes.size]))) return;
		}
		this.loading_after_apply = false;
		frappe
			.call(ROSTER_API, { company, fiscal_year: this.fiscal_year.get_value() || null })
			.then(({ message }) => {
				this.data = message;
				if (!this.fiscal_year.get_value()) this.fiscal_year.set_value(message.fiscal_year);
				this.changes = new Map();
				this.history = [];
				this.future = [];
				this.shift_by_name = Object.fromEntries(message.shifts.map((s) => [s.name, s]));
				if (!this.brush || !this.shift_by_name[this.brush]) this.brush = message.shifts[0]?.name || null;
				this.render();
			});
	}

	// ── state helpers ──────────────────────────────────────────────────────
	month_locked(i) {
		// A month that has already ended is not painted here: it is paid, or about
		// to be, and a backdated change belongs to Shift Request with HR's eyes on it.
		return this.data.months[i].end < this.data.today;
	}

	server_shift(row, i) {
		// The shift on the month's first day — what a painted cell would replace.
		const spans = row.cells[i];
		return spans.length ? spans[0].shift : null;
	}

	// The shift a row shows in month i once staged changes are applied: the latest
	// change at or before i wins, because every change is "from that month on".
	// A month the person spends off rotation (fixed shift, none) is not carried into.
	effective(row, i) {
		if (!this.changes.has(`${row.employee}|${i}`) && !this.is_rotational(this.server_shift(row, i))) {
			return { shift: this.server_shift(row, i), pending: false, spans: row.cells[i] };
		}
		for (let j = i; j >= 0; j--) {
			const staged = this.changes.get(`${row.employee}|${j}`);
			if (staged) return { shift: staged, pending: true, spans: null };
		}
		return { shift: this.server_shift(row, i), pending: false, spans: row.cells[i] };
	}

	snapshot() {
		this.history.push(new Map(this.changes));
		if (this.history.length > 100) this.history.shift();
		this.future = [];
	}

	// What month i would show if it had no change of its own: the latest change
	// before it, else what the server has on the month's first day.
	baseline(row, i) {
		for (let j = i - 1; j >= 0; j--) {
			const staged = this.changes.get(`${row.employee}|${j}`);
			if (staged) return staged;
		}
		return this.server_shift(row, i);
	}

	stage(row, i, shift) {
		const key = `${row.employee}|${i}`;
		if (this.month_locked(i) || !this.is_rotational(this.server_shift(row, i))) return;
		const base = this.baseline(row, i);
		if (!this.is_rotational(base)) return; // fixed-shift and unrostered people stay put
		delete this.refusals[key];
		if (base === shift) this.changes.delete(key); // painting what is already there
		else this.changes.set(key, shift);
	}

	is_rotational(shift) {
		return !!this.shift_by_name[shift];
	}

	// ── render ─────────────────────────────────────────────────────────────
	render() {
		if (!this.data) return;
		const { months, shifts } = this.data;
		const term = (this.search.get_value() || "").toLowerCase();
		const rows = this.data.rows.filter(
			(r) => !term || `${r.employee_name} ${r.employee} ${r.department || ""}`.toLowerCase().includes(term),
		);

		if (!shifts.length) {
			this.$body.html(
				`<div class="sr-empty">${__(
					"No shift of {0} is ticked Takes Part in Rotation. Tick it on the Shift Type first.",
					[frappe.utils.escape_html(this.company.get_value())],
				)}</div>`,
			);
			return;
		}

		const palette = shifts
			.map(
				(s, n) => `<button class="sr-brush ${s.name === this.brush ? "active" : ""}" data-shift="${frappe.utils.escape_html(s.name)}"
					style="--chip:${s.color}" title="${frappe.utils.escape_html(s.name)} — ${__("key")} ${n + 1}">
					<span class="sr-dot"></span>${s.label}<small>${frappe.utils.escape_html(s.name)}</small></button>`,
			)
			.join("");

		const head = months
			.map((m, i) => {
				const cls = [this.month_locked(i) ? "locked" : "", this.is_current(i) ? "current" : ""].join(" ");
				const swap = this.month_locked(i)
					? `<span class="sr-lock" title="${__("Month over")}">🔒</span>`
					: `<button class="sr-swap" data-month="${i}" title="${__("Swap everyone in {0} to the other shift", [m.label])}">⇄</button>`;
				return `<div class="sr-mh ${cls}"><b>${m.label}</b><small>${m.bs_year}</small>${swap}</div>`;
			})
			.join("");

		const body = rows.map((r) => this.row_html(r)).join("");
		const coverage = this.coverage_html(rows);

		this.$body.html(`
			<div class="sr-bar">
				<div class="sr-palette"><span class="sr-hint">${__("Paint with")}</span>${palette}</div>
				<div class="sr-help">${__("Click or drag down a column to paint · right-click: alternate to year end · ⇄ swap a month · Ctrl+Z undo")}</div>
			</div>
			<div class="sr-scroll">
				<div class="sr-grid" style="--months:${months.length}">
					<div class="sr-corner">${__("{0} staff", [rows.length])}</div>${head}
					${body || `<div class="sr-empty sr-span">${__("Nobody matches.")}</div>`}
					${coverage}
				</div>
			</div>
			${this.pending_html()}
		`);
		this.bind_grid();
	}

	is_current(i) {
		const m = this.data.months[i];
		return m.start <= this.data.today && this.data.today <= m.end;
	}

	row_html(r) {
		const cells = this.data.months
			.map((m, i) => {
				const eff = this.effective(r, i);
				const key = `${r.employee}|${i}`;
				const classes = ["sr-cell"];
				if (this.month_locked(i)) classes.push("locked");
				if (this.is_current(i)) classes.push("current");
				if (this.changes.has(key)) classes.push("changed");
				else if (eff.pending) classes.push("carried");
				if (this.refusals[key]) classes.push("refused");
				const title = this.refusals[key] || this.cell_title(eff, m);
				return `<div class="${classes.join(" ")}" data-emp="${r.employee}" data-month="${i}" title="${frappe.utils.escape_html(title)}">${this.chip_html(eff, m)}</div>`;
			})
			.join("");
		return `<div class="sr-name" title="${frappe.utils.escape_html(r.employee)}">
				<b>${frappe.utils.escape_html(r.employee_name || r.employee)}</b>
				<small>${frappe.utils.escape_html(r.department || r.employee)}</small>
			</div>${cells}`;
	}

	chip_html(eff, month) {
		// A month with a mid-month change is drawn split, each part as wide as its days.
		if (!eff.pending && eff.spans && eff.spans.length > 1) {
			const total = eff.spans.reduce((n, s) => n + this.days(s.from, s.to), 0);
			return `<div class="sr-split">${eff.spans
				.map((s) => {
					const w = (100 * this.days(s.from, s.to)) / total;
					const sh = this.shift_by_name[s.shift];
					return `<span style="width:${w}%;--chip:${sh ? sh.color : "var(--gray-500)"}">${w > 30 ? (sh ? sh.label : "·") : ""}</span>`;
				})
				.join("")}</div>`;
		}
		const sh = this.shift_by_name[eff.shift];
		if (sh) return `<span class="sr-chip" style="--chip:${sh.color}">${sh.label}</span>`;
		if (eff.shift) return `<span class="sr-chip fixed" title="${frappe.utils.escape_html(eff.shift)}">${__("fixed")}</span>`;
		return `<span class="sr-chip none">—</span>`;
	}

	cell_title(eff, month) {
		if (eff.spans && eff.spans.length > 1) {
			return eff.spans.map((s) => `${s.shift || __("No shift")}: ${s.from} → ${s.to}`).join("\n");
		}
		const base = `${month.label} ${month.bs_year}: ${eff.shift || __("No shift")}`;
		return eff.pending ? `${base} (${__("not saved")})` : base;
	}

	days(from, to) {
		return frappe.datetime.get_day_diff(to, from) + 1;
	}

	coverage_html(rows) {
		// Head-count per rotational shift per month, from the first day of the month.
		const lines = this.data.shifts.map((s) => {
			const cells = this.data.months
				.map((m, i) => {
					const counts = this.data.shifts.map((x) => rows.filter((r) => this.effective(r, i).shift === x.name).length);
					const n = rows.filter((r) => this.effective(r, i).shift === s.name).length;
					const total = counts.reduce((a, b) => a + b, 0);
					let level = "";
					if (total && n === 0) level = "empty";
					else if (total && n / total > 0.85 && this.data.shifts.length > 1) level = "heavy";
					const bar = total ? Math.round((100 * n) / total) : 0;
					return `<div class="sr-cov ${level}" title="${frappe.utils.escape_html(s.name)}: ${n}">
						<span class="sr-cov-bar" style="--chip:${s.color};width:${bar}%"></span><b>${n}</b></div>`;
				})
				.join("");
			return `<div class="sr-name sr-cov-label"><span class="sr-dot" style="--chip:${s.color}"></span>${s.label} ${__("on shift")}</div>${cells}`;
		});
		return lines.join("");
	}

	pending_html() {
		if (!this.changes.size) return "";
		const people = new Set([...this.changes.keys()].map((k) => k.split("|")[0])).size;
		return `<div class="sr-pending">
			<span>${__("{0} change(s) for {1} employee(s), not saved", [this.changes.size, people])}</span>
			<button class="btn btn-default btn-sm sr-review">${__("Review")}</button>
			<button class="btn btn-default btn-sm sr-discard">${__("Discard")}</button>
			<button class="btn btn-primary btn-sm sr-apply">${__("Apply")}</button>
		</div>`;
	}

	// ── interaction ────────────────────────────────────────────────────────
	bind_grid() {
		const $b = this.$body;
		$b.find(".sr-brush").on("click", (e) => {
			this.brush = $(e.currentTarget).data("shift");
			this.render();
		});
		$b.find(".sr-swap").on("click", (e) => this.swap_month(+$(e.currentTarget).data("month")));
		$b.find(".sr-review").on("click", () => this.review());
		$b.find(".sr-discard").on("click", () => {
			this.snapshot();
			this.changes = new Map();
			this.render();
		});
		$b.find(".sr-apply").on("click", () => this.apply());

		const row_of = (emp) => this.data.rows.find((r) => r.employee === emp);
		$b.find(".sr-cell")
			.on("mousedown", (e) => {
				if (e.button !== 0 || !this.brush) return;
				e.preventDefault();
				this.snapshot();
				this.painting = true;
				this.paint_cell(e.currentTarget, row_of);
			})
			.on("mouseenter", (e) => {
				if (this.painting) this.paint_cell(e.currentTarget, row_of);
			})
			.on("contextmenu", (e) => {
				e.preventDefault();
				const $c = $(e.currentTarget);
				this.alternate(row_of($c.data("emp")), +$c.data("month"));
			});
		$(document)
			.off("mouseup.shiftroster")
			.on("mouseup.shiftroster", () => {
				if (!this.painting) return;
				this.painting = false;
				this.render();
			});
	}

	paint_cell(el, row_of) {
		const $c = $(el);
		const row = row_of($c.data("emp"));
		const i = +$c.data("month");
		if (!row) return;
		this.stage(row, i, this.brush);
		// Redraw just this row's cells while dragging; the full render runs on mouseup.
		$c.closest(".sr-grid")
			.find(`.sr-cell[data-emp="${row.employee}"]`)
			.each((_, cell) => {
				const j = +$(cell).data("month");
				const eff = this.effective(row, j);
				$(cell)
					.toggleClass("changed", this.changes.has(`${row.employee}|${j}`))
					.toggleClass("carried", eff.pending && !this.changes.has(`${row.employee}|${j}`))
					.html(this.chip_html(eff, this.data.months[j]));
			});
	}

	swap_month(i) {
		const shifts = this.data.shifts.map((s) => s.name);
		if (shifts.length < 2) return;
		this.snapshot();
		for (const row of this.data.rows) {
			const at = shifts.indexOf(this.effective(row, i).shift);
			if (at === -1) continue;
			this.stage(row, i, shifts[(at + 1) % shifts.length]);
		}
		this.render();
	}

	alternate(row, from) {
		// 6–2, 12–8, 6–2 … from this month to the year end, starting with the brush.
		if (!row || this.month_locked(from) || !this.is_rotational(this.baseline(row, from))) return;
		const shifts = this.data.shifts.map((s) => s.name);
		if (shifts.length < 2) return;
		this.snapshot();
		let at = Math.max(shifts.indexOf(this.brush), 0);
		for (let i = from; i < this.data.months.length; i++) {
			this.changes.set(`${row.employee}|${i}`, shifts[at]);
			at = (at + 1) % shifts.length;
		}
		this.prune(row);
		this.render();
	}

	prune(row) {
		// Drop changes that repeat what the row already has, so only real moves are sent.
		for (let i = 0; i < this.data.months.length; i++) {
			const key = `${row.employee}|${i}`;
			if (this.changes.get(key) === this.baseline(row, i)) this.changes.delete(key);
		}
	}

	bind_keys() {
		$(document)
			.off("keydown.shiftroster")
			.on("keydown.shiftroster", (e) => {
				if (frappe.get_route()[0] !== "shift-roster" || !this.data) return;
				if ($(e.target).is("input, textarea, select")) return;
				const mod = e.ctrlKey || e.metaKey;
				if (mod && e.key.toLowerCase() === "z" && !e.shiftKey) {
					e.preventDefault();
					this.undo();
				} else if (mod && (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey))) {
					e.preventDefault();
					this.redo();
				} else if (/^[1-9]$/.test(e.key) && this.data.shifts[+e.key - 1]) {
					this.brush = this.data.shifts[+e.key - 1].name;
					this.render();
				}
			});
	}

	undo() {
		if (!this.history.length) return;
		this.future.push(new Map(this.changes));
		this.changes = this.history.pop();
		this.render();
	}

	redo() {
		if (!this.future.length) return;
		this.history.push(new Map(this.changes));
		this.changes = this.future.pop();
		this.render();
	}

	// ── review & apply ─────────────────────────────────────────────────────
	planned_periods() {
		// One period per run of consecutive months a row would change to the same
		// shift, carried months included. A month already wholly on that shift is
		// not sent, so a run never asks for what is there.
		const periods = [];
		for (const row of this.data.rows) {
			let run = null;
			this.data.months.forEach((month, i) => {
				const eff = this.effective(row, i);
				const spans = row.cells[i];
				const differs = eff.pending && !(spans.length === 1 && spans[0].shift === eff.shift);
				if (differs && run && run.shift === eff.shift && run.last === i - 1) {
					run.end = month.end;
					run.last = i;
					run.keys.push(`${row.employee}|${i}`);
					return;
				}
				if (run) periods.push(run);
				run = differs
					? { employee: row.employee, employee_name: row.employee_name, shift: eff.shift, start: month.start, end: month.end, first: i, last: i, keys: [`${row.employee}|${i}`] }
					: null;
			});
			if (run) periods.push(run);
		}
		return periods.sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : 0));
	}

	period_label(p) {
		const m = this.data.months;
		const from = `${m[p.first].label} ${m[p.first].bs_year}`;
		return p.first === p.last ? from : `${from} – ${m[p.last].label} ${m[p.last].bs_year}`;
	}

	review() {
		const html = this.planned_periods()
			.map(
				(p) => `<p><b>${frappe.utils.escape_html(p.employee_name || p.employee)}</b>: ${frappe.utils.escape_html(this.period_label(p))}
				(${frappe.datetime.str_to_user(p.start)} → ${frappe.datetime.str_to_user(p.end)}) → ${frappe.utils.escape_html(p.shift)}</p>`,
			)
			.join("");
		frappe.msgprint({ title: __("Changes to apply"), message: html || __("Nothing would change."), wide: true });
	}

	async apply() {
		const periods = this.planned_periods();
		const company = this.company.get_value();
		let moved = 0;
		const refused = [];
		this.refusals = {};
		if (!periods.length) return;
		frappe.dom.freeze(__("Applying {0} change(s)…", [periods.length]));
		try {
			const { message } = await frappe.call({
				method: PERIODS_API,
				args: { company, changes: periods.map(({ employee, shift, start, end }) => ({ employee, shift, start, end })) },
			});
			moved = message.moved.length;
			for (const r of message.refused) {
				const p = periods.find((x) => x.employee === r.employee && x.start === r.start);
				refused.push(`${r.employee_name || r.employee} (${p ? this.period_label(p) : r.start}): ${r.reason}`);
				(p ? p.keys : []).forEach((key) => (this.refusals[key] = r.reason));
			}
		} finally {
			frappe.dom.unfreeze();
		}
		const lines = [];
		if (moved) lines.push(`<b>${__("{0} change(s) saved", [moved])}</b>`);
		if (refused.length) {
			lines.push(`<b>${__("{0} not saved", [refused.length])}</b>`);
			refused.forEach((r) => lines.push(frappe.utils.escape_html(r)));
		}
		frappe.msgprint({ title: __("Shift Roster"), indicator: refused.length ? "orange" : "green", message: lines.join("<br>") });
		this.loading_after_apply = true;
		this.load();
	}

	// ── style ──────────────────────────────────────────────────────────────
	inject_style() {
		if (document.getElementById("shift-roster-style")) return;
		$(`<style id="shift-roster-style">
			.sr-root { padding-bottom: 70px; }
			.sr-empty { padding: 40px; text-align: center; color: var(--text-muted); }
			.sr-bar { display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between; margin: 8px 0 12px; }
			.sr-palette { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
			.sr-hint, .sr-help { color: var(--text-muted); font-size: var(--text-sm); }
			.sr-brush { display:flex; align-items:center; gap:6px; border:1px solid var(--border-color); background: var(--card-bg);
				border-radius: 999px; padding: 4px 12px 4px 8px; font-weight:600; color: var(--text-color); }
			.sr-brush small { font-weight:400; color: var(--text-muted); }
			.sr-brush.active { border-color: var(--chip); box-shadow: 0 0 0 2px color-mix(in srgb, var(--chip) 35%, transparent); }
			.sr-dot { width:10px; height:10px; border-radius:50%; background: var(--chip); display:inline-block; }
			.sr-scroll { overflow:auto; max-height: calc(100vh - 260px); border:1px solid var(--border-color); border-radius: var(--border-radius-md); background: var(--card-bg); }
			.sr-grid { display:grid; grid-template-columns: minmax(180px, 240px) repeat(var(--months), minmax(64px, 1fr)); user-select:none; }
			.sr-grid > div { border-bottom:1px solid var(--border-color); }
			.sr-corner, .sr-mh { position:sticky; top:0; z-index:2; background: var(--subtle-fg, var(--card-bg)); }
			.sr-corner { left:0; z-index:3; padding:8px 10px; color: var(--text-muted); font-size: var(--text-sm); display:flex; align-items:flex-end; }
			.sr-mh { padding:6px 4px; text-align:center; display:flex; flex-direction:column; align-items:center; gap:1px; font-size: var(--text-sm); }
			.sr-mh small { color: var(--text-muted); font-size: 10px; }
			.sr-mh.current { color: var(--primary); }
			.sr-mh.locked { opacity:.55; }
			.sr-swap { border:none; background:none; color: var(--text-muted); padding:0 4px; border-radius:4px; line-height:1.2; }
			.sr-swap:hover { background: var(--fg-hover-color, var(--gray-100)); color: var(--text-color); }
			.sr-lock { font-size: 10px; }
			.sr-name { position:sticky; left:0; z-index:1; background: var(--card-bg); padding:6px 10px; display:flex; flex-direction:column;
				justify-content:center; min-width:0; border-right:1px solid var(--border-color); }
			.sr-name b, .sr-name small { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
			.sr-name small { color: var(--text-muted); font-size: 11px; }
			.sr-cell { padding:5px 4px; display:flex; align-items:center; justify-content:center; cursor: crosshair; }
			.sr-cell.current { background: color-mix(in srgb, var(--primary) 6%, transparent); }
			.sr-cell.locked { cursor: not-allowed; opacity:.5; }
			.sr-chip { display:inline-flex; align-items:center; justify-content:center; min-width:46px; height:24px; padding:0 8px; border-radius:6px;
				font-size:12px; font-weight:600; color:#fff; background: var(--chip); }
			.sr-chip.fixed, .sr-chip.none { background: var(--control-bg, var(--gray-100)); color: var(--text-muted); font-weight:400; }
			.sr-cell.changed .sr-chip { outline: 2px dashed var(--text-color); outline-offset: 2px; }
			.sr-cell.carried .sr-chip { opacity:.65; background-image: repeating-linear-gradient(45deg, transparent 0 4px, rgba(255,255,255,.25) 4px 8px); }
			.sr-cell.refused .sr-chip { outline: 2px solid var(--red-500, #e24c4c); outline-offset: 2px; }
			.sr-split { display:flex; width:100%; max-width:64px; height:24px; border-radius:6px; overflow:hidden; }
			.sr-split span { background: var(--chip); color:#fff; font-size:11px; font-weight:600; display:flex; align-items:center; justify-content:center; }
			.sr-cov-label { font-size: var(--text-sm); flex-direction:row; align-items:center; justify-content:flex-start; gap:6px; background: var(--subtle-fg, var(--card-bg)); }
			.sr-cov { position:relative; padding:4px; display:flex; align-items:center; justify-content:center; font-size:12px; background: var(--subtle-fg, var(--card-bg)); }
			.sr-cov-bar { position:absolute; left:4px; bottom:3px; height:3px; border-radius:2px; background: var(--chip); max-width: calc(100% - 8px); }
			.sr-cov.empty { color: var(--red-600, #c0392b); background: color-mix(in srgb, var(--red-500, #e24c4c) 12%, transparent); }
			.sr-cov.heavy { color: var(--orange-600, #b9770e); background: color-mix(in srgb, var(--orange-500, #f2994a) 12%, transparent); }
			.sr-span { grid-column: 1 / -1; }
			.sr-pending { position:fixed; left:50%; bottom:20px; transform:translateX(-50%); z-index:20; display:flex; gap:8px; align-items:center;
				background: var(--card-bg); border:1px solid var(--border-color); border-radius: 999px; padding:8px 10px 8px 18px;
				box-shadow: var(--shadow-lg, 0 8px 24px rgba(0,0,0,.15)); }
		</style>`).appendTo("head");
	}
}
