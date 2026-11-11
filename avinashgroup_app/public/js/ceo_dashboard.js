// CEO Dashboard: one screen for the whole group that behaves like a Power BI
// report. The server (avinashgroup_app.ceo_dashboard.api.get_dashboard) sends
// three fiscal years as pre-aggregated rows once; every click is computed here
// in memory, so a click redraws in milliseconds with no round trip.
//
// Timeline: `slot` = half-month position, 24 per fiscal year, oldest year first
// (see api.py). A period is a set of slots ending at the "data through" slot;
// the comparison period is the same set minus 24 (a year earlier, same days).
//
// Interaction model (what a Power BI user expects):
//   - Period, measure, fiscal year and inter-company are global switches.
//   - Clicking a company / segment HIGHLIGHTS: bar charts keep the full bar
//     faint and draw the selected part solid inside it; KPIs, tables and
//     findings narrow to the selection.
//   - Clicking a month narrows the period to that month (Ctrl/Shift adds).
//   - Clicking a customer narrows everything to that customer.
//   - Every row and bar has a drill (›) into a side panel with the next level
//     down, ending at the Sales Invoices themselves.
//   - The whole state lives in the URL, so a view can be bookmarked or sent.
//
// Row layouts:
//   sales: [slot, co, cust, seg, kg, gasRs, netRs, bills]
//   coll:  [slot, co, cust, Rs]
//   customers: [code, name, seg, lastAD, lastBS, internal, firstAD]
//
// Credit and dues comes from a separate snapshot (credit_snapshot.get_credit):
// every limited customer's credit-control position, rebuilt in the background
// every 4 hours. It is a position at one moment, so the period switch does not
// apply to it; company / segment / customer selections do.
//
// Money (money.get_money) is a third call: ledger balances (cash and bank,
// bank loans, what customers owe, what we owe suppliers) at every month end and
// on the data-through day, plus gas purchase cost for the margin per kg. The
// page shows the brief at once and fills the money tiles when it arrives.

