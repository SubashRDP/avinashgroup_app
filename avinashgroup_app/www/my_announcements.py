# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

"""My Announcements (/my-announcements) for the customer portal.

Lists the Portal Announcement History records — the message and image of every
announcement sent to customer portal users — newest first.

Only a login listed in some Customer's Portal Users table may open it; those are
exactly the users the announcement popup is sent to. Everyone else gets a
permission error. The records are read with ignore_permissions because portal
users hold no desk role on the doctype; the Portal User check above is the guard.
"""

import frappe
from frappe import _
from frappe.utils import get_url

from avinashgroup_app.avinash_group_app.doctype.portal_announcement.portal_announcement import (
	_is_customer_portal_user,
)

# Website pages are cached by path, not user — this page must be built per request.
no_cache = 1


def get_context(context):
	context.no_cache = 1
	user = frappe.session.user

	if user == "Guest":
		frappe.throw(_("You need to be logged in to access this page"), frappe.PermissionError)

	if not _is_customer_portal_user(user):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	announcements = frappe.get_all(
		"Portal Announcement History",
		fields=["name", "title", "message", "image", "custom_html", "sent_on"],
		order_by="sent_on desc",
		ignore_permissions=True,
	)
	for row in announcements:
		if row.image and not row.image.startswith("http"):
			row.image = get_url(row.image)

	context.announcements = announcements
	context.title = _("My Announcements")
	context.show_sidebar = True
