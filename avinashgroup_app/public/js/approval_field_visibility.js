/*
 * Dynamic Approval Field Visibility
 * ----------------------------------
 * Automatically hides/shows approval-related custom fields
 * based on whether a Dynamic Approval Setting exists for
 * the current document's DocType + Company.
 *
 * Included globally via app_include_js in hooks.py.
 */

(function () {
    const APPROVAL_FIELDS = [
        "custom_current_approval_level",
        "custom_current_approver",
        "custom_total_approval_levels",
    ];

    $(document).on("form-refresh", function (e, frm) {
        if (!frm || !frm.doc || !frm.meta) return;

        let has_fields = APPROVAL_FIELDS.some(f => frm.fields_dict[f]);
        if (!has_fields) return;

        const workflow = window.avinashgroup_app && window.avinashgroup_app.approval_workflow;

        // ── 0. Filter the approval setting picker by doctype + company ──
        if (frm.fields_dict["custom_approval_setting"]) {
            frm.set_query("custom_approval_setting", function () {
                return {
                    filters: {
                        document_type: frm.doc.doctype,
                        company: frm.doc.company || "",
                        is_active: 1,
                    },
                };
            });
        }

        // ── 1. Lock form for non-current-approvers while Pending Approval ──
        if (frm.doc.workflow_state === "Pending Approval") {
            const approval = workflow
                ? workflow.getContext(frm, {
                    currentApproverField: "custom_current_approver",
                    currentLevelField: "custom_current_approval_level",
                    totalLevelsField: "custom_total_approval_levels",
                    approvalTableField: "custom_approval_approvers",
                })
                : {
                    currentApprover: frm.doc.custom_current_approver,
                    currentLevel: parseInt(frm.doc.custom_current_approval_level) || 0,
                    isApprover: (
                        frappe.session.user === frm.doc.custom_current_approver ||
                        frappe.session.user === "Administrator"
                    ),
                };

            const is_current_approver = approval.isApprover;
            if (!is_current_approver) {
                frm.disable_form();
                if (workflow) {
                    workflow.hideWorkflowActions(frm, ["Approve", "Reject"]);
                }
            }

            // ── 2. Visually lock already-approved rows in the hierarchy table ──
            const current_level = approval.currentLevel || 0;
            if (current_level > 1) {
                setTimeout(function () {
                    Object.values(frm.fields_dict).forEach(function (field) {
                        if (field.df.fieldtype !== "Table" || field.df.options !== "Dynamic Approval Approver") return;
                        const grid = field.grid;
                        if (!grid) return;
                        (grid.grid_rows || []).forEach(function (grid_row) {
                            const lvl = parseInt((grid_row.doc || {}).level) || 0;
                            if (lvl > 0 && lvl < current_level) {
                                grid_row.row.find(".grid-delete-row, .grid-duplicate-row").hide();
                                grid_row.row.css({ "opacity": "0.55", "pointer-events": "none" });
                            }
                        });
                    });
                }, 300);
            }

        }

        // ── 3. Hide the hidden workflow-driver fields ──
        let company = frm.doc.company;
        if (!company) {
            APPROVAL_FIELDS.forEach(f => {
                if (frm.fields_dict[f]) frm.toggle_display(f, false);
            });
            return;
        }

        frappe.call({
            method: "avinashgroup_app.custom_code.dynamic_approval.has_approval_config",
            args: { doctype: frm.doc.doctype, company: company },
            async: true,
            callback: function (r) {
                let show = r && r.message;
                APPROVAL_FIELDS.forEach(f => {
                    if (frm.fields_dict[f]) frm.toggle_display(f, show);
                });
            }
        });
    });
})();
