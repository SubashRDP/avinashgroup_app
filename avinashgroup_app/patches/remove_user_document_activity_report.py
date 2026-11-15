# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Delete the short-lived "User Document Activity" report record.

It existed for a day as a separate report before its job was folded into User
Daily Entry Summary. Its code is gone, so on any site that picked the record up
it would be a dead link in the report list. Frappe's migrate removes orphaned
DocTypes but not orphaned Reports, hence this patch. No-op where it never existed.
"""

import frappe


def execute():
	frappe.delete_doc_if_exists("Report", "User Document Activity", force=True)
