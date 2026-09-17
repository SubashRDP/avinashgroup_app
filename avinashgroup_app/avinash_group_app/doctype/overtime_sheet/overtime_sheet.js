// Overtime Sheet — rows evaluate live as they are filled, so HR sees the day and
// what each person earns before saving; no times are entered (attendance gives them). The rules themselves are server-side only
// (avinashgroup_app.hr.overtime); this script just asks and shows the answer.
const OVERTIME_PREVIEW = "avinashgroup_app.hr.overtime.preview";

frappe.ui.form.on("Overtime Sheet", {
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

	work_date(frm) {
		(frm.doc.employees || []).forEach((row) => preview_row(frm, row.doctype, row.name));
	},
});

frappe.ui.form.on("Overtime Sheet Employee", {
	// A new person gets the work type their day implies; changing the date or the
	// work type re-checks it against the day.
	employee(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "work_type", "");
		preview_row(frm, cdt, cdn);
	},
	work_type: (frm, cdt, cdn) => preview_row(frm, cdt, cdn),
});

function preview_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.employee || !frm.doc.work_date) return;

	frappe
		.call(OVERTIME_PREVIEW, {
			employee: row.employee,
			work_date: frm.doc.work_date,
			work_type: row.work_type,
		})
		.then(({ message: r }) => {
			if (!r) return;
			if (!r.ok) {
				// Clear stale results so a refused row never shows an old entitlement.
				["day_type", "entitlement"].forEach((f) => frappe.model.set_value(cdt, cdn, f, ""));
				if (r.message) frappe.show_alert({ message: r.message, indicator: "orange" }, 7);
				return;
			}
			const values = {
				day_type: r.day_type,
				entitlement: r.entitlement,
				employee_category: r.employee_category,
				shift: r.shift,
			};
			// Only fill the work type when HR has not chosen one — never overwrite a choice.
			if (!row.work_type) values.work_type = r.work_type;
			frappe.model.set_value(cdt, cdn, values);
		});
}
