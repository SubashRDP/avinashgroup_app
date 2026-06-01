# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestGeneratedDocument(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = frappe.db.get_value("Company", {}, "name")
		if frappe.db.exists("Document Template", "_Test GD Template"):
			cls.template = "_Test GD Template"
			return
		tpl = frappe.new_doc("Document Template")
		tpl.template_name = "_Test GD Template"
		tpl.target_doctype = "Customer"
		tpl.data_provider = "Single Record"
		tpl.company = company
		tpl.append(
			"sections",
			{"section_title": "Body", "section_type": "Rich Text", "content": "<p>x</p>"},
		)
		tpl.insert(ignore_permissions=True)
		cls.template = tpl.name

	def _new_doc(self, **overrides):
		doc = frappe.new_doc("Generated Document")
		doc.title = overrides.get("title", "_Test Generated Document")
		doc.template = self.template
		doc.data_provider = "Single Record"
		doc.append(
			"working_sections",
			{
				"section_title": "Body",
				"section_type": "Rich Text",
				"content": overrides.get("content", "<p>Hello world</p>"),
				"enabled": 1,
			},
		)
		return doc

	def test_rendered_html_is_populated_on_save(self):
		doc = self._new_doc()
		doc.insert(ignore_permissions=True)
		self.assertIn("Hello world", doc.rendered_html)
		self.assertIn("<!DOCTYPE html>", doc.rendered_html)
		frappe.delete_doc("Generated Document", doc.name, force=True)

	def test_section_html_is_sanitized(self):
		doc = self._new_doc(content='<p>safe</p><script>alert("x")</script>')
		doc.insert(ignore_permissions=True)
		self.assertNotIn("<script>", doc.working_sections[0].content)
		frappe.delete_doc("Generated Document", doc.name, force=True)

	def test_sent_status_requires_recipients(self):
		doc = self._new_doc()
		doc.status = "Sent"
		self.assertRaises(frappe.ValidationError, doc.insert)
