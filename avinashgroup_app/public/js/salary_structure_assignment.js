// Allowances on the assignment: the allowances this person gets, at their rate.
// Picking the Salary Structure on a draft replaces the Allowances table with the
// structure's Allowance Rates (get_structure_allowances): remove the ones this
// person does not get and type the rates left at 0. Picking an allowance on a
// row fills its Rate from the structure; change it for this person. Yearly and
// hand-entered allowances are paid when entered, so they are not offered. The
// server checks the same on save (payroll/allowance.py).
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

	salary_structure(frm) {
		if (frm.doc.docstatus !== 0 || !frm.doc.salary_structure) return;
		frappe.call({
			method: "avinashgroup_app.payroll.allowance.get_structure_allowances",
			args: { salary_structure: frm.doc.salary_structure },
			callback(r) {
				frm.clear_table("custom_allowances");
				(r.message || []).forEach((d) =>
					frm.add_child("custom_allowances", { allowance: d.allowance, rate: d.rate, unit: d.unit })
				);
				frm.refresh_field("custom_allowances");
			},
		});
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
