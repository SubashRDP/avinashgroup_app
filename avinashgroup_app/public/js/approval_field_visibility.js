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
    // The custom fields that setup_workflow injects onto target doctypes
    const APPROVAL_FIELDS = [
        "custom_approval_approvers",
        "custom_approval_history",
        "custom_current_approval_level",
        "custom_current_approver",
        "custom_total_approval_levels",
    ];

    $(document).on("form-refresh", function (e, frm) {
        if (!frm || !frm.doc || !frm.meta) return;

        // Quick check: does this doctype even have any of our approval fields?
        let has_fields = APPROVAL_FIELDS.some(f => frm.fields_dict[f]);
        if (!has_fields) return;

        let company = frm.doc.company;
        if (!company) {
            // No company selected yet — hide approval fields by default
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
