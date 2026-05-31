"""Engine-level patch that makes Stock Adjustment rows entered at rate=0
behave as quantity-only ("measurement") adjustments — preserving the
warehouse's stock_value and posting stock_value_difference=0 on every pass,
including reposts triggered by backdated entries.

Why a patch is needed
---------------------
ERPNext's standard valuation engine (FIFO / Moving Average / Batched)
ALWAYS values outgoing stock at its actual cost; it does not honour a
"declare value of outgoing line" intent. On submit we can post-process the
SLE, but any subsequent backdated Stock Entry / Purchase Invoice / Sales
Invoice will queue a Repost Item Valuation, and the repost recomputes
stock_value_difference from the warehouse's real cost and re-posts the
GL entries we tried to suppress.

To survive reposts we have to intercept the engine itself. We monkey-patch
`update_entries_after.process_sle` (the per-SLE workhorse) so that
zero-rate Stock Adjustment SLEs use our preservation math at the same
point in the flow where the engine's own math would otherwise run. This
keeps `wh_data` (the engine's running state) consistent so downstream
SLEs see the correct baseline.

Safety
------
- The patch only branches when voucher_type == "Stock Adjustment" AND the
  referenced row's `rate` is exactly 0. All other vouchers fall through
  to the original engine unchanged.
- `apply_patch()` is idempotent and re-binds the patched method on each
  call; no risk of double-wrapping.
- A short request-scoped cache avoids repeated DB lookups when a single
  repost walks the SLE multiple times.
"""

import json

import frappe
from frappe.utils import cint, flt, now

from erpnext.stock.stock_ledger import update_entries_after as _UEA


# Will be set to the original method on first apply_patch().
_original_process_sle = None


def _get_row_rate(voucher_detail_no):
	"""Look up the Stock Adjustment Item row's rate. Cached per-request."""
	if not voucher_detail_no:
		return None
	cache = getattr(frappe.local, "_stock_adj_row_rate_cache", None)
	if cache is None:
		cache = {}
		frappe.local._stock_adj_row_rate_cache = cache
	if voucher_detail_no in cache:
		return cache[voucher_detail_no]
	rate = frappe.db.get_value("Stock Adjustment Item", voucher_detail_no, "rate")
	cache[voucher_detail_no] = rate
	return rate


def _is_zero_rate_stock_adjustment(sle):
	"""True if this SLE belongs to a Stock Adjustment row recorded at rate=0."""
	if not sle:
		return False
	if sle.get("voucher_type") != "Stock Adjustment":
		return False
	if not sle.get("voucher_detail_no"):
		return False
	# Skip serial / batch / dimension-bound lines — those keep their native engine path.
	if sle.get("serial_and_batch_bundle") or sle.get("serial_no") or sle.get("batch_no"):
		return False
	rate = _get_row_rate(sle.get("voucher_detail_no"))
	if rate is None:
		return False
	return flt(rate) == 0


def _patched_process_sle(self, sle):
	"""Wrapper around update_entries_after.process_sle.

	For zero-rate Stock Adjustment lines: preserve wh_data.stock_value
	(no monetary change), update qty, recompute valuation_rate, and write
	to the SLE. Skip the standard FIFO/MA dispatch entirely.

	For everything else: delegate to the original engine.
	"""
	if not _is_zero_rate_stock_adjustment(sle):
		return _original_process_sle(self, sle)

	# Mirror the housekeeping the original method does up-front.
	self.wh_data = self.data[sle.warehouse]
	self.validate_previous_sle_qty(sle)
	self.affected_transactions.add((sle.voucher_type, sle.voucher_no))

	# Honour the negative-stock guard — without it the user could quietly
	# drive a warehouse negative through a zero-rate Loss.
	if not cint(self.allow_negative_stock):
		if not self.validate_negative_stock(sle):
			self.wh_data.qty_after_transaction += flt(sle.actual_qty)
			return

	# Our preservation math:
	#   stock_value stays where it was (whatever the prior SLE left it at)
	#   qty changes by actual_qty
	#   valuation_rate = stock_value / new qty
	self.wh_data.qty_after_transaction += flt(sle.actual_qty)
	qty_after = flt(self.wh_data.qty_after_transaction, self.flt_precision)

	# Round the preserved stock_value to the currency precision, matching
	# what the original method does at the end of its dispatch.
	self.wh_data.stock_value = flt(self.wh_data.stock_value, self.currency_precision)
	if qty_after == 0:
		# Bin going to zero — value follows the engine's standard rule.
		self.wh_data.stock_value = 0.0
		self.wh_data.valuation_rate = 0
	else:
		self.wh_data.valuation_rate = self.wh_data.stock_value / qty_after

	# Compute sv_diff exactly the way the engine does, then update prev.
	stock_value_difference = self.wh_data.stock_value - self.wh_data.prev_stock_value
	self.wh_data.prev_stock_value = self.wh_data.stock_value

	# Write back to the SLE in the same shape the original method uses.
	sle.qty_after_transaction = qty_after
	sle.valuation_rate = self.wh_data.valuation_rate
	sle.stock_value = self.wh_data.stock_value
	sle.stock_queue = json.dumps(self.wh_data.stock_queue)
	sle.stock_value_difference = stock_value_difference  # = 0 by construction

	sle.doctype = "Stock Ledger Entry"
	sle.modified = now()
	frappe.get_doc(sle).db_update()


def apply_patch():
	"""Replace update_entries_after.process_sle with our wrapper.
	Idempotent: re-binds the same wrapper on each call.
	"""
	global _original_process_sle
	if _original_process_sle is None:
		_original_process_sle = _UEA.process_sle
	_UEA.process_sle = _patched_process_sle
