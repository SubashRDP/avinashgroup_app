import frappe


OLD = "Nepal Gas Invoice A5"
NEW = "Nepal Gas Sales Invoice"


def execute():
	"""Rename the "Nepal Gas Invoice A5" print format to "Nepal Gas Sales Invoice".

	Runs before model sync, so the existing record is renamed in place and the
	sync then updates it from the renamed JSON — instead of the sync creating a
	second format beside the old one.
	"""
	if not frappe.db.exists("Print Format", OLD):
		return

	if frappe.db.exists("Print Format", NEW):
		frappe.delete_doc("Print Format", OLD, force=True, ignore_permissions=True)
	else:
		frappe.rename_doc("Print Format", OLD, NEW, force=True)

	# A Customize Form default print format is stored as plain text, which
	# rename_doc does not follow.
	frappe.db.set_value(
		"Property Setter",
		{"property": "default_print_format", "value": OLD},
		"value",
		NEW,
	)
