import frappe
from frappe import _
from frappe.model.docstatus import DocStatus
from frappe.model import workflow as workflow_module


BYPASS_WORKFLOW_NAME = "Material Request One-Line Approver"


def _is_admin_bypass(workflow, user):
    return user == "Administrator" and workflow and workflow.name == BYPASS_WORKFLOW_NAME


@frappe.whitelist()
def get_transitions(doc, workflow=None, raise_exception: bool = False):
    """Return list of possible transitions for the given doc.

    For Administrator on the specified workflow, return all transitions for the
    current state without checking role or condition.
    """
    from frappe.model.document import Document

    if not isinstance(doc, Document):
        doc = frappe.get_doc(frappe.parse_json(doc))
        doc.load_from_db()

    if doc.is_new():
        return []

    doc.check_permission("read")

    workflow = workflow or workflow_module.get_workflow(doc.doctype)

    if not _is_admin_bypass(workflow, frappe.session.user):
        return workflow_module.get_transitions(doc, workflow, raise_exception)

    current_state = doc.get(workflow.workflow_state_field)

    if not current_state:
        if raise_exception:
            raise workflow_module.WorkflowStateError
        frappe.throw(_("Workflow State not set"), workflow_module.WorkflowStateError)

    transitions = []
    for transition in workflow.transitions:
        if transition.state == current_state:
            transitions.append(transition.as_dict())

    return transitions


@frappe.whitelist()
def apply_workflow(doc, action):
    """Allow workflow action on the current doc.

    For Administrator on the specified workflow, bypass role/condition checks.
    """
    user = frappe.session.user

    doc = frappe.get_doc(frappe.parse_json(doc))
    doc.load_from_db()
    workflow = workflow_module.get_workflow(doc.doctype)

    if not _is_admin_bypass(workflow, user):
        return workflow_module.apply_workflow(doc, action)

    transitions = get_transitions(doc, workflow)

    # find the transition
    transition = None
    for t in transitions:
        if t.action == action:
            transition = t
            break

    if not transition:
        frappe.throw(_("Not a valid Workflow Action"), workflow_module.WorkflowTransitionError)

    if not workflow_module.has_approval_access(user, doc, transition):
        frappe.throw(_("Self approval is not allowed"))

    # update workflow state field
    doc.set(workflow.workflow_state_field, transition.next_state)

    # find settings for the next state
    next_state = next(d for d in workflow.states if d.state == transition.next_state)

    # update any additional field
    if next_state.update_field:
        doc.set(next_state.update_field, next_state.update_value)

    new_docstatus = DocStatus(next_state.doc_status or 0)
    if doc.docstatus.is_draft() and new_docstatus.is_draft():
        doc.save()
    elif doc.docstatus.is_draft() and new_docstatus.is_submitted():
        from frappe.core.doctype.submission_queue.submission_queue import queue_submission
        from frappe.utils.scheduler import is_scheduler_inactive

        if doc.meta.queue_in_background and not is_scheduler_inactive():
            queue_submission(doc, "Submit")
            return

        doc.submit()
    elif doc.docstatus.is_submitted() and new_docstatus.is_submitted():
        doc.save()
    elif doc.docstatus.is_submitted() and new_docstatus.is_cancelled():
        doc.cancel()
    else:
        frappe.throw(_("Illegal Document Status for {0}").format(next_state.state))

    doc.add_comment("Workflow", _(next_state.state))

    return doc
