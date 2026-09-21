"""Journals that HRMS writes itself need this app's JV Type and Document No.

Every Journal Entry here carries a JV Type (`custom_p_type`) and a Document No
(`custom_document_no`), both mandatory. On the desk the accountant picks the
type, and for Journal Entry and Cash Entry types types the number too — on every
company those two series are numbered by hand; only Bank Entry numbers itself.

HRMS writes two journals with nobody at the form: the payroll accrual when the
salary slips are submitted, and the payout of an Employee Advance. Neither
knows these fields exist, so a payroll run got as far as 87 submitted slips,
failed on the journal, and rolled the whole month back.

So a journal that points at a Payroll Entry or an Employee Advance takes, when
it has none:

  - the JV Type matching its own voucher type (Journal Entry, Bank Entry or
    Cash Entry — all three are JV Types here);
  - for a hand-numbered series, the next number in that same series (company +
    JV Type + fiscal year), marked manual so the normal duplicate check still
    guards it. An auto-numbered series (Bank Entry) is left to draw its own.

Anything an accountant typed is left alone, and their own journals are not
touched at all.
"""

import frappe

HR_REFERENCES = ("Payroll Entry", "Employee Advance")


def default_jv_type(doc, method=None):
	if not any(row.reference_type in HR_REFERENCES for row in doc.get("accounts") or []):
		return

	if not doc.get("custom_p_type"):
		jv_type = doc.voucher_type if frappe.db.exists("JV Type", doc.voucher_type) else "Journal Entry"
		if not frappe.db.exists("JV Type", jv_type):
			return
		doc.custom_p_type = jv_type

	if doc.get("custom_document_no"):
		return

	from avinashgroup_app.custom_code.Override import naming_series

	if naming_series._docno_scope(doc):
		return  # auto-numbered series: the save draws the number itself

	scope = naming_series._docno_scope(doc, ignore_eligibility=True)
	if not scope:
		return
	doc.custom_document_no = naming_series._draw_next_document_no(doc, scope)
	if doc.meta.has_field("custom_document_no_manual"):
		doc.custom_document_no_manual = 1
