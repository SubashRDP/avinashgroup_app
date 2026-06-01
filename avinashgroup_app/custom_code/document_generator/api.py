# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Whitelisted endpoints for the Document Generator page.

Flow: get_matching_templates -> instantiate_document -> (user edits) ->
render_html (live preview) -> save_generated_document -> download_document_pdf /
send_document_email.
"""

import json

import frappe
from frappe import _

from avinashgroup_app.custom_code.document_generator import providers
from avinashgroup_app.custom_code.document_generator.pdf import build_pdf
from avinashgroup_app.custom_code.document_generator.sections import render_section
from avinashgroup_app.custom_code.document_generator.styles import build_document


def _loads(value, default=None):
	"""Accept either a JSON string (from the client) or an already-parsed value."""
	if value is None or value == "":
		return default
	if isinstance(value, str):
		return json.loads(value)
	return value


@frappe.whitelist()
def get_matching_templates(target_doctype=None, company=None):
	"""Active templates for the given target doctype / company (for the selector)."""
	filters = {"is_active": 1}
	if target_doctype:
		filters["target_doctype"] = target_doctype
	templates = frappe.get_all(
		"Document Template",
		filters=filters,
		fields=["name", "template_name", "target_doctype", "data_provider", "party_type"],
		order_by="template_name asc",
	)
	if not company:
		return templates
	# Keep templates scoped to this company, or scoped to all companies (empty list).
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
	"""Selector metadata for a template (provider, target doctype, party type, companies)."""
	tpl = frappe.db.get_value(
		"Document Template",
		template,
		["data_provider", "target_doctype", "party_type"],
		as_dict=True,
	)
	if not tpl:
		frappe.throw(_("Template not found: {0}").format(template))
	tpl["companies"] = _template_companies(template)
	tpl["inputs"] = frappe.get_all(
		"Document Template Input",
		filters={"parent": template, "parenttype": "Document Template"},
		fields=["fieldname", "label", "input_type", "options", "reqd"],
		order_by="idx asc",
	)
	return tpl


@frappe.whitelist()
def instantiate_document(template, payload):
	"""Build a working (unsaved) document from a template + a generation payload.

	Renders each template section's Jinja against the data context so placeholders
	become real text, then returns editable working sections.
	"""
	payload = _loads(payload, {}) or {}
	tpl = frappe.get_doc("Document Template", template)
	tpl.check_permission("read")

	# Fill provider inputs the template already knows about.
	payload.setdefault("target_doctype", tpl.target_doctype)
	if tpl.party_type:
		payload.setdefault("party_type", tpl.party_type)
	# Company: explicit choice from the page, else the only configured company.
	if not payload.get("company"):
		companies = [c.company for c in tpl.companies]
		if len(companies) == 1:
			payload["company"] = companies[0]

	if tpl.data_provider == "Custom Data Sources":
		context = providers.build_custom_context(tpl, payload)
	else:
		context = providers.build_context(tpl.data_provider, payload)
	context["letter_head_html"] = _letter_head_html(tpl.letter_head, context)

	working_sections = []
	for idx, section in enumerate(tpl.sections, start=1):
		working_sections.append(
			{
				"section_title": section.section_title,
				"section_type": section.section_type,
				"content": render_section(section.as_dict(), context),
				"enabled": section.default_enabled,
				"is_locked": section.is_mandatory,
				"align": section.align or "Left",
				"width_pct": section.width_pct or "100",
				"idx": idx,
			}
		)

	return {
		"template": tpl.name,
		"target_doctype": tpl.target_doctype,
		"company": payload.get("company"),
		"data_provider": tpl.data_provider,
		"print_orientation": tpl.print_orientation or "Portrait",
		"payload": payload,
		"reference_name": _reference_name(tpl, payload),
		"party": payload.get("party"),
		"title": _suggested_title(tpl, payload),
		"working_sections": working_sections,
	}


@frappe.whitelist()
def render_html(working_sections):
	"""Assemble enabled working sections (already-resolved HTML) into a full document.

	Used by the live preview and reused by PDF/email generation. The section content
	is treated as HTML and is NOT re-evaluated as Jinja.
	"""
	sections = _loads(working_sections, []) or []
	return build_document(sections)


@frappe.whitelist()
def get_template_for_design(template):
	"""Load a template's sections for the visual (boxy) layout designer.

	Text sections return their raw content (so the admin sees/edits the
	``{{ placeholders }}``); table/spacer sections return a stub-rendered preview
	so they can be positioned, while their ``config_json`` is preserved untouched.
	"""
	tpl = frappe.get_doc("Document Template", template)
	tpl.check_permission("write")

	stub = providers.stub_context()

	text_types = ("Rich Text", "Letter Head", "Signature Block")
	sections = []
	for idx, s in enumerate(tpl.sections, start=1):
		if s.section_type in text_types:
			display = s.content or ""
		else:
			try:
				display = render_section(s.as_dict(), stub)
			except Exception:
				display = f"<i>{s.section_type}</i>"

		sections.append(
			{
				"section_title": s.section_title,
				"section_type": s.section_type,
				"content": s.content or "",
				"config_json": s.config_json or "",
				"display_content": display,
				"enabled": s.default_enabled,
				"is_locked": s.is_mandatory,
				"align": s.align or "Left",
				"width_pct": s.width_pct or "100",
				"idx": idx,
			}
		)

	return {"template": tpl.name, "template_name": tpl.template_name, "sections": sections}


@frappe.whitelist()
def save_template_layout(template, sections):
	"""Persist the boxy designer's layout + content back onto the template's sections."""
	tpl = frappe.get_doc("Document Template", template)
	tpl.check_permission("write")
	sections = _loads(sections, []) or []

	tpl.set("sections", [])
	for i, s in enumerate(sections, start=1):
		tpl.append(
			"sections",
			{
				"section_title": s.get("section_title"),
				"section_type": s.get("section_type"),
				"content": s.get("content"),
				"config_json": s.get("config_json"),
				"default_enabled": s.get("enabled"),
				"is_mandatory": s.get("is_locked"),
				"align": s.get("align") or "Left",
				"width_pct": s.get("width_pct") or "100",
				"idx": i,
			},
		)
	tpl.save()
	return {"template": tpl.name}


@frappe.whitelist()
def get_generated_document(name):
	"""Load a saved Generated Document back into the editor's working state."""
	doc = frappe.get_doc("Generated Document", name)
	doc.check_permission("read")
	return {
		"name": doc.name,
		"template": doc.template,
		"target_doctype": doc.target_doctype,
		"company": doc.company,
		"data_provider": doc.data_provider,
		"print_orientation": doc.print_orientation or "Portrait",
		"payload": _loads(doc.payload, {}),
		"reference_name": doc.reference_name,
		"party": doc.party,
		"title": doc.title,
		"recipients": doc.recipients,
		"working_sections": [
			{
				"section_title": s.section_title,
				"section_type": s.section_type,
				"content": s.content,
				"enabled": s.enabled,
				"is_locked": s.is_locked,
				"align": s.align or "Left",
				"width_pct": s.width_pct or "100",
			}
			for s in doc.working_sections
		],
	}


