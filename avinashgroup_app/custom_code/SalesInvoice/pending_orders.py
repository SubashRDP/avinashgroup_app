"""Sales Orders still waiting for an invoice — the data behind the billing nudges.

Customers order through the portal, but billing staff kept typing Sales
Invoices by hand instead of pulling them from the order. Three desk nudges
point them at the order instead, and all read from here:

- public/js/sales_invoice_pending_orders.js — the pending-orders popup when a
  customer is picked on a draft invoice, and the swipe-in drawer: on the
  invoice form (that invoice's company) and on the Sales Invoice / Sales Order
  list, report and dashboard views and the Selling / Accounting workspaces
  (every company the user may read, with a per-company filter).
- public/js/sales_order_alerts.js — the chat-style card a Sales Person gets
  when an order arrives (pushed live by customer_notifications.py), and the
  catch-up of cards they missed while offline (get_order_alerts).

"Pending" is exactly what ERPNext's own Get Items From > Sales Order offers:
submitted, not Closed / On Hold / Completed, billed under 99.99 %. Mapping an
order onto an invoice is still erpnext's make_sales_invoice; nothing here
writes a document.
"""

import frappe
from frappe.utils import cint, flt

from avinashgroup_app.custom_code.CBMS.utils import bs_date_str


def _pending_filters(company=None, customer=None):
	filters = {
		"docstatus": 1,
		"status": ["not in", ["Closed", "On Hold", "Completed"]],
		"per_billed": ["<", 99.99],
	}
	if company:
		filters["company"] = company
	if customer:
		filters["customer"] = customer
	return filters


@frappe.whitelist()
def get_pending_orders(company=None, customer=None, txt=None, limit=50, with_companies=False):
	"""Pending orders, newest first — of one company, or of every company the
	user may read when none is given (optionally one customer, a search text).

	get_list keeps the user's Sales Order read permissions in force, User
	Permissions on Company included, so the rows, the count and the per-company
	breakdown are only what this user could open anyway.

	with_companies adds [{company, abbr, count}] over all their companies
	(ignoring `company`, so the filter chips keep their numbers when one is
	picked).
	"""
	filters = _pending_filters(company, customer)
	or_filters = None
	if txt:
		like = ["like", f"%{txt}%"]
		or_filters = {"name": like, "customer_name": like, "customer": like}

	fields = ["name", "company", "customer", "customer_name", "transaction_date", "grand_total",
		"currency", "per_billed", "total_qty"]
	# custom_remarks is the customer's note from the portal; not on every site
	has_remarks = frappe.db.has_column("Sales Order", "custom_remarks")
	if has_remarks:
		fields.append("custom_remarks")

	orders = frappe.get_list(
		"Sales Order",
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		order_by="transaction_date desc, creation desc",
		page_length=cint(limit) or 50,
	)
	for o in orders:
		o.miti = bs_date_str(o.transaction_date) if o.transaction_date else ""
		o.grand_total = flt(o.grand_total)
		o.per_billed = flt(o.per_billed)
		o.total_qty = flt(o.total_qty)
		o.remarks = (o.pop("custom_remarks", None) or "") if has_remarks else ""

	abbr = dict(frappe.get_all("Company", fields=["name", "abbr"], as_list=True))
	for o in orders:
		o.company_abbr = abbr.get(o.company) or o.company

	count = len(frappe.get_list(
		"Sales Order", filters=filters, or_filters=or_filters, pluck="name", page_length=0,
	))
	out = {"count": count, "orders": orders}

	if cint(with_companies):
		per_company = {}
		for c in frappe.get_list(
			"Sales Order",
			filters=_pending_filters(None, customer),
			or_filters=or_filters,
			pluck="company",
			page_length=0,
		):
			per_company[c] = per_company.get(c, 0) + 1
		out["companies"] = [
			{"company": c, "abbr": abbr.get(c) or c, "count": n}
			for c, n in sorted(per_company.items(), key=lambda kv: -kv[1])
		]
	return out


@frappe.whitelist()
def get_order_alerts(limit=5):
	"""New-order cards this user has not dealt with yet.

	The live push only reaches a browser that is open. Anyone who was offline
	gets the same cards on their next desk load: their unread Notification
	Logs on Sales Orders that are still waiting for an invoice. Opening or
	dismissing a card marks its log read, so it does not come back.
	"""
	logs = frappe.get_all(
		"Notification Log",
		filters={"for_user": frappe.session.user, "read": 0, "document_type": "Sales Order"},
		fields=["name", "document_name", "creation"],
		order_by="creation desc",
		limit=cint(limit) or 5,
	)
	if not logs:
		return []

	names = [l.document_name for l in logs]
	orders = {
		o.name: o
		for o in frappe.get_all(
			"Sales Order",
			filters={**_pending_filters(), "name": ["in", names]},
			fields=["name", "customer", "customer_name", "company", "grand_total", "currency"],
		)
	}

	alerts = []
	for log in logs:
		o = orders.get(log.document_name)
		if o:
			alerts.append(order_alert_payload(o, log.name, log.creation))
	return alerts


def order_alert_payload(order, notification, when=None):
	"""The fields an alert card shows. Also the realtime message body."""
	return {
		"notification": notification,
		"name": order.name,
		"customer": order.customer,
		"customer_name": order.get("customer_name") or order.customer,
		"company": order.company,
		"grand_total": flt(order.grand_total),
		"currency": order.get("currency"),
		"when": str(when or frappe.utils.now_datetime()),
	}
