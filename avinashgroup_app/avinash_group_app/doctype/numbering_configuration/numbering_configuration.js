// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.ui.form.on("Numbering Configuration", {
	setup(frm) {
		// Branch dropdown limited to the chosen company.
		frm.set_query("branch", () => {
			return { filters: frm.doc.company ? { custom_company: frm.doc.company } : {} };
		});
	},

	refresh(frm) {
		load_field_options(frm);
		render_preview(frm);
		add_buttons(frm);
	},

	document_type(frm) {
		frm.set_value("company", null);
		frm.set_value("branch", null);
		load_field_options(frm);
		render_preview(frm);
	},

	company(frm) { render_preview(frm); },
	company_abbr(frm) { render_preview(frm); },
	branch(frm) {
		frm._branch_abbr = null;
		if (frm.doc.branch) {
			frappe.db.get_value("Branch", frm.doc.branch, "custom_abbr").then((r) => {
				frm._branch_abbr = (r.message || {}).custom_abbr;
				render_preview(frm);
			});
		}
		render_preview(frm);
	},
	separator(frm) { render_preview(frm); },
	legacy_upto(frm) { render_preview(frm); },
	legacy_source_field(frm) { render_preview(frm); },
});

// Voucher No. conditions (Equals only, no operator).
frappe.ui.form.on("Numbering Condition", {
	conditions_add(frm) { render_preview(frm); },
	conditions_remove(frm) { render_preview(frm); },
	// Opening a row's detail form: render the value control for the row's field.
	form_render(frm, cdt, cdn) {
		set_smart_value_options(frm, cdt, cdn);
	},
	field(frm, cdt, cdn) {
		set_smart_value_options(frm, cdt, cdn);
		render_preview(frm);
	},
	value(frm) { render_preview(frm); },
});

// Document No. conditions (with operators). Only used when Auto-fill is on.
frappe.ui.form.on("Numbering Document No Condition", {
	document_no_conditions_add(frm) { render_preview(frm); },
	document_no_conditions_remove(frm) { render_preview(frm); },
	form_render(frm, cdt, cdn) {
		set_smart_value_options(frm, cdt, cdn);
	},
	field(frm, cdt, cdn) {
		set_smart_value_options(frm, cdt, cdn);
		render_preview(frm);
	},
	operator(frm, cdt, cdn) {
		// In / Not In need a free-text list; Is Set / Is Not Set need no value.
		set_smart_value_options(frm, cdt, cdn);
		render_preview(frm);
	},
	value(frm) { render_preview(frm); },
});

frappe.ui.form.on("Numbering Segment", {
	segments_add(frm) { render_preview(frm); },
	segments_remove(frm) { render_preview(frm); },
	segments_move(frm) { render_preview(frm); },
	// Opening a row's detail form: make sure its pickers match the row's state.
	form_render(frm, cdt, cdn) {
		set_segment_field_options(frm, cdt, cdn);
		set_fetch_field_options(frm, cdt, cdn);
	},
	segment_type(frm, cdt, cdn) {
		set_segment_field_options(frm, cdt, cdn, true);
		render_preview(frm);
	},
	static_value(frm) { render_preview(frm); },
	return_value(frm) { render_preview(frm); },
	field(frm, cdt, cdn) {
		set_fetch_field_options(frm, cdt, cdn, true);
		render_preview(frm);
	},
	fetch_field(frm) { render_preview(frm); },
	number_length(frm) { render_preview(frm); },
	join_previous(frm) { render_preview(frm); },
});

// --- buttons --------------------------------------------------------------

