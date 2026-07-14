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
from frappe.utils import fmt_money, formatdate

from avinashgroup_app.custom_code.SalesInvoice.print_count import invoice_copy_titles

ESC = "\x1b"
FF = "\x0c"

# --- calibration ---------------------------------------------------------
X0_MM = 22.0  # paper-left -> printer column 0 (FACT prints S.No. at 22.1mm = its col 0)
Y0_MM = 0.0   # top-of-form offset; + moves everything down

# --- measured field targets (mm from paper top-left), data baseline tops --
POS = {
	"copy_label":   (70.0, 1.5),
	"invoice_no":   (33.0, 29.6),
	"ref_inv":      (84.0, 39.0),
	"trans_date":   (196.5, 27.5),
	"invoice_date": (196.5, 32.8),
	"do_no":        (196.1, 37.8),
	"customer":     (54.0, 43.5),
	"address":      (54.7, 49.0),
	"pan":          (55.0, 53.9),
	"body_top":     (0, 72.4),
	"row_h":        4.8,
	"words":        (52.0, 88.0),
	# column anchors inside the table (left x for left-aligned, right x for numeric)
	"c_sno":        22.1,
	"c_hs":         27.0,
	"c_part":       50.5,
	"r_qty":        160.0,   # right edge for qty
	"r_rate":       185.0,
	"r_amt":        225.0,   # right edge; X0+8.0in head travel = 225.2mm hard limit
	# totals rows: right-aligned numerics at r_amt
	"y_disc":       88.2,
	"y_taxable":    93.9,
	"y_vat":        100.1,
	"y_grand":      106.9,
}

ROWS_PER_PAGE = 3
CPI = 10  # default pica; char cell = 2.54mm


def _h(x_mm: float) -> str:
	"""ESC $ absolute horizontal position (1/60in units from column 0)."""
	n = max(0, round((x_mm - X0_MM) * 60 / 25.4))
	return f"{ESC}${chr(n % 256)}{chr(n // 256)}"


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
		step = min(units, 255)
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
		if bold:
			out.append(f"{ESC}E")
		out.append(s)
		if bold:
			out.append(f"{ESC}F")
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
	bs_date = doc.get("custom_invoice_miti") or ""
	if not bs_date:
		try:
			from avinashgroup_app.custom_code.CBMS.utils import bs_date_str

			bs_date = bs_date_str(doc.posting_date)
		except Exception:
			bs_date = ""
	ad_date = formatdate(doc.posting_date, "dd-MM-yyyy")
	do_nos = ", ".join(sorted({i.delivery_note for i in doc.items if i.get("delivery_note")}))
	address = (doc.address_display or doc.get("custom_citytown") or "")
	address = frappe.utils.strip_html(address.replace("<br>", ", ")).replace("\n", " ").strip().rstrip(",")
	is_cn = bool(doc.get("is_return"))

	vat = doc.get("custom_total_vat_amount") or 0
	if not vat:
		for t in doc.get("taxes") or []:
			if "vat" in f"{t.description or ''}{t.account_head or ''}".lower():
				vat += t.tax_amount or 0
	grand = doc.get("rounded_total") or doc.get("grand_total") or 0

	# One full form run per copy title — pair=False: one sheet per print
	# event (1st INVOICE, 2nd TAX INVOICE, then copies).
	copy_titles = invoice_copy_titles(doc, pair=False)

	items = list(doc.items)
	pages = [items[i : i + ROWS_PER_PAGE] for i in range(0, len(items), ROWS_PER_PAGE)] or [[]]

	out = [f"{ESC}@", f"{ESC}C{chr(33)}", f"{ESC}x{chr(1)}"]  # init, form=33 lines(5.5in), LQ mode
	P = POS
	runs = [(t, pno, pi) for t in copy_titles for pno, pi in enumerate(pages, 1)]
	for copy_label, pno, page_items in runs:
		last = pno == len(pages)
		el: list = []
		_el(el, P["copy_label"][0], P["copy_label"][1], copy_label, bold=True)
		_el(el, P["invoice_no"][0], P["invoice_no"][1], invoice_no, bold=True)
		_el(el, P["trans_date"][0], P["trans_date"][1], bs_date)
		_el(el, P["invoice_date"][0], P["invoice_date"][1], ad_date)
		_el(el, P["do_no"][0], P["do_no"][1], do_nos[:20])
		if is_cn and doc.get("return_against"):
			_el(el, P["ref_inv"][0], P["ref_inv"][1], f"Ref Inv: {doc.return_against}")
		_el(el, P["customer"][0], P["customer"][1], (doc.customer_name or "")[:34])
		_el(el, P["address"][0], P["address"][1], address[:34])
		_el(el, P["pan"][0], P["pan"][1], doc.get("tax_id") or "")

		base_sno = (pno - 1) * ROWS_PER_PAGE
		for i, it in enumerate(page_items):
			y = P["body_top"][1] + i * P["row_h"]
			hs = frappe.db.get_value("Item", it.item_code, "custom_hs_code") or ""
			_el(el, P["c_sno"], y, str(base_sno + i + 1))
			_el(el, P["c_hs"], y, str(hs)[:8])
			_el(el, P["c_part"], y, (it.item_name or it.item_code or "")[:33])
			_el(el, P["r_qty"], y, f"{_qty(it.qty)} {it.uom or ''}".strip(), right=True)
			_el(el, P["r_rate"], y, _money(it.rate), right=True)
			_el(el, P["r_amt"], y, _money(it.amount), right=True)

		if last:
			if doc.get("additional_discount_percentage"):
				_el(el, P["r_amt"], P["y_disc"], f"{abs(doc.additional_discount_percentage)}%", right=True)
			_el(el, P["r_amt"], P["y_taxable"], _money(doc.net_total), right=True)
			_el(el, P["r_amt"], P["y_vat"], _money(vat), right=True)
			_el(el, P["r_amt"], P["y_grand"], _money(grand), bold=True, right=True)
			for j, line in enumerate(_wrap(doc.get("in_words") or "", 33)[:4]):
				_el(el, P["words"][0], P["words"][1] + j * 4.3, line)
		else:
			_el(el, P["c_part"], P["y_taxable"], "Contd. on next form...", bold=True)
		out.append(_emit(el))
		out.append(FF)
	out.append(f"{ESC}@")
	return "".join(out)


def ngi_escp(doc) -> str:
	"""Jinja entry point for the raw_commands template."""
	return build(doc)
