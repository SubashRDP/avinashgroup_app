import frappe
from frappe import _
from frappe.model.workflow import (
	get_workflow,
	is_transition_condition_satisfied,
	has_approval_access,
	WorkflowStateError,
	WorkflowTransitionError,
)
from frappe.model.docstatus import DocStatus


@frappe.whitelist()
def get_transitions(doc, workflow=None, raise_exception=False):
	from frappe.model.document import Document

	if not isinstance(doc, Document):
		doc = frappe.get_doc(frappe.parse_json(doc))
		doc.load_from_db()

	if doc.is_new():
		return []

	doc.check_permission("read")

	workflow = workflow or get_workflow(doc.doctype)
	current_state = doc.get(workflow.workflow_state_field)

	if not current_state:
		if raise_exception:
			raise WorkflowStateError
		else:
			frappe.throw(_("Workflow State not set"), WorkflowStateError)

	transitions = []

	if frappe.session.user == "Administrator":
		for transition in workflow.transitions:
			if transition.state == current_state:
				if not is_transition_condition_satisfied(transition, doc):
					continue
				transitions.append(transition.as_dict())
	else:
		roles = frappe.get_roles()
		for transition in workflow.transitions:
			if transition.state == current_state and transition.allowed in roles:
				if not is_transition_condition_satisfied(transition, doc):
					continue
				transitions.append(transition.as_dict())

	return transitions


@frappe.whitelist()
def apply_workflow(doc, action):
	"""Allow workflow action — Administrator bypasses role restrictions"""
	doc = frappe.get_doc(frappe.parse_json(doc))
	doc.load_from_db()
	workflow = get_workflow(doc.doctype)
	transitions = get_transitions(doc, workflow)  # uses our override
	user = frappe.session.user

	transition = None
	for t in transitions:
		if t.action == action:
			transition = t

	if not transition:
		frappe.throw(_("Not a valid Workflow Action"), WorkflowTransitionError)

	if not has_approval_access(user, doc, transition):
		frappe.throw(_("Self approval is not allowed"))

	doc.set(workflow.workflow_state_field, transition.next_state)

	next_state = next(d for d in workflow.states if d.state == transition.next_state)

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
