# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

"""The customer portal's Invoices page (/invoices), the sibling of portal_orders.py.

ERPNext routes /invoices to the endpoint "Sales Invoice", so www/Sales Invoice.html
takes the page over without patching either app.

Permissions: every row is loaded by ERPNext's get_transaction_list, which forces
the customer filter to the session user's Portal User links. The queries here only
choose which names to ask it for, always inside those same customers.

Landmines:
  * get_transaction_list sorts by modified desc whatever order_by says, and a bulk
    update gave the demo invoices one identical modified. For a portal customer the
    page is therefore ranked by posting date first, then loaded through it by name.
  * A module of its own: gunicorn workers keep an already-imported portal_orders.
"""

import frappe
from frappe import _
from frappe.utils import cint, quoted
from frappe.utils.user import is_website_user

from erpnext.controllers.website_list_for_contact import (
	get_customers_suppliers,
	get_transaction_list,
)

from avinashgroup_app.portal_orders import TONES, _item_summary
from avinashgroup_app.utils.voucher_numbers import resolve as resolve_voucher_numbers, target_fields

no_cache = 1

DOCTYPE = "Sales Invoice"
PAGE_LENGTH = 20
MAX_QUERY_LENGTH = 80
MAX_SEARCH_MATCHES = 500

STATUS_FILTERS = {
	"unpaid": {"status": ["in", ["Unpaid", "Unpaid and Discounted"]]},
	"overdue": {"status": ["in", ["Overdue", "Overdue and Discounted"]]},
	"partly_paid": {"status": ["in", ["Partly Paid", "Partly Paid and Discounted"]]},
	"paid": {"status": "Paid"},
	"returns": {"status": ["in", ["Return", "Credit Note Issued"]]},
}
STATUS_LABELS = (
	("", "All"),
	("unpaid", "Unpaid"),
	("overdue", "Overdue"),
	("partly_paid", "Partly Paid"),
	("paid", "Paid"),
	("returns", "Returns"),
)


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/invoices"
		raise frappe.Redirect

	# The template is also reachable at its literal path; keep one address.
	if frappe.local.path != "invoices":
		frappe.local.flags.redirect_location = "/invoices"
		raise frappe.Redirect

	query = _clean_query(frappe.form_dict.get("q"))
	status = _clean_status(frappe.form_dict.get("status"))
	rows, has_more = _load_rows(query, status, 0)

	context.no_cache = 1
	context.show_sidebar = True
	context.no_breadcrumbs = True
	context.title = _("Invoices")
	context.query = query
	context.status = status
	context.status_tabs = [{"key": key, "label": _(label)} for key, label in STATUS_LABELS]
	context.rows = rows
	context.has_more = has_more
	context.next_start = PAGE_LENGTH


@frappe.whitelist()
def get_invoices(q=None, status=None, start=0):
	"""The next page of invoice rows, already rendered, for "Load more"."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in"), frappe.PermissionError)

	start = max(cint(start), 0)
	rows, has_more = _load_rows(_clean_query(q), _clean_status(status), start)
	html = "".join(
		frappe.render_template("templates/includes/portal_invoice_row.html", {"row": row}) for row in rows
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

	customers = _portal_customers()
	if customers:
		ranked = frappe.get_all(
			DOCTYPE,
			filters={**filters, "customer": ["in", customers], "docstatus": 1},
			pluck="name",
			order_by="posting_date desc, name desc",
			limit_start=start,
			limit_page_length=PAGE_LENGTH + 1,
		)
		if not ranked:
			return [], False
		has_more = len(ranked) > PAGE_LENGTH
		ranked = ranked[:PAGE_LENGTH]
		# Still ERPNext's list: it re-applies the customer filter to these names.
		docs = get_transaction_list(
			DOCTYPE, filters={"name": ["in", ranked]}, limit_start=0, limit_page_length=len(ranked)
		)
		position = {name: index for index, name in enumerate(ranked)}
		docs.sort(key=lambda doc: position[doc.name])
	else:
		docs = get_transaction_list(
			DOCTYPE, filters=filters, limit_start=start, limit_page_length=PAGE_LENGTH + 1
		)
		has_more = len(docs) > PAGE_LENGTH
		docs = docs[:PAGE_LENGTH]

	numbers = resolve_voucher_numbers((DOCTYPE, doc.name) for doc in docs)
	return [_row(doc, numbers.get((DOCTYPE, doc.name))) for doc in docs], has_more


def _portal_customers():
	"""The customers get_transaction_list would force for this user; [] if it would not."""
	if not is_website_user():
		return []
	customers, _suppliers = get_customers_suppliers(DOCTYPE, frappe.session.user)
	return customers or []


def _matching_names(query):
	"""Invoices of the session user's own customers matching number, name, PO or item."""
	customers, _suppliers = get_customers_suppliers(DOCTYPE, frappe.session.user)
	if not customers:
		return []

	scope = [["customer", "in", customers], ["docstatus", "=", 1]]
	like = f"%{query}%"
	fields = ["name", "customer_name", "po_no"]
	number_field = target_fields().get(DOCTYPE)
	if number_field and frappe.db.has_column(DOCTYPE, number_field):
		fields.append(number_field)

	names = set(
		frappe.get_all(
			DOCTYPE,
			filters=scope,
			or_filters=[[field, "like", like] for field in fields],
			pluck="name",
			limit=MAX_SEARCH_MATCHES,
			order_by="posting_date desc",
		)
	)
	names.update(
		frappe.get_all(
			DOCTYPE,
			filters=[*scope, ["Sales Invoice Item", "item_name", "like", like]],
			pluck="name",
			distinct=True,
			limit=MAX_SEARCH_MATCHES,
			order_by="posting_date desc",
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
		route=f"/invoices/{quoted(doc.name)}",
		miti=invoice_miti(doc),
		date=frappe.utils.formatdate(doc.posting_date, "d MMM yyyy"),
		customer=doc.customer_name or doc.customer,
		company=doc.company,
		items=items,
		extra_items=extra,
		total_qty=total_qty,
		total=doc.get_formatted(total_field),
		outstanding=doc.get_formatted("outstanding_amount") if doc.outstanding_amount else "",
		status=_(doc.status),
		tone=TONES.get(doc.get("indicator_color"), "plain"),
	)


def invoice_miti(doc):
	"""The stored BS date where the site has the field, else the converted one."""
	if doc.meta.has_field("custom_invoice_miti") and doc.get("custom_invoice_miti"):
		return doc.custom_invoice_miti
	try:
		from avinashgroup_app.custom_code.CBMS.utils import bs_date_str

		return bs_date_str(doc.posting_date) or ""
	except Exception:
		return ""
