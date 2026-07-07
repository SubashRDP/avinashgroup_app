# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Sync the Numbering Configuration DocType to create its database table.

	The DocType definition exists but the table was not created during app install.
	This patch ensures the table exists before the naming_series code tries to query it.
	"""
	if frappe.db.exists("DocType", "Numbering Configuration"):
		frappe.get_doc("DocType", "Numbering Configuration").sync_fieldnames()
