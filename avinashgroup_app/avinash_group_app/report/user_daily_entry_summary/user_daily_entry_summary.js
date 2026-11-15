// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

// User Daily Entry Summary — the front door of the audit trail.
//
// The server returns ordinary report rows (indent 0 = document type, indent 1 =
// document), so Export and Print work as for any report. On screen, though, the
// stock grid made a poor tree: tiny toggles, ticks lost in wide columns, no room
// to show what changed. So the grid is kept but hidden, and the same rows are
// drawn here as expandable document types, with the user's own changes to a
// document shown in a card when it is hovered or focused.

// [fieldname, label, indicator colour] — order is the column order.
const UDES_ACTIONS = [
	["created", "Created", "blue"],
	["amended", "Amended", "orange"],
	["submitted", "Submitted", "green"],
	["edited", "Edited", "yellow"],
	["cancelled", "Cancelled", "red"],
	["deleted", "Deleted", "red"],
];
const UDES_STATUS_COLOUR = { Draft: "gray", Submitted: "green", Cancelled: "red", Deleted: "red" };

// Documents drawn when a type is opened; a month of purchase invoices is in the
// thousands and nobody reads that many rows before searching.
const UDES_PAGE = 200;

frappe.query_reports["User Daily Entry Summary"] = {
	// Always run fresh — never serve a previously generated/cached (prepared) report.
	onload: function (report) {
		report.ignore_prepared_report = true;
	},

	filters: [
		{
			fieldname: "user",
			label: __("User"),
			fieldtype: "Link",
			options: "User",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.now_date(),
			reqd: 1,
		},
		{
			fieldname: "document_type",
			label: __("Document Type"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe
					.call({
						method: "avinashgroup_app.avinash_group_app.report.user_daily_entry_summary.user_daily_entry_summary.get_tracked_doctypes",
						args: { txt: txt },
					})
					.then((r) => r.message || []);
			},
		},
	],

	// Runs after every refresh that returned rows. With no rows the report page
	// hides the whole wrapper, this view included.
	after_datatable_render: function () {
		new UserDailyEntryView(frappe.query_report).render();
	},
};

class UserDailyEntryView {
	constructor(report) {
		this.report = report;
		// which types are open survives a refresh of the same report
		report.udes_open = report.udes_open || new Set();
		this.open = report.udes_open;
	}

	render() {
		const $wrap = this.report.$report;
		$wrap.children(".datatable").hide();
		$wrap.children(".udes").remove();
		this.add_styles();

		this.types = this.group(this.report.data || []);
		this.$root = $(`
			<div class="udes">
				<div class="udes-bar">
					<input type="text" class="form-control udes-search" placeholder="${__(
						"Find a document number"
					)}" aria-label="${__("Find a document number")}">
					<button class="btn btn-default btn-sm udes-expand">${__("Expand all")}</button>
					<button class="btn btn-default btn-sm udes-collapse">${__("Collapse all")}</button>
				</div>
				<div class="udes-scroll"><div class="udes-table">
					<div class="udes-grid udes-head">
						<div>${__("Document Type")}</div>
						<div class="udes-num">${__("All")}</div>
						${UDES_ACTIONS.map((a) => `<div class="udes-num">${__(a[1])}</div>`).join("")}
						<div class="udes-num">${__("Still Draft")}</div>
					</div>
					${this.types.map((t, i) => this.type_html(t, i)).join("")}
				</div></div>
				<div class="udes-card" role="tooltip" hidden></div>
			</div>`).prependTo($wrap);

		this.$card = this.$root.find(".udes-card");
		// The page rebuilds its footer right after this hook returns. Its tree
		// buttons and its ">5, <10" hint both drive the hidden grid, so they
		// would do nothing visible here; the execution time stays.
		setTimeout(() => {
			const $footer = this.report.$report_footer;
			if (!$footer) return;
			$footer.find(".tree-footer").hide();
			$footer.find(".col-md-12 > span").first().hide();
		}, 0);
		this.bind();
		this.types.forEach((t, i) => this.open.has(t.name) && this.toggle(i, true));
	}

	// rows -> [{name, counts, docs: [...]}]
	group(rows) {
		const types = [];
		rows.forEach((row) => {
			if (row.indent === 0) types.push({ name: row.document_type, counts: row, docs: [] });
			// indent === 1 only: when "Add Total Row" is ticked on the Report record
			// the page appends a totals row, which is not a document
			else if (row.indent === 1 && types.length) types[types.length - 1].docs.push(row);
		});
		return types;
	}

