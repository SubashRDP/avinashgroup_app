// Accounts in the Allowances table are offered only from this company, as
// ledgers. The Allowance column suggests the existing pay lines; a new name is
// created as a Salary Component on save.
frappe.ui.form.on("Company Allowance", {
	setup(frm) {
		for (const field of ["account_admin", "account_marketing", "account_plant"]) {
			frm.set_query(field, "allowances", () => ({
				filters: { company: frm.doc.company, is_group: 0 },
			}));
		}
	},
	onload(frm) {
		frappe.db
			.get_list("Salary Component", { fields: ["name"], limit: 0, order_by: "name asc" })
			.then((rows) => {
				const names = rows.map((r) => r.name);
				frm.fields_dict.allowances.grid.update_docfield_property("salary_component", "options", names);
			});
	},
});
