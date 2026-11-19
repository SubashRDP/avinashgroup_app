// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

// Memo Generator: pick a memo template, edit the memo, see the paper on the right.
// "Generate Memo" saves it as a Memo Log and shows the final paper (Memo No +
// approval table). Backend: avinashgroup_app.custom_code.document_generator.memo

frappe.pages["memo-generator"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Memo Generator"),
		single_column: true,
	});
	wrapper.memo_generator = new MemoGenerator(page);
};

frappe.pages["memo-generator"].on_page_show = function (wrapper) {
	// Opened again with a template from the Document Template button.
	const ro = frappe.route_options || {};
	if (ro.template && wrapper.memo_generator) {
		frappe.route_options = null;
		wrapper.memo_generator.start_new(ro.template);
	}
};

const MEMO_API = "avinashgroup_app.custom_code.document_generator.memo";

class MemoGenerator {
	constructor(page) {
		this.page = page;
		this.controls = {};
		this.memo_name = null; // set once generated; later Generates update it
		this.grid = [];

		this.make_layout();
		this.make_controls();
		this.make_actions();

		const ro = frappe.route_options || {};
		frappe.route_options = null;
		if (ro.template) this.controls.memo_template.set_value(ro.template);
		this.render_grid();
		this.schedule_preview();
	}

	make_layout() {
		this.body = $(`
			<div class="mg-wrap">
				<div class="mg-form">
					<div class="mg-card mg-setup"><h6>${__("Memo")}</h6></div>
					<div class="mg-card mg-head"><h6>${__("Heading")}</h6></div>
					<div class="mg-card mg-above"><h6>${__("Text Above Table")}</h6></div>
					<div class="mg-card mg-table">
						<h6>${__("Table")}</h6>
						<div class="mg-table-size mg-row"></div>
						<div class="mg-grid-wrap" style="overflow-x:auto;margin-top:8px"></div>
						<div class="text-muted small">${__("Row 1 is the heading row.")}</div>
					</div>
					<div class="mg-card mg-below"><h6>${__("Text Below Table")}</h6></div>
				</div>
				<div class="mg-paper-col">
					<div class="mg-status text-muted small"></div>
					<div class="mg-paper"><iframe></iframe></div>
				</div>
			</div>
		`).appendTo(this.page.main);
		this.$status = this.body.find(".mg-status");
		this.$iframe = this.body.find(".mg-paper iframe");
	}

	make_control(parent, df) {
		const control = frappe.ui.form.make_control({
			df: Object.assign({ placeholder: df.label }, df),
			parent: $('<div class="mg-field"></div>').appendTo(parent)[0],
			render_input: true,
		});
		control.refresh();
		this.controls[df.fieldname] = control;
		return control;
	}

	make_controls() {
		const preview = () => this.schedule_preview();

		const setup = $('<div class="mg-row"></div>').appendTo(this.body.find(".mg-setup"));
		this.make_control(setup, {
			fieldname: "memo_template", label: __("Memo Template"), fieldtype: "Link",
			options: "Document Template", reqd: 1,
			get_query: () => ({ filters: { is_memo: 1, is_active: 1 } }),
			onchange: () => this.on_template_change(),
		});
		this.make_control(setup, {
			fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
			onchange: () => {
				if (this.controls.custom_department?.get_value()) this.controls.custom_department.set_value("");
				preview();
			},
		});
		this.make_control(setup, {
			fieldname: "posting_date", label: __("Date"), fieldtype: "Date", reqd: 1,
			default: frappe.datetime.get_today(), onchange: preview,
		});
		this.make_control(setup, {
			fieldname: "custom_department", label: __("Department"), fieldtype: "Link", options: "Department",
			get_query: () => {
				const company = this.controls.company.get_value();
				return company ? { filters: { company } } : {};
			},
			onchange: preview,
		});

		const head = $('<div class="mg-row"></div>').appendTo(this.body.find(".mg-head"));
		[
			["memo_title", __("Memo Heading")],
			["memo_to", __("To")],
			["memo_from", __("From")],
			["memo_cc", __("CC")],
		].forEach(([fieldname, label]) =>
			this.make_control(head, { fieldname, label, fieldtype: "Data", onchange: preview })
		);
		const subject_row = $('<div class="mg-row"></div>').appendTo(this.body.find(".mg-head"));
		this.make_control(subject_row, {
			fieldname: "subject", label: __("Subject"), fieldtype: "Data", reqd: 1, onchange: preview,
		});

		this.make_control(this.body.find(".mg-above"), {
			fieldname: "text_above", label: "", fieldtype: "Text Editor", onchange: preview,
		});
		this.make_control(this.body.find(".mg-below"), {
			fieldname: "text_below", label: "", fieldtype: "Text Editor", onchange: preview,
		});

		const size = this.body.find(".mg-table-size");
		this.make_control(size, {
			fieldname: "table_rows", label: __("Rows"), fieldtype: "Int",
			onchange: () => this.resize_grid(),
		});
		this.make_control(size, {
			fieldname: "table_columns", label: __("Columns"), fieldtype: "Int",
			onchange: () => this.resize_grid(),
		});

		// Controls with a default don't always show it until set.
		["company", "posting_date"].forEach((f) => {
			const c = this.controls[f];
			if (c.df.default && !c.get_value()) c.set_value(c.df.default);
		});
	}

