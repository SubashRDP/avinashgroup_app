// Salary Revision — type a percent or type an amount; the other one follows.
frappe.ui.form.on("Salary Revision", {
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
		set_arrears(frm, row);
		set_totals(frm);
	},

	new_dearness_allowance(frm, cdt, cdn) {
		set_arrears(frm, locals[cdt][cdn]);
		set_totals(frm);
	},

	arrears_amount(frm) {
		set_totals(frm);
	},

	employees_remove(frm) {
		set_totals(frm);
	},
});

// Arrears are the monthly difference times the months already paid at the old
// rate, so any change to the new pay has to redraw them.
function set_arrears(frm, row) {
	if (!frm.doc.pay_arrears) {
		return;
	}
	const difference =
		flt(row.new_base) +
		flt(row.new_dearness_allowance) -
		flt(row.current_base) -
		flt(row.current_dearness_allowance);
	frappe.model.set_value(
		row.doctype,
		row.name,
		"arrears_amount",
		difference * flt(row.arrears_months)
	);
}

function get_employees(frm) {
	frappe.call({
		doc: frm.doc,
		method: "get_employees",
		freeze: true,
		freeze_message: __("Reading everyone's current salary…"),
		callback(r) {
			frm.refresh_field("employees");
			frm.refresh_field("total_increase");
			frm.refresh_field("employee_count");
			frappe.show_alert({
				message: __("{0} employees", [r.message || 0]),
				indicator: "green",
			});
		},
	});
}

function set_totals(frm) {
	let increase = 0;
	let arrears = 0;
	(frm.doc.employees || []).forEach((row) => {
		increase +=
			flt(row.new_base) +
			flt(row.new_dearness_allowance) -
			flt(row.current_base) -
			flt(row.current_dearness_allowance);
		arrears += flt(row.arrears_amount);
	});
	frm.set_value("total_increase", increase);
	frm.set_value("total_arrears", arrears);
	frm.set_value("employee_count", (frm.doc.employees || []).length);
}
