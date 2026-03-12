(function () {
	"use strict";

	function is_reject_action(action, transition) {
		if (!action && !transition) return false;
		const action_name = (action || "").toString().trim().toLowerCase();
		const next_state = (transition && transition.next_state)
			? transition.next_state.toString().trim().toLowerCase()
			: "";
		return action_name === "reject" || next_state === "rejected";
	}

	function is_target_doc(frm) {
		const doctype = (frm && frm.doctype) ? frm.doctype.toString().trim() : "";
		return doctype === "Purchase Order";
	}

	function is_custom_approver(frm) {
		const approver = (frm && frm.doc && frm.doc.custom_approver)
			? frm.doc.custom_approver.toString().trim()
			: "";
		return approver && approver === frappe.session.user;
	}

	function show_reject_dialog(frm, proceed) {
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
			primary_action: function() {
				let reason = d.get_value("reject_reason");
				if (!reason || !reason.trim()) {
					frappe.msgprint("Please enter rejection reason");
					return;
				}
				frm.__reject_reason = reason.trim();
				d.hide();
				proceed();
			}
		});
		d.show();
	}

	function patch_workflow_actions() {
		if (!frappe.ui || !frappe.ui.form || !frappe.ui.form.States) return false;

		const current = frappe.ui.form.States.prototype.show_actions;
		if (current && current.__patched_reject) {
			return true;
		}

		const original = current;

		frappe.ui.form.States.prototype.show_actions = function () {
			var added = false;
			var me = this;

			if (this.frm.doc.__unsaved === 1) {
				return;
			}

			function has_approval_access(transition) {
				let approval_access = false;
				const user = frappe.session.user;
				if (
					user === "Administrator" ||
					transition.allow_self_approval ||
					user !== me.frm.doc.owner
				) {
					approval_access = true;
				}
				return approval_access;
			}

			frappe.workflow.get_transitions(this.frm.doc).then((transitions) => {
				this.frm.page.clear_actions_menu();
				const frm = this.frm;
				
				transitions.forEach((d) => {
					if (frappe.user_roles.includes(d.allowed) && has_approval_access(d)) {
						added = true;
						me.frm.page.add_action_item(__(d.action), function () {
							
							const run_workflow = () => {
								me.frm.selected_workflow_action = d.action;
								
								if (!frappe.ui.form.check_mandatory(frm)) {
									frappe.dom.unfreeze();
									return;
								}

								const persist_reject_reason = () => {
									if (is_reject_action(d.action, d) && is_target_doc(frm) && frm.__reject_reason) {
										console.log("Attempting to save rejection reason:", frm.__reject_reason);
										
										return frappe.xcall("avinashgroup_app.custom_code.workflow.set_reject_reason", {
											doctype: frm.doctype,
											name: frm.doc.name,
											reason: frm.__reject_reason,
										}).then((response) => {
											console.log("Rejection reason saved successfully:", response);
											return response;
										}).catch((error) => {
											console.error("Failed to save rejection reason:", error);
											frappe.msgprint(__("Failed to save rejection reason: " + error.message));
											throw error;
										});
									}
									return Promise.resolve();
								};

								me.frm.script_manager.trigger("before_workflow_action").then(() => {
									persist_reject_reason().then(() => {
										frappe.xcall("frappe.model.workflow.apply_workflow", {
											doc: me.frm.doc,
											action: d.action,
										}).then((doc) => {
											console.log("Workflow applied successfully");
											frappe.model.sync(doc);
											
											me.frm.reload_doc().then(() => {
												me.frm.selected_workflow_action = null;
												me.frm.__reject_reason = null;
												me.frm.script_manager.trigger("after_workflow_action");
											});
										}).catch((error) => {
											console.error("Workflow apply failed:", error);
											frappe.msgprint(__("Workflow action failed: " + error.message));
										}).finally(() => {
											frappe.dom.unfreeze();
										});
									}).catch((error) => {
										console.error("Persist reason failed:", error);
										frappe.dom.unfreeze();
									});
								}).catch((error) => {
									console.error("Before workflow action failed:", error);
									frappe.dom.unfreeze();
								});
							};

							// If Reject action - show dialog first for assigned approver only
							if (is_reject_action(d.action, d) && is_target_doc(frm)) {
								if (!is_custom_approver(frm)) {
									frappe.msgprint(__("Only the assigned approver can reject this document."));
									return;
								}
								show_reject_dialog(frm, run_workflow);
							} else {
								run_workflow();
							}
						});
					}
				});

				this.setup_btn(added);
			});
		};

		frappe.ui.form.States.prototype.show_actions.__patched_reject = true;
		return true;
	}

	function ensure_patch() {
		if (patch_workflow_actions()) return;
		let retries = 0;
		const timer = setInterval(() => {
			retries += 1;
			if (patch_workflow_actions() || retries > 50) {
				clearInterval(timer);
			}
		}, 200);
	}

	if (frappe.ready) {
		frappe.ready(ensure_patch);
	} else {
		$(ensure_patch);
	}
})();
