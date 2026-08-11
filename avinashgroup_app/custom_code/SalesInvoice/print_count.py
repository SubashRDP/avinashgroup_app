# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""IRD print-copy tracking for Sales Invoice.

The IRD electronic-billing rules require the software to count how many times
an invoice is printed and to label every reprint as a copy of the original.
`invoice_copy_titles` is the single source of truth for the series — the Jinja
templates and the ESC/P builders both call it.

Sheet-based series (pair=True — Nepal Gas / Grishma / Avinash dot-matrix):

	1st print -> TAX INVOICE + INVOICE   (one print event, TWO sheets)
	2nd print -> COPY OF INVOICE 1
	3rd print -> COPY OF INVOICE 2
	nth print -> COPY OF INVOICE (n - 1)

The counter counts SHEETS, so the two-sheet original pair advances the count
by 2 (the first print leaves the count at 2), and each later single-sheet copy
adds 1.

Single-sheet series (pair=False — Grihalaxmi A4/Half, Nepal Gas Half) follows
the SAME order as the dot-matrix pair, one sheet per print:

	1st -> TAX INVOICE, 2nd -> INVOICE, 3rd -> COPY OF INVOICE 1,
	4th -> COPY OF INVOICE 2, ...

No pre-printed roll carries a title, on any company's stationery, so every
sheet's title is typed by the format (2026-07-25 — the overlays used to skip
exactly "TAX INVOICE" on the assumption the roll said it).

Returns print a single "Sales Return" sheet on every print (no copy-of prefix,
however many times printed).

The counter increments only on an *actual* print — the browser Print button
(printview?trigger_print=1), a PDF download, or raw/server printing. Rendering
the preview in the Print view does NOT consume sheets; the preview shows the
titles the NEXT print will get.

Each actual print inserts one Sales Invoice Print Log row per sheet (who, when,
which sheet number) — the per-event trail behind the Invoice Activity Report.
Logging must never block the print: a failure goes to the Error Log and the
print proceeds.

"Who" is recorded twice on purpose: `owner` is the real user id, and
`printed_by` is the display name. The Materialized Report and the pre-Frappe
history backfilled from the old NGI billing software both need a name, and that
software's user names (ASHISH, NDILLI) are not Frappe users.
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

# Print formats that print ONE sheet per event (Grihalaxmi): the Tax Invoice /
# Invoice pair is spread across the first two prints instead of one two-sheet
# event. Everything else is a "pair" format (Nepal Gas / Grishma / Avinash).
SINGLE_SHEET_FORMATS = {
	"Grihalaxmi Invoice A4",
	"Grihalaxmi Invoice A4 Return",
	"Grihalaxmi Invoice Half A4",
	"Grihalaxmi Invoice Half A4 Return",
}


def _current_print_format() -> str:
	"""The print format of the in-flight request (download_pdf/printview use
	`format`, get_rendered_raw_commands uses `print_format`)."""
	fd = getattr(frappe.local, "form_dict", None) or {}
	return fd.get("format") or fd.get("print_format") or ""


def _titles_for(prev_sheets: int, pair: bool, is_return: bool) -> list[str]:
	"""Sheet titles for ONE print event, given the sheet count BEFORE it.

	Returns always print a single "Sales Return".

	pair=True: first print is the TAX INVOICE + INVOICE pair (two sheets),
	every later print a single COPY OF INVOICE N; the count is sheets:

		prev 0  -> [TAX INVOICE, INVOICE]   (count -> 2)
		prev 2  -> [COPY OF INVOICE 1]      (count -> 3)
		prev n  -> [COPY OF INVOICE n - 1]

	pair=False (Grihalaxmi, unchanged): one sheet per print, count == prints.
	"""
	if is_return:
		return ["Sales Return"]
	if pair:
		if prev_sheets <= 0:
			return ["TAX INVOICE", "INVOICE"]
		# after the 2-sheet pair prev is 2 -> COPY OF INVOICE 1; guard against
		# legacy counts of 1 (old event-based scheme) so we never show "0".
		return [f"COPY OF INVOICE {max(1, prev_sheets - 1)}"]
	# pair=False (single-sheet: Grihalaxmi A4/Half, Nepal Gas Half). Follows the
	# same order as the dot-matrix pair, spread one sheet per print:
	#   1st -> TAX INVOICE, 2nd -> INVOICE, 3rd -> COPY OF INVOICE 1, ...
	if prev_sheets == 0:
		return ["TAX INVOICE"]
	if prev_sheets == 1:
		return ["INVOICE"]
	return [f"COPY OF INVOICE {prev_sheets - 1}"]


