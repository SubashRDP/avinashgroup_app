# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Render a single template section to HTML against a Jinja context.

Used at *instantiation* time only: the resulting HTML is copied into the editable
Generated Document, after which it is plain HTML and is never re-evaluated as Jinja.
"""

import json

import frappe
from frappe import _
from markupsafe import escape


def render_section(section, context):
	"""Render one section (a dict-like with section_type/content/config_json).

	Returns an HTML string wrapped in a ``dg-section`` div.
	"""
	section_type = section.get("section_type")
	handler = _HANDLERS.get(section_type)
	if not handler:
		frappe.throw(_("Unknown section type: {0}").format(section_type))

	inner = handler(section, context)
	css_type = (section_type or "").lower().replace(" ", "-")
	return f'<div class="dg-section dg-{css_type}">{inner}</div>'


def _render_jinja(section, context):
	content = section.get("content") or ""
	return frappe.render_template(content, context) if content else ""


def _render_letter_head(section, context):
	content = section.get("content")
	if content:
		return frappe.render_template(content, context)
	return context.get("letter_head_html") or ""


def _render_field_table(section, context):
	rows = _load_config(section, expect=list)
	cells = []
	for row in rows:
		label = escape(row.get("label") or "")
		value_expr = row.get("value_expr") or ""
		value = frappe.render_template("{{ " + value_expr + " }}", context) if value_expr else ""
		cells.append(
			f'<tr><td class="dg-ft-label">{label}</td>'
			f'<td class="dg-ft-value">{value}</td></tr>'
		)
	return '<table class="dg-field-table">' + "".join(cells) + "</table>"


def _render_data_table(section, context):
	config = _load_config(section, expect=dict)
	columns = config.get("columns") or []
	rows = _resolve_path(context, config.get("source") or "")
	if not isinstance(rows, (list, tuple)):
		rows = []

	head = "".join(f"<th>{escape(c.get('label') or '')}</th>" for c in columns)
	body = []
	for row in rows:
		getter = row.get if hasattr(row, "get") else (lambda k, _r=row: getattr(_r, k, ""))
		tds = "".join(f"<td>{escape(str(getter(c.get('key'), '') or ''))}</td>" for c in columns)
		body.append(f"<tr>{tds}</tr>")
	return (
		'<table class="dg-data-table"><thead><tr>'
		+ head
		+ "</tr></thead><tbody>"
		+ "".join(body)
		+ "</tbody></table>"
	)


def _render_spacer(section, context):
	config = _load_config(section, expect=dict, default={})
	height = frappe.utils.cint(config.get("height_mm")) or 10
	return f'<div style="height:{height}mm"></div>'


def _load_config(section, expect, default=None):
	raw = section.get("config_json")
	if not raw:
		return default if default is not None else (expect())
	try:
		parsed = json.loads(raw)
	except (ValueError, TypeError):
		frappe.throw(_("Section {0}: Config (JSON) is not valid JSON.").format(section.get("section_title")))
	if not isinstance(parsed, expect):
		frappe.throw(
			_("Section {0}: Config (JSON) must be a {1}.").format(
				section.get("section_title"), expect.__name__
			)
		)
	return parsed


def _resolve_path(context, path):
	"""Resolve a dotted path like ``data.rows`` against the context."""
	value = context
	for part in path.split("."):
		if not part:
			continue
		if hasattr(value, "get"):
			value = value.get(part)
		else:
			value = getattr(value, part, None)
		if value is None:
			return None
	return value


_HANDLERS = {
	"Rich Text": _render_jinja,
	"Letter Head": _render_letter_head,
	"Signature Block": _render_jinja,
	"Image": _render_jinja,
	"Field Table": _render_field_table,
	"Data Table": _render_data_table,
	"Spacer": _render_spacer,
}
