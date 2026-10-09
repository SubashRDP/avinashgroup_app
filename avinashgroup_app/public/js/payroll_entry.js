// Payroll Entry: choose Fiscal Year + Month (BS); the dates follow.
// The server fills the rest on save (payroll/payroll_month.py); this shows the
// month's dates as soon as it is picked, from the same calendar
// (hr/bs_calendar.py, Nepal BS Period first), and locks the English date
// fields so a typed date cannot move the payroll into another month.

const BS_CALENDAR = "avinashgroup_app.hr.bs_calendar";
const BS_LOCKED_FIELDS = ["posting_date", "start_date", "end_date", "payroll_frequency"];

function lock_bs_dates(frm) {
	const locked = !!(frm.doc.custom_fiscal_year && frm.doc.custom_bs_month);
	BS_LOCKED_FIELDS.forEach((f) => frm.set_df_property(f, "read_only", locked ? 1 : 0));
}

function show_bs_month(frm) {
	const { custom_fiscal_year: fiscal_year, custom_bs_month: bs_month, company } = frm.doc;
	lock_bs_dates(frm);
	if (frm.doc.docstatus !== 0 || !fiscal_year || !bs_month) return;
	frappe.call({
		method: `${BS_CALENDAR}.get_month`,
		args: { fiscal_year, bs_month, company },
		callback: (r) => {
			const p = r.message;
			// A newer pick may have come in while this call was out.
			if (!p || frm.doc.custom_fiscal_year !== fiscal_year || frm.doc.custom_bs_month !== bs_month) return;
			// Set on the doc directly: HRMS's own start/end/posting handlers
			// would otherwise recompute the dates from the AD calendar.
			Object.assign(frm.doc, {
				start_date: p.start_date,
				end_date: p.end_date,
				posting_date: p.end_date,
				payroll_frequency: "Monthly",
			});
			frm.refresh_fields();
			lock_bs_dates(frm);
			frappe.show_alert({
				message: __("{0}: {1} to {2}", [
					p.label,
					frappe.datetime.str_to_user(p.start_date),
					frappe.datetime.str_to_user(p.end_date),
				]),
				indicator: "blue",
			});
		},
	});
}

frappe.ui.form.on("Payroll Entry", {
	onload(frm) {
		if (!frm.is_new() || frm.doc.custom_bs_month) return;
		frappe.call({
			method: `${BS_CALENDAR}.get_default_month`,
			args: { company: frm.doc.company },
			callback: (r) => {
				if (!r.message || frm.doc.custom_bs_month) return;
				frm.doc.custom_fiscal_year = r.message.fiscal_year;
				frm.doc.custom_bs_month = r.message.bs_month;
				show_bs_month(frm);
			},
		});
	},
	custom_fiscal_year: show_bs_month,
	custom_bs_month: show_bs_month,
	company: show_bs_month,

	refresh(frm) {
		lock_bs_dates(frm);
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
								const refreshed = r.message.slips_refreshed || 0;
								let msg = __("{0} allowance and fine records, {1} advance instalments.", [created, recovered]);
								if (refreshed) {
									msg += " " + __("{0} draft salary slips updated.", [refreshed]);
								}
								if (skipped) {
									msg += " " + __("{0} skipped — see Error Log.", [skipped]);
								}
								frm.reload_doc();
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
