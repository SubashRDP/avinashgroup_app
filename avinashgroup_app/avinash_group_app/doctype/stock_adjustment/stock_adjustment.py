import frappe
from frappe.model.document import Document


class StockAdjustment(Document):
	def on_submit(self):
		"""Create Stock Entry for each adjustment item"""
		for row in self.items:
			self._create_stock_entry(row)

	def on_cancel(self):
		"""Cancel linked Stock Entries"""
		for row in self.items:
			if row.stock_entry:
				se = frappe.get_doc("Stock Entry", row.stock_entry)
				if se.docstatus == 1:
					se.cancel()

	def _create_stock_entry(self, item_row):
		"""Create Stock Entry for a single adjustment item"""
		is_gain = self.adjustment_type == "Gain"

		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Receipt" if is_gain else "Material Issue"
		se.company = self.company
		se.posting_date = self.posting_date
		if self.posting_time:
			se.posting_time = self.posting_time
		se.remarks = f"Stock Adjustment ({self.adjustment_type}) - {self.reason}"

		se.append("items", {
			"item_code": item_row.item_code,
			"t_warehouse" if is_gain else "s_warehouse": item_row.warehouse,
			"qty": item_row.adjustment_qty,
			"basic_rate": item_row.rate or 0,
			"allow_zero_valuation_rate": 1,
		})

		se.insert()
		se.submit()

		item_row.db_set("stock_entry", se.name)