	// ------------------------------------------------------------------ html

	// A count; clicking it opens that document type's list, filtered to exactly
	// the documents behind the number.
	num(value, key, extra_class = "") {
		return value
			? `<div class="udes-num ${extra_class}"><a href="#" class="udes-count" data-key="${key}"
				title="${__("Open these documents in the list")}">${value}</a></div>`
			: `<div class="udes-num udes-zero">–</div>`;
	}

	type_html(type, index) {
		const c = type.counts;
		return `
			<div class="udes-type" data-index="${index}">
				<div class="udes-grid udes-type-row" role="button" tabindex="0" aria-expanded="false">
					<div class="udes-type-name">
						<span class="udes-caret">${frappe.utils.icon("right", "xs")}</span>
						${frappe.utils.escape_html(__(type.name))}
					</div>
					${this.num(c.total, "total", "udes-all")}
					${UDES_ACTIONS.map((a) => this.num(c[a[0]], a[0])).join("")}
					${this.num(c.draft, "draft")}
				</div>
				<div class="udes-docs" hidden></div>
			</div>`;
	}

	doc_html(type_index, doc, doc_index) {
		const name = frappe.utils.escape_html(doc.label || "");
		let href = "";
		let hint = "";
		if (doc.deleted_document) {
			// the document is gone; the only thing left to open is its deleted copy
			href = `/app/deleted-document/${encodeURIComponent(doc.deleted_document)}`;
			hint = __("Deleted copy");
		} else if (doc.exists) {
			href = `/app/document-audit-trail/${encodeURIComponent(doc.document_type)}/${encodeURIComponent(
				doc.document_name
			)}`;
			hint = __("Audit trail");
		}
		const pills = UDES_ACTIONS.filter((a) => doc[a[0]])
			.map((a) => `<span class="indicator-pill no-indicator-dot ${a[2]}">${__(a[1])}</span>`)
			.join("");
		const status = doc.status
			? `<span class="indicator-pill ${UDES_STATUS_COLOUR[doc.status] || "gray"}">${__(doc.status)}</span>`
			: "";
		const changes = (doc.changes || []).length + (doc.more_changes || 0);
		const tag = href ? "a" : "div";
		return `
			<${tag} class="udes-doc" ${href ? `href="${href}"` : 'tabindex="0"'}
				data-type="${type_index}" data-doc="${doc_index}">
				<span class="udes-doc-name">${name}</span>
				<span class="udes-pills">${pills}</span>
				<span class="udes-changes">${changes ? __("{0} change(s)", [changes]) : ""}</span>
				<span class="udes-time">${frappe.datetime.str_to_user(doc.first_activity) || ""}</span>
				<span class="udes-status">${status}</span>
				<span class="udes-go">${hint}${hint ? " →" : ""}</span>
			</${tag}>`;
	}

	card_html(doc) {
		const esc = frappe.utils.escape_html;
		const lines = (doc.changes || [])
			.map((c) =>
				c.note
					? `<div class="udes-line"><b>${esc(c.label)}</b> ${esc(c.new)}</div>`
					: `<div class="udes-line"><b>${esc(c.label)}</b>
						<span class="udes-old">${esc(c.old) || __("empty")}</span> →
						<span class="udes-new">${esc(c.new) || __("empty")}</span></div>`
			)
			.join("");
		const more = doc.more_changes
			? `<div class="udes-more">${__("and {0} more, in the audit trail", [doc.more_changes])}</div>`
			: "";
		const body =
			lines ||
			`<div class="udes-more">${
				doc.deleted
					? __("Deleted by this user. Open the deleted copy to see what it held.")
					: __("No field changes by this user in this period.")
			}</div>`;
		return `<div class="udes-card-title">${esc(doc.label || "")}</div>${body}${more}`;
	}

	// ---------------------------------------------------------------- behaviour

	toggle(index, show) {
		const type = this.types[index];
		const $type = this.$root.find(`.udes-type[data-index="${index}"]`);
		const $docs = $type.children(".udes-docs");
		const open = show === undefined ? $docs.prop("hidden") : show;
		if (open && !$docs.data("drawn")) this.draw_docs(index, UDES_PAGE);
		$docs.prop("hidden", !open);
		$type.toggleClass("udes-open", open);
		$type.children(".udes-type-row").attr("aria-expanded", String(open));
		open ? this.open.add(type.name) : this.open.delete(type.name);
	}

