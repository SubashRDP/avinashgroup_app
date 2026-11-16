"""Keeps the Transporter list in step with suppliers ticked "Is Transporter".

"Name of Transportor" on Purchase Invoice / Purchase Receipt links to the
Transporter doctype. That list holds two kinds of names: transporters typed in
by hand (no supplier needed) and suppliers ticked "Is Transporter". Without this
hook a supplier ticked as transporter would never show in the field.

Deliberately add-only: unticking a supplier does not delete or disable its
Transporter, because bills that already use the name must keep linking to it.
Hiding one from the dropdown is done by ticking Disabled on the Transporter.
The one-time setup (old Select names, already-ticked suppliers, Select -> Link)
is patches/transporter_select_to_link.py. See docs/transporter.md.
"""

import frappe


def add_supplier_as_transporter(doc, method=None):
	"""Supplier on_update (hooks.py): create a Transporter named after a
	supplier ticked "Is Transporter", if there isn't one already."""
	if doc.is_transporter and doc.supplier_name:
		ensure_transporter(doc.supplier_name)


def ensure_transporter(name):
	"""Create a Transporter whose name (and record ID) is `name`; no-op if it exists."""
	name = name.strip()
	if name and not frappe.db.exists("Transporter", name):
		frappe.get_doc({"doctype": "Transporter", "transporter_name": name}).insert(
			ignore_permissions=True, set_name=name
		)
