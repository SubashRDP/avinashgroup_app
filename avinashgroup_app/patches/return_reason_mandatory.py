# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Reason for Return is mandatory on Sales Invoice returns.

The custom_reason_for_return field already displays only on returns
(depends_on eval:doc.is_return); this makes it required there too. The form
asterisk/check comes from mandatory_depends_on; the hard guarantee is the
server check in salesinvoice_taxes.validate_return_reason (mandatory_depends_on
alone is not enforced for API-created documents). Idempotent."""

import frappe


def execute():
	if not frappe.db.exists("Custom Field", "Sales Invoice-custom_reason_for_return"):
		return
	frappe.db.set_value(
		"Custom Field",
		"Sales Invoice-custom_reason_for_return",
		"mandatory_depends_on",
		"eval:doc.is_return",
	)
	frappe.clear_cache(doctype="Sales Invoice")
