// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

// Document Audit Trail — /app/document-audit-trail/<doctype>/<name>
//
// Draws one document in its own form layout (sections, columns, tabs and labels
// come straight from the doctype's field list, so nothing here is hand-laid-out
// per doctype) and hangs each field's earlier values under the current one.
// Everything is read-only: controls are never bound to a real document, so
// nothing on this page can save. Data comes from document_audit_trail.py.

frappe.pages["document-audit-trail"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Document Audit Trail"),
		single_column: true,
	});
	wrapper.audit_trail = new DocumentAuditTrail(page);
};

frappe.pages["document-audit-trail"].on_page_show = function (wrapper) {
	wrapper.audit_trail && wrapper.audit_trail.load_from_route();
};

const DAT_API =
	"avinashgroup_app.avinash_group_app.page.document_audit_trail.document_audit_trail.get_document_history";

// History lines shown under a field before "show older" is needed.
const DAT_VISIBLE_HISTORY = 3;
// A child table wider than this stops being readable; in_list_view columns come
// first, then columns that only appear because one of their cells changed.
const DAT_MAX_COLUMNS = 10;

const DAT_TABLE_TYPES = ["Table", "Table MultiSelect"];
// Field types that draw nothing useful without the live form behind them.
const DAT_SKIP_TYPES = ["Button", "HTML", "Geolocation", "Signature", "Barcode"];

// A FieldGroup that can draw Tab Breaks without a live form.
//
// Frappe's Tab (frappe/public/js/frappe/form/tab.js) takes its element ids from
// frm.doctype and calls frm.set_active_tab() when a tab is shown, so a tabbed
// doctype in a plain FieldGroup throws while the layout is still being built.
// The layout's `frm` is lent to each Tab for the length of its construction
// only, so no control ever sees it and nothing can reach a real document.
class DatLayout extends frappe.ui.FieldGroup {
	make_tab(df) {
		this.frm = {
			// prefixed so the ids differ from the real form's tabs, which may be
			// open in another desk page at the same time
			doctype: `dat ${this.dat_doctype}`,
			set_active_tab() {},
			get_perm: () => true,
		};
		try {
			return super.make_tab(df);
		} finally {
			this.frm = undefined;
		}
	}
}

class DocumentAuditTrail {
	constructor(page) {
		this.page = page;
		this.loaded = null;
		this.add_styles();
		this.make_pickers();
		this.$body = $('<div class="dat-body"></div>').appendTo(this.page.main);
		this.show_empty();
	}

	make_pickers() {
		this.doctype_field = this.page.add_field({
			fieldtype: "Link",
			fieldname: "doctype",
			label: __("Document Type"),
			options: "DocType",
			get_query: () => ({ filters: { istable: 0, issingle: 0 } }),
			change: () => {
				const doctype = this.doctype_field.get_value();
				if (doctype === this.name_field.df.options) return;
				this.name_field.df.options = doctype || "";
				this.name_field.set_value("");
			},
		});
		this.name_field = this.page.add_field({
			fieldtype: "Link",
			fieldname: "docname",
			label: __("Document"),
			options: "",
			change: () => {
				const doctype = this.doctype_field.get_value();
				const name = this.name_field.get_value();
				if (doctype && name && this.loaded !== `${doctype}::${name}`) {
					frappe.set_route("document-audit-trail", doctype, name);
				}
			},
		});
	}

	load_from_route() {
		const route = frappe.get_route();
		const doctype = route[1];
		// document names can contain "/" (NGI/82-83/0001), which the router splits
		const name = route.slice(2).join("/");
		if (!doctype || !name) return;
		if (this.loaded === `${doctype}::${name}`) return;
		this.loaded = `${doctype}::${name}`;

		this.name_field.df.options = doctype;
		this.doctype_field.set_value(doctype);
		this.name_field.set_value(name);

		this.$body.html(`<div class="dat-note">${__("Loading")}…</div>`);
		frappe.model.with_doctype(doctype, () => {
			frappe
				.call({ method: DAT_API, args: { doctype, name } })
				.then((r) => this.render(doctype, name, r.message))
				.catch(() => {
					this.loaded = null;
					this.$body.html(
						`<div class="dat-note">${__("This document could not be loaded.")}</div>`
					);
				});
		});
	}

