frappe.ui.form.on("Payroll Entry", {
	refresh(frm) {
		if (frm.doc.docstatus === 2) return;

		frm.add_custom_button(
			__("Prepare Payroll Inputs"),
			() => {
				frappe.confirm(
					__(
						"Work out this month's tea, meals, overtime and late fines from attendance, and take this month's advance instalments? Anything this button posted before for the month is replaced."
					),
					() => {
						frappe.dom.freeze(__("Preparing payroll inputs..."));
						frappe
							.call({
								method: "avinashgroup_app.payroll.attendance_allowance.trigger_for_payroll_entry",
								args: { payroll_entry: frm.doc.name },
							})
							.then((r) => {
								frappe.dom.unfreeze();
								if (!r || !r.message) return;
								const created = r.message.created || 0;
								const skipped = r.message.skipped || 0;
								const recovered = r.message.advance_recoveries || 0;
								let msg = __("{0} allowance and fine records, {1} advance instalments.", [created, recovered]);
								if (skipped) {
									msg += " " + __("{0} skipped — see Error Log.", [skipped]);
								}
								frappe.show_alert({
									message: msg,
									indicator: skipped ? "orange" : created ? "green" : "orange",
								});
							})
							.catch(() => frappe.dom.unfreeze());
					}
				);
			},
			__("Nepal HRMS")
		);
	},
});
