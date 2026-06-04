/*
 * Dynamic Approval Workflow — Auto UI
 * -----------------------------------
 * Generic, doctype-agnostic wiring for ANY doctype that has a Dynamic
 * Approval workflow. A doctype "has" one as soon as `setup_workflow`
 * created its driver fields (custom_current_approver, ...), so onboarding
 * a new doctype needs ZERO new JS and ZERO hooks edits.
 *
 * Responsibilities:
 *   1. Render the level-progress banner ( ✔ Lvl1 → ⏳ Lvl2 → ◯ Lvl3 ).
 *   2. Hide Approve/Reject for non-current-approvers.
 *   3. Show the rejection-reason dialog on the Reject action.
 *
 * Form locking / field hiding for non-approvers is handled separately and
 * generically by approval_field_visibility.js. Loaded globally via
 * app_include_js in hooks.py.
 */

(function () {
	const FIELD_OPTS = {
		currentApproverField: "custom_current_approver",
		currentLevelField: "custom_current_approval_level",
		totalLevelsField: "custom_total_approval_levels",
		approvalTableField: "custom_approval_approvers",
	};
	const REJECT_METHOD = "avinashgroup_app.custom_code.workflow.set_reject_reason";

	// Doctypes we've already bound before_workflow_action on (bind once).
	const bound = new Set();

	function _has_approval_fields(frm) {
		return !!(frm && frm.fields_dict && frm.fields_dict[FIELD_OPTS.currentApproverField]);
	}

	// True if a per-doctype form script already declares its own
	// before_workflow_action handler (e.g. material_request.js). In that case
	// we must NOT add ours too, or the reject dialog would open twice.
	function _doctype_has_own_bwa_handler(doctype) {
		const h = frappe.ui.form.handlers;
		return !!(
			h &&
			h[doctype] &&
			Array.isArray(h[doctype].before_workflow_action) &&
			h[doctype].before_workflow_action.length
		);
	}

	function _render_banner(frm, approval) {
		const current_level = approval.currentLevel || 0;
		const total_levels = approval.totalLevels || 0;
		const current_approver = approval.currentApprover || "";
		const already_approved_levels = approval.alreadyApprovedLevels || [];
		const already_approved = approval.alreadyApproved || false;
		const is_approver = approval.isApprover || false;

		if (!current_level || !total_levels) return;

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

	$(document).on("form-refresh", function (e, frm) {
		const workflow = window.avinashgroup_app && window.avinashgroup_app.approval_workflow;
		if (!workflow || !_has_approval_fields(frm)) return;

		// 1 + 2. Banner and action-hiding (no-op unless Pending Approval).
		workflow.applyPendingApprovalUi(
			frm,
			Object.assign({}, FIELD_OPTS, {
				visibleActions: ["Approve", "Reject"],
				onRender(state, form) {
					_render_banner(form, state);
				},
			})
		);

		// 3. Lazily bind the rejection dialog for this doctype, exactly once.
		//    Late frappe.ui.form.on() registration is picked up on the next
		//    trigger (the Reject click always happens after this refresh).
		//    Skip doctypes that already supply their own before_workflow_action
		//    (e.g. material_request.js) to avoid a double reject dialog.
		if (!bound.has(frm.doctype)) {
			bound.add(frm.doctype);
			if (!_doctype_has_own_bwa_handler(frm.doctype)) {
				frappe.ui.form.on(frm.doctype, {
					before_workflow_action(f) {
						const wf = window.avinashgroup_app && window.avinashgroup_app.approval_workflow;
						if (!wf) return;
						return wf.handleRejectAction(f, { rejectReasonMethod: REJECT_METHOD });
					},
				});
			}
		}
	});
})();
