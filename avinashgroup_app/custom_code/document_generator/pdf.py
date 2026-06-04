# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Shared wkhtmltopdf helper.

Uses ``pdfkit`` directly rather than ``frappe.utils.pdf.get_pdf`` because get_pdf
force-overrides ``margin-top``/``margin-bottom`` to 15mm when the HTML has no
``id=header-html``/``id=footer-html`` element. We need exact control of the page
margins (to reserve space for pre-printed letterhead), and pdfkit honours them.
Our HTML is self-contained (data-URI images), so we don't need get_pdf's cookie /
local-image handling.
"""

import pdfkit

_DEFAULT_MARGINS = {
	"margin-top": "15mm",
	"margin-right": "15mm",
	"margin-bottom": "15mm",
	"margin-left": "15mm",
}


def build_pdf(html, orientation="Portrait", margins=None, footer=True):
	"""Render HTML to PDF bytes with exact margins.

	orientation: "Portrait" or "Landscape".
	margins: dict of wkhtmltopdf margin options; defaults to 15mm all round.
	footer: include a "Page x/y" text footer (used by reports, not the letters).
	"""
	options = {
		"page-size": "A4",
		"orientation": orientation or "Portrait",
		"encoding": "UTF-8",
		"enable-local-file-access": "",
		"print-media-type": "",
		"quiet": "",
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
	pdf = pdfkit.from_string(html, False, options=options)
	return pdf if isinstance(pdf, (bytes, bytearray)) else pdf.encode("latin-1")