@frappe.whitelist()
def save_generated_document(data):
	"""Create or update a Generated Document from the editor's working state.

	``data`` (JSON): {name?, template, target_doctype, company, reference_name, party,
	data_provider, payload, title, status, working_sections: [...]}
	Returns the saved document name.
	"""
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
	doc.party = data.get("party")
	doc.data_provider = data.get("data_provider")
	doc.print_orientation = data.get("print_orientation") or "Portrait"
	doc.payload = frappe.as_json(data.get("payload") or {})
	doc.recipients = data.get("recipients")
	if data.get("status"):
		doc.status = data.get("status")

	doc.set("working_sections", [])
	for idx, section in enumerate(data.get("working_sections") or [], start=1):
		doc.append(
			"working_sections",
			{
				"section_title": section.get("section_title"),
				"section_type": section.get("section_type"),
				"content": section.get("content"),
				"enabled": section.get("enabled"),
				"is_locked": section.get("is_locked"),
				"align": section.get("align") or "Left",
				"width_pct": section.get("width_pct") or "100",
				"idx": idx,
			},
		)

	doc.save()
	return {"name": doc.name, "title": doc.title, "status": doc.status}


@frappe.whitelist()
def download_document_pdf(generated_document=None, working_sections=None, title=None, orientation="Portrait"):
	"""Stream a PDF for a saved Generated Document (by name) or ad-hoc working sections.

	Called via ``window.open`` (GET) from the page, so it sets ``frappe.response``.
	"""
	html, doc = _resolve_html(generated_document, working_sections)
	if doc:
		orientation = doc.print_orientation or orientation
		title = title or doc.title

	pdf_bytes = _safe_build_pdf(html, orientation)

	frappe.response.filename = f"{frappe.utils.cstr(title or 'document')}.pdf"
	frappe.response.filecontent = pdf_bytes
	frappe.response.type = "download"


