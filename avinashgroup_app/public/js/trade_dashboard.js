// Selling / Buying dashboard — one period of sales or purchases at a glance,
// with that side's menu.
//
// One implementation for both sides; `mode` picks the data:
//   "selling" → Sales Invoices, customers, money received
//   "buying"  → Purchase Invoices, suppliers, money paid
// Mounted at the top of the stock Selling and Buying workspaces by
// public/js/trade_workspace.js.
// Data: avinashgroup_app.sales_purchase.dashboard.get_dashboard / get_menu —
// every figure there is read through frappe.get_list, so it obeys the user's
// role, Company/Branch User Permissions and fiscal-year access.
//
// Usage: avinash_trade_dashboard.mount(element, { mode: "selling" | "buying" })

(function () {
	if (window.avinash_trade_dashboard) return;

	const API = "avinashgroup_app.sales_purchase.dashboard.";
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const num = (v) => format_number(v || 0, null, 0);
	const money = (v) => "Rs " + format_number(Math.round(v || 0), null, 0);

	// Lakh / crore, the way the accounts team reads amounts: Rs 12.48 L, Rs 3.05 Cr.
	function compact(v, prefix = "Rs ") {
		const a = Math.abs(v || 0), sign = v < 0 ? "−" : "";
		let s;
		if (a >= 1e7) s = (a / 1e7).toFixed(a >= 1e9 ? 0 : 2) + " Cr";
		else if (a >= 1e5) s = (a / 1e5).toFixed(2) + " L";
		else if (a >= 1e3) s = (a / 1e3).toFixed(1) + "K";
		else s = String(Math.round(a));
		return sign + prefix + s;
	}

	// Words per side. Everything else on the page is shared.
	const TEXT = {
		selling: {
			hero: __("Net sales"), gross: __("Sales"), returns: __("Sales returns"), paid: __("Money received"),
			party: __("customers"), top_party: __("Top customers"), invoice: "Sales Invoice", item_word: __("sold"),
			// "New order" (Sales Order) left out for now with the Orders menu; to
			// bring it back: ["box", __("New order"), "Sales Order", "/app/sales-order/new"],
			actions: [
				["receipt", __("New invoice"), "Sales Invoice", "/app/sales-invoice/new"],
				["wallet", __("Receive payment"), "Payment Entry", "/app/payment-entry/new?payment_type=Receive&party_type=Customer"],
				["people", __("New customer"), "Customer", "/app/customer/new"],
			],
			report: "Sales Register Report",
		},
		buying: {
			hero: __("Net purchases"), gross: __("Purchases"), returns: __("Purchase returns"), paid: __("Money paid"),
			party: __("suppliers"), top_party: __("Top suppliers"), invoice: "Purchase Invoice", item_word: __("bought"),
			// "New order" (Purchase Order) left out for now; to bring it back:
			// ["box", __("New order"), "Purchase Order", "/app/purchase-order/new"],
			actions: [
				["receipt", __("New invoice"), "Purchase Invoice", "/app/purchase-invoice/new"],
				["truck", __("New receipt"), "Purchase Receipt", "/app/purchase-receipt/new"],
				["people", __("New supplier"), "Supplier", "/app/supplier/new"],
			],
			report: "Purchase Register Report",
		},
	};

	// The Quick actions card (new invoice / payment / customer…) is hidden to
	// keep the dashboard to figures and reports (2026-11-04). Set true to bring
	// it back; the per-side lists in TEXT are unchanged.
	const SHOW_QUICK_ACTIONS = false;

	// Report panel height limits (px): enough to show the filters and a few
	// rows; past the max the report scrolls inside its panel.
	const MIN_REPORT_HEIGHT = 420;
	const MAX_REPORT_HEIGHT = 1400;

	// Branch colours, by the branch's place in the user's branch list — never
	// by rank, so a branch keeps its colour when a filter changes the order.
	// Validated categorical palette, first six slots; "No branch" is grey.
	const SERIES = 6;

	const ICONS = {
		cart: '<path d="M3 4h2.5l2.2 10.5h10.6L20.5 7H6.4"/><circle cx="9.5" cy="19" r="1.4"/><circle cx="17" cy="19" r="1.4"/>',
		chart: '<path d="M4 20V4M4 20h16"/><path d="M8 16v-4M12 16V8M16 16v-6"/>',
		box: '<path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5z"/><path d="M3.5 7.5 12 12l8.5-4.5M12 12v9"/>',
		wallet: '<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M16 14.5h2"/>',
		gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
		bank: '<path d="M3 10 12 4l9 6M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18"/>',
		people: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.3-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/><path d="M16 4.8a3.3 3.3 0 0 1 0 6.4M18 14.8c2 .6 3.2 2.3 3.5 5.2"/>',
		receipt: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6M9 16h3"/>',
		truck: '<path d="M3 6h11v10H3zM14 9h4l3 3.5V16h-7"/><circle cx="7" cy="17.5" r="1.6"/><circle cx="17.5" cy="17.5" r="1.6"/>',
		chevron: '<path d="m9 6 6 6-6 6"/>',
		down: '<path d="m6 9 6 6 6-6"/>',
		search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
		refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"/>',
		plus: '<path d="M12 5v14M5 12h14"/>',
		up: '<path d="M12 19V5M6 11l6-6 6 6"/>',
		dn: '<path d="M12 5v14M6 13l6 6 6-6"/>',
		check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
		table: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17M3.5 14.5h17M9.5 9.5v10"/>',
		bars: '<path d="M6 20V11M12 20V5M18 20v-6"/>',
		branch: '<circle cx="6" cy="6" r="2.2"/><circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="9" r="2.2"/><path d="M6 8.2v7.6M8 17c6 0 10-2.5 10-5.8"/>',
		building: '<path d="M4 21V5l8-2v18M12 8h8v13M8 8h.01M8 12h.01M8 16h.01M16 12h.01M16 16h.01M2.5 21h19"/>',
		tag: '<path d="M3.5 12.5V4.5h8l9 9-8 8z"/><circle cx="8" cy="9" r="1.3"/>',
		clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
	};
	const icon = (name, cls = "") =>
		`<svg class="tdb-icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;

	function store(mode, patch) {
		const key = "trade-dashboard-" + mode;
		let state = {};
		try {
			state = JSON.parse(localStorage.getItem(key) || "{}");
			if (patch) localStorage.setItem(key, JSON.stringify(Object.assign(state, patch)));
		} catch (e) {
			// Storage can be blocked (private window); the page works without it.
		}
		return state;
	}

	// Change against the comparison window, as { text, cls, arrow }.
	// `up_is_good`: true for sales, false for returns, null when neither (purchases).
	function delta(now, before, up_is_good) {
		if (!before) return now ? { text: __("new"), cls: "is-flat", arrow: "" } : null;
		const pct = ((now - before) / Math.abs(before)) * 100;
		if (Math.abs(pct) < 0.5) return { text: "0%", cls: "is-flat", arrow: "" };
		const up = pct > 0;
		const cls = up_is_good == null ? "is-flat" : up === up_is_good ? "is-good" : "is-bad";
		const shown = Math.abs(pct) >= 1000 ? "999+" : Math.abs(pct).toFixed(Math.abs(pct) < 10 ? 1 : 0);
		return { text: shown + "%", cls, arrow: up ? "up" : "dn" };
	}
	const delta_chip = (d) =>
		d ? `<span class="tdb-delta ${d.cls}">${d.arrow ? icon(d.arrow) : ""}${esc(d.text)}</span>` : "";

	class TradeDashboard {
		constructor(container, opts) {
			this.mode = opts.mode;
			this.t = TEXT[this.mode];
			const saved = store(this.mode);
			this.company = saved.company || "";
			this.branch = saved.branch || "";
			this.kind = saved.kind || "month";
			this.period = null; // {bs_year, bs_month} or {fiscal_year}; null = let the server pick
			this.view = "chart";

			this.$root = $(`<div class="tdb mode-${this.mode}">
				<main class="tdb-main"><div class="tdb-loading"><span class="tdb-spinner"></span>${__("Loading…")}</div></main>
				<section class="tdb-card tdb-reports" hidden></section>
			</div>`).appendTo(container);
			this.$main = this.$root.find(".tdb-main");
			this.$reports = this.$root.find(".tdb-reports");
			this.report = null; // the report open in the viewer, by name
			this.load_reports();
			this.refresh();
		}

		// ------------------------------------------------------------ reports
		// The real report runs inside the dashboard, in a frame of the desk's own
		// report page with the desk chrome hidden. It is the same report code
		// running as the same user, so role permission, User Permissions, filters,
		// totals, print and export are exactly those of the report page. The list
		// holds only reports this user's role may open (get_menu checks).
		load_reports() {
			frappe.xcall(API + "get_menu", { mode: this.mode }).then((groups) => {
				this.groups = groups;
				if (!groups.length) return;
				this.$reports.prop("hidden", false).html(`
					<div class="tdb-card-head"><div><h3>${icon("chart", "tdb-h-icon")}${__("Reports")}</h3>
						<p class="tdb-rep-hint">${__("Pick a report — it opens here, with the company and period above")}</p></div>
						<button type="button" class="tdb-rep-toggle" hidden>${icon("table")}<span>${__("All reports")}</span></button></div>
					<div class="tdb-rep">
						<div class="tdb-rep-list">
							<label class="tdb-search">${icon("search")}
								<input type="search" placeholder="${__("Find a report…")}" aria-label="${__("Find a report")}"></label>
							${groups
								.map((g) => `<div class="tdb-rep-group"><h4>${icon(g.icon)}${esc(g.label)}</h4>
									${g.items.map((i) => `<button type="button" data-report="${esc(i.name)}" data-search="${esc((i.label + " " + i.name).toLowerCase())}">${esc(i.label)}</button>`).join("")}
								</div>`)
								.join("")}
						</div>
						<div class="tdb-rep-view">
							<div class="tdb-rep-empty">${icon("chart")}<p>${__("Choose a report on the left to see it here.")}</p></div>
						</div>
					</div>`);
				this.$reports.on("click", "[data-report]", (e) => this.open_report($(e.currentTarget).data("report")));
				// With a report open the list folds away so the report gets the
				// full width; this button brings the list back.
				this.$reports.on("click", ".tdb-rep-toggle", () => this.$reports.find(".tdb-rep").toggleClass("show-list"));
				this.$reports.on("input", "input[type=search]", (e) => {
					const q = e.target.value.trim().toLowerCase();
					this.$reports.find("[data-report]").each((_, b) => $(b).toggle(!q || $(b).data("search").includes(q)));
					this.$reports.find(".tdb-rep-group").each((_, g) => $(g).toggle($(g).find("[data-report]:visible").length > 0));
				});
			});
		}

		// The dashboard's company, branch and period, as filters for the report
		// page. The report page sets only the filters a report actually has and
		// ignores the rest, so every report can be given all of them.
		report_filters() {
			const f = {};
			const p = this.data && this.data.period;
			// "All companies" is not a value a report can take: use the user's
			// only company if they have one, else leave the report's own default.
			const company = this.company || (this.data && this.data.companies.length === 1 ? this.data.companies[0].name : "");
			if (company) f.company = company;
			// Every report here calls its branch filter "branch". "No branch set"
			// has no report equivalent, so it is not sent.
			if (this.branch && this.branch !== "__none__") f.branch = this.branch;
			if (p) {
				f.from_date = p.start;
				f.to_date = p.end;
			}
			return f;
		}

		open_report(name) {
			this.report = name;
			this.$reports.find("[data-report]").removeClass("is-on").filter((_, b) => $(b).data("report") === name).addClass("is-on");
			this.$reports.find(".tdb-rep").addClass("has-report").removeClass("show-list");
			this.$reports.find(".tdb-rep-toggle").prop("hidden", false);
			this.$reports.find(".tdb-rep-hint").text(__("{0} — filtered by the company and period above", [name]));
			const filters = this.report_filters();
			this.report_key = JSON.stringify(filters);
			const url = `/app/query-report/${encodeURIComponent(name)}?${new URLSearchParams(filters).toString()}`;
			const $view = this.$reports.find(".tdb-rep-view").html(`
				<div class="tdb-rep-loading"><span class="tdb-spinner"></span>${__("Opening {0}…", [esc(name)])}</div>
				<iframe class="tdb-rep-frame" title="${esc(name)}" src="${url}"></iframe>`);
			const frame = $view.find("iframe")[0];
			frame.addEventListener("load", () => {
				try {
					this.strip_desk(frame);
				} catch (e) {
					// A cross-origin page (should not happen on the same site) cannot be
					// restyled; it still shows, with the desk bars.
				}
				$view.find(".tdb-rep-loading").remove();
			});
			if (window.innerWidth < 900) this.$reports[0].scrollIntoView({ behavior: "smooth", block: "start" });
		}

		// Hide the desk's navbar and sidebar inside the frame so only the report
		// (its title, filters, table, Print / Export menu) shows. Also keeps the
		// frame on this report: a click that would leave it opens a new tab.
		strip_desk(frame) {
			const doc = frame.contentDocument;
			if (!doc) return;
			const style = doc.createElement("style");
			style.textContent = `
				.navbar, .layout-side-section, .page-head .sidebar-toggle-btn, footer { display: none !important; }
				body { padding-top: 0 !important; background: var(--card-bg) !important; }
				.page-head { position: static !important; top: 0 !important; }
				.page-container, .container { max-width: none !important; }
				.layout-main-section-wrapper { padding: 0 !important; }
				.page-container .container, .page-body.container { padding-left: 12px !important; padding-right: 12px !important; }
				.page-head .container { padding-left: 12px !important; padding-right: 12px !important; }`;
			doc.head.appendChild(style);
			// Grow the frame to the report's own height, so a short report leaves
			// no empty space and a long one needs no scroll bar inside the frame.
			const fit = () => {
				// The page itself is never shorter than the frame, so measure the
				// report's own section instead.
				const main = doc.querySelector(".layout-main-section") || doc.body;
				const h = Math.ceil(main.getBoundingClientRect().bottom + frame.contentWindow.scrollY + 24);
				frame.style.height = Math.max(MIN_REPORT_HEIGHT, Math.min(h, MAX_REPORT_HEIGHT)) + "px";
			};
			new frame.contentWindow.ResizeObserver(fit).observe(doc.body);
			fit();
			doc.documentElement.setAttribute("data-theme", document.documentElement.getAttribute("data-theme") || "light");
			const win = frame.contentWindow;
			const start = win.location.pathname;
			// The desk router changes the URL with pushState; anything that is not
			// this report goes to a new tab and the frame goes back.
			const keep = () => {
				const now = win.location.pathname;
				if (now !== start && !now.startsWith("/app/query-report/")) {
					window.open(win.location.href, "_blank");
					win.history.back();
				}
			};
			win.addEventListener("popstate", keep);
			const push = win.history.pushState.bind(win.history);
			win.history.pushState = function () {
				push.apply(null, arguments);
				keep();
			};
		}

		// After the company or period changes, show the open report for the new one.
		sync_report() {
			if (!this.report) return;
			if (JSON.stringify(this.report_filters()) !== this.report_key) this.open_report(this.report);
		}

		// ------------------------------------------------------------ data
		refresh(force) {
			const args = { mode: this.mode, company: this.company, branch: this.branch, period: this.kind, force: force ? 1 : 0 };
			if (this.period) Object.assign(args, this.period);
			this.$main.addClass("is-busy");
			return frappe
				.xcall(API + "get_dashboard", args)
				.then((d) => {
					this.data = d;
					const p = d.period;
					this.period = p.kind === "year" ? { fiscal_year: p.fiscal_year } : { bs_year: p.bs_year, bs_month: p.bs_month };
					this.render();
					this.sync_report();
				})
				.catch(() => {
					// A saved company/branch the user has lost access to: start clean.
					if (this.company || this.branch) {
						this.company = this.branch = "";
						store(this.mode, { company: "", branch: "" });
						return this.refresh(force);
					}
				})
				.finally(() => this.$main.removeClass("is-busy"));
		}

		go(patch) {
			Object.assign(this, patch);
			store(this.mode, { company: this.company, branch: this.branch, kind: this.kind });
			return this.refresh();
		}

		// ------------------------------------------------------------ page
		render() {
			const d = this.data;
			if (!d.can_read_invoice) {
				this.$main.html(`${this.hero_shell(d, "")}<div class="tdb-card tdb-empty">${icon("receipt")}
					<p>${__("You do not have access to {0}.", [__(this.t.invoice)])}</p></div>`);
				return this.bind();
			}
			this.$main.html(`
				${this.hero_shell(d, this.hero_figures(d))}
				<section class="tdb-kpis">${this.kpis(d)}</section>
				<section class="tdb-grid">
					<div class="tdb-col">
						${this.trend_card(d)}
						${this.split_cards(d)}
						${this.items_card(d)}
					</div>
					<div class="tdb-col tdb-side">
						${this.pipeline_card(d)}
						${this.parties_card(d)}
						${this.actions_card()}
					</div>
				</section>`);
			this.bind();
			this.draw_chart();
		}

		hero_shell(d, figures) {
			const p = d.period;
			const first = (frappe.session.user_fullname || "").split(" ")[0];
			const branches = d.branches.filter((b) => !this.company || b.company === this.company);
			const updated = d.generated_at ? moment(frappe.datetime.convert_to_user_tz(d.generated_at)).fromNow() : "";
			return `<header class="tdb-hero">
				<div class="tdb-hero-top">
					<div class="tdb-hello">
						<span class="tdb-eyebrow">${esc(d.title)}</span>
						<h2>${__("Namaste")}${first ? ", " + esc(first) : ""}</h2>
						<p>${esc(d.today.bs_label)} · ${esc(__(d.today.weekday))}</p>
					</div>
					<div class="tdb-filters">
						<label class="tdb-select">${icon("building")}
							<select class="tdb-company" aria-label="${__("Company")}">
								${d.companies.length > 1 ? `<option value="">${__("All companies")}</option>` : ""}
								${d.companies.map((c) => `<option value="${esc(c.name)}" ${c.name === d.company ? "selected" : ""}>${esc(c.name)}</option>`).join("")}
							</select>
						</label>
						<label class="tdb-select">${icon("branch")}
							<select class="tdb-branch" aria-label="${__("Branch")}">
								<option value="">${__("All branches")}</option>
								${branches.map((b) => `<option value="${esc(b.name)}" ${b.name === d.branch ? "selected" : ""}>${esc(b.label)}${this.company || d.companies.length === 1 ? "" : " · " + esc(b.abbr)}</option>`).join("")}
								<option value="__none__" ${d.branch === "__none__" ? "selected" : ""}>${__("No branch set")}</option>
							</select>
						</label>
						<div class="tdb-seg" role="group" aria-label="${__("Period type")}">
							<button type="button" data-kind="month" class="${p.kind === "month" ? "is-on" : ""}">${__("Month")}</button>
							<button type="button" data-kind="year" class="${p.kind === "year" ? "is-on" : ""}">${__("Fiscal year")}</button>
						</div>
						<div class="tdb-stepper" role="group" aria-label="${__("Period")}">
							<button type="button" class="tdb-prev" ${p.prev ? "" : "disabled"} title="${esc(p.prev ? p.prev.label : "")}" aria-label="${__("Previous")}">${icon("chevron", "tdb-flip")}</button>
							<div class="tdb-period"><strong>${esc(p.label)}</strong>
								<span>${frappe.datetime.str_to_user(p.start)} – ${frappe.datetime.str_to_user(p.end)}</span></div>
							<button type="button" class="tdb-next" ${p.next ? "" : "disabled"} title="${esc(p.next ? p.next.label : "")}" aria-label="${__("Next")}">${icon("chevron")}</button>
						</div>
						<button type="button" class="tdb-refresh" title="${esc(__("Refresh") + (updated ? " · " + __("updated {0}", [updated]) : ""))}" aria-label="${__("Refresh")}">${icon("refresh")}</button>
					</div>
				</div>
				${figures}
			</header>`;
		}

		hero_figures(d) {
			const now = d.totals.now, before = d.totals.before, p = d.period;
			const up_good = this.mode === "selling" ? true : null;
			const progress = p.in_progress ? Math.round((100 * p.elapsed) / p.days) : 100;
			return `<div class="tdb-hero-body">
				<div class="tdb-hero-main">
					<span class="tdb-hero-label">${this.t.hero} · ${esc(p.label)}</span>
					<div class="tdb-hero-value" title="${esc(money(now.net))}">${compact(now.net)}</div>
					<div class="tdb-hero-sub">
						${delta_chip(delta(now.net, before.net, up_good))}
						<span>${__("vs {0}", [esc(p.compare_label)])} (${compact(before.net)})</span>
					</div>
					<div class="tdb-hero-note">${money(now.net)} ${__("excl. VAT")} · ${compact(now.grand)} ${__("incl. VAT")}</div>
				</div>
				<dl class="tdb-hero-stats">
					<div><dt>${__("Bills")}</dt><dd>${num(now.bills)}</dd><small>${now.return_bills ? __("+{0} returns", [num(now.return_bills)]) : __("no returns")}</small></div>
					<div><dt>${__("Parties")}</dt><dd>${num(now.parties)}</dd><small>${this.t.party}</small></div>
					<div><dt>${__("Average bill")}</dt><dd>${compact(now.avg_bill)}</dd><small>${__("per bill")}</small></div>
				</dl>
				${p.in_progress ? `<div class="tdb-progress" title="${esc(__("{0} of {1} days", [p.elapsed, p.days]))}">
					<span style="width:${progress}%"></span><em>${__("Day {0} of {1}", [p.elapsed, p.days])}</em></div>` : ""}
			</div>`;
		}

		kpis(d) {
			const now = d.totals.now, before = d.totals.before;
			const tiles = [
				{ ic: "receipt", tone: "accent", label: this.t.gross, value: compact(now.gross), full: money(now.gross),
					delta: delta(now.gross, before.gross, this.mode === "selling" ? true : null),
					sub: __("{0} bills", [num(now.bills)]) },
				{ ic: "dn", tone: "rose", label: this.t.returns, value: compact(Math.abs(now.returns)), full: money(Math.abs(now.returns)),
					delta: delta(Math.abs(now.returns), Math.abs(before.returns), false),
					sub: now.gross ? __("{0}% of {1}", [((100 * Math.abs(now.returns)) / now.gross).toFixed(1), this.t.gross.toLowerCase()]) : "—" },
				d.paid && { ic: "wallet", tone: "green", label: this.t.paid, value: compact(d.paid.now.amount), full: money(d.paid.now.amount),
					delta: delta(d.paid.now.amount, d.paid.before.amount, this.mode === "selling" ? true : null),
					sub: __("{0} payment entries", [num(d.paid.now.entries)]) + " · " + __("via Payment Entry") },
			].filter(Boolean);
			// Information only — tiles do not open other pages.
			return tiles
				.map((t) => `<div class="tdb-card tdb-kpi tone-${t.tone}" title="${esc(t.full)}">
					<span class="tdb-kpi-top"><span class="tdb-kpi-icon">${icon(t.ic)}</span>${delta_chip(t.delta)}</span>
					<span class="tdb-kpi-label">${t.label}</span>
					<span class="tdb-kpi-value">${t.value}</span>
					<span class="tdb-kpi-sub">${t.sub}</span>
				</div>`)
				.join("");
		}

		// ------------------------------------------------------------ trend
		trend_card(d) {
			const tr = d.trend, p = d.period;
			const has = tr.buckets.some((b) => b.value || b.before);
			const unit = tr.unit === "day" ? __("Each column is one day of {0}", [esc(p.label)]) : __("Each column is one BS month of {0}", [esc(p.label)]);
			const prev_label = p.prev ? p.prev.label : __("previous");
			const best = tr.buckets.reduce((a, b) => (b.value > (a ? a.value : 0) ? b : a), null);
			return `<article class="tdb-card tdb-trend">
				<div class="tdb-card-head">
					<div><h3>${this.mode === "selling" ? __("Sales trend") : __("Purchase trend")}</h3><p>${unit}</p></div>
					<div class="tdb-view" role="group" aria-label="${__("View")}">
						<button type="button" data-view="chart" class="${this.view === "chart" ? "is-on" : ""}" title="${__("Chart")}">${icon("bars")}</button>
						<button type="button" data-view="table" class="${this.view === "table" ? "is-on" : ""}" title="${__("Table")}">${icon("table")}</button>
					</div>
				</div>
				${has ? `<div class="tdb-legend">
						<span><i class="sw sw-now"></i>${esc(p.label)}</span>
						<span><i class="sw sw-prev"></i>${esc(prev_label)}</span>
						${best && best.value > 0 ? `<span class="tdb-best">${__("Best")}: <b>${esc(tr.unit === "day" ? __("day {0}", [best.label]) : best.full_label)}</b> · ${compact(best.value)}</span>` : ""}
					</div>
					<div class="tdb-chart ${this.view === "table" ? "is-hidden" : ""}"><div class="tdb-chart-svg"></div><div class="tdb-tip" role="status"></div></div>
					<div class="tdb-table-wrap ${this.view === "chart" ? "is-hidden" : ""}">${this.trend_table(d)}</div>`
					: this.empty(__("No {0} in {1} yet.", [this.mode === "selling" ? __("sales") : __("purchases"), p.label]))}
			</article>`;
		}

		trend_table(d) {
			const tr = d.trend, p = d.period;
			const rows = tr.buckets
				.filter((b) => !b.future || b.before)
				.map((b) => `<tr><th scope="row">${esc(tr.unit === "day" ? `${b.label} · ${b.weekday}` : b.full_label)}</th>
					<td>${b.future ? "—" : money(b.value)}</td><td>${b.future ? "—" : num(b.bills)}</td>
					<td>${b.before == null ? "—" : money(b.before)}</td></tr>`)
				.join("");
			return `<table class="tdb-table"><thead><tr><th>${tr.unit === "day" ? __("Day") : __("Month")}</th>
				<th>${esc(p.label)}</th><th>${__("Bills")}</th><th>${esc(p.prev ? p.prev.label : __("Previous"))}</th></tr></thead>
				<tbody>${rows}</tbody></table>`;
		}

		// Drawn at the card's real width so axis text stays 11px on a phone.
		draw_chart() {
			const $box = this.$main.find(".tdb-chart-svg");
			if (!$box.length) return;
			const paint = () => $box.html(trend_svg(this.data.trend, Math.max(300, $box.width())));
			paint();
			this.resize && this.resize.disconnect();
			let last = $box.width();
			this.resize = new ResizeObserver(() => {
				if ($box.width() && Math.abs($box.width() - last) > 8) {
					last = $box.width();
					paint();
				}
			});
			this.resize.observe($box[0]);
		}

		// ------------------------------------------------------------ splits
		split_cards(d) {
			const cards = [];
			if (d.by_branch) cards.push(this.branch_card(d));
			if (d.by_company) cards.push(this.company_card(d));
			return cards.length ? `<div class="tdb-pair ${cards.length === 1 ? "is-single" : ""}">${cards.join("")}</div>` : "";
		}

		branch_card(d) {
			const parts = d.by_branch;
			const total = parts.reduce((s, x) => s + Math.max(0, x.value), 0) || 1;
			// Slot by the branch's place in the user's own branch list (stable).
			const order = d.branches.map((b) => b.name);
			const coloured = order.length <= SERIES;
			const slot = (p) => (p.branch === "__none__" ? "none" : coloured ? "s" + (order.indexOf(p.branch) + 1) : "s1");
			const body = coloured
				? `<div class="tdb-stack" role="img" aria-label="${esc(parts.map((p) => `${p.label} ${Math.round((100 * p.value) / total)}%`).join(", "))}">
						${parts.filter((p) => p.value > 0).map((p) => `<span class="seg c-${slot(p)}" style="flex:${p.value}" title="${esc(p.label)} · ${esc(money(p.value))}"></span>`).join("")}
					</div>
					<ul class="tdb-keys">${parts.map((p) => `<li><i class="sw c-${slot(p)}"></i><span>${esc(p.label)}</span>
						<b>${compact(p.value)}</b><small>${Math.round((100 * Math.max(0, p.value)) / total)}%</small></li>`).join("")}</ul>`
				: this.bar_list(parts.map((p) => ({ label: p.label, value: p.value, text: compact(p.value), muted: p.branch === "__none__" })));
			const none = parts.find((p) => p.branch === "__none__");
			return `<article class="tdb-card">
				<div class="tdb-card-head"><div><h3>${icon("branch", "tdb-h-icon")}${__("By branch")}</h3>
				<p>${none && none.value / total > 0.5 ? __("Most bills have no branch set") : __("Share of {0}", [this.t.hero.toLowerCase()])}</p></div></div>
				${body}
			</article>`;
		}

		company_card(d) {
			const parts = d.by_company;
			return `<article class="tdb-card">
				<div class="tdb-card-head"><div><h3>${icon("building", "tdb-h-icon")}${__("By company")}</h3><p>${__("{0}, excl. VAT", [this.t.hero])}</p></div></div>
				${this.bar_list(parts.map((p) => ({ label: p.label, title: p.title, value: p.value, text: compact(p.value), company: p.company })), "company")}
			</article>`;
		}

		bar_list(rows, kind) {
			const max = Math.max(1, ...rows.map((r) => Math.abs(r.value)));
			return `<ul class="tdb-bars">${rows
				.map((r, i) => `<li title="${esc((r.title || r.label) + " · " + money(r.value))}" ${kind ? `data-${kind}="${i}" tabindex="0" role="button"` : ""}>
					<span class="lbl">${esc(r.label)}</span>
					<span class="track"><span class="fill ${r.muted ? "is-muted" : ""}" style="width:${Math.max(1.5, (100 * Math.max(0, r.value)) / max)}%"></span></span>
					<span class="val">${r.text}</span></li>`)
				.join("")}</ul>`;
		}

		items_card(d) {
			const items = d.top_items;
			if (!items.length) return "";
			const total = d.totals.now.gross || items.reduce((s, x) => s + x.value, 0) || 1;
			const rows = items
				.map((it, i) => `<tr>
					<td class="rank">${i + 1}</td>
					<th scope="row">${esc(it.label)}</th>
					<td class="num">${format_number(it.qty, null, it.qty % 1 ? 2 : 0)} <small>${esc(it.uom || "")}</small></td>
					<td class="num">${compact(it.value)}</td>
					<td class="share"><span class="meter"><i style="width:${Math.min(100, (100 * it.value) / total)}%"></i></span>
						<small>${((100 * it.value) / total).toFixed(1)}%</small></td>
				</tr>`)
				.join("");
			return `<article class="tdb-card">
				<div class="tdb-card-head"><div><h3>${icon("tag", "tdb-h-icon")}${__("Top items")}</h3>
					<p>${__("By amount {0} in {1}", [this.t.item_word, esc(d.period.label)])}</p></div></div>
				<div class="tdb-table-wrap"><table class="tdb-table tdb-items"><thead><tr><th></th><th>${__("Item")}</th>
					<th class="num">${__("Qty")}</th><th class="num">${__("Amount")}</th><th>${__("Share")}</th></tr></thead>
					<tbody>${rows}</tbody></table></div>
			</article>`;
		}

		// ------------------------------------------------------------ side
		pipeline_card(d) {
			if (!d.pipeline.length) return "";
			const icons = { Quotation: "receipt", "Sales Order": "box", "Delivery Note": "truck", "Sales Invoice": "receipt",
				"Material Request": "clock", "Purchase Order": "box", "Purchase Receipt": "truck", "Purchase Invoice": "receipt" };
			const waiting = d.pipeline.filter((x) => x.count).length;
			const rows = d.pipeline
				.map((x) => `<li><div class="tdb-row ${x.count ? "" : "is-zero"}">
					<span class="tdb-pipe-icon">${icon(icons[x.doctype] || "receipt")}</span>
					<span class="tdb-pipe-text"><strong>${esc(x.label)}</strong>
						<small>${x.amount ? compact(x.amount) : x.count ? __("{0} documents", [num(x.count)]) : __("Nothing waiting")}${x.in_period ? " · " + __("this period") : ""}${x.all_branches ? " · " + __("all branches") : ""}</small></span>
					<b class="tdb-pill">${num(x.count)}</b></div></li>`)
				.join("");
			return `<article class="tdb-card">
				<div class="tdb-card-head"><div><h3>${__("Waiting for next step")}</h3>
					<p>${waiting ? __("{0} queues need attention", [waiting]) : __("All clear")}</p></div></div>
				<ul class="tdb-pipe">${rows}</ul>
			</article>`;
		}

		parties_card(d) {
			const rows = d.top_parties;
			const head = `<div class="tdb-card-head"><div><h3>${this.t.top_party}</h3>
				<p>${__("By {0}, {1}", [this.t.hero.toLowerCase(), esc(d.period.label)])}</p></div></div>`;
			if (!rows.length) return `<article class="tdb-card">${head}${this.empty(__("Nobody yet this period."))}</article>`;
			const total = d.totals.now.net || 1;
			return `<article class="tdb-card">${head}
				<ol class="tdb-rank">${rows
					.map((r) => `<li><div class="tdb-row" title="${esc(r.label + " · " + money(r.value))}">
						<span class="tdb-avatar">${esc((r.label || "?").trim().charAt(0).toUpperCase())}</span>
						<span class="tdb-rank-text"><strong>${esc(r.label)}</strong>
							<span class="meter"><i style="width:${Math.min(100, (100 * r.value) / rows[0].value)}%"></i></span></span>
						<span class="tdb-rank-val"><b>${compact(r.value)}</b><small>${((100 * r.value) / total).toFixed(1)}% · ${__("{0} bills", [num(r.bills)])}</small></span>
					</div></li>`)
					.join("")}</ol>
			</article>`;
		}

		actions_card() {
			if (!SHOW_QUICK_ACTIONS) return "";
			const actions = this.t.actions.filter(([, , doctype]) => frappe.model.can_create(doctype));
			if (!actions.length) return "";
			return `<article class="tdb-card">
				<h3 class="tdb-eyebrow">${__("Quick actions")}</h3>
				<div class="tdb-actions">${actions
					.map(([ic, label, , href]) => `<a href="${href}">${icon(ic)}<span>${label}</span></a>`)
					.join("")}</div>
			</article>`;
		}

		empty(text) {
			return `<div class="tdb-empty">${icon("chart")}<p>${esc(text)}</p></div>`;
		}

		// ------------------------------------------------------------ events
		bind() {
			const $m = this.$main, d = this.data;
			$m.find(".tdb-company").on("change", (e) => this.go({ company: e.target.value, branch: "" }));
			$m.find(".tdb-branch").on("change", (e) => this.go({ branch: e.target.value }));
			$m.find(".tdb-seg button").on("click", (e) => {
				const kind = $(e.currentTarget).data("kind");
				if (kind !== this.kind) this.go({ kind, period: null });
			});
			$m.find(".tdb-prev").on("click", () => this.go({ period: this.step(d.period.prev) }));
			$m.find(".tdb-next").on("click", () => this.go({ period: this.step(d.period.next) }));
			$m.find(".tdb-refresh").on("click", () => this.refresh(true));
			$m.find(".tdb-view button").on("click", (e) => {
				this.view = $(e.currentTarget).data("view");
				$m.find(".tdb-view button").removeClass("is-on").filter(`[data-view=${this.view}]`).addClass("is-on");
				$m.find(".tdb-chart").toggleClass("is-hidden", this.view !== "chart");
				$m.find(".tdb-trend .tdb-table-wrap").toggleClass("is-hidden", this.view !== "table");
				if (this.view === "chart") this.draw_chart();
			});

			// Clicking a company bar narrows this dashboard to it; nothing here
			// opens another page.
			$m.find("[data-company]").on("click keydown", (e) => {
				if (e.type === "keydown" && e.key !== "Enter") return;
				this.go({ company: d.by_company[$(e.currentTarget).data("company")].company, branch: "" });
			});

			// Hover layer on the trend chart: one tooltip per column.
			const $chart = $m.find(".tdb-chart");
			const $tip = $chart.find(".tdb-tip");
			const tr = d.trend;
			$chart.on("mouseenter focusin", ".col", (e) => {
				const b = tr.buckets[$(e.currentTarget).data("i")];
				$chart.find(".col").removeClass("is-hover");
				$(e.currentTarget).addClass("is-hover");
				const title = tr.unit === "day"
					? `${esc(d.period.label.split(" ")[0])} ${b.label} <span class="muted">· ${esc(b.weekday)} · ${frappe.datetime.str_to_user(b.date)}</span>`
					: esc(b.full_label);
				const dl = !b.future && b.before ? delta(b.value, b.before, this.mode === "selling" ? true : null) : null;
				$tip.html(`<strong>${title}</strong>
					${b.future ? `<span class="muted">${__("Not reached yet")}</span>`
						: `<span><i class="sw sw-now"></i>${esc(d.period.label)} <b>${money(b.value)}</b></span>
						<span class="muted">${__("{0} bills", [num(b.bills)])}</span>`}
					${b.before != null ? `<span><i class="sw sw-prev"></i>${esc(d.period.prev ? d.period.prev.label : __("Previous"))} <b>${money(b.before)}</b></span>` : ""}
					${dl ? `<span>${delta_chip(dl)}</span>` : ""}`);
				const box = $chart[0].getBoundingClientRect();
				const col = e.currentTarget.getBoundingClientRect();
				const left = Math.min(box.width - 210, Math.max(0, col.left - box.left + col.width / 2 - 105));
				$tip.css({ left: left + "px" }).addClass("is-shown");
			});
			$chart.on("mouseleave focusout", () => {
				$chart.find(".col").removeClass("is-hover");
				$tip.removeClass("is-shown");
			});
		}

		step(target) {
			if (!target) return this.period;
			return this.kind === "year" ? { fiscal_year: target.fiscal_year } : { bs_year: target.bs_year, bs_month: target.bs_month };
		}

		destroy() {
			this.resize && this.resize.disconnect();
		}
	}

	// Columns for this period, a 2px line for the previous one, on one axis.
	function trend_svg(tr, W) {
		const b = tr.buckets;
		const H = 250, L = 56, R = 6, B = 26, T = 12;
		const plot_h = H - B - T;
		const vals = b.flatMap((x) => [x.future ? 0 : x.value, x.before || 0]);
		const hi = Math.max(1, ...vals);
		let lo = Math.min(0, ...vals);
		// A month with only a few returns dips just below zero; don't give the
		// whole axis a negative band for it. The bar is clamped to the baseline.
		if (lo > -hi * 0.03) lo = 0;
		const step = nice_step(hi - lo);
		const top = Math.ceil(hi / step) * step, bottom = Math.floor(lo / step) * step;
		const y = (v) => T + plot_h - ((v - bottom) / (top - bottom || 1)) * plot_h;
		const bw = (W - L - R) / b.length;
		const barw = Math.max(3, Math.min(24, bw - 2 - bw * 0.25));
		const every = tr.unit === "month" ? 1 : bw < 14 ? 5 : bw < 22 ? 2 : 1;

		let grid = "";
		for (let v = bottom; v <= top + step / 2; v += step) {
			grid += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="${v === 0 ? "base" : "grid"}"/>
				<text x="${L - 8}" y="${y(v) + 4}" class="tick" text-anchor="end">${v === 0 ? "0" : axis_label(v)}</text>`;
		}
		const cx = (i) => L + i * bw + bw / 2;
		const cols = b
			.map((x, i) => {
				const x0 = cx(i) - barw / 2;
				const v = x.future ? 0 : x.value;
				const shown = Math.max(v, bottom); // clamp a dip the axis does not show
				const bar = shown ? `<path class="bar" d="${bar_path(x0, y(0), y(shown), barw, 4)}"/>` : "";
				const label = i % every === 0 || i === b.length - 1
					? `<text x="${cx(i)}" y="${H - 8}" class="tick" text-anchor="middle">${esc(x.label)}</text>` : "";
				return `<g class="col ${x.future ? "is-future" : ""}" data-i="${i}" tabindex="0" aria-label="${esc(x.full_label || x.label)}: ${esc(money(v))}">
					<rect class="hover-band" x="${L + i * bw}" y="${T}" width="${bw}" height="${plot_h}"/>${bar}${label}
					${x.before != null ? `<circle class="dot" cx="${cx(i)}" cy="${y(x.before)}" r="4"/>` : ""}
					<rect class="hit" x="${L + i * bw}" y="${T}" width="${bw}" height="${plot_h + B}"/></g>`;
			})
			.join("");
		const pts = b.map((x, i) => (x.before == null ? null : `${cx(i).toFixed(1)},${y(x.before).toFixed(1)}`)).filter(Boolean);
		const line = pts.length > 1 ? `<polyline class="prev" points="${pts.join(" ")}"/>` : "";
		return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${__("Trend")}">${grid}${line}${cols}</svg>`;
	}

	// Axis ticks are round numbers: "80 Cr", "2.5 L", not "80.00 Cr".
	function axis_label(v) {
		return compact(v, "").replace(/\.0+(?= |K|$)/, "").replace(/(\.\d*?)0+(?= |K|$)/, "$1");
	}

	function nice_step(range) {
		const raw = range / 5 || 1;
		const pow = Math.pow(10, Math.floor(Math.log10(raw)));
		return [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw) || pow * 10;
	}

	// A column from the baseline (y0) to its value (y1), rounded only at the
	// data end — the top for a positive value, the bottom for a negative one.
	function bar_path(x, y0, y1, w, r) {
		const h = Math.abs(y0 - y1);
		r = Math.min(r, w / 2, h);
		if (y1 <= y0) {
			// positive: grows up
			return `M${x},${y0}V${y1 + r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + r}V${y0}z`;
		}
		return `M${x},${y0}V${y1 - r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 - r}V${y0}z`;
	}

	window.avinash_trade_dashboard = {
		mount(container, opts) {
			return new TradeDashboard(container, opts);
		},
	};
})();
