# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Exempt the virtual "Total Amount" preview field from the after-submit check.

Any Data Import of type "Update Existing Records" against submitted Sales
Invoices fails on ng-group with, for every row:

    frappe.exceptions.UpdateAfterSubmitError:
      Not allowed to change Total Amount after submission from 24180.0 to 0.0

"Total Amount" is `custom_expected_grand_total` — the VIRTUAL field added by
add_grand_total_preview_field.py. It has no database column; its value comes
from evaluating

    (doc.custom_total_amount_including_excise or 0) + (doc.custom_total_vat_amount or 0)

Frappe's `_validate_update_after_submit` (base_document.py) compares every
field of the in-memory document against the stored one and throws on any
difference where allow_on_submit is 0. Newer Frappe skips virtual fields:

    if df and not df.allow_on_submit and not df.is_virtual and (...)

That `not df.is_virtual` guard landed in **v15.107.0** (commit 0fe9147).
ng-group runs **15.80.0**, so the guard is absent and the virtual field is
compared like a real one. The two sides then disagree for a reason that has
nothing to do with the data: the document loaded from the database evaluates
the expression against its stored source fields (24180.0), while the import's
version has no such columns in the spreadsheet and evaluates to 0.0.

The proper fix is upgrading Frappe past 15.107.0. Until then this marks the
field allow_on_submit, which only exempts it from that comparison. Nothing is
stored (is_virtual) and nobody can type into it (read_only), so permitting it
"on submit" changes no behaviour and no data — it just stops an old Frappe
blocking updates over a display-only preview.

Safe to drop once Frappe is upgraded; harmless if left in place.
"""

import frappe

FIELD = "Sales Invoice-custom_expected_grand_total"


def execute():
	if not frappe.db.exists("Custom Field", FIELD):
		return

	if frappe.db.get_value("Custom Field", FIELD, "allow_on_submit"):
		return

	field = frappe.get_doc("Custom Field", FIELD)
	field.allow_on_submit = 1
	field.flags.ignore_permissions = True
	field.save()

	# db.set_value would skip Custom Field's on_update, so clear explicitly:
	# the check reads df.allow_on_submit off the cached Sales Invoice meta.
	frappe.clear_cache(doctype="Sales Invoice")
	print(f"{FIELD}: allow_on_submit = 1")
