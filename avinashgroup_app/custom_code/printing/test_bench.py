# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Backing API for the "Overlay Print Test" desk page.

Everything the page shows is discovered from the site it is running on. Nothing
about which formats exist, which form key each passes, or which companies route
to them is written down here — a demo site and a live site legitimately differ,
and a hardcoded list would be wrong on one of them the moment they diverge.

Discovery rule: a print format belongs on the page if its HTML includes the
shared overlay template. That is the same fact that makes it an overlay format,
so a new one appears on the page the moment it is installed, with no edit here.
"""

import os
import re
import subprocess
import tempfile

import frappe

from avinashgroup_app.custom_code.printing.overlay import _FORMS

#: The shared template every overlay format wraps.
TEMPLATE = "avinashgroup_app/templates/print_formats/nepal_gas_invoice_a5_overlay.html"

_FORM_RE = re.compile(r"""set\s+form\s*=\s*['"]([a-z_]+)['"]""")
_PAGE_RE = re.compile(r"""set\s+page\s*=\s*['"]([a-z0-9]+)['"]""")


@frappe.whitelist()
def get_overlay_formats(doctype: str = "Sales Invoice") -> list[dict]:
	"""Overlay print formats installed on THIS site, with what each one is.

	Per format: the `form` key it passes into the shared template, the module
	that holds that roll's calibrated measurements, its pdf_generator, and the
	companies (if any) whose Company Print Template row routes to it.

	`problems` is a list of human-readable warnings — a format that renders
	through wkhtmltopdf, or whose form key has no module, is broken in a way
	worth seeing before you spend a form on it.
	"""
	frappe.has_permission("Print Format", throw=True)

	routing = _routing(doctype)
	out = []

	for r in frappe.get_all(
		"Print Format",
		filters={"doc_type": doctype, "disabled": 0},
		fields=["name", "html", "pdf_generator", "print_format_type"],
	):
		html = r.html or ""
		if TEMPLATE not in html:
			continue

		form = (_FORM_RE.search(html) or [None, None])[1]
		page = (_PAGE_RE.search(html) or [None, None])[1] or "form"
		module = _FORMS.get(form)

		problems = []
		if not form:
			problems.append("no form key in the format HTML — it will fall back to 'ngi'")
		elif not module:
			problems.append(f"form '{form}' is not registered in overlay.py:_FORMS")
		if r.pdf_generator != "chrome":
			problems.append(
				f"pdf_generator is '{r.pdf_generator or 'wkhtmltopdf'}', not 'chrome' — "
				"wkhtmltopdf renders every length at 0.7688x and the form will print shrunk"
			)

		out.append({
			"format": r.name,
			"form": form,
			"module": f"custom_code/printing/{module}.py" if module else None,
			"page": page,
			"pdf_generator": r.pdf_generator,
			"companies": routing.get(r.name, []),
			"problems": problems,
		})

	return sorted(out, key=lambda d: (not d["companies"], d["format"]))


