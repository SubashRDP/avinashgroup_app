# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Backfill created_by on existing CBMS Bill / CBMS Bill Return rows.

New bills stamp it at creation from the invoice's owner
(sales_invoice_hooks.build_cbms_fields); this fills the rows written before the
field existed, so the Materialized Report's "Entered By" column is populated for
history too.

Stores the owner's FULL NAME, matching what build_cbms_fields writes — a name,
not a User link, so the value survives a user being renamed or removed. Rows
whose invoice has since been deleted keep an empty created_by rather than
inventing one. Idempotent: only touches rows still empty.
"""

import frappe


def execute():
	for doctype in ("CBMS Bill", "CBMS Bill Return"):
		if not frappe.db.has_column(doctype, "created_by"):
			continue

		frappe.db.sql(
			f"""
			UPDATE `tab{doctype}` bill
			JOIN `tabSales Invoice` si ON si.name = bill.sales_invoice
			LEFT JOIN `tabUser` u ON u.name = si.owner
			SET bill.created_by = COALESCE(NULLIF(u.full_name, ''), si.owner)
			WHERE IFNULL(bill.created_by, '') = ''
			"""
		)
