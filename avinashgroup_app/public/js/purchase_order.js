frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (frm.doc.workflow_state !== "Pending Approval") return;

		const current_level  = frm.doc.custom_current_approval_level || 0;
		const total_levels   = frm.doc.custom_total_approval_levels   || 0;
		const current_approver = frm.doc.custom_current_approver;

		// Check if this user already approved at a past level
		const approvers_table = frm.doc.custom_approval_approvers || [];
		const already_approved_levels = approvers_table
			.filter(row => row.approver === frappe.session.user && row.level < current_level)
			.map(row => row.level);
		const already_approved = already_approved_levels.length > 0;

		const is_approver = (
			!already_approved
			&& (current_approver === frappe.session.user || frappe.session.user === "Administrator")
		);

		// ── Approval progress banner ──────────────────────────────────────
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

		// ── Hide Approve / Reject for non-approvers ───────────────────────
		if (!is_approver) {
			frm.page.actions_btn_group.find("li a, li button").filter(function () {
				return ["Approve", "Reject"].includes($(this).text().trim());
			}).closest("li").hide();

			frm.page.inner_toolbar.find(".btn").filter(function () {
				return ["Approve", "Reject"].includes($(this).text().trim());
			}).hide();
		}
	},

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
