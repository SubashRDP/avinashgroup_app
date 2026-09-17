// Holiday Duty Sheet — keep the employee picker to active staff of the sheet's
// company. Rules live server-side in holiday_duty_sheet.py.
frappe.ui.form.on("Holiday Duty Sheet", {
	setup(frm) {
		frm.set_query("employee", "employees", () => ({
			filters: { company: frm.doc.company, status: "Active" },
		}));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},
});
