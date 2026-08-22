"""The customer portal's own notification bell.

Portal users have no desk, so the Notification Log entries raised for them by
custom_code/customer_notifications.py were being written where they could never
read them. These two endpoints back a bell in the portal navbar.

Scope is not a filter the caller passes: every query is pinned to
frappe.session.user, so a customer can only ever read their own notifications
and there is no customer parameter to tamper with.
"""

import frappe
from frappe.utils import pretty_date, strip_html


def _is_customer():
	return "Customer" in frappe.get_roles(frappe.session.user)


@frappe.whitelist()
def get_my_notifications(limit=15):
	"""This user's notifications, newest first, with the unread count."""
	if frappe.session.user == "Guest" or not _is_customer():
		return {"unread": 0, "items": []}

	rows = frappe.get_all(
		"Notification Log",
		filters={"for_user": frappe.session.user},
		fields=["name", "subject", "email_content", "document_type", "document_name", "read", "creation"],
		order_by="creation desc",
		limit=frappe.utils.cint(limit) or 15,
		ignore_permissions=True,
	)

	items = []
	for r in rows:
		items.append({
			"name": r.name,
			"subject": strip_html(r.subject or "").strip(),
			"message": strip_html(r.email_content or "").strip(),
			"document_type": r.document_type,
			"document_name": r.document_name,
			"read": 1 if r.read else 0,
			"when": pretty_date(r.creation),
		})

	unread = frappe.db.count("Notification Log", {"for_user": frappe.session.user, "read": 0})
	return {"unread": unread, "items": items}


@frappe.whitelist()
def mark_all_read():
	"""Clear this user's unread count. Never touches another user's rows."""
	if frappe.session.user == "Guest" or not _is_customer():
		return {"unread": 0}

	frappe.db.set_value(
		"Notification Log",
		{"for_user": frappe.session.user, "read": 0},
		"read",
		1,
		update_modified=False,
	)
	return {"unread": 0}
