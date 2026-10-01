"""How buying-side money lands on 2 decimals: two rules, one module.

The purchase team's rule, stated 2026-09-23 and revised 2026-10-01:

ROUNDED HALF-UP (a 5 in the third decimal always goes up):
- The line amount (rate x qty). 120.15700 x 1 = 120.16; 24.025 x 5 = 120.125
  -> 120.13. Stock ERPNext uses the site's Banker's Rounding here, which sends
  that tie DOWN to 120.12 (and 120.135 up to 120.14) — the half-paisa went
  whichever way made the second decimal even.
- VAT 13% on a line. 88.50 x 13% = 11.505 -> 11.51; 120.16 x 13% = 15.6208
  -> 15.62. Until 2026-10-01 this was cut (11.50).

CUT (the paisa beyond the second decimal is dropped):
- TDS %, Excise %, and each row's share of a header discount.

Sums need nothing: they add values that are already 2 dp.

Both rules work away from / toward zero symmetrically, so a return line is the
mirror of the bill it reverses (-11.505 -> -11.51 rounded, -11.50 cut).

Where each lives:
- Line amount: TruncatingTaxesAndTotals.calculate_item_values here; form
  preview in public/js/purchase_paisa_truncation.js.
- VAT / TDS / Excise lines: purchase_taxes_handler (server) and
  purchase_taxes_common.js (form preview), via `round_half_up` / `truncate`.
- Header-discount shares: TruncatingTaxesAndTotals.apply_discount_amount here;
  the form preview is public/js/purchase_paisa_truncation.js.
Both overrides reach Purchase Invoice / Order / Receipt and Supplier Quotation
through the classes in custom_code/Override/overrides.py.

Deliberately NOT touched:
- Anything on the selling side — Sales Invoice keeps the site's rounding method.
- System Settings > Rounding Method: switching it to Commercial Rounding would
  give the same half-up, but for every document on the site.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

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


def round_half_up(value, precision):
	"""Round `value` to `precision` decimals, ties away from zero (11.505 -> 11.51, -11.505 -> -11.51)."""
	cleaned = Decimal(str(flt(value, FLOAT_NOISE_PRECISION)))
	return float(cleaned.quantize(Decimal(1).scaleb(-int(precision)), rounding=ROUND_HALF_UP))


class TruncatingTaxesAndTotals(calculate_taxes_and_totals):
	def calculate_item_values(self):
		"""Re-derive each line amount rounded half-up instead of the site's Banker's Rounding."""
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

			amount = round_half_up(flt(item.rate) * qty, item.precision("amount"))
			base_amount = round_half_up(amount * conversion_rate, item.precision("base_amount"))
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


class CutDiscountShares:
	"""Mixin for the buying controllers in Override/overrides.py.

	Replaces AccountsController.calculate_taxes_and_totals, whose only other
	work (commission / contribution) is selling-only."""

	def calculate_taxes_and_totals(self):
		TruncatingTaxesAndTotals(self)
