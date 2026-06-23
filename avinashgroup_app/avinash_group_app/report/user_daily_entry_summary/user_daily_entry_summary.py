# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""User Daily Entry Summary — for a chosen user and a single day, count how many
*parent* documents that user created and/or modified, broken down by document type.

Only the document types configured in **User Daily Entry Summary Settings** are
scanned — this keeps the report fast instead of looping every audited doctype.

  * "Created" -> each tracked doctype, counted by custom_created_by + creation date.
  * "Modified" -> Frappe's Version table (owner = the user who saved); distinct
                  docnames per ref_doctype, so a doc with child-row edits counts once.

Child-table rows are never counted — both sources are inherently parent-level.
Only doctypes the *running* user can read are surfaced.
"""

import json

import frappe
from frappe import _

CREATED_BY_FIELD = "custom_created_by"
SETTINGS_DOCTYPE = "User Daily Entry Summary Settings"


def execute(filters=None):
	filters = frappe._dict(filters or {})

	if not filters.get("user"):
		frappe.throw(_("Please select a User."))
	if not filters.get("date"):
		frappe.throw(_("Please select a Date."))

	action = filters.get("action") or "Both"
	from_dt = f"{filters.date} 00:00:00"
	to_dt = f"{filters.date} 23:59:59"

	tracked = _tracked_doctypes()
	if not tracked:
		frappe.msgprint(
			_("No document types are configured. Add them in {0} first.").format(
				frappe.utils.get_link_to_form("User Daily Entry Summary Settings", SETTINGS_DOCTYPE)
			)
		)
		return _columns(action), []

	doctypes = _scope_doctypes(filters.get("document_type"), tracked)

	# Cache read-permission per doctype for the running user (not the audited user).
	perm_cache = {}

	def can_read(dt):
		if dt not in perm_cache:
			perm_cache[dt] = frappe.has_permission(dt, "read")
		return perm_cache[dt]

	readable = [dt for dt in doctypes if frappe.db.exists("DocType", dt) and can_read(dt)]

	created = (
		_created_counts(filters.user, from_dt, to_dt, readable)
		if action in ("Both", "Created")
		else {}
	)
	modified = (
		_modified_counts(filters.user, from_dt, to_dt, readable)
		if action in ("Both", "Modified")
		else {}
	)

	rows = []
	for dt in sorted(set(created) | set(modified)):
		c = created.get(dt, 0)
		mod_names = modified.get(dt, [])
		m = len(mod_names)
		if not c and not m:
			continue
		rows.append(
			{
				"document_type": dt,
				"created": c,
				"modified": m,
				"total": c + m,
				# Carried for the JS formatter so the Modified cell can link to the
				# exact documents (Version rows have no doctype field to filter on).
				"modified_names": json.dumps(mod_names),
			}
		)

	# Busiest doctype first, then alphabetical for stable ordering.
	rows.sort(key=lambda r: (-r["total"], r["document_type"]))

	return _columns(action), rows


def _tracked_doctypes():
	"""The configured list of doctypes to count (from the settings Single)."""
	try:
		settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
	except Exception:
		return []

	seen = []
	for row in settings.get("tracked_doctypes") or []:
		if row.document_type and row.document_type not in seen:
			seen.append(row.document_type)
	return seen


def _scope_doctypes(document_type, tracked):
	"""Configured doctypes, optionally narrowed to the selected document_type filter."""
	if not document_type:
		return tracked

	selected = document_type if isinstance(document_type, (list, tuple)) else [document_type]
	selected = set(selected)
	return [d for d in tracked if d in selected]


def _created_counts(user, from_dt, to_dt, doctypes):
	"""{doctype: number of parent docs created by `user` on the day}."""
	counts = {}
	for dt in doctypes:
		# Doctype may not (yet) carry the audit field — skip cleanly.
		if not frappe.get_meta(dt).has_field(CREATED_BY_FIELD):
			continue
		try:
			n = frappe.db.count(
				dt,
				{
					CREATED_BY_FIELD: user,
					"creation": ["between", [from_dt, to_dt]],
				},
			)
		except Exception:
			# Defensive: any doctype-specific query issue shouldn't break the report.
			continue
		if n:
			counts[dt] = n
	return counts


def _modified_counts(user, from_dt, to_dt, doctypes):
	"""{doctype: [distinct parent docnames `user` modified on the day]}.

	One grouped query over the Version table; GROUP BY (ref_doctype, docname) so
	multiple edits to the same document (or several child-row changes) yield the
	document once. The names let the report link the count to those exact docs.
	"""
	if not doctypes:
		return {}

	rows = frappe.db.sql(
		"""
		SELECT ref_doctype AS dt, docname
		FROM `tabVersion`
		WHERE owner = %(user)s
		  AND creation BETWEEN %(from_dt)s AND %(to_dt)s
		  AND ref_doctype IN %(doctypes)s
		GROUP BY ref_doctype, docname
		""",
		{
			"user": user,
			"from_dt": from_dt,
			"to_dt": to_dt,
			"doctypes": tuple(doctypes),
		},
		as_dict=True,
	)
	result = {}
	for r in rows:
		result.setdefault(r.dt, []).append(r.docname)
	return result


def _columns(action):
	doc_col = {
		"label": _("Document Type"),
		"fieldname": "document_type",
		"fieldtype": "Link",
		"options": "DocType",
		"width": 240,
	}
	created_col = {"label": _("Created"), "fieldname": "created", "fieldtype": "Int", "width": 120}
	modified_col = {"label": _("Modified"), "fieldname": "modified", "fieldtype": "Int", "width": 120}
	total_col = {"label": _("Total"), "fieldname": "total", "fieldtype": "Int", "width": 120}

	if action == "Created":
		return [doc_col, created_col]
	if action == "Modified":
		return [doc_col, modified_col]
	return [doc_col, created_col, modified_col, total_col]


@frappe.whitelist()
def get_tracked_doctypes(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None):
	"""Feed the Document Type MultiSelect filter with the configured doctype list."""
	tracked = _tracked_doctypes()
	if txt:
		txt_lower = txt.lower()
		tracked = [d for d in tracked if txt_lower in d.lower()]
	return [{"value": d, "description": d} for d in tracked]
