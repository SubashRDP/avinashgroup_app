# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Whitelisted endpoints for the Document Generator.

Flow: get_matching_templates -> get_template_meta -> instantiate_document
(renders the template's HTML body with the SQL/Python data) -> (user edits the
document) -> save_generated_document -> download_document_pdf / send_document_email.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import flt

from avinashgroup_app.custom_code.document_generator import providers
from avinashgroup_app.custom_code.document_generator.pdf import build_pdf
from avinashgroup_app.custom_code.document_generator.styles import wrap_document

_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)


def _loads(value, default=None):
	"""Accept either a JSON string (from the client) or an already-parsed value."""
	if value is None or value == "":
		return default
	if isinstance(value, str):
		return json.loads(value)
	return value


def _scrub(html):
	"""Strip <script> tags from user-edited HTML (kept lenient to preserve layout)."""
	return _SCRIPT_RE.sub("", html or "")


# ── Selector ────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_matching_templates(company=None):
	"""Active templates, optionally scoped to a company (for the selector)."""
	templates = frappe.get_all(
		"Document Template",
		filters={"is_active": 1},
		fields=["name", "template_name"],
		order_by="template_name asc",
	)
	if not company:
		return templates
	return [t for t in templates if _template_allows_company(t.name, company)]


def _template_companies(template):
	return frappe.get_all(
		"Document Template Company",
		filters={"parent": template, "parenttype": "Document Template"},
		pluck="company",
	)


def _template_allows_company(template, company):
	companies = _template_companies(template)
	return (not companies) or (company in companies)


@frappe.whitelist()
def get_template_meta(template):
	"""Selector metadata for a template (companies + the inputs the user fills)."""
	tpl = frappe.db.get_value("Document Template", template, ["target_doctype"], as_dict=True)
	if not tpl:
		frappe.throw(_("Template not found: {0}").format(template))
	tpl["companies"] = _template_companies(template)
	tpl["inputs"] = frappe.get_all(
		"Document Template Input",
		filters={"parent": template, "parenttype": "Document Template"},
		fields=["fieldname", "label", "input_type", "options", "reqd", "exclusive_group", "exclusive_set"],
		order_by="idx asc",
	)
	for inp in tpl["inputs"]:
		inp["company_filter_field"] = _company_filter_field(inp)
	return tpl


def _company_filter_field(inp):
	"""For a Link input, return the linked doctype's company field (``company`` or
	``custom_company``) so the selector can scope its options to the chosen company.
	Returns None when the input isn't a company-scoped Link."""
	if inp.get("input_type") != "Link" or not inp.get("options"):
		return None
	try:
		meta = frappe.get_meta(inp["options"])
	except Exception:
		return None
	for field in ("company", "custom_company"):
		if meta.get_field(field):
			return field
	return None


# ── Render ───────────────────────────────────────────────────────────────────────

def _render_hf(tpl, context):
	"""Render the header/footer (template fields, or the linked Letter Head as fallback).
	Returns (header_html, footer_html, header_height, footer_height)."""
	lh_content = lh_footer = ""
	if tpl.letter_head:
		lh = frappe.db.get_value("Letter Head", tpl.letter_head, ["content", "footer"], as_dict=True) or {}
		lh_content, lh_footer = lh.get("content") or "", lh.get("footer") or ""
	header_src = tpl.header_html or lh_content
	footer_src = tpl.footer_html or lh_footer
	header = frappe.render_template(header_src, context) if header_src else ""
	footer = frappe.render_template(footer_src, context) if footer_src else ""
	return header, footer, flt(tpl.header_height) or 25, flt(tpl.footer_height) or 15


@frappe.whitelist()
def instantiate_document(template, payload):
	"""Render the template body with the SQL/Python data and return the editable HTML."""
	payload = _loads(payload, {}) or {}
	tpl = frappe.get_doc("Document Template", template)
	tpl.check_permission("read")

	if not payload.get("company"):
		companies = [c.company for c in tpl.companies]
		if len(companies) == 1:
			payload["company"] = companies[0]

	context = providers.build_custom_context(tpl, payload)
	context["letter_head_html"] = ""
	body = frappe.render_template(tpl.body_html or "", context)
	header, footer, hh, fh = _render_hf(tpl, context)

	return {
		"template": tpl.name,
		"target_doctype": tpl.target_doctype,
		"company": payload.get("company"),
		"print_orientation": tpl.print_orientation or "Portrait",
		"payload": payload,
		"reference_name": payload.get("company") or "",
		"title": _suggested_title(tpl, payload),
		"body_html": body,
		"header_html": header,
		"footer_html": footer,
		"header_height": hh,
		"footer_height": fh,
	}


