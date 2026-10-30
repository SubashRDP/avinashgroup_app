"""Cross-check the rates on a draft Sales Invoice against today's Item Price.

A rate on an invoice row is fetched once, when the item or UOM is picked, and
then never again: a form left open across a price change, an invoice made from
a Delivery Note, or a draft saved yesterday all keep the old price, and nothing
on the screen says so.

This only REPORTS. It returns the rows whose rate is not today's price and
sales_invoice_rate_check.js shows them above the Items table. It never changes
a rate and never blocks a save; a rate typed on purpose is the user's call.

"Today's price" is the same lookup the Sales Order -> Sales Invoice repricing
uses (so_latest_rate.current_price), so the two always agree.
"""

import frappe
from frappe.utils import flt

from avinashgroup_app.custom_code.SalesInvoice.so_latest_rate import RATE_CHANGE_TOLERANCE, current_price


@frappe.whitelist()
def check_rates(doc):
	"""Compare each row's rate with today's Item Price, after the row's discount %.

	doc: the Sales Invoice as the form holds it (JSON string or dict).

	Returns {"checked": rows compared, "mismatched": [...], "unpriced": [...]}.
	Each mismatched entry has idx, item_name, uom, rate and price; unpriced lists
	the rows whose item has no Item Price in this price list (nothing to compare).
	"""
	doc = frappe._dict(frappe.parse_json(doc))
	result = {"checked": 0, "mismatched": [], "unpriced": []}

	# A return carries the original invoice's rate on purpose.
	if doc.get("is_return") or not doc.get("selling_price_list"):
		return result

	for row in doc.get("items") or []:
		row = frappe._dict(row)
		if not row.item_code or row.get("is_free_item"):
			continue

		price = current_price(doc, row)
		if not price:
			result["unpriced"].append({"idx": row.idx, "item_name": row.item_name or row.item_code, "uom": row.uom})
			continue

		result["checked"] += 1
		expected = flt(price) * (1 - flt(row.discount_percentage) / 100)
		if abs(flt(row.rate) - expected) >= RATE_CHANGE_TOLERANCE:
			result["mismatched"].append({
				"idx": row.idx,
				"item_name": row.item_name or row.item_code,
				"uom": row.uom,
				"rate": flt(row.rate),
				"price": expected,
			})

	return result
