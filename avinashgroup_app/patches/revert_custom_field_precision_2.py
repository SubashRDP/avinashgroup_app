# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Revert precision back to default (2) on every custom field that was at 5.

Only the standard per-unit rate fields (Group A: Item Price.price_list_rate and the
6 rate fields on the selling item tables — see rate_fields_precision_5) should keep
5 decimals. None of those are custom fields, so every Custom Field sitting at
precision 5 (the VAT / TDS / Excise fields) is reset to the default precision.
Idempotent."""

import frappe


def execute():
	affected = set()
	for cf in frappe.get_all(
		"Custom Field", filters={"precision": "5"}, fields=["name", "dt", "fieldname"]
	):
		frappe.db.set_value("Custom Field", cf.name, "precision", "", update_modified=False)
		affected.add(cf.dt)

	for doctype in affected:
		frappe.clear_cache(doctype=doctype)
