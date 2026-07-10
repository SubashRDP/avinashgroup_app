# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Set 5-decimal precision on every Currency field of the selling documents
(Sales Invoice, Sales Order, Quotation, Delivery Note) and Payment Entry,
including all their child tables — applied once per site on migrate.

The setters persist afterwards: every exported customization file in
avinash_group_app/custom/ now has sync_on_migrate: 0, so nothing deletes
Property Setters on migrate anymore. Sites keep these values (and any later
Customize Form change the functional team makes on top)."""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

PARENT_DOCTYPES = [
	"Sales Invoice",
	"Payment Entry",
	"Sales Order",
	"Quotation",
	"Delivery Note",
]

PRECISION = "5"


def execute():
	doctypes = set()
	for parent in PARENT_DOCTYPES:
		doctypes.add(parent)
		for table_field in frappe.get_meta(parent).get_table_fields():
			doctypes.add(table_field.options)

	for doctype in sorted(doctypes):
		for df in frappe.get_meta(doctype).fields:
			if df.fieldtype != "Currency":
				continue
			frappe.db.delete(
				"Property Setter",
				{"doc_type": doctype, "field_name": df.fieldname, "property": "precision"},
			)
			make_property_setter(
				doctype,
				df.fieldname,
				"precision",
				PRECISION,
				"Select",
				for_doctype=False,
				validate_fields_for_doctype=False,
			)
		frappe.clear_cache(doctype=doctype)
