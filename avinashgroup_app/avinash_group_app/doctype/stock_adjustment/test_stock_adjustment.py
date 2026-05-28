import frappe
from frappe.tests.utils import FrappeTestCase


class TestStockAdjustment(FrappeTestCase):
	def setUp(self):
		"""Set up test fixtures"""
		# Use existing company and warehouse from avinas1
		self.company = "Nepal Gas Udhyog (Karnali) Pvt. Ltd."

		# Get first warehouse for this company
		wh = frappe.db.get_value("Warehouse", {"company": self.company}, "name")
		self.warehouse = wh or "Main Store"

		# Use existing item - find one that exists
		existing_item = frappe.db.get_value("Item", {"is_stock_item": 1}, "name")
		self.item_code = existing_item or "NGK-ITEM-00008"

	def test_stock_adjustment_gain(self):
		"""Test creating a stock adjustment with GAIN"""
		gva = frappe.new_doc("Stock Adjustment")
		gva.posting_date = frappe.utils.nowdate()
		gva.adjustment_type = "Gain"
		gva.reason = "Temperature fluctuation - test"
		gva.company = self.company

		gva.append("items", {
			"item_code": self.item_code,
			"warehouse": self.warehouse,
			"adjustment_qty": 10.0,
		})

		gva.insert()
		gva.submit()

		# Verify stock entry was created
		self.assertEqual(gva.items[0].stock_entry, None)  # Will be set by on_submit
		# Re-fetch to get updated value
		gva.reload()
		self.assertIsNotNone(gva.items[0].stock_entry)

		# Verify Stock Entry type
		se = frappe.get_doc("Stock Entry", gva.items[0].stock_entry)
		self.assertEqual(se.stock_entry_type, "Material Receipt")
		self.assertEqual(se.remarks, "Gas Volume Adjustment (Gain) - Temperature fluctuation - test")

	def test_stock_adjustment_loss(self):
		"""Test creating a stock adjustment with LOSS"""
		gva = frappe.new_doc("Stock Adjustment")
		gva.posting_date = frappe.utils.nowdate()
		gva.adjustment_type = "Loss"
		gva.reason = "Evaporation - test"
		gva.company = self.company

		gva.append("items", {
			"item_code": "NGK-ITEM-00008",
			"warehouse": self.warehouse,
			"adjustment_qty": 5.0,
		})

		gva.insert()
		gva.submit()

		# Verify stock entry was created
		gva.reload()
		self.assertIsNotNone(gva.items[0].stock_entry)

		# Verify Stock Entry type
		se = frappe.get_doc("Stock Entry", gva.items[0].stock_entry)
		self.assertEqual(se.stock_entry_type, "Material Issue")

	def test_stock_adjustment_multiple_items(self):
		"""Test creating adjustment with multiple items"""
		gva = frappe.new_doc("Stock Adjustment")
		gva.posting_date = frappe.utils.nowdate()
		gva.adjustment_type = "Gain"
		gva.reason = "Calibration - test"
		gva.company = self.company

		# Add multiple items
		gva.append("items", {
			"item_code": "NGK-ITEM-00008",
			"warehouse": self.warehouse,
			"adjustment_qty": 10.0,
		})

		gva.insert()
		gva.submit()

		# Verify Stock Entries were created for each item
		gva.reload()
		for item_row in gva.items:
			self.assertIsNotNone(item_row.stock_entry)
			se = frappe.get_doc("Stock Entry", item_row.stock_entry)
			self.assertEqual(se.docstatus, 1)  # Submitted