def _safe_build_pdf(html, orientation):
	"""Build the PDF, surfacing a clean error (and a log entry) on wkhtmltopdf failure."""
	try:
		return build_pdf(html, orientation=orientation)
	except Exception:
		frappe.log_error(title="Document Generator PDF failed", message=frappe.get_traceback())
		frappe.throw(_("Could not generate the PDF. The error has been logged."))


@frappe.whitelist()
def send_document_email(generated_document, recipients=None, action="Email"):
	"""Email the generated document's PDF to the resolved recipients.

	Mirrors the app's existing sendmail pattern (async, try/except + log_error).
	"""
	doc = frappe.get_doc("Generated Document", generated_document)
	doc.check_permission("email")

	resolved = _resolve_recipients(doc, recipients)
	if not resolved:
		frappe.throw(_("No recipient email could be resolved. Please enter one explicitly."))

	html = doc.rendered_html or build_document([s.as_dict() for s in doc.working_sections])
	orientation = doc.print_orientation or "Portrait"
	pdf_bytes = _safe_build_pdf(html, orientation)

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
	"""Order: explicit input -> target record field -> party email -> primary contact."""
	if recipients:
		if isinstance(recipients, str):
			recipients = [r.strip() for r in recipients.split(",") if r.strip()]
		if recipients:
			return recipients

	payload = _loads(doc.payload, {}) or {}
	recipient_field = (
		frappe.db.get_value("Document Template", doc.template, "default_recipient_field")
		or "email_id"
	)

	if doc.data_provider == "Party Balance Confirmation" and doc.party:
		party_type = payload.get("party_type")
		email = frappe.db.get_value(party_type, doc.party, recipient_field) if party_type else None
		if not email and party_type:
			email = _primary_contact_email(party_type, doc.party)
		return [email] if email else []

	if doc.target_doctype and doc.reference_name:
		email = frappe.db.get_value(doc.target_doctype, doc.reference_name, recipient_field)
		return [email] if email else []

	return []


def _primary_contact_email(party_type, party):
	contacts = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": party_type, "link_name": party, "parenttype": "Contact"},
		fields=["parent"],
		limit=1,
	)
	if not contacts:
		return None
	return frappe.db.get_value("Contact", contacts[0].parent, "email_id")


def _email_subject(doc):
	subject = frappe.db.get_value("Document Template", doc.template, "email_subject")
	if not subject:
		return frappe.utils.cstr(doc.title)
	try:
		return frappe.render_template(
			subject,
			{"title": doc.title, "company": doc.company, "party": doc.party},
		)
	except Exception:
		return subject


def _resolve_html(generated_document, working_sections):
	"""Return (html, doc_or_None) from either a saved doc name or ad-hoc sections."""
	if generated_document:
		doc = frappe.get_doc("Generated Document", generated_document)
		doc.check_permission("read")
		html = doc.rendered_html or build_document([s.as_dict() for s in doc.working_sections])
		return html, doc
	sections = _loads(working_sections, []) or []
	return build_document(sections), None


def _letter_head_html(letter_head, context):
	if not letter_head:
		return ""
	content = frappe.db.get_value("Letter Head", letter_head, "content") or ""
	return frappe.render_template(content, context) if content else ""


def _reference_name(tpl, payload):
	if tpl.data_provider == "Party Balance Confirmation":
		return f"{payload.get('party')} @ {payload.get('from_date')}..{payload.get('to_date')}"
	if tpl.data_provider == "Custom Data Sources":
		return payload.get("company") or ""
	return payload.get("record_name") or ""


def _suggested_title(tpl, payload):
	ref = _reference_name(tpl, payload)
	return f"{tpl.template_name} - {ref}" if ref else tpl.template_name
