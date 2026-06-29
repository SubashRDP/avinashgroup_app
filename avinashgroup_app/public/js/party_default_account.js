// Customer/Supplier: keep one Default Accounts (accounts) row by default and
// auto-fill its Company with the selected company (custom_company).

frappe.ui.form.on("Customer", {
	refresh: ensure_default_account_row,
	custom_company: ensure_default_account_row,
});

frappe.ui.form.on("Supplier", {
	refresh: ensure_default_account_row,
	custom_company: ensure_default_account_row,
});

function ensure_default_account_row(frm) {
	const company = frm.doc.custom_company;
	if (!company) return;

	const rows = frm.doc.accounts || [];

	// No rows yet -> add one pre-filled with the selected company.
	if (!rows.length) {
		frm.add_child("accounts", { company: company });
		frm.refresh_field("accounts");
		return;
	}

	// Always keep the default row's company in sync with the selected company.
	if (rows[0].company !== company) {
		rows[0].company = company;
		frm.refresh_field("accounts");
	}
}