	make_actions() {
		this.page.set_primary_action(__("Generate Memo"), () => this.generate(), "printer");
		this.page.add_action_item(__("Print"), () => this.print());
		this.page.add_action_item(__("Download PDF"), () => this.download_pdf());
		this.page.add_action_item(__("Open Memo Log"), () => this.open_memo());
		this.page.add_action_item(__("New Memo"), () => this.start_new());
	}

	// ── Template ──────────────────────────────────────────────

	async on_template_change() {
		const template = this.controls.memo_template.get_value();
		if (!template || this._loading) return;
		const r = await frappe.call({ method: `${MEMO_API}.get_memo_template`, args: { template } });
		const t = r.message || {};
		this._loading = true; // one preview at the end, not one per field
		try {
			for (const f of ["memo_title", "memo_to", "memo_from", "memo_cc", "subject", "text_above", "text_below"]) {
				await this.controls[f].set_value(t[f] || "");
			}
			this.grid = JSON.parse(t.table_data || "[]");
			await this.controls.table_rows.set_value(t.table_rows || 0);
			await this.controls.table_columns.set_value(t.table_columns || 0);
		} finally {
			this._loading = false;
		}
		this.render_grid();
		this.schedule_preview();
	}

	start_new(template) {
		this.memo_name = null;
		this.grid = [];
		["memo_title", "memo_to", "memo_from", "memo_cc", "subject", "text_above", "text_below",
			"custom_department", "table_rows", "table_columns"].forEach((f) => this.controls[f].set_value(""));
		this.controls.memo_template.set_value(template || "");
		this.render_grid();
		this.schedule_preview();
	}

	// ── Table grid ────────────────────────────────────────────

	size() {
		return [
			Math.max(cint(this.controls.table_rows.get_value()), 0),
			Math.max(cint(this.controls.table_columns.get_value()), 0),
		];
	}

	// Make this.grid exactly rows x cols, keeping old cell values that still fit.
	fit_grid() {
		const [rows, cols] = this.size();
		const grid = [];
		for (let r = 0; r < rows; r++) {
			const old_row = Array.isArray(this.grid[r]) ? this.grid[r] : [];
			const row = [];
			for (let c = 0; c < cols; c++) row.push(old_row[c] != null ? String(old_row[c]) : "");
			grid.push(row);
		}
		this.grid = grid;
	}

	resize_grid() {
		if (this._loading) return;
		this.render_grid();
		this.schedule_preview();
	}

	render_grid() {
		this.fit_grid();
		const wrap = this.body.find(".mg-grid-wrap").empty();
		if (!this.grid.length || !this.grid[0].length) return;

		let html = '<table class="table table-bordered mg-grid" style="margin:0">';
		this.grid.forEach((row, r) => {
			html += "<tr>";
			row.forEach((value, c) => {
				html += `<td><input type="text" class="form-control input-xs" data-r="${r}" data-c="${c}"
					value="${frappe.utils.escape_html(value)}"></td>`;
			});
			html += "</tr>";
		});
		html += "</table>";
		wrap.html(html);
		wrap.find("input").on("input", (e) => {
			const $i = $(e.currentTarget);
			this.grid[$i.data("r")][$i.data("c")] = $i.val();
			this.schedule_preview();
		});
	}

