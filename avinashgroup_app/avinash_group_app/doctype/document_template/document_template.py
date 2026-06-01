# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class DocumentTemplate(Document):
	def validate(self):
		self.validate_sections()
		self.validate_party_type()
		self.validate_companies()
		self.validate_jinja()

	def validate_sections(self):
		if not self.sections:
			frappe.throw(_("Add at least one section to the template."))

	def validate_party_type(self):
		if self.data_provider == "Party Balance Confirmation" and not self.party_type:
			frappe.throw(_("Party Type is required for the Party Balance Confirmation data provider."))

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
		"""Dry-render each Jinja section against a permissive stub to catch syntax
		errors early (without needing the real data, which only exists at generation)."""
		from avinashgroup_app.custom_code.document_generator.providers import stub_context

		stub = stub_context()
		if self.companies:
			stub["company"] = self.companies[0].company
		for row in self.sections:
			if row.section_type in ("Rich Text", "Letter Head", "Signature Block") and row.content:
				try:
					frappe.render_template(row.content, stub)
				except Exception as e:
					frappe.throw(
						_("Section {0} ({1}) has an invalid template: {2}").format(
							row.idx, row.section_title, str(e)
						)
					)
