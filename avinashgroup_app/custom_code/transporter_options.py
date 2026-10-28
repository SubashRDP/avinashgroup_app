import frappe

# "Name of Transportor" is a Select field on these doctypes. Its options are
# the old fixed names plus every supplier ticked "Is Transporter".
TRANSPORTER_FIELD = "custom_name_of_transportor"
TRANSPORTER_DOCTYPES = ("Purchase Invoice", "Purchase Receipt")


def add_transporter_option(doc, method=None):
	"""Supplier on_update: add this supplier's name to the transporter list.

	Names are only ever added, never removed, so old bills that use a name
	stay valid even after the supplier is unticked.
	"""
	if doc.is_transporter and doc.supplier_name:
		add_option(doc.supplier_name)


def add_option(name):
	name = name.strip()
	for doctype in TRANSPORTER_DOCTYPES:
		field = frappe.db.get_value(
			"Custom Field",
			{"dt": doctype, "fieldname": TRANSPORTER_FIELD},
			["name", "options"],
			as_dict=True,
		)
		if not field:
			continue

		options = (field.options or "").split("\n")
		if name in [o.strip() for o in options]:
			continue

		# Drop trailing blank lines so the new name goes right after the last one;
		# the leading blank line (the empty choice) is kept.
		while len(options) > 1 and not options[-1].strip():
			options.pop()
		options.append(name)

		frappe.db.set_value("Custom Field", field.name, "options", "\n".join(options))
		frappe.clear_cache(doctype=doctype)
