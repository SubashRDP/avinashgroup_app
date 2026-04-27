frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		const workflow = window.avinashgroup_app && window.avinashgroup_app.approval_workflow;
		if (!workflow) return;

		const approval = workflow.applyPendingApprovalUi(frm, {
			currentApproverField: "custom_current_approver",
			currentLevelField: "custom_current_approval_level",
			totalLevelsField: "custom_total_approval_levels",
			approvalTableField: "custom_approval_approvers",
			visibleActions: ["Approve", "Reject"],
			onRender(state, form) {
				renderApprovalBanner(form, state);
			},
		});

		if (!approval || !approval.pending) return;
	},

	before_workflow_action(frm) {
		const workflow = window.avinashgroup_app && window.avinashgroup_app.approval_workflow;
		if (!workflow) return;

		return workflow.handleRejectAction(frm, {
			rejectReasonMethod: "avinashgroup_app.custom_code.workflow.set_reject_reason",
		});
	},
});

function renderApprovalBanner(frm, approval) {
	const current_level = approval.currentLevel || 0;
	const total_levels = approval.totalLevels || 0;
	const current_approver = approval.currentApprover || "";
	const already_approved_levels = approval.alreadyApprovedLevels || [];
	const already_approved = approval.alreadyApproved || false;
	const is_approver = approval.isApprover || false;

	if (current_level && total_levels) {
		const steps = [];
		for (let i = 1; i <= total_levels; i++) {
			if (i < current_level) {
				steps.push(`<span style="color:var(--green-500)">✔ Level ${i}</span>`);
			} else if (i === current_level) {
				steps.push(`<span style="color:var(--yellow-500);font-weight:600">⏳ Level ${i} (current)</span>`);
			} else {
				steps.push(`<span style="color:var(--gray-400)">◯ Level ${i}</span>`);
			}
		}

		let who;
		if (already_approved) {
			who = `<b style="color:var(--green-600)">You approved at Level ${already_approved_levels[already_approved_levels.length - 1]}.</b> Waiting for <b>${current_approver || "approver"}</b> at Level ${current_level}.`;
		} else if (is_approver) {
			who = `<b>Your approval is required at Level ${current_level}.</b>`;
		} else {
			who = `Waiting for <b>${current_approver || "approver"}</b> at Level ${current_level}.`;
		}

		const banner_color = already_approved ? "green" : is_approver ? "yellow" : "blue";
		frm.set_intro(
			`${steps.join("  →  ")}<br><small style="margin-top:4px;display:block">${who}</small>`,
			banner_color
		);
	}
}
