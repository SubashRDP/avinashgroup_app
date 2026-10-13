"""Sales Order Hold / Close / Cancel: save the reason and notify the customer.

public/js/sales_order_status_reason.js asks for a reason, then calls
record_status_reason, which:
  1. adds "<Action>: <reason> (<date>)" as a new line in the Reason field
     (custom_hold_reason), under the earlier reasons,
  2. adds it as a timeline comment,
  3. sends a bell notification to the customer's portal users.

If the notification fails, the error is logged but the reason stays saved.
"""

import frappe
from frappe import _

from avinashgroup_app.custom_code.customer_notifications import _portal_users

# Action → (permission needed, resulting state, check that it really happened).
ACTIONS = {
	"Hold": ("write", "On Hold", lambda doc: doc.status == "On Hold"),
	"Close": ("write", "Closed", lambda doc: doc.status == "Closed"),
	"Cancel": ("cancel", "Cancelled", lambda doc: doc.docstatus == 2),
}

# What the customer sees in the portal bell: subject, and the sentence under it.
# {name} is the order ID, {reason} the text typed in the popup.
CUSTOMER_NOTICES = {
	"Hold": ("Order on hold", "Your order {name} has been put on hold. Reason: {reason}"),
	"Close": ("Order closed", "Your order {name} has been closed. Reason: {reason}"),
	"Cancel": ("Order cancelled", "Your order {name} has been cancelled. Reason: {reason}"),
}


@frappe.whitelist()
def record_status_reason(sales_order: str, action: str, reason: str):
	"""Add "<action>: <reason> (<date>)" to the order's Reason field and timeline.

	Called right after the action succeeds. Throws if the action is unknown,
	the reason is blank, the order is not actually in that state, or the user
	lacks the permission the action itself needs.
	"""
	if action not in ACTIONS:
		frappe.throw(_("Unknown action {0}.").format(action))
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Reason is required."))

	doc = frappe.get_doc("Sales Order", sales_order)
	ptype, state, happened = ACTIONS[action]
	doc.check_permission(ptype)
	if not happened(doc):
		frappe.throw(_("{0} is not {1}; reason not saved.").format(sales_order, _(state)))

	# Date the order was held / closed / cancelled, e.g. "Hold: no gas left (2026-10-13)".
	text = f"{action}: {reason} ({frappe.utils.nowdate()})"
	# Add on a new line under the earlier reasons, so every reason stays.
	old_reasons = (doc.custom_hold_reason or "").strip()
	all_reasons = f"{old_reasons}\n{text}" if old_reasons else text
	doc.db_set("custom_hold_reason", all_reasons)
	doc.add_comment("Comment", text)
	_notify_customer(doc, action, reason)


def _notify_customer(doc, action, reason):
	"""One Notification Log per Portal User of the order's customer. A customer
	with no portal login gets nothing — there is nobody to address it to."""
	try:
		recipients = _portal_users(doc.customer)
		if not recipients:
			return
		subject, body = CUSTOMER_NOTICES[action]
		message = body.format(name=doc.name, reason=reason)
		for user in recipients:
			frappe.get_doc({
				"doctype": "Notification Log",
				"for_user": user,
				"from_user": frappe.session.user,
				"type": "Alert",
				"document_type": "Sales Order",
				"document_name": doc.name,
				"subject": _(subject),
				"email_content": f"<p>{frappe.utils.escape_html(message)}</p>",
			}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title="Sales Order status notification failed",
			message=f"Sales Order {doc.name} ({action})\n\n{frappe.get_traceback()}",
		)
