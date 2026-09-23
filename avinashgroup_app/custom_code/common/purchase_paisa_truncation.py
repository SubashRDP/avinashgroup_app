"""Buying-side money derived FROM the line amount is CUT to 2 decimals, never rounded.

The purchase team's rule, stated 2026-09-23:
- The line amount (rate x qty) rounds exactly as Sales Invoice does — stock
  ERPNext, flt(rate * qty, 2). 120.15700 x 1 = 120.16.
- Everything computed from it after that drops the paisa beyond the second
  decimal: VAT 13%, TDS %, Excise %, and each row's share of a header
  discount. 120.16 x 13% = 15.6208 -> 15.62; 88.50 x 13% = 11.505 -> 11.50
  (not the 11.51 a half-up round gives).
- Sums need nothing: they add values that are already 2 dp.

Truncation is toward zero, so a return line (-11.505) becomes -11.50, the
mirror of the bill it reverses.

Where each cut lives:
- VAT / TDS / Excise lines: purchase_taxes_handler (server) and
  purchase_taxes_common.js (form preview), both via `truncate` below.
- Header-discount shares: TruncatingTaxesAndTotals.apply_discount_amount here,
  wired into Purchase Invoice / Order / Receipt and Supplier Quotation through
  the classes in custom_code/Override/overrides.py; the form preview is
  public/js/purchase_paisa_truncation.js.

Deliberately NOT touched:
- The line amount itself (see above) and anything on the selling side.
- ERPNext's own base-currency conversions.
"""

from decimal import ROUND_DOWN, Decimal

from frappe.utils import flt

from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

# A percentage of a 2 dp amount is exact well inside 9 dp; rounding the float
# product there first strips binary noise such as 0.29 * 100 = 28.999999999999996,
# which a bare truncation would wrongly cut to 28.99.
FLOAT_NOISE_PRECISION = 9


def truncate(value, precision):
	"""Cut `value` to `precision` decimals toward zero (11.505 -> 11.5, -11.505 -> -11.5)."""
	cleaned = Decimal(str(flt(value, FLOAT_NOISE_PRECISION)))
	return float(cleaned.quantize(Decimal(1).scaleb(-int(precision)), rounding=ROUND_DOWN))


class TruncatingTaxesAndTotals(calculate_taxes_and_totals):
	def apply_discount_amount(self):
		"""Spread a header discount with every row's net_amount CUT, not rounded.

		ERPNext rounds each row's share and pushes the leftover paisa onto rows so
		they foot exactly to (total - discount). Cutting every row leaves the sum
		a few paisa short, so the LAST row takes that remainder — the rows must
		still foot to the net total ERPNext settled on. Then totals and taxes are
		recomputed from the re-spread rows."""
		spread = self._discount_spread_inputs()
		super().apply_discount_amount()
		if not spread or not self.discount_amount_applied:
			return

		discount, total_for_discount, rows = spread
		target = sum(flt(item.net_amount) for item, _ in rows)
		cut = [
			truncate(before - discount * before / total_for_discount, item.precision("net_amount"))
			for item, before in rows
		]
		last_item = rows[-1][0]
		cut[-1] = flt(target - sum(cut[:-1]), last_item.precision("net_amount"))
		if all(flt(item.net_amount) == value for (item, _), value in zip(rows, cut)):
			return

		conversion_rate = flt(self.doc.conversion_rate) or 1
		for (item, before), net_amount in zip(rows, cut):
			item.net_amount = net_amount
			item.distributed_discount_amount = flt(
				before - net_amount, item.precision("distributed_discount_amount")
			)
			item.net_rate = flt(net_amount / item.qty, item.precision("net_rate")) if item.qty else 0
			item.base_net_amount = truncate(net_amount * conversion_rate, item.precision("base_net_amount"))
			self._set_in_company_currency(item, ["net_rate"])
		self._calculate()

	def _discount_spread_inputs(self):
		"""(discount, total_for_discount, [(item, net_amount before discount)]) when
		ERPNext is about to spread a header discount across rows, else None."""
		doc = self.doc
		if not flt(doc.discount_amount) or not self._items:
			return None
		if doc.apply_discount_on == "Grand Total" and doc.get("is_cash_or_non_trade_discount"):
			return None
		total_for_discount = self.get_total_for_discount_amount()
		if not total_for_discount:
			return None
		return flt(doc.discount_amount), total_for_discount, [(i, flt(i.net_amount)) for i in self._items]


class CutDiscountShares:
	"""Mixin for the buying controllers in Override/overrides.py.

	Replaces AccountsController.calculate_taxes_and_totals, whose only other
	work (commission / contribution) is selling-only."""

	def calculate_taxes_and_totals(self):
		TruncatingTaxesAndTotals(self)
