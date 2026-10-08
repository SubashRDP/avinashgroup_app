// Allowances on the assignment offer allowances only, not the Yearly or
// hand-entered kinds (paid when entered). The server checks the same on save
// (payroll/allowance.py).
frappe.ui.form.on("Salary Structure Assignment", {
	setup(frm) {
		frm.set_query("allowance", "custom_allowances", () => ({
			filters: {
				custom_is_allowance: 1,
				disabled: 0,
				custom_allowance_kind: ["not in", ["Entered by Hand", "Yearly"]],
			},
		}));
	},
});
