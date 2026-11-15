# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""User Daily Entry Summary — what one user did, per document type, in a date range.

This report used to count only the documents a user CREATED on one day, split by
their current status. That left the auditor's real questions unanswered: what
did the clerk cancel, amend, edit or delete, and which documents were they? It
is now the front door of the audit trail: one row per document type with a
count per action, each type expandable to the documents behind the count, each
document opening in /app/document-audit-trail, and the user's own changes to a
document shown when it is hovered.

Actions, and where each comes from:
  Created    documents the user entered (custom_created_by, else owner)
  Amended    the same, where the document is an amendment of a cancelled one
  Submitted  Version row by the user with docstatus 0 -> 1
  Edited     any other Version row by the user with a real change in it
  Cancelled  Version row by the user with docstatus -> 2
  Deleted    Deleted Document rows the user owns (the deleter is its owner)
  Draft      documents entered in the range that are still unsubmitted now
A count is a number of documents, not of saves: ten edits to one invoice are 1.

The screen is drawn by user_daily_entry_summary.js from the rows returned here
(indent 0 = document type, indent 1 = document); the same rows are what Export
writes, so the report still exports like any other.

Deliberately narrow:
  * Only the document types listed in User Daily Entry Summary Settings.
  * It reports what the tables recorded. A document created and deleted inside
    the range shows as Deleted only (its creation row went with it), and edits
    written with db_set never produced a Version to count.
  * Background-job edits are owned by Administrator in Version, so they are not
    attributed to the person here. See docs/document-audit-trail.md.
