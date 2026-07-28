"""Geometry tests for the PRE-PRINTED data-only overlays (the browser path).

Run it (needs google-chrome + pdftotext/pdftoppm + Pillow, cwd MUST be sites/):

    cd /home/sijan/frappe-15/sites
    ../env/bin/python ../apps/avinashgroup_app/avinashgroup_app/test_overlay_print.py

Covers the two formats in production use today:
    Grishma Invoice A5 Overlay          (form 'grishma')
    Nepal Gas Udyog Invoice A5 Overlay  (form 'ngi_udyog')

It renders EXISTING invoices and writes nothing: no print counter moves,
because the counter only advances on an actual print (form_dict.trigger_print
or a download cmd), and a standalone render sets neither. The run asserts that.

WHY EACH LAYER EXISTS
---------------------
A. HTML vs an INDEPENDENT transcription of the ESC/P map. The expectation
   tables below were written by reading escp_grishma.py / escp_ngi_udyog.py —
   NOT by reading overlay.py. That is the whole point: if overlay.py is
   "fixed" wrongly, this disagrees. It is what catches the two bugs found on
   2026-07-25 — the copy label anchored as a centre on a form whose ESC/P map
   says the x is a left edge, and the A5 width clamps (dates -> 205mm,
   amounts -> 207mm) being applied on the 241.3mm form too, dragging the
   dates ~11mm inboard of their calibrated box.

B. PDF page facts. Page size 241.3 x 139.7mm with no /Rotate is what makes the
   driver print it 1:1 instead of rotating it; page count == sheet count is the
   "one invoice ate two forms" regression.

C. Measured text positions out of the rendered PDF (pdftotext -bbox). Layers A
   and B prove the HTML says the right millimetres; this proves Chrome PUT them
   there. Without it, a silent shrink-to-fit would pass everything else.

D. Two line items must fit on one form, without colliding with the totals band.
   Requirement from the field: every form has room for at least two rows.
"""

import math
import os
import re
import subprocess
import sys

import frappe

SITE = os.environ.get("TEST_SITE", "nepalgas")
SITES_PATH = "/home/sijan/frappe-15/sites"
TPL = "avinashgroup_app/templates/print_formats/nepal_gas_invoice_a5_overlay.html"
OUT = "/tmp/overlay_print_test"
DPI = 110
PW, PH = 241.3, 139.7          # the real 9.5 x 5.5in form
CAL_MM = 200.0                 # calibration bar, well inside the page

# ---------------------------------------------------------------------------
# Layer A expectations — transcribed by hand from the ESC/P builders, which are
# the calibrated source. Each entry: (x, y, width, align). `align` is the
# ANCHOR the ESC/P builder uses, translated to how the overlay must express it:
#   left   -> div left edge sits at x
#   center -> div is a 50mm box centred on x
#   right  -> div RIGHT edge sits at x (ESC/P right=True)
# ---------------------------------------------------------------------------
FORMS = {
	# escp_grishma.py: copy_label comment says "x = START of the label text",
	# and line 208 emits it with no centring arithmetic -> left.
	# Dates at 198.0 are emitted with no right=True -> left.
	"grishma": {
		"copy_label":   (118.5, 40.0, 50, "left"),
		"invoice_no":   (38.0, 36.0, 90, "left"),
		"trans_date":   (198.0, 36.0, 34, "left"),
		"invoice_date": (198.0, 47.0, 34, "left"),
		"customer":     (57.0, 53.0, 90, "left"),
		"address":      (57.0, 56.0, 95, "left"),
		"pan":          (57.0, 63.0, 70, "left"),
		"words":        (31.0, 95.1, 90, "left"),
		"body_top": 84.0, "row_h": 4.8,
		"c_sno": 17.0, "c_hs": 30.0, "c_part": 54.0,
		"r_qty": 144.0, "r_rate": 177.0, "r_amt": 210.0,
		"y_disc": 94.0, "y_taxable": 100.0, "y_vat": 106.0, "y_grand": 115.0,
	},
	# escp_ngi_udyog.py: copy_label comment says "x = CENTRE (label is centred
	# at emit time)", and line 226 subtracts half the text width -> center.
	"ngi_udyog": {
		"copy_label":   (118.5, 34.7, 50, "center"),
		"invoice_no":   (35.0, 27.5, 90, "left"),
		"trans_date":   (193.0, 28.0, 34, "left"),
		"invoice_date": (193.0, 33.3, 34, "left"),
		"customer":     (52.0, 44.0, 90, "left"),
		"address":      (52.0, 49.0, 95, "left"),
		"pan":          (52.0, 55.0, 70, "left"),
		"words":        (48.0, 87.1, 90, "left"),
		"body_top": 72.0, "row_h": 4.8,
		"c_sno": 15.0, "c_hs": 25.0, "c_part": 50.0,
		"r_qty": 148.0, "r_rate": 182.0, "r_amt": 210.0,
		"y_disc": 87.0, "y_taxable": 93.0, "y_vat": 99.0, "y_grand": 107.0,
	},
}

