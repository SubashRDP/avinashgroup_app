"""PDC guards — stop an invoice or a cheque's Journal Entry being cancelled under it.

Cancelling a Sales / Purchase Invoice that an active PDC Cheque settles would
leave the cheque's holding entry pointing at a cancelled invoice (ERPNext
unlinks it, and the next bounce has nothing to re-open). Cancelling one of a
cheque's Journal Entries from the JE form would leave the cheque's status and
its books disagreeing. Both are refused here; the cheque's own Cancel / Undo
Last Step are the way to unwind (they set INTERNAL_CANCEL_FLAG).

Validation hooks: these throw, by design.
"""

import frappe
from frappe import _

from avinashgroup_app.pdc.accounting import INTERNAL_CANCEL_FLAG
from avinashgroup_app.pdc.lifecycle import ACTIVE_STATUSES


def block_invoice_cancel(doc, method=None):
	if not frappe.db.table_exists("PDC Cheque Reference"):
		return
	cheques = frappe.db.sql(
		"""select distinct c.name from `tabPDC Cheque` c
		join `tabPDC Cheque Reference` r on r.parent = c.name and r.parenttype = 'PDC Cheque'
		where r.reference_doctype = %s and r.reference_name = %s
		and c.docstatus = 1 and c.status in %s""",
		(doc.doctype, doc.name, ACTIVE_STATUSES),
		pluck=True,
	)
	if cheques:
		frappe.throw(
			_("{0} is settled by post-dated cheque {1}. Return or cancel the cheque first.").format(
				doc.name, ", ".join(cheques)
			),
			title=_("Cheque attached"),
		)


def block_je_cancel(doc, method=None):
	if doc.get("pdc_cheque") and not frappe.flags.get(INTERNAL_CANCEL_FLAG):
		frappe.throw(
			_("This entry belongs to PDC Cheque {0}. Use Undo Last Step or Cancel on the cheque.").format(
				doc.pdc_cheque
			),
			title=_("Posted by a cheque"),
		)
