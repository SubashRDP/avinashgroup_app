# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestGeneratedDocument(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Document Template", "_Test GD Template"):
			tpl = frappe.new_doc("Document Template")
			tpl.template_name = "_Test GD Template"
			tpl.body_html = "<p>x</p>"
			tpl.insert(ignore_permissions=True)
		cls.template = "_Test GD Template"

	def _new_doc(self, **overrides):
		doc = frappe.new_doc("Generated Document")
		doc.title = overrides.get("title", "_Test Generated Document")
		doc.template = self.template
		doc.body_html = overrides.get("body_html", "<p>Hello world</p>")
		return doc

	def test_saves_with_body(self):
		doc = self._new_doc()
		doc.insert(ignore_permissions=True)
		self.assertIn("Hello world", doc.body_html)
		frappe.delete_doc("Generated Document", doc.name, force=True)

	def test_sent_status_requires_recipients(self):
		doc = self._new_doc()
		doc.status = "Sent"
		self.assertRaises(frappe.ValidationError, doc.insert)
