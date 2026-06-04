# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestDocumentTemplate(FrappeTestCase):
	def _new_template(self, **overrides):
		doc = frappe.new_doc("Document Template")
		doc.template_name = overrides.get("template_name", "_Test DG Template")
		doc.body_html = overrides.get("body_html", "<p>Hello {{ company }}</p>")
		return doc

	def test_valid_template_saves(self):
		doc = self._new_template(template_name="_Test DG Valid")
		doc.insert()
		self.assertTrue(doc.name)
		frappe.delete_doc("Document Template", doc.name, force=True)

	def test_invalid_jinja_is_rejected(self):
		doc = self._new_template(body_html="<p>{{ unclosed </p>")
		self.assertRaises(Exception, doc.insert)
