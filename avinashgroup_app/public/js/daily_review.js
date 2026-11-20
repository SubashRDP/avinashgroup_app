/* Daily Business Review (page/daily_review). Six cards in the meeting's agenda
   order, each the totals of an existing report for one day; a click opens
   that report with the same filters. Server: ceo_dashboard/daily_review.py.

   Layout rule from the user (2026-11-17): the information must not pile up on
   the left. So the header is centred, the six cards are the same width and
   height on an even grid, and inside a card the headline figure and its three
   stats are centred, with the company list below spanning the full width.

   No figure is computed here beyond sums of the report's own rows, and none
   is flagged: the books are shown as they are. */
window.avinash_daily_review = (() => {
	const API = "avinashgroup_app.ceo_dashboard.daily_review";
	const BS_MONTHS = ["Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin", "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"];
	const LIST_MAX = 7;

	const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
	const inr = (v, d = 0) => Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
	const sum = (rows, f) => (rows || []).reduce((a, r) => a + (Number(typeof f === "function" ? f(r) : r[f]) || 0), 0);
	function rs(v) {
		const a = Math.abs(v || 0), sign = v < 0 ? "−" : "";
		if (a >= 1e7) return `${sign}Rs ${inr(a / 1e7, 2)} Cr`;
		if (a >= 1e5) return `${sign}Rs ${inr(a / 1e5, 2)} L`;
		return `${sign}Rs ${inr(a)}`;
	}
	function mt(kg) {
		const t = (kg || 0) / 1000, a = Math.abs(t);
		return `${t < 0 ? "−" : ""}${inr(a, a < 100 ? 2 : 0)} MT`;
	}
	const fmt = (kind, v) => (kind === "mt" ? mt(v) : kind === "n" ? inr(v) : rs(v));
	const full = (kind, v) => (kind === "mt" ? `${inr((v || 0) / 1000, 3)} MT` : kind === "n" ? inr(v) : `Rs ${inr(v, 2)}`);

	// Agenda order of the meeting (the user's list, 2026-11-17).
	const CARDS = [
		{ key: "bank", title: __("Bank Balance"), ico: "bank", report: "Net Position of Cash and Bank" },
		{ key: "loans", title: __("Loan Summary"), ico: "loan", report: "Loan Summary" },
		{ key: "sales", title: __("Today's Sales"), ico: "sales", report: "Sales Report Summary" },
		{ key: "collection", title: __("Collection"), ico: "coll", report: "Receipt Register" },
		{ key: "stock", title: __("Gas Stock"), ico: "gas", report: "Stock Balance (With Zero Values)" },
		{ key: "debtors", title: __("Debtors Summary"), ico: "people", report: "Debtors Summary" },
	];

	function mount(host, page) {
		const st = { date: frappe.datetime.get_today(), meta: null, data: {}, tab: {}, present: -1, seq: 0 };
		const root = document.createElement("div");
		root.className = "mm";
		host.appendChild(root);
		root.innerHTML = `
			<header class="mm-head">
				<div class="mm-eyebrow">${esc(__("Avinash Group · Management meeting"))}</div>
				<h1 class="mm-title">${esc(__("Daily Business Review"))}</h1>
				<div class="mm-when"></div>
				<div class="mm-bar" role="toolbar">
					<button class="mm-btn icon" data-act="prev" aria-label="${esc(__("Previous day"))}">‹</button>
					<input class="mm-date" type="date" aria-label="${esc(__("Day"))}">
					<button class="mm-btn icon" data-act="next" aria-label="${esc(__("Next day"))}">›</button>
					<span class="mm-sep"></span>
					<button class="mm-btn" data-act="today">${esc(__("Today"))}</button>
					<button class="mm-btn" data-act="yesterday">${esc(__("Yesterday"))}</button>
					<span class="mm-sep"></span>
					<button class="mm-btn" data-act="refresh">${esc(__("Refresh"))}</button>
					<button class="mm-btn primary" data-act="present">${esc(__("Present"))}</button>
				</div>
			</header>
			<main class="mm-grid">${CARDS.map((c, i) => `<article class="mm-card" data-sec="${c.key}" data-i="${i}"></article>`).join("")}</main>
			<nav class="mm-dots" aria-label="${esc(__("Topics"))}">
				<button class="mm-btn icon" data-act="pprev" aria-label="${esc(__("Previous topic"))}">‹</button>
				${CARDS.map((c, i) => `<button class="mm-dot" data-act="pgo" data-i="${i}" aria-label="${esc(c.title)}"><b>${i + 1}</b><span>${esc(c.title)}</span></button>`).join("")}
				<button class="mm-btn icon" data-act="pnext" aria-label="${esc(__("Next topic"))}">›</button>
				<button class="mm-btn" data-act="pexit">${esc(__("Close"))}</button>
			</nav>`;
		const $ = (s) => root.querySelector(s);
		const dateEl = $(".mm-date");

		if (page) {
			page.set_secondary_action(__("CEO Dashboard"), () => frappe.set_route("ceo-dashboard"));
		}

		// ------------------------------------------------------------ dates
		const short = (d) => frappe.datetime.str_to_obj(d).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
		function whenLine() {
			const d = frappe.datetime.str_to_obj(st.date);
			const ad = d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
			const bs = st.meta && st.meta.date === st.date ? st.meta.bs : null;
			$(".mm-when").innerHTML = `<b>${esc(ad)}</b>${bs ? `<span>${esc(`${BS_MONTHS[bs[1] - 1]} ${bs[2]}, ${bs[0]} BS`)}</span>` : ""}`;
		}
		function setDate(d, refresh) {
			if (!d) return;
			st.date = d;
			dateEl.value = d;
			const url = new URL(location.href);
			url.searchParams.set("date", d);
			history.replaceState(history.state, "", url);
			load(refresh);
		}
		const shift = (n) => setDate(frappe.datetime.add_days(st.date, n));

		// ------------------------------------------------------------ load
		function load(refresh) {
			const seq = ++st.seq;
			st.data = {};
			whenLine();
			frappe.call({ method: `${API}.get_meta`, args: { date: st.date } }).then((r) => {
				if (seq !== st.seq) return;
				st.meta = r.message;
				whenLine();
			});
			CARDS.forEach((c, i) => {
				drawCard(i);
				frappe.call({ method: `${API}.get_section`, args: { section: c.key, date: st.date, refresh: refresh ? 1 : 0 } })
					.then((r) => { if (seq === st.seq) { st.data[c.key] = r.message; drawCard(i); } })
					.catch(() => { if (seq === st.seq) { st.data[c.key] = { error: true }; drawCard(i); } });
			});
		}

		// ------------------------------------------------------------ cards
		// Each section becomes the same shape: hero figure, change since the
		// day before, three stats, and one or two lists.
		function model(key, d) {
			const day = short(st.date);
			if (key === "bank") {
				const rows = d.rows || [];
				const closing = sum(rows, "closing"), opening = sum(rows, "opening");
				return {
					hero: rs(closing), heroFull: full("rs", closing), cap: __("Cash and bank, closing on {0}", [day]),
					chg: closing - opening, kind: "rs",
					stats: [[__("Bank"), rs(sum(rows, "bank"))], [__("Cash"), rs(sum(rows, "cash"))], [__("Received / paid"), rs(sum(rows, "receipts")), `${__("paid")} ${rs(sum(rows, "payments"))}`]],
					lists: [{ name: __("By company"), kind: "rs", rows: rows.map((r) => ({ label: r.abbr, value: r.closing, co: r.co })) }],
					open: (row) => ({ company: (row && row.co) || (rows[0] && rows[0].co), from_date: st.date, to_date: st.date }),
				};
			}
			if (key === "loans") {
				return {
					hero: rs(d.total), heroFull: full("rs", d.total), cap: __("Loans outstanding on {0}", [day]),
					chg: d.before == null ? null : d.total - d.before, kind: "rs",
					stats: [[__("Short term"), rs(d.short)], [__("Long term"), rs(d.long)], [__("Companies"), inr((d.companies || []).length)]],
					lists: [
						{ name: __("By loan type"), kind: "rs", rows: (d.types || []).map((r) => ({ label: r.label, value: r.value })) },
						{ name: __("By company"), kind: "rs", rows: (d.companies || []).map((r) => ({ label: r.abbr, value: r.value })) },
					],
					open: () => ({ from_date: d.fy_start, to_date: st.date }),
				};
			}
			if (key === "sales") {
				const rows = d.rows || [], kg = sum(rows, "kg");
				return {
					hero: mt(kg), heroFull: full("mt", kg), cap: __("LP Gas sold on {0}", [day]),
					chg: kg - sum(d.before, "kg"), kind: "mt",
					stats: [[__("Taxable sales"), rs(sum(rows, "taxable"))], [__("VAT"), rs(sum(rows, "vat"))], [__("Total with VAT"), rs(sum(rows, "amount"))]],
					lists: [
						{ name: __("By company"), kind: "rs", rows: rows.map((r) => ({ label: r.abbr, value: r.taxable, sub: r.kg ? mt(r.kg) : "" })) },
						{ name: __("By item"), kind: "rs", rows: (d.items || []).map((r) => ({ label: r.item, value: r.taxable, sub: `${inr(r.qty)} × ${r.uom || ""}` })) },
					],
					open: () => ({ report_type: "Sales Report Summary", company: (st.meta ? st.meta.companies : []).map((c) => c.name), date_filter_type: "Date Range", from_date: st.date, to_date: st.date }),
					empty: __("No sales on this day"),
				};
			}
			if (key === "collection") {
				const rows = d.rows || [], amt = sum(rows, "amount");
				const top = d.top || [];
				return {
					hero: rs(amt), heroFull: full("rs", amt), cap: __("Received from customers on {0}", [day]),
					chg: amt - sum(d.before, "amount"), kind: "rs",
					stats: [[__("Customers paid"), inr(sum(rows, "customers"))], [__("Largest receipt"), top.length ? rs(top[0].amount) : "–"], [__("Day before"), rs(sum(d.before, "amount"))]],
					lists: [
						{ name: __("By company"), kind: "rs", rows: rows.map((r) => ({ label: r.abbr, value: r.amount, sub: `${inr(r.customers)} ${r.customers === 1 ? __("customer") : __("customers")}`, co: r.co })) },
						{ name: __("Top customers"), kind: "rs", rows: top.map((r) => ({ label: r.name, value: r.amount, sub: r.abbr })) },
					],
					open: (row) => ({ view: "Customer Wise Summary", company: (row && row.co) || (rows[0] && rows[0].co) || (st.meta && st.meta.companies[0].name), from_date: st.date, to_date: st.date }),
					empty: __("No receipts on this day"),
				};
			}
			if (key === "stock") {
				const rows = d.rows || [], closing = sum(rows, "closing");
				return {
					hero: mt(closing), heroFull: full("mt", closing), cap: __("LP Gas closing stock on {0}", [day]),
					chg: closing - sum(rows, "opening"), kind: "mt",
					stats: [[__("Opening"), mt(sum(rows, "opening"))], [__("Received"), mt(sum(rows, "in"))], [__("Issued"), mt(sum(rows, "out"))]],
					lists: [
						{ name: __("By company"), kind: "mt", rows: rows.map((r) => ({ label: r.abbr, value: r.closing, sub: r.in || r.out ? `+${mt(r.in)} / −${mt(r.out)}` : "", co: r.co, group: r.group })) },
						{ name: __("By warehouse"), kind: "mt", rows: rows.flatMap((r) => r.warehouses.map((w) => ({ label: w.name, value: w.closing, co: r.co, group: r.group }))) },
					],
					open: (row) => { const r = row || rows[0] || {}; return { company: r.co, from_date: st.date, to_date: st.date, item_group: r.group }; },
				};
			}
			// debtors
			const rows = d.rows || [];
			return {
				hero: rs(d.total), heroFull: full("rs", d.total), cap: __("Receivable on {0}", [day]),
				chg: d.before == null ? null : d.total - d.before, kind: "rs",
				stats: [[__("Gas customers"), rs(d.gas)], [__("Cylinder deposits"), rs(d.cyl)], [__("Companies"), inr(rows.length)]],
				lists: [{ name: __("By company"), kind: "rs", rows: rows.map((r) => ({ label: r.abbr, value: r.total, sub: r.total !== r.before ? `${r.total > r.before ? "▲" : "▼"} ${rs(Math.abs(r.total - r.before))}` : "" })) }],
				open: () => (d.bs ? { view: "Monthly", bs_year: d.bs[0], bs_month: `${String(d.bs[1]).padStart(2, "0")} - ${BS_MONTHS[d.bs[1] - 1]}` } : {}),
			};
		}

		function chgLine(m) {
			if (m.chg == null) return "";
			if (Math.abs(m.chg) < (m.kind === "mt" ? 0.5 : 0.5)) return `<div class="mm-chg flat">${esc(__("No change from the day before"))}</div>`;
			const up = m.chg > 0;
			return `<div class="mm-chg ${up ? "up" : "down"}" title="${esc(full(m.kind, m.chg))}"><i>${up ? "▲" : "▼"}</i>${esc(fmt(m.kind, Math.abs(m.chg)))} <span>${esc(__("from the day before"))}</span></div>`;
		}

		function listHtml(list, key) {
			const rows = list.rows.filter((r) => r.value).sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
			if (!rows.length) return "";
			const shown = rows.slice(0, LIST_MAX), rest = rows.slice(LIST_MAX);
			if (rest.length) shown.push({ label: __("{0} more", [rest.length]), value: sum(rest, "value"), rest: true });
			const max = Math.max(...shown.map((r) => Math.abs(r.value))) || 1;
			const neg = shown.some((r) => r.value < 0);
			return `<ol class="mm-list ${neg ? "has-neg" : ""}">${shown.map((r, i) => {
				const w = (Math.abs(r.value) / max) * (neg ? 50 : 100);
				const bar = neg ? `left:${r.value < 0 ? 50 - w : 50}%;width:${w}%` : `left:0;width:${w}%`;
				const click = !r.rest && (r.co || r.group) ? `data-act="openrow" data-row="${i}"` : "";
				return `<li ${click} class="${r.value < 0 ? "neg" : ""} ${r.rest ? "rest" : ""}" title="${esc(`${r.label}: ${full(list.kind, r.value)}`)}">
					<span class="mm-l">${esc(r.label)}${r.sub ? `<small>${esc(r.sub)}</small>` : ""}</span>
					<span class="mm-track"><span class="mm-fill" style="${bar}"></span>${neg ? `<span class="mm-zero"></span>` : ""}</span>
					<span class="mm-v">${esc(fmt(list.kind, r.value))}</span>
				</li>`;
			}).join("")}</ol>`;
		}

		function drawCard(i) {
			const c = CARDS[i], el = root.querySelector(`.mm-card[data-i="${i}"]`);
			const d = st.data[c.key];
			const head = `<header class="mm-chead">
				<span class="mm-no">${i + 1}</span>
				<span class="mm-ico" data-ico="${c.ico}"></span>
				<h2>${esc(c.title)}</h2>
				<button class="mm-open" data-act="open" data-i="${i}" ${d && !d.error ? "" : "disabled"} title="${esc(__("Open {0}", [c.report]))}">${esc(__("Report"))} <span aria-hidden="true">↗</span></button>
			</header>`;
			if (!d) {
				el.innerHTML = `${head}<div class="mm-hero"><div class="mm-skel big"></div><div class="mm-skel"></div></div><div class="mm-stats">${"<div><div class='mm-skel'></div></div>".repeat(3)}</div><div class="mm-skel block"></div>`;
				el.classList.add("is-loading");
				return;
			}
			el.classList.remove("is-loading");
			if (d.error) {
				el.innerHTML = `${head}<div class="mm-empty">${esc(__("Could not read {0}. Refresh to try again.", [c.report]))}</div>`;
				return;
			}
			const m = model(c.key, d);
			el._model = m;
			const tab = Math.min(st.tab[c.key] || 0, m.lists.length - 1);
			const list = m.lists[tab];
			const body = listHtml(list, c.key);
			el.innerHTML = `${head}
				<div class="mm-hero">
					<div class="mm-val" title="${esc(m.heroFull)}">${esc(m.hero)}</div>
					<div class="mm-cap">${esc(m.cap)}</div>
					${chgLine(m)}
				</div>
				<div class="mm-stats">${m.stats.map(([l, v, sub]) => `<div><span>${esc(l)}</span><b>${esc(v)}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</div>`).join("")}</div>
				<div class="mm-lists">
					${m.lists.length > 1 ? `<div class="mm-tabs" role="tablist">${m.lists.map((l, k) => `<button role="tab" aria-selected="${k === tab}" data-act="tab" data-i="${i}" data-k="${k}">${esc(l.name)}</button>`).join("")}</div>` : `<div class="mm-tabs one"><span>${esc(list.name)}</span></div>`}
					${body || `<div class="mm-empty">${esc(m.empty || __("Nothing on this day"))}</div>`}
				</div>`;
			el._rows = list.rows.filter((r) => r.value).sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
		}

		function openReport(i, row) {
			const c = CARDS[i], el = root.querySelector(`.mm-card[data-i="${i}"]`);
			if (!el._model) return;
			const filters = el._model.open(row);
			if (st.present >= 0) present(-1);
			frappe.route_options = filters;
			frappe.set_route("query-report", c.report);
		}

		// ------------------------------------------------------------ present
		// One topic at a time on the meeting screen; arrow keys move, Esc closes.
		function present(i) {
			st.present = i;
			root.classList.toggle("is-present", i >= 0);
			document.body.classList.toggle("mm-presenting", i >= 0);
			root.querySelectorAll(".mm-card").forEach((el, k) => el.classList.toggle("is-on", k === i));
			root.querySelectorAll(".mm-dot").forEach((el, k) => el.setAttribute("aria-current", k === i ? "step" : "false"));
			if (i >= 0 && !document.fullscreenElement && root.requestFullscreen) root.requestFullscreen().catch(() => {});
			if (i < 0 && document.fullscreenElement) document.exitFullscreen().catch(() => {});
		}
		const step = (n) => present((st.present + n + CARDS.length) % CARDS.length);

		root.addEventListener("click", (e) => {
			const b = e.target.closest("[data-act]");
			if (!b || b.disabled) return;
			const act = b.dataset.act;
			if (act === "prev") shift(-1);
			else if (act === "next") shift(1);
			else if (act === "today") setDate(frappe.datetime.get_today());
			else if (act === "yesterday") setDate(frappe.datetime.add_days(frappe.datetime.get_today(), -1));
			else if (act === "refresh") load(true);
			else if (act === "present") present(0);
			else if (act === "pprev") step(-1);
			else if (act === "pnext") step(1);
			else if (act === "pgo") present(+b.dataset.i);
			else if (act === "pexit") present(-1);
			else if (act === "tab") { st.tab[CARDS[+b.dataset.i].key] = +b.dataset.k; drawCard(+b.dataset.i); }
			else if (act === "open") openReport(+b.dataset.i);
			else if (act === "openrow") { const card = b.closest(".mm-card"); openReport(+card.dataset.i, card._rows[+b.dataset.row]); }
		});
		dateEl.addEventListener("change", () => setDate(dateEl.value));
		const onKey = (e) => {
			if (st.present < 0 || !document.body.contains(root)) return;
			if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " ") { e.preventDefault(); step(1); }
			else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); step(-1); }
			else if (e.key === "Escape") present(-1);
			else if (/^[1-6]$/.test(e.key)) present(+e.key - 1);
		};
		document.addEventListener("keydown", onKey);
		document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement && st.present >= 0) present(-1); });

		const fromUrl = new URLSearchParams(location.search).get("date");
		setDate(/^\d{4}-\d{2}-\d{2}$/.test(fromUrl || "") ? fromUrl : st.date);
		return { show() { if (st.present >= 0) present(-1); } };
	}

	return { mount };
})();
