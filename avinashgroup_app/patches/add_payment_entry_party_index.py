"""Add an index on Payment Entry.party for the Sales Invoice credit control checks.

validate_sales_invoice and get_credit_position (credit_control.py) both sum
unallocated advances with a WHERE party = %s filter. Payment Entry ships with
no search_index on that field, so every call was a full table scan (~55-589ms
measured on avinas1). Idempotent: skips if the index already exists.
"""

import frappe

INDEX_NAME = "payment_entry_party_index"


def execute():
	already_indexed = frappe.db.sql(
		"SHOW INDEX FROM `tabPayment Entry` WHERE Key_name = %s", INDEX_NAME
	)
	if already_indexed:
		return

	frappe.db.add_index("Payment Entry", ["party"], index_name=INDEX_NAME)
