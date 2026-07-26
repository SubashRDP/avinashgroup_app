# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""ESC/P byte stream for the Nepal Gas continuous-form invoice (LQ-310).

Why raw ESC/P instead of a PDF
------------------------------
The branches replaced FACT, which printed these forms for years on the same
Windows PC + LQ-310 with zero printer configuration. FACT never went through
the Windows graphics driver: it sent the printer plain text with ESC/P control
codes, so paper size / orientation / scaling never entered the picture. Our PDF
path does go through the driver, which believes A4 is loaded and rotates the
9.5x5.5in page — the "vertical" print. This module restores the FACT mechanism:
the server renders raw ESC/P, QZ Tray (or a network share) carries the bytes,
the printer types with its own font and advances exactly one form per invoice.

Coordinates
-----------
All field positions are the millimetre targets measured off a rectified scan of
a real FACT-printed Narayani form (see nepal_gas_invoice.html for the method).
Horizontal: ESC $ absolute positioning in 1/60in units, relative to the
printer's column 0. On the reference print the rightmost ink sits at 227.9mm
from the paper edge = X0 + the LQ-310's full 8.0in head travel, giving
X0 ~= 24.7mm: the tractor holds the paper so that column 0 falls ~24.7mm from
the left paper edge. That single offset (and Y0 for top-of-form) are the only
calibration knobs; adjust them if a whole print is shifted, never the fields.
Vertical: ESC J paper feeds in 1/180in units, top-of-form relative.

