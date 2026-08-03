# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SalesInvoicePrintCount(Document):
	def validate(self):
		# branch_name mirrors the invoice, so it is never typed in by hand.
		self.branch_name = (
			frappe.db.get_value("Sales Invoice", self.sales_invoice, "custom_branch_name")
			or ""
		)

	def on_trash(self):
		"""Deleting the counter resets the invoice to "never printed".

		The Print Log rows survive, so the sheets already produced stay on
		record and reconcile_print_counts() can rebuild the count from them.
		"""
		logged = frappe.db.count(
			"Sales Invoice Print Log", {"sales_invoice": self.sales_invoice}
		)
		if logged:
			frappe.msgprint(
				_(
					"The next print of {0} will start again at copy 1, but its {1} logged "
					"sheet(s) remain in Sales Invoice Print Log."
				).format(self.sales_invoice, logged),
				indicator="orange",
				alert=True,
			)
