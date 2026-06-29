// Item: keep one Item Defaults (item_defaults) row by default and auto-fill its
// Company with the selected company (custom_company).

frappe.ui.form.on("Item", {
	refresh: ensure_default_item_row,
	custom_company: ensure_default_item_row,
});

function ensure_default_item_row(frm) {
	const company = frm.doc.custom_company;
	if (!company) return;

	const rows = frm.doc.item_defaults || [];

	// No rows yet -> add one pre-filled with the selected company.
	if (!rows.length) {
		frm.add_child("item_defaults", { company: company });
		frm.refresh_field("item_defaults");
		return;
	}

	// Always keep the default row's company in sync with the selected company.
	if (rows[0].company !== company) {
		rows[0].company = company;
		frm.refresh_field("item_defaults");
	}
}
