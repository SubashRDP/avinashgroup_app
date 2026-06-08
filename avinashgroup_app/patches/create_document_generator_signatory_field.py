# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Custom Employee->User link used by the Document Generator to resolve the
signatory for {{ user.* }} (name, designation, signature).

We intentionally do NOT use the stock Employee.user_id relation; the signatory is
mapped through this dedicated field instead. Idempotent (create_custom_fields skips
existing)."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Employee": [
				{
					"fieldname": "custom_document_user",
					"label": "Document Signatory User",
					"fieldtype": "Link",
					"options": "User",
					"insert_after": "user_id",
					"description": "Login user mapped to this employee for the Document Generator signature block.",
				}
			],
		},
		ignore_validate=True,
	)
