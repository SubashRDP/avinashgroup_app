# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""IRD print-copy tracking for Sales Invoice.

The IRD electronic-billing rules require the software to count how many times
an invoice is printed and to label every reprint as a copy of the original:

	1st print  -> Tax Invoice
	2nd print  -> Copy of Original
	3rd print  -> Copy of Original 2
	nth print  -> Copy of Original (n - 1)

The counter increments only on an *actual* print — the browser Print button
(printview?trigger_print=1), a PDF download, or raw/server printing. Rendering
the preview in the Print view does NOT consume a copy number; the preview shows
the title the NEXT print will get.
"""

import frappe
from frappe.utils import cint

# /api/method endpoints that produce a physical/file output of the document.
PRINT_OUTPUT_CMDS = {
	"frappe.utils.print_format.download_pdf",
	"frappe.utils.print_format.download_multi_pdf",
	"frappe.utils.print_format.print_by_server",
	"frappe.utils.weasyprint.download_pdf",
}


def is_actual_print() -> bool:
	form_dict = getattr(frappe.local, "form_dict", None) or {}
	if cint(form_dict.get("trigger_print")):
		return True
	return (form_dict.get("cmd") or "") in PRINT_OUTPUT_CMDS


def before_print(doc, method=None, *args, **kwargs):
	"""Set doc.custom_print_count to the number this render represents.

	Submitted invoice + real print: increment the stored counter (atomic) and
	stamp the new value on the doc. Anything else (preview, draft, cancelled):
	stamp stored + 1 in memory only, so the render shows the upcoming title
	without consuming it.
	"""
	stored = cint(
		frappe.db.get_value("Sales Invoice", doc.name, "custom_print_count")
		if doc.name and not doc.get("__islocal")
		else 0
	)

	if doc.docstatus == 1 and is_actual_print():
		frappe.db.sql(
			"UPDATE `tabSales Invoice` SET custom_print_count = custom_print_count + 1 WHERE name = %s",
			doc.name,
		)
		doc.custom_print_count = cint(
			frappe.db.get_value("Sales Invoice", doc.name, "custom_print_count")
		)
		# printview / download_pdf are GET requests — commit explicitly so the
		# increment survives the request-end rollback.
		frappe.db.commit()
	else:
		doc.custom_print_count = stored + 1