def invoice_copy_titles(doc, pair=True) -> list[str]:
	"""Titles of the sheets this print event produces, in print order.

	before_print stamps doc.flags.print_prev_sheets with the sheet count BEFORE
	this event (previews fall back to the stored count, so a never-printed
	invoice previews the TAX INVOICE + INVOICE pair). The counter lives in the
	Sales Invoice Print Count doctype (one row per invoice), NOT on the invoice.

	`pair` is supplied by the caller (the format): the Grihalaxmi templates pass
	pair=False; the Nepal Gas / Grishma / Avinash builders use the default True.
	"""
	if "print_prev_sheets" in doc.flags:
		prev = cint(doc.flags.get("print_prev_sheets"))
	else:
		prev = _stored_count(doc.get("name"))
	return _titles_for(prev, pair, cint(doc.get("is_return")))


def is_actual_print() -> bool:
	form_dict = getattr(frappe.local, "form_dict", None) or {}
	if cint(form_dict.get("trigger_print")):
		return True
	return (form_dict.get("cmd") or "") in PRINT_OUTPUT_CMDS


def before_print(doc, method=None, *args, **kwargs):
	"""Stamp doc.flags.print_prev_sheets with the sheet count BEFORE this event.

	The counter lives in the Sales Invoice Print Count doctype (one row per
	invoice, autonamed by the invoice) — NOT on the Sales Invoice itself.

	Submitted invoice + real print: advance that counter by the number of
	sheets this event prints (the pair = 2, a copy = 1) and log one row per
	sheet. Anything else (preview, draft, cancelled): stamp the stored count in
	memory only, so the render shows the upcoming titles without consuming them.
	"""
	stored = _stored_count(doc.name) if doc.name and not doc.get("__islocal") else 0
	# titles for THIS event are computed from the sheets printed BEFORE it, so
	# the flag stays `stored` even after we advance the stored counter below.
	doc.flags.print_prev_sheets = stored

	if doc.docstatus == 1 and is_actual_print():
		pair = _current_print_format() not in SINGLE_SHEET_FORMATS
		titles = _titles_for(stored, pair, cint(doc.get("is_return")))
		_add_print_count_doc(doc, len(titles))
		_log_print(doc, stored, titles)
		# printview / download_pdf are GET requests — commit explicitly so the
		# increment survives the request-end rollback.
		frappe.db.commit()


def _stored_count(invoice_name) -> int:
	"""Current sheet count for an invoice, from Sales Invoice Print Count (0 if none).

	The doctype is autonamed by sales_invoice, so its name IS the invoice name.
	"""
	if not invoice_name:
		return 0
	return cint(
		frappe.db.get_value("Sales Invoice Print Count", invoice_name, "print_count")
	)