	// ── Preview / Generate ────────────────────────────────────

	values() {
		const v = {};
		["memo_template", "company", "posting_date", "custom_department", "memo_title", "memo_to",
			"memo_from", "memo_cc", "subject", "text_above", "text_below", "table_rows", "table_columns",
		].forEach((f) => (v[f] = this.controls[f].get_value()));
		this.fit_grid();
		v.table_data = JSON.stringify(this.grid);
		return v;
	}

	schedule_preview() {
		if (this._loading) return;
		clearTimeout(this._preview_timer);
		this._preview_timer = setTimeout(() => this.preview(), 500);
	}

	async preview() {
		const r = await frappe.call({
			method: `${MEMO_API}.preview_memo`,
			args: { data: JSON.stringify(this.values()) },
		});
		this.show_paper(r.message || "");
		this.set_status();
	}

	show_paper(html) {
		const doc = `<!doctype html><html><head><meta charset="utf-8">
			<style>body{margin:0;padding:38px 45px;background:#fff}</style></head>
			<body>${html}</body></html>`;
		this.$iframe.attr("srcdoc", doc);
	}

	set_status(extra) {
		const text = this.memo_name
			? __("Generated: {0}. Edits here update this memo when you press Generate Memo again.", [
					`<a href="/app/memo-log/${encodeURIComponent(this.memo_name)}">${frappe.utils.escape_html(this.memo_name)}</a>`,
			  ])
			: __("Preview. The Memo No appears after you press Generate Memo. The approval box appears on the paper after the final approval.");
		this.$status.html(text + (extra ? `<br>${extra}` : ""));
	}

	async generate() {
		const v = this.values();
		const missing = [];
		if (!v.memo_template) missing.push(__("Memo Template"));
		if (!v.company) missing.push(__("Company"));
		if (!v.posting_date) missing.push(__("Date"));
		if (!v.subject) missing.push(__("Subject"));
		if (missing.length) {
			frappe.msgprint(__("Please fill: {0}", [missing.join(", ")]));
			return;
		}

		const r = await frappe.call({
			method: `${MEMO_API}.generate_memo`,
			args: { data: JSON.stringify(v), name: this.memo_name },
			freeze: true,
			freeze_message: __("Generating memo..."),
		});
		const m = r.message;
		this.memo_name = m.name;
		this.show_paper(m.html);
		this.set_status(
			m.approval_rule
				? __("Approval rule: {0}. Open Memo Log and press Submit for Approval. The approval box prints after the final approval.", [frappe.utils.escape_html(m.approval_rule)])
				: __("No approval rule matched for this Created By + Department, so there is no approval table.")
		);
		frappe.show_alert({ message: __("Memo {0} generated", [m.memo_no]), indicator: "green" });
	}

	// ── Output ────────────────────────────────────────────────

	need_memo() {
		if (!this.memo_name) {
			frappe.msgprint(__("Press Generate Memo first."));
			return false;
		}
		return true;
	}

	print() {
		if (!this.need_memo()) return;
		const params = new URLSearchParams({
			doctype: "Memo Log", name: this.memo_name, format: "Memo Log",
			no_letterhead: 1, trigger_print: 1,
		});
		window.open(`/printview?${params.toString()}`, "_blank");
	}

	download_pdf() {
		if (!this.need_memo()) return;
		const params = new URLSearchParams({
			doctype: "Memo Log", name: this.memo_name, format: "Memo Log", no_letterhead: 1,
		});
		window.open(`/api/method/frappe.utils.print_format.download_pdf?${params.toString()}`, "_blank");
	}

	open_memo() {
		if (!this.need_memo()) return;
		frappe.set_route("Form", "Memo Log", this.memo_name);
	}
}
