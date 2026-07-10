"""Sales Invoice: Save and Submit are one atomic action.

IRD invoices must never leave a failed draft behind: an invoice number is
consumed the moment a draft is saved, so a draft whose submit later fails
would leave a gap in the IRD numbering sequence. Instead of Save → Submit as
two separate requests, the desk form's Save action on a Sales Invoice draft
is escalated to Submit, making insert + submit ONE request and therefore ONE
database transaction — if anything in the submit path throws, Frappe rolls
the whole transaction back and neither the draft nor its invoice number (the
tabSeries increment happens in the same transaction) survives.

The escalation deliberately does NOT apply when:
  - the user lacks submit permission (they can still save plain drafts), or
  - an active Workflow governs Sales Invoice (approval flows need drafts —
    doc.submit() would be blocked by validate_workflow anyway).

Only the desk endpoint (frappe.desk.form.save.savedocs) is wrapped; documents
created programmatically or via Data Import are untouched.
"""

import json

import frappe
from frappe.desk.form.save import savedocs as _core_savedocs
from frappe.utils import cint


def _has_active_workflow(doctype):
	return bool(frappe.db.exists("Workflow", {"document_type": doctype, "is_active": 1}))


@frappe.whitelist(methods=["POST", "PUT"])
def savedocs(doc, action):
	parsed = json.loads(doc) if isinstance(doc, str) else doc

	if (
		action == "Save"
		and parsed.get("doctype") == "Sales Invoice"
		and cint(parsed.get("docstatus") or 0) == 0
		and frappe.has_permission("Sales Invoice", "submit")
		and not _has_active_workflow("Sales Invoice")
	):
		action = "Submit"

	return _core_savedocs(doc, action)
