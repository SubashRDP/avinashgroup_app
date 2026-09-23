# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

"""Per-user read receipts for portal announcements.

Portal Announcement History holds one record per announcement and says nothing
about who has seen it, so the portal could only ever show every announcement as
equally new. This doctype adds the missing half: one row per (announcement, user)
the moment that user opens the announcement's detail page.

The row's NAME is a hash of announcement + user, so a second read is a duplicate
key the database rejects rather than a second row. That is what makes marking a
read safe to call on every page view, and safe against two tabs racing.

Deliberately narrow: this records that a user OPENED an announcement. It is not
a delivery receipt — the login popup showing an announcement does not mark it
read, because the popup is dismissed without being read all the time.
"""

import hashlib

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

HISTORY = "Portal Announcement History"


class PortalAnnouncementRead(Document):
	pass


def _receipt_name(announcement, user):
	"""Deterministic name for one user's receipt of one announcement.

	Hashed rather than formatted because announcements are named after their
	title ("Happy Teej"), so the parts contain spaces and are not length-bounded.
	"""
	return hashlib.sha256(f"{announcement}\u0000{user}".encode()).hexdigest()[:32]


def mark_read(announcement, user=None):
	"""Record that `user` has opened `announcement`. Idempotent.

	Called from the announcement detail page on every view. A repeat view hits the
	deterministic name above and is ignored, so read_on stays the FIRST time the
	user opened it.
	"""
	user = user or frappe.session.user
	if user == "Guest" or not announcement:
		return

	name = _receipt_name(announcement, user)
	if frappe.db.exists("Portal Announcement Read", name):
		return

	doc = frappe.get_doc(
		{
			"doctype": "Portal Announcement Read",
			"announcement": announcement,
			"user": user,
			"read_on": now_datetime(),
		}
	)
	try:
		doc.insert(ignore_permissions=True, set_name=name)
	except frappe.DuplicateEntryError:
		# Another tab or request inserted the same receipt first. Already read.
		frappe.clear_last_message()


def get_read_announcements(user=None):
	"""Set of announcement names `user` has already opened."""
	user = user or frappe.session.user
	if user == "Guest":
		return set()

	return set(
		frappe.get_all(
			"Portal Announcement Read",
			filters={"user": user},
			pluck="announcement",
			ignore_permissions=True,
		)
	)


@frappe.whitelist()
def get_unread_count():
	"""Unread total for the portal sidebar badge, called by portal_announcement_badge.js.

	Returns 0 — never an error — for Guests and for logins that are not customer
	portal users, so the badge simply never appears for them. It must come over
	this call rather than page context: portal pages are cached by path, not by
	user, so a count baked into the sidebar HTML would be served to the next
	visitor of that page.
	"""
	from avinashgroup_app.avinash_group_app.doctype.portal_announcement.portal_announcement import (
		_is_customer_portal_user,
	)

	user = frappe.session.user
	if user == "Guest" or not _is_customer_portal_user(user):
		return 0

	return count_unread(user)


def count_unread(user=None):
	"""How many announcements `user` has never opened.

	Every portal user sees the whole history (decided 2026-09-13, no date cutoff),
	so unread is simply the history count less this user's receipts. Receipts are
	counted against existing announcements only, so a deleted announcement cannot
	push the count negative.
	"""
	user = user or frappe.session.user
	if user == "Guest":
		return 0

	total = frappe.db.count(HISTORY)
	if not total:
		return 0

	read = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabPortal Announcement Read` r
		WHERE r.user = %s AND EXISTS (
			SELECT 1 FROM `tabPortal Announcement History` h WHERE h.name = r.announcement
		)
		""",
		user,
	)[0][0]

	return max(total - read, 0)