DIV_RE = re.compile(
	r'<div style="position:absolute;\s*left:([-\d.]+)mm;\s*top:([-\d.]+)mm;\s*'
	r'width:([\d.]+)mm;\s*text-align:(\w+);\s*font-size:([\d.]+)pt;\s*'
	r'(font-weight:bold;)?\s*white-space:nowrap;[^>]*>(.*?)</div>',
	re.S,
)


def divs_of(html):
	"""[(left, top, width, align, size, bold, text)] in document order."""
	out = []
	for m in DIV_RE.finditer(html):
		out.append((
			float(m.group(1)), float(m.group(2)), float(m.group(3)),
			m.group(4), float(m.group(5)), bool(m.group(6)),
			re.sub(r"\s+", " ", m.group(7)).strip(),
		))
	return out


def sheets_of(html):
	"""HTML split per .ov-sheet, in print order."""
	parts = html.split('<div class="ov-sheet')
	return parts[1:]


def near(a, b, tol):
	return abs(a - b) <= tol


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def render(doc, form, page="form", rows_per_page=None, prev_sheets=None, params=None):
	"""`params` go into frappe.form_dict (rot / ox / oy / guide). Mutate the dict
	in place — get_safe_globals binds the object into the jinja env when the env
	is first built, so REPLACING frappe.local.form_dict is invisible to later
	renders in the same process."""
	frappe.local.form_dict.clear()
	frappe.local.form_dict.update(params or {})
	if prev_sheets is not None:
		doc.flags.print_prev_sheets = prev_sheets
	rp = f"{{% set rows_per_page = {rows_per_page} %}}" if rows_per_page else ""
	src = (
		f"{{% set form = '{form}' %}}{{% set page = '{page}' %}}{rp}"
		+ '{%% include "%s" %%}' % TPL
	)
	return frappe.render_template(src, {"doc": doc})


def to_pdf(html, tag):
	os.makedirs(OUT, exist_ok=True)
	base = f"{OUT}/{tag}"
	open(base + ".html", "w").write(html)
	subprocess.run(
		["google-chrome-stable", "--headless", "--disable-gpu", "--no-sandbox",
		 "--no-pdf-header-footer", f"--print-to-pdf={base}.pdf", f"file://{base}.html"],
		capture_output=True,
	)
	return base + ".pdf"


def pdf_facts(pdf):
	d = open(pdf, "rb").read()
	boxes = []
	for m in re.finditer(rb"/MediaBox\s*\[([^\]]*)\]", d):
		v = [float(x) for x in m.group(1).split()]
		boxes.append((round((v[2] - v[0]) * 25.4 / 72, 1), round((v[3] - v[1]) * 25.4 / 72, 1)))
	rot = [int(m.group(1)) for m in re.finditer(rb"/Rotate\s+(-?\d+)", d)]
	pages = len(re.findall(rb"/Type\s*/Page[^s]", d))
	return boxes, rot, pages


WORD_RE = re.compile(
	r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>'
)


def words_mm(pdf, page=1):
	"""[(x0, y0, x1, y1, text)] in mm from the page's top-left."""
	out = subprocess.run(
		["pdftotext", "-bbox", "-f", str(page), "-l", str(page), pdf, "-"],
		capture_output=True, text=True,
	).stdout
	k = 25.4 / 72
	return [
		(float(a) * k, float(b) * k, float(c) * k, float(d) * k, t)
		for a, b, c, d, t in WORD_RE.findall(out)
	]


