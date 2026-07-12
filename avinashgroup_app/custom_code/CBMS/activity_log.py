"""Append-only activity trail for the CBMS integration (CBMS Sync Log).

One row per event in a bill's journey to IRD: Queued (created on invoice
submit), Synced / Failed (each actual HTTP attempt, with the response code),
Held (a return waiting because its original bill is not Synced yet).

log_cbms_activity never raises: a broken audit trail must not break invoice
submission or the background sender. It also never commits — callers own the
transaction (send_* functions commit right after via _record_result)."""

import frappe


def log_cbms_activity(
	cbms_doc,
	operation,
	details="",
	response_code="",
	triggered_from="Submit",
):
	"""Insert one CBMS Sync Log row from a CBMS Bill / CBMS Bill Return doc."""
	try:
		is_return = cbms_doc.doctype == "CBMS Bill Return"
		frappe.get_doc(
			{
				"doctype": "CBMS Sync Log",
				"sales_invoice": cbms_doc.sales_invoice,
				"invoice_number": (
					cbms_doc.credit_note_number if is_return else cbms_doc.invoice_number
				),
				"company": cbms_doc.company,
				"direction": "Bill Return" if is_return else "Bill",
				"cbms_ref_doctype": cbms_doc.doctype,
				"cbms_ref": cbms_doc.name,
				"triggered_from": triggered_from,
				"operation": operation,
				"response_code": response_code or "",
				"details": (details or "")[:500],
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title=f"CBMS Sync Log write failed: {getattr(cbms_doc, 'name', '?')}",
			message=frappe.get_traceback(),
		)
