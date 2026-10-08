// The Allowances table offers only what the employee's own company pays
// (Company Allowance): NGI's tea on a Karnali employee would be paid at a rate
// nobody set for Karnali. The server checks the same on save.
frappe.ui.form.on("Employee", {
	setup(frm) {
		frm.set_query("salary_component", "custom_attendance_allowances", () => ({
			query: "avinashgroup_app.payroll.company_allowance.allowance_query",
			filters: { company: frm.doc.company },
		}));
	},
});
