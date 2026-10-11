# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Sales Order: "Remarks" (custom_remarks).

The customer portal's Place Order page has a Remarks box where the customer
can leave a note for the depot (in place of the old Order Date / Expected
Delivery fields, which are now set by the server). Stock Sales Order has no
free-text field for this, so create_sales_order in
templates/pages/place_order.py writes the note here.

Sits under Customer's Purchase Order Date so the depot sees it at the top of
the order. Editable in the desk; not tied to any validation.

Ships as a name-scoped Custom Field fixture in hooks.py too; this patch exists
because sync_on_migrate is intentionally 0 on this app's customizations.

Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

FIELD = {
	"fieldname": "custom_remarks",
	"label": "Remarks",
	"fieldtype": "Small Text",
	"insert_after": "po_date",
	"description": "Note from the customer, entered on the portal's Place Order page.",
}


def execute():
	create_custom_field("Sales Order", FIELD, ignore_validate=True)
	frappe.clear_cache(doctype="Sales Order")
