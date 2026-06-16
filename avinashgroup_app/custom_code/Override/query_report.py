# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt
#
# Override of frappe.desk.query_report.get_data_for_custom_field — the server method
# behind a report's "Add Column" dialog.
# Customer's "Customer Group") shows the linked record's *id* (here a code like
# "NGK-CGR-0002"). This override resolves Link values to the linked record's display
# name (its title field, or a "<doctype>_name" field) so "Add Column" shows the name
# instead of the id — for every report, generically.

import frappe
from frappe import _


@frappe.whitelist()
def get_data_for_custom_field(doctype, field, names=None):
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not Permitted to read {0}").format(_(doctype)), frappe.PermissionError)

	filters = {}
	if names:
		if isinstance(names, (str, bytearray)):
			names = frappe.json.loads(names)
		filters.update({"name": ["in", names]})

	value_map = frappe._dict(
		frappe.get_list(doctype, filters=filters, fields=["name", field], as_list=1)
	)

	# If the added field is itself a Link, swap each id for the linked record's name.
	df = frappe.get_meta(doctype).get_field(field)
	if df and df.fieldtype == "Link" and df.options:
		name_map = _link_display_map(df.options, [v for v in value_map.values() if v])
		if name_map:
			value_map = frappe._dict({k: (name_map.get(v) or v) for k, v in value_map.items()})

	return value_map


def _link_display_map(link_doctype, ids):
	"""id -> display name for a linked doctype, via its title field (or '<doctype>_name')."""
	ids = list({i for i in ids if i})
	if not ids:
		return {}

	meta = frappe.get_meta(link_doctype)
	title = meta.title_field
	if not title:
		guess = frappe.scrub(link_doctype) + "_name"  # e.g. customer_group_name
		if meta.get_field(guess):
			title = guess
	# No usable display field (or it's just the name itself) → leave ids untouched.
	if not title or title == "name":
		return {}

	rows = frappe.get_all(link_doctype, filters={"name": ["in", ids]}, fields=["name", title])
	return {r["name"]: (r.get(title) or r["name"]) for r in rows}
