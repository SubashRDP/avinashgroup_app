# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class PortalAnnouncementHistory(Document):
	"""A copy of the message and image of a Portal Announcement as it was sent to
	customer portal users. Created by portal_announcement.get_login_popups the
	first time each version of an announcement is shown; never entered by hand."""

	pass
