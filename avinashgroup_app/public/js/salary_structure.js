// Allowance Rates on the structure: the usual rate of each allowance, copied
// onto an assignment when HR picks the allowance there. A submitted
// structure's existing rate changes only through a Salary Revision (Raise
// Rate), which moves the people on it too (payroll/allowance.py).
frappe.ui.form.on("Salary Structure", {
	setup(frm) {
		frm.set_query("allowance", "custom_allowance_rates", () => ({
			filters: {
				custom_is_allowance: 1,
				disabled: 0,
				custom_allowance_kind: ["not in", ["Entered by Hand", "Yearly"]],
			},
		}));
	},
});
