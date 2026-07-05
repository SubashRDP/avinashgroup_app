# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""User Audit Trail — for a chosen user, show the documents they created and the
field-level changes they made (original -> new), across the audited doctypes.

Two data sources, merged into one chronological table:
  * "Created" rows  -> each audited doctype, filtered by custom_created_by.
  * "Modified" rows -> Frappe's Version table (owner = the user who changed it),
                       its `data` JSON expanded one row per changed field /
                       child-row add / remove / change.

Only documents whose doctype the *running* user can read are surfaced.
"""

import json

import frappe
from frappe import _
from frappe.utils import cstr

from avinashgroup_app.utils.audit_file_manager import AuditBase

CREATED_BY_FIELD = "custom_created_by"

# Friendlier rendering for the framework's docstatus field (the most common change).
DOCSTATUS_LABELS = {"0": "Draft", "1": "Submitted", "2": "Cancelled"}
FIELD_LABEL_OVERRIDES = {"docstatus": "Document Status", "name": "ID"}


def execute(filters=None):
	filters = frappe._dict(filters or {})

	if not filters.get("user"):
		frappe.throw(_("Please select a User."))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("Please select From Date and To Date."))

	action = filters.get("action") or "All"
	from_dt = f"{filters.from_date} 00:00:00"
	to_dt = f"{filters.to_date} 23:59:59"

	doctypes = _scope_doctypes(filters.get("document_type"))

	# Cache read-permission per doctype for the running user (not the audited user).
	perm_cache = {}

	def can_read(dt):
		if dt not in perm_cache:
			perm_cache[dt] = frappe.has_permission(dt, "read")
		return perm_cache[dt]

	rows = []
	if action in ("All", "Created"):
		rows += _created_rows(filters.user, from_dt, to_dt, doctypes, can_read)
	if action in ("All", "Modified"):
		rows += _modified_rows(filters.user, from_dt, to_dt, doctypes, can_read)

	# Newest first.
	rows.sort(key=lambda r: r.get("_ts") or "", reverse=True)
	for r in rows:
		r.pop("_ts", None)

	return _columns(), rows


def _scope_doctypes(document_type):
	"""Audited doctypes, optionally narrowed to the selected document_type filter."""
	audited = sorted(set(AuditBase.doctypes))
	if not document_type:
		return audited

	selected = document_type if isinstance(document_type, (list, tuple)) else [document_type]
	selected = set(selected)
	return [d for d in audited if d in selected]


def _created_rows(user, from_dt, to_dt, doctypes, can_read):
	rows = []
	# One query for all doctypes' existence instead of one per doctype.
	existing = set(frappe.get_all("DocType", filters={"name": ["in", doctypes]}, pluck="name"))
	for dt in doctypes:
		if dt not in existing or not can_read(dt):
			continue
		# Doctype may not (yet) carry the audit field — skip cleanly.
		if not frappe.get_meta(dt).has_field(CREATED_BY_FIELD):
			continue

		try:
			records = frappe.get_all(
				dt,
				filters={
					CREATED_BY_FIELD: user,
					"creation": ["between", [from_dt, to_dt]],
				},
				fields=["name", "creation"],
			)
		except Exception:
			# Defensive: any doctype-specific query issue shouldn't break the report.
			continue

		for rec in records:
			rows.append(
				{
					"_ts": cstr(rec.creation),
					"timestamp": rec.creation,
					"document_type": dt,
					"document_name": rec.name,
					"action": "Created",
					"field": "",
					"original_value": "",
					"new_value": "",
				}
			)
	return rows


def _modified_rows(user, from_dt, to_dt, doctypes, can_read):
	allowed = set(doctypes)
	versions = frappe.get_all(
		"Version",
		filters={
			"owner": user,
			"creation": ["between", [from_dt, to_dt]],
			"ref_doctype": ["in", list(allowed)],
		},
		fields=["ref_doctype", "docname", "creation", "data"],
		order_by="creation desc",
	)

	rows = []
	for v in versions:
		dt = v.ref_doctype
		if not can_read(dt):
			continue
		try:
			data = json.loads(v.data or "{}")
		except (ValueError, TypeError):
			continue

		base = {
			"_ts": cstr(v.creation),
			"timestamp": v.creation,
			"document_type": dt,
			"document_name": v.docname,
			"action": "Modified",
		}

		for change in data.get("changed", []):
			fieldname, old, new = (list(change) + [None, None, None])[:3]
			rows.append(
				{
					**base,
					"field": _field_label(dt, fieldname),
					"original_value": _val(old, fieldname),
					"new_value": _val(new, fieldname),
				}
			)

		for entry in data.get("row_changed", []):
			# [table_fieldname, row_index, row_name, [[child_field, old, new], ...]]
			table_field = entry[0]
			child_dt = _child_doctype(dt, table_field)
			for child_change in entry[3] or []:
				cf, old, new = (list(child_change) + [None, None, None])[:3]
				rows.append(
					{
						**base,
						"field": f"{_field_label(dt, table_field)} → {_field_label(child_dt, cf)}",
						"original_value": _val(old),
						"new_value": _val(new),
					}
				)

		for entry in data.get("added", []):
			table_field = entry[0]
			rows.append(
				{
					**base,
					"field": _field_label(dt, table_field),
					"original_value": "",
					"new_value": _("Row added: {0}").format(_row_summary(entry[1])),
				}
			)

		for entry in data.get("removed", []):
			table_field = entry[0]
			rows.append(
				{
					**base,
					"field": _field_label(dt, table_field),
					"original_value": _("Row removed: {0}").format(_row_summary(entry[1])),
					"new_value": "",
				}
			)

	return rows


def _field_label(doctype, fieldname):
	"""Human label for a fieldname; fall back to the raw name (e.g. docstatus, name)."""
	if not fieldname:
		return ""
	if fieldname in FIELD_LABEL_OVERRIDES:
		return FIELD_LABEL_OVERRIDES[fieldname]
	if not doctype:
		return fieldname
	try:
		df = frappe.get_meta(doctype).get_field(fieldname)
		if df and df.label:
			return df.label
	except Exception:
		pass
	return fieldname


def _child_doctype(parent_doctype, table_fieldname):
	try:
		df = frappe.get_meta(parent_doctype).get_field(table_fieldname)
		return df.options if df else None
	except Exception:
		return None


def _val(value, fieldname=None):
	if value is None:
		return ""
	if fieldname == "docstatus":
		return DOCSTATUS_LABELS.get(cstr(value), cstr(value))
	return cstr(value)


def _row_summary(row_dict):
	"""Compact identifier for an added/removed child row — a few meaningful fields."""
	if not isinstance(row_dict, dict):
		return cstr(row_dict)
	skip = {"name", "parent", "parentfield", "parenttype", "doctype", "idx", "owner",
		"creation", "modified", "modified_by", "docstatus"}
	parts = []
	for key, val in row_dict.items():
		if key in skip or val in (None, "", 0):
			continue
		parts.append(f"{key}={val}")
		if len(parts) >= 4:
			break
	return ", ".join(parts) or (row_dict.get("name") or "")


def _columns():
	return [
		{"label": _("Date / Time"), "fieldname": "timestamp", "fieldtype": "Datetime", "width": 160},
		{"label": _("Document Type"), "fieldname": "document_type", "fieldtype": "Link",
			"options": "DocType", "width": 160},
		{"label": _("Document"), "fieldname": "document_name", "fieldtype": "Dynamic Link",
			"options": "document_type", "width": 200},
		{"label": _("Action"), "fieldname": "action", "fieldtype": "Data", "width": 90},
		{"label": _("Field"), "fieldname": "field", "fieldtype": "Data", "width": 200},
		{"label": _("Original Value"), "fieldname": "original_value", "fieldtype": "Data", "width": 240},
		{"label": _("New Value"), "fieldname": "new_value", "fieldtype": "Data", "width": 240},
	]


@frappe.whitelist()
def get_audited_doctypes(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None):
	"""Feed the Document Type MultiSelect filter with the audited doctype list."""
	audited = sorted(set(AuditBase.doctypes))
	if txt:
		txt_lower = txt.lower()
		audited = [d for d in audited if txt_lower in d.lower()]
	return [{"value": d, "description": d} for d in audited]