@frappe.whitelist()
def preview_template(template, payload=None):
	"""Render a template for the admin's Preview — with real data if inputs are passed,
	else with a permissive stub (blank placeholders) so syntax/layout can be checked."""
	tpl = frappe.get_doc("Document Template", template)
	tpl.check_permission("read")
	payload = _loads(payload, None)
	if payload:
		if not payload.get("company"):
			companies = [c.company for c in tpl.companies]
			if len(companies) == 1:
				payload["company"] = companies[0]
		context = providers.build_custom_context(tpl, payload)
	else:
		context = providers.stub_context()
	context["letter_head_html"] = ""
	body = frappe.render_template(tpl.body_html or "", context)
	header, footer, hh, fh = _render_hf(tpl, context)
	return wrap_document(body, header, footer, hh, fh)


@frappe.whitelist()
def render_html(body_html):
	"""Wrap an HTML body into a full document (used for an iframe preview if needed)."""
	return wrap_document(body_html or "")


@frappe.whitelist()
def get_generated_document_html(name):
	"""Fully-wrapped, render-ready HTML (header + body + footer) for a saved Generated
	Document — used for the read-only preview shown on its form."""
	doc = frappe.get_doc("Generated Document", name)
	doc.check_permission("read")
	return wrap_document(
		doc.body_html or "",
		doc.header_html or "",
		doc.footer_html or "",
		doc.header_height,
		doc.footer_height,
	)


_NORMAL_MARGINS = {"margin-top": "15mm", "margin-bottom": "15mm", "margin-left": "15mm", "margin-right": "15mm"}


def _doc_pdf(doc, include_hf=True):
	"""Build the PDF for a Generated Document.

	- Email / digital (include_hf=True): the header is drawn at the top and the footer
	  after the content (normal margins).
	- Print on pre-printed letterhead paper (include_hf=False): header/footer are NOT
	  drawn; instead the page margins reserve the header/footer height as blank space.
	"""
	orientation = doc.print_orientation or "Portrait"
	if include_hf:
		html = wrap_document(
			doc.body_html or "", doc.header_html or "", doc.footer_html or "",
			doc.header_height, doc.footer_height,
		)
		return _safe_build_pdf(html, orientation, _NORMAL_MARGINS, footer=False)

	hh, fh = flt(doc.header_height), flt(doc.footer_height)
	margins = {
		"margin-top": f"{int(hh) if hh else 15}mm",
		"margin-bottom": f"{int(fh) if fh else 15}mm",
		"margin-left": "15mm",
		"margin-right": "15mm",
	}
	return _safe_build_pdf(wrap_document(doc.body_html or ""), orientation, margins, footer=False)


# ── Persistence ─────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_generated_document(name):
	"""Load a saved Generated Document back into the editor."""
	doc = frappe.get_doc("Generated Document", name)
	doc.check_permission("read")
	return {
		"name": doc.name,
		"template": doc.template,
		"target_doctype": doc.target_doctype,
		"company": doc.company,
		"print_orientation": doc.print_orientation or "Portrait",
		"payload": _loads(doc.payload, {}),
		"reference_name": doc.reference_name,
		"title": doc.title,
		"recipients": doc.recipients,
		"body_html": doc.body_html,
		"header_html": doc.header_html,
		"footer_html": doc.footer_html,
		"header_height": doc.header_height,
		"footer_height": doc.footer_height,
	}


@frappe.whitelist()
def save_generated_document(data):
	"""Create or update a Generated Document from the editor's current HTML."""
	data = _loads(data, {}) or {}
	name = data.get("name")

	if name:
		doc = frappe.get_doc("Generated Document", name)
		doc.check_permission("write")
	else:
		doc = frappe.new_doc("Generated Document")

	doc.title = data.get("title")
	doc.template = data.get("template")
	doc.target_doctype = data.get("target_doctype")
	doc.company = data.get("company")
	doc.reference_name = data.get("reference_name")
	doc.print_orientation = data.get("print_orientation") or "Portrait"
	doc.payload = frappe.as_json(data.get("payload") or {})
	doc.recipients = data.get("recipients")
	doc.body_html = _scrub(data.get("body_html"))
	doc.header_html = _scrub(data.get("header_html"))
	doc.footer_html = _scrub(data.get("footer_html"))
	doc.header_height = flt(data.get("header_height")) or 25
	doc.footer_height = flt(data.get("footer_height")) or 15
	if data.get("status"):
		doc.status = data.get("status")

	doc.save()
	return {"name": doc.name, "title": doc.title, "status": doc.status}