	// Draw up to `limit` documents of a type, honouring the search box.
	draw_docs(index, limit) {
		const type = this.types[index];
		const query = (this.query || "").toLowerCase();
		const matches = [];
		type.docs.forEach((doc, i) => {
			if (!query || String(doc.label || "").toLowerCase().includes(query)) matches.push(i);
		});
		const shown = matches.slice(0, limit);
		const rest = matches.length - shown.length;
		const $docs = this.$root.find(`.udes-type[data-index="${index}"] > .udes-docs`);
		$docs
			.html(
				shown.map((i) => this.doc_html(index, type.docs[i], i)).join("") +
					(matches.length ? "" : `<div class="udes-none">${__("No matching documents")}</div>`) +
					(rest > 0
						? `<button class="btn btn-default btn-xs udes-show-all" data-index="${index}">${__(
								"Show {0} more",
								[rest]
						  )}</button>`
						: "")
			)
			.data("drawn", true);
		return matches.length;
	}

	search(query) {
		this.query = query.trim();
		this.types.forEach((type, index) => {
			const $type = this.$root.find(`.udes-type[data-index="${index}"]`);
			if (!this.query) {
				$type.prop("hidden", false);
				$type.children(".udes-docs").data("drawn", false);
				this.toggle(index, this.open.has(type.name));
				return;
			}
			const found = this.draw_docs(index, UDES_PAGE);
			$type.prop("hidden", !found);
			// open the matches without changing what the user had open before
			$type.children(".udes-docs").prop("hidden", !found);
			$type.toggleClass("udes-open", !!found);
		});
	}

	// Open the list view on the documents behind one count. route_options, not
	// a query string: a month of invoices is far too many names for a URL.
	open_list(index, key) {
		const type = this.types[index];
		const live = type.docs
			.filter((d) => d.exists && (key === "total" || d[key]))
			.map((d) => d.document_name);
		if (key === "deleted" || !live.length) {
			// deleted documents have no list of their own; show their saved copies
			const copies = type.docs.map((d) => d.deleted_document).filter(Boolean);
			frappe.route_options = { name: ["in", copies] };
			frappe.set_route("List", "Deleted Document");
			return;
		}
		frappe.route_options = { name: ["in", live] };
		frappe.set_route("List", type.name);
	}

	show_card($doc) {
		const doc = this.types[$doc.data("type")].docs[$doc.data("doc")];
		this.$card.html(this.card_html(doc)).prop("hidden", false);
		// fixed to the viewport: under the row, or above it near the bottom edge
		const row = $doc[0].getBoundingClientRect();
		const card = this.$card[0].getBoundingClientRect();
		const below = row.bottom + 6 + card.height <= window.innerHeight;
		const left = Math.max(8, Math.min(row.left + 24, window.innerWidth - card.width - 8));
		this.$card.css({ left, top: below ? row.bottom + 6 : Math.max(8, row.top - card.height - 6) });
	}

