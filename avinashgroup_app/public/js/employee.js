// An employee's allowance (tea/meal) group belongs to their own company — the
// rates differ, so offering another company's group invites paying NGI's 235 a
// day to a Karnali employee.
frappe.ui.form.on("Employee", {
	setup(frm) {
		frm.set_query("custom_allowance_category", () => ({
			filters: { company: frm.doc.company },
		}));
	},
	company(frm) {
		if (frm.doc.custom_allowance_category) {
			frappe.db.get_value("Allowance Category", frm.doc.custom_allowance_category, "company").then((r) => {
				if (r.message && r.message.company !== frm.doc.company) {
					frm.set_value("custom_allowance_category", null);
				}
			});
		}
	},
});