# ── Output ───────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def download_document_pdf(generated_document=None, body_html=None, title=None, orientation="Portrait", with_header=0):
	"""Stream a PDF for a saved Generated Document (by name) or ad-hoc HTML.
	Called via ``window.open``/fetch (GET) from the page, so it sets ``frappe.response``.

	with_header=0 (default) is for printing on pre-printed letterhead paper: the
	header/footer space is reserved but their content is not drawn. with_header=1
	draws the header/footer (digital letterhead)."""
	if generated_document:
		doc = frappe.get_doc("Generated Document", generated_document)
		doc.check_permission("read")
		title = title or doc.title
		pdf_bytes = _doc_pdf(doc, include_hf=bool(int(with_header or 0)))
	else:
		pdf_bytes = _safe_build_pdf(wrap_document(body_html or ""), orientation)

	frappe.response.filename = f"{frappe.utils.cstr(title or 'document')}.pdf"
	frappe.response.filecontent = pdf_bytes
	frappe.response.type = "download"


def _safe_build_pdf(html, orientation="Portrait", margins=None, footer=True):
	"""Build the PDF, surfacing a clean error (and a log entry) on wkhtmltopdf failure."""
	try:
		return build_pdf(html, orientation=orientation, margins=margins, footer=footer)
	except Exception:
		frappe.log_error(title="Document Generator PDF failed", message=frappe.get_traceback())
		frappe.throw(_("Could not generate the PDF. The error has been logged."))


@frappe.whitelist()
def send_document_email(generated_document, recipients=None, action="Email"):
	"""Email the generated document's PDF to the resolved recipients."""
	doc = frappe.get_doc("Generated Document", generated_document)
	doc.check_permission("email")

	resolved = _resolve_recipients(doc, recipients)
	if not resolved:
		frappe.throw(_("No recipient email could be resolved. Please enter one explicitly."))

	pdf_bytes = _doc_pdf(doc)
	subject = _email_subject(doc)
	message = _("Please find attached: {0}.").format(frappe.utils.cstr(doc.title))
	filename = f"{frappe.utils.cstr(doc.title or 'document')}.pdf"

	try:
		frappe.sendmail(
			recipients=resolved,
			subject=subject,
			message=message,
			attachments=[{"fname": filename, "fcontent": pdf_bytes}],
			reference_doctype="Generated Document",
			reference_name=doc.name,
			now=False,
		)
		doc.db_set(
			{
				"recipients": ", ".join(resolved),
				"output_action": action,
				"email_status": "Queued",
				"status": "Sent",
				"error": None,
			}
		)
	except Exception:
		error = frappe.get_traceback()
		doc.db_set({"email_status": "Failed", "error": error[:140]})
		frappe.log_error(title="Document Generator email failed", message=error)
		frappe.throw(_("Failed to send email. The error has been logged."))

	return {"name": doc.name, "recipients": ", ".join(resolved), "status": doc.status}


def _resolve_recipients(doc, recipients):
	if recipients:
		if isinstance(recipients, str):
			recipients = [r.strip() for r in recipients.split(",") if r.strip()]
		if recipients:
			return recipients
	recipient_field = (
		frappe.db.get_value("Document Template", doc.template, "default_recipient_field") or "email_id"
	)
	if doc.target_doctype and doc.reference_name:
		email = frappe.db.get_value(doc.target_doctype, doc.reference_name, recipient_field)
		return [email] if email else []
	return []


def _email_subject(doc):
	subject = frappe.db.get_value("Document Template", doc.template, "email_subject")
	if not subject:
		return frappe.utils.cstr(doc.title)
	try:
		return frappe.render_template(subject, {"title": doc.title, "company": doc.company})
	except Exception:
		return subject


def _suggested_title(tpl, payload):
	ref = payload.get("company") or ""
	return f"{tpl.template_name} - {ref}" if ref else tpl.template_name
