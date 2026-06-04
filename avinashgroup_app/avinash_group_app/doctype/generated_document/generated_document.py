# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class GeneratedDocument(Document):
	def validate(self):
		self.set_title()
		self.validate_recipients_for_send()

	def set_title(self):
		if not self.title:
			self.title = self.template or _("Generated Document")

	def validate_recipients_for_send(self):
		if self.status == "Sent" and not self.recipients:
			frappe.throw(_("Recipients are required before a document can be marked as Sent."))
