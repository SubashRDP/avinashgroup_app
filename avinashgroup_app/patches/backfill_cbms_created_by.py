# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Backfill created_by on existing CBMS Bill / CBMS Bill Return rows.

New bills stamp it at creation from the invoice (build_cbms_fields); this fills
the rows written before the field existed, so the Materialized Report's
"Entered By" column is populated for history too.

Source is the invoice's custom_created_by — the app-wide audit field — and only
then its owner. They are not interchangeable: invoices created through the API
carry the API user in owner (Administrator on every one of avinas1's 48,837
invoices) while custom_created_by holds the clerk who actually entered it.

Stores the FULL NAME, matching what build_cbms_fields writes — a name, not a
User link, so the value survives a user being renamed or removed. Rows whose
invoice has since been deleted keep an empty created_by rather than inventing
one. Idempotent: only touches rows still empty.
"""

import frappe


def execute():
	entered_by = "si.owner"
	if frappe.db.has_column("Sales Invoice", "custom_created_by"):
		entered_by = "COALESCE(NULLIF(si.custom_created_by, ''), si.owner)"

	for doctype in ("CBMS Bill", "CBMS Bill Return"):
		if not frappe.db.has_column(doctype, "created_by"):
			continue

		frappe.db.sql(
			f"""
			UPDATE `tab{doctype}` bill
			JOIN `tabSales Invoice` si ON si.name = bill.sales_invoice
			LEFT JOIN `tabUser` u ON u.name = {entered_by}
			SET bill.created_by = COALESCE(NULLIF(u.full_name, ''), {entered_by})
			WHERE IFNULL(bill.created_by, '') = ''
			"""
		)
