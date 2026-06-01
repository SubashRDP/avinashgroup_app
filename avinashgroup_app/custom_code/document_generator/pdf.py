# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Shared wkhtmltopdf helper.

Extracted from the Party Ledger report so both that report and the Document
Generator use a single, consistent PDF pipeline (A4, page-numbered footer).

Page numbers use wkhtmltopdf's NATIVE text footer (``--footer-center`` with the
``[page]``/``[topage]`` substitutions) rather than ``--footer-html``. The HTML
footer triggers a second JavaScript WebKit render that segfaults (exit -11) in the
headless/forked web-worker process, so the text footer is far more robust.
"""

from frappe.utils.pdf import get_pdf

_DEFAULT_MARGINS = {
	"margin-top": "15mm",
	"margin-right": "15mm",
	"margin-bottom": "15mm",
	"margin-left": "15mm",
}

_ZERO_MARGINS = {
	"margin-top": "0mm",
	"margin-right": "0mm",
	"margin-bottom": "0mm",
	"margin-left": "0mm",
}


def build_pdf(html, orientation="Portrait", margins=None, footer=True):
	"""Render HTML to PDF bytes.

	orientation: "Portrait" or "Landscape".
	margins: optional dict overriding the default 15mm margins.
	footer: include the "Page x/y" text footer (uses page margin space).
	"""
	options = {
		"page-size": "A4",
		"orientation": orientation or "Portrait",
		"encoding": "UTF-8",
		"enable-local-file-access": None,
	}
	if footer:
		options.update(
			{
				"footer-center": "Page [page] of [topage]",
				"footer-font-size": "8",
				"footer-font-name": "Arial",
				"footer-spacing": "2",
			}
		)
	options.update(margins or _DEFAULT_MARGINS)
	return get_pdf(html, options)


def build_canvas_pdf(html, orientation="Portrait"):
	"""PDF for the absolute-layout canvas: zero margins, no footer, so the 794px
	page maps 1:1 onto A4 (210mm = 794px @ 96 dpi)."""
	return build_pdf(html, orientation=orientation, margins=_ZERO_MARGINS, footer=False)