window.avinash_ceo_dashboard = (function () {
	"use strict";

	const R_SLOT = 0, R_CO = 1, R_CU = 2, R_SEG = 3, R_KG = 4, R_GAS = 5, R_AMT = 6, R_BILLS = 7;
	const C_AMT = 3;
	const SLOTS = 24;
	// Days without a bill before a customer counts as "gone quiet", and the
	// oldest last bill still counted (older = lost long ago, not news).
	const QUIET_DAYS = 30, QUIET_MAX_DAYS = 365;
	// A company-month whose Rs/kg is this far from the group's that month is flagged.
	const PRICE_ALERT = 0.12;
	// ...but only when the company sold at least this much gas that month (kg).
	const PRICE_ALERT_MIN_KG = 20000;
	const TOP_N = 12;
	// Rows in "Gone quiet": about as tall as the TOP_N-row customer table beside it.
	const QUIET_ROWS = 11;
	// Companies keep being added, so nothing is laid out one-per-company side by
	// side and no company owns a colour (only 8 colours stay distinguishable).
	// Lists show the largest COMPANY_LIST_MAX with "Show all"; the share bar
	// shows the largest SHARE_PARTS_MAX and folds the rest into "Other".
	const COMPANY_LIST_MAX = 8, SHARE_PARTS_MAX = 6;
	// Receipts below this share of billing in the comparison period mean receipts
	// were not booked through Payment Entry back then (demo-nggroup: none before
	// 82/83), so a "collected" change would be meaningless and is not shown.
	const COLL_BOOKED_MIN = 0.2;
	// Ageing buckets for "oldest unpaid bill" (days), and limit-use bands.
	const AGE_BUCKETS = [[0, 7, "0–7 days"], [8, 15, "8–15 days"], [16, 30, "16–30 days"], [31, 60, "31–60 days"], [61, 90, "61–90 days"], [91, 1e9, "Over 90 days"]];
	const NEAR_LIMIT = 0.8;
	// An amount limit this small is a "cash only" setting, not a credit line:
	// 2,441 customers on demo-nggroup have Rs 1-100. They are shown as "Cash
	// only" and left out of the limit-use bands, or every one reads "over limit".
	const CASH_ONLY_MAX = 100;
	const BLOCK_LABEL = ["", "Too many unpaid bills", "Oldest bill too old", "Over amount limit"];
	const BLOCK_SHORT = ["", "Bills", "Days", "Amount"];
	const PERIODS = [["wk", "Week"], ["mtd", "Month"], ["qtd", "Quarter"], ["ytd", "Year to date"], ["r12", "12 months"]];
	// Most fiscal years that can be added together (api.MAX_YEARS_BACK allows
	// that many plus the year before the earliest, for the comparison).
	const MAX_FYS = 6;
	// Gas margin = sale price minus that company's gas purchase price in the same
	// month; gas bought late in a month is sold the next, so a month without a
	// purchase bill uses the month before.
	const BUY_RATE_CARRY = 1;
	// Below this share of volume with a purchase price, the margin is "partial".
	const MARGIN_PARTIAL = 0.5;
	// The page shows this period's figures only: no change badges, no "a year
	// earlier" lines or columns, no explanatory subtitles or notes (the CEO's
	// call, 2026-11-09). The comparison data is still computed; set this to true
	// to bring the badges, lines and columns back.
	const SHOW_COMPARISON = false;
	// Gas margin (sale price minus gas purchase price) is off: most companies have
	// no gas purchase bills, so on demo-nggroup it covered only ~23% of 83/84's
	// volume and was not a fair figure (the CEO's call, 2026-11-10). The code is
	// kept; set true once every gas-selling company books its purchases.
	const SHOW_MARGIN = false;
	// Fiscal-year ticks apply by themselves (no "Show" button, the CEO's call
	// 2026-11-10) this long after the last tick, so ticking three years quickly
	// reloads once, not three times.
	const FY_APPLY_DELAY = 600;
	// "Average price per kg" chart is off: the gas price is fixed, so a price
	// trend tells the CEO nothing (the CEO's call, 2026-11-10).
	const SHOW_PRICE_CHART = false;
	// Rs/kg columns in the scorecard and segment rows follow the same rule.
	const SHOW_RATE = SHOW_PRICE_CHART;
	// A value axis goes below zero only when the most negative value is at least
	// this share of the largest positive one (a real loss, not a few returns).
	const NEG_AXIS_MIN = 0.05;
	// Bar charts print the value on every bar up to this many bars (single series).
	const BAR_LABELS_MAX = 14;
	// Compare chart (series.get_series): what can be put on it, in a fixed order
	// with a fixed colour each (CSS .s-*), and the grains a fiscal year can be
	// read at. Volume (MT) exists for sales and purchases only.
	const CMP_SERIES = [["sales", "Sales", true], ["buy", "Purchases", true], ["coll", "Collected", false], ["exp", "Expenses", false]];
	const CMP_GRAINS = [["half", "Half-year"], ["quarter", "Quarter"], ["month", "Month"], ["halfmonth", "Half-month"], ["week", "Week"], ["day", "Day"]];
	// Dash patterns for the 2nd and 3rd fiscal year on the same chart. Every
	// line on the chart also gets its own colour, in order (CSS .k0-.k5, a
	// validated six-colour set), so several comparisons stay apart.
	const CMP_DASH = ["", "7 5", "2 4"];
	const CMP_COLOURS = 6;
	// Time charts that carry a funnel panel (chart options) and their default shape.
	const CHART_SHAPE = { trend: "bar", coll: "bar", cash: "line", recv: "line", pay: "line" };
	// A change this large (10 = +1,000%) is shown as "12×" instead of a percentage.
	const DELTA_TIMES_FROM = 10;

	// ------------------------------------------------------------ formatting
	const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
	const inr = (v, d = 0) => Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
	function rs(v) {
		const a = Math.abs(v || 0), sign = v < 0 ? "−" : "";
		if (a >= 1e7) return `${sign}Rs ${inr(a / 1e7, a >= 1e9 ? 0 : 2)} Cr`;
		if (a >= 1e5) return `${sign}Rs ${inr(a / 1e5, 1)} L`;
		return `${sign}Rs ${inr(a)}`;
	}
	function mt(kg) {
		const t = (kg || 0) / 1000, a = Math.abs(t);
		return `${t < 0 ? "−" : ""}${inr(a, a < 10 ? 1 : 0)} MT`;
	}
	function axisNum(v, kind) {
		const a = Math.abs(v);
		if (kind === "amt") return a >= 1e7 ? `${inr(v / 1e7, a >= 1e8 || v === 0 ? 0 : 1)} Cr` : a >= 1e5 ? `${inr(v / 1e5, 0)} L` : inr(v);
		if (kind === "rate") return inr(v);
		const t = v / 1000;
		return Math.abs(t) >= 10000 ? `${inr(t / 1000, 0)}K` : inr(t);
	}
	const pct = (a, b) => (b ? (a - b) / Math.abs(b) : null);
	const pctTxt = (d) => `${d >= 0 ? "+" : "−"}${inr(Math.abs(d) * 100, Math.abs(d) < 0.1 ? 1 : 0)}%`;
	function delta(cur, prev, { upGood = true, note = "" } = {}) {
		if (!SHOW_COMPARISON) return "";
		const d = pct(cur, prev);
		const n = note ? `<span class="ceo-delta-note">${esc(note)}</span>` : "";
		if (d == null || !isFinite(d)) return `<span class="ceo-delta flat" title="${esc(__("Nothing in the comparison period"))}">${cur ? __("new") : "—"}</span>${n}`;
		const up = d >= 0, cls = Math.abs(d) < 0.0005 || upGood == null ? "flat" : up === upGood ? "good" : "bad";
		// From a near-zero base a percentage means nothing ("+7,39,959%"): say how many times.
		if (Math.abs(d) >= DELTA_TIMES_FROM) return `<span class="ceo-delta ${cls}" title="${esc(pctTxt(d))}"><span class="ceo-arrow" aria-hidden="true">${up ? "▲" : "▼"}</span>${up && prev > 0 ? `${inr(cur / prev, 0)}×` : pctTxt(d)}</span>${n}`;
		return `<span class="ceo-delta ${cls}"><span class="ceo-arrow" aria-hidden="true">${up ? "▲" : "▼"}</span>${pctTxt(d)}</span>${n}`;
	}
	// "43,541 MT" -> 43,541 with a small MT; "Rs 508 Cr" -> small Rs, 508, small Cr.
	function bigNum(v) {
		const m = /^(−?)(Rs )?([\d,.]+)( [A-Za-z]+)?$/.exec(String(v));
		if (!m) return v;
		return `${m[1]}${m[2] ? `<small class="pre">Rs</small>` : ""}${m[3]}${m[4] ? `<small>${m[4].trim()}</small>` : ""}`;
	}
	function niceTicks(lo, hi, count = 4) {
		if (!(hi > lo)) hi = lo + 1;
		const raw = (hi - lo) / count, mag = Math.pow(10, Math.floor(Math.log10(raw)));
		const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
		const out = [];
		for (let v = Math.floor(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(v);
		if (out[out.length - 1] < hi) out.push(out[out.length - 1] + step);
		return out;
	}
	const daysBetween = (a, b) => Math.round((new Date(b) - new Date(a)) / 86400000);
	function roundTop(x, y, w, h, r) {
		if (!(h > 0)) return "";
		r = Math.min(r, w / 2, h);
		return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
	}

	// ------------------------------------------------------------ the dashboard
	function mount(root, page) {
		const st = {
			data: null,
			fy: null,
			measure: "kg",
			period: "ytd",
			internal: false,
			sel: { co: new Set(), seg: new Set(), mo: new Set(), cust: new Set() },
			custTab: "top",
			month: null,       // picked fiscal month 0-11 (null = the latest); period "mtd"
			quarter: null,     // picked quarter 0-3 (null = the current); period "qtd"
			week: null,        // picked week number from 1 (null = the latest); period "wk"
			base: null,        // the server's sales / coll before a week was folded in
			weekKey: null,
			weekInfo: null,
			custSearch: "",
			tables: new Set(),
			drawer: null,
			tips: [],
			W: null,
			credit: null,      // raw snapshot from the server
			cr: null,          // prepared rows (see prepareCredit)
			crTab: "hold",
			crBucket: null,
			coShowAll: { company: false, crco: false, recv: false, buyco: false },
			ddOpen: false,
			ddSearch: "",
			fys: [],           // fiscal years added together (empty or one = the single year st.fy)
			fyOpen: false,     // fiscal year picker open
			fyDraft: null,     // ticks not yet loaded (applied FY_APPLY_DELAY after the last tick)
			ser: null,         // day-by-day series for the Compare chart (series.get_series)
			cmp: { grain: "auto", series: ["sales"], years: [] },   // trend chart options ("auto" grain = follow the period)
			shape: {},         // chart name -> "bar" | "line" where it differs from CHART_SHAPE
			pop: null,         // the chart whose funnel panel is open
			pdOpen: false,     // period dropdown open
			buying: null,      // purchases from the server (buying.get_buying)
			by: null,          // prepared (see prepareBuying)
			money: null,       // raw ledger figures from the server
			mn: null,          // prepared (see prepareMoney)
		};
		readUrl();

		root.classList.add("ceo-host");
		root.innerHTML = `<div class="ceo" role="region" aria-label="${esc(__("CEO Dashboard"))}">
			<div class="ceo-filters" data-slot="filters"></div>
			<div class="ceo-chips" data-slot="chips" hidden></div>
			<div data-slot="main">${skeleton()}</div>
			<aside class="ceo-drawer" data-slot="drawer" hidden aria-label="${esc(__("Details"))}"></aside>
			<div class="ceo-tip" role="tooltip" hidden></div>
		</div>`;
		const $ = (sel) => root.querySelector(sel);
		const slot = (n) => root.querySelector(`[data-slot="${n}"]`);
		// Card subtitles are off (no explanatory text on the page); kept as a no-op so callers stay simple.
		const sub = () => {};
		const tipEl = $(".ceo-tip");

		function skeleton() {
			const b = (cls) => `<div class="ceo-skel ${cls}"></div>`;
			return `<div class="ceo-kpis six">${b("kpi hero")}${b("kpi")}${b("kpi")}${b("kpi")}${b("kpi")}${b("kpi")}</div>${b("wide")}<div class="ceo-grid">${b("span-8 tall")}${b("span-4 tall")}${b("span-12 tall")}</div>`;
		}

		// -------------------------------------------------------- URL state
		function readUrl() {
			const q = new URLSearchParams(location.search);
			if (q.get("fy")) { st.fys = q.get("fy").split(",").filter(Boolean).slice(0, MAX_FYS).sort(fyCmp); st.fy = st.fys[st.fys.length - 1]; }
			if (["kg", "amt"].includes(q.get("m"))) st.measure = q.get("m");
			if (PERIODS.some(([p]) => p === q.get("p"))) st.period = q.get("p");
			if (q.get("ic") === "1") st.internal = true;
			const int = (k, max) => { const v = parseInt(q.get(k), 10); return v >= 0 && v <= max ? v : null; };
			st.month = int("pm", 11); st.quarter = int("pq", 3); st.week = int("pw", 60) || null;
			st.pending = { co: q.get("co"), seg: q.get("seg"), mo: q.get("mo"), cu: q.get("cu") };
			if (CMP_GRAINS.some(([g]) => g === q.get("cg"))) st.cmp.grain = q.get("cg");
			for (const kv of (q.get("sh") || "").split(",")) { const [k, v] = kv.split(":"); if (CHART_SHAPE[k] && ["bar", "line"].includes(v)) st.shape[k] = v; }
			const cs = (q.get("cs") || "").split(",").filter((k) => CMP_SERIES.some(([x]) => x === k));
			if (cs.length) st.cmp.series = cs;
			st.cmp.years = (q.get("cy") || "").split(",").filter(Boolean).slice(0, 2);
		}
		function applyPendingUrl() {
			const p = st.pending, d = st.data;
			if (!p) return;
			st.pending = null;
			const abbrs = new Map(d.companies.map((c, i) => [c.abbr, i]));
			(p.co || "").split(",").filter(Boolean).forEach((a) => abbrs.has(a) && st.sel.co.add(abbrs.get(a)));
			(p.seg || "").split(",").filter(Boolean).forEach((s) => { const i = d.segments.indexOf(s); if (i >= 0) st.sel.seg.add(i); });
			(p.mo || "").split(",").filter(Boolean).forEach((m) => { const i = +m; if (i >= 0 && i < NM()) st.sel.mo.add(i); });
			if (p.cu) { const i = d.customers.findIndex((c) => c[0] === p.cu); if (i >= 0) st.sel.cust.add(i); }
		}
		function writeUrl() {
			const d = st.data, q = new URLSearchParams();
			if (d && (multiYear() || (st.fy && st.fy !== d.fiscal_years[0]))) q.set("fy", multiYear() ? st.fys.join(",") : st.fy);
			if (st.measure !== "kg") q.set("m", st.measure);
			if (st.period !== "ytd") q.set("p", st.period);
			if (st.period === "mtd" && st.month != null) q.set("pm", st.month);
			if (st.period === "qtd" && st.quarter != null) q.set("pq", st.quarter);
			if (st.period === "wk" && st.week != null) q.set("pw", st.week);
			if (st.internal) q.set("ic", "1");
			if (st.cmp.grain !== "auto") q.set("cg", st.cmp.grain);
			const sh = Object.entries(st.shape).filter(([k, v]) => CHART_SHAPE[k] && CHART_SHAPE[k] !== v).map(([k, v]) => `${k}:${v}`).join(",");
			if (sh) q.set("sh", sh);
			if (st.cmp.series.join() !== "sales") q.set("cs", st.cmp.series.join(","));
			if (st.cmp.years.length) q.set("cy", st.cmp.years.join(","));
			if (d) {
				if (st.sel.co.size) q.set("co", [...st.sel.co].map((i) => d.companies[i].abbr).join(","));
				if (st.sel.seg.size) q.set("seg", [...st.sel.seg].map((i) => d.segments[i]).join(","));
				if (st.sel.mo.size) q.set("mo", [...st.sel.mo].sort((a, b) => a - b).join(","));
				if (st.sel.cust.size) q.set("cu", d.customers[[...st.sel.cust][0]][0]);
			}
			const qs = q.toString();
			if (location.pathname.indexOf("ceo-dashboard") === -1) return;   // user navigated away
			history.replaceState(history.state, "", location.pathname + (qs ? `?${qs}` : ""));
		}

		// -------------------------------------------------------- fiscal years
		// "83/84" -> 83, for ordering and spans. Several picked years are added
		// together: the server sends every picked year plus one before the
		// earliest (years_back), so each year is compared with the year before.
		// Function declarations, not const: readUrl() runs at the top of mount and
		// sorts with fyCmp before this line is reached.
		function fyNum(f) { return parseInt(f, 10); }
		function fyCmp(a, b) { return fyNum(a) - fyNum(b); }
		const multiYear = () => st.fys.length > 1;
		// The latest picked fiscal year has ended (e.g. 82/83 picked in 83/84).
		// Credit and dues and "Gone quiet" describe today, not that year, so they
		// are hidden then (the CEO saw today's holds under 82/83, 2026-11-10).
		const pastYear = () => { const b = D().month_bounds; return b[b.length - 1][1] < D().today; };
		const yearsBack = () => (multiYear() ? Math.max(2, fyNum(st.fys[st.fys.length - 1]) - fyNum(st.fys[0]) + 1) : 2);

		// -------------------------------------------------------- time model
		const D = () => st.data;
		// Timeline length: 24 slots / 12 months per fiscal year the server sent.
		const NS = () => D().years.length * 24, NM = () => D().years.length * 12;
		// A picked week is fetched on demand (periods.get_days) and folded into the
		// fact table on two slots past the real ones: wkS() for the week and
		// wkC() = wkS() - 24 for the same weekdays a year earlier, so inWin / inCmp
		// work unchanged. Monthly series index slot >> 1 into NM()-long arrays, so
		// these slots fall outside them and never reach a month chart.
		const wkC = () => NS(), wkS = () => NS() + 24;
		const P = () => D().through_slot;              // "data through" slot (early half of that month)
		const PM = () => P() >> 1;                     // absolute month index of the data-through month
		const FY0 = () => PM() - (PM() % 12);         // first month of the chosen fiscal year on the timeline
		const curQuarter = () => Math.floor((PM() - FY0()) / 3);
		function windowSlots() {
			const w = new Uint8Array(wkS() + 1), p = P();
			// Comparison = the period one year (24 slots) earlier; flag 2, independent of flag 1.
			const cmp = () => { for (let s = 0; s + SLOTS < w.length; s++) if (w[s + SLOTS] & 1) w[s] |= 2; return w; };
			if (st.sel.mo.size) {
				for (const m of st.sel.mo) for (const s of [m * 2, m * 2 + 1]) if (s <= p) w[s] = 1;
				return cmp();
			}
			if (multiYear()) {
				for (const f of st.fys) { const y = D().years.indexOf(f); if (y >= 0) for (let s = y * 24; s < y * 24 + 24 && s <= p; s++) w[s] = 1; }
				return cmp();
			}
			if (st.period === "wk") { w[wkS()] = 1; return cmp(); }
			const pm = PM(), b = FY0();
			let start, end = p;
			if (st.period === "mtd") { const m = st.month == null ? pm : Math.min(pm, b + st.month); start = m * 2; end = Math.min(p, m * 2 + 1); }
			else if (st.period === "qtd") { const qs = b + 3 * Math.min(curQuarter(), st.quarter == null ? curQuarter() : st.quarter); start = qs * 2; end = Math.min(p, qs * 2 + 5); }
			else start = { ytd: b * 2, r12: p - 23 }[st.period];
			for (let s = Math.max(0, start); s <= end; s++) w[s] = 1;
			return cmp();
		}
		const inWin = (W, s) => (W[s] & 1) === 1;
		const inCmp = (W, s) => (W[s] & 2) === 2;
		const monthIn = (W, m) => inWin(W, m * 2) || inWin(W, m * 2 + 1);
		// Weeks of the chosen fiscal year up to "data through": Sunday to Saturday,
		// week 1 from the first day of the year to the first Saturday.
		function fyWeeks() {
			const d = D(), day = 86400000, iso = (t) => new Date(t).toISOString().slice(0, 10);
			const start = Date.parse(d.month_bounds[FY0()][0] + "T00:00:00Z"), last = d.through, out = [];
			let a = start, e = start + ((6 - new Date(start).getUTCDay() + 7) % 7) * day;
			while (iso(a) <= last) { out.push([iso(a), iso(e) < last ? iso(e) : last]); a = e + day; e = a + 6 * day; }
			return out;
		}
		// "11 Bhadra" for an AD date on the timeline.
		function bsDay(isoDate) {
			const mb = D().month_bounds;
			for (let i = 0; i < mb.length; i++) if (isoDate >= mb[i][0] && isoDate <= mb[i][1]) return { m: i, day: daysBetween(mb[i][0], isoDate) + 1 };
			return null;
		}
		const bsShort = (isoDate) => { const x = bsDay(isoDate); return x ? `${x.day} ${monthName(x.m)}` : isoDate; };
		const weekLabel = (n, [a, b]) => `${__("Week {0}", [n])} · ${bsShort(a)}${a === b ? "" : ` – ${bsShort(b)}`}`;
		function loadWeek() {
			const weeks = fyWeeks();
			if (!weeks.length) return;
			if (st.week == null || st.week > weeks.length) st.week = weeks.length;
			const [a, b] = weeks[st.week - 1], key = `${st.fy}:${a}:${b}`;
			if (st.weekKey === key) return;
			const el = $(".ceo"), fy = st.fy;
			el.classList.add("is-loading");
			frappe.call({
				method: "avinashgroup_app.ceo_dashboard.periods.get_days",
				args: { fiscal_year: fy, from_date: a, to_date: b },
				callback: (r) => {
					el.classList.remove("is-loading");
					if (!r.message || st.fy !== fy || st.period !== "wk") return;
					applyWeek(r.message, key);
					render(true);
				},
				error: () => el.classList.remove("is-loading"),
			});
		}
		function applyWeek(w, key) {
			const d = D(), byCode = new Map(d.customers.map((x, i) => [x[0], i]));
			const cu = (code) => {
				let i = byCode.get(code);
				if (i == null) { const x = w.customers[code] || [code, d.segments.length - 1, 0]; i = d.customers.length; d.customers.push([code, x[0], x[1], null, null, x[2], null]); byCode.set(code, i); }
				return i;
			};
			d.sales = st.base.sales.concat(w.sales.map((r) => [r[0] ? wkS() : wkC(), r[1], cu(r[2]), r[3], r[4], r[5], r[6], r[7]]));
			d.coll = st.base.coll.concat(w.coll.map((r) => [r[0] ? wkS() : wkC(), r[1], cu(r[2]), r[3]]));
			const bd = bsDay(w.from);
			st.weekInfo = { ...w, mo: bd ? bd.m : PM() };
			st.weekKey = key;
		}
		const monthName = (m) => D().months[m % 12];
		const yearOf = (m) => D().years[Math.floor(m / 12)] || "";
		function bsYear(m) {   // "83/84" -> 2083 for Shrawan..Chaitra, 2084 for Baisakh..Ashadh
			const y = 2000 + parseInt(yearOf(m), 10);
			return isNaN(y) ? "" : y + (m % 12 >= 9 ? 1 : 0);
		}
		const monthLabel = (m, short) => `${short ? monthName(m).slice(0, 3) : monthName(m)} ${bsYear(m)}`;
		function periodLabel(W) {
			if (multiYear() && !st.sel.mo.size) return `${st.fys.join(" + ")}${st.fys[st.fys.length - 1] === D().fiscal_years[0] ? ` (${__("to {0}", [D().through_label])})` : ""}`;
			if (inWin(W, wkS())) { const wk = fyWeeks(); return st.week && wk[st.week - 1] ? `${weekLabel(st.week, wk[st.week - 1])} ${bsYear(FY0())}` : __("Week"); }
			const months = [];
			for (let m = 0; m < NM(); m++) if (monthIn(W, m)) months.push(m);
			if (!months.length) return "";
			const a = months[0], b = months[months.length - 1];
			if (b - a + 1 !== months.length) return months.map((m) => monthLabel(m, true)).join(", ");
			const end = b === PM() ? D().through_label : monthLabel(b);
			if (a === b) return b === PM() ? `1 – ${end}` : monthLabel(a);
			// Rolling 12 starts in the late half of a month: say the exact day.
			const startsLate = !inWin(W, a * 2) && inWin(W, a * 2 + 1);
			return `${startsLate ? `${D().through_day + 1} ` : ""}${monthLabel(a)} – ${end}`;
		}
		function compareLabel() {
			if (st.sel.mo.size) return __("vs the same months a year earlier");
			if (multiYear()) return __("vs each year's previous year ({0})", [st.fys.map((f) => { const n = fyNum(f) - 1; return `${n}/${n + 1}`; }).join(" + ")]);
			if (st.period === "wk") return st.weekInfo ? __("vs the same weekdays a year earlier ({0})", [st.weekInfo.prev_label]) : __("vs the same weekdays a year earlier");
			if (st.period === "mtd" && st.month != null && FY0() + st.month < PM()) return __("vs the same month last year");
			if (st.period === "qtd" && st.quarter != null && st.quarter < curQuarter()) return __("vs the same quarter last year");
			return { mtd: __("vs the same days last year"), qtd: __("vs the same days last year"), ytd: __("vs the same period last year"), r12: __("vs the 12 months before") }[st.period];
		}

		// -------------------------------------------------------- filters
		const okInternal = (cu) => st.internal || !D().customers[cu][5];
		// pass(row, skip): row passes the selection on every dimension not named in `skip`.
		function pass(r, skip = "") {
			if (!okInternal(r[R_CU])) return false;
			const s = st.sel;
			if (s.co.size && !skip.includes("co") && !s.co.has(r[R_CO])) return false;
			if (s.seg.size && !skip.includes("seg") && !s.seg.has(r[R_SEG])) return false;
			if (s.cust.size && !skip.includes("cust") && !s.cust.has(r[R_CU])) return false;
			return true;
		}
		function passColl(r, skip = "") {
			if (!okInternal(r[R_CU])) return false;
			const s = st.sel;
			if (s.co.size && !skip.includes("co") && !s.co.has(r[R_CO])) return false;
			if (s.seg.size && !skip.includes("seg") && !s.seg.has(D().customers[r[R_CU]][2])) return false;
			if (s.cust.size && !skip.includes("cust") && !s.cust.has(r[R_CU])) return false;
			return true;
		}
		const mv = (r) => (st.measure === "kg" ? r[R_KG] : r[R_AMT]);
		const fmtM = (v) => (st.measure === "kg" ? mt(v) : rs(v));
		const measureName = () => (st.measure === "kg" ? __("LP Gas volume") : __("Net sales"));
		const dimState = (dim, val) => (!st.sel[dim].size ? "" : st.sel[dim].has(val) ? "is-sel" : "is-dim");
		const highlightActive = () => st.sel.co.size > 0 || st.sel.seg.size > 0;
		const narrowed = () => st.sel.co.size > 0 || st.sel.seg.size > 0 || st.sel.cust.size > 0;

		// Totals over the window (cur) and the comparison window (prev).
		function totals(W, rowPass, collPass) {
			const t = { kg: 0, amt: 0, gas: 0, gasKg: 0, coll: 0, cust: new Set(), kgP: 0, amtP: 0, gasP: 0, gasKgP: 0, collP: 0, custP: new Set() };
			for (const r of D().sales) {
				const s = r[R_SLOT], c = inWin(W, s), p = inCmp(W, s);
				if (!(c || p) || !rowPass(r)) continue;
				if (c) { t.kg += r[R_KG]; t.amt += r[R_AMT]; t.gas += r[R_GAS]; t.gasKg += r[R_GAS] ? r[R_KG] : 0; if (r[R_AMT] > 0) t.cust.add(r[R_CU]); }
				if (p) { t.kgP += r[R_KG]; t.amtP += r[R_AMT]; t.gasP += r[R_GAS]; t.gasKgP += r[R_GAS] ? r[R_KG] : 0; if (r[R_AMT] > 0) t.custP.add(r[R_CU]); }
			}
			for (const r of D().coll) {
				const s = r[R_SLOT];
				if (!collPass(r)) continue;
				if (inWin(W, s)) t.coll += r[C_AMT];
				if (inCmp(W, s)) t.collP += r[C_AMT];
			}
			t.rate = t.gasKg ? t.gas / t.gasKg : 0;
			t.rateP = t.gasKgP ? t.gasP / t.gasKgP : 0;
			return t;
		}
		// Per-month sums over the whole timeline for rows passing rowPass.
		function monthly(rowPass, fn, src) {
			const out = new Float64Array(NM());
			for (const r of src || D().sales) if (rowPass(r)) out[r[R_SLOT] >> 1] += fn(r);
			return out;
		}
		const last24 = (arr) => { const pm = PM(); return Array.from(arr).slice(pm - 23, pm + 1); };
		const winMonths = (W) => { const from = PM() - 23; return Array.from({ length: 24 }, (_, i) => monthIn(W, from + i)); };

		// -------------------------------------------------------- selection
		function toggle(dim, val, additive) {
			const set = st.sel[dim];
			if (dim === "cust") additive = false;
			if (additive) set.has(val) ? set.delete(val) : set.add(val);
			else if (set.size === 1 && set.has(val)) set.clear();
			else { set.clear(); set.add(val); }
			render(true);
		}

		// -------------------------------------------------------- tooltip
		function tip(html) { st.tips.push(html); return st.tips.length - 1; }
		function showTip(el, ev) {
			const i = el.getAttribute("data-tip");
			if (i == null || st.tips[i] == null) return hideTip();
			tipEl.innerHTML = st.tips[i];
			tipEl.hidden = false;
			const host = $(".ceo").getBoundingClientRect();
			let x, y;
			if (ev && ev.clientX != null && ev.type !== "focusin") { x = ev.clientX; y = ev.clientY; }
			else { const b = el.getBoundingClientRect(); x = b.left + b.width / 2; y = b.top; }
			const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
			let left = x - host.left + 16, top = y - host.top - h - 14;
			if (left + w > host.width - 4) left = x - host.left - w - 16;
			if (top < 0) top = y - host.top + 20;
			tipEl.style.left = `${Math.max(4, left)}px`;
			tipEl.style.top = `${top}px`;
		}
		function hideTip() { tipEl.hidden = true; }
		// Tooltip: title and value rows. Comparison rows (key "prev") and the foot
		// (change badge, notes) show only with SHOW_COMPARISON.
		function tipRows(title, rows, foot) {
			if (!SHOW_COMPARISON) rows = rows.filter(([key]) => !String(key || "").startsWith("prev"));
			return `<div class="ceo-tip-title">${esc(title)}</div>` + rows.map(([key, label, value]) =>
				`<div class="ceo-tip-row"><span class="ceo-key ${key || ""}"></span><strong>${value}</strong><span>${esc(label)}</span></div>`).join("") + (foot && SHOW_COMPARISON ? `<div class="ceo-tip-foot">${foot}</div>` : "");
		}

		// -------------------------------------------------------- events
		root.addEventListener("click", (ev) => {
			const act = ev.target.closest("[data-act]");
			if (act) {
				ev.preventDefault();
				const a = act.dataset.act, v = act.dataset.val;
				if (a === "measure") { st.measure = v; render(true); }
				else if (a === "period") { st.period = v; st.sel.mo.clear(); if (v === "wk") loadWeek(); if (!["mtd", "qtd", "wk"].includes(v)) st.pdOpen = false; render(true); }
				else if (a === "pd-toggle") { st.pdOpen = !st.pdOpen; st.ddOpen = false; st.fyOpen = false; renderFilters(); }
				else if (a === "pick") { const n = +v; if (st.period === "mtd") st.month = n; else if (st.period === "qtd") st.quarter = n; else if (st.period === "wk") { st.week = n; loadWeek(); } st.pdOpen = false; render(true); }
				else if (a === "internal") { st.internal = v === "1"; render(true); }
				else if (a === "reset") { Object.values(st.sel).forEach((s) => s.clear()); render(true); }
				else if (a === "unsel") { st.sel[act.dataset.dim].delete(+v); render(true); }
				else if (a === "table") { const n = act.dataset.name; st.tables.has(n) ? st.tables.delete(n) : st.tables.add(n); render(false); }
				else if (a === "custtab") { st.custTab = v; renderCustomers(); if (act.closest("[data-slot='insights']")) slot("customers").scrollIntoView({ behavior: "smooth", block: "center" }); }
				else if (a === "drill") openDrawer(act.dataset.kind, +v);
				else if (a === "close-drawer") closeDrawer();
				else if (a === "open-list") frappe.set_route("List", act.dataset.doctype || "Sales Invoice", JSON.parse(act.dataset.filters));
				else if (a === "open-doc") frappe.set_route("Form", act.dataset.doctype, v);
				else if (a === "print") window.print();
				else if (a === "fy-toggle") { st.fyOpen = !st.fyOpen; st.ddOpen = false; renderFilters(); }
				else if (a === "fy-pick") {
					const cur = st.fyDraft || (multiYear() ? st.fys.slice() : [st.data.fiscal_year]);
					const next = cur.includes(v) ? cur.filter((f) => f !== v) : [...cur, v].slice(0, MAX_FYS);
					if (!next.length) return;   // at least one year stays ticked
					st.fyDraft = next;
					renderFilters();
					clearTimeout(st.fyTimer);
					st.fyTimer = setTimeout(() => { st.fyTimer = null; applyFys(); }, FY_APPLY_DELAY);
				}
				else if (a === "dd-toggle") { st.ddOpen = !st.ddOpen; st.ddSearch = ""; renderFilters(); if (st.ddOpen) { const i = root.querySelector(".ceo-ddsearch"); i && i.focus(); } }
				else if (a === "dd-close") { st.ddOpen = false; renderFilters(); }
				else if (a === "dd-all") { st.sel.co.clear(); st.ddOpen = false; render(true); }
				else if (a === "dd-pick") { const i = +v; st.sel.co.has(i) ? st.sel.co.delete(i) : st.sel.co.add(i); render(true); }
				else if (a === "show-all") { st.coShowAll[v] = !st.coShowAll[v]; render(false); }
				else if (a === "copts") { st.pop = st.pop === v ? null : v; renderPop(); }
				else if (a === "shape") { st.shape[act.dataset.name] = v; render(false); renderPop(); }
				else if (a === "cmp-grain") { st.cmp.grain = v; render(false); renderPop(); }
				else if (a === "cmp-tog") { st.cmp.series = st.cmp.series.includes(v) ? st.cmp.series.filter((k) => k !== v) : CMP_SERIES.map(([k]) => k).filter((k) => k === v || st.cmp.series.includes(k)); if (!st.cmp.series.length) st.cmp.series = ["sales"]; render(false); renderPop(); }
				else if (a === "cmp-year") { st.cmp.years = st.cmp.years.includes(v) ? st.cmp.years.filter((y) => y !== v) : [...st.cmp.years, v].slice(-2); render(false); renderPop(); }
				else if (a === "cr-tab") { st.crTab = v; st.crBucket = null; renderCredit(); }
				else if (a === "cr-bucket") { st.crBucket = st.crBucket === +v ? null : +v; st.crTab = "all"; renderCredit(); }
				else if (a === "cr-refresh") {
					frappe.call({ method: "avinashgroup_app.ceo_dashboard.credit_snapshot.refresh", callback: (r) => {
						frappe.show_alert({ message: r.message && r.message.already ? __("A refresh is already running.") : __("Refreshing credit positions. This takes several minutes; reload the page afterwards."), indicator: "blue" });
					} });
				}
				else if (a === "goto-credit") slot("credit-kpis").scrollIntoView({ behavior: "smooth", block: "start" });
				else if (a === "chart-month") {
					// A month of the chosen year opens as that month (day by day); an older one as a month filter.
					const mo = +v, b = FY0();
					st.sel.mo.clear();
					// With years added together the period buttons are off, so a month opens as a month filter.
					if (!multiYear() && mo >= b && mo <= PM()) { st.period = "mtd"; st.month = mo - b; } else st.sel.mo.add(mo);
					render(true);
				}
				else if (a === "goto") { const t = root.querySelector(`[data-anchor="${v}"]`) || slot(v); t && t.scrollIntoView({ behavior: "smooth", block: "start" }); }
				return;
			}
			const m = ev.target.closest("[data-dim]");
			if (m) { ev.preventDefault(); toggle(m.dataset.dim, +m.dataset.val, ev.ctrlKey || ev.metaKey || ev.shiftKey); }
		});
		document.addEventListener("pointerdown", (ev) => {
			if (st.ddOpen && !ev.target.closest(".ceo-dd")) { st.ddOpen = false; st.data && renderFilters(); }
			if (st.pdOpen && !ev.target.closest("[data-dd='pd']")) { st.pdOpen = false; st.data && renderFilters(); }
			if (st.fyOpen && !ev.target.closest("[data-dd='fy']")) { st.fyOpen = false; st.data && renderFilters(); }
			if (st.pop && !ev.target.closest(".ceo-optwrap")) { st.pop = null; renderPop(); }
		});
		root.addEventListener("keydown", (ev) => {
			if (ev.key === "Escape" && st.ddOpen) { st.ddOpen = false; renderFilters(); return; }
			if (ev.key === "Escape" && st.pdOpen) { st.pdOpen = false; renderFilters(); return; }
			if (ev.key === "Escape" && st.fyOpen) { st.fyOpen = false; renderFilters(); return; }
			if (ev.key === "Escape" && st.pop) { st.pop = null; renderPop(); return; }
			if (ev.key === "Escape" && st.drawer) { closeDrawer(); return; }
			if (ev.key !== "Enter" && ev.key !== " ") return;
			const m = ev.target.closest("[data-dim]");
			if (m && !ev.target.closest("input,select,button")) { ev.preventDefault(); toggle(m.dataset.dim, +m.dataset.val, ev.ctrlKey || ev.metaKey || ev.shiftKey); }
		});
		root.addEventListener("pointermove", (ev) => {
			const t = ev.target.closest("[data-tip]");
			t ? showTip(t, ev) : hideTip();
			root.querySelectorAll(".ceo-band.hover").forEach((b) => b !== t && b.classList.remove("hover"));
			if (t && t.classList.contains("ceo-band")) t.classList.add("hover");
		});
		root.addEventListener("pointerleave", () => { hideTip(); root.querySelectorAll(".ceo-band.hover").forEach((b) => b.classList.remove("hover")); });
		root.addEventListener("focusin", (ev) => { const t = ev.target.closest("[data-tip]"); t ? showTip(t, ev) : hideTip(); });
		root.addEventListener("focusout", hideTip);
		root.addEventListener("change", (ev) => {
			if (ev.target.matches("[data-change='pick']")) {
				const v = +ev.target.value;
				if (st.period === "mtd") st.month = v; else if (st.period === "qtd") st.quarter = v; else if (st.period === "wk") { st.week = v; loadWeek(); }
				render(true);
			}
		});
		root.addEventListener("input", (ev) => {
			if (ev.target.matches("[data-input='search']")) { st.custSearch = ev.target.value; renderCustomers(); }
			if (ev.target.matches("[data-input='dd-search']")) {
				st.ddSearch = ev.target.value;
				const pos = ev.target.selectionStart;
				renderFilters();
				const i = root.querySelector(".ceo-ddsearch"); if (i) { i.focus(); i.setSelectionRange(pos, pos); }
			}
		});
		let rzTimer, lastW = 0;
		new ResizeObserver(() => {
			const w = root.clientWidth;
			if (Math.abs(w - lastW) < 8) return;
			lastW = w;
			clearTimeout(rzTimer);
			rzTimer = setTimeout(() => st.data && render(false), 150);
		}).observe(root);

		if (page) {
			page.set_secondary_action(__("Refresh"), () => { load(true); loadCredit(); }, "refresh");
			page.add_menu_item(__("Print / PDF"), () => window.print());
		}

		// -------------------------------------------------------- load
		function load(force) {
			const el = $(".ceo");
			el.classList.add("is-loading");
			frappe.call({
				method: "avinashgroup_app.ceo_dashboard.api.get_dashboard",
				args: { fiscal_year: st.fy, force: force ? 1 : 0, years_back: yearsBack() },
				callback: (r) => {
					el.classList.remove("is-loading");
					if (!r.message) return;
					st.data = r.message;
					if (st.fyDraft && !st.fyTimer) st.fyDraft = null;   // drafted ticks are now the loaded years
					st.base = { sales: st.data.sales, coll: st.data.coll };
					st.weekKey = st.weekInfo = null;
					// Money and day rows index the old data's customers and timeline: drop
					// them before drawing; loadMoney / ensureDaily fetch them again.
					st.money = st.mn = null;
					st.buying = st.by = null;
					st.daily = null;
					st.fy = st.data.fiscal_year;
					st.cr = null;
					cmpDayInfo.clear();   // dates were placed on the previous timeline
					applyPendingUrl();
					prepareCredit();
					render(true);
					loadMoney(force);
					loadBuying(force);
					if (st.ser && force) loadSeries(true);
					if (st.period === "wk") loadWeek();
				},
				error: () => el.classList.remove("is-loading"),
			});
		}

		function loadCredit() {
			frappe.call({
				method: "avinashgroup_app.ceo_dashboard.credit_snapshot.get_credit",
				callback: (r) => {
					st.credit = r.message || { missing: true };
					st.cr = null;
					if (st.data) { prepareCredit(); render(false); }
				},
			});
		}
		function loadSeries(force) {
			const fy = st.fy, yb = yearsBack();
			if (st.ser && !st.ser.failed && st.ser.fiscal_year === fy && st.ser.years_back === yb && !force) return;
			if (st.ser && st.ser.loading && st.ser.fiscal_year === fy) return;
			st.ser = { loading: true, fiscal_year: fy };
			frappe.call({
				method: "avinashgroup_app.ceo_dashboard.series.get_series",
				args: { fiscal_year: fy, years_back: yb, force: force ? 1 : 0 },
				callback: (r) => { if (st.fy !== fy || !r.message) return; st.ser = { ...r.message, years_back: yb }; st.data && renderTrend(); },
				error: () => { if (st.fy === fy) { st.ser = { failed: true }; st.data && renderTrend(); } },
			});
		}
		function loadMoney(force) {
			const fy = st.fy;
			st.money = null;
			st.mn = null;
			frappe.call({
				method: "avinashgroup_app.ceo_dashboard.money.get_money",
				args: { fiscal_year: fy, force: force ? 1 : 0, years_back: yearsBack() },
				callback: (r) => { if (st.fy !== fy) return; st.money = r.message || { failed: true }; prepareMoney(); st.data && render(false); },   // money.months matches the same years_back
				error: () => { if (st.fy !== fy) return; st.money = { failed: true }; st.data && render(false); },
			});
		}
		const padM = (a) => { const o = new Array(NM()).fill(null); a.forEach((v, i) => (o[i] = v)); return o; };
		// Ledger rows onto the dashboard's indexes. Customers with a balance but no
		// bills in three years are added to the customer list (as prepareCredit does).
		function prepareMoney() {
			const m = st.money, d = st.data;
			if (!m || m.failed || !d || st.mn || m.fiscal_year !== d.fiscal_year) return;
			const byCode = new Map(d.customers.map((x, i) => [x[0], i]));
			const recv = m.recv.map((r) => {
				let cu = byCode.get(r[1]);
				if (cu == null) { cu = d.customers.length; d.customers.push([r[1], r[2], r[3], null, null, r[4], null]); byCode.set(r[1], cu); }
				return { co: r[0], cu, seg: r[3], now: r[5], ly: r[6] };
			});
			const buy = new Map();
			for (const [mo, co, kg, amt] of m.buy) if (kg > 0) buy.set(co * 100 + mo, amt / kg);
			st.mn = {
				recv,
				recvM: m.recv_m.map((r) => ({ co: r[0], seg: r[1], internal: r[2], owed: padM(r[3]) })),
				cash: m.cash.map((r) => ({ co: r[0], kind: r[1], name: r[2], m: padM(r[3]), now: r[4], ly: r[5] })),
				pay: m.pay.map((r) => ({ co: r[0], code: r[1], name: r[2], internal: r[3], now: r[4], ly: r[5], bill: r[6] })),
				payM: m.pay_m.map((r) => ({ co: r[0], internal: r[1], owed: padM(r[2]) })),
				buy,
			};
		}
		const passCo = (co) => !st.sel.co.size || st.sel.co.has(co);
		const passRecv = (x) => okInternal(x.cu) && passCo(x.co) && (!st.sel.seg.size || st.sel.seg.has(x.seg)) && (!st.sel.cust.size || st.sel.cust.has(x.cu));
		const passRecvM = (x) => (st.internal || !x.internal) && passCo(x.co) && (!st.sel.seg.size || st.sel.seg.has(x.seg));
		const passPay = (x) => (st.internal || !x.internal) && passCo(x.co);
		function buyRate(co, mo) {
			for (let k = 0; k <= BUY_RATE_CARRY && mo - k >= 0; k++) { const v = st.mn.buy.get(co * 100 + mo - k); if (v != null) return v; }
			return null;
		}
		// Gas margin over the window and the comparison window: only kg whose
		// company-month has a purchase price count (`cov`); `share` says how much.
		function marginTotals(W, rowPass) {
			if (!st.mn) return null;
			const z = () => ({ kg: 0, cov: 0, gas: 0, cost: 0 }), c = z(), p = z();
			for (const r of D().sales) {
				if (!r[R_GAS]) continue;
				const s = r[R_SLOT], inC = inWin(W, s), inP = inCmp(W, s);
				if (!(inC || inP) || !rowPass(r)) continue;
				const b = buyRate(r[R_CO], s === wkS() ? st.weekInfo.mo : s === wkC() ? st.weekInfo.mo - 12 : s >> 1);
				for (const x of [inC && c, inP && p]) {
					if (!x) continue;
					x.kg += r[R_KG];
					if (b != null) { x.cov += r[R_KG]; x.gas += r[R_GAS]; x.cost += r[R_KG] * b; }
				}
			}
			const fin = (x) => ({ ...x, m: x.cov > 0 ? (x.gas - x.cost) / x.cov : null, sell: x.cov > 0 ? x.gas / x.cov : null, buy: x.cov > 0 ? x.cost / x.cov : null, share: x.kg ? x.cov / x.kg : 0 });
			return { cur: fin(c), prev: fin(p) };
		}
		function marginMonthly(rowPass) {
			const n = NM(), gas = new Float64Array(n), cost = new Float64Array(n), cov = new Float64Array(n), kg = new Float64Array(n);
			for (const r of D().sales) {
				if (!r[R_GAS] || !rowPass(r)) continue;
				const mo = r[R_SLOT] >> 1, b = buyRate(r[R_CO], mo);
				kg[mo] += r[R_KG];
				if (b != null) { cov[mo] += r[R_KG]; gas[mo] += r[R_GAS]; cost[mo] += r[R_KG] * b; }
			}
			const at = (f) => Array.from({ length: n }, (_, i) => (cov[i] > 0 ? f(i) : null));
			return { m: at((i) => (gas[i] - cost[i]) / cov[i]), sell: at((i) => gas[i] / cov[i]), buy: at((i) => cost[i] / cov[i]), share: Array.from(kg, (v, i) => (v ? cov[i] / v : 0)) };
		}
		function moneyTotals() {
			if (!st.mn) return null;
			const t = { cash: 0, bank: 0, cashLy: 0, bankLy: 0, loan: 0, owed: 0, owedLy: 0, adv: 0, pay: 0, payLy: 0, payAdv: 0 };
			for (const x of st.mn.cash) {
				if (!passCo(x.co)) continue;
				if (x.kind === 0) { t.cash += x.now; t.cashLy += x.ly; } else if (x.kind === 1) { t.bank += x.now; t.bankLy += x.ly; } else t.loan += x.now;
			}
			for (const x of st.mn.recv) { if (!passRecv(x)) continue; if (x.now > 0) t.owed += x.now; else t.adv -= x.now; if (x.ly > 0) t.owedLy += x.ly; }
			for (const x of st.mn.pay) { if (!passPay(x)) continue; if (x.now > 0) t.pay += x.now; else t.payAdv -= x.now; if (x.ly > 0) t.payLy += x.ly; }
			return t;
		}
		// Month-end balances over the timeline (null after the data-through month). The
		// receivable trend is per company x segment, so it is not drawn for one customer.
		function moneySeries() {
			const pm = PM(), z = (on) => Array.from({ length: NM() }, (_, i) => (on && i <= pm ? 0 : null));
			const out = { cash: z(true), owed: z(!st.sel.cust.size), pay: z(true) };
			const add = (arr, vals) => vals.forEach((v, i) => { if (v != null && arr[i] != null) arr[i] += v; });
			for (const x of st.mn.cash) if (x.kind < 2 && passCo(x.co)) add(out.cash, x.m);
			for (const x of st.mn.recvM) if (passRecvM(x)) add(out.owed, x.owed);
			for (const x of st.mn.payM) if (passPay(x)) add(out.pay, x.owed);
			return out;
		}
		// Map snapshot rows onto the dashboard's customer and company indexes.
		// Customers with limits but no bills in three years are added to the list.
		function prepareCredit() {
			const c = st.credit, d = st.data;
			if (!c || !d || c.missing || st.cr) return;
			const byCode = new Map(d.customers.map((x, i) => [x[0], i]));
			const coByAbbr = new Map(d.companies.map((x, i) => [x.abbr, i]));
			st.cr = c.rows.map((r) => {
				let cu = byCode.get(r[0]);
				if (cu == null) { cu = d.customers.length; d.customers.push([r[0], r[1], r[2], null, null, r[3], null]); byCode.set(r[0], cu); }
				return { cu, seg: r[2], co: coByAbbr.has(r[4]) ? coByAbbr.get(r[4]) : -1, blocked: r[5], owed: r[6], adv: r[7], exp: r[8], lim: r[9], days: r[10], dlim: r[11], bills: r[12], blim: r[13], oldest: r[14] };
			});
		}
		const passCredit = (x, skip = "") => {
			if (!okInternal(x.cu)) return false;
			const s = st.sel;
			if (s.co.size && !skip.includes("co") && !s.co.has(x.co)) return false;
			if (s.seg.size && !skip.includes("seg") && !s.seg.has(x.seg)) return false;
			if (s.cust.size && !skip.includes("cust") && !s.cust.has(x.cu)) return false;
			return true;
		};
		const cashOnly = (x) => x.lim > 0 && x.lim <= CASH_ONLY_MAX;
		const limitUse = (x) => (x.lim > CASH_ONLY_MAX ? x.exp / x.lim : null);
		// Owed with no unpaid bill behind it = a journal debit (credit_control's
		// je_debit): it has no date, so it cannot age. Bucket index = AGE_BUCKETS.length.
		const journalOnly = (x) => x.owed > 0 && !x.bills;
		const ageBucket = (x) => (x.owed <= 0 ? -1 : journalOnly(x) ? AGE_BUCKETS.length : AGE_BUCKETS.findIndex(([a, b]) => x.days >= a && x.days <= b));
		// Average monthly measure over the last 12 months, per customer (the "usual" size).
		function usualMonthly() {
			const p = P(), out = new Map();
			for (const r of D().sales) { const sl = r[R_SLOT]; if (sl > p - 24 && sl <= p) out.set(r[R_CU], (out.get(r[R_CU]) || 0) + mv(r) / 12); }
			return out;
		}

		// -------------------------------------------------------- layout
		function layout() {
			const card = (name, span, title, extra = "") => `<section class="ceo-card ${span}" data-card="${name}"><header><div><h3 data-title="${name}">${title}</h3></div>${extra}</header><div class="ceo-body" data-slot="${name}"></div></section>`;
			// Each part of the page sits in its own tinted panel (Sales mint, Buying
			// pink, Money sand, Credit lilac, Customers sky) so it is found at a
			// glance; the top tiles carry the same tint. Colours in ceo_dashboard.css.
			const zoneHead = (title) => `<span class="ceo-zone-key" aria-hidden="true"></span><h2>${title}</h2>`;
			// Funnel button + its panel (filled by renderPop) beside the Table button.
			const tools = (n) => `<div class="ceo-tools"><span class="ceo-optwrap"><button class="ceo-icon small" data-act="copts" data-val="${n}" aria-haspopup="dialog" title="${esc(__("Chart options"))}" aria-label="${esc(__("Chart options"))}"><svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="M1.5 2.5h13L9.5 8.6V13l-3 1.6V8.6z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg></button><div class="ceo-pop" data-pop="${n}" role="dialog" hidden></div></span>${tbl(n)}</div>`;
			const tbl = (n) => `<button class="ceo-ghost" data-act="table" data-name="${n}" aria-pressed="false" title="${esc(__("Show as table"))}">${__("Table")}</button>`;
			return `
				<div class="ceo-kpis six ceo-top" data-slot="kpis"></div>
				<section class="ceo-zone" data-zone="sales" data-anchor="sales">
					<div class="ceo-section">${zoneHead(__("Sales"))}</div>
					<div class="ceo-grid">
						${card("trend", "span-8", __("Last 24 months"), tools("trend"))}
						${card("company", "span-4", __("By company"))}
						${card("matrix", "span-12", __("Company scorecard"))}
						${card("segment", "span-12 ceo-feature", __("Customer segment"), tbl("segment"))}
						${SHOW_PRICE_CHART ? card("price", "span-6", __("Average price per kg"), tbl("price")) : ""}
						${card("coll", SHOW_PRICE_CHART ? "span-6" : "span-12", __("Billed and collected"), tools("coll"))}
					</div>
				</section>
				<section class="ceo-zone" data-zone="buy" data-anchor="buying">
					<div class="ceo-section">${zoneHead(__("Buying"))}<span data-slot="buy-label"></span></div>
					<div class="ceo-kpis small" data-slot="buy-kpis"></div>
					<div class="ceo-grid">
						${card("buytrend", "span-8", __("Purchases"), tbl("buytrend"))}
						${card("buyco", "span-4", __("Purchases by company"))}
						${card("buycat", "span-6", __("What we buy"))}
						${card("buysup", "span-6", __("Top suppliers"))}
						${SHOW_MARGIN ? card("margin", "span-6", __("Gas margin per kg"), tbl("margin")) : ""}
						${card("pay", SHOW_MARGIN ? "span-6" : "span-12", __("We owe suppliers"), tools("pay"))}
					</div>
				</section>
				<section class="ceo-zone" data-zone="money" data-anchor="money">
					<div class="ceo-section">${zoneHead(__("Money"))}<span data-slot="money-label"></span></div>
					<div class="ceo-grid">
						${card("cash", "span-6", __("Cash and bank"), tools("cash"))}
						${card("recv", "span-6", __("Customers owe us"), tools("recv"))}
					</div>
				</section>
				<section class="ceo-zone" data-zone="credit" data-anchor="credit">
					<div class="ceo-section">${zoneHead(__("Credit and dues"))}<span data-slot="credit-label"></span></div>
					<div class="ceo-kpis small" data-slot="credit-kpis"></div>
					<div class="ceo-grid" data-slot="credit-grid">
						${card("crage", "span-4", __("Owed, by age of oldest unpaid bill"))}
						${card("crco", "span-4", __("Credit by company"))}
						${card("cruse", "span-4", __("Use of amount limit"))}
						${card("crlist", "span-12", __("Customers"), `<div class="ceo-tools" data-slot="crtools"></div>`)}
					</div>
				</section>
				<section class="ceo-zone" data-zone="cust" data-anchor="customers">
					<div class="ceo-section">${zoneHead(__("Customers"))}</div>
					<div class="ceo-grid">
						${card("customers", "span-8", __("Customers"), `<div class="ceo-tools" data-slot="custtools"></div>`)}
						<div class="ceo-stack span-4">
							${card("quiet", "", __("Gone quiet"))}
							${SHOW_COMPARISON ? card("alerts", "", __("Price alerts")) : ""}
						</div>
					</div>
				</section>
				<div class="ceo-footnote" data-slot="footnote"></div>`;
		}

		// -------------------------------------------------------- render
		function render(animate) {
			if (!st.data) return;
			st.tips = [];
			const main = slot("main");
			if (!main.querySelector("[data-slot='kpis']")) main.innerHTML = layout();
			const host = $(".ceo");
			host.classList.remove("anim");
			if (animate) { void host.offsetWidth; host.classList.add("anim"); }
			const W = (st.W = windowSlots());
			renderFilters();
			renderChips();
			renderKpis(W);
			st.view = chartView();
			ensureDaily(st.view);
			renderTrend();
			renderCompanies(W);
			renderMatrix(W);
			renderSegments(W);
			if (SHOW_PRICE_CHART) renderPrice();
			renderColl();
			renderMoney(W);
			renderBuying(W);
			renderCustomers();
			renderQuiet();
			if (slot("alerts")) renderAlerts();   // a comparison with the typical company: off with SHOW_COMPARISON
			renderCredit();
			renderFootnote();
			if (st.drawer) renderDrawer();
			root.querySelectorAll("[data-act='table']").forEach((b) => b.setAttribute("aria-pressed", st.tables.has(b.dataset.name)));
			writeUrl();
		}

		let activeCache = null;
		const activeCompanies = () => {
			if (activeCache && activeCache.data === st.data) return activeCache.list;
			const has = new Set();
			for (const r of D().sales) has.add(r[R_CO]);
			const list = D().companies.map((c, i) => ({ ...c, i })).filter((c) => has.has(c.i));
			activeCache = { data: st.data, list };
			return list;
		};
		// Picking companies FILTERS (the user's call, 2026-11-09): lists, tables and
		// charts show only the picked companies, not all of them with the rest greyed.
		const shownCompanies = () => (st.sel.co.size ? activeCompanies().filter((c) => st.sel.co.has(c.i)) : activeCompanies());
		// One accent for every company; identity is the name beside the mark.
		const coColor = () => "var(--ceo-cur)";

		// "1 Shrawan 2083 – 11 Bhadra 2083": the exact first and last day of the
		// period on screen (replaces "Data through", the CEO's call 2026-11-11; the
		// last day is the data-through day whenever the period reaches it).
		function periodRange() {
			const [a, b] = st.W ? windowDates() : [D().through, D().through];
			const full = (iso) => { const m = monthOfIso(iso); return m >= 0 ? `${bsShort(iso)} ${bsYear(m)}` : iso; };
			return a === b ? `<strong>${esc(full(a))}</strong>` : `<strong>${esc(full(a))}</strong> <span>–</span> <strong>${esc(full(b))}</strong>`;
		}
		function renderFilters() {
			const d = D();
			const seg = (act, items, cur, label) => `<div class="ceo-seg" role="group" aria-label="${esc(label)}">${items.map(([v, l]) => `<button data-act="${act}" data-val="${v}" aria-pressed="${cur === v}">${esc(__(l))}</button>`).join("")}</div>`;
			slot("filters").innerHTML = `
				${fyPicker()}
				${multiYear() ? "" : periodDd()}
				${seg("measure", [["kg", "Volume"], ["amt", "Rupees"]], st.measure, __("Measure"))}
				${companyPicker()}
				${seg("internal", [["0", "Excl. inter-company"], ["1", "Incl."]], st.internal ? "1" : "0", __("Sales between group companies"))}
				<nav class="ceo-nav" aria-label="${esc(__("Sections"))}">${[["sales", "sales", __("Sales")], ["buying", "buy", __("Buying")], ["money", "money", __("Money")], ["credit", "credit", __("Credit and dues")], ["customers", "cust", __("Customers")]].filter(([k]) => k !== "credit" || !pastYear()).map(([k, z, l]) => `<button data-act="goto" data-val="${k}" data-zone="${z}"><i aria-hidden="true"></i>${esc(l)}</button>`).join("")}</nav>
				<div class="ceo-asof" title="${esc(__("Data through {0}", [d.through_label]))}">${periodRange()}
					<button class="ceo-icon" data-act="print" title="${esc(__("Print / PDF"))}" aria-label="${esc(__("Print / PDF"))}"><svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="M4 6V2h8v4M4 12H2.5A1.5 1.5 0 0 1 1 10.5v-3A1.5 1.5 0 0 1 2.5 6h11A1.5 1.5 0 0 1 15 7.5v3a1.5 1.5 0 0 1-1.5 1.5H12M4 9.5h8V14H4z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg></button></div>`;
		}

		// One compact dropdown for the period: the kind (week, month, quarter,
		// year to date, 12 months) and, for a week, month or quarter, which one.
		function periodSub() {
			const b = FY0(), pm = PM();
			if (st.period === "mtd") {
				// All twelve months, Shrawan to Ashadh; months after "data through" are listed but cannot be picked.
				const cur = st.month == null ? pm - b : Math.min(st.month, pm - b);
				return { cur, label: monthLabel(b + cur), opts: Array.from({ length: 12 }, (_, i) => [i, monthLabel(b + i), b + i > pm]) };
			}
			if (st.period === "qtd") {
				const cur = st.quarter == null ? curQuarter() : Math.min(st.quarter, curQuarter());
				const ql = (q) => `Q${q + 1} · ${monthName(b + q * 3).slice(0, 3)} – ${monthName(b + q * 3 + 2).slice(0, 3)}`;
				return { cur, label: ql(cur), opts: Array.from({ length: 4 }, (_, q) => [q, ql(q), q > curQuarter()]) };
			}
			if (st.period === "wk") {
				const wk = fyWeeks(), cur = st.week == null ? wk.length : st.week;
				return { cur, label: wk[cur - 1] ? weekLabel(cur, wk[cur - 1]) : __("Week"), opts: wk.map((w, i) => [i + 1, weekLabel(i + 1, w)]).reverse() };
			}
			return null;
		}
		function periodDd() {
			const sub = st.sel.mo.size ? null : periodSub();
			const kind = (PERIODS.find(([k]) => k === st.period) || [])[1];
			const label = st.sel.mo.size ? __("Picked months") : sub ? sub.label : __(kind);
			return `<div class="ceo-dd ${st.pdOpen ? "open" : ""}" data-dd="pd">
				<button class="ceo-ddbtn" data-act="pd-toggle" aria-haspopup="dialog" aria-expanded="${st.pdOpen}"><span class="ceo-ddlbl">${__("Period")}</span><strong>${esc(label)}</strong><span class="ceo-ddcaret" aria-hidden="true">▾</span></button>
				${st.pdOpen ? `<div class="ceo-ddpanel period">
					<div class="ceo-seg small ceo-pdkinds" role="group" aria-label="${esc(__("Period"))}">${PERIODS.map(([v, l]) => `<button data-act="period" data-val="${v}" aria-pressed="${!st.sel.mo.size && st.period === v}">${esc(__(l))}</button>`).join("")}</div>
					${sub ? `<div class="ceo-ddlist ceo-pdlist">${sub.opts.map(([v, l, off]) => `<button class="ceo-pdopt" data-act="pick" data-val="${v}" aria-pressed="${v === sub.cur}" ${off ? "disabled" : ""}>${esc(l)}</button>`).join("")}</div>` : ""}
				</div>` : ""}
			</div>`;
		}

		// Fiscal years: one ticked = that year (with the period buttons); several
		// ticked = those years added together. Each tick applies by itself
		// FY_APPLY_DELAY after the last one (each change reloads the data).
		// Load the ticked years (called FY_APPLY_DELAY after the last tick). The
		// draft stays shown in the picker until the new data arrives (see load()).
		function applyFys() {
			const picked = (st.fyDraft || []).slice().sort(fyCmp);
			if (!picked.length) return;
			st.fys = picked.length > 1 ? picked : [];
			st.fy = picked[picked.length - 1];
			st.month = st.quarter = st.week = null;
			Object.values(st.sel).forEach((x) => x.clear());
			closeDrawer();
			load(false);
		}
		function fyPicker() {
			const d = D(), on = st.fyDraft || (multiYear() ? st.fys : [d.fiscal_year]);
			const label = on.length > 1 ? on.slice().sort(fyCmp).join(" + ") : on[0];
			return `<div class="ceo-dd ${st.fyOpen ? "open" : ""}" data-dd="fy">
				<button class="ceo-ddbtn ${on.length > 1 ? "has-sel" : ""}" data-act="fy-toggle" aria-haspopup="listbox" aria-expanded="${st.fyOpen}"><span class="ceo-ddlbl">${__("Fiscal year")}</span><strong>${esc(label)}</strong><span class="ceo-ddcaret" aria-hidden="true">▾</span></button>
				${st.fyOpen ? `<div class="ceo-ddpanel" role="listbox" aria-multiselectable="true">
					<div class="ceo-ddlist">${d.fiscal_years.map((f) => `<label class="ceo-ddopt"><input type="checkbox" data-act="fy-pick" data-val="${esc(f)}" ${on.includes(f) ? "checked" : ""} ${!on.includes(f) && on.length >= MAX_FYS ? "disabled" : ""}><strong>${esc(f)}</strong></label>`).join("")}</div>
				</div>` : ""}
			</div>`;
		}

		function companyPicker() {
			const list = activeCompanies(), n = st.sel.co.size;
			const label = !n ? __("All companies") : n === 1 ? D().companies[[...st.sel.co][0]].abbr : __("{0} companies", [n]);
			const q = st.ddSearch.trim().toLowerCase();
			const shown = list.filter((c) => !q || (c.abbr + " " + c.name).toLowerCase().includes(q));
			return `<div class="ceo-dd ${st.ddOpen ? "open" : ""}">
				<button class="ceo-ddbtn ${n ? "has-sel" : ""}" data-act="dd-toggle" aria-haspopup="listbox" aria-expanded="${st.ddOpen}"><span class="ceo-ddlbl">${__("Company")}</span><strong>${esc(label)}</strong><span class="ceo-ddcaret" aria-hidden="true">▾</span></button>
				${st.ddOpen ? `<div class="ceo-ddpanel" role="listbox" aria-multiselectable="true">
					${list.length > 6 ? `<input type="search" class="ceo-search ceo-ddsearch" data-input="dd-search" value="${esc(st.ddSearch)}" placeholder="${esc(__("Find company"))}" aria-label="${esc(__("Find company"))}">` : ""}
					<div class="ceo-ddlist">${shown.map((c) => `<label class="ceo-ddopt"><input type="checkbox" data-act="dd-pick" data-val="${c.i}" ${st.sel.co.has(c.i) ? "checked" : ""}><strong>${esc(c.abbr)}</strong><span>${esc(c.name)}</span></label>`).join("") || `<div class="ceo-empty">${__("No match")}</div>`}</div>
					<div class="ceo-ddfoot"><button class="ceo-ghost" data-act="dd-all">${__("All companies")}</button><button class="ceo-ghost" data-act="dd-close">${__("Done")}</button></div>
				</div>` : ""}
			</div>`;
		}

		function renderChips() {
			const d = D(), parts = [];
			const add = (dim, label, vals, name) => vals.forEach((v) => parts.push(
				`<button class="ceo-chip" data-act="unsel" data-dim="${dim}" data-val="${v}" title="${esc(__("Remove filter"))}"><span>${esc(label)}</span>${esc(name(v))}<span aria-hidden="true">✕</span></button>`));
			add("co", __("Company"), [...st.sel.co], (v) => d.companies[v].abbr);
			add("mo", __("Month"), [...st.sel.mo].sort((a, b) => a - b), (v) => monthLabel(v, true));
			add("seg", __("Segment"), [...st.sel.seg], (v) => d.segments[v]);
			add("cust", __("Customer"), [...st.sel.cust], (v) => d.customers[v][1]);
			const el = slot("chips");
			el.hidden = !parts.length;
			el.innerHTML = parts.length ? `<span class="ceo-chips-label">${__("Showing")}</span>${parts.join("")}<button class="ceo-ghost" data-act="reset">${__("Clear all")}</button>` : "";
		}

		// -------------------------------------------------------- KPIs
		function renderKpis(W) {
			const t = totals(W, (r) => pass(r), (r) => passColl(r));
			const from = PM() - 23;
			const kgS = flow(last24(monthly(pass, (r) => r[R_KG]))), amtS = flow(last24(monthly(pass, (r) => r[R_AMT])));
			const gasS = last24(monthly(pass, (r) => r[R_GAS])), gkS = last24(monthly(pass, (r) => (r[R_GAS] ? r[R_KG] : 0)));
			const collS = flow(last24(monthly(passColl, (r) => r[C_AMT], D().coll)));
			const wm = winMonths(W), cmp = compareLabel();
			const rateS = gasS.map((g, i) => (gkS[i] ? g / gkS[i] : null));
			let bills = 0;
			for (const r of D().sales) if (inWin(W, r[R_SLOT]) && pass(r)) bills += r[R_BILLS] || 0;
			const tiles = [
				{ hero: true, key: "kg", label: __("LP Gas volume"), value: mt(t.kg), d: delta(t.kg, t.kgP, { note: cmp }), sub: esc(`${mt(t.kgP)} ${__("in the comparison period")} · ${inr(t.cust.size)} ${__("customers")}`), foot: esc(`${inr(t.cust.size)} ${__("customers")} · ${inr(bills)} ${__("bills")}`), s: kgS },
				{ key: "amt", label: __("Net sales"), value: rs(t.amt), d: delta(t.amt, t.amtP), sub: esc(`${rs(t.amtP)} ${__("before")} · Rs ${inr(t.rate, 2)}/kg`), foot: esc(`${__("Collected")} ${rs(t.coll)}${t.amt ? ` · ${inr((t.coll / t.amt) * 100, 0)}%` : ""}`), s: amtS },
				marginTile(W, t, rateS),
				...moneyTiles(t, collS),
				buyTile(W),
			];
			// Same order and tint as the panels: Sales, Buying, Money.
			const [vol, amt, mg, cash, owed, pay, buy] = tiles;
			Object.assign(vol, { zone: "sales" }); Object.assign(amt, { zone: "sales" });
			Object.assign(mg, { zone: "buy", goto: mg.loading ? undefined : "buying" }); Object.assign(pay, { zone: "buy", goto: pay.loading ? undefined : "buying" });
			Object.assign(cash, { zone: "money" }); Object.assign(owed, { zone: "money" });
			tiles.splice(0, tiles.length, ...[vol, amt, SHOW_MARGIN ? mg : null, buy, pay, cash, owed].filter(Boolean));
			slot("kpis").classList.toggle("five", tiles.length === 5);
			slot("kpis").innerHTML = tiles.map((x) => x.loading ? `<div class="ceo-kpi" data-zone="${x.zone}"><div class="ceo-kpi-label">${esc(x.label)}</div><div class="ceo-skel line"></div><div class="ceo-skel line short"></div></div>` : `<div class="ceo-kpi ${x.hero ? "hero" : ""} ${x.key === st.measure ? "is-measure" : ""} ${x.cls || ""}" data-zone="${x.zone || ""}" ${x.goto ? `data-act="goto" data-val="${x.goto}" tabindex="0" role="link"` : ""} ${x.tip != null ? `data-tip="${tip(x.tip)}"` : ""}>
				<div class="ceo-kpi-label">${esc(x.label)}</div>
				<div class="ceo-kpi-value">${bigNum(x.value)}</div>
				${SHOW_COMPARISON ? `<div class="ceo-kpi-delta">${x.d}</div><div class="ceo-kpi-foot">${x.sub}</div>` : x.foot ? `<div class="ceo-kpi-foot">${x.foot}</div>` : ""}
				${x.s ? spark(x.s, wm, x.hero) : ""}
			</div>`).join("");
		}
		function marginTile(W, t, rateS) {
			const label = __("Gas margin");
			if (!st.money) return { label, loading: true };
			const mg = st.mn && marginTotals(W, (r) => pass(r));
			if (!mg || mg.cur.m == null) {
				return { label, value: "—", d: "", sub: esc(st.money.failed ? __("The ledger could not be read.") : __("No gas purchase bills in this period, so no purchase price to set the sale price against.")), s: rateS, goto: "money" };
			}
			const c = mg.cur, partial = c.share < MARGIN_PARTIAL;
			const ser = last24(marginMonthly((r) => pass(r)).m);
			return {
				label, goto: "money", cls: partial ? "is-partial" : "",
				value: `Rs ${inr(c.m, 2)}<small>/kg</small>`,
				d: mg.prev.m != null ? delta(c.m, mg.prev.m) : "",
				sub: `${__("Sold at")} Rs ${inr(c.sell, 2)} − ${__("bought at")} Rs ${inr(c.buy, 2)}${c.share < 0.995 ? ` · <span class="${partial ? "ceo-warnink" : ""}">${__("{0}% of volume has a purchase price", [inr(c.share * 100, 0)])}</span>` : ""}`,
				s: ser,
				tip: tipRows(__("Gas margin per kg"), [["", __("Sale price"), `Rs ${inr(c.sell, 2)}`], ["", __("Purchase price"), `Rs ${inr(c.buy, 2)}`], ["", __("Volume with a purchase price"), `${esc(mt(c.cov))} ${__("of")} ${esc(mt(c.kg))}`]], `<div class="ceo-tip-note">${__("Purchase price = that company's gas Purchase Invoices that month (or the month before). The stock ledger values gas at zero, so it cannot be used.")}</div>`),
			};
		}
		function moneyTiles(t, collS) {
			const labels = [__("Cash and bank"), __("Customers owe us"), __("We owe suppliers")];
			if (!st.money) return labels.map((label) => ({ label, loading: true }));
			if (st.money.failed || !st.mn) return labels.map((label) => ({ label, value: "—", d: "", sub: esc(__("The ledger could not be read.")) }));
			const m = moneyTotals(), ser = moneySeries(), ly = st.money.through_ly_label;
			return [
				{ label: labels[0], goto: "money", value: rs(m.cash + m.bank), d: delta(m.cash + m.bank, m.cashLy + m.bankLy, { note: __("vs {0}", [ly]) }), sub: esc(`${__("Cash in hand")} ${rs(m.cash)} · ${__("bank")} ${rs(m.bank)}`), foot: esc(`${__("Cash")} ${rs(m.cash)} · ${__("bank")} ${rs(m.bank)}`), s: last24(ser.cash) },
				{ label: labels[1], goto: "money", value: rs(m.owed), d: delta(m.owed, m.owedLy, { upGood: false }), sub: esc(`${__("Advances held")} ${rs(m.adv)}${t.amt ? ` · ${__("collected")} ${inr((t.coll / t.amt) * 100, 0)}% ${__("of billed")}` : ""}`), foot: esc(`${__("Advances held")} ${rs(m.adv)}`), s: st.sel.cust.size ? collS : last24(ser.owed) },
				{ label: labels[2], goto: "money", value: rs(m.pay), d: delta(m.pay, m.payLy, { upGood: null }), sub: esc(`${__("Bank loans")} ${rs(m.loan)} · ${__("paid ahead")} ${rs(m.payAdv)}`), foot: esc(`${__("Bank loans")} ${rs(m.loan)}`), s: last24(ser.pay) },
			];
		}
		// 24-month sparkline; months inside the period are drawn in the accent.
		// The current month is part-way through, so its total is always low and a
		// flow sparkline (volume, sales, purchases, receipts) would end in a cliff
		// every day of the month. Leave that last point off; balances keep theirs.
		const partMonth = () => D().through < D().month_bounds[PM()][1];
		const flow = (a) => (partMonth() ? a.map((v, i) => (i === a.length - 1 ? null : v)) : a);
		function spark(vals, inW, big) {
			const pts = vals.map((v, i) => [i, v]).filter((p) => p[1] != null && isFinite(p[1]));
			if (pts.length < 2) return "";
			const w = 240, h = big ? 48 : 34, ys = pts.map((p) => p[1]);
			const max = Math.max(...ys), lo = Math.min(...ys), min = lo > max * 0.6 ? lo - (max - lo) * 0.3 : Math.min(0, lo);
			const x = (i) => 3 + (i / 23) * (w - 6), y = (v) => h - 4 - ((v - min) / (max - min || 1)) * (h - 8);
			let path = "", win = "", pen = false, wpen = false;
			pts.forEach(([i, v]) => {
				path += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true;
				if (inW[i]) { win += `${wpen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; wpen = true; } else wpen = false;
			});
			const lp = pts[pts.length - 1];
			const area = `${path}L${x(lp[0]).toFixed(1)},${h}L${x(pts[0][0]).toFixed(1)},${h}Z`;
			return `<svg class="ceo-spark ${big ? "big" : ""}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><path class="area" d="${area}"/><path class="all" d="${path}"/><path class="win" d="${win}"/><circle cx="${x(lp[0])}" cy="${y(lp[1])}" r="3.5"/></svg>`;
		}

		// -------------------------------------------------------- period charts
		// The time charts follow the period: a week or a month day by day, a
		// quarter week by week (Sunday to Saturday), a year month by month, 12
		// months the last 12 months. Several months clicked on a chart keep the
		// 24-month view. Month views read the in-memory fact table; day and week
		// views fetch day rows for the range and the comparison range
		// (charts.get_daily). A view describes the buckets; bucketSums fills them.
		const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
		const isoAdd = (iso, n) => new Date(Date.parse(iso + "T00:00:00Z") + n * 86400000).toISOString().slice(0, 10);
		const dow = (iso) => new Date(iso + "T00:00:00Z").getUTCDay();
		const minIso = (a, b) => (a < b ? a : b);
		const isoMonth = new Map();   // AD date -> timeline month (for the purchase price of a day's gas)
		const monthOfIso = (iso) => { let m = isoMonth.get(iso); if (m == null) { const x = bsDay(iso); m = x ? x.m : -1; isoMonth.set(iso, m); } return m; };
		const bsDm = (iso) => { const x = bsDay(iso); return x ? `${x.day} ${monthName(x.m).slice(0, 3)}` : ""; };

		function chartView() {
			const d = D(), mb = d.month_bounds, pm = PM(), b = FY0(), thr = d.through;
			const months = (ms, title, multi) => ({
				grain: "month", n: ms.length, title, noun: __("month"), xTitle: __("Month (Nepali calendar)"), hint: __("Click a month to see it day by day."),
				inCur: (i) => ms[i] <= pm, inPrev: (i) => ms[i] >= 12, month: (i) => ms[i],
				label: (i, nar) => monthName(ms[i]).slice(0, nar ? 1 : 3),
				group: (i) => (i === 0 || ms[i] % 12 === 0 ? yearOf(ms[i]) : null),
				long: (i) => monthLabel(ms[i]) + (ms[i] === pm ? ` (${__("to {0}", [d.through_label])})` : ""),
				longPrev: (i) => monthLabel(ms[i] - 12),
				band: (i) => (ms[i] <= pm ? `data-act="chart-month" data-val="${ms[i]}"` : ""),
				dim: (i) => (multi ? dimState("mo", ms[i]) : ""),
				shade: (i) => multi && monthIn(st.W, ms[i]),
				last: (i) => ms[i] === pm,
			});
			const ranged = (o) => ({
				band: () => "", dim: () => "", shade: () => false, last: () => false,
				...o,
				key: JSON.stringify([st.fy, yearsBack(), ...o.fetch, st.sel.cust.size ? D().customers[[...st.sel.cust][0]][0] : ""]),
			});
			const range = (n) => Array.from({ length: n }, (_, i) => i);

			if (st.sel.mo.size > 1) return months(range(24).map((i) => pm - 23 + i), __("Last 24 months"), true);
			if (multiYear() && !st.sel.mo.size) {
				const ms = st.fys.flatMap((f) => { const y = d.years.indexOf(f); return y < 0 ? [] : range(12).map((i) => y * 12 + i); }).filter((mo) => mo <= pm);
				return months(ms, __("Month by month · {0}", [st.fys.join(" + ")]));
			}
			const dayView = (m) => {
				const s = mb[m][0], e = mb[m][1], hasP = m >= 12, ps = hasP ? mb[m - 12][0] : s, pe = hasP ? mb[m - 12][1] : s;
				const n = Math.max(daysBetween(s, e), hasP ? daysBetween(ps, pe) : 0) + 1;
				return ranged({
					grain: "day", n, from: s, title: __("Day by day · {0}", [monthLabel(m)]), noun: __("day"), xTitle: __("Day of {0}", [monthName(m)]), hint: "",
					fetch: [s, minIso(e, thr), ps, pe], hasPrev: hasP,
					pos: (iso, prev) => daysBetween(prev ? ps : s, iso),
					inCur: (i) => { const x = isoAdd(s, i); return x <= e && x <= thr; }, inPrev: (i) => hasP && isoAdd(ps, i) <= pe,
					label: (i) => String(i + 1), group: (i) => (i === 0 ? monthLabel(m) : null),
					long: (i) => `${i + 1} ${monthLabel(m)} · ${WEEKDAY[dow(isoAdd(s, i))]}`, longPrev: (i) => `${i + 1} ${monthLabel(m - 12)}`,
				});
			};
			if (st.sel.mo.size === 1) return dayView([...st.sel.mo][0]);
			if (st.period === "mtd") return dayView(st.month == null ? pm : Math.min(pm, b + st.month));
			if (st.period === "wk") {
				const wks = fyWeeks(), w = wks[(st.week || wks.length) - 1];
				if (w) {
					const vs = isoAdd(w[0], -dow(w[0])), back = (x) => isoAdd(x, -364);   // the Sunday the week's row starts on
					return ranged({
						grain: "day", n: 7, from: vs, title: __("Day by day · {0}", [weekLabel(st.week || wks.length, w)]), noun: __("day"), xTitle: __("Day of the week (Nepali date below)"), hint: "",
						fetch: [w[0], w[1], back(w[0]), back(w[1])], hasPrev: true,
						pos: (iso, prev) => daysBetween(prev ? back(vs) : vs, iso),
						inCur: (i) => { const x = isoAdd(vs, i); return x >= w[0] && x <= w[1]; }, inPrev: (i) => { const x = isoAdd(vs, i); return x >= w[0] && x <= w[1]; },
						label: (i, nar) => (nar ? WEEKDAY[i][0] : WEEKDAY[i]), sub: (i) => bsDm(isoAdd(vs, i)),
						long: (i) => `${WEEKDAY[i]} ${bsShort(isoAdd(vs, i))}`, longPrev: (i) => `${WEEKDAY[i]} ${bsShort(back(isoAdd(vs, i)))}`,
					});
				}
			}
			if (st.period === "qtd") {
				// Day by day across the quarter's three BS months; the line is the same
				// BS days a year earlier (1 Shrawan against 1 Shrawan).
				const q = st.quarter == null ? curQuarter() : Math.min(st.quarter, curQuarter()), qs = b + 3 * q;
				const s = mb[qs][0], e = mb[qs + 2][1], hasP = qs >= 12, ps = hasP ? mb[qs - 12][0] : s, pe = hasP ? mb[qs - 10][1] : s;
				const n = Math.max(daysBetween(s, e), hasP ? daysBetween(ps, pe) : 0) + 1;
				const dayOf = (i) => bsDay(isoAdd(s, i));
				return ranged({
					grain: "day", n, from: s, title: `${__("Day by day")} · Q${q + 1} · ${yearOf(qs)}`, noun: __("day"),
					xTitle: __("Day (Nepali calendar)"), hint: __("Click a day to see its month."),
					fetch: [s, minIso(e, thr), ps, pe], hasPrev: hasP, every: 1,
					pos: (iso, prev) => daysBetween(prev ? ps : s, iso),
					inCur: (i) => { const x = isoAdd(s, i); return x <= e && x <= thr; }, inPrev: (i) => hasP && isoAdd(ps, i) <= pe,
					// Day numbers on the 1st, 8th, 15th, 22nd and 29th only; month names where a month starts.
					label: (i) => { const x = dayOf(i); return x && x.day % 7 === 1 ? String(x.day) : ""; },
					group: (i) => { const x = dayOf(i); return x && x.day === 1 ? monthLabel(x.m) : null; },
					band: (i) => { const x = isoAdd(s, i); return x <= thr ? `data-act="chart-month" data-val="${monthOfIso(x)}"` : ""; },
					long: (i) => { const x = isoAdd(s, i); return `${bsShort(x)} ${bsYear(monthOfIso(x))} · ${WEEKDAY[dow(x)]}`; },
					longPrev: (i) => { const x = isoAdd(ps, i); return `${bsShort(x)} ${bsYear(monthOfIso(x))}`; },
				});
			}
			if (st.period === "r12") return months(range(12).map((i) => pm - 11 + i), __("Last 12 months"));
			// Only the months that have happened: a year that is two months old is two
			// wide bars, not two bars and ten blanks.
			return months(range(pm - b + 1).map((i) => b + i), __("Month by month · {0}", [yearOf(b)]));
		}

		// Day rows for a day / week view, fetched once per range (and customer).
		function ensureDaily(v) {
			if (v.grain === "month" || (st.daily && st.daily.key === v.key)) return;
			const key = v.key, [a, b, pa, pb] = v.fetch;
			st.daily = { key, data: null };
			frappe.call({
				method: "avinashgroup_app.ceo_dashboard.charts.get_daily",
				args: { fiscal_year: st.fy, years_back: yearsBack(), from_date: a, to_date: b, prev_from: pa, prev_to: pb, customer: st.sel.cust.size ? D().customers[[...st.sel.cust][0]][0] : null },
				callback: (r) => {
					if (!st.daily || st.daily.key !== key || !r.message) return;
					// Reshape to the fact table's columns where they overlap:
					// sales [date, co, -, seg, kg, gas Rs, net Rs, inter-company], coll [date, co, -, Rs, seg, inter-company].
					st.daily.data = {
						sales: r.message.sales.map((x) => [x[0], x[1], -1, x[2], x[4], x[5], x[6], x[3]]),
						coll: r.message.coll.map((x) => [x[0], x[1], -1, x[4], x[2], x[3]]),
					};
					render(false);
				},
				error: () => { if (st.daily && st.daily.key === key) st.daily = null; },
			});
		}
		// Row filters that work on fact rows and day rows alike (day rows carry
		// their inter-company flag; the customer filter was applied by the server).
		const onCo = (co, skip) => !st.sel.co.size || skip.includes("co") || st.sel.co.has(co);
		const onSeg = (seg, skip) => !st.sel.seg.size || skip.includes("seg") || st.sel.seg.has(seg);
		const passX = (r, skip = "", day = false) => (day ? (st.internal || !r[7]) && onCo(r[1], skip) && onSeg(r[3], skip) : pass(r, skip));
		const passCollX = (r, skip = "", day = false) => (day ? (st.internal || !r[5]) && onCo(r[1], skip) && onSeg(r[4], skip) : passColl(r, skip));
		const allX = (r, day = false) => (day ? st.internal || !r[7] : okInternal(r[R_CU]));
		// Sum val(row, month) into the view's buckets: { cur, prev } (null while day rows load).
		function bucketSums(v, { coll = false, ok, val }) {
			const cur = new Array(v.n).fill(0), prev = new Array(v.n).fill(0);
			if (v.grain === "month") {
				const idx = new Map(Array.from({ length: v.n }, (_, i) => [v.month(i), i]));
				for (const r of coll ? D().coll : D().sales) {
					if (r[0] >= NS() || !ok(r, false)) continue;   // >= NS(): a folded-in week, not a month
					const m = r[0] >> 1;
					let i = idx.get(m); if (i != null) cur[i] += val(r, m);
					i = idx.get(m + 12); if (i != null) prev[i] += val(r, m);
				}
			} else {
				const dd = st.daily && st.daily.key === v.key && st.daily.data;
				if (!dd) return null;
				for (const r of coll ? dd.coll : dd.sales) {
					if (!ok(r, true)) continue;
					const isPrev = r[0] < v.from, i = v.pos(r[0], isPrev);
					if (i >= 0 && i < v.n) (isPrev ? prev : cur)[i] += val(r, monthOfIso(r[0]));
				}
			}
			return { cur: cur.map((x, i) => (v.inCur(i) ? x : null)), prev: v.hasPrev === false ? prev.map(() => null) : prev.map((x, i) => (v.inPrev(i) ? x : null)) };
		}
		const viewAxis = (v) => ({ n: v.n, val: () => undefined, label: v.label, sub: v.sub, group: v.group || (() => null), shade: v.shade, dim: v.dim, last: v.last, band: v.band, aria: v.long, xTitle: v.xTitle, every: v.every });
		// What the value axis is measured in.
		const yTitleOf = (kind) => ({ kg: __("LP Gas sold, metric tonnes (MT)"), amt: __("Rupees (L = lakh, Cr = crore)"), rate: __("Rupees per kg") })[kind];
		function axis24() {
			const pm = PM(), from = pm - 23;
			return {
				n: 24, val: (i) => from + i, xTitle: __("Month end (Nepali calendar)"),
				label: (i, nar) => monthName(from + i).slice(0, nar ? 1 : 3),
				group: (i) => ((from + i) % 12 === 0 || i === 0 ? yearOf(from + i) : null),
				shade: (i) => monthIn(st.W, from + i),
				dim: (i) => dimState("mo", from + i), last: (i) => from + i === pm,
				band: (i) => `data-dim="mo" data-val="${from + i}"`, aria: (i) => monthLabel(from + i),
			};
		}
		const setTitle = (name, text) => { const h = root.querySelector(`[data-title="${name}"]`); if (h) h.textContent = text; };
		const chartLoading = () => `<div class="ceo-skel chart"></div>`;

		function timeAxis(el, { series, kind, tipFor, height, axis, yTitle }) {
			// series: [{ type: "bar"|"line", vals: [n], cls, full?: [n] (faint full bar behind), dots? }]
			// Axis titles: x from the axis (what one bar is), y from the measure (its unit).
			if (!SHOW_COMPARISON) series = series.filter((x) => x.cls !== "prev");
			const A = axis || axis24(), N = A.n, hasSub = !!A.sub, xb = A.xTitle ? 24 : 0;
			const W = Math.max(300, el.clientWidth || 600), H = (height || Math.max(230, Math.min(310, W * 0.38))) + (hasSub ? 12 : 0) + xb;
			// Chart text is large (CEO_DASHBOARD css: ticks 13.5px, axis titles 15px), so the margins are wide.
			let yT = yTitle || yTitleOf(kind);
			const m = { t: 12, r: 8, b: (hasSub ? 62 : 48) + xb, l: 66 + (yT ? 24 : 0) }, iw = W - m.l - m.r, ih = H - m.t - m.b, band = iw / N;
			// A short chart has no room for the long title: keep the first words ("Rupees").
			if (yT && ih < 190) yT = yT.replace(/[,(].*$/, "").trim();
			const all = series.flatMap((s) => [...s.vals, ...(s.full || [])]).filter((v) => v != null && isFinite(v));
			if (!all.length) return `<div class="ceo-empty">${__("Nothing to show for this selection.")}</div>`;
			let lo = Math.min(0, ...all), hi = Math.max(...all, 1);
			if (lo < 0 && -lo < hi * NEG_AXIS_MIN) lo = 0;   // a few returns: no whole negative axis for them
			if (kind === "rate") { lo = Math.min(...all) * 0.94; hi = Math.max(...all) * 1.02; }
			const ticks = niceTicks(lo, hi), y0 = ticks[0], y1 = ticks[ticks.length - 1];
			const y = (v) => m.t + ih - ((v - y0) / (y1 - y0 || 1)) * ih, xc = (i) => m.l + band * i + band / 2;
			const narrow = band < 32, every = A.every || (narrow ? Math.ceil(32 / band) : 1);
			let s = `<svg class="ceo-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img">`;
			if (yT) s += `<text class="ceo-axis-title" transform="translate(16 ${m.t + ih / 2}) rotate(-90)" text-anchor="middle">${esc(yT)}</text>`;
			if (A.xTitle) s += `<text class="ceo-axis-title" x="${m.l + iw / 2}" y="${H - 3}" text-anchor="middle">${esc(A.xTitle)}</text>`;
			for (let i = 0; i < N; i++) if (A.shade(i)) s += `<rect class="ceo-win" x="${m.l + band * i}" y="${m.t}" width="${band}" height="${ih}"/>`;
			for (const t of ticks) s += `<line class="ceo-grid-l" x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/><text class="ceo-tick" x="${m.l - 8}" y="${y(t) + 4}" text-anchor="end">${esc(axisNum(t, kind))}</text>`;
			s += `<line class="ceo-base" x1="${m.l}" x2="${W - m.r}" y1="${y(y0)}" y2="${y(y0)}"/>`;
			for (let i = 0; i < N; i++) {
				if (i % every === 0) {
					s += `<text class="ceo-tick ${A.dim(i)}" x="${xc(i)}" y="${H - xb - (hasSub ? 44 : 30)}" text-anchor="middle">${esc(A.label(i, false))}</text>`;
					if (hasSub && !narrow) s += `<text class="ceo-tick sub" x="${xc(i)}" y="${H - xb - 27}" text-anchor="middle">${esc(A.sub(i))}</text>`;
				}
				const g = A.group(i);
				if (g) s += `<text class="ceo-tick yr" x="${m.l + band * i + 3}" y="${H - xb - 8}">${esc(g)}</text>${i ? `<line class="ceo-yr" x1="${m.l + band * i}" x2="${m.l + band * i}" y1="${m.t}" y2="${H - xb - 4}"/>` : ""}`;
			}
			const bars = series.filter((x) => x.type === "bar");
			bars.forEach((se, bi) => {
				const nb = bars.length, bw = Math.min(nb > 1 ? 24 : 46, band * (nb > 1 ? 0.36 : 0.62)), off = (bi - (nb - 1) / 2) * (bw + 3);
				const base = y(Math.max(y0, 0)), labels = nb === 1 && N <= BAR_LABELS_MAX && bw >= 26 && !series.some((x) => x.type === "line" && x.vals.some((v) => v != null));
				se.vals.forEach((v, i) => {
					const x0 = xc(i) - bw / 2 + off;
					if (se.full && se.full[i] > 0) s += `<path class="ceo-bar full ${se.cls}" d="${roundTop(x0, y(se.full[i]), bw, base - y(se.full[i]), 5)}"/>`;
					if (v > 0) s += `<path class="ceo-bar ${se.cls} ${A.dim(i)} ${A.last(i) ? "is-last" : ""}" style="--i:${i}" d="${roundTop(x0, y(v), bw, base - y(v), Math.min(5, bw / 2))}"/>`;
					// The figure on top of each bar (single series, few bars): the chart reads without the axis.
					if (labels && v > 0) s += `<text class="ceo-barlbl ${A.dim(i)}" x="${xc(i) + off}" y="${y(v) - 7}" text-anchor="middle">${esc(axisNum(v, kind))}</text>`;
				});
			});
			const lines = series.filter((x) => x.type === "line");
			for (const se of lines) {
				let path = "", pen = false, first = null, last = null;
				se.vals.forEach((v, i) => { if (v == null || !isFinite(v)) { pen = false; return; } path += `${pen ? "L" : "M"}${xc(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true; if (first == null) first = i; last = i; });
				// A soft area under a lone line, a thicker stroke, and a marker only on the latest point.
				if (lines.length === 1 && !bars.length && se.area !== false && last != null) s += `<path class="ceo-area ${se.cls}" d="${path}L${xc(last).toFixed(1)},${y(Math.max(y0, 0))}L${xc(first).toFixed(1)},${y(Math.max(y0, 0))}Z"/>`;
				s += `<path class="ceo-line ${se.cls}" ${se.dash ? `stroke-dasharray="${se.dash}"` : ""} d="${path}"/>`;
				if (se.dots === true && band >= 9) se.vals.forEach((v, i) => { if (v != null && isFinite(v)) s += `<circle class="ceo-mark ${se.cls} ${A.dim(i)}" cx="${xc(i)}" cy="${y(v)}" r="${band < 16 ? 2.5 : 3.5}"/>`; });
				else if (last != null && se.dots !== false) s += `<circle class="ceo-mark ${se.cls}" cx="${xc(last)}" cy="${y(se.vals[last])}" r="4.5"/>`;
			}
			for (let i = 0; i < N; i++) {
				s += `<rect class="ceo-band ${A.dim(i)}" x="${m.l + band * i}" y="${m.t}" width="${band}" height="${ih}" ${A.band(i)} data-tip="${tip(tipFor(i, A.val(i)))}" tabindex="0" aria-label="${esc(A.aria(i))}"/>`;
			}
			return s + "</svg>";
		}
		const legend = (items) => { items = items.filter(([cls]) => SHOW_COMPARISON || cls !== "prev"); return items.length < 2 ? "" : `<div class="ceo-legend">${items.map(([cls, label, shape]) => `<span><i class="ceo-lk ${shape || "line"} ${cls}"></i>${esc(label)}</span>`).join("")}</div>`; };
		function table(headers, rows) {
			return `<div class="ceo-tablewrap"><table class="ceo-table"><thead><tr>${headers.map((h, i) => `<th class="${i ? "num" : ""}">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td class="${i ? "num" : ""}">${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
		}

		const shapeOf = (name) => st.shape[name] || CHART_SHAPE[name];
		const cmpActive = () => st.cmp.series.length > 1 || st.cmp.years.length > 0 || st.cmp.grain !== "auto";
		function renderTrend() {
			if (cmpActive()) return renderTrendCompare();
			const el = slot("trend"), v = st.view, sel = st.sel.seg.size > 0, line = shapeOf("trend") === "line";
			const what = st.measure === "kg" ? __("LP Gas sold") : __("Net sales");
			setTitle("trend", `${what} · ${v.title}`);
			sub("trend", `${st.measure === "kg"
				? __("Each bar = metric tonnes (MT) of LP Gas sold in that {0}.", [v.noun])
				: __("Each bar = net sales billed in that {0}, in rupees (after discount, before VAT).", [v.noun])}${sel ? " " + __("Solid = the picked segment, faint = all segments.") : ""} ${__("Grey line = the same {0} a year earlier.", [v.noun])} ${v.hint}`);
			const hl = bucketSums(v, { ok: (r, day) => passX(r, "", day), val: mv });
			if (!hl) { el.innerHTML = chartLoading(); return; }
			const fullS = sel ? bucketSums(v, { ok: (r, day) => passX(r, "seg", day), val: mv }).cur : null;
			const cur = hl.cur, ly = hl.prev;
			if (st.tables.has("trend")) {
				el.innerHTML = SHOW_COMPARISON
					? table([__("Period"), __("Value"), __("A year earlier"), __("Change")], cur.map((x, i) => [esc(v.long(i)), x == null ? "—" : esc(fmtM(x)), ly[i] == null ? "—" : esc(fmtM(ly[i])), x != null && ly[i] ? delta(x, ly[i]) : ""]).filter((r, i) => cur[i] != null || ly[i] != null))
					: table([__("Period"), __("Value")], cur.map((x, i) => [esc(v.long(i)), x == null ? "—" : esc(fmtM(x))]).filter((r, i) => cur[i] != null));
				return;
			}
			el.innerHTML = legend([["cur", sel ? __("Picked segment") : __("This period"), line ? "line" : "rect"], ...(sel && !line ? [["full", __("All segments"), "rect"]] : []), ["prev", __("Same {0} a year earlier", [v.noun])]]) + timeAxis(el, {
				axis: viewAxis(v),
				series: [line ? { type: "line", vals: cur, cls: "cur" } : { type: "bar", vals: cur, full: fullS, cls: "cur" }, { type: "line", vals: ly, cls: "prev" }],
				kind: st.measure,
				tipFor: (i) => {
					const rows = [["cur rect", sel ? __("Picked segment") : measureName(), cur[i] == null ? "—" : esc(fmtM(cur[i]))]];
					if (sel) rows.push(["full rect", __("All segments"), `${esc(fmtM(fullS[i] || 0))}${fullS[i] ? ` · ${inr(((cur[i] || 0) / fullS[i]) * 100, 0)}% ${__("share")}` : ""}`]);
					if (ly[i] != null) rows.push(["prev", `${__("A year earlier")} · ${v.longPrev(i)}`, esc(fmtM(ly[i]))]);
					return tipRows(v.long(i), rows, cur[i] != null && ly[i] ? delta(cur[i], ly[i]) : "");
				},
			});
		}

		// -------------------------------------------------------- compare
		// One chart, any mix of sales / purchases / collected / expenses, this
		// fiscal year with up to two others dashed over it, at any grain from a
		// half-year to a day. Day rows come from series.get_series; the buckets
		// are built here, so every switch is instant.
		function cmpBuckets(grain, y) {
			const d = D(), mb = d.month_bounds, m0 = y * 12, fyStart = mb[m0][0], fyEnd = mb[m0 + 11][1];
			const days = daysBetween(fyStart, fyEnd) + 1, mname = (i) => monthName(m0 + i);
			const monthStart = (mi) => mb[m0 + mi][0];
			const specs = {
				half: { n: 2, of: (x) => (x.mi < 6 ? 0 : 1), start: (i) => monthStart(i * 6), label: (i) => `${mname(i * 6).slice(0, 3)}–${mname(i * 6 + 5).slice(0, 3)}`, long: (i) => `${mname(i * 6)} – ${mname(i * 6 + 5)}`, xTitle: __("Half-year (Nepali calendar)") },
				quarter: { n: 4, of: (x) => Math.floor(x.mi / 3), start: (i) => monthStart(i * 3), label: (i) => `Q${i + 1}`, sub: (i) => `${mname(i * 3).slice(0, 3)}–${mname(i * 3 + 2).slice(0, 3)}`, long: (i) => `Q${i + 1} · ${mname(i * 3)} – ${mname(i * 3 + 2)}`, xTitle: __("Quarter (Nepali calendar)") },
				month: { n: 12, of: (x) => x.mi, start: (i) => monthStart(i), label: (i, nar) => mname(i).slice(0, nar ? 1 : 3), long: (i) => mname(i), xTitle: __("Month (Nepali calendar)") },
				halfmonth: { n: 24, of: (x) => x.mi * 2 + (x.day > 15 ? 1 : 0), start: (i) => (i % 2 ? isoAdd(monthStart(i >> 1), 15) : monthStart(i >> 1)), label: (i) => (i % 2 ? "16+" : mname(i >> 1).slice(0, 3)), long: (i) => `${mname(i >> 1)} ${i % 2 ? "16 – " + __("end") : "1 – 15"}`, xTitle: __("Half-month (Nepali calendar)") },
				week: { n: Math.ceil(days / 7), of: (x) => Math.floor(x.off / 7), start: (i) => isoAdd(fyStart, i * 7), label: (i) => (i % 4 === 0 ? `W${i + 1}` : ""), long: (i) => `${__("Week {0}", [i + 1])} · ${bsShort(isoAdd(fyStart, i * 7))} – ${bsShort(isoAdd(fyStart, Math.min(days - 1, i * 7 + 6)))}`, xTitle: __("Week of the fiscal year"), every: 1 },
				day: { n: days, of: (x) => x.off, start: (i) => isoAdd(fyStart, i), label: (i) => { const x = bsDay(isoAdd(fyStart, i)); return x && x.day % 10 === 1 && x.day < 31 ? String(x.day) : ""; }, long: (i) => { const iso = isoAdd(fyStart, i); return `${bsShort(iso)} · ${WEEKDAY[dow(iso)]}`; }, xTitle: __("Day (Nepali calendar)"), every: 1 },
			};
			const sp = specs[grain];
			// The year at the start; month names where a month starts (week and day grains).
			const group = (i) => {
				if (grain !== "week" && grain !== "day") return i === 0 ? yearOf(m0) : null;
				const x = bsDay(sp.start(i)), prev = i ? bsDay(sp.start(i - 1)) : null;
				return x && (!prev || prev.m !== x.m) ? mname(x.m - m0) : null;
			};
			return { ...sp, group, fyStart, year: y };
		}
		const cmpDayInfo = new Map();   // AD date -> { y, mi, day, off } on the timeline
		function cmpInfo(iso) {
			let x = cmpDayInfo.get(iso);
			if (x === undefined) {
				const b = bsDay(iso);
				x = b ? { y: Math.floor(b.m / 12), mi: b.m % 12, day: b.day, off: daysBetween(D().month_bounds[b.m - (b.m % 12)][0], iso) } : null;
				cmpDayInfo.set(iso, x);
			}
			return x;
		}
		function cmpSeriesValues(key, grain, y) {
			const B = cmpBuckets(grain, y), out = new Array(B.n).fill(0), ser = st.ser, kg = st.measure === "kg";
			const put = (iso, v) => { const x = cmpInfo(iso); if (x && x.y === y) { const i = B.of(x); if (i >= 0 && i < B.n) out[i] += v; } };
			if (key === "sales") for (const r of ser.sales) { if ((st.internal || !r[3]) && passCo(r[1]) && (!st.sel.seg.size || st.sel.seg.has(r[2]))) put(r[0], kg ? r[4] : r[5]); }
			else if (key === "coll") for (const r of ser.coll) { if ((st.internal || !r[3]) && passCo(r[1]) && (!st.sel.seg.size || st.sel.seg.has(r[2]))) put(r[0], r[4]); }
			else if (key === "buy") for (const r of ser.buy) { if ((st.internal || !r[2]) && passCo(r[1])) put(r[0], kg ? r[3] : r[4]); }
			else if (key === "exp") for (const r of ser.exp) { if (passCo(r[1])) put(r[0], r[2]); }
			// Buckets after "data through" are blank, not zero.
			const thr = st.ser.through;
			return out.map((v, i) => (B.start(i) <= thr ? v : null));
		}
		// The trend chart with options from its funnel panel: extra series,
		// other fiscal years, a chosen grain. Bars or lines (shape).
		function renderTrendCompare() {
			const el = slot("trend"), d = D(), c = st.cmp, kg = st.measure === "kg", line = shapeOf("trend") === "line";
			const allowed = CMP_SERIES.filter(([, , hasKg]) => !kg || hasKg), active = allowed.filter(([k]) => c.series.includes(k));
			const yBase = d.years.indexOf(st.fy), yrs = [st.fy, ...c.years.filter((y) => d.years.includes(y) && y !== st.fy)];
			const grain = c.grain === "auto" ? "month" : c.grain, gl = (CMP_GRAINS.find(([g]) => g === grain) || [])[1];
			setTitle("trend", `${active.map(([, l]) => __(l)).join(" · ")} · ${__("by {0}", [__(gl).toLowerCase()])} · ${yrs.join(" · ")}`);
			// Day rows must be for this fiscal year and timeline; otherwise fetch (loadSeries skips a fetch already running).
			const stale = !st.ser || st.ser.loading || (!st.ser.failed && (st.ser.fiscal_year !== st.fy || st.ser.years_back !== yearsBack()));
			if (stale) { loadSeries(false); el.innerHTML = chartLoading(); return; }
			if (st.ser.failed || yBase < 0) { el.innerHTML = `<div class="ceo-empty">${__("Not available.")}</div>`; return; }
			const B = cmpBuckets(grain, yBase), lines = [];
			for (const [k, l] of active) yrs.forEach((y, yi) => {
				const yy = d.years.indexOf(y);
				if (yy >= 0) lines.push({ key: k, label: `${__(l)}${yrs.length > 1 ? ` ${y}` : ""}`, year: y, yi, vals: cmpSeriesValues(k, grain, yy), dash: CMP_DASH[yi] });
			});
			lines.forEach((x, i) => (x.cls = `k${i % CMP_COLOURS}`));
			const fmt = (v) => (v == null ? "—" : kg ? mt(v) : rs(v));
			if (st.tables.has("trend")) {
				el.innerHTML = table([__("Period"), ...lines.map((x) => x.label)], Array.from({ length: B.n }, (_, i) => [esc(B.long(i)), ...lines.map((x) => esc(fmt(x.vals[i])))]).filter((r, i) => lines.some((x) => x.vals[i] != null)));
				return;
			}
			// Bars: only the first series in the chosen year is bars; whatever it is
			// compared with (another year, an added series) is a line over the bars.
			const asLine = (x, i) => line || i > 0;
			const key = (x, i) => asLine(x, i)
				? `<svg width="26" height="6" aria-hidden="true"><line class="ceo-line ${x.cls}" x1="1" y1="3" x2="25" y2="3" ${x.dash ? `stroke-dasharray="${x.dash}"` : ""}/></svg>`
				: `<i class="ceo-lk rect ${x.cls}"></i>`;
			const lg = `<div class="ceo-legend">${lines.map((x, i) => `<span>${key(x, i)}${esc(x.label)}</span>`).join("")}</div>`;
			el.innerHTML = lg + timeAxis(el, {
				axis: { n: B.n, val: () => undefined, label: B.label, sub: B.sub, group: B.group, shade: () => false, dim: () => "", last: () => false, band: () => "", aria: B.long, xTitle: B.xTitle, every: B.every },
				series: lines.map((x, i) => (asLine(x, i) ? { type: "line", vals: x.vals, cls: x.cls, dash: x.dash, area: line && lines.length === 1 } : { type: "bar", vals: x.vals, cls: x.cls })),
				kind: kg ? "kg" : "amt",
				tipFor: (i) => tipRows(B.long(i), lines.map((x, k) => [`${x.cls} ${asLine(x, k) ? "" : "rect"}`, x.label, esc(fmt(x.vals[i]))])),
			});
		}
		// The funnel panel of a chart: shape for every time chart; grain, extra
		// series and other years for the trend chart.
		function popHtml(name) {
			const d = D(), c = st.cmp, kg = st.measure === "kg";
			const seg = (act, items, cur, extra = "") => `<div class="ceo-seg small">${items.map(([v, l]) => `<button data-act="${act}" data-val="${v}" ${extra} aria-pressed="${cur === v}">${esc(__(l))}</button>`).join("")}</div>`;
			let h = `<section><h5>${__("Shape")}</h5>${seg("shape", [["bar", "Bars"], ["line", "Line"]], shapeOf(name), `data-name="${name}"`)}</section>`;
			if (name !== "trend") return h;
			h += `<section><h5>${__("Show by")}</h5>${seg("cmp-grain", [["auto", "Follow the period"], ...CMP_GRAINS], c.grain)}</section>`;
			const extra = CMP_SERIES.filter(([k, , hasKg]) => k !== "sales" && (!kg || hasKg));
			h += `<section><h5>${__("Add")}</h5><div class="ceo-chips-row">${extra.map(([k, l]) => `<button class="ceo-chip ${c.series.includes(k) ? "on" : "add"}" data-act="cmp-tog" data-val="${k}"><i></i>${esc(__(l))}${c.series.includes(k) ? `<span aria-hidden="true">✕</span>` : ""}</button>`).join("")}</div></section>`;
			const others = d.years.filter((y) => y !== st.fy).reverse();
			if (others.length) h += `<section><h5>${__("Compare with")}</h5><div class="ceo-chips-row">${others.map((y) => `<button class="ceo-chip ${c.years.includes(y) ? "on year" : "add"}" data-act="cmp-year" data-val="${esc(y)}"><i class="dash d${c.years.indexOf(y) + 1}"></i>${esc(y)}${c.years.includes(y) ? `<span aria-hidden="true">✕</span>` : ""}</button>`).join("")}</div></section>`;
			return h;
		}
		function renderPop() {
			root.querySelectorAll("[data-pop]").forEach((e) => {
				const open = e.dataset.pop === st.pop;
				e.hidden = !open;
				if (open) e.innerHTML = popHtml(e.dataset.pop);
				const b = e.parentElement.querySelector("[data-act='copts']");
				if (b) { b.setAttribute("aria-expanded", open); b.classList.toggle("is-on", e.dataset.pop === "trend" ? cmpActive() || !!st.shape.trend : !!st.shape[e.dataset.pop]); }
			});
		}

		function renderPrice() {
			const el = slot("price"), v = st.view, sel = narrowed();
			sub("price", __("Each point = average selling price of LP Gas in that {0}: net sales ÷ kg sold, in rupees per kg.", [v.noun]));
			const gas = bucketSums(v, { ok: (r, day) => r[R_GAS] && passX(r, "", day), val: (r) => r[R_GAS] });
			const kg = bucketSums(v, { ok: (r, day) => r[R_GAS] && passX(r, "", day), val: (r) => r[R_KG] });
			if (!gas) { el.innerHTML = chartLoading(); return; }
			// With a customer picked, day rows are that customer's only: no group line then.
			const showGrp = sel && !st.sel.co.size && !(v.grain !== "month" && st.sel.cust.size);
			const gG = showGrp && bucketSums(v, { ok: (r, day) => r[R_GAS] && allX(r, day), val: (r) => r[R_GAS] });
			const kG = showGrp && bucketSums(v, { ok: (r, day) => r[R_GAS] && allX(r, day), val: (r) => r[R_KG] });
			const rate = (g, k, i) => (k[i] > 0 && g[i] != null ? g[i] / k[i] : null);
			const cur = gas.cur.map((_, i) => rate(gas.cur, kg.cur, i)), grp = showGrp ? gG.cur.map((_, i) => rate(gG.cur, kG.cur, i)) : null;
			if (st.tables.has("price")) {
				el.innerHTML = table([__("Period"), sel ? __("Selection") : __("Group"), ...(showGrp ? [__("Group")] : [])], cur.map((x, i) => [esc(v.long(i)), x == null ? "—" : `Rs ${inr(x, 2)}`, ...(showGrp ? [grp[i] == null ? "—" : `Rs ${inr(grp[i], 2)}`] : [])]).filter((r, i) => cur[i] != null));
				return;
			}
			el.innerHTML = legend(showGrp ? [["cur", __("Your selection")], ["prev", __("Whole group")]] : [["cur", sel ? __("Your selection") : __("Group average")]]) + timeAxis(el, {
				axis: viewAxis(v),
				series: [...(showGrp ? [{ type: "line", vals: grp, cls: "prev", dots: false }] : []), { type: "line", vals: cur, cls: "cur" }],
				kind: "rate", height: 240,
				tipFor: (i) => tipRows(v.long(i), [["cur", sel ? __("Selection") : __("Group"), cur[i] == null ? "—" : `Rs ${inr(cur[i], 2)}`], ...(showGrp ? [["prev", __("Whole group"), grp[i] == null ? "—" : `Rs ${inr(grp[i], 2)}`]] : [])]),
			});
		}

		function renderColl() {
			const el = slot("coll"), v = st.view;
			sub("coll", __("Blue bar = net sales billed in that {0}; green bar = money received from customers in that {0} (Payment Entries). Rupees.", [v.noun]));
			const Bs = bucketSums(v, { ok: (r, day) => passX(r, "", day), val: (r) => r[R_AMT] });
			const Cs = bucketSums(v, { coll: true, ok: (r, day) => passCollX(r, "", day), val: (r) => r[C_AMT] });
			if (!Bs || !Cs) { el.innerHTML = chartLoading(); return; }
			const B = Bs.cur, C = Cs.cur;
			if (st.tables.has("coll")) {
				el.innerHTML = table([__("Period"), __("Billed"), __("Collected"), "%"], B.map((x, i) => [esc(v.long(i)), x == null ? "—" : esc(rs(x)), C[i] == null ? "—" : esc(rs(C[i])), x ? `${inr((C[i] / x) * 100, 0)}%` : "—"]).filter((r, i) => B[i] != null));
				return;
			}
			const shape = shapeOf("coll"), lk = shape === "line" ? "line" : "rect";
			el.innerHTML = legend([["bill", __("Billed (net sales)"), lk], ["coll", __("Collected (received)"), lk]]) + timeAxis(el, {
				axis: viewAxis(v),
				series: [{ type: shape, vals: B, cls: "bill" }, { type: shape, vals: C, cls: "coll" }],
				kind: "amt", height: 240,
				tipFor: (i) => tipRows(v.long(i), [["bill rect", __("Billed"), B[i] == null ? "—" : esc(rs(B[i]))], ["coll rect", __("Collected"), C[i] == null ? "—" : esc(rs(C[i]))], ["", __("Collected / billed"), B[i] ? `${inr((C[i] / B[i]) * 100, 0)}%` : "—"]]),
			});
		}

		// Sale and purchase price per kg in the view's buckets (purchase price =
		// the company's gas Purchase Invoices that month, see buyRate).
		function marginBuckets(v) {
			const ok = (r, day) => r[R_GAS] && passX(r, "", day);
			const priced = (f) => (r, mo) => { const b = buyRate(r[R_CO], mo); return b == null ? 0 : f(r, b); };
			const gas = bucketSums(v, { ok, val: priced((r) => r[R_GAS]) });
			if (!gas) return null;
			const kg = bucketSums(v, { ok, val: priced((r) => r[R_KG]) }).cur, cost = bucketSums(v, { ok, val: priced((r, b) => r[R_KG] * b) }).cur;
			const allKg = bucketSums(v, { ok, val: (r) => r[R_KG] }).cur;
			const at = (f) => kg.map((k, i) => (k > 0 ? f(i, k) : null));
			return { sell: at((i, k) => gas.cur[i] / k), buy: at((i, k) => cost[i] / k), m: at((i, k) => (gas.cur[i] - cost[i]) / k), share: kg.map((k, i) => (allKg[i] ? k / allKg[i] : 0)) };
		}

		// -------------------------------------------------------- bar lists
		function barList(items, { dim, colorFor, drill, fill, fmt = fmtM, upGood = true, named = false }) {
			const max = Math.max(1, ...items.map((x) => Math.max(x.full ?? x.cur, SHOW_COMPARISON ? x.prev : 0)));
			return `<div class="ceo-bars ${named ? "named" : ""}" role="list">${items.map((x, k) => {
				const w = (Math.max(0, x.cur) / max) * 100, fw = x.full != null ? (Math.max(0, x.full) / max) * 100 : null, pw = (Math.max(0, x.prev) / max) * 100;
				const color = colorFor ? colorFor(x.val) : fill || "var(--ceo-neutral)";
				return `<div class="ceo-barrow ${SHOW_COMPARISON ? "" : "nochg"} ${dimState(dim, x.val)}" role="listitem" tabindex="0" data-dim="${dim}" data-val="${x.val}" data-tip="${tip(x.tip)}">
					<div class="ceo-barlabel">${colorFor ? `<span class="ceo-dot" style="background:${color}"></span>` : ""}<span title="${esc(x.title || x.label)}">${esc(x.label)}${x.sub ? `<small>${esc(x.sub)}</small>` : ""}</span></div>
					<div class="ceo-bartrack">
						${fw != null ? `<div class="ceo-barfill faint" style="width:${fw}%;background:${color}"></div>` : ""}
						<div class="ceo-barfill" style="width:${w}%;background:${color};--i:${k}"></div>
						${SHOW_COMPARISON && x.prev > 0 ? `<div class="ceo-bartick" style="left:${pw}%"></div>` : ""}
					</div>
					<div class="ceo-barval">${esc(fmt(x.cur))}</div>
					${SHOW_COMPARISON ? `<div class="ceo-barchg">${delta(x.cur, x.prev, { upGood })}</div>` : ""}
					${drill ? `<button class="ceo-drill" data-act="drill" data-kind="${drill}" data-val="${x.val}" title="${esc(__("Details"))}" aria-label="${esc(__("Details"))}">›</button>` : ""}
				</div>`;
			}).join("")}</div>`;
		}
		// Sum this period / comparison per key, plus `full` (ignoring the highlight dims).
		function byDim(W, keyFn, hlSkip, fullSkip) {
			const out = new Map();
			const get = (k) => out.get(k) || out.set(k, { cur: 0, prev: 0, full: 0, cust: new Set() }).get(k);
			for (const r of D().sales) {
				const s = r[R_SLOT], c = inWin(W, s), p = inCmp(W, s);
				if (!c && !p) continue;
				if (c && pass(r, fullSkip)) get(keyFn(r)).full += mv(r);
				if (pass(r, hlSkip)) { const x = get(keyFn(r)); if (c) { x.cur += mv(r); if (r[R_AMT] > 0) x.cust.add(r[R_CU]); } if (p) x.prev += mv(r); }
			}
			return out;
		}

		function renderCompanies(W) {
			const el = slot("company"), hlSeg = st.sel.seg.size > 0;
			const b = byDim(W, (r) => r[R_CO], "co", "co,seg");
			const items = shownCompanies().map((c) => {
				const x = b.get(c.i) || { cur: 0, prev: 0, full: 0 };
				return {
					val: c.i, label: c.abbr, sub: c.name, title: c.name, cur: x.cur, prev: x.prev, full: hlSeg ? x.full : null,
					tip: tipRows(c.name, [["cur rect", hlSeg ? __("Selected segment") : __("This period"), esc(fmtM(x.cur))], ...(hlSeg ? [["full rect", __("All segments"), esc(fmtM(x.full))]] : []), ["prev", __("Comparison period"), esc(fmtM(x.prev))]], delta(x.cur, x.prev)),
				};
			}).filter((x) => x.cur || x.prev || x.full).sort((a, b) => (b.full ?? b.cur) - (a.full ?? a.cur));
			const total = items.reduce((a, x) => a + Math.max(0, x.cur), 0);
			sub("company", `${measureName()}. ${__("Tick = comparison period.")}`);
			el.innerHTML = shareBar(items, total) + barList(capped(items, "company"), { dim: "co", drill: "co", fill: "var(--ceo-cur)", named: true }) + showAll(items, "company");
		}

		// One-colour segmented bar: the largest parts by name, the rest as "Other".
		function shareBar(items, total) {
			if (!(total > 0)) return "";
			const pos = items.filter((x) => x.cur > 0).sort((a, b) => b.cur - a.cur);
			const head = pos.slice(0, SHARE_PARTS_MAX), rest = pos.slice(SHARE_PARTS_MAX);
			const restV = rest.reduce((a, x) => a + x.cur, 0);
			const part = (x, sh) => `<div class="ceo-share-part ${dimState("co", x.val)}" style="flex:${sh}" data-dim="co" data-val="${x.val}" data-tip="${tip(tipRows(x.title, [["", st.sel.co.size ? __("Share of picked companies") : __("Share of group"), `${inr(sh * 100, 1)}%`], ["", measureName(), esc(fmtM(x.cur))]]))}">${sh > 0.15 ? `<span>${esc(x.label)} ${inr(sh * 100, 0)}%</span>` : sh > 0.06 ? `<span>${inr(sh * 100, 0)}%</span>` : ""}</div>`;
			return `<div class="ceo-share" role="img" aria-label="${esc(__("Share of group"))}">${head.map((x) => part(x, x.cur / total)).join("")}${restV > 0 ? `<div class="ceo-share-part other" style="flex:${restV / total}" data-tip="${tip(tipRows(__("Other {0} companies", [rest.length]), [["", __("Share of group"), `${inr((restV / total) * 100, 1)}%`], ["", measureName(), esc(fmtM(restV))]]))}">${restV / total > 0.15 ? `<span>${__("Other")} ${inr((restV / total) * 100, 0)}%</span>` : restV / total > 0.06 ? `<span>${inr((restV / total) * 100, 0)}%</span>` : ""}</div>` : ""}</div>`;
		}
		// Largest COMPANY_LIST_MAX unless "Show all"; a selected company always stays visible.
		function capped(items, key) {
			if (st.coShowAll[key] || items.length <= COMPANY_LIST_MAX) return items;
			const top = items.slice(0, COMPANY_LIST_MAX);
			return [...top, ...items.slice(COMPANY_LIST_MAX).filter((x) => st.sel.co.has(x.val))];
		}
		const showAll = (items, key) => (items.length > COMPANY_LIST_MAX ? `<button class="ceo-ghost ceo-showall" data-act="show-all" data-val="${key}">${st.coShowAll[key] ? __("Show the largest {0}", [COMPANY_LIST_MAX]) : __("Show all {0} companies", [items.length])}</button>` : "");

		function renderSegments(W) {
			const d = D(), el = slot("segment"), from = PM() - 23;
			// Per segment: this period / comparison (for the picked companies, if
			// any), Rs/kg, customers, 24-month series.
			const seg = d.segments.map(() => ({ cur: 0, prev: 0, gas: 0, gasK: 0, gasP: 0, gasKP: 0, kg: 0, amt: 0, cust: new Set(), custP: new Set(), spark: new Float64Array(24) }));
			for (const r of d.sales) {
				const s = r[R_SLOT], c = inWin(W, s), p = inCmp(W, s), x = seg[r[R_SEG]], m = (s >> 1) - from;
				if (pass(r, "seg")) {
					if (m >= 0 && m < 24) x.spark[m] += mv(r);
					if (c) { x.cur += mv(r); x.kg += r[R_KG]; x.amt += r[R_AMT]; x.gas += r[R_GAS]; x.gasK += r[R_GAS] ? r[R_KG] : 0; if (r[R_AMT] > 0) x.cust.add(r[R_CU]); }
					if (p) { x.prev += mv(r); x.gasP += r[R_GAS]; x.gasKP += r[R_GAS] ? r[R_KG] : 0; if (r[R_AMT] > 0) x.custP.add(r[R_CU]); }
				}
			}
			const items = d.segments.map((name, i) => ({ val: i, label: name, ...seg[i] }));
			const total = items.reduce((a, x) => a + Math.max(0, x.cur), 0);
			sub("segment", `${measureName()}. ${__("From the Customer Group name: dealer, bulk, other. Click a segment to highlight it everywhere.")}`);
			if (st.tables.has("segment")) {
				el.innerHTML = !SHOW_COMPARISON ? table([__("Segment"), __("This period"), __("Share"), __("Customers"), otherName(), __("Per customer")], items.map((x) => [esc(x.label), esc(fmtM(x.cur)), total ? `${inr((x.cur / total) * 100, 1)}%` : "—", inr(x.cust.size), esc(otherVal(x)), x.cust.size ? esc(fmtM(x.cur / x.cust.size)) : "—"])) : table([__("Segment"), __("This period"), __("Before"), __("Change"), __("Share"), __("Customers"), __("Rs/kg"), __("Per customer")], items.map((x) => [esc(x.label), esc(fmtM(x.cur)), esc(fmtM(x.prev)), delta(x.cur, x.prev), total ? `${inr((x.cur / total) * 100, 1)}%` : "—", inr(x.cust.size), x.gasK ? `Rs ${inr(x.gas / x.gasK, 2)}` : "—", x.cust.size ? esc(fmtM(x.cur / x.cust.size)) : "—"]));
				return;
			}
			const max = Math.max(1, ...items.map((x) => Math.max(x.cur, SHOW_COMPARISON ? x.prev : 0)));
			const wm = winMonths(W);
			const rows = items.map((x) => {
				const share = total ? x.cur / total : 0, perCust = x.cust.size ? x.cur / x.cust.size : 0, perCustP = x.custP.size ? x.prev / x.custP.size : 0;
				const rate = x.gasK ? x.gas / x.gasK : 0, rateP = x.gasKP ? x.gasP / x.gasKP : 0;
				const third = SHOW_RATE ? `<div class="ceo-segstat"><span>${__("Rs/kg")}</span><strong>${rate ? inr(rate, 2) : "—"}</strong>${rateP ? delta(rate, rateP) : ""}</div>`
					: `<div class="ceo-segstat"><span>${esc(otherName())}</span><strong>${esc(otherVal(x))}</strong></div>`;
				return `<div class="ceo-segrow ${dimState("seg", x.val)}" data-dim="seg" data-val="${x.val}" tabindex="0" data-tip="${tip(tipRows(x.label, [["cur rect", __("This period"), esc(fmtM(x.cur))], ["prev", __("Comparison period"), esc(fmtM(x.prev))]], delta(x.cur, x.prev)))}">
					<div class="ceo-segname"><span class="ceo-segkey" style="background:var(--ceo-seg${x.val})"></span><div><strong>${esc(x.label)}</strong><small>${inr(share * 100, 1)}% ${__("of the total")}</small></div></div>
					<div class="ceo-segmain">
						<div class="ceo-segval"><strong>${esc(fmtM(x.cur))}</strong>${SHOW_COMPARISON ? `${delta(x.cur, x.prev)}<span class="ceo-muted">${__("from")} ${esc(fmtM(x.prev))}</span>` : ""}</div>
						<div class="ceo-bartrack big"><div class="ceo-barfill" style="width:${(Math.max(0, x.cur) / max) * 100}%;background:var(--ceo-seg${x.val});--i:${x.val}"></div>${SHOW_COMPARISON && x.prev > 0 ? `<div class="ceo-bartick" style="left:${(x.prev / max) * 100}%"></div>` : ""}</div>
					</div>
					<div class="ceo-segstat"><span>${__("Customers")}</span><strong>${inr(x.cust.size)}</strong>${delta(x.cust.size, x.custP.size)}</div>
					<div class="ceo-segstat"><span>${__("Per customer")}</span><strong>${x.cust.size ? esc(fmtM(perCust)) : "—"}</strong>${perCustP ? delta(perCust, perCustP) : ""}</div>
					${third}
					<div class="ceo-segspark"><span>${__("24 months")}</span>${spark(flow(Array.from(x.spark)), wm, false)}</div>
				</div>`;
			}).join("");
			el.innerHTML = `<div class="ceo-segbig">${segDonut(items, total)}<div class="ceo-segrows">${rows}</div></div>`;
		}
		// The measure not being shown: net sales beside volume, volume beside sales.
		const otherName = () => (st.measure === "kg" ? __("Net sales") : __("Volume"));
		const otherVal = (x) => (st.measure === "kg" ? rs(x.amt) : mt(x.kg));
		// Ring showing the split; the rows beside it carry the values.
		function segDonut(items, total) {
			if (!(total > 0)) return "";
			const r = 70, c = 2 * Math.PI * r, cx = 90;
			let off = 0;
			const segs = items.filter((x) => x.cur > 0).map((x) => {
				const len = (x.cur / total) * c, gap = Math.min(3, len / 3);
				const s = `<circle r="${r}" cx="${cx}" cy="${cx}" fill="none" class="ceo-ring ${dimState("seg", x.val)}" stroke="var(--ceo-seg${x.val})" stroke-width="20" stroke-dasharray="${Math.max(0.01, len - gap)} ${c}" stroke-dashoffset="${-off}" transform="rotate(-90 ${cx} ${cx})" data-dim="seg" data-val="${x.val}" data-tip="${tip(tipRows(x.label, [["", __("Share"), `${inr((x.cur / total) * 100, 1)}%`], ["", measureName(), esc(fmtM(x.cur))]]))}"/>`;
				off += len;
				return s;
			}).join("");
			return `<div class="ceo-donutwrap"><svg class="ceo-donut" viewBox="0 0 180 180" width="190" height="190" role="img" aria-label="${esc(__("Segment split"))}">${segs}<text x="${cx}" y="${cx - 4}" text-anchor="middle" class="ceo-donut-v">${esc(fmtM(total))}</text><text x="${cx}" y="${cx + 16}" text-anchor="middle" class="ceo-donut-l">${__("all segments")}</text></svg>
				<div class="ceo-donutleg">${items.filter((x) => x.cur > 0).map((x) => `<span><i style="background:var(--ceo-seg${x.val})"></i>${esc(x.label)} <b>${inr((x.cur / total) * 100, 0)}%</b></span>`).join("")}</div></div>`;
		}

		// -------------------------------------------------------- scorecard
		function renderMatrix(W) {
			const d = D(), el = slot("matrix"), from = PM() - 23;
			const per = new Map();
			const get = (i) => per.get(i) || per.set(i, { kg: 0, kgP: 0, amt: 0, amtP: 0, gas: 0, gasK: 0, coll: 0, bills: 0, cust: new Set(), spark: new Float64Array(24) }).get(i);
			for (const r of d.sales) {
				if (!pass(r)) continue;
				const s = r[R_SLOT], m = (s >> 1) - from, x = get(r[R_CO]);
				if (m >= 0 && m < 24) x.spark[m] += mv(r);
				if (inWin(W, s)) { x.kg += r[R_KG]; x.amt += r[R_AMT]; x.gas += r[R_GAS]; x.gasK += r[R_GAS] ? r[R_KG] : 0; x.bills += r[R_BILLS] || 0; if (r[R_AMT] > 0) x.cust.add(r[R_CU]); }
				if (inCmp(W, s)) { x.kgP += r[R_KG]; x.amtP += r[R_AMT]; }
			}
			for (const r of d.coll) if (inWin(W, r[R_SLOT]) && passColl(r)) get(r[R_CO]).coll += r[C_AMT];
			const rows = shownCompanies().map((c) => ({ c, x: get(c.i) })).filter(({ x }) => x.kg || x.amt || x.kgP || x.coll).sort((a, b) => b.x.kg - a.x.kg || b.x.amt - a.x.amt);
			const maxKg = Math.max(1, ...rows.map((r) => r.x.kg)), maxAmt = Math.max(1, ...rows.map((r) => r.x.amt));
			const tot = rows.reduce((t, { x }) => { for (const k of ["kg", "kgP", "amt", "amtP", "gas", "gasK", "coll", "bills"]) t[k] += x[k]; x.cust.forEach((c) => t.cust.add(c)); x.spark.forEach((v, i) => (t.spark[i] += v)); return t; }, { kg: 0, kgP: 0, amt: 0, amtP: 0, gas: 0, gasK: 0, coll: 0, bills: 0, cust: new Set(), spark: new Float64Array(24) });
			const wm = winMonths(W), totKg = tot.kg || 1;
			const pctCell = (num, den) => (num && den ? `<span class="ceo-pct ${num / den < 0.5 ? "low" : ""}"><i><b style="width:${Math.min(100, (num / den) * 100)}%"></b></i>${inr((num / den) * 100, 0)}%</span>` : "—");
			const cells = (x, isTotal) => `
				<td class="num"><div class="ceo-cellbar"><span style="width:${(x.kg / (isTotal ? x.kg || 1 : maxKg)) * 100}%"></span></div>${esc(mt(x.kg))}</td>
				<td class="num">${isTotal ? "100%" : `${inr((x.kg / totKg) * 100, 1)}%`}</td>
				${SHOW_COMPARISON ? `<td class="num">${delta(x.kg, x.kgP)}</td>` : ""}
				<td class="num"><div class="ceo-cellbar amt"><span style="width:${(x.amt / (isTotal ? x.amt || 1 : maxAmt)) * 100}%"></span></div>${esc(rs(x.amt))}</td>
				${SHOW_COMPARISON ? `<td class="num">${delta(x.amt, x.amtP)}</td>` : ""}
				${SHOW_RATE ? `<td class="num">${x.gasK ? "Rs " + inr(x.gas / x.gasK, 2) : "—"}</td>` : ""}
				<td class="num">${x.coll ? esc(rs(x.coll)) : "—"}</td>
				<td class="num">${pctCell(x.coll, x.amt)}</td>
				<td class="num">${inr(x.cust.size)}</td>
				<td class="num">${inr(x.bills)}</td>
				<td class="ceo-sparkcell">${spark(flow(Array.from(x.spark)), wm, false)}</td>`;
			sub("matrix", __("This period against the comparison period. Click a row to show only that company, › for details."));
			el.innerHTML = `<div class="ceo-tablewrap"><table class="ceo-table ceo-matrix">
				<thead><tr><th>${__("Company")}</th><th class="num">${__("Volume")}</th><th class="num">${__("Share")}</th>${SHOW_COMPARISON ? `<th class="num">${__("Change")}</th>` : ""}<th class="num">${__("Net sales")}</th>${SHOW_COMPARISON ? `<th class="num">${__("Change")}</th>` : ""}${SHOW_RATE ? `<th class="num">${__("Rs/kg")}</th>` : ""}<th class="num">${__("Collected")}</th><th class="num">${__("Collected %")}</th><th class="num">${__("Customers")}</th><th class="num">${__("Bills")}</th><th>${__("24 months")}</th><th></th></tr></thead>
				<tbody>${rows.map(({ c, x }) => `<tr class="ceo-click ${dimState("co", c.i)}" data-dim="co" data-val="${c.i}" tabindex="0">
					<td><strong>${esc(c.abbr)}</strong> <span class="ceo-muted ceo-hide-sm">${esc(c.name)}</span></td>${cells(x)}
					<td><button class="ceo-drill" data-act="drill" data-kind="co" data-val="${c.i}" title="${esc(__("Details"))}" aria-label="${esc(__("Details"))}">›</button></td></tr>`).join("")}</tbody>
				<tfoot><tr><td><strong>${st.sel.co.size ? __("Picked companies") : __("All companies")}</strong></td>${cells(tot, true)}<td></td></tr></tfoot>
			</table></div>`;
		}

		// -------------------------------------------------------- customers
		function custAgg(W, skip) {
			const m = new Map();
			for (const r of D().sales) {
				const s = r[R_SLOT], c = inWin(W, s), p = inCmp(W, s);
				if ((!c && !p) || !pass(r, skip)) continue;
				let x = m.get(r[R_CU]);
				if (!x) m.set(r[R_CU], (x = { i: r[R_CU], cur: 0, prev: 0, cos: new Set() }));
				if (c) x.cur += mv(r);
				if (p) x.prev += mv(r);
				x.cos.add(r[R_CO]);
			}
			return m;
		}
		function renderCustomers() {
			const d = D(), el = slot("customers"), W = st.W;
			const q = st.custSearch.trim().toLowerCase();
			let list = [...custAgg(W, "cust").values()].filter((x) => x.cur || x.prev);
			const total = list.reduce((a, x) => a + Math.max(0, x.cur), 0);
			if (q) list = list.filter((x) => (d.customers[x.i][1] + " " + d.customers[x.i][0]).toLowerCase().includes(q));
			const tabs = {
				top: [__("Largest"), (a, b) => b.cur - a.cur, () => true],
				drop: [__("Falling"), (a, b) => (a.cur - a.prev) - (b.cur - b.prev), (x) => x.cur < x.prev],
				gain: [__("Rising"), (a, b) => (b.cur - b.prev) - (a.cur - a.prev), (x) => x.cur > x.prev && x.prev > 0],
				new: [__("New"), (a, b) => b.cur - a.cur, (x) => x.cur > 0 && x.prev <= 0],
				lost: [__("Lost"), (a, b) => b.prev - a.prev, (x) => x.prev > 0 && x.cur <= 0],
			};
			// Falling / Rising / New / Lost are comparisons: only "Largest" without them.
			if (!SHOW_COMPARISON) { for (const k of Object.keys(tabs)) if (k !== "top") delete tabs[k]; st.custTab = "top"; }
			const [, sorter, keep] = tabs[st.custTab];
			list = list.filter(keep).sort(sorter);
			const tools = slot("custtools");
			if (!tools.querySelector("input")) tools.innerHTML = `<input type="search" class="ceo-search" data-input="search" placeholder="${esc(__("Find customer"))}" aria-label="${esc(__("Find customer"))}"><div class="ceo-seg small" role="tablist"></div>`;
			tools.querySelector(".ceo-seg").hidden = !SHOW_COMPARISON;
			tools.querySelector(".ceo-seg").innerHTML = Object.entries(tabs).map(([k, [l]]) => `<button data-act="custtab" data-val="${k}" role="tab" aria-pressed="${st.custTab === k}">${esc(l)}</button>`).join("");
			sub("customers", `${measureName()}. ${__("Click a customer to see only them; › opens their bills.")}`);
			const top = list.slice(0, TOP_N);
			if (!top.length) { el.innerHTML = `<div class="ceo-empty">${__("No customers here for this selection.")}</div>`; return; }
			const max = Math.max(1, ...top.map((x) => Math.max(x.cur, SHOW_COMPARISON ? x.prev : 0)));
			el.innerHTML = `<div class="ceo-tablewrap"><table class="ceo-table ceo-cust">
				<thead><tr><th>${__("Customer")}</th><th>${__("Company")}</th><th class="num">${__("This period")}</th>${SHOW_COMPARISON ? `<th class="num">${__("Before")}</th><th class="num">${__("Change")}</th>` : ""}<th class="num">${__("Share")}</th><th class="num">${__("Last bill")}</th><th></th></tr></thead>
				<tbody>${top.map((x) => {
					const c = d.customers[x.i];
					return `<tr class="ceo-click ${dimState("cust", x.i)}" data-dim="cust" data-val="${x.i}" tabindex="0">
						<td><div class="ceo-custname"><span>${esc(c[1])}</span><small>${esc(d.segments[c[2]])}</small></div><div class="ceo-cellbar wide"><span style="width:${(Math.max(0, x.cur) / max) * 100}%"></span>${SHOW_COMPARISON && x.prev > 0 ? `<i style="left:${(x.prev / max) * 100}%"></i>` : ""}</div></td>
						<td class="ceo-cos">${[...x.cos].map((i) => `<span>${esc(d.companies[i].abbr)}</span>`).join("")}</td>
						<td class="num">${esc(fmtM(x.cur))}</td>
						${SHOW_COMPARISON ? `<td class="num">${esc(fmtM(x.prev))}</td><td class="num">${delta(x.cur, x.prev)}</td>` : ""}
						<td class="num">${total && x.cur > 0 ? inr((x.cur / total) * 100, 1) + "%" : "—"}</td>
						<td class="num">${esc(c[4] || "—")}</td>
						<td><button class="ceo-drill" data-act="drill" data-kind="cust" data-val="${x.i}" title="${esc(__("Details"))}" aria-label="${esc(__("Details"))}">›</button></td></tr>`;
				}).join("")}</tbody></table></div>
				<div class="ceo-foot">${__("Showing {0} of {1}", [inr(top.length), inr(list.length)])}</div>`;
		}

		function quietList() {
			const d = D(), W = new Uint8Array(NS()); for (let s = 0; s <= P(); s++) W[s] = 1;   // the whole timeline up to now
			const list = [];
			for (const x of custAgg(W, "cust").values()) {
				const c = d.customers[x.i];
				if (!c[3] || x.cur <= 0) continue;
				const gap = daysBetween(c[3], d.through);
				if (gap >= QUIET_DAYS && gap <= QUIET_MAX_DAYS) list.push({ ...x, gap, c });
			}
			return list.sort((a, b) => b.cur - a.cur);
		}
		function renderQuiet() {
			const past = pastYear(), stack = root.querySelector(".ceo-stack"), custCard = root.querySelector("[data-card='customers']");
			if (stack) stack.style.display = past ? "none" : "";
			if (custCard) custCard.style.gridColumn = past ? "span 12" : "";
			if (past) return;
			const d = D(), el = slot("quiet"), list = quietList();
			sub("quiet", __("Regular buyers with no bill for {0}+ days, largest first.", [QUIET_DAYS]));
			if (!list.length) { el.innerHTML = `<div class="ceo-empty">${__("Everyone here bought in the last {0} days.", [QUIET_DAYS])}</div>`; return; }
			el.innerHTML = `<ol class="ceo-list">${list.slice(0, QUIET_ROWS).map((x) => `<li class="ceo-click ${dimState("cust", x.i)}" data-dim="cust" data-val="${x.i}" tabindex="0" data-tip="${tip(tipRows(x.c[1], [["", __("Last bill"), esc(x.c[4])], ["", __("Bought in three years"), esc(fmtM(x.cur))]]))}">
				<div class="ceo-list-name"><span>${esc(x.c[1])}</span><small>${[...x.cos].map((i) => esc(d.companies[i].abbr)).join(", ")} · ${esc(d.segments[x.c[2]])} · ${__("last")} ${esc(x.c[4])}</small></div>
				<div class="ceo-badge ${x.gap > 90 ? "serious" : "warning"}"><span aria-hidden="true">${x.gap > 90 ? "!!" : "!"}</span><strong>${inr(x.gap)}</strong>&nbsp;${__("days")}</div>
				<button class="ceo-drill" data-act="drill" data-kind="cust" data-val="${x.i}" aria-label="${esc(__("Details"))}">›</button>
			</li>`).join("")}</ol><div class="ceo-foot">${__("{0} customers in all", [inr(list.length)])}</div>`;
		}

		// Company-months whose Rs/kg is far from the typical company that month (last
		// 24 months). The baseline is the MEDIAN of the companies' rates, not the
		// volume-weighted group rate: one large wrong month (NGN Chaitra 82/83,
		// 2,039 MT at Rs 36/kg on demo-nggroup) would otherwise drag the group rate
		// down and flag every other company as "too high".
		function alertList() {
			const d = D(), from = PM() - 23;
			const gas = new Map(), kg = new Map();
			for (const r of d.sales) {
				if (!r[R_GAS] || !okInternal(r[R_CU])) continue;
				const m = r[R_SLOT] >> 1;
				if (m < from || m > PM()) continue;   // folded-in week slots are not months
				const k = r[R_CO] * 100 + m;
				gas.set(k, (gas.get(k) || 0) + r[R_GAS]); kg.set(k, (kg.get(k) || 0) + r[R_KG]);
			}
			const rates = new Map();   // month -> [rates of companies with enough volume]
			for (const [k, g] of gas) { const q = kg.get(k); if (q >= PRICE_ALERT_MIN_KG) { const m = k % 100; (rates.get(m) || rates.set(m, []).get(m)).push(g / q); } }
			const median = (a) => { const b = [...a].sort((x, y) => x - y), h = b.length >> 1; return b.length % 2 ? b[h] : (b[h - 1] + b[h]) / 2; };
			const alerts = [];
			for (const [k, g] of gas) {
				const co = Math.floor(k / 100), m = k % 100, q = kg.get(k), peers = rates.get(m) || [];
				if (!passCo(co)) continue;
				if (q < PRICE_ALERT_MIN_KG || peers.length < 3) continue;
				const rate = g / q, grp = median(peers), dev = (rate - grp) / grp;
				if (Math.abs(dev) >= PRICE_ALERT) alerts.push({ co, m, rate, grp, dev, q });
			}
			return alerts.sort((a, b) => Math.abs(b.dev) - Math.abs(a.dev));
		}
		function renderAlerts() {
			const d = D(), el = slot("alerts"), alerts = alertList();
			sub("alerts", __("A company's Rs/kg more than {0}% away from the typical company that month (median, last 24 months).", [PRICE_ALERT * 100]));
			if (!alerts.length) { el.innerHTML = `<div class="ceo-empty">${__("No company priced far from the group.")}</div>`; return; }
			el.innerHTML = `<ol class="ceo-list">${alerts.slice(0, 4).map((a) => `<li class="ceo-click ${dimState("co", a.co)}" data-dim="co" data-val="${a.co}" tabindex="0" data-tip="${tip(tipRows(`${d.companies[a.co].name}, ${monthLabel(a.m)}`, [["", __("Company Rs/kg"), `Rs ${inr(a.rate, 2)}`], ["", __("Typical company Rs/kg"), `Rs ${inr(a.grp, 2)}`], ["", __("Volume that month"), esc(mt(a.q))]]))}">
				<div class="ceo-list-name"><span>${esc(d.companies[a.co].abbr)} · ${esc(monthLabel(a.m))}</span><small>Rs ${inr(a.rate, 2)}/kg ${__("vs typical")} Rs ${inr(a.grp, 2)} · ${esc(mt(a.q))}</small></div>
				<div class="ceo-badge ${Math.abs(a.dev) > 0.25 ? "serious" : "warning"}"><span aria-hidden="true">${a.dev < 0 ? "▼" : "▲"}</span><strong>${pctTxt(a.dev)}</strong></div>
			</li>`).join("")}</ol>`;
		}


		// -------------------------------------------------------- money
		// Ledger balances (positions, so the period switch does not apply) and the
		// gas margin (which does). Company selection applies everywhere; segment and
		// customer only where the ledger can be split that way (customer balances).
		function renderMoney(W) {
			const label = slot("money-label");
			if (!label) return;
			const cards = ["cash", ...(SHOW_MARGIN ? ["margin"] : []), "recv", "pay"];
			if (!st.money) {
				label.textContent = __("Reading the ledger…");
				cards.forEach((n) => (slot(n).innerHTML = `<div class="ceo-skel line"></div><div class="ceo-skel line"></div><div class="ceo-skel line short"></div>`));
				return;
			}
			if (st.money.failed || !st.mn) {
				label.textContent = __("The ledger could not be read.");
				cards.forEach((n) => (slot(n).innerHTML = `<div class="ceo-empty">${__("Not available.")}</div>`));
				return;
			}
			const d = D(), ser = moneySeries(), lyLabel = st.money.through_ly_label;
			label.innerHTML = esc(__("On {0}", [d.through_label]));
			if (slot("buy-label")) slot("buy-label").innerHTML = label.innerHTML;
			// Month ends the balance charts show: the same months as the rest of the
			// page (the chosen fiscal year so far, the picked years, or the last 12
			// months), not a fixed 24 months. Until 2026-11-11 they always showed the
			// last 24 month-ends, a leftover from before the charts followed the period.
			const pmM = PM(), fy0 = FY0();
			const ms = multiYear()
				? st.fys.flatMap((f) => { const y = d.years.indexOf(f); return y < 0 ? [] : Array.from({ length: 12 }, (_, i) => y * 12 + i); }).filter((mo) => mo <= pmM)
				: st.period === "r12" ? Array.from({ length: 12 }, (_, i) => pmM - 11 + i).filter((mo) => mo >= 0)
				: Array.from({ length: pmM - fy0 + 1 }, (_, i) => fy0 + i);
			// A balance chart starts from the opening balance (the CEO's call,
			// 2026-11-11): the month end before the first month shown, i.e. what the
			// period started with. pts = [opening month end, ...month ends]; there is
			// no opening point when the timeline has no month before the first one.
			const hasOpen = ms.length > 0 && ms[0] >= 1, pts = hasOpen ? [ms[0] - 1, ...ms] : ms, isOpen = (i) => hasOpen && i === 0;
			const ptLabel = (i) => (isOpen(i) ? `${__("Opening")} · 1 ${monthLabel(ms[0])}` : `${__("End of")} ${monthLabel(pts[i])}${pts[i] === pmM && !pastYear() ? ` (${d.through_label})` : ""}`);
			const balAxis = {
				n: pts.length, val: (i) => i, xTitle: __("Opening, then each month end (Nepali calendar)"),
				label: (i) => (isOpen(i) ? __("Opening") : monthName(pts[i]).slice(0, 3)),
				group: (i) => (!isOpen(i) && (i === (hasOpen ? 1 : 0) || pts[i] % 12 === 0) ? yearOf(pts[i]) : null),
				shade: () => false, dim: () => "", last: (i) => pts[i] === pmM, band: () => "", aria: ptLabel,
			};
			const notSplit = st.sel.seg.size || st.sel.cust.size ? ` ${__("Not split by segment or customer.")}` : "";
			const coName = (co) => `<strong>${esc(d.companies[co].abbr)}</strong>`;
			const balChart = (name, vals, what, height = 220, host = null) => {
				const el = host || slot(name), cur = pts.map((mo) => vals[mo]), ly = pts.map((mo) => (mo >= 12 ? vals[mo - 12] : null));
				// Opening, where it stands now (closing, for a past year) and the movement between them.
				const open = hasOpen ? cur[0] : null, now = cur[cur.length - 1];
				const sum = open != null && now != null ? `<div class="ceo-balsum"><span>${__("Opening")} <b>${esc(rs(open))}</b></span><span>${pastYear() ? __("Closing") : __("Now")} <b>${esc(rs(now))}</b></span><span>${__("Change")} <b class="${now - open < 0 ? "ceo-neg" : ""}">${now - open >= 0 ? "+" : "−"}${esc(rs(Math.abs(now - open)))}</b></span></div>` : "";
				if (st.tables.has(name) && !SHOW_COMPARISON) return sum + table([__("Month end"), what], cur.map((v, i) => [esc(ptLabel(i)), v == null ? "—" : esc(rs(v))]).reverse());
				if (st.tables.has(name)) return sum + table([__("Month end"), what, __("A year earlier"), __("Change")], cur.map((v, i) => [esc(ptLabel(i)), v == null ? "—" : esc(rs(v)), ly[i] == null ? "—" : esc(rs(ly[i])), v != null && ly[i] ? delta(v, ly[i], { upGood: null }) : ""]).reverse());
				const shape = shapeOf(name);
				return sum + legend([["cur", __("{0}, month end", [what]), shape === "bar" ? "rect" : "line"], ["prev", __("Same month end a year earlier")]]) + timeAxis(el, {
					axis: balAxis,
					series: [{ type: "line", vals: ly, cls: "prev", dots: false }, { type: shape, vals: cur, cls: "cur" }],
					kind: "amt", height,
					tipFor: (i) => tipRows(ptLabel(i), [["cur", what, cur[i] == null ? "—" : esc(rs(cur[i]))], ["prev", __("A year earlier"), ly[i] == null ? "—" : esc(rs(ly[i]))]]),
				});
			};

			// Cash and bank
			const per = new Map();
			for (const x of st.mn.cash) {
				if (!passCo(x.co)) continue;
				const y = per.get(x.co) || per.set(x.co, { cash: 0, bank: 0, loan: 0, ly: 0 }).get(x.co);
				if (x.kind === 0) y.cash += x.now; else if (x.kind === 1) y.bank += x.now; else y.loan += x.now;
				if (x.kind < 2) y.ly += x.ly;
			}
			const money = (v) => `<span class="${v < 0 ? "ceo-neg" : ""}">${esc(rs(v))}</span>`;
			const coRows = [...per.entries()].filter(([, y]) => y.cash || y.bank || y.loan).sort((a, b) => b[1].cash + b[1].bank - (a[1].cash + a[1].bank));
			sub("cash", `${__("Blue line = cash in hand plus bank balances at the end of each month, in rupees; grey line = a year earlier. Bank loans are shown apart in the table.")}${notSplit}`);
			slot("cash").innerHTML = balChart("cash", ser.cash, __("Cash and bank")) + (coRows.length ? `<div class="ceo-tablewrap"><table class="ceo-table compact ceo-money">
				<thead><tr><th>${__("Company")}</th><th class="num">${__("Cash in hand")}</th><th class="num">${__("Bank")}</th><th class="num">${__("Total")}</th>${SHOW_COMPARISON ? `<th class="num">${__("vs {0}", [esc(lyLabel)])}</th>` : ""}<th class="num">${__("Bank loans")}</th></tr></thead>
				<tbody>${coRows.map(([co, y]) => `<tr class="ceo-click ${dimState("co", co)}" data-dim="co" data-val="${co}" tabindex="0"><td>${coName(co)}</td><td class="num">${money(y.cash)}</td><td class="num">${money(y.bank)}</td><td class="num"><b>${money(y.cash + y.bank)}</b></td>${SHOW_COMPARISON ? `<td class="num">${delta(y.cash + y.bank, y.ly)}</td>` : ""}<td class="num">${esc(rs(y.loan))}</td></tr>`).join("")}</tbody></table></div>` : "");

			// Gas margin (off with SHOW_MARGIN)
			if (SHOW_MARGIN) {
			const vw = st.view, mm = marginBuckets(vw);
			sub("margin", __("Blue line = average price we sold LP Gas at, per kg; green line = price we paid per kg on gas purchase bills, in each {0}. The gap between the lines is the margin. Blank where there are no gas purchase bills.", [vw.noun]));
			let mHtml;
			const sell = mm && mm.sell, buy = mm && mm.buy, mar = mm && mm.m, share = mm && mm.share;
			if (!mm) {
				mHtml = chartLoading();
			} else if (st.tables.has("margin")) {
				mHtml = table([__("Period"), __("Sale price"), __("Purchase price"), __("Margin"), __("Volume priced")], sell.map((v, i) => [esc(vw.long(i)), v == null ? "—" : `Rs ${inr(v, 2)}`, buy[i] == null ? "—" : `Rs ${inr(buy[i], 2)}`, mar[i] == null ? "—" : `<b>Rs ${inr(mar[i], 2)}</b>`, share[i] ? `${inr(share[i] * 100, 0)}%` : "—"]).filter((r, i) => sell[i] != null));
			} else if (!sell.some((v) => v != null)) {
				mHtml = `<div class="ceo-empty">${__("No gas purchase bills for this period and selection.")}</div>`;
			} else {
				mHtml = legend([["cur", __("Selling price per kg")], ["coll", __("Purchase price per kg")]]) + timeAxis(slot("margin"), {
					axis: viewAxis(vw),
					series: [{ type: "line", vals: buy, cls: "coll" }, { type: "line", vals: sell, cls: "cur" }],
					kind: "rate", height: 220,
					tipFor: (i) => tipRows(vw.long(i), [["cur", __("Sale price"), sell[i] == null ? "—" : `Rs ${inr(sell[i], 2)}`], ["coll", __("Purchase price"), buy[i] == null ? "—" : `Rs ${inr(buy[i], 2)}`], ["", __("Margin"), mar[i] == null ? "—" : `<b>Rs ${inr(mar[i], 2)}</b>`]], share[i] && share[i] < 0.995 ? `<div class="ceo-tip-note">${__("{0}% of the volume here has a purchase price", [inr(share[i] * 100, 0)])}</div>` : ""),
				});
			}
			const mRows = shownCompanies().map((c) => ({ c, g: marginTotals(W, (r) => r[R_CO] === c.i && pass(r, "co")) })).filter((x) => x.g.cur.m != null).sort((a, b) => b.g.cur.cov - a.g.cur.cov);
			slot("margin").innerHTML = mHtml + (mRows.length ? `<div class="ceo-tablewrap"><table class="ceo-table compact ceo-money">
				<thead><tr><th>${__("Company")}</th><th class="num">${__("Sold at")}</th><th class="num">${__("Bought at")}</th><th class="num">${__("Margin")}</th>${SHOW_COMPARISON ? `<th class="num">${__("Change")}</th>` : ""}<th class="num">${__("Volume priced")}</th></tr></thead>
				<tbody>${mRows.map(({ c, g }) => `<tr class="ceo-click ${dimState("co", c.i)}" data-dim="co" data-val="${c.i}" tabindex="0"><td>${coName(c.i)}</td><td class="num">Rs ${inr(g.cur.sell, 2)}</td><td class="num">Rs ${inr(g.cur.buy, 2)}</td><td class="num"><b>Rs ${inr(g.cur.m, 2)}</b></td>${SHOW_COMPARISON ? `<td class="num">${g.prev.m != null ? delta(g.cur.m, g.prev.m) : "—"}</td>` : ""}<td class="num"><span class="${g.cur.share < MARGIN_PARTIAL ? "ceo-warnink" : ""}">${inr(g.cur.share * 100, 0)}%</span></td></tr>`).join("")}</tbody></table></div>`
				: `<div class="ceo-foot">${__("No company has gas purchase bills in this period.")}</div>`);

			}

			// Customers owe us
			sub("recv", __("Blue line = total that customers owed us at the end of each month (ledger balances, advances not subtracted), in rupees; grey line = a year earlier. Credit and dues below is credit control's view of customers with limits."));
			const rc = new Map();
			for (const x of st.mn.recv) {
				if (!passRecv(x)) continue;
				const y = rc.get(x.co) || rc.set(x.co, { now: 0, ly: 0, adv: 0, n: 0 }).get(x.co);
				if (x.now > 0) { y.now += x.now; y.n++; } else y.adv -= x.now;
				if (x.ly > 0) y.ly += x.ly;
			}
			const rItems = [...rc.entries()].map(([co, y]) => ({ val: co, label: d.companies[co].abbr, title: d.companies[co].name, cur: y.now, prev: y.ly, tip: tipRows(d.companies[co].name, [["", __("Owed now"), esc(rs(y.now))], ["", __("A year earlier"), esc(rs(y.ly))], ["", __("Advances held"), esc(rs(y.adv))], ["", __("Customers owing"), inr(y.n)]]) })).filter((x) => x.cur || x.prev).sort((a, b) => b.cur - a.cur);
			const recvChart = st.sel.cust.size ? `<div class="ceo-empty small">${__("Month-end trend is kept per company and segment, not per customer.")}</div>` : balChart("recv", ser.owed, __("Customers owe us"));
			slot("recv").innerHTML = recvChart + (rItems.length ? `<h4 class="ceo-subh">${__("By company")}</h4>` + barList(capped(rItems, "recv"), { dim: "co", fill: "var(--ceo-cur)", fmt: rs, upGood: false }) + showAll(rItems, "recv") : "");

			// We owe suppliers
			const sups = st.mn.pay.filter((x) => passPay(x) && x.now > 0).sort((a, b) => b.now - a.now);
			const totalPay = sups.reduce((a, x) => a + x.now, 0);
			sub("pay", `${__("Blue line = total we owed suppliers at the end of each month (ledger balances), in rupees; grey line = a year earlier. Inter-company suppliers follow the inter-company switch.")}${notSplit}`);
			const maxS = sups.length ? sups[0].now : 1;
			// Largest balances and the month-end trend side by side (the CEO's call,
			// 2026-11-11); they stack on narrow screens (CSS .ceo-split).
			slot("pay").innerHTML = `<div class="ceo-split"><div>${(sups.length ? `<h4 class="ceo-subh">${__("Largest balances")}</h4><div class="ceo-bars named wide">${sups.slice(0, 8).map((x) => `<div class="ceo-barrow nochg" data-tip="${tip(tipRows(x.name, [["", __("We owe"), esc(rs(x.now))], ["", __("Share"), totalPay ? `${inr((x.now / totalPay) * 100, 1)}%` : "—"]]))}">
				<div class="ceo-barlabel"><span title="${esc(x.name)}">${esc(x.name)}<small>${esc(d.companies[x.co].abbr)}${x.bill ? ` · <button class="ceo-inl" data-act="open-doc" data-doctype="Purchase Invoice" data-val="${esc(x.bill[0])}">${esc(x.bill[0])}</button> ${esc(rs(x.bill[2]))}` : ""}</small></span></div>
				<div class="ceo-bartrack"><div class="ceo-barfill" style="width:${(x.now / maxS) * 100}%;background:var(--zone-key, var(--ceo-cur))"></div></div>
				<div class="ceo-barval">${esc(rs(x.now))}</div></div>`).join("")}</div><div class="ceo-foot">${__("{0} suppliers with a balance", [inr(sups.length)])}</div>` : `<div class="ceo-empty">${__("Nothing owed to suppliers.")}</div>`)}</div><div class="ceo-split-chart"><h4 class="ceo-subh">${__("Month end")}</h4><div data-chart="pay"></div></div></div>`;
			const payHost = slot("pay").querySelector("[data-chart='pay']");
			payHost.innerHTML = balChart("pay", ser.pay, __("We owe suppliers"), 340, payHost);   // about as tall as the eight-row list beside it

		}

		// -------------------------------------------------------- buying
		// Purchases (buying.get_buying): Purchase Invoice rows per day x company x
		// supplier x category, with the sales table's slot, and supplier payments.
		// Same period and company / inter-company filters as sales; segment and
		// customer do not apply (purchases have neither).
		function loadBuying(force) {
			const fy = st.fy;
			st.buying = st.by = null;
			frappe.call({
				method: "avinashgroup_app.ceo_dashboard.buying.get_buying",
				args: { fiscal_year: fy, force: force ? 1 : 0, years_back: yearsBack() },
				callback: (r) => { if (st.fy !== fy) return; st.buying = r.message || { failed: true }; prepareBuying(); st.data && render(false); },
				error: () => { if (st.fy !== fy) return; st.buying = { failed: true }; st.data && render(false); },
			});
		}
		function prepareBuying() {
			const b = st.buying;
			if (!b || b.failed || !st.data || b.fiscal_year !== st.data.fiscal_year) return;
			st.by = { rows: b.rows, pay: b.pay, sup: b.suppliers, cats: b.categories };
		}
		const BR_SLOT = 0, BR_DATE = 1, BR_CO = 2, BR_SUP = 3, BR_CAT = 4, BR_KG = 5, BR_AMT = 6, BR_BILLS = 7;
		const passBuy = (co, sup) => passCo(co) && (st.internal || !st.by.sup[sup][2]);
		// [in the period, in the comparison] for a buying row: a picked week compares
		// dates (its slots are folded-in sales slots), everything else compares slots.
		function buyIn(W, slot, iso) {
			if (inWin(W, wkS())) {
				const w = st.weekInfo;
				return w ? [iso >= w.from && iso <= w.to, iso >= w.prev_from && iso <= w.prev_to] : [false, false];
			}
			return [inWin(W, slot), inCmp(W, slot)];
		}
		function buyTotals(W) {
			const t = { amt: 0, kg: 0, gasAmt: 0, paid: 0, bills: 0, sups: new Set(), byCo: new Map(), byCat: st.by.cats.map(() => ({ amt: 0, kg: 0 })), bySup: new Map() };
			const billKey = new Map();   // a bill with lines in two categories sits in two rows: count it once
			for (const r of st.by.rows) {
				if (!buyIn(W, r[BR_SLOT], r[BR_DATE])[0] || !passBuy(r[BR_CO], r[BR_SUP])) continue;
				const a = r[BR_AMT];
				t.amt += a;
				t.byCo.set(r[BR_CO], (t.byCo.get(r[BR_CO]) || 0) + a);
				const c = t.byCat[r[BR_CAT]];
				c.amt += a; c.kg += r[BR_KG];
				if (r[BR_CAT] === 0) { t.kg += r[BR_KG]; t.gasAmt += a; }
				const s = t.bySup.get(r[BR_SUP]) || t.bySup.set(r[BR_SUP], { amt: 0, bills: 0, last: "", cos: new Set() }).get(r[BR_SUP]);
				s.amt += a; s.cos.add(r[BR_CO]);
				if (r[BR_DATE] > s.last) s.last = r[BR_DATE];
				t.sups.add(r[BR_SUP]);
				const k = `${r[BR_DATE]}|${r[BR_CO]}|${r[BR_SUP]}`;
				billKey.set(k, Math.max(billKey.get(k) || 0, r[BR_BILLS]));
			}
			for (const [k, n] of billKey) { t.bills += n; t.bySup.get(+k.split("|")[2]).bills += n; }
			for (const r of st.by.pay) if (buyIn(W, r[0], r[1])[0] && passBuy(r[2], r[3])) t.paid += r[4];
			return t;
		}
		// Purchases in the chart view's buckets (this period only, like the sales chart).
		function buyBuckets(v) {
			const cur = new Array(v.n).fill(0);
			if (v.grain === "month") {
				const idx = new Map(Array.from({ length: v.n }, (_, i) => [v.month(i), i]));
				for (const r of st.by.rows) { if (!passBuy(r[BR_CO], r[BR_SUP])) continue; const i = idx.get(r[BR_SLOT] >> 1); if (i != null) cur[i] += r[BR_AMT]; }
			} else {
				for (const r of st.by.rows) {
					if (r[BR_DATE] < v.from || !passBuy(r[BR_CO], r[BR_SUP])) continue;
					const i = v.pos(r[BR_DATE], false);
					if (i >= 0 && i < v.n) cur[i] += r[BR_AMT];
				}
			}
			return cur.map((x, i) => (v.inCur(i) ? x : null));
		}
		// Top tile: purchases in the period, with a 24-month sparkline.
		function buyTile(W) {
			const label = __("Purchases");
			if (!st.buying) return { label, loading: true, zone: "buy" };
			if (st.buying.failed || !st.by) return { label, value: "—", d: "", foot: esc(__("Purchases could not be read.")), zone: "buy" };
			const t = buyTotals(W), m = new Float64Array(NM());
			for (const r of st.by.rows) if (passBuy(r[BR_CO], r[BR_SUP])) m[r[BR_SLOT] >> 1] += r[BR_AMT];
			return { label, value: rs(t.amt), d: "", sub: "", foot: esc(`${mt(t.kg)} ${__("LP Gas")} · ${inr(t.bills)} ${__("bills")}`), s: flow(last24(m)), zone: "buy", goto: "buying" };
		}
		function renderBuying(W) {
			const cards = ["buytrend", "buyco", "buycat", "buysup"];
			if (!slot("buytrend")) return;
			if (!st.buying || (!st.by && !st.buying.failed)) {
				slot("buy-kpis").innerHTML = "";
				cards.forEach((n) => (slot(n).innerHTML = chartLoading()));
				return;
			}
			if (st.buying.failed) { cards.forEach((n) => (slot(n).innerHTML = `<div class="ceo-empty">${__("Purchases could not be read.")}</div>`)); return; }
			const d = D(), v = st.view, t = buyTotals(W);
			slot("buy-label").textContent = periodLabel(W);

			// Small figures
			const tile = (lbl, val, foot) => `<div class="ceo-kpi"><div class="ceo-kpi-label">${esc(lbl)}</div><div class="ceo-kpi-value">${val}</div><div class="ceo-kpi-foot">${foot}</div></div>`;
			slot("buy-kpis").innerHTML =
				tile(__("Purchases"), esc(rs(t.amt)), esc(__("net, before VAT"))) +
				tile(__("LP Gas bought"), esc(mt(t.kg)), t.kg ? esc(`${__("average")} Rs ${inr(t.gasAmt / t.kg, 2)}/kg · ${rs(t.gasAmt)}`) : "") +
				tile(__("Paid to suppliers"), esc(rs(t.paid)), esc(__("Payment Entries"))) +
				tile(__("Suppliers"), inr(t.sups.size), esc(`${inr(t.bills)} ${__("bills")}`));

			// Purchases over time (follows the period like the sales chart)
			const el = slot("buytrend"), vals = buyBuckets(v);
			setTitle("buytrend", `${__("Purchases")} · ${v.title}`);
			el.innerHTML = st.tables.has("buytrend")
				? table([__("Period"), __("Purchases")], vals.map((x, i) => [esc(v.long(i)), x == null ? "—" : esc(rs(x))]).filter((r, i) => vals[i] != null))
				: timeAxis(el, {
					axis: viewAxis(v),
					series: [{ type: "bar", vals, cls: "buyc" }],
					kind: "amt", yTitle: __("Purchases, rupees (L = lakh, Cr = crore)"),
					tipFor: (i) => tipRows(v.long(i), [["buyc rect", __("Purchases"), vals[i] == null ? "—" : esc(rs(vals[i]))]]),
				});

			// By company
			const coItems = shownCompanies().map((c) => ({ val: c.i, label: c.abbr, title: c.name, cur: t.byCo.get(c.i) || 0, prev: 0, tip: tipRows(c.name, [["", __("Purchases"), esc(rs(t.byCo.get(c.i) || 0))], ["", __("Share"), t.amt ? `${inr(((t.byCo.get(c.i) || 0) / t.amt) * 100, 1)}%` : "—"]]) })).filter((x) => x.cur).sort((a, b) => b.cur - a.cur);
			slot("buyco").innerHTML = coItems.length ? barList(capped(coItems, "buyco"), { dim: "co", fill: "var(--zone-key, var(--ceo-cur))", fmt: rs }) + showAll(coItems, "buyco") : `<div class="ceo-empty">${__("No purchases in this period.")}</div>`;

			// What we buy (fixed category order; bars on one scale)
			const maxC = Math.max(1, ...t.byCat.map((c) => c.amt));
			const catRow = (name, c, extra) => `<div class="ceo-barrow nochg" data-tip="${tip(tipRows(name, [["", __("Purchases"), esc(rs(c.amt))], ["", __("Share"), t.amt ? `${inr((c.amt / t.amt) * 100, 1)}%` : "—"], ...(extra ? [["", __("LP Gas"), esc(extra)]] : [])]))}">
				<div class="ceo-barlabel"><span>${esc(name)}${extra ? `<small>${esc(extra)}</small>` : ""}</span></div>
				<div class="ceo-bartrack"><div class="ceo-barfill" style="width:${(Math.max(0, c.amt) / maxC) * 100}%;background:var(--zone-key, var(--ceo-cur))"></div></div>
				<div class="ceo-barval">${esc(rs(c.amt))}<small class="ceo-block ceo-muted">${t.amt ? `${inr((c.amt / t.amt) * 100, c.amt / t.amt < 0.1 ? 1 : 0)}%` : ""}</small></div></div>`;
			const cats = st.by.cats.map((name, i) => ({ name: __(name), c: t.byCat[i], i })).filter((x) => x.c.amt);
			slot("buycat").innerHTML = cats.length ? `<div class="ceo-bars named">${cats.map((x) => catRow(x.name, x.c, x.i === 0 && x.c.kg ? `${mt(x.c.kg)} · Rs ${inr(x.c.amt / x.c.kg, 2)}/kg` : "")).join("")}</div>` : `<div class="ceo-empty">${__("No purchases in this period.")}</div>`;

			// Top suppliers (click: their Purchase Invoices in this period)
			const [wa, wb] = windowDates();
			const sups = [...t.bySup.entries()].sort((a, b) => b[1].amt - a[1].amt);
			const maxS = sups.length ? Math.max(1, sups[0][1].amt) : 1;
			slot("buysup").innerHTML = sups.length ? `<div class="ceo-bars named wide">${sups.slice(0, 8).map(([i, s]) => {
				const sp = st.by.sup[i], filters = { supplier: sp[0], docstatus: 1, posting_date: ["Between", [wa, wb]] };
				return `<div class="ceo-barrow nochg ceo-click" data-act="open-list" data-doctype="Purchase Invoice" data-filters="${esc(JSON.stringify(filters))}" tabindex="0" data-tip="${tip(tipRows(sp[1], [["", __("Purchases"), esc(rs(s.amt))], ["", __("Share"), t.amt ? `${inr((s.amt / t.amt) * 100, 1)}%` : "—"], ["", __("Bills"), inr(s.bills)], ["", __("Last bill"), esc(bsShort(s.last))]]))}">
					<div class="ceo-barlabel"><span title="${esc(sp[1])}">${esc(sp[1])}<small>${[...s.cos].map((c) => esc(d.companies[c].abbr)).join(", ")}${sp[2] ? ` · ${esc(__("group company"))}` : ""} · ${inr(s.bills)} ${esc(__("bills"))}</small></span></div>
					<div class="ceo-bartrack"><div class="ceo-barfill" style="width:${(s.amt / maxS) * 100}%;background:var(--zone-key, var(--ceo-cur))"></div></div>
					<div class="ceo-barval">${esc(rs(s.amt))}<small class="ceo-block ceo-muted">${t.amt ? `${inr((s.amt / t.amt) * 100, s.amt / t.amt < 0.1 ? 1 : 0)}%` : ""}</small></div></div>`;
			}).join("")}</div><div class="ceo-foot">${__("{0} suppliers · click one to open their bills", [inr(sups.length)])}</div>` : `<div class="ceo-empty">${__("No purchases in this period.")}</div>`;
		}

		// -------------------------------------------------------- credit and dues
		function renderCredit() {
			const zone = root.querySelector("[data-zone='credit']");
			if (zone) zone.style.display = pastYear() ? "none" : "";
			if (pastYear()) return;
			const c = st.credit, label = slot("credit-label");
			if (!label) return;
			const grid = slot("credit-grid"), kpis = slot("credit-kpis");
			if (!c || (!c.missing && !st.cr)) { label.textContent = __("Loading credit positions…"); return; }
			if (c.missing) {
				label.textContent = "";
				kpis.innerHTML = `<div class="ceo-card span-12"><div class="ceo-empty">${__("Credit positions have not been worked out yet. They are rebuilt every 4 hours.")} ${c.can_refresh ? `<button class="ceo-inl" data-act="cr-refresh">${__("Work them out now")}</button>` : ""}</div></div>`;
				grid.hidden = true;
				return;
			}
			grid.hidden = false;
			label.innerHTML = `${esc(__("On {0}", [c.as_of_label]))}${c.can_refresh ? ` <button class="ceo-ghost" data-act="cr-refresh" title="${esc(__("Work out every customer's position again (several minutes)"))}">${__("Refresh")}</button>` : ""}`;
			const rows = st.cr.filter((x) => passCredit(x));
			const hold = rows.filter((x) => x.blocked), byReason = [0, 0, 0, 0];
			hold.forEach((x) => byReason[x.blocked]++);
			const owed = rows.reduce((a, x) => a + Math.max(0, x.owed), 0);
			const adv = rows.reduce((a, x) => a + x.adv, 0);
			const near = rows.filter((x) => !x.blocked && limitUse(x) != null && limitUse(x) >= NEAR_LIMIT);
			const holdOwed = hold.reduce((a, x) => a + Math.max(0, x.owed), 0);
			const old30 = rows.filter((x) => x.owed > 0 && x.days > 30).reduce((a, x) => a + x.owed, 0);
			const tile = (lbl, val, sub, cls = "") => `<div class="ceo-kpi ${cls}"><div class="ceo-kpi-label">${esc(lbl)}</div><div class="ceo-kpi-value">${val}</div><div class="ceo-kpi-foot">${sub}</div></div>`;
			kpis.innerHTML =
				tile(__("Customers on hold"), `<span class="ceo-status critical" aria-hidden="true">●</span>${inr(hold.length)}`, `${[3, 2, 1].filter((k) => byReason[k]).map((k) => `${inr(byReason[k])} ${esc(__(BLOCK_SHORT[k]).toLowerCase())}`).join(" · ") || __("nobody is blocked")}<br>${__("owing")} ${esc(rs(holdOwed))}`) +
				tile(__("Owed after advances"), esc(rs(owed)), `${esc(rs(old30))} ${__("over 30 days")}`) +
				tile(__("Advance held"), esc(rs(adv)), "") +
				tile(__("Near the limit"), inr(near.length), `${__("{0}%+ of limit used", [NEAR_LIMIT * 100])}`);

			// Ageing
			const ageLabels = [...AGE_BUCKETS.map((b) => __(b[2])), __("No bill (journal debit)")];
			const ages = ageLabels.map(() => ({ owed: 0, n: 0 }));
			rows.forEach((x) => { const b = ageBucket(x); if (b >= 0) { ages[b].owed += x.owed; ages[b].n++; } });
			const maxA = Math.max(1, ...ages.map((a) => a.owed));
			sub("crage", __("Owed per customer, grouped by how old their oldest unpaid bill is. Click a row to list them."));
			slot("crage").innerHTML = `<div class="ceo-bars">${ages.map((a, i) => (a.n || i < AGE_BUCKETS.length ? `<div class="ceo-barrow ${st.crBucket == null ? "" : st.crBucket === i ? "is-sel" : "is-dim"}" data-act="cr-bucket" data-val="${i}" tabindex="0" data-tip="${tip(tipRows(ageLabels[i], [["", __("Owed"), esc(rs(a.owed))], ["", __("Customers"), inr(a.n)]], i === AGE_BUCKETS.length ? `<div class="ceo-tip-note">${__("Money owed through Journal Entries with no Sales Invoice behind it; it has no bill date, so it cannot age.")}</div>` : ""))}">
				<div class="ceo-barlabel"><span>${esc(ageLabels[i])}<small>${inr(a.n)} ${__("customers")}</small></span></div>
				<div class="ceo-bartrack"><div class="ceo-barfill" style="width:${(a.owed / maxA) * 100}%;background:${i < AGE_BUCKETS.length ? `var(--ceo-age${i})` : "var(--ceo-neutral)"}"></div></div>
				<div class="ceo-barval">${esc(rs(a.owed))}</div><div></div></div>` : "")).join("")}</div>`;

			// By company
			const per = new Map();
			st.cr.filter((x) => passCredit(x)).forEach((x) => { const k = x.co; const y = per.get(k) || per.set(k, { owed: 0, adv: 0, hold: 0, n: 0 }).get(k); y.owed += Math.max(0, x.owed); y.adv += x.adv; y.n++; if (x.blocked) y.hold++; });
			const cos = [...per.entries()].filter(([k]) => k >= 0).sort((a, b) => b[1].owed - a[1].owed);
			const maxC = Math.max(1, ...cos.map(([, y]) => y.owed));
			sub("crco", __("Owed after advances, and how many customers are on hold. Hover for the advance held."));
			const coItems = cos.map(([k, y]) => ({ val: k, k, y }));
			slot("crco").innerHTML = cos.length ? `<div class="ceo-bars">${capped(coItems, "crco").map(({ k, y }) => `<div class="ceo-barrow ${dimState("co", k)}" data-dim="co" data-val="${k}" tabindex="0" data-tip="${tip(tipRows(D().companies[k].name, [["", __("Owed"), esc(rs(y.owed))], ["", __("Advance held"), esc(rs(y.adv))], ["", __("On hold"), `${inr(y.hold)} ${__("of")} ${inr(y.n)}`]]))}">
				<div class="ceo-barlabel"><span title="${esc(D().companies[k].name)}">${esc(D().companies[k].abbr)}</span></div>
				<div class="ceo-bartrack"><div class="ceo-barfill" style="width:${(y.owed / maxC) * 100}%;background:var(--ceo-cur)"></div></div>
				<div class="ceo-barval">${esc(rs(y.owed))}</div>
				<div class="ceo-barchg">${y.hold ? `<span class="ceo-badge serious" title="${esc(__("On hold"))}"><span aria-hidden="true">!!</span><strong>${inr(y.hold)}</strong></span>` : `<span class="ceo-delta flat">0</span>`}</div></div>`).join("")}</div>${showAll(coItems, "crco")}` : `<div class="ceo-empty">${__("No credit limits here.")}</div>`;

			// Limit use
			const bands = [[__("Paid ahead"), (u) => u != null && u < 0], [__("Under 50%"), (u) => u != null && u >= 0 && u < 0.5], [__("50–80%"), (u) => u != null && u >= 0.5 && u < NEAR_LIMIT], [__("80–100%"), (u) => u != null && u >= NEAR_LIMIT && u <= 1], [__("Over the limit"), (u) => u != null && u > 1]];
			const withLim = rows.filter((x) => x.lim > CASH_ONLY_MAX);
			const cash = rows.filter(cashOnly);
			const bandN = bands.map(([, f]) => withLim.filter((x) => f(limitUse(x))));
			const maxB = Math.max(1, ...bandN.map((b) => b.length));
			sub("cruse", __("Customers with a real credit line, by how much of it they use (owed minus advance, ÷ limit)."));
			slot("cruse").innerHTML = `<div class="ceo-bars">${bands.map(([l], i) => `<div class="ceo-barrow" data-tip="${tip(tipRows(l, [["", __("Customers"), inr(bandN[i].length)], ["", __("Owed"), esc(rs(bandN[i].reduce((a, x) => a + Math.max(0, x.owed), 0)))]]))}">
				<div class="ceo-barlabel"><span>${esc(l)}</span></div>
				<div class="ceo-bartrack"><div class="ceo-barfill" style="width:${(bandN[i].length / maxB) * 100}%;background:var(--ceo-use${i})"></div></div>
				<div class="ceo-barval">${inr(bandN[i].length)}</div><div></div></div>`).join("")}</div>
`;

			renderCreditList(rows);
		}

		function renderCreditList(rows) {
			const d = D(), el = slot("crlist"), tools = slot("crtools");
			const usual = usualMonthly();
			const tabs = {
				hold: [__("On hold"), (x) => x.blocked > 0, (a, b) => b.owed - a.owed],
				near: [__("Near the limit"), (x) => !x.blocked && limitUse(x) != null && limitUse(x) >= NEAR_LIMIT, (a, b) => limitUse(b) - limitUse(a)],
				owed: [__("Owe the most"), (x) => x.owed > 0, (a, b) => b.owed - a.owed],
				adv: [__("Advance holders"), (x) => x.adv > 0, (a, b) => b.adv - a.adv],
				all: [__("All"), () => true, (a, b) => b.owed - a.owed],
			};
			tools.innerHTML = `<div class="ceo-seg small" role="tablist">${Object.entries(tabs).map(([k, [l]]) => `<button data-act="cr-tab" data-val="${k}" aria-pressed="${st.crTab === k && st.crBucket == null}">${esc(l)}</button>`).join("")}</div>`;
			let list = rows.filter(tabs[st.crTab][1]);
			if (st.crBucket != null) list = list.filter((x) => ageBucket(x) === st.crBucket);
			list.sort(tabs[st.crTab][2]);
			const head = st.crBucket != null ? (st.crBucket < AGE_BUCKETS.length ? `${__("Oldest unpaid bill")}: ${__(AGE_BUCKETS[st.crBucket][2])}` : __("Owed by journal debit, no bill")) : tabs[st.crTab][0];
			sub("crlist", `${head}. ${__("Usual = average {0} a month over the last 12 months: what is at stake while they are on hold.", [st.measure === "kg" ? __("volume") : __("sales")])}`);
			if (!list.length) { el.innerHTML = `<div class="ceo-empty">${__("Nobody here.")}</div>`; return; }
			const top = list.slice(0, 15);
			const lim = (used, max, unit) => (max ? `<span class="${used > max ? "ceo-over" : ""}">${inr(used)}</span><span class="ceo-muted"> / ${inr(max)}${unit}</span>` : `<span class="ceo-muted">${inr(used)}${unit}</span>`);
			el.innerHTML = `<div class="ceo-tablewrap"><table class="ceo-table ceo-credit">
				<thead><tr><th>${__("Customer")}</th><th>${__("Company")}</th><th>${__("Status")}</th><th class="num">${__("Owed")}</th><th class="num">${__("Advance")}</th><th class="num">${__("Oldest bill")}</th><th class="num">${__("Unpaid bills")}</th><th class="num">${__("Limit used")}</th><th class="num">${__("Usual")}</th><th></th></tr></thead>
				<tbody>${top.map((x) => {
					const c = d.customers[x.cu], u = limitUse(x);
					return `<tr class="ceo-click ${dimState("cust", x.cu)}" data-dim="cust" data-val="${x.cu}" tabindex="0">
						<td><div class="ceo-custname"><span>${esc(c[1])}</span><small>${esc(d.segments[x.seg])}</small></div></td>
						<td class="ceo-cos">${x.co >= 0 ? `<span>${esc(d.companies[x.co].abbr)}</span>` : ""}</td>
						<td>${x.blocked ? `<span class="ceo-badge serious"><span aria-hidden="true">!!</span>${esc(__(BLOCK_LABEL[x.blocked]))}</span>` : u != null && u >= NEAR_LIMIT ? `<span class="ceo-badge warning"><span aria-hidden="true">!</span>${__("Near limit")}</span>` : `<span class="ceo-badge ok"><span aria-hidden="true">✓</span>${__("Can buy")}</span>`}</td>
						<td class="num">${x.owed > 0 ? esc(rs(x.owed)) : "—"}</td>
						<td class="num">${x.adv > 0 ? esc(rs(x.adv)) : "—"}</td>
						<td class="num">${journalOnly(x) ? `<span class="ceo-muted" title="${esc(__("Owed through Journal Entries with no Sales Invoice behind it"))}">${__("journal only")}</span>` : x.owed > 0 ? lim(x.days, x.dlim, " d") : "—"}</td>
						<td class="num">${lim(x.bills, x.blim, "")}</td>
						<td class="num">${u == null ? `<span class="ceo-muted">${cashOnly(x) ? __("cash only") : __("no limit")}</span>` : `<div class="ceo-usebar"><span style="width:${Math.min(100, Math.max(0, u * 100))}%" class="${u > 1 ? "over" : u >= NEAR_LIMIT ? "near" : ""}"></span></div>${u < 0 ? __("paid ahead") : inr(u * 100, 0) + "%"}`}</td>
						<td class="num">${usual.get(x.cu) ? esc(fmtM(usual.get(x.cu))) : "—"}</td>
						<td><button class="ceo-drill" data-act="drill" data-kind="cust" data-val="${x.cu}" aria-label="${esc(__("Details"))}">›</button></td></tr>`;
				}).join("")}</tbody></table></div>
				<div class="ceo-foot">${__("Showing {0} of {1}", [inr(top.length), inr(list.length)])}</div>`;
		}

		function companyMoney(co, W) {
			if (!st.mn) return "";
			let cash = 0, loan = 0, owed = 0, pay = 0;
			for (const x of st.mn.cash) if (x.co === co) { if (x.kind < 2) cash += x.now; else loan += x.now; }
			for (const x of st.mn.recv) if (x.co === co && okInternal(x.cu) && x.now > 0) owed += x.now;
			for (const x of st.mn.pay) if (x.co === co && passPay(x) && x.now > 0) pay += x.now;
			const g = SHOW_MARGIN ? marginTotals(W, (r) => r[R_CO] === co && pass(r, "co")).cur : null;
			return `<h4>${__("Money")} <span class="ceo-muted">· ${esc(D().through_label)}</span></h4><div class="ceo-crbox"><dl>
				<dt>${__("Cash and bank")}</dt><dd>${esc(rs(cash))}</dd><dt>${__("Bank loans")}</dt><dd>${esc(rs(loan))}</dd>
				<dt>${__("Customers owe")}</dt><dd>${esc(rs(owed))}</dd><dt>${__("We owe suppliers")}</dt><dd>${esc(rs(pay))}</dd>
				${SHOW_MARGIN ? `<dt>${__("Gas margin")}</dt><dd>${g.m != null ? `Rs ${inr(g.m, 2)}/kg${g.share < MARGIN_PARTIAL ? ` <span class="ceo-muted">(${inr(g.share * 100, 0)}% ${__("of volume")})</span>` : ""}` : "—"}</dd>` : ""}</dl></div>`;
		}

		function renderFootnote() {
			if (!SHOW_COMPARISON) { slot("footnote").textContent = ""; return; }   // explanatory text is off with the comparisons
			const d = D();
			slot("footnote").textContent = [
				__("Sales from submitted Sales Invoices; volume = items sold by the kg (LP Gas). Collections = Payment Entry receipts only (Journal Entry receipts are not counted)."),
				__("Money figures are ledger balances (GL Entries) on the data-through day; gas margin = sale price minus the company's gas Purchase Invoice price that month."),
				d.thin ? __("Billing on this site thins out after {0}; the {1} bills after it are not counted.", [d.through_label, inr(d.excluded.bills)]) : "",
				st.internal ? "" : __("Sales between group companies are left out."),
				__("Figures refreshed {0}.", [frappe.datetime.str_to_user(d.generated)]),
			].filter(Boolean).join(" ");
		}

		// -------------------------------------------------------- drill-down panel
		function openDrawer(kind, val) { st.drawer = { kind, val, invoices: null }; renderDrawer(); if (kind === "cust") fetchInvoices(); }
		function closeDrawer() { st.drawer = null; const el = slot("drawer"); el.hidden = true; el.innerHTML = ""; }
		function windowDates() {
			const d = D(), W = st.W;
			if (inWin(W, wkS())) return st.weekInfo ? [st.weekInfo.from, st.weekInfo.to] : [d.through, d.through];
			let a = null, b = null;
			for (let m = 0; m < NM(); m++) if (monthIn(W, m)) { if (a == null) a = m; b = m; }
			if (a == null) return [d.through, d.through];
			// A window that starts in the late half of a month (12 months) starts the
			// day after the data-through day of that month, not on the 1st.
			const lateStart = !inWin(W, a * 2) && inWin(W, a * 2 + 1);
			return [lateStart ? isoAdd(d.month_bounds[a][0], d.through_day) : d.month_bounds[a][0], b === PM() ? d.through : d.month_bounds[b][1]];
		}
		function fetchInvoices() {
			const dr = st.drawer, c = D().customers[dr.val], [a, b] = windowDates();
			frappe.call({
				method: "avinashgroup_app.ceo_dashboard.api.get_customer_invoices",
				args: { customer: c[0], from_date: a, to_date: b },
				callback: (r) => { if (st.drawer === dr) { dr.invoices = r.message || []; renderDrawer(); } },
			});
		}
		function renderDrawer() {
			const dr = st.drawer, d = D(), el = slot("drawer"), W = st.W;
			el.hidden = false;
			const [a, b] = windowDates();
			let title, subtitle, rowPass, collPass, extra = "", listFilters;
			if (dr.kind === "cust") {
				const c = d.customers[dr.val];
				title = c[1];
				subtitle = `${d.segments[c[2]]} · ${__("first bill")} ${c[6] ? frappe.datetime.str_to_user(c[6]) : "—"} · ${__("last bill")} ${c[4] || "—"}`;
				rowPass = (r) => r[R_CU] === dr.val;
				collPass = (r) => r[R_CU] === dr.val;
				listFilters = { customer: c[0], docstatus: 1, posting_date: ["Between", [a, b]] };
				const cr = !pastYear() && st.cr && st.cr.find((x) => x.cu === dr.val);   // today's position: not for a past year
				const crBlock = cr ? `<h4>${__("Credit control")} <span class="ceo-muted">· ${esc(st.credit.as_of_label)}</span></h4>
					<div class="ceo-crbox">${cr.blocked ? `<span class="ceo-badge serious"><span aria-hidden="true">!!</span>${__("On hold")}: ${esc(__(BLOCK_LABEL[cr.blocked]))}</span>` : `<span class="ceo-badge ok"><span aria-hidden="true">✓</span>${__("Can buy")}</span>`}
					<dl><dt>${__("Owed")}</dt><dd>${esc(rs(Math.max(0, cr.owed)))}</dd><dt>${__("Advance left")}</dt><dd>${esc(rs(cr.adv))}</dd>
					<dt>${__("Oldest unpaid bill")}</dt><dd>${journalOnly(cr) ? __("none (journal debit)") : cr.owed > 0 ? `${inr(cr.days)} ${__("days")}${cr.dlim ? ` / ${inr(cr.dlim)}` : ""}` : "—"}</dd>
					<dt>${__("Unpaid bills")}</dt><dd>${inr(cr.bills)}${cr.blim ? ` / ${inr(cr.blim)}` : ""}</dd>
					<dt>${__("Amount limit")}</dt><dd>${cashOnly(cr) ? __("Cash only") : cr.lim ? `${esc(rs(cr.exp))} / ${esc(rs(cr.lim))}` : "—"}</dd></dl></div>` : "";
				extra = crBlock + `<h4>${__("Bills in this period")}</h4>` + (dr.invoices == null ? `<div class="ceo-skel line"></div><div class="ceo-skel line"></div><div class="ceo-skel line"></div>`
					: dr.invoices.length ? `<table class="ceo-table compact"><tbody>${dr.invoices.map((iv) => `<tr class="ceo-click" data-act="open-doc" data-doctype="Sales Invoice" data-val="${esc(iv.name)}"><td><strong>${esc(iv.name)}</strong><small class="ceo-block">${esc(iv.posting_date_bs)}${iv.is_return ? ` · ${__("return")}` : ""}</small></td><td class="num">${esc(rs(iv.base_net_total))}<small class="ceo-block">${inr(iv.total_qty)} ${__("qty")}</small></td></tr>`).join("")}</tbody></table>`
					: `<div class="ceo-empty">${__("No bills in this period.")}</div>`);
			} else {
				const c = d.companies[dr.val];
				title = c.name;
				subtitle = `${c.abbr} · ${periodLabel(W)}`;
				rowPass = (r) => r[R_CO] === dr.val && pass(r, "co");
				collPass = (r) => r[R_CO] === dr.val && passColl(r, "co");
				listFilters = { company: c.name, docstatus: 1, posting_date: ["Between", [a, b]] };
				const agg = new Map(), segs = d.segments.map(() => 0);
				for (const r of d.sales) { if (!inWin(W, r[R_SLOT]) || !rowPass(r)) continue; agg.set(r[R_CU], (agg.get(r[R_CU]) || 0) + mv(r)); segs[r[R_SEG]] += mv(r); }
				const top = [...agg.entries()].sort((x, y) => y[1] - x[1]).slice(0, 8), tot = [...agg.values()].reduce((x, y) => x + y, 0);
				extra = `<h4>${__("Segment split")}</h4><div class="ceo-share small">${segs.map((v, i) => (v > 0 ? `<div class="ceo-share-part" style="flex:${v};background:var(--ceo-seg${i})" data-tip="${tip(tipRows(d.segments[i], [["", measureName(), esc(fmtM(v))], ["", __("Share"), tot ? `${inr((v / tot) * 100, 1)}%` : "—"]]))}">${tot && v / tot > 0.14 ? `<span>${esc(d.segments[i])}</span>` : ""}</div>` : "")).join("")}</div>
					${companyMoney(dr.val, W)}
					<h4>${__("Top customers")}</h4><table class="ceo-table compact"><tbody>${top.map(([cu, v]) => `<tr class="ceo-click" data-act="drill" data-kind="cust" data-val="${cu}"><td>${esc(d.customers[cu][1])}</td><td class="num">${esc(fmtM(v))}</td><td class="num ceo-muted">${tot ? inr((v / tot) * 100, 0) + "%" : ""}</td></tr>`).join("")}</tbody></table>`;
			}
			const t = totals(W, rowPass, collPass);
			const ser = last24(monthly(rowPass, mv));
			const stat = (l, v, dd) => `<div class="ceo-dstat"><span>${esc(l)}</span><strong>${v}</strong>${dd || ""}</div>`;
			el.innerHTML = `<header><div><h3>${esc(title)}</h3><p>${esc(subtitle)}</p></div><button class="ceo-icon" data-act="close-drawer" aria-label="${esc(__("Close"))}">✕</button></header>
				<div class="ceo-dbody">
				<div class="ceo-dstats">${stat(__("Volume"), esc(mt(t.kg)), delta(t.kg, t.kgP))}${stat(__("Net sales"), esc(rs(t.amt)), delta(t.amt, t.amtP))}${stat(__("Rs/kg"), t.rate ? `Rs ${inr(t.rate, 2)}` : "—", delta(t.rate, t.rateP))}${stat(__("Collected"), esc(rs(t.coll)), t.amt ? `<span class="ceo-delta-note">${inr((t.coll / t.amt) * 100, 0)}% ${__("of billed")}</span>` : "")}</div>
				<h4>${__("24 months")} · ${esc(measureName())}</h4>${spark(flow(ser), winMonths(W), true)}
				${extra}
				<button class="ceo-btn" data-act="open-list" data-filters="${esc(JSON.stringify(listFilters))}">${__("Open these Sales Invoices")} →</button>
				</div>`;
		}

		load(false);
		loadCredit();
		return { refresh: () => { load(false); loadCredit(); }, state: st };
	}

	return { mount };
})();
