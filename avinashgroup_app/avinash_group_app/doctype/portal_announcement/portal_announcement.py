# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_url, getdate, nowdate


class PortalAnnouncement(Document):
	def validate(self):
		if self.valid_from and self.valid_upto and getdate(self.valid_upto) < getdate(self.valid_from):
			frappe.throw(_("Valid Upto cannot be earlier than Valid From."))

		if not self.custom_html and not (self.message or self.image):
			frappe.throw(_("Provide a Message, an Image, or Custom HTML for the popup to show anything."))


def _is_customer_portal_user(user):
	"""True when this login is listed in some Customer's Portal Users table."""
	return bool(
		frappe.db.exists(
			"Portal User",
			{"parenttype": "Customer", "user": user},
		)
	)


def _has_custom_html(popup):
	return bool((popup.custom_html or "").strip())


def _image_url(popup):
	if not popup.image:
		return ""
	return popup.image if popup.image.startswith("http") else get_url(popup.image)


def _body_html(popup):
	"""Body under the image: Custom HTML replaces the Message; without it the
	Message is the body. The image is returned separately so the front-end can
	keep it full-width while it scales an oversized Custom HTML down to fit."""
	if _has_custom_html(popup):
		return popup.custom_html
	if popup.message:
		return f'<div class="ag-popup-msg">{popup.message}</div>'
	return ""


@frappe.whitelist()
def get_login_popups():
	"""Active popups for the logged-in customer portal user, highest priority first.

	Called once per browser session by portal_announcement.js on both the desk and the
	website portal. Returns [] for Guests and for any login that is not in a
	Customer's Portal Users table, so nothing here widens what a user can see.
	"""
	user = frappe.session.user
	if user == "Guest" or not _is_customer_portal_user(user):
		return []

	today = getdate(nowdate())
	popups = []
	for row in frappe.get_all(
		"Portal Announcement",
		filters={"enabled": 1},
		fields=["name", "title", "message", "image", "custom_html", "modified", "valid_from", "valid_upto"],
		order_by="priority asc, creation asc",
	):
		if row.valid_from and getdate(row.valid_from) > today:
			continue
		if row.valid_upto and getdate(row.valid_upto) < today:
			continue
		popups.append(
			{
				"name": row.name,
				"title": row.title,
				"image": _image_url(row),
				"html": _body_html(row),
				"custom": _has_custom_html(row),
				"modified": str(row.modified),
			}
		)
	return popups
