# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""User Daily Entry Summary — for a chosen user and a single day, count how many
*parent* documents that user created and/or modified, broken down by document type.

Only the document types configured in **User Daily Entry Summary Settings** are
scanned — this keeps the report fast instead of looping every audited doctype.

Counting reads each doctype's own table using standard, indexed timestamp columns
(no `tabVersion` scan):

  * "Created"  -> owner = user AND creation within the day.
  * "Modified" -> modified_by = user AND modified within the day, excluding rows
                  that were only inserted (modified == creation) so a freshly
                  created document is not also counted as modified.

Both sources are parent-level, so child-table rows are never counted. Only
doctypes the *running* user can read are surfaced. The `creation` index added by
`add_creation_index_daily_entry` keeps the Created lookup fast; `modified` is
already indexed by Frappe.
"""

import frappe
from frappe import _

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

	want_created = action in ("Both", "Created")
	want_modified = action in ("Both", "Modified")
	created, modified = _entry_counts(filters.user, from_dt, to_dt, readable, want_created, want_modified)

	rows = []
	for dt in sorted(set(created) | set(modified)):
		c = created.get(dt, 0)
		m = modified.get(dt, 0)
		if not c and not m:
			continue
		rows.append(
			{
				"document_type": dt,
				"created": c,
				"modified": m,
				"total": c + m,
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


def _entry_counts(user, from_dt, to_dt, doctypes, want_created, want_modified):
	"""Per-doctype counts read straight from each doctype's own table.

	One indexed range scan per metric per doctype:
	  * Created  uses the `creation` index (added by the daily-entry patch).
	  * Modified uses Frappe's built-in `modified` index, and excludes rows where
	    `modified == creation` (a pure insert) so a same-day creation is not also
	    counted as a modification.
	"""
	created, modified = {}, {}
	params = {"user": user, "from_dt": from_dt, "to_dt": to_dt}

	for dt in doctypes:
		table = f"tab{dt}"

		if want_created:
			c = frappe.db.sql(
				f"""
				SELECT COUNT(*) FROM `{table}`
				WHERE owner = %(user)s
				  AND creation BETWEEN %(from_dt)s AND %(to_dt)s
				""",
				params,
			)[0][0]
			if c:
				created[dt] = c

		if want_modified:
			m = frappe.db.sql(
				f"""
				SELECT COUNT(*) FROM `{table}`
				WHERE modified_by = %(user)s
				  AND modified BETWEEN %(from_dt)s AND %(to_dt)s
				  AND modified > creation
				""",
				params,
			)[0][0]
			if m:
				modified[dt] = m

	return created, modified


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
