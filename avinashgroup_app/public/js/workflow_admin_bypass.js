// For Administrator: patch get_transitions so the role check in show_actions passes
const _orig_get_transitions = frappe.workflow.get_transitions;
frappe.workflow.get_transitions = function (doc) {
    return _orig_get_transitions(doc).then((transitions) => {
        if (frappe.session.user === "Administrator") {
            return transitions.map((t) => Object.assign({}, t, { allowed: "Administrator" }));
        }
        return transitions;
    });
};

frappe.ui.form.on('Purchase Order', {
    onload(frm) {
        access_po(frm);
    },
    refresh(frm) {
        access_po(frm);
    },
    onload_post_render(frm) {
        access_po(frm);
    }
});

function access_po(frm) {
    if (frappe.session.user != "Administrator") {

        if (frm.doc.workflow_state == "Draft" && frm.doc.owner != frappe.session.user) {
            $('.actions-btn-group').hide();
            frm.disable_form();
        }

        if (frm.doc.workflow_state == "Pending" && frm.doc.custom_initiator_manager != frappe.session.user) {
            $('.actions-btn-group').hide();
            frm.disable_form();
        }

        if (frm.doc.workflow_state == "Pending Approval" && frm.doc.custom_recommended_to != frappe.session.user) {
            $('.actions-btn-group').hide();
            frm.disable_form();
        }

        if (frm.doc.workflow_state == "Recommeded" && frm.doc.custom_recommended_to != frappe.session.user) {
            $('.actions-btn-group').hide();
            frm.disable_form();
        }

        if (frm.doc.workflow_state == "Reviewed" && frm.doc.custom_recommended_to != frappe.session.user) {
            $('.actions-btn-group').hide();
            frm.disable_form();
        }

        if (frm.doc.workflow_state == "Approved") {
            $('.actions-btn-group').hide();
            frm.disable_form();
        }

        if (frappe.session.user != frm.doc.owner && frm.doc.workflow_state == "Cancelled") {
            $('button[data-label="Amend"]').hide();
            frm.disable_form();
        }
    }
}
