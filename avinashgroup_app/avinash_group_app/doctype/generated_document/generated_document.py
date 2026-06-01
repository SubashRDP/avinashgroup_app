# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import sanitize_html

from avinashgroup_app.custom_code.document_generator.styles import build_document


class GeneratedDocument(Document):
	def validate(self):
		self.set_title()
		self.sanitize_sections()
		self.refresh_rendered_html()
		self.validate_recipients_for_send()

	def set_title(self):
		if not self.title:
			self.title = self.template or _("Generated Document")

	def sanitize_sections(self):
		"""User-edited HTML is sanitized on save to avoid stored XSS."""
		for row in self.working_sections or []:
			if row.content:
				row.content = sanitize_html(row.content)

	def refresh_rendered_html(self):
		sections = [row.as_dict() for row in self.working_sections or []]
		self.rendered_html = build_document(sections)

	def validate_recipients_for_send(self):
		if self.status == "Sent" and not self.recipients:
			frappe.throw(_("Recipients are required before a document can be marked as Sent."))
