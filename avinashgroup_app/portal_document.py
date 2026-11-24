# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

"""The NG detail page for /orders/<name> and /invoices/<name>.

ERPNext sends every transaction detail route (orders, invoices, purchase orders,
purchase invoices, quotations) to the one endpoint "order". www/order.html wins
that endpoint because this app is installed after erpnext, and:

  * ERPNext's own get_context always runs first, so the document load and the
    has_website_permission refusal are exactly the stock ones.
  * Only Sales Order and Sales Invoice get the NG template. Every other doctype
    extends ERPNext's order.html unchanged.

Amounts are the documents' stored values through get_formatted; nothing is
recalculated except the coupon lines, which use the stock template's formula.
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, formatdate

from erpnext.templates.pages.order import get_context as stock_get_context

from avinashgroup_app.portal_invoices import invoice_miti
from avinashgroup_app.portal_orders import TONES, _miti
from avinashgroup_app.utils.voucher_numbers import resolve as resolve_voucher_numbers

no_cache = 1
sitemap = 0

TEMPLATE = "templates/includes/portal_document.html"
PAGES = {
	"Sales Order": {"list": "/orders", "list_label": "Orders", "kind": "Sales Order"},
	"Sales Invoice": {"list": "/invoices", "list_label": "Invoices", "kind": "Tax Invoice"},
}


def get_context(context):
	stock_get_context(context)
	doc = context.doc
	page = PAGES.get(doc.doctype)
	if not page:
		return

	context.no_cache = 1
	context.no_breadcrumbs = True
	context.portal_document_template = TEMPLATE
	context.list_route = page["list"]
	context.list_label = _(page["list_label"])
	context.kind_label = _(page["kind"]) if doc.doctype == "Sales Order" else _("Invoice")
	context.number = resolve_voucher_numbers([(doc.doctype, doc.name)]).get((doc.doctype, doc.name)) or doc.name
	context.status_label = _(doc.get("indicator_title")) or _(doc.status) or _("Submitted")
	context.tone = TONES.get(doc.get("indicator_color"), "plain")
	context.facts = _facts(doc)
	context.totals = _totals(doc)


def _date(value):
	return formatdate(value, "d MMM yyyy") if value else ""


def _facts(doc):
	if doc.doctype == "Sales Invoice":
		rows = [
			(_("Miti (BS)"), invoice_miti(doc)),
			(_("Posting Date"), _date(doc.posting_date)),
			(_("Due Date"), _date(doc.get("due_date"))),
		]
	else:
		rows = [
			(_("Miti (BS)"), _miti(doc)),
			(_("Order Date"), _date(doc.transaction_date)),
			(_("Delivery Date"), _date(doc.get("delivery_date"))),
		]
	rows.append((_("Customer PO"), doc.get("po_no")))
	return [(label, value) for label, value in rows if value]


def _totals(doc):
	rows = []
	if doc.get("taxes"):
		rows.append((_("Net Total"), doc.get_formatted("net_total"), ""))
	for tax in doc.get("taxes") or []:
		if tax.tax_amount:
			rows.append((tax.description, tax.get_formatted("tax_amount"), ""))

	if doc.doctype == "Sales Order" and doc.get("coupon_code"):
		full = sum(flt(i.price_list_rate) * flt(i.qty) for i in doc.items)
		saved = sum(flt(i.price_list_rate) * flt(i.qty) * flt(i.discount_percentage) / 100 for i in doc.items)
		code = frappe.db.get_value("Coupon Code", doc.coupon_code, "coupon_code")
		rows.append((_("Total Amount"), fmt_money(full, currency=doc.currency), ""))
		rows.append((_("Applied Coupon Code"), code or "", ""))
		rows.append((_("Savings"), fmt_money(saved, currency=doc.currency), ""))

	rows.append((_("Grand Total"), doc.get_formatted("grand_total"), "is-grand"))
	if doc.get("rounded_total") and not doc.is_rounded_total_disabled() and doc.rounded_total != doc.grand_total:
		rows.append((_("Rounded Total"), doc.get_formatted("rounded_total"), "is-grand"))
	if doc.doctype == "Sales Invoice":
		rows.append((_("Outstanding"), doc.get_formatted("outstanding_amount"), "is-due" if doc.outstanding_amount else ""))
	return rows
