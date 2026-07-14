# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""VAT Apply On: default VAT 13%, never auto-changed.

Business rule: custom_vat_apply_on must default to "VAT 13%" and only ever
change when the user edits it manually. Two things violated that:

1. The Custom Field default was "VAT 0%" (or empty), so Frappe stamped VAT 0%
   on every new row and the desk JS raced to overwrite it — losing the race on
   barcode scans / fast entry, and API/Data Import rows kept VAT 0% silently.
   The custom/*.json exports carry the new default too, but sync_on_migrate is
   intentionally 0 on this app's customizations, so this patch applies it.

2. A legacy DB-only Client Script "Purchase Invoice" force-wrote the obsolete
   'Percentage (%)' option (no longer in the field's options → Select rendered
   blank) on item_code/items_add. Its only unique live feature — the Subtype
   dropdown filter — is ported to public/js/purchase_taxes_common.js, so the
   script is disabled here.

Purchase Invoice Item is included: its old 'Percentage (%)' percentage-mode
default maps to 'VAT 13%' in the current option scheme. Idempotent."""

import frappe

DOCTYPES = [
	"Sales Invoice Item",
	"Quotation Item",
	"Sales Order Item",
	"Delivery Note Item",
	"Purchase Invoice Item",
	"Purchase Order Item",
	"Purchase Receipt Item",
	"Supplier Quotation Item",
]


def execute():
	for dt in DOCTYPES:
		name = frappe.db.get_value(
			"Custom Field", {"dt": dt, "fieldname": "custom_vat_apply_on"}
		)
		if name:
			frappe.db.set_value("Custom Field", name, "default", "VAT 13%")
			frappe.clear_cache(doctype=dt)

	if frappe.db.exists("Client Script", "Purchase Invoice"):
		frappe.db.set_value("Client Script", "Purchase Invoice", "enabled", 0)
		frappe.clear_cache()
