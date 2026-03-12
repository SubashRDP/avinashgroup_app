frappe.ui.form.on("Purchase Order", {
	before_workflow_action: function (frm) {
		if (frm.selected_workflow_action !== "Reject") return;

		if (!frm.doc.custom_approver || frm.doc.custom_approver !== frappe.session.user) {
			frappe.msgprint(__("Only the assigned approver can reject this document."));
			return Promise.reject("not_approver");
		}

		return new Promise((resolve, reject) => {
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
					d.hide();
					frappe.xcall("avinashgroup_app.custom_code.workflow.set_reject_reason", {
						doctype: frm.doctype,
						name: frm.doc.name,
						reason: reason.trim(),
					}).then(resolve).catch(reject);
				},
				secondary_action_label: __("Cancel"),
				secondary_action() {
					d.hide();
					reject("cancelled");
				},
			});
			d.show();
		});
	},
});
