# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

"""The customer portal's Orders page (/orders).

Stock renders /orders through frappe's generic www/list.html, a bare row list
with no date, customer, company or quantity. ERPNext routes /orders to the
endpoint "Sales Order", and TemplatePage is tried before ListPage, so the file
www/Sales Order.html takes the page over without patching either app. Its
same-named .py only re-exports get_context and no_cache from here.

Permissions: every row comes from ERPNext's get_transaction_list, the function
the stock list calls, which forces the customer filter to the session user's
Portal User links. Search only narrows that: it resolves candidate names inside
the same customers, then hands them to get_transaction_list as a filter.

Landmines:
  * Website HTML is cached by path, not user, so no_cache must stay on.
  * The status shown is the billing label from SalesOrder.set_indicator, so the
    filters below select on billing_status, not on the stock workflow status.
  * get_transaction_list sorts by modified desc regardless of its order_by.
"""

import frappe
from frappe import _
from frappe.utils import cint, quoted

from erpnext.controllers.website_list_for_contact import (
	get_customers_suppliers,
	get_transaction_list,
)

from avinashgroup_app.utils.voucher_numbers import resolve as resolve_voucher_numbers, target_fields

no_cache = 1

PAGE_LENGTH = 20
MAX_QUERY_LENGTH = 80
MAX_SEARCH_MATCHES = 500
ITEMS_SHOWN = 2

_RUNNING = ["not in", ["On Hold", "Closed"]]
STATUS_FILTERS = {
	"not_billed": {"billing_status": "Not Billed", "status": _RUNNING},
	"partly_billed": {"billing_status": "Partly Billed", "status": _RUNNING},
	"billed": {"billing_status": "Fully Billed", "status": _RUNNING},
	"on_hold": {"status": "On Hold"},
	"closed": {"status": "Closed"},
}
STATUS_LABELS = (
	("", "All"),
	("not_billed", "Not Billed"),
	("partly_billed", "Partly Billed"),
	("billed", "Billed"),
	("on_hold", "On Hold"),
	("closed", "Closed"),
)
TONES = {"orange": "warn", "yellow": "part", "green": "ok", "red": "stop"}


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/orders"
		raise frappe.Redirect

	# The template is also reachable at its literal path; keep one address.
	if frappe.local.path != "orders":
		frappe.local.flags.redirect_location = "/orders"
		raise frappe.Redirect

	query = _clean_query(frappe.form_dict.get("q"))
	status = _clean_status(frappe.form_dict.get("status"))
	rows, has_more = _load_rows(query, status, 0)

	context.no_cache = 1
	context.show_sidebar = True
	context.no_breadcrumbs = True
	context.title = _("Orders")
	context.query = query
	context.status = status
	context.status_tabs = [{"key": key, "label": _(label)} for key, label in STATUS_LABELS]
	context.rows = rows
	context.has_more = has_more
	context.next_start = PAGE_LENGTH


@frappe.whitelist()
def get_orders(q=None, status=None, start=0):
	"""The next page of order rows, already rendered, for "Load more"."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in"), frappe.PermissionError)

	start = max(cint(start), 0)
	rows, has_more = _load_rows(_clean_query(q), _clean_status(status), start)
	html = "".join(
		frappe.render_template("templates/includes/portal_order_row.html", {"row": row}) for row in rows
	)
	return {"html": html, "has_more": has_more, "next_start": start + PAGE_LENGTH}


def _clean_query(value):
	return (value or "").strip()[:MAX_QUERY_LENGTH]


def _clean_status(value):
	return value if value in STATUS_FILTERS else ""


def _load_rows(query, status, start):
	filters = dict(STATUS_FILTERS.get(status, {}))
	if query:
		names = _matching_names(query)
		if not names:
			return [], False
		filters["name"] = ["in", names]

	docs = get_transaction_list(
		"Sales Order", filters=filters, limit_start=start, limit_page_length=PAGE_LENGTH + 1
	)
	has_more = len(docs) > PAGE_LENGTH
	docs = docs[:PAGE_LENGTH]
	numbers = resolve_voucher_numbers(("Sales Order", doc.name) for doc in docs)
	return [_row(doc, numbers.get(("Sales Order", doc.name))) for doc in docs], has_more


def _matching_names(query):
	"""Orders of the session user's own customers matching number, name, PO or item."""
	customers, _suppliers = get_customers_suppliers("Sales Order", frappe.session.user)
	if not customers:
		return []

	scope = [["customer", "in", customers], ["docstatus", "=", 1]]
	like = f"%{query}%"
	fields = ["name", "customer_name", "po_no"]
	number_field = target_fields().get("Sales Order")
	if number_field and frappe.db.has_column("Sales Order", number_field):
		fields.append(number_field)

	names = set(
		frappe.get_all(
			"Sales Order",
			filters=scope,
			or_filters=[[field, "like", like] for field in fields],
			pluck="name",
			limit=MAX_SEARCH_MATCHES,
			order_by="modified desc",
		)
	)
	names.update(
		frappe.get_all(
			"Sales Order",
			filters=[*scope, ["Sales Order Item", "item_name", "like", like]],
			pluck="name",
			distinct=True,
			limit=MAX_SEARCH_MATCHES,
			order_by="modified desc",
		)
	)
	return list(names)


def _row(doc, number):
	total_field = (
		"grand_total" if doc.is_rounded_total_disabled() or not doc.get("rounded_total") else "rounded_total"
	)
	items, extra, total_qty = _item_summary(doc.items)
	return frappe._dict(
		name=doc.name,
		number=number or doc.name,
		route=f"/orders/{quoted(doc.name)}",
		miti=_miti(doc),
		date=frappe.utils.formatdate(doc.transaction_date, "d MMM yyyy"),
		customer=doc.customer_name or doc.customer,
		company=doc.company,
		items=items,
		extra_items=extra,
		total_qty=total_qty,
		total=doc.get_formatted(total_field),
		status=_(doc.status),
		tone=TONES.get(doc.get("indicator_color"), "plain"),
	)


def _item_summary(items):
	"""[(item name, qty)] for the first few items, how many more, and the total qty."""
	quantities = {}
	for item in items:
		label = item.item_name or item.item_code
		quantities[label] = quantities.get(label, 0) + (item.qty or 0)
	shown = [(label, f"{qty:g}") for label, qty in list(quantities.items())[:ITEMS_SHOWN]]
	return shown, max(len(quantities) - ITEMS_SHOWN, 0), f"{sum(quantities.values()):g}"


def _miti(doc):
	"""The stored BS date where the site has the field, else the converted one."""
	if doc.meta.has_field("custom_miti") and doc.get("custom_miti"):
		return doc.custom_miti
	try:
		from avinashgroup_app.custom_code.CBMS.utils import bs_date_str

		return bs_date_str(doc.transaction_date) or ""
	except Exception:
		return ""
