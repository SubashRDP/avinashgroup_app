# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""ESC/P byte stream for the Avinash pre-printed invoice slip (wide carriage).

Same mechanism as escp_invoice.py (the Nepal Gas form): the server renders raw
ESC/P, QZ Tray carries the bytes, the printer types with its own font and
advances exactly one slip per form feed. See that module's header for why raw
ESC/P instead of a PDF.

The slip is 243mm x 140mm — its field span (12mm to 222mm = 210mm) exceeds a
narrow carriage's 8.0in (203mm) head travel, so this format REQUIRES a
wide-carriage printer (Epson LQ-2190 class). Those are ESC/P2, which also
lets the form length be set exactly: 140mm is not a whole number of 1/6in
lines (33 lines = 139.7mm would creep 0.3mm per slip on continuous forms),
so ESC ( U defines a 1/360in unit and ESC ( C sets the page to 1984 units.

All field positions are the millimetre values from the confirmed HTML slip
template (Print Format "Avinash Test" / the user's calibration block).
Horizontal: ESC $ absolute positioning in 1/60in from the printer's column 0.
Vertical: ESC J paper feeds in 1/180in, top-of-form relative. X0_MM / Y0_MM
are the only calibration knobs — adjust them if a whole print is shifted,
never the fields. The helpers are deliberately copied, not imported, from
escp_invoice.py: the two forms calibrate and evolve independently.
"""

import frappe
from frappe.utils import fmt_money

from avinashgroup_app.custom_code.SalesInvoice.print_count import invoice_copy_titles

ESC = "\x1b"
FF = "\x0c"

# --- calibration ---------------------------------------------------------
X0_MM = 12.0  # paper-left -> printer column 0 (S.No. column); calibrate on first live print
Y0_MM = 0.0   # top-of-form offset; + moves everything down

# --- field targets (mm from slip top-left), from the confirmed HTML slip --
POS = {
	"copy_label":   (90.0, 16.0),
	"invoice_no":   (40.0, 28.0),
	"trans_date":   (188.0, 28.0),
	"invoice_date": (188.0, 33.0),
	"customer":     (48.0, 42.0),
	"address":      (48.0, 47.0),
	"pan":          (48.0, 52.0),
	"body_top":     (0, 74.0),
	"row_h":        6.0,
	"words":        (48.0, 88.0),
	# column anchors inside the table (left x for left-aligned, right x for numeric)
	"c_sno":        12.0,
	"c_hs":         30.0,
	"c_part":       54.0,
	"r_qty":        170.0,   # right edge (QTY_X 150 + QTY_W 20)
	"r_rate":       194.0,
	"r_amt":        222.0,   # right edge; needs wide-carriage head travel
	# totals rows: right-aligned numerics at r_amt
	"y_disc":       88.0,
	"y_taxable":    94.0,
	"y_vat":        100.0,
	"y_grand":      106.0,
}

ROWS_PER_PAGE = 2
CPI = 10  # default pica; char cell = 2.54mm

# 140mm slip in 1/360in units for ESC ( C (ESC/P2 exact page length)
PAGE_LEN_UNITS = round(140 / 25.4 * 360)  # = 1984


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


def _clean(s) -> str:
	return frappe.utils.strip_html(frappe.utils.cstr(s)).replace("\n", " ").strip()


def _customer_address(doc) -> str:
	"""Primary (else newest) Address linked to the customer: line1, city, phone —
	the same lookup the HTML slip template uses."""
	links = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Address", "link_doctype": "Customer", "link_name": doc.customer},
		pluck="parent",
	)
	if not links:
		return ""
	rows = frappe.get_all(
		"Address",
		filters={"name": ["in", links]},
		fields=["address_line1", "city", "phone"],
		order_by="is_primary_address desc, creation desc",
		limit=1,
	)
	if not rows:
		return ""
	a = rows[0]
	parts = [a.address_line1, a.city, (a.phone or "").strip()]
	return ", ".join(p for p in parts if p)


def build(doc) -> str:
	"""Full ESC/P job for one Sales Invoice. One FF per 2-item slip."""
	bs_date = str(doc.get("custom_invoice_miti") or "").split(" ")[0]
	pan = frappe.db.get_value("Customer", doc.customer, "tax_id") or ""
	address = _customer_address(doc)
	price_list = (
		frappe.db.get_value("Price List", doc.selling_price_list, "price_list_name")
		if doc.get("selling_price_list")
		else ""
	) or (doc.get("selling_price_list") or "")

	grand = doc.get("grand_total") or 0

	# One full slip run per copy title: the first print of an invoice is the
	# INVOICE + TAX INVOICE pair (two form feeds), reprints a single copy.
	copy_titles = invoice_copy_titles(doc)

	items = list(doc.items)
	pages = [items[i : i + ROWS_PER_PAGE] for i in range(0, len(items), ROWS_PER_PAGE)] or [[]]

	out = [
		f"{ESC}@",
		f"{ESC}(U\x01\x00\x0a",  # define unit = 10/3600in = 1/360in
		f"{ESC}(C\x02\x00" + chr(PAGE_LEN_UNITS % 256) + chr(PAGE_LEN_UNITS // 256),  # page = 140mm
		f"{ESC}x\x01",  # LQ mode
	]
	P = POS
	runs = [(t, pno, pi) for t in copy_titles for pno, pi in enumerate(pages, 1)]
	for copy_label, pno, page_items in runs:
		last = pno == len(pages)
		el: list = []
		_el(el, P["copy_label"][0], P["copy_label"][1], copy_label, bold=True)
		_el(el, P["invoice_no"][0], P["invoice_no"][1], doc.name, bold=True)
		_el(el, P["trans_date"][0], P["trans_date"][1], bs_date)
		_el(el, P["invoice_date"][0], P["invoice_date"][1], bs_date)
		_el(el, P["customer"][0], P["customer"][1], _clean(doc.customer_name)[:47])
		_el(el, P["address"][0], P["address"][1], _clean(address)[:47])
		_el(el, P["pan"][0], P["pan"][1], pan)
		# VAT No. boxes = company's own VAT, pre-printed. Nothing goes there.

		base_sno = (pno - 1) * ROWS_PER_PAGE
		for i, it in enumerate(page_items):
			y = P["body_top"][1] + i * P["row_h"]
			part = ", ".join(
				p for p in (_clean(it.description), it.uom or "", f"({price_list})" if price_list else "")
				if p
			)
			_el(el, P["c_sno"], y, str(base_sno + i + 1))
			_el(el, P["c_hs"], y, str(it.get("gst_hsn_code") or "")[:12])
			_el(el, P["c_part"], y, part[:33])
			_el(el, P["r_qty"], y, _qty(it.qty), right=True)
			_el(el, P["r_rate"], y, _money(it.rate), right=True)
			_el(el, P["r_amt"], y, _money(it.amount), right=True)

		if last:
			if doc.get("discount_amount"):
				_el(el, P["r_amt"], P["y_disc"], _money(doc.discount_amount), right=True)
			_el(el, P["r_amt"], P["y_taxable"], _money(doc.total), right=True)
			_el(el, P["r_amt"], P["y_vat"], _money(doc.total_taxes_and_charges), right=True)
			_el(el, P["r_amt"], P["y_grand"], _money(grand), bold=True, right=True)
			for j, line in enumerate(_wrap(doc.get("in_words") or "", 37)[:3]):
				_el(el, P["words"][0], P["words"][1] + j * 4.3, line)
		else:
			_el(el, P["c_part"], P["y_taxable"], "Contd. on next slip...", bold=True)
		out.append(_emit(el))
		out.append(FF)
	out.append(f"{ESC}@")
	return "".join(out)


def avinash_slip_escp(doc) -> str:
	"""Jinja entry point for the raw_commands template."""
	return build(doc)
