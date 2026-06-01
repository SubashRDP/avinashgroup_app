// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

const DT_API = "avinashgroup_app.custom_code.document_generator.api";

frappe.ui.form.on("Document Template", {
	refresh(frm) {
		mount_designer(frm);
		add_designer_buttons(frm);
	},

	before_save(frm) {
		sync_canvas_to_sections(frm);
	},
});

function add_designer_buttons(frm) {
	if (frm.is_new()) return;
	frm.add_custom_button(__("Add Section"), () => frm._dg_canvas && frm._dg_canvas.add_section(), __("Layout"));
	frm.add_custom_button(__("Add Image"), () => frm._dg_canvas && frm._dg_canvas.add_image(), __("Layout"));
}

function mount_designer(frm) {
	const field = frm.get_field("layout_designer");
	if (!field) return;
	const $wrap = field.$wrapper;

	if (frm.is_new()) {
		$wrap.html(
			`<div class="text-muted" style="padding:16px">${__(
				"Save this template once, then design its layout here (drag, resize, edit boxes)."
			)}</div>`
		);
		return;
	}

	// Skip if already mounted and still in the DOM (avoid clobbering unsaved edits).
	if (frm._dg_canvas && frm._dg_canvas.$page && document.body.contains(frm._dg_canvas.$page[0])) {
		return;
	}
	if (typeof DocumentCanvas === "undefined" || frm._dg_mounting) return;

	frm._dg_mounting = true;
	$wrap.empty();
	const $host = $('<div class="dg-canvas-host"></div>').appendTo($wrap);
	const sync = frappe.utils.debounce(() => sync_canvas_to_sections(frm), 600);

	// Seed from the server so table sections get a config-driven preview + geometry.
	frappe.call({
		method: `${DT_API}.get_template_for_design`,
		args: { template: frm.doc.name },
		callback: (r) => {
			frm._dg_mounting = false;
			if (frm._dg_canvas) frm._dg_canvas.destroy();
			frm._dg_canvas = new DocumentCanvas({
				$mount: $host,
				sections: (r.message && r.message.sections) || [],
				onChange: sync,
			});
		},
	});
}

// Write the canvas state back into the sections child table so a normal Save persists it.
function sync_canvas_to_sections(frm) {
	if (!frm._dg_canvas) return;
	const sections = frm._dg_canvas.get_sections();
	frm.clear_table("sections");
	sections.forEach((s) => {
		const row = frm.add_child("sections");
		row.section_title = s.section_title;
		row.section_type = s.section_type;
		row.content = s.content;
		row.config_json = s.config_json;
		row.default_enabled = s.enabled;
		row.is_mandatory = s.is_locked;
		row.align = s.align;
		row.width_pct = s.width_pct;
	});
	frm.refresh_field("sections");
	frm.dirty();
}
