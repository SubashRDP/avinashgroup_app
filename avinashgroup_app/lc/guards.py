"""LC guards — stop a Purchase Receipt / Invoice or an LC's Journal Entry being
cancelled under a Letter of Credit.

A settlement entry references the shipment's Purchase Invoice; cancelling the
invoice would leave the LC settled against nothing. A Purchase Receipt linked to
a shipment is what the LC's Landed Cost Voucher loads its charges onto. And
cancelling one of the LC's own Journal Entries from the JE form would leave the
LC's position and its books disagreeing. All three are refused here; the LC's
Undo Last Step is the way to unwind (it sets INTERNAL_CANCEL_FLAG).

Validation hooks: these throw, by design. Called from hooks.py doc_events
(before_cancel on Purchase Invoice, Purchase Receipt and Journal Entry).
"""

import frappe
from frappe import _

from avinashgroup_app.lc.accounting import INTERNAL_CANCEL_FLAG


def block_purchase_cancel(doc, method=None):
	if not frappe.db.table_exists("LC Shipment"):
		return
	field = "purchase_receipt" if doc.doctype == "Purchase Receipt" else "purchase_invoice"
	linked = frappe.db.sql(
		f"""select l.name, s.shipment_no from `tabLC Shipment` s
		join `tabLetter of Credit` l on l.name = s.parent and s.parenttype = 'Letter of Credit'
		where s.{field} = %s and l.docstatus = 1""",
		doc.name,
	)
	if linked:
		frappe.throw(
			_("{0} is linked to shipment {1} of Letter of Credit {2}. Undo that link on the LC first.").format(
				doc.name, linked[0][1], linked[0][0]),
			title=_("Linked to an LC"),
		)


def block_je_cancel(doc, method=None):
	if doc.get("letter_of_credit") and not frappe.flags.get(INTERNAL_CANCEL_FLAG):
		frappe.throw(
			_("This entry belongs to Letter of Credit {0}. Use Undo Last Step on the LC.").format(doc.letter_of_credit),
			title=_("Posted by an LC"),
		)
