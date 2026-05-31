import frappe
from frappe import _
from frappe.utils import flt

from erpnext.controllers.stock_controller import StockController

# Apply the engine patch so zero-rate rows survive reposts of backdated entries.
from .engine_patch import apply_patch as _apply_engine_patch

_apply_engine_patch()


class StockAdjustment(StockController):
	def validate(self):
		if not self.items:
			frappe.throw(_("Add at least one item"))
		for row in self.items:
			if flt(row.adjustment_qty) <= 0:
				frappe.throw(
					_("Row #{0}: Adjustment Qty must be greater than zero").format(row.idx)
				)
			if flt(row.rate) != 0:
				frappe.throw(
					_(
						"Row #{0}: Rate must be 0. Stock Adjustment is a quantity-only "
						"correction; use Stock Entry for value-bearing movements."
					).format(row.idx)
				)

	def on_submit(self):
		self.update_stock_ledger()
		self.repost_future_sle_and_gle()

	def on_cancel(self):
		self.ignore_linked_doctypes = (
			"Stock Ledger Entry",
			"Repost Item Valuation",
		)
		self.update_stock_ledger()
		self.repost_future_sle_and_gle()

	def update_stock_ledger(self):
		sign = 1 if self.adjustment_type == "Gain" else -1
		sl_entries = [self._sl_entry(row, sign) for row in self.items]
		if sl_entries:
			allow_negative = frappe.db.get_single_value("Stock Settings", "allow_negative_stock")
			self.make_sl_entries(sl_entries, allow_negative_stock=allow_negative)

	def _sl_entry(self, row, sign):
		return frappe._dict({
			"item_code": row.item_code,
			"warehouse": row.warehouse,
			"posting_date": self.posting_date,
			"posting_time": self.posting_time,
			"voucher_type": self.doctype,
			"voucher_no": self.name,
			"voucher_detail_no": row.name,
			"actual_qty": sign * flt(row.adjustment_qty),
			"incoming_rate": 0,
			"company": self.company,
			"stock_uom": frappe.get_cached_value("Item", row.item_code, "stock_uom"),
			"is_cancelled": 1 if self.docstatus == 2 else 0,
			"allow_zero_valuation_rate": 1,
			"is_adjustment_entry": 1,
		})
