# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Turn "Name of Transportor" on Purchase Invoice / Purchase Receipt from a
Select with a fixed list into a Link to the Transporter doctype.

Every name the Select offered or any bill already holds becomes a Transporter
record named exactly that, so existing bills keep their value and it now links
to a real record. No bill is changed. Suppliers already ticked "Is Transporter"
are added too; later ticks are handled by custom_code/transporter.py.

Frappe does not allow Select -> Link from Customize Form, so the Custom Field
is updated directly. Both types use the same varchar column, so the column and
its data are untouched."""

import frappe

from avinashgroup_app.custom_code.transporter import ensure_transporter

FIELDNAME = "custom_name_of_transportor"
DOCTYPES = ("Purchase Invoice", "Purchase Receipt")


def execute():
	names = set()
	for doctype in DOCTYPES:
		options = frappe.db.get_value(
			"Custom Field", {"dt": doctype, "fieldname": FIELDNAME}, "options"
		)
		if options and options != "Transporter":
			names.update(options.split("\n"))

		names.update(
			frappe.get_all(
				doctype,
				filters={FIELDNAME: ["is", "set"]},
				pluck=FIELDNAME,
				distinct=True,
			)
		)

	names.update(frappe.get_all("Supplier", filters={"is_transporter": 1}, pluck="supplier_name"))

	for name in sorted(n for n in names if n and n.strip()):
		ensure_transporter(name)

	for doctype in DOCTYPES:
		field = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": FIELDNAME})
		if not field:
			continue
		frappe.db.set_value(
			"Custom Field", field, {"fieldtype": "Link", "options": "Transporter"}
		)
		frappe.clear_cache(doctype=doctype)
