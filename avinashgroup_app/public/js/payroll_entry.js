frappe.ui.form.on("Payroll Entry", {
	refresh(frm) {
		if (frm.doc.docstatus === 2) return;

		frm.add_custom_button(
			__("Calculate Attendance Allowances"),
			() => {
				frappe.confirm(
					__(
						"Re-create Additional Salary drafts for all attendance-driven Salary Components on this Payroll Entry? Existing drafts tagged by this calculator will be replaced."
					),
					() => {
						frappe.dom.freeze(__("Computing attendance allowances..."));
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
								let msg = __("{0} Additional Salary records created.", [created]);
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
