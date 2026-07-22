# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Set 5-decimal precision, field-wise, on the per-unit RATE fields only:

- Item Price -> price_list_rate (its "Rate" field)
- Sales Invoice Item / Sales Order Item / Quotation Item / Delivery Note Item
  -> price_list_rate, base_price_list_rate, rate, base_rate, net_rate, base_net_rate

Unlike sales_currency_precision_5 (which set every Currency field to 5), this
targets only the rate fields, where the extra decimals actually matter. Applied
once per site on migrate; idempotent (safe to re-run)."""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

PRECISION = "5"

# doctype -> the Currency fields to bump to 5 decimals
TARGETS = {
	"Item Price": ["price_list_rate"],
	"Sales Invoice Item": ["price_list_rate", "base_price_list_rate", "rate", "base_rate", "net_rate", "base_net_rate"],
	"Sales Order Item": ["price_list_rate", "base_price_list_rate", "rate", "base_rate", "net_rate", "base_net_rate"],
	"Quotation Item": ["price_list_rate", "base_price_list_rate", "rate", "base_rate", "net_rate", "base_net_rate"],
	"Delivery Note Item": ["price_list_rate", "base_price_list_rate", "rate", "base_rate", "net_rate", "base_net_rate"],
}


def set_precision(doctype, fieldname):
	df = frappe.get_meta(doctype).get_field(fieldname)
	if not df or df.fieldtype != "Currency":
		# Field missing or not a Currency field on this site — skip quietly.
		return
	frappe.db.delete(
		"Property Setter",
		{"doc_type": doctype, "field_name": fieldname, "property": "precision"},
	)
	make_property_setter(
		doctype,
		fieldname,
		"precision",
		PRECISION,
		"Select",
		for_doctype=False,
		validate_fields_for_doctype=False,
	)


def execute():
	for doctype, fields in TARGETS.items():
		for fieldname in fields:
			set_precision(doctype, fieldname)
		frappe.clear_cache(doctype=doctype)
