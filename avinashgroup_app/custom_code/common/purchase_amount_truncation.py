"""Buying-side item amounts are CUT to 2 decimals, never rounded.

Rates on the buying item tables carry 5 decimals (patch
purchase_rate_fields_precision_5). Stock ERPNext then prices each line as
``flt(rate * qty, 2)`` — a normal round — so 120.15700 x 1 lands as 120.16.
The purchase team's rule is that the paisa beyond the second decimal is
dropped: 120.15700 x 1 = 120.15. Truncation is toward zero, so a return line
(-120.157) becomes -120.15, the mirror of the bill it reverses.

What this touches: amount, net_amount and their base_ twins on each item of
Purchase Invoice / Purchase Order / Purchase Receipt / Supplier Quotation, at
the one place ERPNext derives them (calculate_taxes_and_totals ->
calculate_item_values). Totals, VAT (purchase_taxes_handler) and the GL all
follow from those fields, so nothing downstream needs changing.

Also cut, same rule:
- A HEADER discount's per-row share (apply_discount_amount below). The rows
  still foot exactly to the discounted net total, so the last row carries
  the paisa the cuts leave over.
- Line VAT at 13% (purchase_taxes_handler.calculate_item_vat_amounts).

Deliberately NOT touched:
- Selling. Sales Invoice keeps ERPNext's normal rounding.
- Excise and TDS percentage lines — still rounded to paisa.
- Tax rows and grand total — they are sums of already-cut 2 dp amounts.

The browser preview is kept in step by public/js/purchase_amount_truncation.js;
without it the form shows 120.16 until save and 120.15 after.

Wired in through the Purchase* / SupplierQuotation classes in
custom_code/Override/overrides.py (override_doctype_class in hooks.py).
"""

from decimal import ROUND_DOWN, Decimal

from frappe.utils import flt

from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

# rate (5 dp) x qty (up to 9 dp) is exact well inside 9 dp; rounding the float
# product there first strips binary noise such as 0.29 * 100 = 28.999999999999996,
# which a bare truncation would wrongly cut to 28.99.
FLOAT_NOISE_PRECISION = 9


def truncate(value, precision):
	"""Cut `value` to `precision` decimals toward zero (120.157 -> 120.15, -120.157 -> -120.15)."""
	cleaned = Decimal(str(flt(value, FLOAT_NOISE_PRECISION)))
	return float(cleaned.quantize(Decimal(1).scaleb(-int(precision)), rounding=ROUND_DOWN))


class TruncatingTaxesAndTotals(calculate_taxes_and_totals):
	def calculate_item_values(self):
		super().calculate_item_values()
		# Same guards as the parent: consolidated docs and the second pass after a
		# header discount leave item amounts alone.
		if self.doc.get("is_consolidated") or self.discount_amount_applied:
			return

		conversion_rate = flt(self.doc.conversion_rate) or 1
		for item in self.doc.items:
			qty = flt(item.qty)
			# Mirrors the parent's zero-qty credit/debit note cases.
			if not qty and self.doc.get("is_return") and self.doc.doctype != "Purchase Receipt":
				qty = -1
			elif not qty and self.doc.get("is_debit_note"):
				qty = 1

			amount = truncate(flt(item.rate) * qty, item.precision("amount"))
			base_amount = truncate(amount * conversion_rate, item.precision("base_amount"))
			item.amount = item.net_amount = amount
			item.base_amount = item.base_net_amount = base_amount

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


class TruncateItemAmounts:
	"""Mixin for the buying controllers in Override/overrides.py.

	Replaces AccountsController.calculate_taxes_and_totals, whose only other
	work (commission / contribution) is selling-only."""

	def calculate_taxes_and_totals(self):
		TruncatingTaxesAndTotals(self)
