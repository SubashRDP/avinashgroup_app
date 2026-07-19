# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Add a composite `(company, creation)` index on Sales Invoice Print Log.

The Invoice Activity Report's Printed source, and the doctype list view once a
user is scoped to their companies, both filter `company IN (...) AND creation
BETWEEN day` and sort by creation DESC. A composite (company, creation) index
matches that exactly — equality (IN) on company, range + ordering on creation —
so the scan touches only the in-range rows of the permitted companies instead of
the whole table. Idempotent: skips if the index already exists.
"""

import frappe

INDEX_NAME = "print_log_company_creation"


def execute():
	already_indexed = frappe.db.sql(
		"SHOW INDEX FROM `tabSales Invoice Print Log` WHERE Key_name = %s", INDEX_NAME
	)
	if already_indexed:
		return

	frappe.db.add_index(
		"Sales Invoice Print Log", ["company", "creation"], index_name=INDEX_NAME
	)
