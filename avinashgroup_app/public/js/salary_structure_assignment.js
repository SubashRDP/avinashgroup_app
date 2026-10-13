// Allowances on the assignment: the allowances this person gets, at their rate.
// Picking the Salary Structure on a draft lists its Allowance Rates here as a
// starting point (get_structure_allowances): remove the ones this person does
// not get and type the rates left at 0. Rows already there are replaced only
// after a confirm. Picking an allowance on a row fills its Rate from the
// structure; change it for this person. Yearly and hand-entered allowances are
// paid when entered, so they are not offered. The server checks the same on
// save (payroll/allowance.py).
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
				const rows = r.message || [];
				if (!rows.length) {
					frappe.show_alert({
						message: __("{0} lists no Allowance Rates: add this person's allowances by hand", [
							frm.doc.salary_structure,
						]),
						indicator: "orange",
					});
					return;
				}
				const existing = (frm.doc.custom_allowances || []).filter((d) => d.allowance);
				if (!existing.length) {
					fill_allowances(frm, rows);
					return;
				}
				const key = (list) =>
					list
						.map((d) => `${d.allowance}|${flt(d.rate)}`)
						.sort()
						.join("\n");
				if (key(existing) === key(rows)) return;
				frappe.confirm(
					__(
						"Replace the {0} allowance row(s) already on this assignment with the {1} allowances of {2}? Rates typed for this person will be lost.",
						[existing.length, rows.length, frm.doc.salary_structure]
					),
					() => fill_allowances(frm, rows)
				);
			},
		});
	},
});

function fill_allowances(frm, rows) {
	frm.clear_table("custom_allowances");
	rows.forEach((d) =>
		frm.add_child("custom_allowances", { allowance: d.allowance, rate: d.rate, unit: d.unit })
	);
	frm.refresh_field("custom_allowances");
	frm.dirty();
	const to_type = rows.filter((d) => !flt(d.rate) && !d.computed);
	frappe.show_alert({
		message: to_type.length
			? __("Allowances filled from the structure. Remove those this person does not get, and type the rate for: {0}", [
					to_type.map((d) => d.allowance).join(", "),
			  ])
			: __("Allowances filled from the structure. Remove those this person does not get."),
		indicator: "blue",
	}, 10);
}

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
