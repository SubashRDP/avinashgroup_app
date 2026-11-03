"""Keep `custom_invoice_miti` (BS) in lockstep with `posting_date` (AD).

Both fields are read-only on the desk form (public/js/sales_invoice.js), so the
BS miti can no longer be typed in by hand — it is derived here on every save
from the posting date, which makes it impossible for the two to disagree on an
invoice. Existing invoices keep whatever they have until they are saved again.
"""

import frappe

from avinashgroup_app.custom_code.CBMS.utils import bs_date_str


def set_invoice_miti(doc, method=None):
	"""Require today's posting date, then set the BS miti from it.

	The today-only rule is skipped during a Data Import (frappe.flags.in_import,
	set by frappe's Importer, which fast_import also runs through), because
	imports carry historical invoices. A failed miti conversion is only logged,
	never thrown."""
	if not doc.get("posting_date"):
		return

	if not frappe.flags.in_import:
		posting = frappe.utils.getdate(doc.posting_date)
		current = frappe.utils.getdate(frappe.utils.today())
		if posting > current:
			frappe.throw("Posting Date cannot be a future date. It must be today's date.")
		if posting < current:
			frappe.throw("Posting Date cannot be backdated. It must be today's date.")

	try:
		doc.custom_invoice_miti = bs_date_str(doc.posting_date)
	except Exception:
		frappe.log_error(
			title="Sales Invoice: BS miti conversion failed",
			message=f"{doc.name or '(new)'} posting_date={doc.posting_date}\n{frappe.get_traceback()}",
		)
