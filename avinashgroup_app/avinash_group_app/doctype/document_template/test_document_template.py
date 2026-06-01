# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


def _any_company():
	return frappe.db.get_value("Company", {}, "name")


class TestDocumentTemplate(FrappeTestCase):
	def _new_template(self, **overrides):
		doc = frappe.new_doc("Document Template")
		doc.template_name = overrides.get("template_name", "_Test DG Template")
		doc.target_doctype = "Customer"
		doc.data_provider = overrides.get("data_provider", "Single Record")
		doc.company = _any_company()
		doc.append(
			"sections",
			{
				"section_title": "Body",
				"section_type": "Rich Text",
				"content": overrides.get("content", "<p>Hello {{ company }}</p>"),
				"default_enabled": 1,
			},
		)
		return doc

	def test_requires_a_section(self):
		doc = self._new_template()
		doc.sections = []
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_party_provider_requires_party_type(self):
		doc = self._new_template(data_provider="Party Balance Confirmation")
		doc.party_type = None
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_invalid_jinja_is_rejected(self):
		doc = self._new_template(content="<p>{{ unclosed </p>")
		self.assertRaises(Exception, doc.insert)

	def test_valid_template_saves(self):
		doc = self._new_template(template_name="_Test DG Valid")
		doc.insert()
		self.assertTrue(doc.name)
		frappe.delete_doc("Document Template", doc.name, force=True)