def span_of(words, text):
	"""x_left, x_right, y_top of the words making up `text` (first match)."""
	toks = text.split()
	if not toks:
		return None
	for i in range(len(words) - len(toks) + 1):
		if [w[4] for w in words[i:i + len(toks)]] == toks:
			g = words[i:i + len(toks)]
			return min(w[0] for w in g), max(w[2] for w in g), min(w[1] for w in g)
	return None


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------
RESULTS = []


def check(name, ok, detail=""):
	RESULTS.append((name, bool(ok), detail))
	print(f"    [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def layer_a(form, html, doc):
	"""HTML coordinates vs the independent ESC/P transcription."""
	E = FORMS[form]
	sheet = sheets_of(html)[0]
	d = divs_of(sheet)
	by_text = {x[6]: x for x in d}

	def at(field, text, tol=0.001):
		x, y, w, align = E[field]
		# divs_of() collapses runs of whitespace; real data has doubled spaces
		# ("Grishma Enterprises  Pvt. Ltd."), so normalise the expectation too.
		text = re.sub(r"\s+", " ", text or "").strip()
		got = by_text.get(text)
		if not got:
			return check(f"{form}: {field} present", False, f"text {text!r} not rendered")
		left = x - 25 if align == "center" else x
		exp_align = "center" if align == "center" else "left"
		ok = near(got[0], left, tol) and near(got[1], y, tol) and got[3] == exp_align
		check(
			f"{form}: {field} @ {left:.1f},{y:.1f} {exp_align}",
			ok,
			"" if ok else f"got left={got[0]} top={got[1]} align={got[3]}",
		)

	at("copy_label", "TAX INVOICE")
	at("invoice_no", doc.get("custom_branch_name") or doc.name)
	at("customer", doc.customer_name)
	at("pan", doc.tax_id or "")

	# dates: left-anchored at their own x on the form page (NOT clamped to 205).
	# Matched on x as well as y: a form may deliberately put the transaction date
	# on the same line as the invoice number (both ngi and grishma do), and
	# selecting by y alone then picks whichever div the renderer emitted first.
	x, y, w, _ = E["trans_date"]
	date_divs = [z for z in d if near(z[1], y, 0.001) and near(z[0], x, 0.001)]
	check(
		f"{form}: trans_date left-anchored at {x}",
		bool(date_divs) and date_divs[0][3] == "left",
		"" if date_divs else f"no div at x={x} y={y}; that row holds {[(z[0], z[6]) for z in d if near(z[1], y, 0.001)]}",
	)

	# item row 1: column anchors straight off the ESC/P map
	ry = E["body_top"]
	row = [z for z in d if near(z[1], ry, 0.001)]
	got_left = {round(z[0], 2) for z in row}
	want_left = {
		round(E["c_sno"], 2), round(E["c_hs"], 2), round(E["c_part"], 2),
		round(E["r_qty"] - 22, 2), round(E["r_rate"] - 28, 2), round(E["r_amt"] - 30, 2),
	}
	check(f"{form}: item row columns", got_left == want_left,
	      "" if got_left == want_left else f"got {sorted(got_left)} want {sorted(want_left)}")

	# amounts right-anchored on the form's own r_amt, not the A5 clamp (207)
	grand = [z for z in d if near(z[1], E["y_grand"], 0.001)]
	ok = bool(grand) and near(grand[0][0] + grand[0][2], E["r_amt"], 0.001)
	check(f"{form}: grand total right edge @ {E['r_amt']}", ok,
	      "" if ok else f"got right={grand[0][0] + grand[0][2] if grand else None}")


def layer_b(form, html, pdf, expect_sheets):
	boxes, rot, pages = pdf_facts(pdf)
	sheets = html.count('class="ov-sheet')
	check(f"{form}: sheets == {expect_sheets}", sheets == expect_sheets, f"got {sheets}")
	check(f"{form}: pages == sheets", pages == sheets, f"pages={pages} sheets={sheets}")
	check(f"{form}: one .last", html.count("ov-sheet last") == 1)
	check(
		f"{form}: page {PW}x{PH}mm",
		bool(boxes) and all(near(w, PW, 0.5) and near(h, PH, 0.5) for w, h in boxes),
		f"got {set(boxes)}",
	)
	check(f"{form}: no /Rotate", not [r for r in rot if r % 360], f"got {rot}")


def layer_c(form, html, doc):
	"""Measured positions in the rendered PDF vs what the HTML declared."""
	E = FORMS[form]
	bar = (f'<div style="position:absolute;left:10mm;top:130mm;'
	       f'width:{CAL_MM}mm;height:2mm;background:#f00"></div>')
	marked = html.replace('<div class="ov-sheet', '<div class="ov-sheet', 1)
	i = marked.find(">", marked.find('<div class="ov-sheet')) + 1
	marked = marked[:i] + bar + marked[i:]
	pdf = to_pdf(marked, f"{form}_measured")

	words = words_mm(pdf, 1)
	check(f"{form}: text extracted from PDF", len(words) > 5, f"{len(words)} words")

	inv = doc.get("custom_branch_name") or doc.name
	s = span_of(words, inv)
	if s:
		x, y, _, _ = E["invoice_no"]
		check(f"{form}: invoice no measured at x={x}", near(s[0], x, 0.8),
		      f"measured {s[0]:.2f}mm want {x}mm")
	else:
		check(f"{form}: invoice no measured", False, "not found in PDF text")

	# scale: the injected bar must measure CAL_MM, proving no shrink-to-fit
	subprocess.run(["pdftoppm", "-png", "-r", str(DPI), "-f", "1", "-l", "1",
	                pdf, f"{OUT}/{form}_measured"], capture_output=True)
	png = f"{OUT}/{form}_measured-1.png"
	if os.path.exists(png):
		from PIL import Image, ImageChops
		r, g, b = Image.open(png).convert("RGB").split()
		mask = ImageChops.darker(
			r.point(lambda v: 255 if v > 150 else 0),
			ImageChops.darker(g.point(lambda v: 255 if v < 120 else 0),
			                  b.point(lambda v: 255 if v < 120 else 0)))
		bb = mask.getbbox()
		got = (bb[2] - bb[0]) * 25.4 / DPI if bb else 0.0
		check(f"{form}: scale 1:1 (bar {CAL_MM}mm)", near(got, CAL_MM, 1.2),
		      f"measured {got:.2f}mm")


def layer_d(form, doc):
	"""Two line items must fit on ONE form, clear of the totals band."""
	E = FORMS[form]
	two = frappe.get_doc(doc.as_dict())
	two.items = [doc.items[0], doc.items[0]]
	html = render(two, form, prev_sheets=2)          # single copy, keeps it simple
	sheet = sheets_of(html)
	check(f"{form}: 2 items stay on 1 sheet", len(sheet) == 1, f"got {len(sheet)} sheets")

	d = divs_of(sheet[0])
	r1 = [z for z in d if near(z[1], E["body_top"], 0.001)]
	r2 = [z for z in d if near(z[1], E["body_top"] + E["row_h"], 0.001)]
	check(f"{form}: row 2 rendered at pitch {E['row_h']}mm", bool(r1) and bool(r2),
	      f"row1={len(r1)} divs, row2={len(r2)} divs")
	# row 2's text must clear the first totals line
	row2_bottom = E["body_top"] + E["row_h"] + 3.0     # ~3mm of glyph at 8.5pt
	first_total = min(E["y_disc"], E["y_taxable"])
	check(f"{form}: row 2 clears totals band ({first_total}mm)",
	      row2_bottom < first_total, f"row2 bottom ~{row2_bottom}mm")


def layer_e(form, doc):
	"""&rot= must produce a page whose shape matches the rotation, with the
	content rotated to match — so nothing downstream has a reason to rotate
	again. This is the "make the orientation come out right on any machine"
	knob; each value has to actually do what it claims.

	Also proves ox/oy still work, since a rotation that silently ate the
	offsets would break calibration.
	"""
	cases = [
		(0,   PW, PH, None),
		(90,  PH, PW, "rotate(90deg)"),
		(180, PW, PH, "rotate(180deg)"),
		(270, PH, PW, "rotate(270deg)"),
	]
	for rot, want_w, want_h, marker in cases:
		html = render(doc, form, prev_sheets=2, params={"rot": rot})
		pdf = to_pdf(html, f"{form}_rot{rot}")
		boxes, rotate, pages = pdf_facts(pdf)
		ok_size = bool(boxes) and all(
			near(w, want_w, 0.5) and near(h, want_h, 0.5) for w, h in boxes)
		check(f"{form}: rot={rot} page {want_w}x{want_h}mm", ok_size, f"got {set(boxes)}")
		check(f"{form}: rot={rot} no /Rotate in PDF", not [r for r in rotate if r % 360])
		if marker:
			check(f"{form}: rot={rot} content transformed", marker in html)
		else:
			check(f"{form}: rot=0 no transform", "rotate(" not in html)

	# offsets survive rotation
	html = render(doc, form, prev_sheets=2, params={"rot": 90, "ox": 3, "oy": -2})
	E = FORMS[form]
	d = divs_of(sheets_of(html)[0])
	x, y, _, align = E["invoice_no"]
	got = [z for z in d if near(z[1], y - 2, 0.001) and near(z[0], x + 3, 0.001)]
	check(f"{form}: ox/oy apply under rotation", bool(got),
	      f"want left={x + 3} top={y - 2}")


def series_checks():
	from avinashgroup_app.custom_code.SalesInvoice.print_count import _titles_for
	cases = [
		((0, True, 0), ["TAX INVOICE", "INVOICE"]),
		((2, True, 0), ["COPY OF INVOICE 1"]),
		((3, True, 0), ["COPY OF INVOICE 2"]),
		((4, True, 0), ["COPY OF INVOICE 3"]),
		((0, False, 0), ["TAX INVOICE"]),
		((1, False, 0), ["INVOICE"]),
		((2, False, 0), ["COPY OF INVOICE 1"]),
		((9, True, 1), ["Sales Return"]),
	]
	for args, want in cases:
		got = _titles_for(*args)
		check(f"titles {args} -> {want}", got == want, "" if got == want else f"got {got}")


def pick_invoice(company):
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"docstatus": 1, "is_return": 0, "company": company},
		fields=["name"], order_by="creation desc", limit=1,
	)
	return rows[0].name if rows else None


