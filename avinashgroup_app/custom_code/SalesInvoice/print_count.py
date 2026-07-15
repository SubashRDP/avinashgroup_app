# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""IRD print-copy tracking for Sales Invoice.

The IRD electronic-billing rules require the software to count how many times
an invoice is printed and to label every reprint as a copy of the original.
`invoice_copy_titles` is the single source of truth for the series — the NGI
Jinja template and the ESC/P builder both call it:

	1st print  -> INVOICE + TAX INVOICE   (one print event, two sheets)
	2nd print  -> COPY OF ORIGINAL
	3rd print  -> COPY OF ORIGINAL 1
	nth print  -> COPY OF ORIGINAL (n - 2)

	Returns print a single CREDIT MEMO instead of the invoice pair; their
	reprints follow the same copy series suffixed "(CREDIT MEMO)".

The counter increments only on an *actual* print — the browser Print button
(printview?trigger_print=1), a PDF download, or raw/server printing. Rendering
the preview in the Print view does NOT consume a copy number; the preview shows
the title the NEXT print will get.

Each actual print also inserts a Sales Invoice Print Log row (who, when, which
copy) — the per-event trail behind the Invoice Activity Report. Logging must
never block the print: a log failure goes to the Error Log and the print
proceeds.
"""

import frappe
from frappe.utils import cint

# /api/method endpoints that produce a physical/file output of the document.
PRINT_OUTPUT_CMDS = {
	"frappe.utils.print_format.download_pdf",
	"frappe.utils.print_format.download_multi_pdf",
	"frappe.utils.print_format.print_by_server",
	"frappe.utils.weasyprint.download_pdf",
	"frappe.www.printview.get_rendered_raw_commands",
}


def invoice_copy_titles(doc, pair=True) -> list[str]:
	"""Titles of the sheets this print event produces, in print order.

	Driven by doc.custom_print_count, which before_print has already set to the
	number this render represents (preview shows the upcoming print, so a
	never-printed invoice previews the INVOICE + TAX INVOICE pair).

	pair=True is the Nepal Gas convention: the first print event produces the
	INVOICE + TAX INVOICE sheet pair, and every reprint is a copy.

	pair=False (Grihalaxmi) prints ONE sheet per event and spreads the pair
	over the first two prints instead:

		1st -> INVOICE, 2nd -> TAX INVOICE, 3rd -> COPY OF ORIGINAL,
		4th -> COPY OF ORIGINAL 2, 5th -> COPY OF ORIGINAL 3, ...
	"""
	n = cint(doc.get("custom_print_count")) or 1
	if cint(doc.get("is_return")):
		if n <= 1:
			return ["CREDIT MEMO"]
		return [_copy_of_original(n) + " (CREDIT MEMO)"]
	if pair:
		if n <= 1:
			return ["INVOICE", "TAX INVOICE"]
		return [_copy_of_original(n)]
	if n == 1:
		return ["INVOICE"]
	if n == 2:
		return ["TAX INVOICE"]
	return ["COPY OF ORIGINAL" if n == 3 else f"COPY OF ORIGINAL {n - 2}"]


def _copy_of_original(n: int) -> str:
	return "COPY OF ORIGINAL" if n == 2 else f"COPY OF ORIGINAL {n - 2}"


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
		_log_print(doc)
		_update_print_count_doc(doc)
		# printview / download_pdf are GET requests — commit explicitly so the
		# increment survives the request-end rollback.
		frappe.db.commit()
	else:
		doc.custom_print_count = stored + 1


def _update_print_count_doc(doc):
	"""Mirror the invoice's current print count into Sales Invoice Print Count.

	One row per invoice (autonamed by sales_invoice), upserted on every actual
	print so the row always holds the latest count and branch. Like _log_print,
	a failure here must never block the print.
	"""
	try:
		values = {
			"branch_name": doc.get("custom_branch_name"),
			"print_count": cint(doc.custom_print_count),
		}
		if frappe.db.exists("Sales Invoice Print Count", doc.name):
			frappe.db.set_value("Sales Invoice Print Count", doc.name, values)
		else:
			frappe.get_doc(
				{
					"doctype": "Sales Invoice Print Count",
					"sales_invoice": doc.name,
					**values,
				}
			).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title=f"Print count doc update failed for Sales Invoice {doc.name}",
			message=frappe.get_traceback(),
		)


def _log_print(doc):
	try:
		frappe.get_doc(
			{
				"doctype": "Sales Invoice Print Log",
				"sales_invoice": doc.name,
				"branch_name": doc.get("custom_branch_name"),
				"company": doc.company,
				"copy_number": cint(doc.custom_print_count),
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title=f"Print log failed for Sales Invoice {doc.name}",
			message=frappe.get_traceback(),
		)
