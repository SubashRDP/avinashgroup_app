"""Buying-side money lands on 2 decimals rounded HALF-UP: 5 or more goes up.

The purchase team's rule, settled 2026-10-01 (it replaces the 2026-09-23 rule
that cut VAT / TDS / excise / discount shares instead of rounding them):

- Rates carry 5 decimals (patch purchase_rate_fields_precision_5).
- Every amount carries 2, and a third decimal of 5 or more rounds UP:
  - the line amount (rate x qty): 24.025 x 5 = 120.125 -> 120.13;
  - VAT 13%, TDS % and Excise % on a line: 88.50 x 13% = 11.505 -> 11.51;
  - each row's share of a header discount.
- Sums need nothing: they add values that are already 2 dp.

Why this needs code at all: the site's rounding method is Banker's Rounding,
which sends an exact half to whichever neighbour is even — 120.125 -> 120.12
but 120.135 -> 120.14. Stock ERPNext uses it for the line amount and the
discount shares.

Ties go away from zero, so a return line is the mirror of the bill it reverses
(-11.505 -> -11.51).

Where each lives:
- Line amount and header-discount shares on Purchase Invoice / Order / Receipt
  and Supplier Quotation: HalfUpTaxesAndTotals here, reached through the
  classes in custom_code/Override/overrides.py; the form preview is
  public/js/purchase_paisa_rounding.js.
- VAT / TDS / Excise lines on the same four: purchase_taxes_handler (server)
  and purchase_taxes_common.js (form preview), via `round_half_up`.
- Material Request line amount (it has no taxes-and-totals controller):
  round_material_request_amounts here, called from purchase_taxes_handler's
  validate hook; form preview in public/js/material_request.js.
- Request for Quotation carries no rate or amount.

Deliberately NOT touched:
- Anything on the selling side — Sales Invoice keeps the site's rounding method.
- System Settings > Rounding Method: switching it to Commercial Rounding would
  give the same half-up, but for every document on the site.
"""

from decimal import ROUND_HALF_UP, Decimal

from frappe.utils import flt

from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

# rate (5 dp) x qty, or a percentage of a 2 dp amount, is exact well inside
# 9 dp; rounding the float product there first strips binary noise such as
# 24.025 * 5 = 120.12499999999999, which would otherwise round DOWN to 120.12.
FLOAT_NOISE_PRECISION = 9


def round_half_up(value, precision):
	"""Round `value` to `precision` decimals, ties away from zero (11.505 -> 11.51, -11.505 -> -11.51)."""
	cleaned = Decimal(str(flt(value, FLOAT_NOISE_PRECISION)))
	return float(cleaned.quantize(Decimal(1).scaleb(-int(precision)), rounding=ROUND_HALF_UP))


def round_material_request_amounts(doc):
	"""Material Request Item.amount = qty x rate, half-up.

	ERPNext only fills it in the browser, unrounded, so without this the stored
	value keeps every decimal and each screen rounds it its own way."""
	for item in doc.get("items") or []:
		item.amount = round_half_up(flt(item.qty) * flt(item.rate), item.precision("amount"))


class HalfUpTaxesAndTotals(calculate_taxes_and_totals):
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
		"""Spread a header discount with every row's net_amount rounded half-up.

		ERPNext rounds each row's share with Banker's Rounding and pushes the
		leftover paisa onto rows so they foot exactly to (total - discount).
		Here every row but the last is rounded half-up and the LAST row takes
		whatever is left — the rows must still foot to the net total ERPNext
		settled on. Then totals and taxes are recomputed from the re-spread rows."""
		spread = self._discount_spread_inputs()
		super().apply_discount_amount()
		if not spread or not self.discount_amount_applied:
			return

		discount, total_for_discount, rows = spread
		target = sum(flt(item.net_amount) for item, _ in rows)
		shares = [
			round_half_up(before - discount * before / total_for_discount, item.precision("net_amount"))
			for item, before in rows
		]
		last_item = rows[-1][0]
		shares[-1] = flt(target - sum(shares[:-1]), last_item.precision("net_amount"))
		if all(flt(item.net_amount) == value for (item, _), value in zip(rows, shares)):
			return

		conversion_rate = flt(self.doc.conversion_rate) or 1
		for (item, before), net_amount in zip(rows, shares):
			item.net_amount = net_amount
			item.distributed_discount_amount = flt(
				before - net_amount, item.precision("distributed_discount_amount")
			)
			item.net_rate = flt(net_amount / item.qty, item.precision("net_rate")) if item.qty else 0
			item.base_net_amount = round_half_up(
				net_amount * conversion_rate, item.precision("base_net_amount")
			)
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


class HalfUpAmounts:
	"""Mixin for the buying controllers in Override/overrides.py.

	Replaces AccountsController.calculate_taxes_and_totals, whose only other
	work (commission / contribution) is selling-only."""

	def calculate_taxes_and_totals(self):
		HalfUpTaxesAndTotals(self)