	show_empty() {
		this.$body.html(
			`<div class="dat-note">${__(
				"Choose a document type and a document to see it with its recorded changes."
			)}</div>`
		);
	}

	// ---------------------------------------------------------------- render

	render(doctype, name, data) {
		this.doctype = doctype;
		this.data = data;
		this.meta = frappe.get_meta(doctype);
		this.$body.empty();
		this.page.set_title(`${__(doctype)}: ${name}`);

		this.render_summary(name);
		this.render_form();
		this.render_timeline();
	}

	render_summary(name) {
		const d = this.data;
		const edits = d.steps.filter((s) => s.kind !== "Created");
		const users = new Set(edits.map((s) => s.user));
		const notes = [];
		if (!d.tracked) {
			notes.push(
				__("Change tracking is off for {0}, so edits to it are not being recorded.", [
					__(this.doctype),
				])
			);
		}
		if (d.truncated) {
			notes.push(__("Only the most recent recorded changes are shown."));
		}
		const count = edits.length
			? __("{0} recorded changes by {1} user(s)", [edits.length, users.size])
			: __("No recorded changes");
		this.$body.append(`
			<div class="dat-summary">
				<div>
					<span class="dat-count">${count}</span>
					<span class="dat-legend"><span class="dat-swatch"></span>${__(
						"marks a value that was changed; earlier values are listed under it"
					)}</span>
				</div>
				<a href="${frappe.utils.get_form_link(this.doctype, name)}">${__("Open document")}</a>
			</div>
			${notes.map((n) => `<div class="dat-note dat-warn">${n}</div>`).join("")}
			<div class="dat-note">${__(
				"History covers changes saved from the screen since change tracking was switched on. Long text fields are not compared."
			)}</div>
		`);
	}

	render_form() {
		const doc = this.data.doc;
		const fields = this.meta.fields.map((src) => this.display_field(src, doc));
		const $form = $('<div class="dat-form"></div>').appendTo(this.$body);
		this.form = new DatLayout({ fields, body: $form[0], dat_doctype: this.doctype });
		this.form.make();

		fields.forEach((df) => {
			const control = this.form.fields_dict[df.fieldname];
			if (!control || df.hidden) return;
			if (df.dat_table) {
				control.$wrapper.html(this.table_html(df.dat_table, doc[df.fieldname] || []));
				return;
			}
			if (!control.df.fieldname || !frappe.model.is_value_type(df.fieldtype)) return;
			// set the value directly: set_value() would validate every Link over the network
			control.value = doc[df.fieldname];
			control.refresh();
			const history = this.data.field_history[df.fieldname];
			if (history) {
				control.$wrapper.addClass("dat-changed").append(this.history_html(history, df, doc));
			}
		});

		$form.on("click", ".dat-more", function () {
			$(this).closest(".dat-history").find(".dat-older").removeClass("hidden");
			$(this).remove();
		});
		$form.on("click", "tr.dat-has-history", function () {
			$(this).next(".dat-row-history").toggleClass("hidden");
		});
	}

	// One doctype field, turned into a read-only field for display.
	display_field(src, doc) {
		const df = Object.assign({}, src);
		const history = this.data.field_history[src.fieldname];
		df.read_only = 1;
		df.reqd = 0;
		df.collapsible = 0;
		df.hidden = this.is_hidden(src, doc, history) ? 1 : 0;
		// already evaluated in is_hidden(); left in place they would run against
		// a FieldGroup that has no real document behind it
		[
			"depends_on",
			"mandatory_depends_on",
			"read_only_depends_on",
			"collapsible_depends_on",
			"onchange",
			"fetch_from",
		].forEach((key) => delete df[key]);

		if (DAT_TABLE_TYPES.includes(src.fieldtype)) {
			df.dat_table = src;
			df.fieldtype = "HTML";
			df.options = "";
		}
		return df;
	}