function add_buttons(frm) {
	if (frm.is_new()) return;

	// Test the rule against a real document (no counter consumed).
	frm.add_custom_button(__("Test on a Document"), () => {
		const d = new frappe.ui.Dialog({
			title: __("Test Numbering Rule"),
			fields: [
				{
					fieldname: "reference",
					fieldtype: "Link",
					label: __("Document"),
					options: frm.doc.document_type,
					description: __("Leave empty to test with a blank sample document."),
				},
			],
			primary_action_label: __("Test"),
			primary_action(values) {
				frm.call("test_number", { reference: values.reference || null }).then((r) => {
					const res = r.message || {};
					const number = res.number
						? `<span style="font-family:var(--font-stack-monospace);font-size:16px;font-weight:600">${frappe.utils.escape_html(res.number)}</span>`
						: `<span class="text-muted">${__("no number produced")}</span>`;
					const matches = res.matches
						? `<span class="indicator-pill green">${__("rule matches this document")}</span>`
						: `<span class="indicator-pill orange">${__("rule would NOT match this document (conditions/scope differ)")}</span>`;
					d.hide();
					frappe.msgprint({
						title: __("Test Result"),
						indicator: res.matches ? "green" : "orange",
						message: `${number}<br><br>${matches}`,
					});
				});
			},
		});
		d.show();
	});

	// Duplicate this rule to other companies in one go.
	frm.add_custom_button(__("Apply to Other Companies"), () => {
		const d = new frappe.ui.Dialog({
			title: __("Duplicate to Companies"),
			fields: [
				{
					fieldname: "companies",
					fieldtype: "MultiSelectList",
					label: __("Companies"),
					get_data(txt) {
						return frappe.db.get_link_options("Company", txt);
					},
				},
			],
			primary_action_label: __("Create Copies"),
			primary_action(values) {
				if (!(values.companies || []).length) return;
				frappe.call({
					method: "avinashgroup_app.avinash_group_app.doctype.numbering_configuration.numbering_configuration.bulk_duplicate",
					args: { source: frm.doc.name, companies: values.companies },
					freeze: true,
					callback(r) {
						d.hide();
						frappe.msgprint(__("Created: {0}", [(r.message || []).join(", ")]));
					},
				});
			},
		});
		d.show();
	});
}

// --- field pickers ----------------------------------------------------------

const SKIP_FIELDTYPES = ["Section Break", "Column Break", "Tab Break", "HTML",
	"Table", "Table MultiSelect", "Button", "Fold", "Heading", "Image"];

function load_field_options(frm) {
	if (!frm.doc.document_type) return;

	frappe.model.with_doctype(frm.doc.document_type, () => {
		const meta = frappe.get_meta(frm.doc.document_type);
		const skip = SKIP_FIELDTYPES;

		// Fields a condition or segment can reference.
		const doc_fields = (meta.fields || [])
			.filter((f) => !skip.includes(f.fieldtype) && f.fieldname)
			.map((f) => f.fieldname)
			.sort();
		// Link fields only — the valid choices for a Fetch from Link segment.
		frm._segment_doc_fields = doc_fields;
		frm._segment_link_fields = (meta.fields || [])
			.filter((f) => f.fieldtype === "Link" && f.options && f.fieldname)
			.map((f) => f.fieldname)
			.sort();
		// Autocomplete suggestions — the user may still type any field name.
		const options = ["", ...doc_fields].join("\n");
		frm.fields_dict.conditions.grid.update_docfield_property("field", "options", options);
		frm.fields_dict.document_no_conditions.grid.update_docfield_property("field", "options", options);
		if (frm.fields_dict.docno_group_by) {
			frm.fields_dict.docno_group_by.grid.update_docfield_property("field", "options", options);
		}
		frm.fields_dict.segments.grid.update_docfield_property("field", "options", options);

		// The grid-wide options above also reset every row's copy — re-narrow
		// each existing segment row to its own segment type.
		(frm.doc.segments || []).forEach((row) => {
			set_segment_field_options(frm, row.doctype, row.name);
			set_fetch_field_options(frm, row.doctype, row.name);
		});

		// Saved condition rows get their typed value control (link picker,
		// select, …) on load — not only after the field is touched.
		[...(frm.doc.conditions || []), ...(frm.doc.document_no_conditions || [])]
			.forEach((row) => set_smart_value_options(frm, row.doctype, row.name));

		// "Date Field" -> date-like fields for the legacy cut-over comparison.
		const date_fields = (meta.fields || [])
			.filter((f) => ["Date", "Datetime"].includes(f.fieldtype) && f.fieldname)
			.map((f) => f.fieldname)
			.sort();
		frm.set_df_property("date_field", "options", ["", ...date_fields].join("\n"));

		// "Store Number In" / "Legacy Source Field" -> text-like fields.
		const text_types = ["Data", "Small Text", "Text", "Long Text", "Text Editor"];
		const text_fields = (meta.fields || [])
			.filter((f) => text_types.includes(f.fieldtype) && f.fieldname)
			.map((f) => f.fieldname)
			.sort();
		frm.set_df_property("target_field", "options", ["", ...text_fields].join("\n"));
		frm.set_df_property("legacy_source_field", "options", ["", ...text_fields].join("\n"));
		// "Document No. field" -> any field (Int/Data usually) can hold the number.
		frm.set_df_property("document_no_field", "options", ["", ...doc_fields].join("\n"));

		if (!frm.doc.target_field && text_fields.includes("custom_branch_name")) {
			frm.set_value("target_field", "custom_branch_name");
		}
		frm.refresh_field("target_field");
		frm.refresh_field("conditions");
		frm.refresh_field("document_no_conditions");
		frm.refresh_field("docno_group_by");
		frm.refresh_field("segments");
	});
}