def _add_print_count_doc(doc, sheets: int) -> int:
	"""Atomically add `sheets` to the invoice's Sales Invoice Print Count row;
	return the new value. Creates the row on the first ever print. A failure
	must never block the print, so it falls back to the stored count.
	"""
	name = doc.name
	branch = doc.get("custom_branch_name")
	company = doc.get("company")
	try:
		if frappe.db.exists("Sales Invoice Print Count", name):
			# raw SQL so the increment is atomic — this bypasses the controller's
			# validate(), so branch_name/company must be set here too.
			frappe.db.sql(
				"UPDATE `tabSales Invoice Print Count` "
				"SET print_count = print_count + %s, branch_name = %s, company = %s "
				"WHERE name = %s",
				(sheets, branch, company, name),
			)
			return _stored_count(name)
		frappe.get_doc(
			{
				"doctype": "Sales Invoice Print Count",
				"sales_invoice": name,
				"branch_name": branch,
				"company": company,
				"print_count": sheets,
			}
		).insert(ignore_permissions=True)
		return sheets
	except Exception:
		frappe.log_error(
			title=f"Print count update failed for Sales Invoice {name}",
			message=frappe.get_traceback(),
		)
		return _stored_count(name)


def _session_display_name() -> str:
	"""Display name of the user doing the printing, for Print Log.printed_by.

	The row's `owner` already carries the user id; printed_by carries the name a
	report shows, so live rows read the same way as the legacy rows backfilled
	from the old billing software (which only ever recorded a name). Falls back
	to the user id, and never raises — this runs on the print path.
	"""
	user = frappe.session.user
	try:
		return frappe.db.get_value("User", user, "full_name") or user
	except Exception:
		return user


def _log_print(doc, start_sheet: int, titles: list[str]):
	"""One Sales Invoice Print Log row per sheet, numbered from start_sheet+1."""
	printed_by = _session_display_name()
	for i, _title in enumerate(titles, 1):
		try:
			frappe.get_doc(
				{
					"doctype": "Sales Invoice Print Log",
					"sales_invoice": doc.name,
					"customer": doc.get("customer"),
					"customer_name": doc.get("customer_name"),
					"branch_name": doc.get("custom_branch_name"),
					"company": doc.company,
					"copy_number": start_sheet + i,
					"printed_by": printed_by,
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"Print log failed for Sales Invoice {doc.name}",
				message=frappe.get_traceback(),
			)


def reconcile_print_counts(company=None, commit=False, limit=None):
	"""Reset each Sales Invoice Print Count.print_count to the true sheet count.

	The counter is a cached total that can drift above the Print Log (an
	increment whose matching log insert failed, a double count). The Print Log
	is authoritative — one row per sheet actually produced — so the correct value
	is its highest copy_number for the invoice. This reads the log and rewrites
	only the counter; it never touches the log itself.

	DRY RUN unless commit=True: returns exactly which counters would change
	({invoice, from, to}) and writes nothing. `company` scopes to one company's
	invoices; `limit` caps how many are adjusted this call. Counters with no log
	rows at all are left untouched (pre-logging history — the log can't say what
	the true count was), and reported under `no_log`.
	"""
	conditions, params = "", {}
	if company:
		conditions = "WHERE company = %(company)s"
		params["company"] = company

	# Authoritative sheet count per invoice = highest copy_number in the log.
	log_max = {
		r.sales_invoice: cint(r.sheets)
		for r in frappe.db.sql(
			f"""
			SELECT sales_invoice, MAX(copy_number) AS sheets
			FROM `tabSales Invoice Print Log`
			{conditions}
			GROUP BY sales_invoice
			""",
			params,
			as_dict=True,
		)
	}

	drift, no_log = [], 0
	for c in frappe.get_all(
		"Sales Invoice Print Count", fields=["name", "print_count"]
	):
		actual = log_max.get(c.name)
		if actual is None:
			if company is None:
				no_log += 1
			continue
		if cint(c.print_count) != actual:
			drift.append({"invoice": c.name, "from": cint(c.print_count), "to": actual})

	drift.sort(key=lambda d: d["invoice"])
	if limit:
		drift = drift[: int(limit)]

	if commit:
		for d in drift:
			frappe.db.set_value(
				"Sales Invoice Print Count",
				d["invoice"],
				"print_count",
				d["to"],
				update_modified=False,
			)
		frappe.db.commit()

	return {
		"dry_run": not commit,
		("adjusted" if commit else "would_adjust"): len(drift),
		"no_log_skipped": no_log,
		"rows": drift,
	}
