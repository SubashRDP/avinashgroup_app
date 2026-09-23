# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

"""Announcement list (/portal_announcement_history) for the customer portal.

Lists every Portal Announcement History record — one per announcement sent to
customer portal users — newest first, as titles with a short preview. The full
message, image and custom HTML live on the detail page, reached at
/portal_announcement_history/<name> (portal_announcement_history_detail.py).

Only a login listed in some Customer's Portal Users table may open it; those are
exactly the users the announcement popup is sent to. Everyone else gets a
permission error. The records are read with ignore_permissions because portal
users hold no desk role on the doctype; the Portal User check is the guard.

Deliberately narrow: this page shows the announcements themselves, not who
received or read them — nothing per-user is recorded (see the doctype).
"""

import frappe
from frappe import _
from frappe.utils import get_url, strip_html

from avinashgroup_app.avinash_group_app.doctype.portal_announcement.portal_announcement import (
	require_customer_portal_user,
)
from avinashgroup_app.avinash_group_app.doctype.portal_announcement_read.portal_announcement_read import (
	get_read_announcements,
)

# Website pages are cached by path, not user — this page must be built per request.
no_cache = 1

# Characters of the message shown under the title in the list. Sized to fit one
# line on a phone without wrapping to a third line.
SNIPPET_CHARS = 140


def get_context(context):
	context.no_cache = 1
	require_customer_portal_user()

	announcements = frappe.get_all(
		"Portal Announcement History",
		fields=["name", "title", "message", "custom_html", "image", "sent_on"],
		order_by="sent_on desc",
		ignore_permissions=True,
	)

	# Safe to read per-user here: no_cache above keeps this page out of the website
	# cache, which is keyed by path and would otherwise serve one user's unread
	# marks to the next.
	read = get_read_announcements()

	for row in announcements:
		row.route = "/portal_announcement_history/" + frappe.utils.quoted(row.name)
		if row.image and not row.image.startswith("http"):
			row.image = get_url(row.image)
		row.snippet = _snippet(row)
		row.unread = row.name not in read

	context.announcements = announcements
	context.unread_count = sum(1 for row in announcements if row.unread)
	context.title = _("My Announcements")
	context.show_sidebar = True


def _snippet(row):
	"""One line of plain text for the list row.

	Custom HTML replaces the message on the detail page, so it is what gets
	summarised when present — same precedence as the popup, so the list never
	previews text the reader will not find when they open it.
	"""
	source = row.custom_html if (row.custom_html or "").strip() else (row.message or "")
	text = " ".join(strip_html(source).split())
	if len(text) <= SNIPPET_CHARS:
		return text
	return text[:SNIPPET_CHARS].rstrip() + "…"
