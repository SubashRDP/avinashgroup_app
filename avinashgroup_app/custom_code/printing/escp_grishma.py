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
from frappe.utils import fmt_money

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
# 2026-07-28: replaced WHOLESALE with the Nepal Gas ('ngi') map, at the
# branches' request, as the base for Grishma's own calibration. The two rolls
# are the same 9.5x5.5in layout, and ngi carries a full day of measurements
# taken on the Windows tills, so it is a far better starting point than
# Grishma's own numbers were. The format also copies ngi's ox/oy, so the two
# print identically until Grishma is measured. Anything that diverges from
# here is Grishma-only and should say so in its comment.
POS = {
	"copy_label":   (118.5, 37.7),  # x = CENTRE (label is centred at emit time)
	"invoice_no":   (35.0, 31.0),
	"ref_inv":      (74.0, 46.7),
	"trans_date":   (199.0, 31.0),  # ends ~201.5mm physical: inside the LQ-310's
	                                # 203.2mm (8in) print band; y tracks invoice_no
	                                # so the two sit on one line
	"invoice_date": (199.0, 37.3),  # same 8in-band pullback as trans_date
	"do_no":        (193.0, 41.5),
	# customer / address / pan share one left edge: three ruled lines of the same
	# block on the form, so they start together
	"customer":     (54.0, 49.0),
	"address":      (54.0, 54.0),
	"pan":          (54.0, 58.0),
	"body_top":     (0, 77.0),
	"row_h":        4.8,
	"words":        (20.0, 99.1),
	"words_w":      75.0,    # box width; overlay only (ESC/P wraps by char count)
	# column anchors inside the table (left x for left-aligned, right x for numeric)
	"c_sno":        15.1,    # box left lands 0.1mm on the page. If S.No vanishes
	                         # from a PRINT but is in the PDF, the job went out as
	                         # media=Custom.<w>x<h>mm: CUPS clips Custom sizes by
	                         # the PPD's HWMargins (6.35mm). Print with a NAMED
	                         # form size, whose ImageableArea is the full page.
	"c_hs":         28.0,
	"hs_label":     (31.0, 70.0),  # "H.S. Code" column heading, typed once per form
	                               # above the item rows — only when the wrapper
	                               # sets show_hs_label
	"c_part":       52.0,
	"r_qty":        157.0,   # right edge for qty
	"r_rate":       185.0,
	"r_amt":        216.0,   # right edge; 201mm physical after ox=-15. NOTE this
	                         # head prints only an 8in/203.2mm band (evidence: every
	                         # right-aligned number lost its last digit at >203mm), so
	                         # nothing may render past ~202mm physical.
	# totals rows: right-aligned numerics at r_amt, so they share one vertical line
	"y_disc":       90.0,
	"y_taxable":    96.0,
	"y_vat":        102.0,
	"y_grand":      110.0,
}

# How to read POS["copy_label"] x — build() below emits it directly, with no
# centring arithmetic, so the x is the LEFT edge where the text starts.
# The HTML overlay reads this constant rather than keeping its own idea of the
# convention: until 2026-07-25 that idea lived in overlay.py, away from the
# measurement it describes, and the two disagreed — the browser path treated
# every form's x as a centre, printing the Grishma title about half a label
# width left of where the ESC/P path puts it.
COPY_LABEL_ANCHOR = "center"  # copied with the ngi map 2026-07-28; build()
                              # below centres the label to match

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
	# BS miti, date only: custom_invoice_miti may carry a time part
	# ("2083-01-16 00:00:00") — keep just the date. The Grishma form shows this
	# same miti in BOTH the Transaction Date and Invoice Date fields.
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
		# copy label is CENTRED on P["copy_label"].x — subtract half the text
		# width before emitting. Changed with the ngi map 2026-07-28, and
		# COPY_LABEL_ANCHOR below says so: that constant has to describe what
		# this line does, or the overlay anchors the title differently from the
		# ESC/P path (the bug found 2026-07-25).
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
		# "H.S. Code" column heading (the form has no pre-printed HS column)
		_el(el, P["hs_label"][0], P["hs_label"][1], "H.S. Code")

		base_sno = (pno - 1) * ROWS_PER_PAGE
		for i, it in enumerate(page_items):
			y = P["body_top"][1] + i * P["row_h"]
			# particulars: description, UOM, (price list)
			desc = frappe.utils.strip_html(frappe.utils.cstr(it.description or it.item_name or it.item_code)).replace("\n", " ").strip()
			part = ", ".join(p for p in (desc, it.uom or "", f"({price_list})" if price_list else "") if p)
			hs = frappe.db.get_value("Item", it.item_code, "custom_hs_code") or ""
			_el(el, P["c_sno"], y, str(base_sno + i + 1))
			# HS code: its own column, no border; +1mm down from the row line per user
			_el(el, P["c_hs"], y + 1, str(hs)[:8])
			_el(el, P["c_part"], y, part[:50])
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
