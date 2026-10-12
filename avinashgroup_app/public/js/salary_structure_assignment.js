// Allowances on the assignment: the allowances this person gets, at their rate.
// Picking an allowance fills its Rate from the salary structure's Allowance
// Rates; change it for this person. Yearly and hand-entered allowances are paid
// when entered, so they are not offered. The server checks the same on save
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

frappe.ui.form.on("Assignment Allowance", {
	allowance(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.allowance) {
			frappe.model.set_value(cdt, cdn, "unit", "");
			return;
		}
		if (!frm.doc.salary_structure) {
			frappe.show_alert({ message: __("Pick the Salary Structure first: it holds the usual rates"), indicator: "orange" });
		}
		frappe.call({
			method: "avinashgroup_app.payroll.allowance.get_rate_for_assignment",
			args: { salary_structure: frm.doc.salary_structure || "", allowance: row.allowance },
			callback(r) {
				if (!r.message) return;
				frappe.model.set_value(cdt, cdn, "unit", r.message.unit);
				frappe.model.set_value(cdt, cdn, "rate", r.message.rate);
			},
		});
	},
});
