# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Document Audit Trail page — one document, laid out like its form, with history.

Frappe already stores every tracked change as a Version row, but the only places
to read it are the form's comment timeline (a wall of text) and the stock Audit
Trail tool, which compares cancel-and-amend chains only and never reads Version.
An auditor asking "what did the rate on this invoice use to be?" had no screen
that answers it. This module feeds /app/document-audit-trail, which draws the
document in its own form layout and hangs each field's earlier values under it.

Called only by the page script (document_audit_trail.js) and by the "Audit
Trail" form menu entry (public/js/document_audit_trail_menu.js). User-facing
notes and the gotchas are in docs/document-audit-trail.md.

Deliberately narrow:
  * Read-only. It never writes, and never reconstructs values that Version did
    not record. Changes made through db_set / raw SQL, and anything before
    track_changes was switched on for the doctype, simply are not there.
  * It does not decide WHICH doctypes are tracked — that is
    patches/enable_track_changes_audited_doctypes.py and AuditBase.doctypes.
  * Frappe does not diff Text Editor / Code / HTML Editor / Markdown fields
    (version.get_diff blacklists them), so those never show history here.
"""

import json

import frappe
from frappe import _
from frappe.model import get_permitted_fields

from avinashgroup_app.avinash_group_app.report.invoice_activity_report.invoice_activity_report import (
	INCIDENTAL_FIELDS,
)

# Same roles as the Page record (document_audit_trail.json). Repeated here
# because a whitelisted method is reachable without opening the page.
ALLOWED_ROLES = ("Auditor", "System Manager", "Accounts Manager")

# The report's side-effect list, minus the two fields that ARE the story on a
# single document's page: when it was submitted / cancelled and how its status
# moved. The rest (in_words, print count, ...) are recalculation noise.
NOISE_FIELDS = frozenset(INCIDENTAL_FIELDS) - {"docstatus", "status"}

# Guard against a pathological document; the busiest invoices on the demo site
# have a few dozen Version rows. Newest rows are kept when the cap is hit.
MAX_VERSIONS = 1000

DOCSTATUS_STEP = {("0", "1"): "Submitted", ("1", "2"): "Cancelled", ("0", "2"): "Cancelled"}


@frappe.whitelist()
def get_document_history(doctype: str, name: str) -> dict:
	"""Return the current document plus its Version history, grouped for display.

	Raises frappe.PermissionError when the user lacks an allowed role or read
	access to this document (so company User Permissions apply as on the form),
	and frappe.DoesNotExistError when the document is gone.

	Returns a dict with:
	  doc            current values, field-level read permissions applied
	  tracked        whether the doctype has track_changes on
	  steps          every recorded step, oldest first (for the bottom timeline)
	  field_history  {fieldname: [{old, new, user, when}]} newest first
	  row_history    {table_field: {row_name: [{fieldname, old, new, user, when}]}}
	  rows_added / rows_removed  {table_field: [{row, user, when}]}
	  prints         Sales Invoice Print Log rows (Sales Invoice only)
	  truncated      True when more than MAX_VERSIONS rows existed
	"""
	frappe.only_for(ALLOWED_ROLES)
	meta = frappe.get_meta(doctype)
	if meta.istable or meta.issingle:
		frappe.throw(_("Pick a normal document type, not a child table or settings page."))

	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	doc.apply_fieldlevel_read_permissions()

	readable = _readable_fields(doctype, meta)
	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": doctype, "docname": name},
		fields=["name", "owner", "creation", "data"],
		order_by="creation desc",
		limit=MAX_VERSIONS + 1,
	)
	truncated = len(versions) > MAX_VERSIONS
	versions = list(reversed(versions[:MAX_VERSIONS]))

	out = frappe._dict(
		doc=doc.as_dict(),
		tracked=bool(meta.track_changes),
		steps=[_created_step(doc)],
		field_history={},
		row_history={},
		rows_added={},
		rows_removed={},
		prints=_print_log(doctype, name),
		truncated=truncated,
	)
	for version in versions:
		_absorb_version(version, readable, out)

	for history in out.field_history.values():
		history.reverse()
	for rows in out.row_history.values():
		for history in rows.values():
			history.reverse()
	return out


def _readable_fields(doctype: str, meta) -> dict:
	"""{None: parent fieldnames, table_field: child fieldnames} the user may read."""
	readable = {None: set(get_permitted_fields(doctype))}
	for df in meta.get_table_fields():
		readable[df.fieldname] = set(get_permitted_fields(df.options, parenttype=doctype))
	return readable


def _created_step(doc) -> dict:
	"""The first timeline entry. Prefers the app's audit pair (the clerk who
	entered it) over owner/creation, which name the API user on imported rows."""
	return {
		"kind": "Created",
		"user": doc.get("custom_created_by") or doc.owner,
		"when": doc.get("custom_created_on") or doc.creation,
		"changed": [],
		"rows": [],
	}


def _absorb_version(version, readable: dict, out) -> None:
	"""Fold one Version row into the grouped maps and the timeline."""
	try:
		data = json.loads(version.data or "{}")
	except ValueError:
		frappe.log_error(
			title="Document Audit Trail: unreadable Version",
			message=f"Version {version.name} has data that is not valid JSON; skipped.",
		)
		return

	# audit_user is set when a background job acted for a person; otherwise the
	# Version owner is whoever's session saved the document.
	user = data.get("audit_user") or version.owner
	when = version.creation
	step = {"kind": "Edited", "user": user, "when": when, "changed": [], "rows": []}
	if data.get("impersonated_by"):
		step["impersonated_by"] = data["impersonated_by"]

	for fieldname, old, new in data.get("changed") or []:
		if fieldname == "docstatus":
			# the step's kind already says it; "docstatus 0 -> 1" adds nothing
			step["kind"] = DOCSTATUS_STEP.get((str(old), str(new)), step["kind"])
			continue
		if fieldname in NOISE_FIELDS or fieldname not in readable[None] or _same_blank(old, new):
			continue
		entry = {"old": old, "new": new, "user": user, "when": when}
		out.field_history.setdefault(fieldname, []).append(entry)
		step["changed"].append({"fieldname": fieldname, "old": old, "new": new})

	for table_field, _idx, row_name, changes in data.get("row_changed") or []:
		allowed = readable.get(table_field)
		if allowed is None:
			continue
		kept = [c for c in changes if c[0] in allowed and not _same_blank(c[1], c[2])]
		if not kept:
			continue
		history = out.row_history.setdefault(table_field, {}).setdefault(row_name, [])
		for fieldname, old, new in kept:
			history.append({"fieldname": fieldname, "old": old, "new": new, "user": user, "when": when})
		step["rows"].append({"table": table_field, "action": "changed", "row_name": row_name, "count": len(kept)})

	for key, target, action in (("added", out.rows_added, "added"), ("removed", out.rows_removed, "removed")):
		for table_field, row in data.get(key) or []:
			allowed = readable.get(table_field)
			if allowed is None:
				continue
			row = {k: v for k, v in row.items() if k in allowed or k in ("name", "idx")}
			target.setdefault(table_field, []).append({"row": row, "user": user, "when": when})
			step["rows"].append({"table": table_field, "action": action, "row_name": row.get("name")})

	if step["changed"] or step["rows"] or step["kind"] != "Edited":
		out.steps.append(step)


def _same_blank(old, new) -> bool:
	"""True for a 'change' between two blanks (0.0 -> None, None -> "").

	Submitting an invoice writes dozens of these: a Float saved as 0.0 is read
	back as None on the next load and Version records the pair as a change.
	Nothing a person would call an edit happened.
	"""
	return old in (None, "", 0) and new in (None, "", 0)


def _print_log(doctype: str, name: str) -> list:
	"""Physical prints, which Version never records. Sales Invoice only — it is
	the one doctype with a print log (custom_code/SalesInvoice/print_count.py)."""
	if doctype != "Sales Invoice":
		return []
	return frappe.get_all(
		"Sales Invoice Print Log",
		filters={"sales_invoice": name},
		fields=["creation", "printed_by", "owner", "copy_number"],
		order_by="creation asc",
	)