Form length is set to 33 lines of 1/6in = 5.5in exactly, so FF lands on the
next form's top regardless of how much was printed.
"""

import frappe
from frappe.utils import fmt_money

from avinashgroup_app.custom_code.SalesInvoice.print_count import invoice_copy_titles

ESC = "\x1b"
FF = "\x0c"

# --- calibration ---------------------------------------------------------
X0_MM = 12.0  # measured 2026-07-14 with the centre-circle target: column 0
              # sits 12mm from the paper's left edge on this rig. Every POS x
              # is a TRUE ruler distance from the left paper edge. Max
              # reachable ink: X0 + 203.2mm head travel = 215.4mm.
Y0_MM = -7.7  # measured 2026-07-14 with the centre-circle target: the printer
              # registers top-of-form 7.7mm below the perforation. With this
              # correction every POS y is a TRUE ruler distance from the
              # perforation — measure the form, type the number.

# --- measured field targets (mm from paper top-left), data baseline tops --
# Re-derived 2026-07-14 from the branch-calibrated "Avinash Sales invoice"
# HTML format: rendered it on A4 via chrome exactly as the branches print it,
# read the glyph boxes with pdftotext -bbox, and added X0 (page x=0 lands on
# printer column 0 = 22mm from the paper edge). The old FACT-scan values are
# in git history if this calibration turns out worse.
POS = {
	"copy_label":   (118.5, 37.7),  # x = CENTRE (label is centred at emit time)
	"invoice_no":   (35.0, 31.5),  # starts 3.5cm from left, 1.5mm up from 3.3cm per user
	"ref_inv":      (74.0, 46.7),
	"trans_date":   (193.0, 31.0),  # printed at 12cpi so the full date fits before the 215.4mm head limit
	"invoice_date": (193.0, 36.3),  # same column/pitch as trans date, 5.3mm below
	"do_no":        (193.0, 41.5),
	"customer":     (52.0, 48.0),  # 5.2cm from left; 2mm up from 5.0cm per user
	"address":      (52.0, 53.0),
	"pan":          (52.0, 58.0),
	"body_top":     (0, 75.0),  # first item row 7.5cm from top per user
	"row_h":        4.8,
	"words":        (48.0, 90.1),  # wraps at 13.5cm (51 chars at 15cpi), continues down
	# column anchors inside the table (left x for left-aligned, right x for numeric)
	"c_sno":        15.0,
	"c_hs":         25.0,
	"c_part":       50.0,    # particulars box runs 5.0 -> 13.8cm (41 chars at 12cpi)
	"r_qty":        148.0,   # right edge for qty
	"r_rate":       182.0,
	"r_amt":        210.0,   # right edge; X0+203.2mm head travel = 215.4mm hard limit
	# totals rows: right-aligned numerics at r_amt
	"y_disc":       90.0,  # 1mm up per user
	"y_taxable":    96.0,  # 1mm up per user
	"y_vat":        102.0,
	"y_grand":      110.0,
}

# How to read POS["copy_label"] x — build() below subtracts half the text width
# before emitting, so the x is the CENTRE the label is centred on. The HTML
# overlay reads this constant so both print paths anchor the title the same way
# (see escp_grishma.py for what went wrong when the convention lived elsewhere).
COPY_LABEL_ANCHOR = "center"

ROWS_PER_PAGE = 2  # the branch format prints 2 item lines per form
CPI = 15  # whole invoice prints at 15cpi; char cell = 1.69mm


def _h(x_mm: float) -> str:
	"""Horizontal position: CR then spaces at the current pitch.

	Deliberately NOT ESC $ — its binary argument bytes exceed 127 for most
	of the form width, and the browser->QZ Tray path UTF-8-encodes the
	command string, mangling any byte over 127 (dates/amounts then print at
	the left edge). CR + spaces keeps the whole job 7-bit ASCII, which every
	transport passes through untouched. Quantization is one char cell
	(25.4/CPI mm), well inside dot-matrix tolerance.
	"""
	n = max(0, round((x_mm - X0_MM) * CPI / 25.4))
	return "\r" + " " * n


def _feed_to(state: dict, y_mm: float) -> str:
	"""Advance paper from state['y'] to y_mm using ESC J (n/180in, n<=255)."""
	target = y_mm + Y0_MM
	delta = target - state["y"]
	if delta <= 0.01:
		return ""
	state["y"] = target
	units = round(delta * 180 / 25.4)
	out = []
	while units > 0:
		step = min(units, 127)  # <=127 keeps the byte 7-bit-safe through UTF-8 transports
		out.append(f"{ESC}J{chr(step)}")
		units -= step
	return "".join(out)


def _emit(elems: list) -> str:
	"""Emit elements in strict top-to-bottom order: ESC J only feeds forward."""
	st = {"y": 0.0}
	out = []
	for y_mm, x_mm, s, bold in sorted(elems, key=lambda e: (e[0], e[1])):
		out.append(_feed_to(st, y_mm))
		out.append(_h(x_mm))
		out.append(s)  # regular weight everywhere; bold flag intentionally ignored
		out.append("\r")
	return "".join(out)


def _el(elems: list, x_mm: float, y_mm: float, s, bold: bool = False, right: bool = False):
	if not s:
		return
	s = str(s)
	if right:
		x_mm = x_mm - len(s) * 25.4 / CPI
	elems.append((y_mm, x_mm, s, bold))


def _money(v) -> str:
	return fmt_money(abs(v), 2) if v is not None else ""


def _qty(q) -> str:
	q = abs(q or 0)
	return str(int(q)) if q == int(q) else str(q)


def _wrap(s: str, width: int) -> list[str]:
	words, lines, cur = (s or "").split(), [], ""
	for w in words:
		if cur and len(cur) + 1 + len(w) > width:
			lines.append(cur)
			cur = w
		else:
			cur = f"{cur} {w}" if cur else w
	if cur:
		lines.append(cur)
	return lines


def build(doc) -> str:
	"""Full ESC/P job for one Sales Invoice. One FF per 3-item form."""
	invoice_no = doc.get("custom_branch_name") or doc.name
	# BS miti, date only: custom_invoice_miti may carry a time part
	# ("2083-01-16 00:00:00") — keep just the date. Shown in BOTH the
	# Transaction Date and Invoice Date fields.
	bs_date = frappe.utils.cstr(doc.get("custom_invoice_miti") or "").split(" ")[0]
	if not bs_date:
		try:
			from avinashgroup_app.custom_code.CBMS.utils import bs_date_str

			bs_date = bs_date_str(doc.posting_date)
		except Exception:
			bs_date = ""
	do_nos = ", ".join(sorted({i.delivery_note for i in doc.items if i.get("delivery_note")}))
	price_list = (
		frappe.db.get_value("Price List", doc.selling_price_list, "price_list_name")
		if doc.get("selling_price_list")
		else ""
	) or (doc.get("selling_price_list") or "")
	address = (doc.address_display or doc.get("custom_citytown") or "")
	address = frappe.utils.strip_html(address.replace("<br>", ", ")).replace("\n", " ").strip().rstrip(",")
	is_cn = bool(doc.get("is_return"))

	vat = doc.get("custom_total_vat_amount") or 0
	if not vat:
		for t in doc.get("taxes") or []:
			if "vat" in f"{t.description or ''}{t.account_head or ''}".lower():
				vat += t.tax_amount or 0
	grand = doc.get("rounded_total") or doc.get("grand_total") or 0

	# One full form run per copy title: the first print of an invoice is the
	# INVOICE + TAX INVOICE pair (two form feeds), reprints a single copy.
	copy_titles = invoice_copy_titles(doc)

	items = list(doc.items)
	pages = [items[i : i + ROWS_PER_PAGE] for i in range(0, len(items), ROWS_PER_PAGE)] or [[]]

	# init, form=33 lines(5.5in), LQ mode, 15cpi, regular weight
	out = [f"{ESC}@", f"{ESC}C{chr(33)}", f"{ESC}x{chr(1)}", f"{ESC}g"]
	P = POS
	runs = [(t, pno, pi) for t in copy_titles for pno, pi in enumerate(pages, 1)]
	for copy_label, pno, page_items in runs:
		last = pno == len(pages)
		el: list = []
		# copy label is centred on P["copy_label"].x (branch format centres it)
		_el(el, P["copy_label"][0] - len(copy_label) * 25.4 / CPI / 2,
			P["copy_label"][1], copy_label, bold=True)
		_el(el, P["invoice_no"][0], P["invoice_no"][1], invoice_no, bold=True)
		_el(el, P["trans_date"][0], P["trans_date"][1], bs_date)
		_el(el, P["invoice_date"][0], P["invoice_date"][1], bs_date)
		_el(el, P["do_no"][0], P["do_no"][1], do_nos[:12])
		if is_cn and doc.get("return_against"):
			_el(el, P["ref_inv"][0], P["ref_inv"][1], f"Ref Inv: {doc.return_against}")
		_el(el, P["customer"][0], P["customer"][1], (doc.customer_name or "")[:34])
		_el(el, P["address"][0], P["address"][1], address[:34])
		_el(el, P["pan"][0], P["pan"][1], doc.get("tax_id") or "")

		base_sno = (pno - 1) * ROWS_PER_PAGE
		for i, it in enumerate(page_items):
			y = P["body_top"][1] + i * P["row_h"]
			hs = frappe.db.get_value("Item", it.item_code, "custom_hs_code") or ""
			# particulars mirror the branch format: description, UOM, (price list)
			desc = frappe.utils.strip_html(frappe.utils.cstr(it.description or it.item_name or it.item_code)).replace("\n", " ").strip()
			part = ", ".join(p for p in (desc, it.uom or "", f"({price_list})" if price_list else "") if p)
			_el(el, P["c_sno"], y, str(base_sno + i + 1))
			_el(el, P["c_hs"], y, str(hs)[:8])
			_el(el, P["c_part"], y, part[:40])
			_el(el, P["r_qty"], y, _qty(it.qty), right=True)
			_el(el, P["r_rate"], y, _money(it.rate), right=True)
			_el(el, P["r_amt"], y, _money(it.amount), right=True)

		if last:
			_el(el, P["r_amt"], P["y_disc"], _money(doc.get("discount_amount") or 0), right=True)
			_el(el, P["r_amt"], P["y_taxable"], _money(doc.net_total), right=True)
			_el(el, P["r_amt"], P["y_vat"], _money(vat), right=True)
			_el(el, P["r_amt"], P["y_grand"], _money(grand), bold=True, right=True)
			# line width: words box runs 4.8 -> 13.5cm = 87mm = 51 chars at 15cpi
			for j, line in enumerate(_wrap(doc.get("in_words") or "", 51)[:4]):
				_el(el, P["words"][0], P["words"][1] + j * 4.3, line)
		out.append(_emit(el))
		out.append(FF)
	out.append(f"{ESC}@")
	return "".join(out)


def ngi_escp(doc) -> str:
	"""Jinja entry point for the raw_commands template."""
	return build(doc)
