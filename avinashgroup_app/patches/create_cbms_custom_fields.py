# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Sales Invoice field used by the CBMS/IRD integration to record why a Sales Return was
made, sent to CBMS as reason_for_return. Idempotent (create_custom_fields skips existing)."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Sales Invoice": [
				{
					"fieldname": "custom_reason_for_return",
					"label": "Reason for Return",
					"fieldtype": "Data",
					"insert_after": "return_against",
					"depends_on": "eval:doc.is_return",
					"description": "Sent to CBMS/IRD as reason_for_return on the credit note.",
				}
			],
		},
		ignore_validate=True,
	)
