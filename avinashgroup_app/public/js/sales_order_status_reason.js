// Sales Order — ask for a reason on Hold, Close and Cancel, and keep it in the
// "Reason" field as "Hold: …", "Close: …" or "Cancel: …".
//
// The action runs first (ERPNext's update_status for Hold/Close, Frappe's own
// cancel), then custom_code/sales_order_status_reason.record_status_reason
// stores the reason and adds it to the timeline. So a failed action never
// leaves a reason behind.

const SO_RECORD_REASON = "avinashgroup_app.custom_code.sales_order_status_reason.record_status_reason";

// Opens the reason popup. on_submit(reason) runs when the user submits;
// on_dismiss runs if the popup is closed without submitting.
function so_ask_reason(title, on_submit, on_dismiss) {
	let submitted = false;
	const d = new frappe.ui.Dialog({
		title: title,
		fields: [{ fieldname: "reason", fieldtype: "Text", reqd: 1 }],
		primary_action_label: __("Submit"),
		primary_action(values) {
			submitted = true;
			d.hide();
			on_submit(values.reason);
		},
	});
	d.onhide = () => {
		if (!submitted && on_dismiss) on_dismiss();
	};
	d.show();
}

function so_record_reason(frm, action, reason) {
	return frappe.call({
		method: SO_RECORD_REASON,
		args: { sales_order: frm.docname, action: action, reason: reason },
	});
}

// Hold / Close: same server call as ERPNext's update_status, then the reason.
function so_status_with_reason(frm, action, status) {
	so_ask_reason(__("Reason for {0}", [__(action)]), (reason) => {
		frappe.ui.form.is_saving = true;
		// frappe.call returns a jQuery promise, which has no .finally();
		// wrap it so the form always reloads and is_saving is always reset.
		Promise.resolve(
			frappe.call({
				method: "erpnext.selling.doctype.sales_order.sales_order.update_status",
				args: { status: status, name: frm.doc.name },
				freeze: true,
			})
		)
			.then(() => so_record_reason(frm, action, reason))
			.finally(() => {
				frappe.ui.form.is_saving = false;
				frm.reload_doc();
			});
	});
}

function avinash_hold_sales_order() {
	so_status_with_reason(this.frm, "Hold", "On Hold");
}

function avinash_close_sales_order() {
	so_status_with_reason(this.frm, "Close", "Closed");
}

frappe.ui.form.on("Sales Order", {
	// Runs before the controller's refresh, which draws the Hold / Close
	// buttons pointing at these cscript methods.
	refresh(frm) {
		if (!frm.cscript) return;
		frm.cscript.hold_sales_order = avinash_hold_sales_order;
		frm.cscript.close_sales_order = avinash_close_sales_order;
	},

	// Frappe waits on this promise before cancelling. Closing the popup
	// without a reason stops the cancel.
	before_cancel(frm) {
		return new Promise((resolve) => {
			so_ask_reason(
				__("Reason for Cancel"),
				(reason) => {
					frm._so_cancel_reason = reason;
					resolve();
				},
				() => {
					frappe.validated = false;
					resolve();
				}
			);
		});
	},

	after_cancel(frm) {
		const reason = frm._so_cancel_reason;
		frm._so_cancel_reason = null;
		if (!reason) return;
		so_record_reason(frm, "Cancel", reason).then(() => frm.reload_doc());
	},
});
