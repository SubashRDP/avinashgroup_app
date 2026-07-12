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

	escalated = (
		action == "Save"
		and parsed.get("doctype") == "Sales Invoice"
		and cint(parsed.get("docstatus") or 0) == 0
		and frappe.has_permission("Sales Invoice", "submit")
		and not _has_active_workflow("Sales Invoice")
	)
	if escalated:
		action = "Submit"

	ret = _core_savedocs(doc, action)

	if escalated:
		# On insert+submit the in-memory doc keeps status "Draft":
		# SalesInvoice.set_status early-returns while the doc is new, and the
		# real status ("Unpaid", ...) is written by update_voucher_outstanding
		# onto a *reloaded* copy the response never sees. Refresh it so the
		# desk doesn't render a submitted invoice with a Draft badge.
		#
		# Returns get no such repair: their outstanding is tracked on
		# return_against, so update_voucher_outstanding never revisits the
		# return itself and its DB status would stay "Draft" forever.
		# Recompute on a reloaded copy (no longer "new") when that happens.
		for d in frappe.response.get("docs") or []:
			if d.get("doctype") == "Sales Invoice" and d.get("name"):
				status = frappe.db.get_value("Sales Invoice", d["name"], "status")
				if status == "Draft":
					si = frappe.get_doc("Sales Invoice", d["name"])
					si.set_status(update=True, update_modified=False)
					status = si.status
				d["status"] = status

	return ret