// Segment "Field" picker, per row: a Fetch from Link segment may only follow
// a Link field, so that row's dropdown lists just the Link fields of the
// document type; other segment types keep the full field list. Options are
// written on the row's own docfield copy (frappe.meta.get_docfield with the
// row name), so rows of different segment types coexist in the same grid.
function set_segment_field_options(frm, cdt, cdn, clear_invalid) {
	if (!frm._segment_doc_fields) return;
	const row = locals[cdt][cdn];
	const fields = row.segment_type === "Fetch from Link"
		? (frm._segment_link_fields || [])
		: frm._segment_doc_fields;
	const df = frappe.meta.get_docfield(cdt, "field", cdn);
	if (df) df.options = ["", ...fields].join("\n");

	// On a type change, a field carried over from another segment type may not
	// be a Link — drop it (and the stale fetch_field) instead of keeping a
	// segment the server will flag as always-empty.
	if (clear_invalid && row.segment_type === "Fetch from Link"
		&& row.field && !fields.includes(row.field)) {
		frappe.model.set_value(cdt, cdn, "field", null);
		frappe.model.set_value(cdt, cdn, "fetch_field", null);
	}
	refresh_segment_row_field(frm, cdn, "field");
}

// Segment "Fetch Field" picker, per row: once the Link field is chosen, offer
// the linked doctype's own fields instead of free text.
function set_fetch_field_options(frm, cdt, cdn, clear_invalid) {
	const row = locals[cdt][cdn];
	if (row.segment_type !== "Fetch from Link" || !row.field || !frm.doc.document_type) return;

	frappe.model.with_doctype(frm.doc.document_type, () => {
		const link_df = frappe.meta.get_docfield(frm.doc.document_type, row.field);
		if (!link_df || link_df.fieldtype !== "Link" || !link_df.options) return;

		frappe.model.with_doctype(link_df.options, () => {
			const target_fields = (frappe.get_meta(link_df.options).fields || [])
				.filter((f) => !SKIP_FIELDTYPES.includes(f.fieldtype) && f.fieldname)
				.map((f) => f.fieldname)
				.sort();
			const df = frappe.meta.get_docfield(cdt, "fetch_field", cdn);
			// "name" is not a docfield but is always fetchable.
			if (df) df.options = ["", "name", ...target_fields].join("\n");
			if (clear_invalid && row.fetch_field && row.fetch_field !== "name"
				&& !target_fields.includes(row.fetch_field)) {
				frappe.model.set_value(cdt, cdn, "fetch_field", null);
			}
			refresh_segment_row_field(frm, cdn, "fetch_field");
		});
	});
}

