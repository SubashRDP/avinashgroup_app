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
		load_field_options(frm, true);
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

frappe.ui.form.on("Numbering Condition", {
	conditions_add(frm) { render_preview(frm); },
	conditions_remove(frm) { render_preview(frm); },
	field(frm, cdt, cdn) {
		set_smart_value_options(frm, cdt, cdn);
		render_preview(frm);
	},
	value(frm) { render_preview(frm); },
});

frappe.ui.form.on("Numbering Segment", {
	segments_add(frm) { render_preview(frm); },
	segments_remove(frm) { render_preview(frm); },
	segments_move(frm) { render_preview(frm); },
	segment_type(frm) { render_preview(frm); },
	static_value(frm) { render_preview(frm); },
	return_value(frm) { render_preview(frm); },
	field(frm) { render_preview(frm); },
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

function load_field_options(frm, reset_default) {
	if (!frm.doc.document_type) return;

	frappe.model.with_doctype(frm.doc.document_type, () => {
		const meta = frappe.get_meta(frm.doc.document_type);
		const skip = ["Section Break", "Column Break", "Tab Break", "HTML",
			"Table", "Table MultiSelect", "Button", "Fold", "Heading", "Image"];

		// Fields a condition or segment can reference.
		const doc_fields = (meta.fields || [])
			.filter((f) => !skip.includes(f.fieldtype) && f.fieldname)
			.map((f) => f.fieldname)
			.sort();
		const options = ["", ...doc_fields].join("\n");
		frm.fields_dict.conditions.grid.update_docfield_property("field", "options", options);
		frm.fields_dict.segments.grid.update_docfield_property("field", "options", options);

		// "Date Field" -> date-like fields for the legacy cut-over comparison.
		const date_fields = (meta.fields || [])
			.filter((f) => ["Date", "Datetime"].includes(f.fieldtype) && f.fieldname)
			.map((f) => f.fieldname)
			.sort();
		frm.set_df_property("date_field", "options", ["", ...date_fields].join("\n"));

		// "Store Number In" / "Legacy Source Field" -> text-like fields.
		const text_types = ["Data", "Small Text", "Text", "Long Text", "Text Editor"];
		const target_fields = (meta.fields || [])
			.filter((f) => text_types.includes(f.fieldtype) && f.fieldname)
			.map((f) => f.fieldname)
			.sort();
		frm.set_df_property("target_field", "options", ["", ...target_fields].join("\n"));
		frm.set_df_property("legacy_source_field", "options", ["", ...target_fields].join("\n"));

		if ((reset_default || !frm.doc.target_field) && target_fields.includes("custom_branch_name")) {
			frm.set_value("target_field", "custom_branch_name");
		}
		frm.refresh_field("target_field");
		frm.refresh_field("conditions");
		frm.refresh_field("segments");
	});
}

// Smart value entry: checkbox -> Yes/No select, Select -> its options.
function set_smart_value_options(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.field || !frm.doc.document_type) return;

	frappe.model.with_doctype(frm.doc.document_type, () => {
		const df = frappe.meta.get_docfield(frm.doc.document_type, row.field);
		const grid = frm.fields_dict.conditions.grid;
		let value_df = { fieldtype: "Data", options: "" };

		if (df && df.fieldtype === "Check") {
			value_df = { fieldtype: "Select", options: "\n1\n0" };
		} else if (df && df.fieldtype === "Select" && df.options) {
			value_df = { fieldtype: "Select", options: "\n" + df.options };
		} else if (df && df.fieldtype === "Link" && df.options) {
			value_df = { fieldtype: "Data", options: "" };
		}

		grid.update_docfield_property("value", "fieldtype", value_df.fieldtype);
		grid.update_docfield_property("value", "options", value_df.options);
		grid.refresh();
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
