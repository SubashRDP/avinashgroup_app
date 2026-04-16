# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class DynamicApprovalSetting(Document):
	def autoname(self):
		abbr = frappe.db.get_value("Company", self.company, "abbr") or self.company
		dept_part = f"-{self.department}" if self.department else ""
		self.name = f"{self.document_type}-{abbr}{dept_part}"

	def validate(self):
		# Ensure unique doctype+company+department combination
		existing = frappe.db.get_value(
			"Dynamic Approval Setting",
			{"document_type": self.document_type, "company": self.company, "department": self.department or "", "name": ("!=", self.name or "")},
			"name",
		)
		if existing:
			frappe.throw(
				_("A Dynamic Approval Setting already exists for {0} + {1} + {2}: {3}").format(
					self.document_type, self.company, self.department or "(any department)", existing
				)
			)
		# Fixed approvers are optional — the approval chain works with user-defined levels alone

	def on_update(self):
		pass

	def on_trash(self):
		pass