	is_hidden(src, doc, history) {
		if (DAT_SKIP_TYPES.includes(src.fieldtype)) return true;
		if (src.hidden) return true;
		if (!frappe.model.is_value_type(src.fieldtype)) {
			if (DAT_TABLE_TYPES.includes(src.fieldtype)) {
				const removed = this.data.rows_removed[src.fieldname];
				return !(doc[src.fieldname] || []).length && !removed;
			}
			// Section / Column / Tab Break: honour depends_on, otherwise show
			return !this.depends_on_ok(src, doc);
		}
		if (!this.depends_on_ok(src, doc)) return true;
		// the form hides empty read-only fields; keep one if it has a history
		const value = doc[src.fieldname];
		const empty = value === null || value === undefined || value === "";
		return empty && !history;
	}

	depends_on_ok(src, doc) {
		const expression = src.depends_on;
		if (!expression) return true;
		if (expression.startsWith("eval:")) {
			try {
				return !!frappe.utils.eval(expression.slice(5), { doc, parent: doc });
			} catch (e) {
				// expressions written for the live form (cur_frm, ...) cannot run here;
				// showing the field is the safe side for an audit screen
				return true;
			}
		}
		if (expression.startsWith("fn:")) return true;
		const value = doc[expression];
		return Array.isArray(value) ? value.length > 0 : !!value;
	}

	// ------------------------------------------------------------ formatting

	format(value, df, doc) {
		if (value === null || value === undefined || value === "") {
			return `<span class="dat-empty">${__("empty")}</span>`;
		}
		if (!df) return frappe.utils.escape_html(String(value));
		return frappe.format(value, df, { inline: true, only_value: true }, doc) || "";
	}

	who_when(entry) {
		const user = frappe.utils.escape_html(frappe.user.full_name(entry.user) || entry.user);
		return `${user} · ${frappe.datetime.str_to_user(entry.when)}`;
	}

	history_html(history, df, doc) {
		const line = (h, index) => `
			<div class="dat-line ${index >= DAT_VISIBLE_HISTORY ? "dat-older hidden" : ""}">
				<span class="dat-old">${this.format(h.old, df, doc)}</span>
				<span class="dat-arrow">→</span>
				<span class="dat-new">${this.format(h.new, df, doc)}</span>
				<span class="dat-meta">${this.who_when(h)}</span>
			</div>`;
		const extra = history.length - DAT_VISIBLE_HISTORY;
		const more =
			extra > 0 ? `<a class="dat-more">${__("Show {0} older", [extra])}</a>` : "";
		return `<div class="dat-history">${history.map(line).join("")}${more}</div>`;
	}

	// ----------------------------------------------------------- child tables

