// Salary Revision — type a percent or type an amount; the other one follows.
// Allowance changes and arrears are worked out on the server when the form is
// saved (salary_revision.py), so what the form shows is what will be paid.
const NOT_ON_ASSIGNMENT = ["Entered by Hand", "Yearly"];

frappe.ui.form.on("Salary Revision", {
	setup(frm) {
		frm.set_query("employee", "employees", () => ({
			filters: { company: frm.doc.company, status: "Active" },
		}));
		frm.set_query("allowance", "allowance_changes", () => ({
			filters: {
				custom_is_allowance: 1,
				disabled: 0,
				custom_allowance_kind: ["not in", NOT_ON_ASSIGNMENT],
			},
		}));
		frm.set_query("salary_structure", "allowance_changes", () => ({
			filters: { company: frm.doc.company, docstatus: 1 },
		}));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Employees"), () => get_employees(frm)).addClass(
				"btn-primary"
			);
		}
	},

	default_increment_percent(frm) {
		if ((frm.doc.employees || []).length) {
			get_employees(frm);
		}
	},
});

frappe.ui.form.on("Salary Revision Row", {
	increment_percent(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(
			cdt,
			cdn,
			"new_base",
			flt(row.current_base) * (1 + flt(row.increment_percent) / 100)
		);
	},

	new_base(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (flt(row.current_base)) {
			const percent = ((flt(row.new_base) - flt(row.current_base)) / flt(row.current_base)) * 100;
			if (Math.abs(percent - flt(row.increment_percent)) > 0.01) {
				frappe.model.set_value(cdt, cdn, "increment_percent", percent);
			}
		}
	},
});

function get_employees(frm) {
	frappe.call({
		doc: frm.doc,
		method: "get_employees",
		freeze: true,
		freeze_message: __("Reading everyone's current salary…"),
		callback(r) {
			frm.refresh_fields();
			frappe.show_alert({
				message: __("{0} employees", [r.message || 0]),
				indicator: "green",
			});
		},
	});
}
