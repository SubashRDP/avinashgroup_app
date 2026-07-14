# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Render a print format to PDF with headless Chrome instead of wkhtmltopdf.

Why this exists
---------------
The Nepal Gas continuous-form invoices are an *overlay*: every element is
absolutely positioned in millimetres so that it lands inside a box that is
already printed on the carbonless roll. That only works if 1 CSS mm becomes
1 mm of paper.

Frappe renders PDFs with wkhtmltopdf. The build shipped by Ubuntu
(`wkhtmltopdf 0.12.6-2build2`) is compiled against *unpatched* Qt, which makes
WebKit's "smart shrinking" impossible to turn off -- it prints

    The switch --disable-smart-shrinking, is not support using unpatched qt,
    and will be ignored.

and then renders every length at 0.7688x. Measured on this box: a 100mm bar
comes out 76.88mm whether it is declared in mm, px, pt or in, on A4, Letter or
a custom page, and neither --zoom nor --dpi nor --disable-smart-shrinking moves
it. The form ends up shrunk into the top-left corner of a correctly sized page.

Chrome honours `@page { size: ... }` and renders mm exactly (measured: 1.0004x,
0.12mm offset over a 241.3mm page), so these formats go through Chrome. Any
other print format is untouched and still uses wkhtmltopdf.

Wiring (hooks.py)
-----------------
    pdf_generator = ["...printing.chrome_pdf.render"]
    override_whitelisted_methods = {
        "frappe.utils.print_format.download_pdf": "...printing.chrome_pdf.download_pdf",
    }

`frappe.utils.print_utils.get_print` calls every `pdf_generator` hook when
`pdf_generator != "wkhtmltopdf"`; a hook returns the PDF if it recognises the
generator name, else None so the next hook (finally wkhtmltopdf) gets a turn.
"""

import os
import re
import shutil
import subprocess
import tempfile

import frappe

#: Formats that cannot tolerate wkhtmltopdf's 0.7688x shrink.
CHROME_PRINT_FORMATS = {
	"Nepal Gas Invoice Pre-Printed",
	"Nepal Gas Invoice Plain Paper",
	"Nepal Gas Invoice A4 Proof",
	"Nepal Gas Invoice A4 Portrait",
	"Avinash Invoice Pre-Printed",
}

_CHROME_BINARIES = ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser")

_TIMEOUT = 60  # seconds


def find_chrome() -> str | None:
	# Explicit wins: lets a server without root (or with chrome-headless-shell
	# in a home directory) declare the binary in site_config/common_site_config,
	# e.g. "chrome_path": "/home/frappe/bin/google-chrome". Needed because web
	# workers under supervisor inherit a bare PATH that misses user dirs.
	# ("chrome_binary" is accepted as an alias.)
	configured = frappe.conf.get("chrome_path") or frappe.conf.get("chrome_binary")
	if configured and os.access(configured, os.X_OK):
		return configured
	for name in _CHROME_BINARIES:
		path = shutil.which(name)
		if path:
			return path
	return None


def _localise_assets(html: str) -> str:
	"""Rewrite site-absolute asset URLs to file:// so Chrome can load them offline.

	The page is handed to Chrome as a file:// URL, so `/assets/...` would resolve
	against the filesystem root. Chrome allows file:// subresources from a
	file:// document, so pointing them at the real paths keeps the cascade intact
	without needing the web server to be up.
	"""
	sites = os.path.abspath(frappe.local.sites_path)
	public = os.path.abspath(frappe.get_site_path("public"))
	private = os.path.abspath(frappe.get_site_path("private"))

	html = re.sub(r'(href|src)="(/assets/[^"]*)"', lambda m: f'{m.group(1)}="file://{sites}{m.group(2)}"', html)
	html = re.sub(r'(href|src)="/files/([^"]*)"', lambda m: f'{m.group(1)}="file://{public}/files/{m.group(2)}"', html)
	html = re.sub(
		r'(href|src)="/private/files/([^"]*)"',
		lambda m: f'{m.group(1)}="file://{private}/files/{m.group(2)}"',
		html,
	)
	return html


def _strip_screen_chrome(html: str) -> str:
	"""Drop printview's on-screen furniture.

	The Print / Get PDF banner is hidden by `.print-hide` in print.bundle.css. We
	remove it outright rather than rely on that stylesheet resolving, and we drop
	the inline <script> since Chrome runs with JS enabled.
	"""
	html = re.sub(r'<div class="action-banner.*?</div>', "", html, flags=re.S)
	html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S)
	return html


def render(print_format=None, html=None, options=None, output=None, pdf_generator=None, **kwargs):
	"""`pdf_generator` hook. Returns PDF bytes, or None to fall through."""
	if pdf_generator != "chrome":
		return None

	binary = find_chrome()
	if not binary:
		frappe.log_error(
			"Chrome/Chromium not found on the server; falling back to wkhtmltopdf, "
			"which renders these formats at 0.7688x. Install google-chrome-stable.",
			"chrome_pdf",
		)
		return None

	html = _localise_assets(_strip_screen_chrome(html or ""))

	workdir = tempfile.mkdtemp(prefix="ngi-pdf-")
	src = os.path.join(workdir, "print.html")
	dst = os.path.join(workdir, "print.pdf")
	try:
		with open(src, "w", encoding="utf-8") as f:
			f.write(html)

		cmd = [
			binary,
			"--headless",
			"--disable-gpu",
			f"--user-data-dir={os.path.join(workdir, 'profile')}",
			"--no-pdf-header-footer",
			"--run-all-compositor-stages-before-draw",
			"--virtual-time-budget=10000",
			f"--print-to-pdf={dst}",
			f"file://{src}",
		]
		if os.geteuid() == 0:
			# Chrome's sandbox refuses to start as root.
			cmd.insert(1, "--no-sandbox")

		proc = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT)
		if proc.returncode != 0 or not os.path.exists(dst):
			frappe.log_error(
				f"chrome exited {proc.returncode}\n{proc.stderr.decode('utf-8', 'replace')[:2000]}",
				"chrome_pdf",
			)
			return None

		with open(dst, "rb") as f:
			pdf = f.read()
	except subprocess.TimeoutExpired:
		frappe.log_error(f"chrome timed out after {_TIMEOUT}s", "chrome_pdf")
		return None
	finally:
		shutil.rmtree(workdir, ignore_errors=True)

	if output:
		import io

		from pypdf import PdfReader

		output.append_pages_from_reader(PdfReader(io.BytesIO(pdf)))
		return output

	return pdf


@frappe.whitelist()
def download_pdf(
	doctype: str,
	name: str,
	format=None,
	doc=None,
	no_letterhead=0,
	language=None,
	letterhead=None,
	pdf_generator=None,
):
	"""Override of `frappe.utils.print_format.download_pdf`.

	Forces the Chrome generator for the continuous-form invoices so that "Get
	PDF" and the desk PDF button produce an mm-exact 241.3x139.7mm page. Every
	other format keeps Frappe's default behaviour.
	"""
	from frappe.utils.print_format import download_pdf as frappe_download_pdf

	if not pdf_generator and format in CHROME_PRINT_FORMATS and find_chrome():
		pdf_generator = "chrome"

	return frappe_download_pdf(
		doctype=doctype,
		name=name,
		format=format,
		doc=doc,
		no_letterhead=no_letterhead,
		language=language,
		letterhead=letterhead,
		pdf_generator=pdf_generator,
	)
