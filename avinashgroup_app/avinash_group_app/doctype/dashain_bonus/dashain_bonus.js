// Dashain Bonus — one button fills the year, the rows stay editable after it.
frappe.ui.form.on("Dashain Bonus", {
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
		if (frm.doc.docstatus === 0 && frm.doc.bonus_given) {
			frm.add_custom_button(__("Get Employees"), () => get_employees(frm)).addClass(
				"btn-primary"
			);
		}
	},

	// The rule decides every row, so changing it after the table is filled has
	// to redraw the table — otherwise the amounts quietly belong to the old rule.
	basis: (frm) => refill(frm),
	percentage: (frm) => refill(frm),
	prorate_new_joiners: (frm) => refill(frm),
	minimum_months: (frm) => refill(frm),
});

frappe.ui.form.on("Dashain Bonus Employee", {
	amount(frm) {
		set_total(frm);
	},
	employees_remove(frm) {
		set_total(frm);
	},
});

function get_employees(frm) {
	frappe.call({
		doc: frm.doc,
		method: "get_employees",
		freeze: true,
		freeze_message: __("Working out everyone's months of service…"),
		callback(r) {
			frm.refresh_field("employees");
			frm.refresh_field("total_amount");
			frm.refresh_field("employee_count");
			frappe.show_alert({
				message: __("{0} employees", [r.message || 0]),
				indicator: "green",
			});
		},
	});
}

function refill(frm) {
	if (frm.doc.docstatus === 0 && (frm.doc.employees || []).length) {
		get_employees(frm);
	}
}

function set_total(frm) {
	let total = 0;
	(frm.doc.employees || []).forEach((row) => {
		total += flt(row.amount);
	});
	frm.set_value("total_amount", total);
	frm.set_value("employee_count", (frm.doc.employees || []).length);
}