// Redraw a row's control after its docfield copy changed: the inline grid
// control (if the row is currently editable) and the expanded detail form
// (if open) both render from the same per-row docfield copy.
function refresh_row_field(frm, parentfield, cdn, fieldname) {
	const table = frm.fields_dict[parentfield];
	if (!table || !table.grid) return;
	const grid_row = table.grid.grid_rows_by_docname && table.grid.grid_rows_by_docname[cdn];
	if (!grid_row) return;
	const column = grid_row.columns && grid_row.columns[fieldname];
	if (column && column.field) column.field.refresh();
	if (grid_row.grid_form && grid_row.grid_form.fields_dict
		&& grid_row.grid_form.fields_dict[fieldname]) {
		grid_row.grid_form.fields_dict[fieldname].refresh();
	}
}

function refresh_segment_row_field(frm, cdn, fieldname) {
	refresh_row_field(frm, "segments", cdn, fieldname);
}

// A cell's control class is chosen from df.fieldtype ONCE, when the control is
// first made (grid_row.make_control returns early if column.field exists) — so
// after the row's value docfield changes TYPE, the old control must be
// destroyed and re-created, both in the inline cell and the expanded row form.
function rebuild_value_control(frm, parentfield, cdn) {
	const table = frm.fields_dict[parentfield];
	if (!table || !table.grid) return;
	const grid_row = table.grid.grid_rows_by_docname && table.grid.grid_rows_by_docname[cdn];
	if (!grid_row) return;   // row not rendered yet -> it will pick up the new df when it is

	const column = grid_row.columns && grid_row.columns.value;
	if (column) {
		if (column.field) {
			const i = grid_row.on_grid_fields.indexOf(column.field);
			if (i > -1) grid_row.on_grid_fields.splice(i, 1);
			delete grid_row.on_grid_fields_dict.value;
			column.field = null;
			column.field_area && column.field_area.empty();
		}
		if (grid_row.row.hasClass("editable-row")) {
			// row is in inline edit right now — remake the control immediately
			grid_row.make_control(column);
			column.static_area.toggle(false);
			column.field_area.toggle(true);
		} else {
			grid_row.refresh_field("value");
		}
	}
	// expanded detail form open: re-render it from the row's docfields
	if (grid_row.grid_form && table.grid.open_grid_row === grid_row.grid_form) {
		grid_row.grid_form.render();
	}
}

// Smart value entry, PER ROW (rows referencing different field types coexist):
// Link -> a real link picker over the target doctype, Select -> its options,
// Check -> Yes/No, Date/Datetime -> date picker, anything else -> free text.
function set_smart_value_options(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!frm.doc.document_type) return;

	const apply = (fieldtype, options) => {
		// the row's own docfield copy — never the grid-wide column definition
		const value_df = frappe.meta.get_docfield(cdt, "value", cdn);
		if (!value_df) return;
		if (value_df.fieldtype === fieldtype && (value_df.options || "") === options) return;
		value_df.fieldtype = fieldtype;
		value_df.options = options;
		// works for either the Voucher No. (conditions) or Document No.
		// (document_no_conditions) grid — the row knows its own parent table.
		rebuild_value_control(frm, row.parentfield, cdn);
	};

	const op = row.operator || "Equals";

	// In / Not In take a comma-separated LIST, so the value must stay free text —
	// a single-pick control can't express a list. Is Set / Is Not Set need no
	// value at all. Only Equals / Not Equals get the typed control.
	if (!row.field || op === "In" || op === "Not In" || op === "Is Set" || op === "Is Not Set") {
		apply("Data", "");
		return;
	}

	frappe.model.with_doctype(frm.doc.document_type, () => {
		const df = frappe.meta.get_docfield(frm.doc.document_type, row.field);

		if (df && df.fieldtype === "Check") {
			apply("Select", "\n1\n0");
		} else if (df && df.fieldtype === "Select" && df.options) {
			apply("Select", "\n" + df.options);
		} else if (df && df.fieldtype === "Link" && df.options) {
			apply("Link", df.options);
		} else if (df && ["Date", "Datetime"].includes(df.fieldtype)) {
			apply("Date", "");
		} else {
			apply("Data", "");
		}
	});
}

