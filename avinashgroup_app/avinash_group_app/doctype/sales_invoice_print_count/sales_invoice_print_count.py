# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from avinashgroup_app.utils.fiscal_year_utils import fiscal_year_for_date


class SalesInvoicePrintCount(Document):
	def validate(self):
		# branch_name, company and fiscal_year mirror the invoice, so none of them
		# is ever typed in by hand.
		row = (
			frappe.db.get_value(
				"Sales Invoice",
				self.sales_invoice,
				["custom_branch_name", "company", "posting_date"],
				as_dict=True,
			)
			or {}
		)
		self.branch_name = row.get("custom_branch_name") or ""
		self.company = row.get("company") or ""
		self.fiscal_year = fiscal_year_for_date(row.get("posting_date"))

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
