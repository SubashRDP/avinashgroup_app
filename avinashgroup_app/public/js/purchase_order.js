frappe.ui.form.on("Purchase Order", {
	before_workflow_action: function (frm) {
		if (frm.selected_workflow_action !== "Reject") return;

		return new Promise((resolve, reject) => {
			let settled = false;
			let is_submitting = false;
			const resolveOnce = (value) => {
				if (settled) return;
				settled = true;
				resolve(value);
			};
			const rejectOnce = (reason) => {
				if (settled) return;
				settled = true;
				reject(reason);
			};
			let d = new frappe.ui.Dialog({
				title: __("Rejection Reason"),
				fields: [
					{
						fieldtype: "Small Text",
						fieldname: "reject_reason",
						label: __("Reason for Rejection"),
						reqd: 1,
					},
				],
				primary_action_label: __("Reject"),
				primary_action() {
					let reason = d.get_value("reject_reason");
					if (!reason || !reason.trim()) {
						frappe.msgprint(__("Please enter a rejection reason."));
						return;
					}
					is_submitting = true;
					d.hide();
					frappe.dom.freeze(__("Submitting rejection..."));
					frappe.xcall("avinashgroup_app.custom_code.workflow.set_reject_reason", {
						doctype: frm.doctype,
						name: frm.doc.name,
						reason: reason.trim(),
					})
						.then(() => {
							frappe.msgprint(__("Rejection recorded successfully"));
							resolveOnce();
						})
						.catch((error) => {
							frappe.msgprint(__("Error saving rejection reason"));
							console.error(error);
							rejectOnce(error);
						})
						.finally(() => {
							frappe.dom.unfreeze();
						});
				},
				secondary_action_label: __("Cancel"),
				secondary_action() {
					d.hide();
					rejectOnce("cancelled");
				},
			});
			d.onhide = () => {
				// If user closes the dialog via X/ESC, do not leave the promise pending.
				if (is_submitting) return;
				rejectOnce("dialog_closed");
			};
			d.show();
			// Allow typing in the dialog while workflow waits on the promise.
			frappe.dom.unfreeze();
		});
	},
});
