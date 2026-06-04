# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""The Document Generator moved from a block/section layout to a single HTML body.
Remove the now-obsolete child doctypes (and their tables) on any site that still has
them. Idempotent."""

import frappe

OBSOLETE_DOCTYPES = ["Document Template Section", "Generated Document Section"]


def execute():
	for dt in OBSOLETE_DOCTYPES:
		if frappe.db.exists("DocType", dt):
			frappe.delete_doc("DocType", dt, force=True, ignore_permissions=True)
