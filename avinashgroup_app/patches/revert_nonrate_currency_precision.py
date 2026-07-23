# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Undo the blanket 5-decimal precision (sales_currency_precision_5) on everything
EXCEPT the per-unit rate fields.

sales_currency_precision_5 set precision=5 on EVERY Currency field of the selling
documents + Payment Entry and their children. We only want 5 decimals on the rate
fields (see rate_fields_precision_5). This removes the precision Property Setter
from every OTHER Currency field on those doctypes, so amounts/totals/taxes go back
to the default currency precision (2). Applied once per site on migrate; idempotent.

Item Price is untouched (it is not a child of these parents; its rate stays at 5)."""

import frappe

PARENT_DOCTYPES = [
	"Sales Invoice",
	"Payment Entry",
	"Sales Order",
	"Quotation",
	"Delivery Note",
]

RATE_FIELDS = ["price_list_rate", "base_price_list_rate", "rate", "base_rate", "net_rate", "base_net_rate"]

# Currency fields to KEEP at 5 (do NOT revert) — the rate fields on the item tables.
KEEP = {
	"Sales Invoice Item": set(RATE_FIELDS),
	"Sales Order Item": set(RATE_FIELDS),
	"Quotation Item": set(RATE_FIELDS),
	"Delivery Note Item": set(RATE_FIELDS),
}


def execute():
	doctypes = set()
	for parent in PARENT_DOCTYPES:
		doctypes.add(parent)
		for table_field in frappe.get_meta(parent).get_table_fields():
			doctypes.add(table_field.options)

	for doctype in sorted(doctypes):
		keep = KEEP.get(doctype, set())
		for df in frappe.get_meta(doctype).fields:
			if df.fieldtype != "Currency" or df.fieldname in keep:
				continue
			frappe.db.delete(
				"Property Setter",
				{"doc_type": doctype, "field_name": df.fieldname, "property": "precision"},
			)
		frappe.clear_cache(doctype=doctype)
