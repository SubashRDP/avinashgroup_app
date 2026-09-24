// HR Dashboard — one BS month of HR at a glance, with the HR menu.
//
// One implementation, mounted in two places:
//   * the top of the stock HR workspace (public/js/hr_workspace.js) — menu as a
//     top bar, since the desk sidebar is already there;
//   * the full-width page /app/hr-dashboard — menu down the left side.
// It also works inside a shadow root (theme mirrored, /app links routed here),
// should it ever be mounted from a Custom HTML Block.
// Data: avinashgroup_app.hr.hr_dashboard.get_dashboard / get_menu.
//
// Usage: avinash_hr_dashboard.mount(element_or_shadow_root, { menu: "top" | "side" })

(function () {
	if (window.avinash_hr_dashboard) return;

	const API = "avinashgroup_app.hr.hr_dashboard.";
	const CSS_URL = "/assets/avinashgroup_app/css/hr_dashboard.css?v=2";
	const STORE_KEY = "hr-dashboard";
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const num = (v) => format_number(v || 0, null, 0);
	const money = (v) => "Rs " + format_number(Math.round(v || 0), null, 0);

	// Small line icons, drawn on a 24px grid (stroke = currentColor).
	const ICONS = {
		people: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.3-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/><path d="M16 4.8a3.3 3.3 0 0 1 0 6.4M18 14.8c2 .6 3.2 2.3 3.5 5.2"/>',
		clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
		shift: '<path d="M4 7h13l-3-3M20 17H7l3 3"/>',
		calendar: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
		wallet: '<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M16 14.5h2"/>',
		gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
		home: '<path d="M3.5 11 12 4l8.5 7"/><path d="M6 9.5V20h12V9.5"/>',
		chevron: '<path d="m9 6 6 6-6 6"/>',
		down: '<path d="m6 9 6 6 6-6"/>',
		search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
		check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
		alert: '<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5M12 17.5v.5"/>',
		cake: '<path d="M4 20h16v-7H4zM4 16c2 1.5 4 1.5 6 0s4-1.5 6 0 3 1.5 4 0"/><path d="M12 13V9M12 6.5v-.5"/>',
		star: '<path d="m12 3.5 2.6 5.4 5.9.8-4.3 4.1 1 5.8L12 16.8l-5.2 2.8 1-5.8-4.3-4.1 5.9-.8z"/>',
		flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
		plus: '<path d="M12 5v14M5 12h14"/>',
		device: '<rect x="6" y="3" width="12" height="18" rx="2"/><path d="M10 17.5h4"/>',
		refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"/>',
		menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
		bank: '<path d="M3 10 12 4l9 6M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18"/>',
		gift: '<rect x="3.5" y="9" width="17" height="11" rx="1.5"/><path d="M12 9v11M3.5 13h17M12 9c-2-4-6-4-6-1.5S10 9 12 9c2 0 6 0 6-1.5S14 5 12 9"/>',
		user_check: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.3-5.5 6.5-5.5 1.6 0 3 .4 4.2 1.2"/><path d="m15 18 2 2 4-4"/>',
		away: '<path d="M4 20h16M6 20V9l6-5 6 5v11"/><path d="M10 20v-5h4v5"/>',
	};
	const icon = (name, cls = "") =>
		`<svg class="hrd-icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;

	function store(patch) {
		let state = {};
		try {
			state = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
			if (patch) localStorage.setItem(STORE_KEY, JSON.stringify(Object.assign(state, patch)));
		} catch (e) {
			// Storage can be blocked (private window); the page works without it.
		}
		return state;
	}

	function menu_href(item) {
		const slug = frappe.router.slug(item.name);
		if (item.type === "report") return `/app/query-report/${encodeURIComponent(item.name)}`;
		if (item.type === "new") return `/app/${slug}/new`;
		return `/app/${slug}`;
	}

	class HRDashboard {
		constructor(container, opts) {
			this.opts = Object.assign({ menu: "side" }, opts);
			this.company = store().company || "";
			this.month = null; // {bs_year, bs_month}; null = let the server pick

			// Inside a shadow root the desk's stylesheet is there but ours is not.
			if (container instanceof ShadowRoot) {
				$(`<link rel="stylesheet" href="${CSS_URL}">`).appendTo(container);
			}
			this.$root = $(`<div class="hrd hrd-menu-${this.opts.menu}">
				<nav class="hrd-nav" aria-label="${__("HR menu")}"></nav>
				<main class="hrd-main"><div class="hrd-loading">${__("Loading…")}</div></main>
			</div>`).appendTo(container);
			this.$nav = this.$root.find(".hrd-nav");
			this.$main = this.$root.find(".hrd-main");

			this.sync_theme();
			new MutationObserver(() => this.sync_theme()).observe(document.documentElement, {
				attributes: true,
				attributeFilter: ["data-theme"],
			});
			this.route_links();
			this.load_menu();
			this.refresh();
		}

		// Selectors in a shadow root cannot see <html data-theme>, so mirror it.
		sync_theme() {
			this.$root.attr("data-theme", document.documentElement.getAttribute("data-theme") || "light");
		}

		// Links inside a shadow root escape the desk router and reload the whole
		// page; route them ourselves. Ctrl/Cmd/middle click still opens a tab.
		route_links() {
			this.$root.on("click", "a[href^='/app']", (e) => {
				if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
				e.preventDefault();
				const [path, query] = e.currentTarget.getAttribute("href").split("?");
				if (query) frappe.route_options = Object.fromEntries(new URLSearchParams(query));
				this.close_menus();
				frappe.set_route(decodeURIComponent(path.replace(/^\/app\//, "")));
			});
		}

		// ------------------------------------------------------------ menu
		load_menu() {
			frappe.xcall(API + "get_menu").then((groups) => {
				this.groups = groups;
				this.opts.menu === "top" ? this.render_top_menu() : this.render_side_menu();
			});
		}

		render_side_menu() {
			const open = store().open || { [this.groups[0]?.label]: true };
			this.$nav.html(`
				<button class="hrd-nav-toggle" type="button">${icon("menu")}<span>${__("HR Menu")}</span></button>
				<div class="hrd-nav-body">
					<label class="hrd-search">${icon("search")}
						<input type="search" placeholder="${__("Search HR…")}" aria-label="${__("Search HR menu")}">
					</label>
					<a class="hrd-nav-home is-active" href="/app/hr-dashboard">${icon("home")}<span>${__("Dashboard")}</span></a>
					${this.groups
						.map(
							(g) => `<section class="hrd-group ${open[g.label] ? "is-open" : ""}" data-group="${esc(g.label)}">
							<button class="hrd-group-head" type="button" aria-expanded="${!!open[g.label]}">
								${icon(g.icon)}<span>${esc(g.label)}</span>${icon("chevron", "hrd-chev")}
							</button>
							<ul>${this.menu_items(g)}</ul>
						</section>`
						)
						.join("")}
					<p class="hrd-empty-search">${__("Nothing matches")}</p>
				</div>`);

			this.$nav.on("click", ".hrd-group-head", (e) => {
				const $g = $(e.currentTarget).closest(".hrd-group").toggleClass("is-open");
				$(e.currentTarget).attr("aria-expanded", $g.hasClass("is-open"));
				const state = store().open || {};
				state[$g.data("group")] = $g.hasClass("is-open");
				store({ open: state });
			});
			this.$nav.on("click", ".hrd-nav-toggle", () => this.$nav.toggleClass("is-shown"));
			this.$nav.on("input", "input[type=search]", (e) => this.filter_menu(e.target.value));
		}

		// A bar of the six groups, each opening its list below it — the desk's
		// own sidebar is already on screen in the workspace, so a second column
		// would only squeeze the dashboard.
		render_top_menu() {
			this.$nav.html(`
				<div class="hrd-topbar">
					${this.groups
						.map(
							(g, i) => `<div class="hrd-top-group" data-group="${i}">
							<button type="button" class="hrd-top-btn" aria-expanded="false" aria-haspopup="true">
								${icon(g.icon)}<span>${esc(g.label)}</span>${icon("down", "hrd-caret")}
							</button>
							<ul class="hrd-drop">${this.menu_items(g)}</ul>
						</div>`
						)
						.join("")}
					<label class="hrd-search hrd-top-search">${icon("search")}
						<input type="search" placeholder="${__("Search HR…")}" aria-label="${__("Search HR menu")}">
						<ul class="hrd-drop hrd-results"></ul>
					</label>
				</div>`);

			this.$nav.on("click", ".hrd-top-btn", (e) => {
				const $g = $(e.currentTarget).closest(".hrd-top-group");
				const was_open = $g.hasClass("is-open");
				this.close_menus();
				if (!was_open) {
					$g.addClass("is-open");
					$(e.currentTarget).attr("aria-expanded", "true");
				}
				e.stopPropagation();
			});
			this.$nav.on("input focus", "input[type=search]", (e) => this.search_top(e.target.value));
			this.$nav.on("keydown", "input[type=search]", (e) => {
				if (e.key === "Enter") this.$nav.find(".hrd-results a").first()[0]?.click();
			});
			$(document).on("click.hrd keydown.hrd", (e) => {
				if (e.type === "keydown" && e.key !== "Escape") return;
				// Clicks inside the shadow root arrive retargeted to the host.
				if (e.type === "click" && this.$nav[0].contains(e.originalEvent?.composedPath?.()[0])) return;
				this.close_menus();
			});
		}

		search_top(text) {
			const q = text.trim().toLowerCase();
			const $results = this.$nav.find(".hrd-results");
			if (!q) return $results.removeClass("is-shown").empty();
			const hits = [];
			this.groups.forEach((g) =>
				g.items.forEach((i) => {
					if ((i.label + " " + i.name).toLowerCase().includes(q)) hits.push([g, i]);
				})
			);
			$results
				.html(
					hits.length
						? hits
								.slice(0, 12)
								.map(([g, i]) => `<li><a href="${menu_href(i)}">${esc(i.label)}<small>${esc(g.label)}</small></a></li>`)
								.join("")
						: `<li class="hrd-no-hit">${__("Nothing matches")}</li>`
				)
				.addClass("is-shown");
		}

		close_menus() {
			this.$nav.find(".hrd-top-group").removeClass("is-open").find(".hrd-top-btn").attr("aria-expanded", "false");
			this.$nav.find(".hrd-results").removeClass("is-shown");
		}

		menu_items(g) {
			return g.items
				.map(
					(i) => `<li><a href="${menu_href(i)}" data-search="${esc((i.label + " " + i.name).toLowerCase())}">
						${i.type === "new" ? icon("plus", "hrd-new") : ""}${esc(i.label)}</a></li>`
				)
				.join("");
		}

		filter_menu(text) {
			const q = text.trim().toLowerCase();
			let any = false;
			this.$nav.find(".hrd-group").each((_, g) => {
				const $g = $(g);
				let hits = 0;
				$g.find("li").each((_, li) => {
					const hit = !q || $(li).find("a").data("search").includes(q);
					$(li).toggle(hit);
					hits += hit;
				});
				$g.toggle(hits > 0).toggleClass("is-searching", !!q);
				any = any || hits > 0;
			});
			this.$nav.find(".hrd-empty-search").toggle(!any);
		}

		// ------------------------------------------------------------ data
		refresh() {
			const args = { company: this.company };
			if (this.month) Object.assign(args, this.month);
			return frappe.xcall(API + "get_dashboard", args).then((d) => {
				this.data = d;
				this.month = { bs_year: d.period.bs_year, bs_month: d.period.bs_month };
				this.render();
			});
		}

		go(month) {
			this.month = month;
			this.$main.addClass("is-busy");
			this.refresh().finally(() => this.$main.removeClass("is-busy"));
		}

		// ------------------------------------------------------------ page
		render() {
			const d = this.data;
			this.$main.html(`
				${this.header(d)}
				<section class="hrd-kpis">${this.kpis(d)}</section>
				<section class="hrd-grid">
					<div class="hrd-col">
						${this.close_card(d)}
						${this.attendance_card(d)}
						${this.payroll_card(d)}
						${this.headcount_card(d)}
					</div>
					<div class="hrd-col hrd-side">
						${this.due_card(d)}
						${this.actions_card()}
						${this.attention_card(d)}
						${this.decisions_card(d)}
						${this.away_card(d)}
						${this.upcoming_card(d)}
						${this.devices_card(d)}
					</div>
				</section>`);
			this.bind(d);
			this.draw_chart();
		}

		header(d) {
			const p = d.period;
			const first = (frappe.session.user_fullname || "").split(" ")[0];
			const range = `${frappe.datetime.str_to_user(p.start)} – ${frappe.datetime.str_to_user(p.end)}`;
			return `<header class="hrd-head">
				<div>
					<h2>${__("Namaste")}${first ? ", " + esc(first) : ""}</h2>
					<p>${esc(d.today.bs_label)} · ${esc(moment(d.today.date).format("dddd"))}</p>
				</div>
				<div class="hrd-controls">
					<select class="hrd-company" aria-label="${__("Company")}">
						<option value="">${__("All companies")}</option>
						${d.companies.map((c) => `<option ${c === d.company ? "selected" : ""}>${esc(c)}</option>`).join("")}
					</select>
					<div class="hrd-month" role="group" aria-label="${__("BS month")}">
						<button type="button" class="hrd-prev" title="${esc(p.prev.label)}" aria-label="${__("Previous month")}">${icon("chevron", "hrd-flip")}</button>
						<div class="hrd-month-label"><strong>${esc(p.label)}</strong><span>${esc(range)} · ${p.days} ${__("days")}</span></div>
						<button type="button" class="hrd-next" title="${esc(p.next.label)}" aria-label="${__("Next month")}" ${p.can_go_next ? "" : "disabled"}>${icon("chevron")}</button>
					</div>
					<button type="button" class="hrd-refresh" title="${__("Refresh")}" aria-label="${__("Refresh")}">${icon("refresh")}</button>
				</div>
			</header>`;
		}

		kpis(d) {
			const a = d.attendance, h = d.headcount, pay = d.payroll;
			const late_share = a.marked ? Math.round((100 * a.late) / a.marked) : 0;
			const tiles = [
				{ tone: "blue", ic: "people", label: __("Employees"), value: num(h.active),
					sub: `${num(h.women)} ${__("women")} · ${h.joined ? "+" + h.joined + " " + __("joined") : __("no joiners")}`,
					route: ["List", "Employee"], opts: { status: "Active" } },
				{ tone: "green", ic: "check", label: __("Attendance rate"),
					value: a.rate == null ? "—" : a.rate + "%",
					sub: a.marked ? `${num(a.marked)} ${__("days marked")}` : __("Nothing marked yet"),
					route: ["query-report", "Monthly Attendance BS"] },
				{ tone: "amber", ic: "clock", label: __("Late arrivals"), value: num(a.late),
					sub: a.marked ? `${late_share}% ${__("of marked days")}` : "—",
					route: ["List", "Attendance"], opts: { late_entry: 1, docstatus: 1, attendance_date: ["between", [d.period.start, d.period.end]] } },
				{ tone: "violet", ic: "calendar", label: __("Today"), value: num(d.today.punched),
					sub: `${__("punched in")} · ${num(d.today.on_leave)} ${__("on leave")}`,
					route: ["List", "Employee Checkin"] },
				pay && { tone: "rose", ic: "wallet", label: __("Net payroll"), value: pay.slips ? money(pay.net) : "—",
					sub: pay.slips ? `${num(pay.slips)} ${__("slips")}${pay.draft_slips ? " · " + pay.draft_slips + " " + __("draft") : ""}`
						: pay.draft_slips ? `${pay.draft_slips} ${__("draft slips")}` : __("Not run for this month"),
					route: ["List", "Salary Slip"], opts: { start_date: d.period.start } },
			].filter(Boolean);
			this.kpi_routes = tiles;
			return tiles
				.map((t, i) => `<button type="button" class="hrd-card hrd-kpi" data-kpi="${i}">
					<span class="hrd-kpi-icon tone-${t.tone}">${icon(t.ic)}</span>
					<span class="hrd-kpi-label">${t.label}</span>
					<span class="hrd-kpi-value">${t.value}</span>
					<span class="hrd-kpi-sub">${t.sub}</span>
				</button>`)
				.join("");
		}

		// Month close: the steps from punches to the bank, one row per paying company.
		close_card(d) {
			const rows = d.month_close;
			if (!rows || !rows.length) return "";
			const heads = rows[0].steps.map((s) => `<th>${esc(s.label)}</th>`).join("");
			const glyph = { done: "check", draft: "clock", todo: "", none: "" };
			const word = { done: __("Done"), draft: __("Draft"), todo: __("To do"), none: "—" };
			const body = rows
				.map((r) => {
					const done = r.steps.filter((s) => s.state === "done" || s.state === "none").length;
					return `<tr>
						<th scope="row"><strong>${esc(r.abbr)}</strong><small>${done}/${r.steps.length}</small></th>
						${r.steps
							.map((s) => `<td><span class="step step-${s.state}" title="${esc(s.label)}: ${s.state === "none" ? __("nothing this month") : word[s.state]}">
								${glyph[s.state] ? icon(glyph[s.state]) : ""}<b>${s.note ? esc(s.note) : word[s.state]}</b></span></td>`)
							.join("")}
					</tr>`;
				})
				.join("");
			return `<article class="hrd-card">
				<div class="hrd-card-head"><div><h3>${__("Month close")}</h3>
					<p>${__("Where each company is in closing {0}", [esc(d.period.label)])}</p></div>
					<a href="/app/payroll-entry">${__("Payroll entries")} →</a></div>
				<div class="hrd-table-wrap"><table class="hrd-close"><thead><tr><th></th>${heads}</tr></thead><tbody>${body}</tbody></table></div>
			</article>`;
		}

		attendance_card(d) {
			const a = d.attendance;
			const body = a.marked
				? `<div class="hrd-legend">
						<span><i class="sw st-present"></i>${__("Present")} <b>${num(a.totals.Present + (a.totals["Work From Home"] || 0))}</b></span>
						<span><i class="sw st-half"></i>${__("Half day")} <b>${num(a.totals["Half Day"])}</b></span>
						<span><i class="sw st-absent"></i>${__("Absent")} <b>${num(a.totals.Absent)}</b></span>
						${a.totals["On Leave"] ? `<span><i class="sw st-leave"></i>${__("On leave")} <b>${num(a.totals["On Leave"])}</b></span>` : ""}
						<span><i class="sw st-off"></i>${__("Saturday")}</span>
					</div>
					<div class="hrd-chart"><div class="hrd-chart-svg"></div><div class="hrd-tip" role="status"></div></div>`
				: this.empty(__("No attendance marked for {0} yet.", [d.period.label]));
			return `<article class="hrd-card">
				<div class="hrd-card-head"><div><h3>${__("Daily attendance")}</h3>
					<p>${__("Each bar is one day of {0}", [esc(d.period.label)])}</p></div>
					<a href="/app/query-report/Monthly Attendance BS">${__("Open report")} →</a></div>
				${body}
			</article>`;
		}

		// Drawn at the chart's real width so the axis text stays 11px on a phone.
		draw_chart() {
			const $box = this.$main.find(".hrd-chart-svg");
			if (!$box.length) return;
			const paint = () => $box.html(attendance_svg(this.data.attendance.days, Math.max(300, $box.width())));
			paint();
			this.resize && this.resize.disconnect();
			let last = $box.width();
			this.resize = new ResizeObserver(() => {
				if (Math.abs($box.width() - last) > 8) {
					last = $box.width();
					paint();
				}
			});
			this.resize.observe($box[0]);
		}

		payroll_card(d) {
			const p = d.payroll;
			if (!p) return "";
			if (!p.slips) {
				return `<article class="hrd-card">
					<div class="hrd-card-head"><div><h3>${__("Payroll")}</h3><p>${esc(d.period.label)}</p></div>
					<a href="/app/payroll-entry/new">${__("Run payroll")} →</a></div>
					${this.empty(p.draft_slips ? __("{0} salary slips are still in draft.", [p.draft_slips]) : __("Payroll has not been run for {0}.", [d.period.label]))}
				</article>`;
			}
			const max = Math.max(...p.by_cost_center.map((c) => c.amount));
			return `<article class="hrd-card">
				<div class="hrd-card-head"><div><h3>${__("Payroll")}</h3><p>${__("Submitted salary slips, {0}", [esc(d.period.label)])}</p></div>
					<a href="/app/salary-slip?start_date=${d.period.start}">${__("View slips")} →</a></div>
				<div class="hrd-money">
					<div><span>${__("Gross")}</span><strong>${money(p.gross)}</strong></div>
					<div><span>${__("Deductions")}</span><strong>${money(p.deduction)}</strong></div>
					<div class="is-net"><span>${__("Net pay")}</span><strong>${money(p.net)}</strong></div>
				</div>
				<h4>${__("Gross by cost centre")}</h4>
				${this.bar_list(p.by_cost_center.map((c) => ({ label: c.label, value: c.amount, text: money(c.amount) })), max)}
			</article>`;
		}

		headcount_card(d) {
			const rows = d.headcount.by_company;
			if (rows.length < 2) return ""; // one company: the Employees tile already says it
			const max = Math.max(...rows.map((r) => r.count));
			return `<article class="hrd-card">
				<div class="hrd-card-head"><div><h3>${__("Headcount by company")}</h3><p>${__("Active employees")}</p></div></div>
				${this.bar_list(rows.map((r) => ({ label: r.abbr, title: r.company, value: r.count, text: num(r.count) })), max)}
			</article>`;
		}

		bar_list(rows, max) {
			return `<ul class="hrd-bars">${rows
				.map((r) => `<li title="${esc(r.title || r.label)}"><span class="lbl">${esc(r.label)}</span>
					<span class="track"><span class="fill" style="width:${Math.max(2, (100 * r.value) / (max || 1))}%"></span></span>
					<span class="val">${r.text}</span></li>`)
				.join("")}</ul>`;
		}

		// Deadlines the law sets on this month's payroll, soonest first.
		due_card(d) {
			const s = d.statutory;
			if (!s || (!s.deposits.length && !s.dashain)) return "";
			const left = (n) =>
				n < 0 ? `<b class="due due-late">${__("{0} days late", [-n])}</b>`
				: n === 0 ? `<b class="due due-soon">${__("today")}</b>`
				: `<b class="due ${n <= 7 ? "due-soon" : ""}">${__("{0} days", [n])}</b>`;
			const deposits = s.deposits
				.slice()
				.sort((a, b) => a.days_left - b.days_left)
				.map((x) => `<li>${icon("bank")}<span><strong>${esc(x.label)} · ${money(x.amount)}</strong>
					<small>${__("{0} salary, deposit by {1}", [esc(x.for_month), esc(x.due_bs)])}</small></span>${left(x.days_left)}</li>`)
				.join("");
			const dash = s.dashain
				? `<li>${icon("gift")}<span><strong>${__("Dashain allowance")}</strong>
					<small>${s.dashain.pending.length
						? __("Pay before {0} · not yet created for {1}", [esc(s.dashain.deadline_bs), esc(s.dashain.pending.join(", "))])
						: __("Paid for every company")}</small></span>
					${s.dashain.pending.length ? left(s.dashain.days_left) : `<b class="due due-ok">${__("Done")}</b>`}</li>`
				: "";
			return `<article class="hrd-card hrd-due">
				<h3 class="hrd-eyebrow">${__("Due soon")}</h3>
				<ul class="hrd-events">${deposits}${dash}</ul>
				${s.dashain && s.dashain.pending.length ? `<a class="hrd-card-link" href="/app/dashain-bonus/new">${__("Create Dashain bonus")} →</a>` : ""}
			</article>`;
		}

		actions_card() {
			const actions = [
				["calendar", __("Apply leave"), "/app/leave-application/new", "tone-green"],
				["clock", __("Attendance"), "/app/query-report/Monthly Attendance BS", "tone-blue"],
				["wallet", __("Run payroll"), "/app/payroll-entry/new", "tone-rose"],
				["people", __("New employee"), "/app/employee/new", "tone-violet"],
			];
			return `<article class="hrd-card">
				<h3 class="hrd-eyebrow">${__("Quick actions")}</h3>
				<div class="hrd-actions">${actions
					.map(([ic, label, href, tone]) => `<a class="${tone}" href="${href}">${icon(ic)}<span>${label}</span></a>`)
					.join("")}</div>
			</article>`;
		}

		attention_card(d) {
			const gaps = d.gaps.items, queues = d.pending.queues;
			if (!gaps.length && !queues.length) {
				return `<article class="hrd-card"><h3 class="hrd-eyebrow">${__("Needs attention")}</h3>
					<p class="hrd-all-clear">${icon("check")} ${__("Nothing waiting, no setup gaps.")}</p></article>`;
			}
			const queue_rows = queues
				.map((q, i) => `<li><button type="button" data-queue="${i}"><span>${esc(q.label)}</span><b class="pill">${num(q.count)}</b></button></li>`)
				.join("");
			const gap_rows = gaps
				.map((g, i) => `<li><button type="button" data-gap="${i}">
					<span><strong>${esc(g.label)}</strong><small>${esc(g.consequence)}</small></span>
					<span class="gap-count"><b>${num(g.count)}</b><small>/ ${num(d.gaps.active)}</small></span>
					<span class="gap-bar"><i style="width:${(100 * g.count) / (d.gaps.active || 1)}%"></i></span>
				</button></li>`)
				.join("");
			return `<article class="hrd-card">
				<h3 class="hrd-eyebrow">${__("Needs attention")}</h3>
				${queues.length ? `<h4>${__("Waiting for approval")}</h4><ul class="hrd-list">${queue_rows}</ul>` : ""}
				${gaps.length ? `<h4>${icon("alert", "hrd-warn")} ${__("Employee data missing")}</h4><ul class="hrd-list hrd-gaps">${gap_rows}</ul>` : ""}
			</article>`;
		}

		// Probation, contracts and retirements coming up — each needs a decision.
		decisions_card(d) {
			if (!d.decisions.length) return "";
			const when = (n) => (n === 0 ? __("today") : __("in {0} days", [n]));
			const rows = d.decisions
				.slice(0, 6)
				.map((x) => `<li>${icon("user_check", "hrd-decision")}
					<span><a href="/app/employee/${encodeURIComponent(x.employee)}"><strong>${esc(x.employee_name)}</strong></a>
					<small>${esc(x.label)} · ${esc(x.bs)} · ${when(x.in_days)}</small></span></li>`)
				.join("");
			return `<article class="hrd-card"><h3 class="hrd-eyebrow">${__("Decisions due")}</h3>
				<ul class="hrd-events">${rows}</ul>
				${d.decisions.length > 6 ? `<p class="hrd-more">+${d.decisions.length - 6} ${__("more")}</p>` : ""}</article>`;
		}

		away_card(d) {
			if (!d.away.length) return "";
			const rows = d.away
				.slice(0, 6)
				.map((x) => `<li>${icon("away", x.now ? "hrd-away-now" : "hrd-away")}
					<span><a href="/app/leave-application/${encodeURIComponent(x.name)}"><strong>${esc(x.employee_name)}</strong></a>
					<small>${esc(x.leave_type)} · ${esc(x.bs_from)}${x.bs_to !== x.bs_from ? " – " + esc(x.bs_to) : ""}</small></span>
					${x.now ? `<b class="due due-soon">${__("Away now")}</b>` : ""}</li>`)
				.join("");
			return `<article class="hrd-card"><h3 class="hrd-eyebrow">${__("On leave this week")}</h3>
				<ul class="hrd-events">${rows}</ul>
				${d.away.length > 6 ? `<p class="hrd-more">+${d.away.length - 6} ${__("more")}</p>` : ""}</article>`;
		}

		upcoming_card(d) {
			const u = d.upcoming;
			const when = (n) => (n === 0 ? __("today") : n === 1 ? __("tomorrow") : __("in {0} days", [n]));
			const holidays = u.holidays
				.slice(0, 6)
				.map((h) => `<li>${icon("flag", "hrd-holiday")}<span><strong>${esc(h.name)}</strong><small>${esc(h.bs)} · ${when(h.in_days)}</small></span></li>`)
				.join("");
			const people = u.people
				.slice(0, 5)
				.map((p) => `<li>${icon(p.kind === "birthday" ? "cake" : "star", "hrd-" + p.kind)}
					<span><a href="/app/employee/${encodeURIComponent(p.employee)}"><strong>${esc(p.employee_name)}</strong></a>
					<small>${p.kind === "birthday" ? __("Birthday") : __("{0} years with us", [p.years])} · ${esc(p.bs)} · ${when(p.in_days)}</small></span></li>`)
				.join("");
			if (!holidays && !people) return "";
			return `<article class="hrd-card">
				<h3 class="hrd-eyebrow">${__("Next 30 days")}</h3>
				${holidays ? `<h4>${__("Holidays")}</h4><ul class="hrd-events">${holidays}</ul>` : ""}
				${people ? `<h4>${__("Birthdays & anniversaries")}</h4><ul class="hrd-events">${people}</ul>
					${u.people_total > 5 ? `<p class="hrd-more">+${u.people_total - 5} ${__("more in the next 30 days")}</p>` : ""}` : ""}
			</article>`;
		}

		devices_card(d) {
			if (!d.devices.length) return "";
			const rows = d.devices
				.map((dv) => {
					const seen = dv.last_contact_time ? moment(dv.last_contact_time) : null;
					const stale = !seen || moment().diff(seen, "minutes") > (dv.alert_threshold_minutes || 120);
					const state = !dv.enabled ? ["off", __("Disabled")] : stale ? ["bad", __("Silent")] : ["ok", __("Online")];
					return `<li><a href="/app/biometric-device/${encodeURIComponent(dv.name)}">${icon("device")}
						<span><strong>${esc(dv.device_name || dv.name)}</strong><small>${seen ? __("last seen {0}", [seen.fromNow()]) : __("never seen")}</small></span>
						<b class="state state-${state[0]}">${state[1]}</b></a></li>`;
				})
				.join("");
			return `<article class="hrd-card"><h3 class="hrd-eyebrow">${__("Biometric devices")}</h3><ul class="hrd-events hrd-devices">${rows}</ul></article>`;
		}

		empty(text) {
			return `<div class="hrd-empty">${icon("calendar")}<p>${esc(text)}</p></div>`;
		}

		// ------------------------------------------------------------ events
		bind(d) {
			const $m = this.$main;
			$m.find(".hrd-company").on("change", (e) => {
				this.company = e.target.value;
				store({ company: this.company });
				this.go(this.month);
			});
			$m.find(".hrd-prev").on("click", () => this.go({ bs_year: d.period.prev.bs_year, bs_month: d.period.prev.bs_month }));
			$m.find(".hrd-next").on("click", () => this.go({ bs_year: d.period.next.bs_year, bs_month: d.period.next.bs_month }));
			$m.find(".hrd-refresh").on("click", () => this.go(this.month));

			$m.find(".hrd-kpi").on("click", (e) => {
				const t = this.kpi_routes[$(e.currentTarget).data("kpi")];
				const opts = Object.assign({}, t.opts || {});
				if (this.company && t.route[0] === "List" && t.route[1] !== "Employee Checkin") opts.company = this.company;
				frappe.route_options = opts;
				frappe.set_route(...t.route);
			});
			$m.find("[data-queue]").on("click", (e) => {
				const q = d.pending.queues[$(e.currentTarget).data("queue")];
				frappe.route_options = q.filters;
				frappe.set_route("List", q.doctype);
			});
			$m.find("[data-gap]").on("click", (e) => {
				const g = d.gaps.items[$(e.currentTarget).data("gap")];
				if (g.field === "salary_structure_assignment") return frappe.set_route("List", "Salary Structure Assignment");
				const opts = { status: "Active" };
				if (this.company) opts.company = this.company;
				if (g.field !== "date_of_joining") opts[g.field] = ["is", "not set"];
				frappe.route_options = opts;
				frappe.set_route("List", "Employee", "Report");
			});

			// Hover layer on the attendance chart: one tooltip per day column.
			const $chart = $m.find(".hrd-chart");
			const $tip = $chart.find(".hrd-tip");
			$chart.on("mouseenter focusin", ".day", (e) => {
				const day = d.attendance.days[$(e.currentTarget).data("i")];
				const total = day.present + day.half_day + day.absent + day.on_leave;
				$chart.find(".day").removeClass("is-hover");
				$(e.currentTarget).addClass("is-hover");
				$tip.html(`<strong>${esc(d.period.label.split(" ")[0])} ${day.bs_day}</strong>
					<span class="muted">${esc(day.weekday)} · ${frappe.datetime.str_to_user(day.date)}</span>
					${total ? `<span><i class="sw st-present"></i>${__("Present")} <b>${day.present}</b></span>
					<span><i class="sw st-half"></i>${__("Half day")} <b>${day.half_day}</b></span>
					<span><i class="sw st-absent"></i>${__("Absent")} <b>${day.absent}</b></span>
					${day.on_leave ? `<span><i class="sw st-leave"></i>${__("On leave")} <b>${day.on_leave}</b></span>` : ""}`
					: `<span class="muted">${__("Nothing marked")}</span>`}`);
				const box = $chart[0].getBoundingClientRect();
				const col = e.currentTarget.getBoundingClientRect();
				const left = Math.min(box.width - 170, Math.max(0, col.left - box.left + col.width / 2 - 85));
				$tip.css({ left: left + "px" }).addClass("is-shown");
			});
			$chart.on("mouseleave", () => {
				$chart.find(".day").removeClass("is-hover");
				$tip.removeClass("is-shown");
			});
		}
	}

	function attendance_svg(days, W) {
		const H = 220, L = 34, B = 26, T = 8;
		const plot_h = H - B - T;
		const max = Math.max(1, ...days.map((x) => x.present + x.half_day + x.absent + x.on_leave));
		const step = nice_step(max);
		const top = Math.ceil(max / step) * step;
		const bw = (W - L) / days.length;
		const barw = Math.max(3, Math.min(18, bw - 3));
		const y = (v) => T + plot_h - (v / top) * plot_h;
		const every = bw < 14 ? 10 : 5; // fewer day labels when bars are thin
		let grid = "";
		for (let v = 0; v <= top; v += step) {
			grid += `<line x1="${L}" x2="${W}" y1="${y(v)}" y2="${y(v)}" class="${v ? "grid" : "base"}"/>
				<text x="${L - 6}" y="${y(v) + 4}" class="tick" text-anchor="end">${v}</text>`;
		}
		const order = [["present", "st-present"], ["half_day", "st-half"], ["absent", "st-absent"], ["on_leave", "st-leave"]];
		const bars = days
			.map((day, i) => {
				const x = L + i * bw + (bw - barw) / 2;
				let acc = 0;
				const segs = order.filter(([k]) => day[k] > 0);
				const rects = segs
					.map(([k, cls], j) => {
						const y0 = y(acc), y1 = y(acc + day[k]);
						acc += day[k];
						const h = Math.max(0, y0 - y1 - (j ? 2 : 0)); // 2px surface gap between segments
						return `<path class="${cls}" d="${round_top(x, y1, barw, h, j === segs.length - 1 ? 3 : 0)}"/>`;
					})
					.join("");
				const weekend = day.weekday === "Sat" ? `<rect class="off" x="${L + i * bw}" y="${T}" width="${bw}" height="${plot_h}"/>` : "";
				const label = day.bs_day === 1 || day.bs_day % every === 0
					? `<text x="${x + barw / 2}" y="${H - 8}" class="tick" text-anchor="middle">${day.bs_day}</text>` : "";
				return `<g class="day" data-i="${i}">${weekend}${rects}${label}
					<rect class="hit" x="${L + i * bw}" y="${T}" width="${bw}" height="${plot_h}"/></g>`;
			})
			.join("");
		return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${__("Daily attendance")}">${grid}${bars}</svg>`;
	}

	function nice_step(max) {
		const raw = max / 5;
		const pow = Math.pow(10, Math.floor(Math.log10(raw)));
		return [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw) || pow * 10;
	}

	// A bar anchored to the baseline with only its top corners rounded.
	function round_top(x, y, w, h, r) {
		r = Math.min(r, w / 2, h);
		if (!r) return `M${x},${y}h${w}v${h}h${-w}z`;
		return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}z`;
	}

	window.avinash_hr_dashboard = {
		CSS_URL,
		mount(container, opts) {
			return new HRDashboard(container, opts);
		},
	};
})();