@frappe.whitelist()
def get_sample_invoice(company: str | None = None, doctype: str = "Sales Invoice"):
	"""Latest submitted non-return invoice, so the page opens on something real.

	Returns None on a site with no submitted invoice rather than throwing — an
	empty demo site is a legitimate state.
	"""
	frappe.has_permission(doctype, throw=True)
	filters = {"docstatus": 1, "is_return": 0}
	if company:
		filters["company"] = company
	rows = frappe.get_all(
		doctype, filters=filters, fields=["name", "company"],
		order_by="creation desc", limit=1,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def get_printers() -> dict:
	"""CUPS queues visible to the SERVER, and which one is its default.

	Discovered with `lpstat`, never listed here — the queues differ per machine.
	Note whose printers these are: the server's, not the browser's. On the
	calibration laptop they are the same machine; on a branch PC they are not,
	and that desk should use the PDF button instead.
	"""
	frappe.has_permission("Print Format", throw=True)
	try:
		out = subprocess.run(["lpstat", "-a"], capture_output=True, text=True, timeout=10)
		printers = [ln.split()[0] for ln in out.stdout.splitlines() if ln.strip()]
		d = subprocess.run(["lpstat", "-d"], capture_output=True, text=True, timeout=10)
		m = re.search(r":\s*(\S+)", d.stdout)
		default = m.group(1) if m else None
	except (OSError, subprocess.SubprocessError):
		return {"printers": [], "default": None}
	return {"printers": printers, "default": default if default in printers else None}


def _page_mm(pdf: bytes) -> tuple[float, float]:
	"""Width and height of the PDF's first page, in mm."""
	import io

	from pypdf import PdfReader

	box = PdfReader(io.BytesIO(pdf)).pages[0].mediabox
	return float(box.width) * 25.4 / 72, float(box.height) * 25.4 / 72


def _page_sizes(printer: str) -> list[str]:
	"""The queue's PageSize choices, e.g. ['NGIForm', 'A4', 'Custom.WIDTHxHEIGHT']."""
	try:
		out = subprocess.run(["lpoptions", "-p", printer, "-l"],
		                     capture_output=True, text=True, timeout=10).stdout
	except (OSError, subprocess.SubprocessError):
		return []
	for line in out.splitlines():
		if line.startswith("PageSize"):
			return [c.lstrip("*") for c in line.split(":", 1)[1].split()]
	return []


@frappe.whitelist()
def print_now(name: str, format: str, printer: str | None = None,
              doctype: str = "Sales Invoice") -> dict:
	"""Render the format to PDF and send it to a CUPS queue on the server.

	The point of this over the PDF button is that nothing between here and the
	paper can rescale or turn the page. Three things enforce that, and if any
	cannot be satisfied this REFUSES rather than printing something wrong:

	  media=Custom.<w>x<h>mm  the paper is set to the page's own measured size,
	                          so there is no mismatch for a driver to "fix".
	                          Without this a 241.3mm-wide form sent to an A4
	                          queue either comes out turned a quarter, or — with
	                          scaling forbidden — comes out BLANK.
	  print-scaling=none      no shrink-to-fit. 1mm of CSS stays 1mm of paper.
	  orientation-requested=3 no auto-rotation. Rotation stays OUR decision,
	                          made in the PDF by &rot= where the preview shows
	                          it, instead of a driver guessing.

	A wrong print on a pre-printed form wastes the form and looks like a
	calibration fault, so refusing is always the better failure.

	`ox` / `oy` / `rot` / `guide` are NOT arguments: the template reads them
	straight off `frappe.form_dict`, and they are already there as request
	arguments — the same path the PDF URL uses, so both buttons cannot drift.

	This COUNTS as a print. `trigger_print` is set so `before_print` advances
	the IRD counter and writes a Print Log row, exactly as the PDF button does.
	A print that lands on paper is a print; calibrate on a throwaway invoice.
	"""
	frappe.has_permission(doctype, "print", doc=name, throw=True)

	found = get_printers()
	printer = printer or found["default"]
	if not printer:
		frappe.throw(frappe._("No printer is configured on the server."))
	# never hand an unvalidated name to a subprocess, even without a shell
	if printer not in found["printers"]:
		frappe.throw(frappe._("Unknown printer {0}.").format(printer))

	frappe.local.form_dict.trigger_print = 1
	pdf = frappe.get_print(doctype, name, format, as_pdf=True, pdf_generator="chrome")

	w_mm, h_mm = _page_mm(pdf)
	sizes = _page_sizes(printer)
	if sizes and not any(s.startswith("Custom.") for s in sizes):
		frappe.throw(
			frappe._(
				"{0} cannot be set to {1:.1f} x {2:.1f} mm — it only offers {3}. "
				"Printing anyway would scale or turn the form, so nothing was sent. "
				"Use the PDF button and print it at 100% instead."
			).format(printer, w_mm, h_mm, ", ".join(sizes))
		)
	media = f"Custom.{w_mm:.1f}x{h_mm:.1f}mm"

	fd, path = tempfile.mkstemp(prefix="overlay-print-", suffix=".pdf")
	try:
		with os.fdopen(fd, "wb") as f:
			f.write(pdf)
		res = subprocess.run(
			[
				"lp", "-d", printer,
				# paper == page, so nothing downstream has a mismatch to resolve
				"-o", f"media={media}",
				# never scale: the whole point is 1mm of CSS = 1mm of paper
				"-o", "print-scaling=none",
				# never rotate; see the docstring
				"-o", "orientation-requested=3",
				path,
			],
			capture_output=True, text=True, timeout=60,
		)
		if res.returncode != 0:
			frappe.throw(
				frappe._("lp failed for {0}: {1}").format(printer, res.stderr.strip() or res.returncode)
			)
		job = (re.search(r"request id is (\S+)", res.stdout) or [None, res.stdout.strip()])[1]
		return {"printer": printer, "job": job, "media": media,
		        "page_mm": f"{w_mm:.1f} x {h_mm:.1f}"}
	finally:
		try:
			os.remove(path)
		except OSError:
			pass


def _routing(doctype: str) -> dict[str, list[str]]:
	"""print format -> companies routed to it by Company Print Template.

	Both the normal and the return slot count: either one means a branch reaches
	this format without picking it by hand.
	"""
	if not frappe.db.exists("DocType", "Company Print Template Company"):
		return {}
	out: dict[str, list[str]] = {}
	for row in frappe.get_all(
		"Company Print Template Company",
		filters={"parent": doctype, "parenttype": "Company Print Template"},
		fields=["company", "print_format", "return_print_format"],
	):
		for fmt in (row.print_format, row.return_print_format):
			if fmt and row.company not in out.setdefault(fmt, []):
				out[fmt].append(row.company)
	return out
