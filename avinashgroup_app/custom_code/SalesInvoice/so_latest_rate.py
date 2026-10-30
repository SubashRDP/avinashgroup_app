"""Bill a Sales Order at today's price, not the price on the day it was ordered.

Stock ERPNext copies each Sales Order row's rate onto the Sales Invoice. Gas
prices change often: an order taken in the afternoon at 1,800 and invoiced the
next morning, after the price moved to 1,900 overnight, would still bill at
1,800. Here every row that comes from a Sales Order takes the current Item
Price instead (same price list, same UOM, priced on the invoice's posting
date), whether the price went up or down.

- A row whose item has no Item Price in that price list keeps the SO rate.
- A discount % on the SO row is kept and applied to the new price.
- issued_at_updated_rate() tells customer_notifications.py whether to add
  "issued at the updated rate" to the portal's "Invoice raised" notice.

Deliberately narrow: only the rate on SO-mapped rows changes. Saving,
submitting, taxes and every other Sales Invoice rule run exactly as before.

A price RISE makes the invoice row bigger than the SO row, which ERPNext's
over-billing check would block (and nobody knows how big the next government
price change will be, so a % allowance cannot cover it).
overbilled_by_price_update() lets exactly that case through, and nothing else:
quantity within the order, rate not above today's Item Price. Over-billing for
any other reason is still blocked as before.

Wired through override_whitelisted_methods in hooks.py, which covers both the
Sales Order's Create > Sales Invoice button and the Sales Invoice's
Get Items From > Sales Order picker (sales_invoice_so_picker.js).
"""

import frappe
from frappe.utils import flt, nowdate

from erpnext.selling.doctype.sales_order.sales_order import (
	make_sales_invoice as erpnext_make_sales_invoice,
)
from erpnext.stock.get_item_details import get_price_list_rate_for

from avinashgroup_app.custom_code.SalesInvoice.salesinvoice_taxes import before_save_salesinvoice
from avinashgroup_app.utils.site_scope import app_installed

# Smallest rate difference that counts as "the rate changed". Rates are kept to
# 5 decimals here; anything under a paisa is rounding, not a price change.
RATE_CHANGE_TOLERANCE = 0.01


@frappe.whitelist()
def make_sales_invoice(source_name, target_doc=None, ignore_permissions=False, args=None):
	"""Override of erpnext...sales_order.make_sales_invoice: same invoice, latest rates."""
	doc = erpnext_make_sales_invoice(source_name, target_doc, ignore_permissions, args)
	if app_installed():
		apply_latest_rates(doc)
	return doc


def apply_latest_rates(doc):
	"""Reprice the SO-mapped rows of an unsaved Sales Invoice from the current Item Price."""
	price_list = doc.get("selling_price_list")
	if not price_list:
		return

	changed = False

	for item in doc.get("items"):
		if not item.get("so_detail"):
			continue

		latest = current_price(doc, item)
		if not latest:
			continue

		new_rate = flt(latest) * (1 - flt(item.discount_percentage) / 100)
		if abs(new_rate - flt(item.rate)) < RATE_CHANGE_TOLERANCE:
			continue

		item.price_list_rate = flt(latest)
		item.discount_amount = flt(latest) - new_rate
		item.rate = new_rate
		changed = True

	# VAT here is an "Actual" tax row built by this app, which ERPNext's own
	# calculate_taxes_and_totals never recomputes. Run the same two steps that
	# saving runs, in the same order (ERPNext's totals first, they fill the
	# base_net_amount the VAT rebuild reads), so the unsaved form already shows
	# the totals that will post.
	if changed:
		doc.calculate_taxes_and_totals()
		before_save_salesinvoice(doc)


def current_price(doc, item):
	"""Today's Item Price for this invoice row (its price list, UOM and posting
	date), or None when the item has no price in that list."""
	price_list = doc.get("selling_price_list")
	if not price_list:
		return None

	return get_price_list_rate_for(
		{
			"price_list": price_list,
			"customer": doc.get("customer"),
			"uom": item.uom,
			"stock_uom": item.stock_uom,
			"conversion_factor": item.conversion_factor,
			"transaction_date": doc.get("posting_date") or nowdate(),
			"qty": item.qty,
			"batch_no": item.get("batch_no"),
			"price_list_uom_dependant": frappe.get_cached_value(
				"Price List", price_list, "price_list_uom_dependant"
			),
		},
		item.item_code,
	)


def overbilled_by_price_update(doc, so_detail):
	"""True when a Sales Order row is over-billed ONLY because the price went up.

	Called by CustomSalesInvoice.limits_crossed_error when ERPNext's over-billing
	check is about to stop the submit. Both must hold:

	- the quantity billed against the SO row (this invoice + earlier submitted
	  ones) is not more than the quantity ordered, and
	- every row of this invoice for that SO row is at or below today's Item Price.

	Anything else — extra quantity, a rate typed above the price list, an item
	with no Item Price — returns False, and ERPNext blocks it as before.
	"""
	rows = [i for i in doc.get("items") if i.get("so_detail") == so_detail]
	if not rows:
		return False

	ordered_qty = flt(frappe.db.get_value("Sales Order Item", so_detail, "qty"))
	earlier_qty = flt(
		frappe.db.sql(
			"""
			select sum(qty) from `tabSales Invoice Item`
			where so_detail = %s and docstatus = 1 and parent != %s
			""",
			(so_detail, doc.name),
		)[0][0]
	)
	if earlier_qty + sum(flt(i.qty) for i in rows) > ordered_qty:
		return False

	for item in rows:
		latest = current_price(doc, item)
		if not latest or flt(item.rate) > flt(latest) + RATE_CHANGE_TOLERANCE:
			return False

	return True


def issued_at_updated_rate(doc):
	"""True when any row of this Sales Invoice is billed at a different rate than
	the Sales Order row it came from."""
	so_details = [i.so_detail for i in doc.get("items") if i.get("so_detail")]
	if not so_details:
		return False

	so_rates = dict(
		frappe.get_all(
			"Sales Order Item",
			filters={"name": ["in", so_details]},
			fields=["name", "rate"],
			as_list=True,
		)
	)
	return any(
		i.get("so_detail") in so_rates
		and abs(flt(i.rate) - flt(so_rates[i.so_detail])) >= RATE_CHANGE_TOLERANCE
		for i in doc.get("items")
	)
