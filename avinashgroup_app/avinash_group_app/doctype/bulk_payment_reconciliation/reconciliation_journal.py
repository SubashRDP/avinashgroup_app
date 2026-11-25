"""JV Type and Document No for the Journal Entries ERPNext makes while reconciling.

When reconciliation uses a return (credit note) to pay another invoice, ERPNext
writes a small Journal Entry that links the two (payment_reconciliation.
reconcile_dr_cr_note): voucher_type "Credit Note" (or "Debit Note" for a
supplier), is_system_generated set, JV Type and Document No left empty.

With both empty, the app's numbering gives every such entry the same Voucher No
("<company abbr>-<fiscal year>"), so only the first one per company per year can
be saved and every later return match fails as a duplicate.

`set_jv_type` (Journal Entry before_insert) gives these entries the JV Type whose
code is JV and the next Document No in that series, through the same helper the
payroll and asset journals use (payroll.hr_journal.fill_system_journal).
Exchange Gain/Loss entries are left alone on purpose.
"""

import frappe

from avinashgroup_app.payroll.hr_journal import fill_system_journal

RECONCILIATION_VOUCHER_TYPES = ("Credit Note", "Debit Note")
JV_TYPE_CODE = "JV"


def is_reconciliation_entry(je) -> bool:
	return bool(je.get("is_system_generated")) and je.voucher_type in RECONCILIATION_VOUCHER_TYPES


def set_jv_type(doc, method=None):
	"""Journal Entry before_insert: JV Type "JV" and the next Document No."""
	if not is_reconciliation_entry(doc) or doc.get("custom_p_type"):
		return

	jv_type = jv_type_for_code(JV_TYPE_CODE, doc.company)
	if not jv_type:
		return
	doc.custom_p_type = jv_type
	fill_system_journal(doc)


def jv_type_for_code(code, company):
	"""The JV Type with this code: the company's own first, else one for all companies."""
	rows = frappe.get_all(
		"JV Type",
		filters={"jv_type_code": code},
		fields=["name", "company"],
		order_by="name",
	)
	for row in rows:
		if row.company == company:
			return row.name
	for row in rows:
		if not row.company:
			return row.name
	return None
