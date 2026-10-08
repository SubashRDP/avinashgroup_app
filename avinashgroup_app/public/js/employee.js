// The Allowance Exceptions table is for attendance allowances only (tea, meal,
// overtime); fixed ones are set in the Salary Structure. The server checks the
// same on save (payroll/allowance.py).
frappe.ui.form.on("Employee", {
	setup(frm) {
		frm.set_query("salary_component", "custom_attendance_allowances", () => ({
			filters: { custom_is_attendance_driven: 1, disabled: 0 },
		}));
	},
});
