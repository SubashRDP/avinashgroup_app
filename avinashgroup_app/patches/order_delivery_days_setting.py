# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Selling Settings: "Default Delivery Days".

The customer portal's Place Order page pre-fills Expected Delivery as today +
N days. N was hard-coded to 7 in templates/pages/place_order.py; the depot
wants to set it without a code change. place_order.get_context reads this
field (and falls back to 7 while it does not exist yet).

Scope: the portal Place Order page only. Desk Sales Orders are untouched.

Ships as a name-scoped Custom Field fixture in hooks.py too; this patch exists
because sync_on_migrate is intentionally 0 on this app's customizations.

Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

FIELD = {
	"fieldname": "custom_order_delivery_days",
	"label": "Default Delivery Days",
	"fieldtype": "Int",
	"default": "7",
	"non_negative": 1,
	"insert_after": "allow_zero_qty_in_quotation",
	"description": (
		"Expected Delivery on the customer portal's Place Order page is filled in as "
		"the order date plus this many days. The customer can still pick another date. "
		"0 = same day."
	),
}


def execute():
	create_custom_field("Selling Settings", FIELD, ignore_validate=True)
	frappe.clear_cache(doctype="Selling Settings")
	# A new field on a Single has no tabSingles row until the settings are saved,
	# and get_single_value reads a missing Int as 0, i.e. same-day delivery. Seed
	# the old hard-coded 7 so behaviour does not change on deploy; a value an
	# admin already saved is left alone.
	stored = frappe.db.sql(
		"""SELECT 1 FROM `tabSingles`
		WHERE doctype = 'Selling Settings' AND field = 'custom_order_delivery_days'"""
	)
	if not stored:
		frappe.db.set_single_value("Selling Settings", "custom_order_delivery_days", 7)
