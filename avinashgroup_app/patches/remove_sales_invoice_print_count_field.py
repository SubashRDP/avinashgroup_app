# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Drop the Sales Invoice custom_print_count field.

The print counter moved off the invoice into the Sales Invoice Print Count
doctype (one row per invoice, counts fresh from the first print). The field is
no longer read by anything, so remove its definition. Idempotent — safe on
sites that never had it. The underlying column, if present, is left in place
(harmless, unused) rather than risking a column drop on the core doctype.
"""

import frappe


def execute():
	frappe.delete_doc_if_exists("Custom Field", "Sales Invoice-custom_print_count")
