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

Deliberately NOT touched:
- Selling. Sales Invoice keeps ERPNext's normal rounding.
- net_amount after a HEADER discount (apply_discount_amount spreads the
  discount across rows with ERPNext's own rounding; it runs after this).
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


class TruncateItemAmounts:
	"""Mixin for the buying controllers in Override/overrides.py.

	Replaces AccountsController.calculate_taxes_and_totals, whose only other
	work (commission / contribution) is selling-only."""

	def calculate_taxes_and_totals(self):
		TruncatingTaxesAndTotals(self)
