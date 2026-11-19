// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.ui.form.on("Document Template", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.is_memo) {
			frm.add_custom_button(__("Preview"), () => preview_memo_template(frm)).addClass("btn-primary");
			return;
		}
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

// Show the memo paper for this template's CURRENT form values (unsaved edits
// included), drawn by the same print template as a real Memo Log. The approval
// box is not shown: it only prints on an approved memo.
function preview_memo_template(frm) {
	const d = frm.doc;
	const rows = Math.max(cint(d.memo_table_rows), 0);
	const cols = Math.max(cint(d.memo_table_columns), 0);
	const headings = (d.memo_table_headers || "")
		.split("\n")
		.map((h) => h.trim())
		.filter((h) => h);
	const grid = [];
	for (let r = 0; r < rows; r++) {
		grid.push(Array.from({ length: cols }, (_, c) => (r === 0 ? headings[c] || "" : "")));
	}

	const values = {
		memo_template: d.name,
		company: (d.companies || [])[0]?.company || frappe.defaults.get_user_default("Company") || "",
		posting_date: frappe.datetime.get_today(),
		memo_title: d.memo_title || "Internal Memo",
		memo_to: d.memo_to || "",
		memo_from: d.memo_from || "",
		memo_cc: d.memo_cc || "",
		subject: d.memo_subject || "",
		text_above: d.memo_text_above || "",
		text_below: d.memo_text_below || "",
		table_rows: rows,
		table_columns: cols,
		table_data: JSON.stringify(grid),
	};

	frappe.call({
		method: "avinashgroup_app.custom_code.document_generator.memo.preview_memo",
		args: { data: JSON.stringify(values) },
		freeze: true,
		callback: (r) => {
			const page = `<!doctype html><html><head><meta charset="utf-8">
				<style>body{margin:0;padding:38px 45px;background:#fff}</style></head>
				<body>${r.message || ""}</body></html>`;
			const dialog = new frappe.ui.Dialog({ title: __("Memo Preview"), size: "large" });
			dialog.$body.html(
				`<iframe style="width:100%;height:75vh;border:0;background:#fff"
					srcdoc="${frappe.utils.escape_html(page)}"></iframe>`
			);
			dialog.show();
		},
	});
}
