// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.ui.form.on("Document Template", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Preview"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Please save the template before previewing."));
				return;
			}
			frappe.call({
				method: "avinashgroup_app.custom_code.document_generator.api.preview_template",
				args: { template: frm.doc.name },
				freeze: true,
				callback: (r) => {
					const d = new frappe.ui.Dialog({ title: __("Preview (sample data)"), size: "large" });
					d.$body.html(
						`<iframe style="width:100%;height:70vh;border:0;background:#fff"
							srcdoc="${frappe.utils.escape_html(r.message || "")}"></iframe>`
					);
					d.show();
				},
			});
		});
	},
});
