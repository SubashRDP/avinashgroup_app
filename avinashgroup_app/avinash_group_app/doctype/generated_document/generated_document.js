// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

const DG_API = "avinashgroup_app.custom_code.document_generator.api";

frappe.ui.form.on("Generated Document", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Edit in Generator"), () => {
				frappe.route_options = { generated_document: frm.doc.name };
				frappe.set_route("document-generator");
			});
		}
		render_preview(frm);
	},
});

// Render the saved document read-only (no inline editing). Edits happen via the
// "Edit in Generator" button, which reopens the Document Generator page.
function render_preview(frm) {
	const field = frm.get_field("rendered_document");
	if (!field || !field.$wrapper) return;
	const $wrap = field.$wrapper;

	if (frm.is_new() || !frm.doc.body_html) {
		$wrap.html(`<div class="text-muted">${__("Nothing to preview yet.")}</div>`);
		return;
	}

	$wrap.html(`<div class="text-muted">${__("Loading preview…")}</div>`);
	frappe.call({
		method: `${DG_API}.get_generated_document_html`,
		args: { name: frm.doc.name },
		callback: (r) => {
			if (!r || !r.message) {
				$wrap.html(`<div class="text-muted">${__("Could not load preview.")}</div>`);
				return;
			}
			const iframe = document.createElement("iframe");
			iframe.style.width = "100%";
			iframe.style.minHeight = "700px";
			iframe.style.border = "1px solid var(--border-color, #d1d8dd)";
			iframe.style.borderRadius = "var(--border-radius-md, 6px)";
			iframe.style.background = "#fff";
			iframe.setAttribute("sandbox", "allow-same-origin");
			iframe.srcdoc = r.message;
			$wrap.empty().append(iframe);
		},
	});
}
