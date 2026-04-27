frappe.ui.form.on("Material Request", {
	before_workflow_action: function (frm) {
		const workflow = window.avinashgroup_app && window.avinashgroup_app.approval_workflow;
		if (!workflow) return;

		return workflow.handleRejectAction(frm, {
			rejectReasonMethod: "avinashgroup_app.custom_code.workflow.set_reject_reason",
		});
	},
});
