# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Remove the mandatory_depends_on property setters for the Vehicle field
(custom_subtype) on Journal Entry Account / Purchase Invoice Item.

v1 of this patch created them, but Frappe's grid mutates the shared docfield
(grid_row.js set_dependant_property sets df.reqd = 1) when the expression is
true for any row, so the Vehicle column got flagged mandatory on every row.
Enforcement now lives in custom_code.vehicle_mandatory (server, per-row) and
public/js/vehicle_mandatory.js (client, per-row). Re-run on existing sites via
the '#2' line in patches.txt; harmless no-op where the setters never existed."""

import frappe


def execute():
	for doctype in ("Journal Entry Account", "Purchase Invoice Item"):
		frappe.db.delete(
			"Property Setter",
			{
				"doc_type": doctype,
				"field_name": "custom_subtype",
				"property": "mandatory_depends_on",
			},
		)
	frappe.clear_cache(doctype="Journal Entry")
	frappe.clear_cache(doctype="Purchase Invoice")
