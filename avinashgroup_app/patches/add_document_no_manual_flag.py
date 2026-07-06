# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Hidden flag that records whether custom_document_no was entered manually.

The document number is auto-managed by default (drawn atomically at save by
avinashgroup_app.custom_code.Override.naming_series.apply_document_no). When the
user types a number themselves this flag is set to 1 so the server keeps that
value verbatim (only uniqueness-checked) instead of overwriting it with the next
auto number. no_copy so amendments/copies start auto again. Idempotent
(create_custom_fields skips existing)."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DOCTYPES = ["Payment Entry", "Journal Entry", "Purchase Invoice", "Purchase Receipt"]


def execute():
	field = {
		"fieldname": "custom_document_no_manual",
		"label": "Document No. Manually Entered",
		"fieldtype": "Check",
		"default": "0",
		"hidden": 1,
		"no_copy": 1,
		"print_hide": 1,
		"report_hide": 1,
		"insert_after": "custom_document_no",
		"description": "Internal: set when the user types the document number manually.",
	}
	create_custom_fields({dt: [field] for dt in DOCTYPES}, ignore_validate=True)