	table_html(table_df, rows) {
		const child_meta = frappe.get_meta(table_df.options);
		const fieldname = table_df.fieldname;
		const row_history = this.data.row_history[fieldname] || {};
		const added = {};
		(this.data.rows_added[fieldname] || []).forEach((a) => (added[a.row.name] = a));
		const removed = this.data.rows_removed[fieldname] || [];

		const changed_fields = new Set();
		Object.values(row_history).forEach((list) =>
			list.forEach((h) => changed_fields.add(h.fieldname))
		);
		const value_fields = child_meta.fields.filter(
			(f) => frappe.model.is_value_type(f.fieldtype) && !f.hidden
		);
		const columns = value_fields
			.filter((f) => f.in_list_view)
			.concat(value_fields.filter((f) => !f.in_list_view && changed_fields.has(f.fieldname)))
			.slice(0, DAT_MAX_COLUMNS);
		const df_by_name = {};
		child_meta.fields.forEach((f) => (df_by_name[f.fieldname] = f));

		const head = columns.map((c) => `<th>${__(c.label || c.fieldname)}</th>`).join("");
		const body_row = (row, cls) =>
			columns
				.map((c) => {
					const changed = (row_history[row.name] || []).some((h) => h.fieldname === c.fieldname);
					return `<td class="${changed && !cls ? "dat-cell-changed" : ""}">${this.format(
						row[c.fieldname],
						c,
						row
					)}</td>`;
				})
				.join("");

		const live = rows
			.map((row) => {
				const history = row_history[row.name];
				const add = added[row.name];
				const badge = add
					? `<span class="dat-badge dat-added" title="${this.who_when(add)}">${__("added")}</span>`
					: "";
				const edited = history
					? `<span class="dat-badge dat-edited" title="${__("Click the row to see what changed")}">${__(
							"{0} change(s)",
							[history.length]
					  )}</span>`
					: "";
				let html = `<tr class="${history ? "dat-has-history" : ""}">
					<td class="dat-idx">${row.idx}${badge}${edited}</td>${body_row(row)}</tr>`;
				if (history) {
					const lines = history
						.map(
							(h) => `<div class="dat-line">
								<b>${__((df_by_name[h.fieldname] || {}).label || h.fieldname)}</b>
								<span class="dat-old">${this.format(h.old, df_by_name[h.fieldname], row)}</span>
								<span class="dat-arrow">→</span>
								<span class="dat-new">${this.format(h.new, df_by_name[h.fieldname], row)}</span>
								<span class="dat-meta">${this.who_when(h)}</span>
							</div>`
						)
						.join("");
					html += `<tr class="dat-row-history hidden"><td colspan="${columns.length + 1}">
						<div class="dat-history">${lines}</div></td></tr>`;
				}
				return html;
			})
			.join("");

		const gone = removed
			.map(
				(r) => `<tr class="dat-removed-row">
					<td class="dat-idx">${r.row.idx || ""}<span class="dat-badge dat-removed">${__(
					"removed"
				)}</span></td>${body_row(r.row, "removed")}</tr>
				<tr class="dat-row-history"><td colspan="${columns.length + 1}">
					<span class="dat-meta">${__("Removed by")} ${this.who_when(r)}</span></td></tr>`
			)
			.join("");

		return `
			<div class="dat-table-label">${__(table_df.label || fieldname)}</div>
			<div class="dat-table-wrap"><table class="table table-bordered dat-table">
				<thead><tr><th class="dat-idx">${__("No.")}</th>${head}</tr></thead>
				<tbody>${live}${gone}</tbody>
			</table></div>`;
	}

	// --------------------------------------------------------------- timeline

	render_timeline() {
		const doc = this.data.doc;
		const label = (fieldname) => {
			const df = frappe.meta.get_docfield(this.doctype, fieldname);
			return __((df && df.label) || fieldname);
		};
		const events = this.data.steps.map((s) => ({ ...s }));
		this.data.prints.forEach((p) =>
			events.push({
				kind: "Printed",
				user: p.printed_by || p.owner,
				when: p.creation,
				changed: [],
				rows: [],
				note: p.copy_number ? __("copy {0}", [p.copy_number]) : "",
			})
		);
		events.sort((a, b) => (a.when < b.when ? -1 : a.when > b.when ? 1 : 0));

		const items = events
			.map((e) => {
				const fields = e.changed
					.map((c) => {
						const df = frappe.meta.get_docfield(this.doctype, c.fieldname);
						return `<div class="dat-line"><b>${label(c.fieldname)}</b>
							<span class="dat-old">${this.format(c.old, df, doc)}</span>
							<span class="dat-arrow">→</span>
							<span class="dat-new">${this.format(c.new, df, doc)}</span></div>`;
					})
					.join("");
				// one line per table and action: "Items: 4 rows removed", not four lines
				const tally = {};
				e.rows.forEach((r) => {
					const key = `${r.table}::${r.action}`;
					tally[key] = tally[key] || { table: r.table, action: r.action, rows: 0, values: 0 };
					tally[key].rows += 1;
					tally[key].values += r.count || 0;
				});
				const rows = Object.values(tally)
					.map((t) => {
						const what =
							t.action === "changed"
								? __("{0} row(s) changed ({1} value(s))", [t.rows, t.values])
								: t.action === "added"
								? __("{0} row(s) added", [t.rows])
								: __("{0} row(s) removed", [t.rows]);
						return `<div class="dat-line"><b>${label(t.table)}</b> ${what}</div>`;
					})
					.join("");
				const acting = e.impersonated_by
					? ` <span class="dat-meta">(${__("impersonated by")} ${frappe.utils.escape_html(
							e.impersonated_by
					  )})</span>`
					: "";
				return `<div class="dat-event">
					<div class="dat-event-head">
						<span class="dat-kind dat-kind-${e.kind.toLowerCase()}">${__(e.kind)}</span>
						${e.note ? `<span>${e.note}</span>` : ""}
						<span class="dat-meta">${this.who_when(e)}</span>${acting}
					</div>${fields}${rows}</div>`;
			})
			.join("");

		this.$body.append(`
			<div class="dat-timeline">
				<h5>${__("Full history, oldest first")}</h5>
				${items}
			</div>`);
	}

