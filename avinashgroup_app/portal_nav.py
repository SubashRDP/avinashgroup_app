"""The standard customer portal menu.

update_website_context (hooked in hooks.py) gives every customer portal page one
menu: a fixed left rail on desktop that collapses with <<, and the same entries
in the ☰ menu on a phone. It is a rail outside the page's own markup, rather than
Frappe's show_sidebar column, so custom pages keep their layout and no page
carries a copy of the menu.

Entries still come from get_portal_sidebar_items (Portal Settings, filtered by
role); this only fixes their order, label and icon, so nothing becomes visible
that wasn't. The HTML is per-user, so it is only added to no_cache pages.

A module of its own on purpose: production gunicorn workers keep already-imported
modules, so a hook pointing at a new function in portal_menu.py would raise on
every website page in a worker holding the old copy until the next restart.
"""

import frappe
from frappe import _
from frappe.website.utils import get_portal_sidebar_items


# route, label, icon: the order every customer sees. Routes the user's roles don't
# include are dropped; enabled routes not listed here follow, under their own title.
STANDARD_MENU = (
	("/place_order", "Place Order", "plus"),
	("/orders", "Orders", "cart"),
	("/invoices", "Invoices", "receipt"),
	("/customer_statement", "Customer Statement", "ledger"),
	("/product_wise_invoice_details", "Product Wise Invoice Details", "box"),
	("/sales_order_analysis", "Sales Order Analysis", "chart"),
	("/portal_announcement_history", "Notice", "bell"),
)
ACCOUNT_ROUTE = "/me"


def get_standard_menu():
	"""The user's menu entries in standard order: [{title, route, icon, target}]."""
	allowed = {}
	for item in get_portal_sidebar_items() or []:
		route = item.get("route")
		if route and item.get("type") != "input":
			allowed.setdefault("/" + route.strip("/"), item)

	menu = []
	for route, label, icon in STANDARD_MENU:
		item = allowed.pop(route, None)
		if item:
			menu.append({"title": _(label), "route": route, "icon": icon, "target": item.get("target") or ""})

	for route, item in allowed.items():
		title = item.get("title") or item.get("label") or route
		menu.append({"title": _(title), "route": route, "icon": "dot", "target": item.get("target") or ""})

	menu.append({"title": _("My Account"), "route": ACCOUNT_ROUTE, "icon": "user", "target": ""})
	return menu


def _active_route(path, menu):
	"""The menu route this path belongs to: itself, or its parent for a detail page."""
	path = "/" + (path or "").strip("/")
	for item in menu:
		if path == item["route"] or path.startswith(item["route"] + "/"):
			return item["route"]
	return None


def update_website_context(context):
	"""Put the standard menu on customer portal pages; every other page is untouched."""
	if frappe.session.user == "Guest" or not context.get("no_cache"):
		return
	if not getattr(frappe.local, "request", None) or "Customer" not in frappe.get_roles():
		return

	menu = get_standard_menu()
	active = _active_route(frappe.local.request.path, menu)
	if not active:
		return

	# The rail replaces Frappe's sidebar column and its ☰ entries.
	context.show_sidebar = False
	context.body_class = " ".join(filter(None, [context.get("body_class"), "ag-pn-page"]))
	nav = frappe.render_template(
		"avinashgroup_app/templates/includes/portal_nav.html", {"menu": menu, "active": active}
	)
	context.banner_html = nav + (context.get("banner_html") or "")
