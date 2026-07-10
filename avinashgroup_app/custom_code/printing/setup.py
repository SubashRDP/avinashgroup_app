# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Make "chrome" a selectable PDF generator and pin it on the NGI invoice formats.

`frappe.utils.print_utils.get_print` decides the generator by reading the Print
Format's own `pdf_generator` field, so setting it there is what makes *every*
path exact -- not just the "Get PDF" button, but also `attach_print` (emailed
invoices) and `print_by_server` (CUPS). The whitelisted-method override in
chrome_pdf.py stays as a safety net for the interactive paths.

Frappe ships `pdf_generator` as a Select whose only option is "wkhtmltopdf", so
the option list has to be widened with a Property Setter before the field can
legitimately hold "chrome". This runs from `after_migrate`, i.e. after the
standard print formats have been re-imported (an import resets the field to its
default), so it re-asserts the value every migrate. It is idempotent.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from avinashgroup_app.custom_code.printing.chrome_pdf import CHROME_PRINT_FORMATS

_OPTIONS = "wkhtmltopdf\nchrome"


def ensure_chrome_generator():
	existing = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Print Format", "field_name": "pdf_generator", "property": "options"},
		"value",
	)
	if existing != _OPTIONS:
		make_property_setter(
			"Print Format",
			"pdf_generator",
			"options",
			_OPTIONS,
			"Text",
			for_doctype=False,
			validate_fields_for_doctype=False,
		)

	for name in CHROME_PRINT_FORMATS:
		if not frappe.db.exists("Print Format", name):
			continue
		if frappe.db.get_value("Print Format", name, "pdf_generator") != "chrome":
			# db_set, not save(): the format is a standard (file-backed) record.
			frappe.db.set_value("Print Format", name, "pdf_generator", "chrome", update_modified=False)

	frappe.clear_cache(doctype="Print Format")
