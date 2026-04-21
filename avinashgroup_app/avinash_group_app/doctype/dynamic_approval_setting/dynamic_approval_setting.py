# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class DynamicApprovalSetting(Document):
	def autoname(self):
		abbr = frappe.db.get_value("Company", self.company, "abbr") or self.company
		self.name = f"{self.document_type}-{abbr}-{frappe.generate_hash(length=6)}"

	def validate(self):
		# Validate that each criteria row has a non-empty field_name and field_value
		for row in (self.match_criteria or []):
			if not row.field_name or not row.field_value:
				frappe.throw(_("Match Criteria row {0}: Field Name and Field Value are required.").format(row.idx))

	def on_update(self):
		pass

	def on_trash(self):
		pass
