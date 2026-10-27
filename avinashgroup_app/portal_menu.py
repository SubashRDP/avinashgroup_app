"""Portal page list for the phone menu (the ☰ button) on custom portal pages.

On a phone Frappe puts the portal sidebar's pages (Orders, Invoices, Customer
Statement, ...) into the ☰ menu, but only on pages that turn show_sidebar on
(frappe/templates/includes/navbar/navbar_items.html). Our custom pages —
Place Order, Product Wise Invoice Details, Customer Statement, Sales Order
Analysis, /me — keep show_sidebar off because the desktop sidebar column breaks
their wide layouts, so their ☰ menu opened empty.

public/js/portal_mobile_menu.js asks this for the same list and adds it to the
☰ menu, only on pages that don't already have it.
"""

import frappe
from frappe import _
from frappe.website.utils import get_portal_sidebar_items


@frappe.whitelist()
def get_portal_menu():
	"""The logged-in user's portal sidebar pages: [{title, route, target}]."""
	if frappe.session.user == "Guest":
		return []

	return [
		{
			"title": _(item.get("title") or item.get("label") or ""),
			"route": item.get("route"),
			"target": item.get("target") or "",
		}
		for item in get_portal_sidebar_items()
		if item.get("type") != "input" and item.get("route")
	]
