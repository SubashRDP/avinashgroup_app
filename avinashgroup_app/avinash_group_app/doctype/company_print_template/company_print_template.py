# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Per-company print templates.

One record per Document Type (the record IS the doctype — autoname
field:document_type), holding a child row per company:

    company -> Print Format [, Return Print Format] [, Print on Submit]

Return Print Format is used when the document has is_return set (Sales
Invoice returns / credit notes, Purchase Invoice debit notes, return
Delivery Notes ...); when blank, returns use the normal Print Format.

The desk consults the enabled rules (public/js/company_print.js) to:

  1. default the Print view's format to the company's template instead of
     the doctype-wide default, and
  2. when "Print on Submit" is on, open that print automatically in a new
     tab the moment the document is submitted.

`get_print_templates` below serves the child rows FLATTENED to one rule per
(document_type, company) — the client never needs to know about the
parent/child shape. Cached in redis; any change to a record invalidates it.
Each rule carries its formats' `pdf_generator` so the client can route
chrome formats (the mm-exact NGI overlays) through download_pdf instead of
the browser-print /printview path — same distinction ngi_print.js makes.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

CACHE_KEY = "company_print_templates"

_FORMAT_FIELDS = ("print_format", "return_print_format")


class CompanyPrintTemplate(Document):
	def validate(self):
		seen = set()
		for row in self.companies:
			if row.company in seen:
				frappe.throw(
					_("Row #{0}: {1} appears more than once").format(
						row.idx, frappe.bold(row.company)
					)
				)
			seen.add(row.company)
			self.validate_row_formats(row)

	def validate_row_formats(self, row):
		for fieldname in _FORMAT_FIELDS:
			print_format = row.get(fieldname)
			if not print_format:
				continue
			target = frappe.db.get_value("Print Format", print_format, "doc_type")
			if target and target != self.document_type:
				frappe.throw(
					_("Row #{0}: Print Format {1} belongs to {2}, not {3}").format(
						row.idx,
						frappe.bold(print_format),
						frappe.bold(target),
						frappe.bold(self.document_type),
					)
				)

	def on_update(self):
		clear_company_print_template_cache()

	def on_trash(self):
		clear_company_print_template_cache()


def clear_company_print_template_cache():
	# Delete now AND after commit: a request racing the save could rebuild the
	# cache from pre-commit data, resurrecting the old rules permanently. The
	# realtime event then tells every open desk to re-fetch (company_print.js).
	frappe.cache().delete_value(CACHE_KEY)
	frappe.db.after_commit.add(lambda: frappe.cache().delete_value(CACHE_KEY))
	frappe.publish_realtime("company_print_templates_updated", after_commit=True)


@frappe.whitelist()
def get_print_templates():
	"""All enabled rules flattened to one per (document_type, company), with
	each Print Format's pdf_generator. Desk-wide config, cached."""

	def build():
		enabled = frappe.get_all("Company Print Template", filters={"enabled": 1}, pluck="name")
		if not enabled:
			return []

		# parent == document_type (autoname field:document_type)
		rules = frappe.get_all(
			"Company Print Template Company",
			filters={"parenttype": "Company Print Template", "parent": ("in", enabled)},
			fields=["parent as document_type", "company", "print_format", "return_print_format", "print_on_submit"],
			order_by="parent, idx",
		)

		formats = {r[f] for r in rules for f in _FORMAT_FIELDS if r[f]}
		generators = {}
		raw_flags = {}
		if formats:
			meta_rows = frappe.get_all(
				"Print Format",
				filters={"name": ("in", list(formats))},
				fields=["name", "pdf_generator", "raw_printing"],
			)
			generators = {m.name: m.pdf_generator for m in meta_rows}
			raw_flags = {m.name: cint(m.raw_printing) for m in meta_rows}
		for r in rules:
			r["pdf_generator"] = generators.get(r.print_format) or "wkhtmltopdf"
			r["raw_printing"] = raw_flags.get(r.print_format, 0)
			r["return_pdf_generator"] = (
				generators.get(r.return_print_format) or "wkhtmltopdf"
				if r.return_print_format
				else None
			)
			r["return_raw_printing"] = raw_flags.get(r.return_print_format, 0)
		return rules

	return frappe.cache().get_value(CACHE_KEY, build)
