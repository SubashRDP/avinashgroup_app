import frappe
from frappe import _


@frappe.whitelist()
def set_reject_reason(doctype, name, reason):
	if not doctype or not name or not reason:
		frappe.throw(_("Missing required parameters: doctype, name, and reason"))

	doctype = str(doctype).strip()
	name = str(name).strip()
	reason = str(reason).strip()

	if doctype != "Material Request":
		frappe.throw(_("Invalid document type. Only 'Material Request' is allowed."))

	try:
		doc = frappe.get_doc(doctype, name)
	except frappe.DoesNotExistError:
		frappe.throw(_("Document {0} {1} does not exist").format(doctype, name))

	if hasattr(doc, "custom_material_request_approver") and doc.custom_material_request_approver:
		if doc.custom_material_request_approver != frappe.session.user:
			frappe.throw(
				_(
					"You are not authorized to reject this document. Only the assigned approver ({0}) can reject it."
				).format(doc.custom_material_request_approver)
			)
	else:
		frappe.throw(_("No approver assigned to this document."))

	if not hasattr(doc, "custom_reason"):
		frappe.throw(_("Document does not have a 'custom_reason' field."))

	frappe.db.set_value(
		doctype,
		name,
		"custom_reason",
		reason,
		update_modified=False,
	)

	return {
		"status": "success",
		"message": _("Rejection reason saved successfully"),
		"doctype": doctype,
		"name": name,
		"custom_reason": reason,
		"saved_by": frappe.session.user,
		"saved_at": frappe.utils.now(),
	}