"""

import json

import frappe
from frappe import _
from frappe.permissions import get_user_permissions
from frappe.utils import cstr

from avinashgroup_app.avinash_group_app.page.document_audit_trail.document_audit_trail import (
	NOISE_FIELDS,
	_same_blank,
)

SETTINGS_DOCTYPE = "User Daily Entry Summary Settings"
CREATED_BY_FIELD = "custom_created_by"

# Column order; also the fieldnames of the count columns.
ACTIONS = ("created", "amended", "submitted", "edited", "cancelled", "deleted")

DOCSTATUS_LABEL = {0: "Draft", 1: "Submitted", 2: "Cancelled"}

# Change lines sent per document for the hover card. More than this does not fit
# a card; the full history is one click away in the audit trail page.
MAX_CHANGE_LINES = 8
# A hover line is one line; a long remark is cut rather than wrapped.
MAX_VALUE_CHARS = 60


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# `date` is the filter this report had when it covered a single day; links
	# saved from then still pass it.
	if filters.get("date") and not filters.get("from_date"):
		filters.from_date = filters.to_date = filters.date
	if not filters.get("user"):
		frappe.throw(_("Please select a User."))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("Please select From Date and To Date."))
	if cstr(filters.from_date) > cstr(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))

	tracked = _tracked_doctypes()
	if not tracked:
		frappe.msgprint(
			_("No document types are configured. Add them in {0} first.").format(
				frappe.utils.get_link_to_form(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)
			)
		)
		return _columns(), []

	window = (f"{filters.from_date} 00:00:00", f"{filters.to_date} 23:59:59.999999")
	doctypes = _readable(_scope_doctypes(filters.get("document_type"), tracked))

	activity = Activity()
	_collect_created(filters.user, window, doctypes, activity)
	_collect_versions(filters.user, window, doctypes, activity)
	_resolve_current_state(activity)
	_collect_deleted(filters.user, window, doctypes, activity)

	return _columns(), _rows(activity), None, None, _summary(activity)


class Activity:
	"""Everything found, keyed by document: {(doctype, key): entry}.

	`key` is the document name, except for a deletion, which is keyed by its
	Deleted Document id — this app reuses a deleted number, so the same name
	can belong to a deleted document and a live one on the same day.
	"""

	def __init__(self):
		self.entries = {}

	def mark(self, doctype, key, action, when, **extra):
		entry = self.entries.setdefault(
			(doctype, key),
			{
				"doctype": doctype,
				"name": key,
				"actions": set(),
				"first": when,
				"exists": None,
				"changes": [],
				"more_changes": 0,
			},
		)
		entry["actions"].add(action)
		if when and (not entry["first"] or when < entry["first"]):
			entry["first"] = when
		entry.update(extra)
		return entry


# ------------------------------------------------------------------ scope


def _tracked_doctypes() -> list:
	"""The configured list of doctypes to report on (from the settings Single)."""
	try:
		settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
	except frappe.DoesNotExistError:
		return []

	seen = []
	for row in settings.get("tracked_doctypes") or []:
		if row.document_type and row.document_type not in seen:
			seen.append(row.document_type)
	return seen


def _scope_doctypes(document_type, tracked) -> list:
	"""Configured doctypes, optionally narrowed to the Document Type filter."""
	if not document_type:
		return tracked
	selected = set(document_type if isinstance(document_type, (list, tuple)) else [document_type])
	return [d for d in tracked if d in selected]


def _readable(doctypes) -> list:
	"""Those that exist here with a table of their own and that the RUNNING
	user (not the audited one) may read."""
	existing = set(
		frappe.get_all(
			"DocType",
			filters={"name": ["in", doctypes], "istable": 0, "issingle": 0, "is_virtual": 0},
			pluck="name",
		)
	)
	return [dt for dt in doctypes if dt in existing and frappe.has_permission(dt, "read")]


# ---------------------------------------------------------------- collect


def _collect_created(user, window, doctypes, activity) -> None:
	"""Documents the user entered. get_list, not get_all: the running user's
	User Permissions (company) must limit what they can see of another user."""
	for doctype in doctypes:
		meta = frappe.get_meta(doctype)
		by_field = CREATED_BY_FIELD if meta.has_field(CREATED_BY_FIELD) else "owner"
		fields = ["name", "creation", "docstatus"]
		if meta.has_field("amended_from"):
			fields.append("amended_from")
		rows = frappe.get_list(
			doctype,
			filters={by_field: user, "creation": ["between", window]},
			fields=fields,
			limit_page_length=0,
		)
		for row in rows:
			action = "amended" if row.get("amended_from") else "created"
			activity.mark(doctype, row.name, action, row.creation, exists=True, docstatus=row.docstatus)


def _collect_versions(user, window, doctypes, activity) -> None:
	"""Submits, cancels and edits, read from the user's Version rows; the
	changes themselves are kept for the hover card."""
	if not doctypes:
		return
	versions = frappe.get_all(
		"Version",
		filters={"owner": user, "creation": ["between", window], "ref_doctype": ["in", doctypes]},
		fields=["name", "ref_doctype", "docname", "creation", "data"],
		order_by="creation asc",
	)
	for version in versions:
		try:
			data = json.loads(version.data or "{}")
		except ValueError:
			frappe.log_error(
				title="User Daily Entry Summary: unreadable Version",
				message=f"Version {version.name} has data that is not valid JSON; skipped.",
			)
			continue
		action, lines = _read_version(version.ref_doctype, data)
		if not action:
			continue
		entry = activity.mark(version.ref_doctype, version.docname, action, version.creation)
		room = MAX_CHANGE_LINES - len(entry["changes"])
		entry["changes"] += lines[: max(room, 0)]
		entry["more_changes"] += max(len(lines) - max(room, 0), 0)


def _read_version(doctype, data):
	"""(action, change lines) for one Version.

	action is 'submitted' / 'cancelled' / 'edited', or None when the Version
	holds only recalculation noise (see NOISE_FIELDS) and so is not something
	the user did. Each line is {"label", "old", "new"}, ready to display.
	"""
	meta = frappe.get_meta(doctype)
	action = None
	lines = []

	for fieldname, old, new in data.get("changed") or []:
		if fieldname == "docstatus":
			action = {"1": "submitted", "2": "cancelled"}.get(str(new), action)
			continue
		if fieldname in NOISE_FIELDS or _same_blank(old, new):
			continue
		lines.append({"label": _label(meta, fieldname), "old": _short(old), "new": _short(new)})

	for table_field, idx, _row_name, changes in data.get("row_changed") or []:
		child_meta = _child_meta(meta, table_field)
		for fieldname, old, new in changes:
			if _same_blank(old, new):
				continue
			lines.append(
				{
					"label": _("{0} row {1} · {2}").format(
						_label(meta, table_field), int(idx) + 1, _label(child_meta, fieldname)
					),
					"old": _short(old),
					"new": _short(new),
				}
			)

	for key, text in (("added", _("row added")), ("removed", _("row removed"))):
		for table_field, _row in data.get(key) or []:
			lines.append({"label": _label(meta, table_field), "old": "", "new": text, "note": 1})

	if not action and lines:
		action = "edited"
	return action, lines


def _label(meta, fieldname) -> str:
	df = meta.get_field(fieldname) if meta else None
	return _(df.label) if df and df.label else fieldname


def _child_meta(meta, table_field):
	df = meta.get_field(table_field)
	return frappe.get_meta(df.options) if df and df.options else None


def _short(value) -> str:
	text = cstr(value)
	return text if len(text) <= MAX_VALUE_CHARS else text[: MAX_VALUE_CHARS - 1] + "…"


def _resolve_current_state(activity) -> None:
	"""For documents known only from Version rows: do they still exist, may the
	running user see them, and what is their status now?

	Not permitted -> dropped. Gone -> kept, linked to its Deleted Document copy
	when there is one, because "edited, then someone deleted it" is exactly what
	an auditor wants to see.
	"""
	pending = {}
	for (doctype, name), entry in activity.entries.items():
		if entry["exists"] is None:
			pending.setdefault(doctype, []).append(name)

	for doctype, names in pending.items():
		name_filter = {"name": ["in", names]}
		permitted = {
			row.name: row.docstatus
			for row in frappe.get_list(doctype, filters=name_filter, fields=["name", "docstatus"], limit_page_length=0)
		}
		existing = set(frappe.get_all(doctype, filters=name_filter, pluck="name"))
		gone = [n for n in names if n not in existing]
		deleted_copy = {}
		if gone:
			for row in frappe.get_all(
				"Deleted Document",
				filters={"deleted_doctype": doctype, "deleted_name": ["in", gone]},
				fields=["name", "deleted_name"],
				order_by="creation asc",
			):
				deleted_copy[row.deleted_name] = row.name

		for name in names:
			entry = activity.entries[(doctype, name)]
			if name in permitted:
				entry.update(exists=True, docstatus=permitted[name])
			elif name in existing:
				del activity.entries[(doctype, name)]
			else:
				entry.update(exists=False, deleted_document=deleted_copy.get(name))


def _collect_deleted(user, window, doctypes, activity) -> None:
	"""Deletions by the user. The document is gone, so the running user's company
	restriction is checked against the company stored in the deleted copy."""
	if not doctypes:
		return
	allowed_companies = {p.get("doc") for p in get_user_permissions(frappe.session.user).get("Company", [])}
	rows = frappe.get_all(
		"Deleted Document",
		filters={"owner": user, "creation": ["between", window], "deleted_doctype": ["in", doctypes]},
		fields=["name", "deleted_doctype", "deleted_name", "creation"] + (["data"] if allowed_companies else []),
		order_by="creation asc",
	)
	for row in rows:
		if allowed_companies and _deleted_company(row) not in allowed_companies | {None}:
			continue
		activity.mark(
			row.deleted_doctype,
			f"deleted::{row.name}",
			"deleted",
			row.creation,
			exists=False,
			deleted_document=row.name,
			display_name=row.deleted_name,
		)


def _deleted_company(row):
	"""Company of a deleted document, or None when it has none / is unreadable."""
	try:
		return json.loads(row.data or "{}").get("company")
	except ValueError:
		return None


# ----------------------------------------------------------------- output


def _is_draft(entry) -> bool:
	"""Entered in the range and still unsubmitted now (submittable types only)."""
	return bool(
		entry.get("exists")
		and entry.get("docstatus") == 0
		and entry["actions"] & {"created", "amended"}
		and frappe.get_meta(entry["doctype"]).is_submittable
	)


def _status(entry) -> str:
	if not entry.get("exists"):
		return "Deleted"
	if not frappe.get_meta(entry["doctype"]).is_submittable:
		return ""
	return DOCSTATUS_LABEL.get(entry.get("docstatus"), "")


def _rows(activity) -> list:
	by_doctype = {}
	for entry in activity.entries.values():
		by_doctype.setdefault(entry["doctype"], []).append(entry)

	rows = []
	# busiest document type first, then alphabetical for a stable order
	for doctype, entries in sorted(by_doctype.items(), key=lambda kv: (-len(kv[1]), kv[0])):
		parent = {"indent": 0, "label": doctype, "document_type": doctype, "total": len(entries)}
		for action in ACTIONS:
			parent[action] = sum(1 for e in entries if action in e["actions"])
		parent["draft"] = sum(1 for e in entries if _is_draft(e))
		rows.append(parent)

		for entry in sorted(entries, key=lambda e: cstr(e["first"] or "")):
			child = {
				"indent": 1,
				"label": entry.get("display_name") or entry["name"],
				"document_type": doctype,
				"document_name": entry["name"],
				"exists": 1 if entry.get("exists") else 0,
				"deleted_document": entry.get("deleted_document"),
				"first_activity": entry["first"],
				"status": _status(entry),
				"changes": entry["changes"],
				"more_changes": entry["more_changes"],
				"draft": 1 if _is_draft(entry) else None,
			}
			for action in ACTIONS:
				child[action] = 1 if action in entry["actions"] else None
			rows.append(child)
	return rows


def _summary(activity) -> list:
	entries = list(activity.entries.values())
	cards = [{"label": _("Documents"), "value": len(entries), "datatype": "Int", "indicator": "Blue"}]
	indicator = {"cancelled": "Red", "deleted": "Red", "amended": "Orange"}
	for action in ACTIONS:
		cards.append(
			{
				"label": _(action.title()),
				"value": sum(1 for e in entries if action in e["actions"]),
				"datatype": "Int",
				"indicator": indicator.get(action, "Green"),
			}
		)
	cards.append(
		{
			"label": _("Still Draft"),
			"value": sum(1 for e in entries if _is_draft(e)),
			"datatype": "Int",
			"indicator": "Orange",
		}
	)
	return cards


def _columns() -> list:
	columns = [
		{"label": _("Document Type / Document"), "fieldname": "label", "fieldtype": "Data", "width": 300},
		{"label": _("All"), "fieldname": "total", "fieldtype": "Int", "width": 80},
	]
	columns += [
		{"label": _(action.title()), "fieldname": action, "fieldtype": "Int", "width": 100} for action in ACTIONS
	]
	columns += [
		{"label": _("Still Draft"), "fieldname": "draft", "fieldtype": "Int", "width": 100},
		{"label": _("First Activity"), "fieldname": "first_activity", "fieldtype": "Datetime", "width": 170},
		{"label": _("Status Now"), "fieldname": "status", "fieldtype": "Data", "width": 110},
	]
	return columns


@frappe.whitelist()
def get_tracked_doctypes(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None):
	"""Feed the Document Type MultiSelect filter with the configured doctype list."""
	tracked = _tracked_doctypes()
	if txt:
		txt_lower = txt.lower()
		tracked = [d for d in tracked if txt_lower in d.lower()]
	return [{"value": d, "description": d} for d in tracked]
