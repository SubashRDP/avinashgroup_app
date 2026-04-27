(function () {
	const ns = (window.avinashgroup_app = window.avinashgroup_app || {});
	const workflow = (ns.approval_workflow = ns.approval_workflow || {});

	const DEFAULT_ACTIONS = ["Approve", "Reject"];

	function _doc_value(doc, fieldname) {
		return doc && fieldname ? doc[fieldname] : undefined;
	}

	function _safe_int(value) {
		const parsed = parseInt(value, 10);
		return Number.isFinite(parsed) ? parsed : 0;
	}

	function _get_context(frm, opts) {
		opts = opts || {};
		const doc = (frm && frm.doc) || {};
		const workflow_state = doc.workflow_state || "";
		const currentApproverField = opts.currentApproverField || "custom_current_approver";
		const currentLevelField = opts.currentLevelField || "custom_current_approval_level";
		const totalLevelsField = opts.totalLevelsField || "custom_total_approval_levels";
		const approvalTableField = opts.approvalTableField || "custom_approval_approvers";
		const currentApprover = _doc_value(doc, currentApproverField) || "";
		const currentLevel = _safe_int(_doc_value(doc, currentLevelField));
		const totalLevels = _safe_int(_doc_value(doc, totalLevelsField));
		const rows = Array.isArray(doc[approvalTableField]) ? doc[approvalTableField] : [];
		const isAdministrator = frappe.session.user === "Administrator";
		const alreadyApprovedLevels = [];

		if (currentLevel > 0 && rows.length) {
			rows.forEach((row) => {
				if (!row || row.approver !== frappe.session.user) return;
				const level = _safe_int(row.level);
				if (level > 0 && level < currentLevel) {
					alreadyApprovedLevels.push(level);
				}
			});
		}

		const alreadyApproved = alreadyApprovedLevels.length > 0;
		const isApprover = !alreadyApproved && (currentApprover === frappe.session.user || isAdministrator);

		return {
			doc,
			workflow_state,
			currentApproverField,
			currentLevelField,
			totalLevelsField,
			approvalTableField,
			currentApprover,
			currentLevel,
			totalLevels,
			alreadyApprovedLevels,
			alreadyApproved,
			isApprover,
			isAdministrator,
			pending: workflow_state === "Pending Approval",
		};
	}

	function _hide_workflow_actions(frm, action_labels) {
		const labels = new Set(action_labels || DEFAULT_ACTIONS);
		const containers = [];

		if (frm && frm.page && frm.page.actions_btn_group) {
			containers.push(frm.page.actions_btn_group);
		}
		if (frm && frm.page && frm.page.inner_toolbar) {
			containers.push(frm.page.inner_toolbar);
		}

		containers.forEach(($container) => {
			if (!$container || !$container.find) return;

			$container.find("li a, li button, .btn").each(function () {
				const text = ($(this).text() || "").trim();
				if (labels.has(text)) {
					$(this).closest("li").hide();
					$(this).hide();
				}
			});
		});
	}

	function _apply_pending_approval_ui(frm, opts) {
		const context = _get_context(frm, opts);
		if (!context.pending) return context;

		if (!context.isApprover) {
			_hide_workflow_actions(frm, (opts && opts.visibleActions) || DEFAULT_ACTIONS);
		}

		if (opts && typeof opts.onRender === "function") {
			try {
				opts.onRender(context, frm);
			} catch (error) {
				console.error("Approval workflow UI render failed", error);
			}
		}

		return context;
	}

	function _open_reject_reason_dialog(frm, opts) {
		opts = opts || {};
		const method = opts.rejectReasonMethod;
		if (!method) return null;

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

			const dialog = new frappe.ui.Dialog({
				title: opts.dialogTitle || __("Rejection Reason"),
				fields: [
					{
						fieldtype: "Small Text",
						fieldname: "reject_reason",
						label: opts.reasonLabel || __("Reason for Rejection"),
						reqd: 1,
					},
				],
				primary_action_label: opts.primaryActionLabel || __("Reject"),
				primary_action() {
					const reason = dialog.get_value("reject_reason");
					if (!reason || !reason.trim()) {
						frappe.msgprint(__("Please enter a rejection reason."));
						return;
					}

					is_submitting = true;
					dialog.hide();
					frappe.dom.freeze(opts.freezeMessage || __("Submitting rejection..."));

					Promise.resolve(
						typeof method === "function"
							? method({
									doctype: frm.doctype,
									name: frm.doc.name,
									reason: reason.trim(),
									frm,
								})
							: frappe.xcall(method, {
									doctype: frm.doctype,
									name: frm.doc.name,
									reason: reason.trim(),
								})
					)
						.then(() => {
							frappe.msgprint(opts.successMessage || __("Rejection recorded successfully"));
							resolveOnce();
						})
						.catch((error) => {
							frappe.msgprint(opts.errorMessage || __("Error saving rejection reason"));
							console.error(error);
							rejectOnce(error);
						})
						.finally(() => {
							frappe.dom.unfreeze();
						});
				},
				secondary_action_label: opts.cancelActionLabel || __("Cancel"),
				secondary_action() {
					dialog.hide();
					rejectOnce("cancelled");
				},
			});

			dialog.onhide = () => {
				if (is_submitting) return;
				rejectOnce("dialog_closed");
			};

			dialog.show();
			frappe.dom.unfreeze();
		});
	}

	workflow.getContext = _get_context;
	workflow.hideWorkflowActions = _hide_workflow_actions;
	workflow.applyPendingApprovalUi = _apply_pending_approval_ui;
	workflow.handleRejectAction = function (frm, opts) {
		if (!frm || frm.selected_workflow_action !== "Reject") return null;
		return _open_reject_reason_dialog(frm, opts);
	};
})();
