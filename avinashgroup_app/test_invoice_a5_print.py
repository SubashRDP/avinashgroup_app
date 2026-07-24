"""Geometry tests for the A5 plain-paper Sales Invoice print format.

Run it (needs google-chrome + pdftoppm + Pillow, and cwd MUST be sites/):

    cd /home/sijan/frappe-15/sites
    ../env/bin/python ../apps/avinashgroup_app/avinashgroup_app/test_invoice_a5_print.py

Not a bench unittest on purpose: it drives a real headless Chrome render and
measures the resulting PDF, which is the only way to catch the failures this
format actually has. It touches no data — it renders existing invoices.

WHAT IT GUARDS, and why each check exists
-----------------------------------------
1. PAGE COUNT == SHEET COUNT.  The branches' old symptom was "one page took
   two papers". In PDF terms that is a trailing blank page: page-break-after
   on the final sheet. Any mismatch here is that bug coming back.

2. PAGE SIZE is A5 and matches the declared orientation, with no /Rotate.
   The other old symptom was "the whole print came out rotated 90 degrees",
   which happened because the PDF asked for a page size the driver did not
   have and the driver improvised.

3. SCALE.  This is the important one and it is not obvious. A calibration bar
   of known width is injected into the form and measured on the rendered page.
   Chrome's print shrink-to-fit measures the UNTRANSFORMED layout width, and
   overflow:hidden does NOT stop it — the form is 241.3mm wide, so without
   `contain: strict` on .a5-sheet Chrome silently scales everything by
   210/233 = 0.90 and the mm-exact geometry quietly stops being mm-exact.
   It only misbehaves once the job runs to a second page, so a one-invoice
   eyeball test will not reveal it. The bar must come out CAL_MM * scale.
"""

import os
import re
import subprocess
import sys

import frappe

TPL = "avinashgroup_app/templates/print_formats/nepal_gas_invoice_a5.html"
SITE = "avinas1"
SITES_PATH = "/home/sijan/frappe-15/sites"
OUT = "/tmp/a5_print_test"
DPI = 110

# crop box + padding, mirroring the template
CX0, CW, CH, PAD = 10.0, 226.0, 128.0, 4.0
CAL_MM = CW  # a bar spanning the whole crop
SCALE = min((148.0 - 2 * PAD) / CH, (210.0 - 2 * PAD) / CW)
CAL = (
    f'<div style="position:absolute;left:{CX0}mm;top:60mm;'
    f'width:{CAL_MM}mm;height:2mm;background:#f00"></div>'
)


def _pdf_facts(pdf):
    d = open(pdf, "rb").read()
    boxes = []
    for m in re.finditer(rb"/MediaBox\s*\[([^\]]*)\]", d):
        v = [float(x) for x in m.group(1).split()]
        boxes.append((round((v[2] - v[0]) * 25.4 / 72, 1), round((v[3] - v[1]) * 25.4 / 72, 1)))
    rot = [int(m.group(1)) for m in re.finditer(rb"/Rotate\s+(-?\d+)", d)]
    pages = len(re.findall(rb"/Type\s*/Page[^s]", d))
    return boxes, rot, pages


def _cal_bbox_mm(png):
    """2-D bbox of the red bar in mm. Must be a real bbox: in portrait the bar
    runs down the page, so a per-column scan collapses the height."""
    from PIL import Image, ImageChops

    r, g, b = Image.open(png).convert("RGB").split()
    mask = ImageChops.darker(
        r.point(lambda v: 255 if v > 150 else 0),
        ImageChops.darker(g.point(lambda v: 255 if v < 120 else 0),
                          b.point(lambda v: 255 if v < 120 else 0)),
    )
    bb = mask.getbbox()
    if not bb:
        return 0.0, 0.0
    k = 25.4 / DPI
    return (bb[2] - bb[0]) * k, (bb[3] - bb[1]) * k


def check(invoice, orient, rows_per_page=None, label=""):
    doc = frappe.get_doc("Sales Invoice", invoice)
    rp = f"{{% set rows_per_page = {rows_per_page} %}}" if rows_per_page else ""
    html = frappe.render_template(
        f"{{% set orient = '{orient}' %}}{rp}" + '{%% include "%s" %%}' % TPL, {"doc": doc}
    )
    sheets = html.count('class="a5-sheet')
    lasts = html.count("a5-sheet last")
    html = html.replace('<div class="a5-form">', '<div class="a5-form">' + CAL, 1)

    tag = f"{orient}{'_r' + str(rows_per_page) if rows_per_page else ''}"
    base = f"{OUT}/{tag}"
    open(base + ".html", "w").write(html)
    subprocess.run(
        ["google-chrome-stable", "--headless", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer", f"--print-to-pdf={base}.pdf", f"file://{base}.html"],
        capture_output=True,
    )
    subprocess.run(["pdftoppm", "-png", "-r", str(DPI), "-f", "1", "-l", "1",
                    base + ".pdf", base], capture_output=True)

    boxes, rot, pages = _pdf_facts(base + ".pdf")
    exp = (148.0, 210.0) if orient == "portrait" else (210.0, 148.0)
    bw, bh = _cal_bbox_mm(base + "-1.png")
    got = bh if orient == "portrait" else bw
    want = CAL_MM * SCALE

    ok = {
        "pages == sheets": pages == sheets,
        "one .last": lasts == 1,
        # Chrome rounds the page box to whole PDF points, so allow 0.5mm
        "A5 page size": bool(boxes) and all(
            abs(w - exp[0]) < 0.5 and abs(h - exp[1]) < 0.5 for w, h in boxes),
        "no /Rotate": not [r for r in rot if r % 360],
        "scale exact": abs(got - want) < 1.2,
    }
    print(f"\n--- {label or orient}  (items={len(doc.items)}, rows/sheet={rows_per_page or 3}) ---")
    print(f"    sheets={sheets} pages={pages} size={set(boxes)} rotate={rot or 'none'}")
    print(f"    calibration bar {got:.1f}mm (want {want:.1f}mm)")
    for k, v in ok.items():
        print(f"    [{'PASS' if v else 'FAIL'}] {k}")
    return all(ok.values())


def main():
    os.makedirs(OUT, exist_ok=True)
    frappe.init(site=SITE, sites_path=SITES_PATH)
    frappe.connect()

    single = frappe.db.get_value("Sales Invoice", {"docstatus": 1}, "name", order_by="modified desc")
    multi = frappe.db.sql(
        "select parent from `tabSales Invoice Item` group by parent having count(*) >= 2 limit 1"
    )
    multi = multi[0][0] if multi else single
    if not single:
        print("no Sales Invoice on this site to render")
        return 1

    results = [
        check(single, "landscape"),
        check(single, "portrait"),
        # rows_per_page=1 forces the multi-sheet path even on small invoices
        check(multi, "landscape", 1, "landscape / multi-sheet"),
        check(multi, "portrait", 1, "portrait / multi-sheet"),
    ]
    print("\n" + "=" * 46)
    print("ALL PASS" if all(results) else "SOME CHECKS FAILED")
    print("=" * 46)
    print("renders in", OUT)
    frappe.destroy()
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
