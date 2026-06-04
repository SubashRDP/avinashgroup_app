# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Image fields used by the Document Generator's signature/letterhead:
- Company.custom_document_stamp  -> {{ org.stamp }}
- Employee.custom_signature_image -> {{ user.signature }}
Idempotent (create_custom_fields skips existing)."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Company": [
				{
					"fieldname": "custom_document_stamp",
					"label": "Document Stamp",
					"fieldtype": "Attach Image",
					"insert_after": "company_logo",
				}
			],
			"Employee": [
				{
					"fieldname": "custom_signature_image",
					"label": "Signature Image",
					"fieldtype": "Attach Image",
					"insert_after": "designation",
				}
			],
		},
		ignore_validate=True,
	)
