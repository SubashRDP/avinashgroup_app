// Copyright (c) 2026, Raindrop and contributors
// For license information, please see license.txt

frappe.ui.form.on("Memo Log", {
	setup(frm) {
		frm.set_query("memo_template", () => ({ filters: { is_memo: 1, is_active: 1 } }));
		frm.set_query("custom_department", () => ({
			filters: frm.doc.company ? { company: frm.doc.company } : {},
		}));
	},

	refresh(frm) {
		// Button first, so a problem drawing the table can never hide it.
		if (!frm.is_new()) {
			frm.add_custom_button(__("Generate Memo"), () => show_memo_paper(frm)).addClass("btn-primary");
		}
		try {
			render_table_editor(frm);
		} catch (e) {
			console.error("Memo Log: could not draw the table editor", e);
		}
	},

	company(frm) {
		frm.set_value("custom_department", "");
	},

	// Copy the template's memo text and table size into this memo.
	memo_template(frm) {
		if (!frm.doc.memo_template) return;
		frappe.db.get_doc("Document Template", frm.doc.memo_template).then((t) => {
			frm.set_value({
				memo_title: t.memo_title || "Internal Memo",
				memo_to: t.memo_to || "",
				memo_from: t.memo_from || "",
				memo_cc: t.memo_cc || "",
				subject: t.memo_subject || "",
				text_above: t.memo_text_above || "",
				text_below: t.memo_text_below || "",
			});

			const rows = cint(t.memo_table_rows);
			const cols = cint(t.memo_table_columns);
			const headings = (t.memo_table_headers || "")
				.split("\n")
				.map((h) => h.trim())
				.filter((h) => h);
			const grid = make_grid([], rows, cols);
			if (rows > 0) {
				headings.slice(0, cols).forEach((h, c) => (grid[0][c] = h));
			}
			// Setting Rows fires resize_table while Columns is still the old value, which
			// would cut every row to 0 cells and lose the headings. So skip resizing
			// while the template loads, then put the grid in.
			frm._memo_loading = true;
			frm.set_value({ table_rows: rows, table_columns: cols }).then(() => {
				frm._memo_loading = false;
				frm.set_value("table_data", JSON.stringify(grid));
				render_table_editor(frm);
			});
		});
	},

	table_rows(frm) {
		resize_table(frm);
	},

	table_columns(frm) {
		resize_table(frm);
	},
});

// Show this memo's paper (saved values) in a popup, with Print and PDF buttons.
// Same Jinja template as the "Memo Log" print format; the approval box appears
// once the memo is approved.
function show_memo_paper(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Please save the memo first."));
		return;
	}
	const print_params = (extra) =>
		new URLSearchParams(
			Object.assign({ doctype: "Memo Log", name: frm.doc.name, format: "Memo Log", no_letterhead: 1 }, extra)
		).toString();

	frappe.call({
		method: "avinashgroup_app.custom_code.document_generator.memo.get_memo_html",
		args: { name: frm.doc.name },
		freeze: true,
		callback: (r) => {
			const page = `<!doctype html><html><head><meta charset="utf-8">
				<style>body{margin:0;padding:38px 45px;background:#fff}</style></head>
				<body>${r.message || ""}</body></html>`;
			const dialog = new frappe.ui.Dialog({
				title: frm.doc.custom_branch_name || frm.doc.name,
				size: "extra-large",
				primary_action_label: __("Print"),
				primary_action: () => window.open(`/printview?${print_params({ trigger_print: 1 })}`, "_blank"),
				secondary_action_label: __("Download PDF"),
				secondary_action: () =>
					window.open(`/api/method/frappe.utils.print_format.download_pdf?${print_params({})}`, "_blank"),
			});
			dialog.$body.html(
				`<div style="background:#f0f0f0;padding:12px">
					<iframe style="display:block;width:100%;max-width:794px;height:75vh;margin:0 auto;border:0;
						background:#fff;box-shadow:0 1px 6px rgba(0,0,0,.18)"
						srcdoc="${frappe.utils.escape_html(page)}"></iframe>
				</div>`
			);
			dialog.show();
		},
	});
}

function read_grid(frm) {
	try {
		const grid = JSON.parse(frm.doc.table_data || "[]");
		return Array.isArray(grid) ? grid : [];
	} catch (e) {
		return [];
	}
}

// Build a rows x cols grid, keeping any old cell values that still fit.
function make_grid(old_grid, rows, cols) {
	const grid = [];
	for (let r = 0; r < rows; r++) {
		const old_row = Array.isArray(old_grid[r]) ? old_grid[r] : [];
		const row = [];
		for (let c = 0; c < cols; c++) {
			row.push(old_row[c] != null ? String(old_row[c]) : "");
		}
		grid.push(row);
	}
	return grid;
}

function resize_table(frm) {
	if (frm._memo_loading) return;
	const rows = Math.max(cint(frm.doc.table_rows), 0);
	const cols = Math.max(cint(frm.doc.table_columns), 0);
	const grid = make_grid(read_grid(frm), rows, cols);
	frm.set_value("table_data", JSON.stringify(grid));
	render_table_editor(frm);
}

// Draw the grid as text boxes. Row 1 is the heading row (shown bold).
function render_table_editor(frm) {
	const wrapper = frm.get_field("table_editor").$wrapper;
	const rows = Math.max(cint(frm.doc.table_rows), 0);
	const cols = Math.max(cint(frm.doc.table_columns), 0);
	if (!rows || !cols) {
		wrapper.empty();
		return;
	}

	const grid = make_grid(read_grid(frm), rows, cols);
	const read_only = frm.doc.docstatus !== 0 || !frm.perm[0] || !frm.perm[0].write;

	let html = `<div style="overflow-x:auto"><table class="table table-bordered" style="margin:0">`;
	grid.forEach((row, r) => {
		html += "<tr>";
		row.forEach((value, c) => {
			const style = r === 0 ? "font-weight:bold;text-align:center" : "";
			html += `<td style="padding:2px;min-width:90px">
				<input type="text" class="form-control input-xs memo-cell" data-r="${r}" data-c="${c}"
					style="${style}" value="${frappe.utils.escape_html(value)}" ${read_only ? "disabled" : ""}>
			</td>`;
		});
		html += "</tr>";
	});
	html += `</table></div>
		<div class="text-muted small" style="margin-top:4px">${__("Row 1 is the heading row.")}</div>`;

	wrapper.html(html);
	wrapper.find(".memo-cell").on("change", function () {
		const current = make_grid(read_grid(frm), rows, cols);
		current[$(this).data("r")][$(this).data("c")] = $(this).val();
		frm.set_value("table_data", JSON.stringify(current));
	});
}
