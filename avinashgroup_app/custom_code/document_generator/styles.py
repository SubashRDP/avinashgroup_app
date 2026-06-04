# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Wrap a document's HTML body into a full, self-contained HTML page for preview/PDF.

For these single-page letters the header/footer render in normal flow (header at the
top, footer after the content) — reliable in wkhtmltopdf, unlike CSS position:fixed or
--header-html. For printing on pre-printed letterhead paper the header/footer are
omitted and the space is reserved via page margins instead (see ``api.py``)."""

DOCUMENT_CSS = """
* { box-sizing: border-box; }
body { margin: 0; font-family: "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt;
       color: #1a1a1a; line-height: 1.55; }
.dg-doc { width: 100%; }
.dg-doc p { margin: 0 0 9px; }
.dg-doc h1, .dg-doc h2, .dg-doc h3 { margin: 0 0 8px; font-weight: 600; line-height: 1.25; }
.dg-doc img, .dg-letter-head img, .dg-letter-foot img { max-width: 100%; }
.dg-letter-head { margin-bottom: 14px; }
.dg-letter-foot { margin-top: 30px; }

/* tables */
.dg-doc table { border-collapse: collapse; width: 100%; }
.dg-doc table.bordered { margin: 12px 0; font-size: 10pt; }
.dg-doc table.bordered th { background: #f3f5f8; border: 1px solid #c9ced6; padding: 7px 10px;
       font-weight: 600; text-align: center; }
.dg-doc table.bordered td { border: 1px solid #c9ced6; padding: 7px 10px; }

/* print-safe utilities (inline-block grid — works in wkhtmltopdf, no flexbox) */
.text-center { text-align: center; } .text-right { text-align: right; } .text-left { text-align: left; }
.fw-bold { font-weight: 600; } .text-muted { color: #667085; }
.mt-1{margin-top:5px} .mt-2{margin-top:10px} .mt-3{margin-top:18px} .mt-4{margin-top:28px}
.mb-1{margin-bottom:5px} .mb-2{margin-bottom:10px} .mb-3{margin-bottom:18px}
.row { font-size: 0; }
.row > .col, .row > [class*="col-"] { display: inline-block; vertical-align: top; font-size: 10.5pt; padding: 0 6px; }
.col-12{width:100%} .col-8{width:66.66%} .col-6{width:50%} .col-4{width:33.33%} .col-3{width:25%}
"""


def wrap_document(body_html, header_html="", footer_html="", header_height=0, footer_height=0):
	"""Wrap the body (+ optional in-flow header/footer) into a full HTML page.

	header_height/footer_height (mm) set the band's min-height so the drawn
	header/footer occupy the same space they'd reserve on a printed page."""
	from frappe.utils import flt

	parts = []
	if header_html:
		hh = flt(header_height)
		style = f"min-height:{hh}mm" if hh else ""
		parts.append(f'<div class="dg-letter-head" style="{style}">{header_html}</div>')
	parts.append(f'<div class="dg-doc">{body_html or ""}</div>')
	if footer_html:
		fh = flt(footer_height)
		style = f"min-height:{fh}mm" if fh else ""
		parts.append(f'<div class="dg-letter-foot" style="{style}">{footer_html}</div>')
	return (
		'<!DOCTYPE html><html><head><meta charset="UTF-8">'
		f"<style>{DOCUMENT_CSS}</style></head>"
		f'<body>{"".join(parts)}</body></html>'
	)