def main():
	frappe.init(site=SITE, sites_path=SITES_PATH)
	frappe.connect()
	frappe.local.form_dict = frappe._dict()
	os.makedirs(OUT, exist_ok=True)

	assert not frappe.local.form_dict.get("cmd"), "must not look like a print request"

	targets = [
		("grishma", "Grishma Enterprises Pvt. Ltd."),
		("ngi_udyog", "Nepal Gas Udhyog Pvt. Ltd."),
	]

	print("\n=== copy-title series ===")
	series_checks()

	for form, company in targets:
		inv = pick_invoice(company)
		if not inv:
			check(f"{form}: invoice available", False, f"no submitted invoice for {company}")
			continue
		doc = frappe.get_doc("Sales Invoice", inv)
		before = frappe.db.get_value("Sales Invoice Print Count", inv, "print_count")

		print(f"\n=== {form}  ({inv}, {len(doc.items)} item(s)) ===")
		html = render(doc, form, prev_sheets=0)       # first print -> 2 copies
		pdf = to_pdf(html, form)
		layer_a(form, html, doc)
		layer_b(form, html, pdf, expect_sheets=2)
		layer_c(form, html, doc)
		layer_d(form, doc)
		layer_e(form, doc)

		after = frappe.db.get_value("Sales Invoice Print Count", inv, "print_count")
		check(f"{form}: no counter side effect", before == after, f"{before} -> {after}")

	frappe.destroy()
	bad = [r for r in RESULTS if not r[1]]
	print(f"\n{'=' * 60}\n{len(RESULTS) - len(bad)}/{len(RESULTS)} passed")
	if bad:
		print("FAILED:")
		for n, _, d in bad:
			print(f"  - {n}" + (f"  ({d})" if d else ""))
	print(f"artifacts in {OUT}")
	sys.exit(1 if bad else 0)


if __name__ == "__main__":
	main()
