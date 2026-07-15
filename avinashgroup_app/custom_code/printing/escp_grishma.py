# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""ESC/P byte stream for the Grishma Enterprises continuous-form invoice (LQ-310).

Clone of escp_invoice.py (Nepal Gas) — see that module's header for why raw
ESC/P instead of a PDF, and for the transport rules (whole job stays 7-bit
ASCII so the browser->QZ Tray path can't mangle it).

The Grishma form (photo 2026-07-15, VAT No. 610489998) is the same 9.5x5.5in
form family with ONE layout difference: there is NO HS Code column. The item
table is  S.No. | Particular | Quantity | Rate | Total Price NRS.

Coordinates
-----------
Every POS value is a TRUE ruler distance in mm from the form's top-left
corner (top = the perforation): measure the form, type the number.
X0_MM / Y0_MM carry the printer-rig geometry measured 2026-07-14 with the
centre-circle target; they are shared with the Nepal Gas format because it is
the same physical printer. If a WHOLE print is shifted, fix X0/Y0 (or check
the tractor position) — never the fields.

The POS values below START from the Nepal Gas calibration (same form family);
calibrate them against a real Grishma form with print_grishma_test.sh at the
bench root: edit a number, run the script, measure again.
"""

import frappe
from frappe.utils import fmt_money, formatdate

from avinashgroup_app.custom_code.SalesInvoice.print_count import invoice_copy_titles

ESC = "\x1b"
FF = "\x0c"

# --- calibration ---------------------------------------------------------
X0_MM = 12.0  # column 0 sits 12mm from the paper's left edge on this rig
              # (measured 2026-07-14, centre-circle target). Max reachable
              # ink: X0 + 203.2mm head travel = 215.4mm.
Y0_MM = -7.7  # printer registers top-of-form 7.7mm below the perforation
              # (measured 2026-07-14, centre-circle target).

# --- field targets (mm from the form's top-left corner) -------------------
# CONVENTION: every x is where the text STARTS (its left edge) — measure to
# where the first character should sit. EXCEPTION: r_qty / r_rate / r_amt are
# RIGHT edges, because numbers are right-aligned so their digits line up in
# the column; for those three, measure to where the number should END.
# Initial values = the Nepal Gas 2026-07-14 calibration, with the HS Code
# column removed (particulars pulled left to follow S.No.). Calibrate each
# number on a real Grishma form.
POS = {
	"copy_label":   (118.5, 40.0),  # x = START of the label text; 4cm from top per user
	"invoice_no":   (41.0, 33.0),  # left start decreased 2mm per user (4.3 -> 4.1cm)
	"ref_inv":      (74.0, 46.7),
	"trans_date":   (198.0, 37.0),  # 19.8cm: latest start where the full date fits
	                                # before the 215.4mm head limit (box is at 20.4
	                                # but the head can't reach 22.1cm)
	"invoice_date": (198.0, 43.0),  # same column as trans date; 2mm up again per user
	"do_no":        (193.0, 41.5),
	"customer":     (58.0, 51.0),  # starts 5.8cm from left, 5.1cm from top per user
	"address":      (58.0, 56.0),  # same left start as customer name
	"pan":          (58.0, 61.0),  # same left start as customer name
	"body_top":     (0, 80.0),   # first item row; +5mm per user
	"row_h":        4.8,
	"words":        (51.0, 92.1),  # amount in words; +3mm left, +2mm down per user
	# column anchors inside the table (left x for left-aligned, right x for numeric)
	"c_sno":        17.0,    # +2mm per user
	"c_part":       29.0,    # particulars start right after S.No.; +4mm per user
	"r_qty":        149.0,   # right edge for qty; +1mm per user
	"r_rate":       182.0,
	"r_amt":        210.0,   # right edge; X0+203.2mm head travel = 215.4mm hard limit
	# totals rows: right-aligned numerics at r_amt
	"y_disc":       90.0,
	"y_taxable":    96.0,
	"y_vat":        102.0,
	"y_grand":      110.0,
}

ROWS_PER_PAGE = 2
CPI = 15  # whole invoice prints at 15cpi; char cell = 1.69mm


def _h(x_mm: float) -> str:
	"""Horizontal position: CR then spaces at the current pitch (7-bit safe)."""
	n = max(0, round((x_mm - X0_MM) * CPI / 25.4))
	return "\r" + " " * n


def _feed_to(state: dict, y_mm: float) -> str:
	"""Advance paper from state['y'] to y_mm using ESC J (n/180in, n<=127)."""
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
	"""Full ESC/P job for one Sales Invoice. One FF per form."""
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
	price_list = (
		frappe.db.get_value("Price List", doc.selling_price_list, "price_list_name")
		if doc.get("selling_price_list")
		else ""
	) or (doc.get("selling_price_list") or "")
	# address_line1 of the customer's primary Address record (per user);
	# blank when the customer has none — no fallback
	address = ""
	if doc.get("customer"):
		rows = frappe.get_all(
			"Address",
			filters={"link_doctype": "Customer", "link_name": doc.customer},
			fields=["address_line1"],
			order_by="`tabAddress`.is_primary_address desc, `tabAddress`.creation desc",
			limit=1,
		)
		address = (rows[0].address_line1 or "") if rows else ""
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
		# copy label starts at P["copy_label"].x (user measures where text begins)
		_el(el, P["copy_label"][0], P["copy_label"][1], copy_label, bold=True)
		_el(el, P["invoice_no"][0], P["invoice_no"][1], invoice_no, bold=True)
		_el(el, P["trans_date"][0], P["trans_date"][1], bs_date)
		_el(el, P["invoice_date"][0], P["invoice_date"][1], ad_date)
		_el(el, P["do_no"][0], P["do_no"][1], do_nos[:12])
		if is_cn and doc.get("return_against"):
			_el(el, P["ref_inv"][0], P["ref_inv"][1], f"Ref Inv: {doc.return_against}")
		_el(el, P["customer"][0], P["customer"][1], (doc.customer_name or "")[:34])
		_el(el, P["address"][0], P["address"][1], address[:34])
		_el(el, P["pan"][0], P["pan"][1], doc.get("tax_id") or "")

		base_sno = (pno - 1) * ROWS_PER_PAGE
		for i, it in enumerate(page_items):
			y = P["body_top"][1] + i * P["row_h"]
			# particulars: description, UOM, (price list) — no HS column on this form
			desc = frappe.utils.strip_html(frappe.utils.cstr(it.description or it.item_name or it.item_code)).replace("\n", " ").strip()
			part = ", ".join(p for p in (desc, it.uom or "", f"({price_list})" if price_list else "") if p)
			_el(el, P["c_sno"], y, str(base_sno + i + 1))
			_el(el, P["c_part"], y, part[:55])
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


def grishma_escp(doc) -> str:
	"""Jinja entry point for the raw_commands template."""
	return build(doc)
