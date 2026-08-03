# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Selling Settings: "Allow Sales Invoice with Zero Quantity".

ERPNext ships allow_zero_qty_in_* checkboxes for Quotation, Sales Order,
Purchase Order, RFQ and Supplier Quotation — but NOT for Sales Invoice, whose
only zero-qty escapes are is_return and is_debit_note (accounts_controller
.validate_qty_is_not_zero). is_debit_note is the wrong shape for a plain
zero-qty row: with qty=0 the totals code bills item.amount = rate, inventing
revenue on a row meant to carry none.

This adds the missing sibling setting, placed next to the ERPNext ones and
worded like them. salesinvoice_taxes.allow_zero_qty_rows reads it.

The field also ships as a name-scoped Custom Field fixture in hooks.py, so new
installs get it. This patch exists because sync_on_migrate is intentionally 0
on this app's customizations, and to cover sites that predate the fixture.

Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

FIELD = {
	"fieldname": "custom_allow_zero_qty_in_sales_invoice",
	"label": "Allow Sales Invoice with Zero Quantity",
	"fieldtype": "Check",
	"default": "0",
	"insert_after": "allow_zero_qty_in_sales_order",
	"description": (
		"Allows Sales Invoices to be saved and submitted with zero quantity item rows. "
		"Such rows carry no value (amount = 0) and post no GL entries. Intended for bulk "
		"data loads of legacy invoices; leave off for normal desk entry, where a zero "
		"quantity is almost always a typo."
	),
}


def execute():
	create_custom_field("Selling Settings", FIELD, ignore_validate=True)
	frappe.clear_cache(doctype="Selling Settings")
