import frappe
from frappe import _


@frappe.whitelist()
def set_reject_reason(doctype, name, reason):
	if not doctype or not name or not reason:
		frappe.throw(_("Missing required parameters: doctype, name, and reason"))

	doctype = str(doctype).strip()
	name = str(name).strip()
	reason = str(reason).strip()

	try:
		doc = frappe.get_doc(doctype, name)
	except frappe.DoesNotExistError:
		frappe.throw(_("Document {0} {1} does not exist").format(doctype, name))

	# Allow any logged-in user to save rejection reason.
	# Approval control is handled by workflow configuration, not here.

	if doc.meta.has_field("custom_reason"):
		frappe.db.set_value(
			doctype,
			name,
			"custom_reason",
			reason,
			update_modified=False,
		)
	else:
		doc.add_comment("Comment", _("Rejection reason: {0}").format(reason))

	return {
		"status": "success",
		"message": _("Rejection reason saved successfully"),
		"doctype": doctype,
		"name": name,
		"custom_reason": reason,
		"saved_by": frappe.session.user,
		"saved_at": frappe.utils.now(),
	}
