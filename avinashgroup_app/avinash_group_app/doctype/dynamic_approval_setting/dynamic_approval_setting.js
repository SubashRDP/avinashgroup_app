function set_criteria_field_options(frm) {
	if (!frm.doc.document_type) return;
	frappe.model.with_doctype(frm.doc.document_type, function () {
		let all = _get_link_field_options(frm);
		if (frm.fields_dict.match_criteria && frm.fields_dict.match_criteria.grid) {
			frm.fields_dict.match_criteria.grid.update_docfield_property("field_name", "options", all);
		}
	});
}

frappe.ui.form.on("Dynamic Approval Setting", {
	refresh(frm) {
		set_criteria_field_options(frm);
		render_sections_ui(frm);

		if (!frm.is_new()) {
			frm.add_custom_button(__("Setup Workflow"), () => {
				frappe.confirm(
					__("This will create/update the workflow and custom fields on <b>{0}</b>. Continue?", [frm.doc.document_type]),
					() => {
						frappe.call({
							method: "avinashgroup_app.custom_code.dynamic_approval.setup_workflow",
							args: { config_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Setting up workflow..."),
							callback(r) {
								if (!r.exc) {
									frappe.msgprint({
										title: __("Success"), indicator: "green",
										message: __("Workflow setup complete for {0}.", [frm.doc.document_type])
									});
								}
							}
						});
					}
				);
			}).addClass("btn-primary");
		}
	},

	document_type(frm) {
		set_criteria_field_options(frm);
	},

	validate(frm) {
		validate_unique_sections_in_form(frm);
	},
});

function validate_unique_sections_in_form(frm) {
	const seen = new Map();

	function track(section, source, idx) {
		const key = (section || "").trim();
		if (!key) return;

		const first = seen.get(key);
		if (first) {
			frappe.throw(
				__(
					"Duplicate section name <b>{0}</b> found in this setting.<br><br>First used in: {1}<br>Duplicate at: {2}",
					[
						frappe.utils.escape_html(key),
						frappe.utils.escape_html(first),
						frappe.utils.escape_html(`${source} row ${idx}`),
					]
				)
			);
		}

		seen.set(key, `${source} row ${idx}`);
	}

	(frm.doc.match_criteria || []).forEach((row, i) => {
		track(row.section, "Match Criteria", row.idx || i + 1);
	});

	(frm.doc.approvers || []).forEach((row, i) => {
		track(row.section, "Approvers", row.idx || i + 1);
	});
}

// ── Child table: update field_value picker based on selected field_name ──
frappe.ui.form.on("Dynamic Approval Match Criteria", {
	field_name(frm, cdt, cdn) {
		update_field_value_options(frm, cdt, cdn);
	},
	form_render(frm, cdt, cdn) {
		update_field_value_options(frm, cdt, cdn);
	},
});

function update_field_value_options(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (!row.field_name || !frm.doc.document_type) return;

	frappe.model.with_doctype(frm.doc.document_type, function () {
		let meta = frappe.get_meta(frm.doc.document_type);
		let field_meta = (meta.fields || []).find(f => f.fieldname === row.field_name);

		let standard_link_map = {
			owner: "User", modified_by: "User",
			company: "Company", department: "Department",
		};

		let linked_doctype = null;
		let select_options = null;

		if (field_meta) {
			if (field_meta.fieldtype === "Link") {
				linked_doctype = field_meta.options;
			} else if (field_meta.fieldtype === "Select") {
				select_options = (field_meta.options || "").split("\n").filter(Boolean);
			}
		} else if (standard_link_map[row.field_name]) {
			linked_doctype = standard_link_map[row.field_name];
		}

		if (linked_doctype) {
			frappe.call({
				method: "frappe.client.get_list",
				args: { doctype: linked_doctype, fields: ["name"], limit: 200 },
				callback(r) {
					if (!r.message) return;
					let options = r.message.map(d => d.name).join("\n");
					_set_field_value_options(frm, cdt, cdn, options);
				},
			});
		} else if (select_options) {
			_set_field_value_options(frm, cdt, cdn, select_options.join("\n"));
		} else {
			_set_field_value_options(frm, cdt, cdn, "");
		}
	});
}

function _set_field_value_options(frm, cdt, cdn, options) {
	let df = frappe.meta.get_docfield(cdt, "field_value", cdn);
	if (df) df.options = options;
	if (frm.fields_dict.match_criteria && frm.fields_dict.match_criteria.grid) {
		frm.fields_dict.match_criteria.grid.update_docfield_property("field_value", "options", options);
	}
	frm.refresh_field("match_criteria");
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  Virtual Section UI
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function render_sections_ui(frm) {
	let wrapper = frm.fields_dict.dept_config_html;
	if (!wrapper || !wrapper.$wrapper) return;

	// Collect all sections from both child tables
	let criteria_rows = frm.doc.match_criteria || [];
	let approver_rows = frm.doc.approvers || [];

	// Build section name list (preserve order of first appearance)
	let section_names = [];
	[...criteria_rows, ...approver_rows].forEach(r => {
		let s = r.section || "Default";
		if (!section_names.includes(s)) section_names.push(s);
	});
	if (!section_names.length) section_names = [];

	// Build cards HTML
	let cards_html = section_names.map(sec => {
		let crit = criteria_rows.filter(r => (r.section || "Default") === sec);
		let appr = approver_rows.filter(r => (r.section || "Default") === sec);
		let is_default = (frm.doc.default_section || "").trim() === sec;

		let crit_html = crit.length
			? crit.map(r => `
				<span style="display:inline-flex;align-items:center;background:#f0f4f8;border:1px solid #d1d8dd;border-radius:4px;padding:2px 8px;margin:2px;font-size:12px;">
					<b>${frappe.utils.escape_html(r.field_name || "")}</b>&nbsp;=&nbsp;${frappe.utils.escape_html(r.field_value || "")}
				</span>`).join("")
			: `<span style="color:#999;font-size:12px;font-style:italic;">No criteria — catch-all</span>`;

		let appr_html = appr.length
			? appr.map((r, i) => `
				<span style="display:inline-flex;align-items:center;background:#fff;border:1px solid #d1d8dd;border-radius:4px;padding:2px 8px;margin:2px;font-size:12px;">
					${i > 0 ? '<span style="color:#aaa;margin-right:4px;">→</span>' : ""}${frappe.utils.escape_html(r.approver_name || r.approver || "")}
				</span>`).join("")
			: `<span style="color:#999;font-size:12px;font-style:italic;">No approvers</span>`;

		return `
		<div style="border:1px solid #d1d8dd;border-radius:8px;margin-bottom:10px;overflow:hidden;">
			<div style="background:#f4f5f6;padding:8px 14px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #d1d8dd;">
				<span style="font-weight:600;font-size:13px;">
					${frappe.utils.escape_html(sec)}
					${is_default ? '<span style="margin-left:6px;background:#e8f7ef;color:#1e7e34;border:1px solid #b7ebc7;border-radius:10px;padding:1px 7px;font-size:10px;">Default</span>' : ""}
				</span>
				<div style="display:flex;gap:6px;">
					<button class="btn btn-xs btn-default btn-section-edit" data-section="${frappe.utils.escape_html(sec)}">
						<svg class="icon icon-sm"><use href="#icon-edit"></use></svg> Edit
					</button>
					<button class="btn btn-xs btn-danger btn-section-delete" data-section="${frappe.utils.escape_html(sec)}">
						<svg class="icon icon-sm"><use href="#icon-delete"></use></svg>
					</button>
				</div>
			</div>
			<div style="padding:10px 14px;">
				<div style="margin-bottom:6px;">
					<span style="font-size:11px;text-transform:uppercase;color:#6c757d;letter-spacing:0.5px;">Match Criteria</span>
					<div style="margin-top:4px;">${crit_html}</div>
				</div>
				<div>
					<span style="font-size:11px;text-transform:uppercase;color:#6c757d;letter-spacing:0.5px;">Approvers (in order)</span>
					<div style="margin-top:4px;">${appr_html}</div>
				</div>
			</div>
		</div>`;
	}).join("");

	if (!section_names.length) {
		cards_html = `<div style="color:#999;padding:16px;text-align:center;border:1px dashed #d1d8dd;border-radius:8px;">No sections configured yet. Click <b>+ Add Section</b> to create your first approval rule.</div>`;
	}

	wrapper.$wrapper.html(`
		<div style="margin-bottom:10px;">
			${cards_html}
			<button class="btn btn-xs btn-primary btn-section-add" style="margin-top:6px;">
				+ Add Section
			</button>
		</div>
	`);

	wrapper.$wrapper.find(".btn-section-add").on("click", e => {
		e.preventDefault();
		open_section_dialog(frm, null);
	});
	wrapper.$wrapper.find(".btn-section-edit").on("click", function (e) {
		e.preventDefault();
		open_section_dialog(frm, $(this).attr("data-section"));
	});
	wrapper.$wrapper.find(".btn-section-delete").on("click", function (e) {
		e.preventDefault();
		let sec = $(this).attr("data-section");
		frappe.confirm(__("Delete section <b>{0}</b> and all its criteria + approvers?", [sec]), () => {
			frm.doc.match_criteria = (frm.doc.match_criteria || []).filter(r => (r.section || "Default") !== sec);
			frm.doc.approvers = (frm.doc.approvers || []).filter(r => (r.section || "Default") !== sec);
			if ((frm.doc.default_section || "").trim() === sec) {
				frm.doc.default_section = "";
				frm.refresh_field("default_section");
			}
			frm.refresh_field("match_criteria");
			frm.refresh_field("approvers");
			frm.dirty();
			render_sections_ui(frm);
		});
	});
}

function open_section_dialog(frm, existing_section) {
	let is_new = !existing_section;

	// Pre-load existing data
	let existing_criteria = is_new ? [] :
		(frm.doc.match_criteria || []).filter(r => (r.section || "Default") === existing_section);
	let existing_approvers = is_new ? [] :
		(frm.doc.approvers || []).filter(r => (r.section || "Default") === existing_section);

	let d = new frappe.ui.Dialog({
		title: is_new ? __("Add Section") : __("Edit Section: {0}", [existing_section]),
		size: "extra-large",
		fields: [
			{
				fieldname: "section_name",
				fieldtype: "Data",
				label: __("Section Name"),
				reqd: 1,
				default: is_new ? "" : existing_section,
				description: __("A unique name for this approval rule (e.g. 'HR Accounts', 'Finance', 'Default')")
			},
			{
				fieldname: "is_default_section",
				fieldtype: "Check",
				label: __("Use as default fallback section"),
				default: (!is_new && (frm.doc.default_section || "").trim() === existing_section) ? 1 : 0,
				description: __("If no criteria matches, this section will be used."),
			},
			{ fieldtype: "Section Break", label: __("Match Criteria") },
			{
				fieldname: "criteria_help",
				fieldtype: "HTML",
				options: `<p class="text-muted" style="font-size:12px;margin:0 0 6px;">
					Define which documents this rule applies to. All rows must match (AND logic).
					This picker is link-aware: choose a Link field, then select a value from the linked DocType.
					Leave empty to make this a catch-all rule.
				</p>`
			},
			{
				fieldname: "criteria_table",
				fieldtype: "Table",
				label: __("Criteria"),
				cannot_add_rows: false,
				in_place_edit: true,
				data: existing_criteria.map(r => ({
					field_name: r.field_name,
					field_value: r.field_value,
					linked_doctype: _get_linked_doctype_for_field(frm, r.field_name),
				})),
				fields: [
					{
						fieldname: "field_name",
						label: __("Field Name"),
						fieldtype: "Select",
						in_list_view: 1,
						reqd: 1,
						columns: 5,
						options: _get_link_field_options(frm),
						onchange: function () {
							this.doc.linked_doctype = _get_linked_doctype_for_field(frm, this.doc.field_name);
							this.doc.field_value = "";
						},
					},
					{
						fieldname: "linked_doctype",
						fieldtype: "Data",
						hidden: 1,
					},
					{
						fieldname: "field_value",
						label: __("Field Value"),
						fieldtype: "Dynamic Link",
						in_list_view: 1,
						reqd: 1,
						columns: 5,
						get_options: function (field) {
							return field.doc.linked_doctype || "";
						},
					}
				]
			},
			{ fieldtype: "Section Break", label: __("Approvers") },
			{
				fieldname: "approvers_help",
				fieldtype: "HTML",
				options: `<p class="text-muted" style="font-size:12px;margin:0 0 6px;">
					Fixed approvers automatically appended at the end of the approval chain for this rule, in order.
				</p>`
			},
			{
				fieldname: "approvers_table",
				fieldtype: "Table",
				label: __("Approvers (in order)"),
				cannot_add_rows: false,
				in_place_edit: true,
				data: existing_approvers.map(r => ({ approver: r.approver, approver_name: r.approver_name })),
				fields: [
					{
						fieldname: "approver",
						label: __("Approver"),
						fieldtype: "Link",
						options: "User",
						in_list_view: 1,
						reqd: 1,
						columns: 5,
					},
					{
						fieldname: "approver_name",
						label: __("Full Name"),
						fieldtype: "Data",
						in_list_view: 1,
						read_only: 1,
						columns: 5,
						fetch_from: "approver.full_name",
					}
				]
			},
		],
		primary_action_label: is_new ? __("Add Section") : __("Update Section"),
		primary_action(values) {
			let sec_name = (values.section_name || "").trim();
			if (!sec_name) {
				frappe.msgprint(__("Please enter a section name."));
				return;
			}

			// Prevent duplicate section names when adding new
			if (is_new) {
				let existing_names = [...new Set([
					...(frm.doc.match_criteria || []).map(r => r.section || "Default"),
					...(frm.doc.approvers || []).map(r => r.section || "Default"),
				])];
				if (existing_names.includes(sec_name)) {
					frappe.msgprint(__("A section named <b>{0}</b> already exists.", [sec_name]));
					return;
				}
			}

			// Remove old rows for this section
			frm.doc.match_criteria = (frm.doc.match_criteria || []).filter(
				r => (r.section || "Default") !== (existing_section || sec_name)
			);
			frm.doc.approvers = (frm.doc.approvers || []).filter(
				r => (r.section || "Default") !== (existing_section || sec_name)
			);

			// Add new criteria rows
			(values.criteria_table || []).filter(r => r.field_name && r.field_value).forEach(r => {
				let child = frappe.model.add_child(frm.doc, "Dynamic Approval Match Criteria", "match_criteria");
				child.section = sec_name;
				child.field_name = r.field_name;
				child.field_value = r.field_value;
			});

			// Add new approver rows
			(values.approvers_table || []).filter(r => r.approver).forEach(r => {
				let child = frappe.model.add_child(frm.doc, "Dynamic Approval Fixed Approver", "approvers");
				child.section = sec_name;
				child.approver = r.approver;
				child.approver_name = r.approver_name || "";
			});

			// Keep exactly one default fallback section.
			const old_section_name = (existing_section || sec_name || "").trim();
			if (values.is_default_section) {
				frm.doc.default_section = sec_name;
			} else if (
				(frm.doc.default_section || "").trim() === old_section_name
				|| (frm.doc.default_section || "").trim() === sec_name
			) {
				frm.doc.default_section = "";
			}

			frm.refresh_field("match_criteria");
			frm.refresh_field("approvers");
			frm.refresh_field("default_section");
			frm.dirty();
			d.hide();
			render_sections_ui(frm);
		},
	});

	d.show();
}

function _get_link_field_options(frm) {
	if (!frm.doc.document_type) return "";
	let meta = frappe.get_meta(frm.doc.document_type);
	if (!meta) return "";
	let fields = (meta.fields || [])
		.filter(f => f.fieldtype === "Link")
		.map(f => f.fieldname);
	let standard = ["owner", "company", "department", "modified_by"];
	return [...new Set([...standard, ...fields])].join("\n");
}

function _get_linked_doctype_for_field(frm, field_name) {
	if (!frm.doc.document_type || !field_name) return "";

	let standard_link_map = {
		owner: "User",
		modified_by: "User",
		company: "Company",
		department: "Department",
	};

	if (standard_link_map[field_name]) {
		return standard_link_map[field_name];
	}

	let meta = frappe.get_meta(frm.doc.document_type);
	if (!meta) return "";

	let field_meta = (meta.fields || []).find(f => f.fieldname === field_name);
	if (field_meta && field_meta.fieldtype === "Link") {
		return field_meta.options || "";
	}

	return "";
}
