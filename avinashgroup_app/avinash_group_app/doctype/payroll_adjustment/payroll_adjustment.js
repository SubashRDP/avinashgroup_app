// Payroll Adjustment — keep the pickers to what the month can actually use.
frappe.ui.form.on("Payroll Adjustment", {
	setup(frm) {
		frm.set_query("employee", "adjustments", () => ({
			filters: { company: frm.doc.company, status: "Active" },
		}));
		// Attendance-driven components are posted by the allowance engine; typing
		// one here would sit beside what the engine already paid.
		frm.set_query("salary_component", "adjustments", () => ({
			filters: { custom_is_attendance_driven: 0, disabled: 0 },
		}));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},
});
