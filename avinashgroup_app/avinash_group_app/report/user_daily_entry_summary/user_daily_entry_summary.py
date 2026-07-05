# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""User Daily Entry Summary — for a chosen user and a single day, count the
documents that user created, broken down by document type and current status:
Draft / Submitted / Cancelled.

Only the document types configured in **User Daily Entry Summary Settings** are
scanned. Counting reads each doctype's own table with one indexed query per
doctype — owner = user AND creation within the day, aggregated by docstatus.
The composite (owner, creation) index added by `add_creation_index_daily_entry`
keeps it fast. Non-submittable doctypes only ever have a Draft (docstatus 0)
state, so their counts land in the Draft column.
"""

import frappe
from frappe import _
from frappe.utils import cint

SETTINGS_DOCTYPE = "User Daily Entry Summary Settings"


def execute(filters=None):
	filters = frappe._dict(filters or {})

	if not filters.get("user"):
		frappe.throw(_("Please select a User."))
	if not filters.get("date"):
		frappe.throw(_("Please select a Date."))

	from_dt = f"{filters.date} 00:00:00"
	to_dt = f"{filters.date} 23:59:59"

	tracked = _tracked_doctypes()
	if not tracked:
		frappe.msgprint(
			_("No document types are configured. Add them in {0} first.").format(
				frappe.utils.get_link_to_form("User Daily Entry Summary Settings", SETTINGS_DOCTYPE)
			)
		)
		return _columns(), []

	doctypes = _scope_doctypes(filters.get("document_type"), tracked)

	# Cache read-permission per doctype for the running user (not the audited user).
	perm_cache = {}

	def can_read(dt):
		if dt not in perm_cache:
			perm_cache[dt] = frappe.has_permission(dt, "read")
		return perm_cache[dt]

	# One query for all doctypes' existence instead of one per doctype.
	valid = set(frappe.get_all("DocType", filters={"name": ["in", doctypes]}, pluck="name"))
	readable = [dt for dt in doctypes if dt in valid and can_read(dt)]

	rows = []
	for dt, counts in _status_counts(filters.user, from_dt, to_dt, readable).items():
		draft, submitted, cancelled = counts
		total = draft + submitted + cancelled
		if not total:
			continue
		rows.append(
			{
				"document_type": dt,
				"draft": draft,
				"submitted": submitted,
				"cancelled": cancelled,
				"total": total,
			}
		)

	# Busiest doctype first, then alphabetical for stable ordering.
	rows.sort(key=lambda r: (-r["total"], r["document_type"]))

	return _columns(), rows


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


def _status_counts(user, from_dt, to_dt, doctypes):
	"""{doctype: (draft, submitted, cancelled)} for docs the user created in the day.

	One conditional-aggregate query per doctype, riding the (owner, creation)
	index for the date range and counting each docstatus in a single pass.
	"""
	result = {}
	params = {"user": user, "from_dt": from_dt, "to_dt": to_dt}

	for dt in doctypes:
		table = f"tab{dt}"
		row = frappe.db.sql(
			f"""
			SELECT
				SUM(docstatus = 0) AS draft,
				SUM(docstatus = 1) AS submitted,
				SUM(docstatus = 2) AS cancelled
			FROM `{table}`
			WHERE owner = %(user)s
			  AND creation BETWEEN %(from_dt)s AND %(to_dt)s
			""",
			params,
			as_dict=True,
		)[0]
		result[dt] = (cint(row.draft), cint(row.submitted), cint(row.cancelled))

	return result


def _columns():
	return [
		{
			"label": _("Document Type"),
			"fieldname": "document_type",
			"fieldtype": "Link",
			"options": "DocType",
			"width": 240,
		},
		{"label": _("Draft"), "fieldname": "draft", "fieldtype": "Int", "width": 110},
		{"label": _("Submitted"), "fieldname": "submitted", "fieldtype": "Int", "width": 110},
		{"label": _("Cancelled"), "fieldname": "cancelled", "fieldtype": "Int", "width": 110},
		{"label": _("Total"), "fieldname": "total", "fieldtype": "Int", "width": 110},
	]


@frappe.whitelist()
def get_tracked_doctypes(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None):
	"""Feed the Document Type MultiSelect filter with the configured doctype list."""
	tracked = _tracked_doctypes()
	if txt:
		txt_lower = txt.lower()
		tracked = [d for d in tracked if txt_lower in d.lower()]
	return [{"value": d, "description": d} for d in tracked]
