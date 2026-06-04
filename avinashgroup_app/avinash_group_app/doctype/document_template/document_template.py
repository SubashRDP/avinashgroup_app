# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class DocumentTemplate(Document):
	def validate(self):
		self.validate_companies()
		self.validate_jinja()

	def validate_companies(self):
		"""De-duplicate the company list (empty list = applies to all companies)."""
		seen = set()
		unique_rows = []
		for row in self.companies or []:
			if row.company and row.company not in seen:
				seen.add(row.company)
				unique_rows.append(row)
		self.companies = unique_rows

	def validate_jinja(self):
		"""Dry-render body/header/footer against a permissive stub to catch syntax
		errors early (without needing the real data, which only exists at generation)."""
		from avinashgroup_app.custom_code.document_generator.providers import stub_context

		stub = stub_context()
		if self.companies:
			stub["company"] = self.companies[0].company
		for label, content in (
			(_("body"), self.body_html),
			(_("header"), self.header_html),
			(_("footer"), self.footer_html),
		):
			if not content:
				continue
			try:
				frappe.render_template(content, stub)
			except Exception as e:
				frappe.throw(_("The document {0} has an invalid template: {1}").format(label, str(e)))