// --- live preview -----------------------------------------------------------

function render_preview(frm) {
	const sep = frm.doc.separator || "/";
	const abbr = frm.doc.company_abbr || (frm.doc.company ? "…" : "ABBR");

	const parts = [];
	let has_number = false;

	// push respecting "Attach" (join_previous): glued parts concatenate onto
	// the previous one instead of getting a separator — e.g. 0001 + A -> 0001A
	const push_part = (s, html) => {
		if (s.join_previous && parts.length) {
			parts[parts.length - 1] += html;
		} else {
			parts.push(html);
		}
	};

	(frm.doc.segments || []).forEach((s) => {
		switch (s.segment_type) {
			case "Static Text":
				if (s.static_value) push_part(s, frappe.utils.escape_html(s.static_value));
				break;
			case "Normal / Return Code": {
				const normal = s.static_value || "?";
				const ret = s.return_value;
				push_part(s, frappe.utils.escape_html(ret ? `${normal}|${ret}` : normal));
				break;
			}
			case "Company Abbr":
				push_part(s, frappe.utils.escape_html(abbr));
				break;
			case "Branch Abbr":
				push_part(s, frappe.utils.escape_html(frm._branch_abbr || (frm.doc.branch ? "…" : "KTM")));
				break;
			case "Fiscal Year":
				push_part(s, sep === "/" ? "82-83" : "82/83");
				break;
			case "Document Field":
				if (s.field) {
					const pad = cint(s.number_length);
					const hint = pad ? ` (${"0".repeat(pad)})` : "";
					push_part(s, `<i>&lt;${frappe.utils.escape_html(s.field + hint)}&gt;</i>`);
				}
				break;
			case "Fetch from Link":
				if (s.field) {
					const label = s.fetch_field
						? `${s.field}→${s.fetch_field}`
						: s.field;
					push_part(s, `<i>&lt;${frappe.utils.escape_html(label)}&gt;</i>`);
				}
				break;
			case "Number": {
				const len = cint(s.number_length) || 6;
				push_part(s, "1".padStart(len, "0"));
				has_number = true;
				break;
			}
		}
	});

	let sample = parts.length
		? parts.join(frappe.utils.escape_html(sep))
		: `<span class="text-muted">${__("add segments above")}</span>`;

	let warn = "";
	if (parts.length && !has_number) {
		warn = `<div class="text-muted small">${__("No Number segment: pass-through rule — copies the segment values as-is (e.g. legacy number from narration), no running counter.")}</div>`;
	}

	const conds = (frm.doc.conditions || [])
		.filter((c) => c.field)
		.map((c) => `${c.field} = ${c.value ?? ""}`);
	const when = conds.length
		? `<div class="text-muted small">${__("Applies only when")}: ${frappe.utils.escape_html(conds.join("  AND  "))}</div>`
		: `<div class="text-muted small">${__("Applies as a default (no conditions).")}</div>`;

	let legacy = "";
	if (frm.doc.legacy_upto) {
		const src = frm.doc.legacy_source_field || "?";
		legacy = `<div class="text-muted small">${__("Up to {0}: number is copied from <b>{1}</b> (legacy); after that, generated as above.",
			[frappe.utils.escape_html(frm.doc.legacy_upto), frappe.utils.escape_html(src)])}</div>`;
	}

	const html = `
		<div style="padding:10px 12px;border:1px solid var(--border-color);border-radius:8px;background:var(--subtle-fg)">
			<div style="font-size:18px;font-family:var(--font-stack-monospace);font-weight:600">${sample}</div>
			${warn}${when}${legacy}
		</div>`;

	const field = frm.get_field("preview");
	if (field) field.html(html);
}

function cint(v) { return parseInt(v, 10) || 0; }