	bind() {
		const $root = this.$root;
		$root.on("click", ".udes-count", (e) => {
			// a count is a link of its own; it must not also fold the row
			e.preventDefault();
			e.stopPropagation();
			const $count = $(e.currentTarget);
			this.open_list($count.closest(".udes-type").data("index"), $count.data("key"));
		});
		$root.on("click", ".udes-type-row", (e) => this.toggle($(e.currentTarget).parent().data("index")));
		$root.on("keydown", ".udes-type-row", (e) => {
			if ($(e.target).closest(".udes-count").length) return;
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				this.toggle($(e.currentTarget).parent().data("index"));
			}
		});
		$root.on("click", ".udes-expand", () => this.types.forEach((t, i) => this.toggle(i, true)));
		$root.on("click", ".udes-collapse", () => this.types.forEach((t, i) => this.toggle(i, false)));
		$root.on("click", ".udes-show-all", (e) => this.draw_docs($(e.currentTarget).data("index"), Infinity));
		$root.on(
			"input",
			".udes-search",
			frappe.utils.debounce((e) => this.search(e.target.value), 200)
		);
		$root.on("mouseenter focusin", ".udes-doc", (e) => this.show_card($(e.currentTarget)));
		$root.on("mouseleave focusout", ".udes-doc", () => this.$card.prop("hidden", true));
	}

	// -------------------------------------------------------------------- style

	add_styles() {
		if (document.getElementById("udes-styles")) return;
		const columns = `minmax(220px, 1fr) repeat(${UDES_ACTIONS.length + 2}, 92px)`;
		const css = `
			.udes { padding: 4px 0 16px; }
			.udes-bar { display: flex; gap: 8px; align-items: center; margin: 0 0 12px; flex-wrap: wrap; }
			.udes-search { max-width: 260px; height: 28px; font-size: var(--text-sm, 12px); }
			.udes-scroll { overflow-x: auto; }
			.udes-table { min-width: 980px; border: 1px solid var(--border-color);
				border-radius: var(--border-radius-md, 8px); overflow: hidden; }
			.udes-grid { display: grid; grid-template-columns: ${columns}; align-items: center;
				column-gap: 8px; padding: 0 16px; }
			.udes-head { height: 36px; background: var(--subtle-fg, var(--bg-color));
				color: var(--text-muted); font-size: var(--text-sm, 12px); font-weight: 500; }
			.udes-num { text-align: right; font-variant-numeric: tabular-nums; }
			.udes-zero { color: var(--text-light, var(--text-muted)); }
			.udes-type { border-top: 1px solid var(--border-color); }
			.udes-type-row { height: 44px; cursor: pointer; user-select: none; }
			.udes-type-row:hover, .udes-type-row:focus-visible { background: var(--subtle-fg, var(--bg-color)); outline: none; }
			.udes-type-row:focus-visible { box-shadow: inset 0 0 0 2px var(--primary, #2490ef); }
			.udes-type-name { font-weight: 600; display: flex; align-items: center; gap: 8px; }
			.udes-all { font-weight: 600; }
			.udes-count { color: inherit; padding: 2px 6px; margin-right: -6px; border-radius: var(--border-radius, 6px); }
			.udes-count:hover, .udes-count:focus-visible { color: var(--primary, #2490ef);
				background: var(--fg-color, #fff); text-decoration: underline; outline: none; }
			.udes-caret { display: inline-flex; transition: transform 120ms ease; color: var(--text-muted); }
			.udes-open > .udes-type-row .udes-caret { transform: rotate(90deg); }
			@media (prefers-reduced-motion: reduce) { .udes-caret { transition: none; } }
			.udes-docs { background: var(--subtle-accent, var(--bg-color)); padding: 6px 16px 10px 40px;
				border-top: 1px solid var(--border-color); }
			.udes-doc { display: grid; grid-template-columns: 220px minmax(200px, 1fr) 100px 150px 110px 110px;
				column-gap: 12px; align-items: center; min-height: 34px; padding: 2px 8px;
				border-radius: var(--border-radius, 6px); color: var(--text-color); font-size: var(--text-sm, 12px); }
			a.udes-doc:hover, .udes-doc:hover, .udes-doc:focus-visible { background: var(--fg-color, #fff);
				text-decoration: none; color: var(--text-color); outline: none;
				box-shadow: 0 0 0 1px var(--border-color); }
			.udes-doc-name { font-weight: 500; overflow-wrap: anywhere; }
			.udes-pills { display: flex; gap: 4px; flex-wrap: wrap; }
			.udes-changes, .udes-time { color: var(--text-muted); font-variant-numeric: tabular-nums; }
			.udes-go { color: var(--text-muted); text-align: right; visibility: hidden; }
			.udes-doc:hover .udes-go, .udes-doc:focus-visible .udes-go { visibility: visible; }
			.udes-none { color: var(--text-muted); padding: 8px; font-size: var(--text-sm, 12px); }
			.udes-show-all { margin: 6px 8px 0; }
			/* pointer-events: none — the card must never sit between the pointer and a row */
			.udes-card { position: fixed; z-index: 1030; pointer-events: none; width: 420px; max-width: calc(100vw - 16px);
				background: var(--modal-bg, var(--fg-color, #fff)); border: 1px solid var(--border-color);
				border-radius: var(--border-radius-md, 8px); box-shadow: var(--shadow-lg, 0 6px 24px rgba(0,0,0,.16));
				padding: 10px 12px; font-size: var(--text-sm, 12px); }
			.udes-card-title { font-weight: 600; margin-bottom: 6px; }
			.udes-line { padding: 2px 0; overflow-wrap: anywhere; }
			.udes-old { text-decoration: line-through; color: var(--text-muted); }
			.udes-new { font-weight: 500; }
			.udes-more { color: var(--text-muted); padding-top: 4px; }
		`;
		$(`<style id="udes-styles">${css}</style>`).appendTo(document.head);
	}
}
