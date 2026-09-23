# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Buying-side twin of rate_fields_precision_5: 5-decimal precision on the
per-unit RATE fields only.

- Purchase Invoice Item / Purchase Order Item / Purchase Receipt Item /
  Supplier Quotation Item
  -> price_list_rate, base_price_list_rate, rate, base_rate, net_rate, base_net_rate
- Material Request Item -> price_list_rate, rate (the only rate fields it has)

Amounts and VAT stay at 2 dp — purchase_taxes_handler rounds each line's VAT to
paisa. Purchase Invoice Item rate/base_rate were at 3, written in the synced
custom/purchase_invoice_item.json — that file (sync_on_migrate: 1) now carries
all six rate fields at 5, and customizations sync AFTER patches on migrate, so
the file is what keeps them at 5 there. Applied once per site on migrate;
idempotent (safe to re-run)."""

import frappe

from avinashgroup_app.patches.rate_fields_precision_5 import set_precision

RATE_FIELDS = ["price_list_rate", "base_price_list_rate", "rate", "base_rate", "net_rate", "base_net_rate"]

# doctype -> the Currency fields to bump to 5 decimals
TARGETS = {
	"Purchase Invoice Item": RATE_FIELDS,
	"Purchase Order Item": RATE_FIELDS,
	"Purchase Receipt Item": RATE_FIELDS,
	"Supplier Quotation Item": RATE_FIELDS,
	"Material Request Item": ["price_list_rate", "rate"],
}


def execute():
	for doctype, fields in TARGETS.items():
		for fieldname in fields:
			set_precision(doctype, fieldname)
		frappe.clear_cache(doctype=doctype)
