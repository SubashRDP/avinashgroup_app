// PDC Cheque list: status colours, "due" highlighting, and bulk Deposit / Clear.
// Bulk steps run pdc/lifecycle.py bulk_action, one savepoint per cheque.

frappe.listview_settings["PDC Cheque"] = {
	add_fields: ["status", "cheque_type", "cheque_date", "docstatus"],
	has_indicator_for_draft: 1,

	get_indicator(doc) {
		if (doc.docstatus === 0) return [__("Draft"), "red", "docstatus,=,0"];
		const due = doc.cheque_date && doc.cheque_date <= frappe.datetime.get_today();
		if (doc.status === "In Hand" && due) return [__("Due for Deposit"), "red", "status,=,In Hand"];
		const colour = {
			"In Hand": "orange",
			Issued: "orange",
			Deposited: "blue",
			Cleared: "green",
			Bounced: "red",
			Returned: "grey",
			Replaced: "grey",
			Cancelled: "grey",
		}[doc.status];
		return [__(doc.status), colour || "grey", `status,=,${doc.status}`];
	},

	onload(listview) {
		listview.page.add_actions_menu_item(__("Deposit Selected"), () => bulk(listview, "deposit"));
		listview.page.add_actions_menu_item(__("Clear Selected"), () => bulk(listview, "clear"));
	},
};

function bulk(listview, action) {
	const names = listview.get_checked_items(true);
	if (!names.length) {
		frappe.msgprint(__("Tick the cheques first."));
		return;
	}
	const d = new frappe.ui.Dialog({
		title: action === "deposit" ? __("Deposit {0} Cheques", [names.length]) : __("Clear {0} Cheques", [names.length]),
		fields: [
			{ fieldname: "posting_date", fieldtype: "Date", label: __("Date"), reqd: 1, default: frappe.datetime.get_today() },
			{
				fieldname: "bank_account",
				fieldtype: "Link",
				options: "Account",
				label: __("Bank Account"),
				reqd: action === "deposit" ? 1 : 0,
				description:
					action === "clear"
						? __("Leave empty to clear each cheque into the account it was deposited to / written on")
						: "",
				get_query: () => ({ filters: { is_group: 0, account_type: ["in", ["Bank", "Cash"]] } }),
			},
		],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: "avinashgroup_app.pdc.lifecycle.bulk_action",
				args: Object.assign({ names, action }, values),
				freeze: true,
				freeze_message: __("Working through {0} cheques…", [names.length]),
				callback: ({ message: r }) => {
					let html = `<p>${__("Done")}: <b>${r.done.length}</b></p>`;
					if (r.failed.length) {
						html += `<p>${__("Not done")}: <b>${r.failed.length}</b></p><ul>`;
						r.failed.forEach((f) => (html += `<li><b>${f.name}</b>: ${frappe.utils.escape_html(f.error)}</li>`));
						html += "</ul>";
					}
					frappe.msgprint({ title: __("Bulk {0}", [action]), message: html, indicator: r.failed.length ? "orange" : "green" });
					listview.refresh();
				},
			});
		},
	});
	d.show();
}
