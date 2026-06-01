# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Page layout + base CSS shared by the canvas editor (preview) and the PDF.

Layout is a simple **vertical flow**: sections stack top-to-bottom in ``idx`` order;
each block has a width percent and an alignment (left/center/right). No absolute
positioning — blocks never overlap and content flows naturally onto the next page.
"""

from frappe.utils import cint

# Editor sheet width (A4 content area at 96 dpi, inside ~15mm margins).
PAGE_WIDTH = 794
CONTENT_WIDTH = 680

DOCUMENT_CSS = """
* { box-sizing: border-box; }
body { margin: 0; font-family: Arial, Helvetica, sans-serif; font-size: 11pt; color: #000; line-height: 1.5; }
.dg-doc { width: 100%; }
.dg-block { margin-bottom: 10px; }
.dg-signature-block { page-break-inside: avoid; margin-top: 24px; }
.dg-block img { max-width: 100%; }
.dg-field-table { width: 100%; border-collapse: collapse; }
.dg-field-table td { padding: 4px 8px; border: 1px solid #000; vertical-align: top; }
.dg-field-table .dg-ft-label { font-weight: bold; width: 45%; }
.dg-data-table { width: 100%; border-collapse: collapse; }
.dg-data-table th, .dg-data-table td { padding: 4px 8px; border: 1px solid #000; text-align: left; }
.dg-data-table th { background: #f2f2f2; }
"""

_ALIGN_TEXT = {"Left": "left", "Center": "center", "Right": "right"}


def block_style(section):
	"""Inline style for a flow block: width percent + alignment."""
	w = cint(section.get("width_pct")) or 100
	align = section.get("align") or "Left"
	ta = _ALIGN_TEXT.get(align, "left")
	style = f"width:{w}%;text-align:{ta};"
	if align == "Center":
		style += "margin-left:auto;margin-right:auto;"
	elif align == "Right":
		style += "margin-left:auto;"
	return style


def assemble_sections(sections):
	"""Concatenate enabled section dicts (in idx order) into a flowing HTML body."""
	enabled = [s for s in sections if cint(s.get("enabled"))]
	enabled.sort(key=lambda s: cint(s.get("idx")))
	return "".join(
		f'<div class="dg-block dg-{(s.get("section_type") or "").lower().replace(" ", "-")}" '
		f'style="{block_style(s)}">{s.get("content") or ""}</div>'
		for s in enabled
	)


def build_document(sections):
	"""Assemble enabled sections into a full, self-contained flowing HTML page."""
	return wrap_document(f'<div class="dg-doc">{assemble_sections(sections)}</div>')


def wrap_document(body_html):
	return (
		'<!DOCTYPE html><html><head><meta charset="UTF-8">'
		f"<style>{DOCUMENT_CSS}</style></head>"
		f"<body>{body_html}</body></html>"
	)
