# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

"""One announcement (/portal_announcement_history/<name>) for the customer portal.

The detail half of the announcement list (portal_announcement_history.py): title,
date, image and the full message of a single Portal Announcement History record,
laid out the same way the login popup lays it out.

Reached through the `website_route_rules` entry in hooks.py, because a Portal
Announcement is named after its title ("Happy Teej") — a name with spaces, which
only a <path:> rule will carry through. The name arrives URL-quoted and is
unquoted here before the lookup.

Same guard as the list: a login not in some Customer's Portal Users table gets a
permission error, so a portal user cannot reach a record by guessing its title.
A name that does not exist raises 404 rather than a permission error, since the
reader is allowed to look — there is simply nothing there.
"""

from urllib.parse import unquote

import frappe
from frappe import _
from frappe.utils import get_url

from avinashgroup_app.avinash_group_app.doctype.portal_announcement.portal_announcement import (
	require_customer_portal_user,
)
from avinashgroup_app.avinash_group_app.doctype.portal_announcement_read.portal_announcement_read import (
	mark_read,
)

# Website pages are cached by path, not user — this page must be built per request.
no_cache = 1


def get_context(context):
	context.no_cache = 1
	require_customer_portal_user()

	name = unquote(frappe.form_dict.get("name") or "")
	if not name or not frappe.db.exists("Portal Announcement History", name):
		raise frappe.DoesNotExistError

	announcement = frappe.get_doc("Portal Announcement History", name)

	image = announcement.image
	if image and not image.startswith("http"):
		image = get_url(image)

	context.announcement = announcement
	context.image = image
	# Custom HTML replaces the message, exactly as the login popup does it — the
	# image still shows. Keeping the rule here means the list's snippet, the popup
	# and this page all summarise the same text.
	context.body_html = (
		announcement.custom_html
		if (announcement.custom_html or "").strip()
		else (announcement.message or "")
	)
	context.title = announcement.title or name
	context.show_sidebar = True

	# Opening the page is what marks it read. A GET that writes is normally a smell,
	# but a read receipt has no other moment to fire, and mark_read is idempotent.
	mark_read(name)
	frappe.db.commit()
