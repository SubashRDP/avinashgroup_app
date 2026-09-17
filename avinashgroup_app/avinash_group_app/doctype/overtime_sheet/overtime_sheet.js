// Overtime Sheet — rows evaluate live as they are filled, so HR sees what each
// person earns before saving. The rules themselves are server-side only
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
	employee: (frm, cdt, cdn) => preview_row(frm, cdt, cdn),
	from_time: (frm, cdt, cdn) => preview_row(frm, cdt, cdn),
	to_time: (frm, cdt, cdn) => preview_row(frm, cdt, cdn),
});

function preview_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.employee || !frm.doc.work_date) return;

	frappe
		.call(OVERTIME_PREVIEW, {
			employee: row.employee,
			work_date: frm.doc.work_date,
			from_time: row.from_time,
			to_time: row.to_time,
		})
		.then(({ message: r }) => {
			if (!r) return;
			if (!r.ok) {
				// Clear stale results so a refused row never shows an old entitlement.
				["day_type", "entitlement", "overtime_hours"].forEach((f) =>
					frappe.model.set_value(cdt, cdn, f, f === "overtime_hours" ? 0 : ""),
				);
				if (r.message) frappe.show_alert({ message: r.message, indicator: "orange" }, 7);
				return;
			}
			frappe.model.set_value(cdt, cdn, {
				day_type: r.day_type,
				entitlement: r.entitlement,
				employee_category: r.employee_category,
				shift: r.shift,
				overtime_hours: r.overtime_hours,
			});
		});
}
