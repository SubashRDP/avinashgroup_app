"""Sales Invoice: Save and Submit are one atomic action.

IRD invoices must never leave a failed draft behind: an invoice number is
consumed the moment a draft is saved, so a draft whose submit later fails
would leave a gap in the IRD numbering sequence. The desk form's Save action
on a Sales Invoice draft therefore also submits it, inside ONE request and
therefore ONE database transaction — if anything in the submit path throws,
Frappe rolls the whole transaction back and neither the draft nor its invoice
number (the tabSeries increment happens in the same transaction) survives.

HOW, and why it matters. The draft is saved through core with the action
UNCHANGED ("Save"), and the saved document is then submitted as a SECOND
document action. Two actions, one transaction. The obvious alternative —
rewriting the action to "Submit" so the row is inserted with docstatus already
1 — is what this module used to do, and it silently broke every `before_save`
hook on Sales Invoice:

    frappe.desk.form.save.savedocs sets doc.docstatus BEFORE inserting, so a
    brand-new doc arrives already submitted. Document.check_docstatus_transition
    (frappe/model/document.py) then picks _action = "submit", and
    run_before_save_methods runs `before_submit` INSTEAD of `before_save` —
    the two are mutually exclusive branches. Every before_save doc_event
    registered for Sales Invoice (audit_file_manager.before_save, and the
    wildcard "*" numbering hook) was skipped, with nothing to signal it.

Saving first avoids that entirely: the insert sees docstatus 0 and runs
`before_save`; the submit runs on a document that is no longer new and runs
`before_submit`. Both fire, in their normal order, with no compensation layer
to keep in sync when a future hook is added. This is the same shape sarathi_app
uses for the documents it creates and submits in one go (insert() then
submit()).

The escalation deliberately does NOT apply when:
  - the user lacks submit permission (they can still save plain drafts), or
  - an active Workflow governs Sales Invoice (approval flows need drafts —
    doc.submit() would be blocked by validate_workflow anyway).

Only the desk endpoint (frappe.desk.form.save.savedocs) is wrapped; documents
created programmatically or via Data Import are untouched.

Cost, so it is not a surprise: `validate` runs on BOTH passes, so the VAT/excise
pipeline executes twice per desk-created invoice. It is deterministic and
recomputes from the item rows, so the second pass reaches the same result;
apply_document_no is idempotent per save and, on the second pass, keeps the
number it already drew (the doc is no longer new, and both duplicate checks
exclude the document itself by name).
"""

import json

import frappe
from frappe.desk.form.load import run_onload
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

	# Action is passed through unchanged — core saves a DRAFT, running the full
	# before_validate → validate → before_save chain.
	ret = _core_savedocs(doc, action)

	if not escalated:
		return ret

	# Second action, same request and same transaction: submit what was just
	# saved. Deliberately unguarded — a failure here must propagate so Frappe
	# rolls back the insert and the tabSeries increment with it.
	docs = frappe.response.get("docs") or []
	for idx, d in enumerate(docs):
		if d.get("doctype") != "Sales Invoice" or not d.get("name"):
			continue
		if cint(d.get("docstatus")):
			continue

		si = frappe.get_doc("Sales Invoice", d["name"])
		si.submit()

		# The real status ("Unpaid", ...) is written by update_voucher_outstanding
		# onto a reloaded copy this object never sees, so read the committed row
		# back. Returns are never revisited by it at all — their outstanding is
		# tracked on return_against — so recompute if the row still says Draft.
		si.reload()
		if si.status == "Draft":
			si.set_status(update=True, update_modified=False)

		run_onload(si)
		si.apply_fieldlevel_read_permissions()

		updated = si.as_dict()
		# The desk maps its local ("new-sales-invoice-N") doc onto the real name
		# via localname; core set it on the draft snapshot, so carry it across.
		if d.get("localname"):
			updated["localname"] = d["localname"]
		docs[idx] = updated

	return ret