	// ------------------------------------------------------------------ style

	add_styles() {
		if (document.getElementById("dat-styles")) return;
		const css = `
			.dat-body { padding: 0 var(--padding-md, 15px) 40px; }
			.dat-summary { display: flex; justify-content: space-between; align-items: center;
				flex-wrap: wrap; gap: 8px; padding: 12px 0; }
			.dat-count { font-weight: 600; margin-right: 16px; }
			.dat-legend, .dat-meta, .dat-empty { color: var(--text-muted); font-size: var(--text-sm, 12px); }
			.dat-swatch { display: inline-block; width: 10px; height: 10px; margin-right: 6px;
				border-left: 3px solid var(--orange-500, #e86c13); background: var(--bg-orange, #fff1e7); }
			.dat-note { color: var(--text-muted); padding: 6px 0; font-size: var(--text-sm, 12px); }
			.dat-warn { color: var(--orange-600, #c45a0e); }
			.dat-form { border: 1px solid var(--border-color); border-radius: var(--border-radius-md, 8px);
				background: var(--card-bg, var(--fg-color)); margin-top: 8px; }
			.dat-changed { border-left: 3px solid var(--orange-500, #e86c13); padding-left: 8px; }
			.dat-history { margin: 2px 0 10px; font-size: var(--text-sm, 12px); }
			.dat-line { padding: 2px 0; overflow-wrap: anywhere; }
			.dat-old { text-decoration: line-through; color: var(--text-muted); }
			.dat-new { font-weight: 500; }
			.dat-arrow { color: var(--text-muted); margin: 0 4px; }
			.dat-line .dat-meta { margin-left: 8px; }
			/* under a field the column can be narrow: who and when get their own line */
			.dat-changed > .dat-history .dat-meta { display: block; margin-left: 0; }
			.dat-edited { background: var(--bg-orange, #fff1e7); color: var(--orange-700, #9a4a0c); }
			.dat-more { cursor: pointer; font-size: var(--text-sm, 12px); }
			.dat-table-label { font-size: var(--text-sm, 12px); color: var(--text-muted); margin-bottom: 4px; }
			.dat-table-wrap { overflow-x: auto; }
			.dat-table { font-size: var(--text-sm, 12px); margin-bottom: 12px; }
			.dat-table th { white-space: nowrap; color: var(--text-muted); font-weight: 500; }
			.dat-idx { width: 1%; white-space: nowrap; }
			.dat-cell-changed { background: var(--bg-orange, #fff1e7);
				box-shadow: inset 3px 0 0 var(--orange-500, #e86c13); }
			tr.dat-has-history { cursor: pointer; }
			tr.dat-row-history > td { background: var(--subtle-fg, var(--bg-color)); padding: 4px 12px; }
			tr.dat-removed-row td { text-decoration: line-through; color: var(--text-muted); }
			tr.dat-removed-row td.dat-idx { text-decoration: none; }
			.dat-badge { margin-left: 6px; padding: 0 6px; border-radius: 8px; font-size: 11px; }
			.dat-added { background: var(--bg-green, #e4f5e9); color: var(--green-700, #16794c); }
			.dat-removed { background: var(--bg-red, #fff0f0); color: var(--red-600, #b52a2a); }
			.dat-timeline { margin-top: 28px; }
			.dat-event { border-left: 2px solid var(--border-color); padding: 4px 0 10px 12px; }
			.dat-event-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; }
			.dat-kind { font-weight: 600; }
			.dat-kind-submitted { color: var(--green-700, #16794c); }
			.dat-kind-cancelled { color: var(--red-600, #b52a2a); }
			.dat-event .dat-line { font-size: var(--text-sm, 12px); }
		`;
		$(`<style id="dat-styles">${css}</style>`).appendTo(document.head);
	}
}
