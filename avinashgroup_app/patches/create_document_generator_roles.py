# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe

ROLES = ["Document Template Manager", "Document Template User"]


def execute():
	"""Create the custom roles used by the Document Generator before the doctypes
	that reference them in their permissions are synced."""
	for role_name in ROLES:
		if not frappe.db.exists("Role", role_name):
			frappe.get_doc(
				{
					"doctype": "Role",
					"role_name": role_name,
					"desk_access": 1,
				}
			).insert(ignore_permissions=True)
