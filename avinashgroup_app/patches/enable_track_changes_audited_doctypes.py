# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Enable `track_changes` on every audited doctype so the User Audit Trail
report has field-level Version history (original -> new) to draw from.

The app already records WHO created/modified a document via the custom audit
fields (custom_created_by / custom_modified_by). To also surface WHAT changed,
Frappe's built-in Version doctype must be populated, which only happens when a
doctype has `track_changes` enabled.

Most ERPNext transactions already track changes; a few (e.g. Leave Application,
Material Request) and the app's own doctypes do not. This patch turns it on for
any audited doctype that is missing it.

Idempotent: skips doctypes that don't exist on the site and those already
tracking changes. Only edits made AFTER this runs get Version records.
"""

import frappe

from avinashgroup_app.utils.audit_file_manager import AuditBase


def execute():
	for doctype in sorted(set(AuditBase.doctypes)):
		if not frappe.db.exists("DocType", doctype):
			continue

		# Already tracking changes → nothing to do.
		if frappe.db.get_value("DocType", doctype, "track_changes"):
			continue

		frappe.db.set_value("DocType", doctype, "track_changes", 1)
		frappe.clear_cache(doctype=doctype)
