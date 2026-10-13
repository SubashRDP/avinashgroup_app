// Leave Encashment list: "Encash Year-End Balances" (payroll/leave_encashment.py
// encash_year_end). One press per company and fiscal year, in the year's last
// month (Ashadh): every active employee's remaining balance on each encashable
// leave type becomes a DRAFT Leave Encashment dated the year's last day, shown
// here for review. HR then selects them and submits (Actions → Submit); each
// submitted one is paid on the Ashadh salary slip. Pressing again rebuilds the
// drafts and never touches a submitted one.
frappe.listview_settings["Leave Encashment"] = Object.assign(frappe.listview_settings["Leave Encashment"] || {}, {
	onload(listview) {
		if (!frappe.model.can_create("Leave Encashment")) return;
		listview.page.add_inner_button(__("Encash Year-End Balances"), () => encash_year_end(listview));
	},
});

function encash_year_end(listview) {
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));
	const money = (v) => format_currency(v || 0);
	const dlg = new frappe.ui.Dialog({
		title: __("Encash Year-End Balances"),
		fields: [
			{ fieldname: "company", fieldtype: "Link", options: "Company", label: __("Company"), reqd: 1,
			  default: frappe.defaults.get_user_default("Company") },
			{ fieldname: "fiscal_year", fieldtype: "Link", options: "Fiscal Year", label: __("Fiscal Year"), reqd: 1,
			  default: frappe.defaults.get_user_default("fiscal_year") },
			{ fieldtype: "HTML", options: `<p class="text-muted small">${__(
				"Only leave types with Allow Encashment are encashed. Days × (monthly basic ÷ the Leave Type's days per month). Drafts only: you submit them after checking."
			)}</p>` },
		],
		primary_action_label: __("Make Drafts"),
		primary_action(v) {
			dlg.hide();
			frappe.dom.freeze(__("Working out leave balances..."));
			frappe.call({ method: "avinashgroup_app.payroll.leave_encashment.encash_year_end", args: v })
				.then(({ message: r }) => {
					frappe.dom.unfreeze();
					if (!r) return;
					const rows = r.created
						.map((c) => `<tr><td><a href="/app/leave-encashment/${encodeURIComponent(c.name)}">${esc(c.employee_name || c.employee)}</a></td>
							<td>${esc(c.leave_type)}</td><td class="text-right">${esc(c.balance)}</td><td class="text-right">${esc(c.days)}</td>
							<td class="text-right">${money(c.rate)}</td><td class="text-right">${money(c.amount)}</td></tr>`)
						.join("");
					const left = (r.left_out || [])
						.map((x) => `<tr><td>${esc(x.employee_name || x.employee)}</td><td>${esc(x.leave_type)}</td><td>${esc(x.reason)}</td></tr>`)
						.join("");
					frappe.msgprint({
						title: __("{0} drafts, total {1}", [r.created.length, money(r.total)]),
						indicator: r.created.length ? "green" : "orange",
						wide: true,
						message: (rows
							? `<div style="max-height:340px;overflow:auto"><table class="table table-sm table-bordered">
								<tr><th>${__("Employee")}</th><th>${__("Leave Type")}</th><th>${__("Balance")}</th><th>${__("Days Encashed")}</th>
								<th>${__("Rate/Day")}</th><th>${__("Amount")}</th></tr>${rows}</table></div>
								<p class="text-muted">${__("Check them, then select the drafts in this list → Actions → Submit.")}</p>`
							: `<p>${__("Nothing to encash.")}</p>`)
							+ (left ? `<p class="mt-3"><b>${__("Not included")} (${r.left_out.length})</b></p>
								<div style="max-height:200px;overflow:auto"><table class="table table-sm table-bordered">${left}</table></div>` : ""),
					});
					listview.refresh();
				})
				.catch(() => frappe.dom.unfreeze());
		},
	});
	dlg.show();
}
