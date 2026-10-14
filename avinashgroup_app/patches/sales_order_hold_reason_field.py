# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Sales Order: "Reason" (custom_hold_reason).

Holds the reasons typed when the order was put On Hold, Closed or
Cancelled, one per line, as "Hold: ... (date)", "Close: ..." or "Cancel: ...". Stock ERPNext keeps
a hold reason only as a timeline Comment and asks none on Close / Cancel.
Written by custom_code/sales_order_status_reason.record_status_reason, from
public/js/sales_order_status_reason.js.

Kept after Resume / Re-open, on purpose: the client wants to see that the
order was stopped once and why. Each action adds a new line, so it holds
every reason, oldest first.

Read-only (filled only by those popups), allow_on_submit (holding happens on
a submitted order), shown only once it has a value. Sits under Order Type.

Uses create_custom_fields(update=True) so a site that already has the field
(it first shipped under Remarks) gets it moved, not skipped.

Ships as a name-scoped Custom Field fixture in hooks.py too; this patch exists
because sync_on_migrate is intentionally 0 on this app's customizations.

Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELD = {
	"fieldname": "custom_hold_reason",
	"label": "Reason",
	"fieldtype": "Small Text",
	"insert_after": "order_type",
	"read_only": 1,
	"allow_on_submit": 1,
	"no_copy": 1,
	"depends_on": "eval:doc.custom_hold_reason",
	# No help text under the field (removed 2026-10-11); "" clears it on sites
	# that already have it.
	"description": "",
}


def execute():
	create_custom_fields({"Sales Order": [FIELD]}, ignore_validate=True, update=True)
	frappe.clear_cache(doctype="Sales Order")
