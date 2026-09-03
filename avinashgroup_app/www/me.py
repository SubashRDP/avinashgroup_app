# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

"""My Account (/me) for the customer portal.

This replaces frappe/www/me.html. TemplatePage.set_template_path walks every
installed app in REVERSE install order, so a file at avinashgroup_app/www/me.html
is found before frappe's own and nothing has to be patched for the override to
take -- see frappe/website/page_renderers/template_page.py.

What it adds over the stock page:

  * The customer's credit position, pinned to the top while the page scrolls.
    The figures come from credit_control.get_credit_position through the same
    whitelisted wrapper the Place Order sheet uses, which is the same core the
    Sales Invoice banner reads. One calculation, three screens -- the customer
    is never shown a number that differs from the one the office sees.

  * The portal menu as a tap grid. The sidebar column is hidden below 768px
    (and the ERPNext mobile app is where most of these customers open this
    page), so on a phone the stock /me is three links and a dead end.

Nothing here widens what anyone can see: get_credit_snapshot refuses a customer
the session user is not linked to, and every figure on the page is that user's
own account.
"""

import frappe
from frappe import _
from frappe.website.utils import get_portal_sidebar_items

from avinashgroup_app.templates.pages.place_order import get_credit_snapshot

# Rendered HTML for a website page is cached by path and language only
# (frappe/website/utils.py: cache_html) -- not by user. This page is built from
# frappe.session.user, so caching it would serve one customer their neighbour's
# balance. Frappe skips the cache when developer_mode is on, which is exactly
# why a mistake here would never show up locally.
no_cache = 1

# How many accounts get their position computed during the page load. Each one
# is a window function over the customer's unpaid bills, so a user linked to a
# dozen accounts would pay for eleven cards they never look at. The rest load on
# tap through get_credit_snapshot, which is the same call and the same figures.
MAX_EAGER_SNAPSHOTS = 4

# Icon for a portal menu entry, first match wins. Matched against the route and
# the title together, lowercased, so both "/orders" and "Sales Orders" land on
# the same tile whatever the Portal Settings row happens to be called.
_LINK_ICONS = (
	("statement", "receipt"),
	("place-order", "cart"),
	("invoice", "invoice"),
	("quotation", "quote"),
	("order", "cart"),
	("shipment", "truck"),
	("delivery", "truck"),
	("issue", "alert"),
	("address", "pin"),
	("timesheet", "clock"),
	("newsletter", "mail"),
	("request", "box"),
	("project", "folder"),
	("task", "check"),
)


def _quick_links():
	"""The portal menu, as tiles.

	Same source the sidebar renders from (get_portal_sidebar_items is
	role-filtered and cached per user), so a tile can never appear for a link
	the sidebar would not have offered. The sidebar itself is built after
	get_context runs -- hence reading the source directly rather than
	context.sidebar_items, which is not there yet.
	"""
	links = []
	for item in get_portal_sidebar_items() or []:
		route = (item.get("route") or "").strip()
		title = (item.get("title") or item.get("label") or "").strip()
		# Group headers carry no route; the search box is a form, not a link.
		if not route or not title or item.get("type") == "input":
			continue
		# This page. A tile back to itself is a dead tap.
		if route.rstrip("/").endswith("/me"):
			continue

		key = f"{route} {title}".lower()
		icon = next((name for token, name in _LINK_ICONS if token in key), "link")
		links.append({"title": title, "route": route, "icon": icon})
	return links


def _portal_customers():
	"""Customers this login is linked to, via the Portal User child table.

	Same link the Place Order sheet and the Customer Statement resolve against.
	Empty for a staff user, which is what keeps the credit strip off their /me.

	Each row carries a `label` for the switcher. A dealer holding an account
	with two of the group companies usually holds it under the SAME trading
	name, so the bare customer_name would print two identical chips; the
	company abbreviation is appended only where it is doing that work.
	"""
	rows = frappe.db.sql(
		"""
		SELECT c.name, c.customer_name, IFNULL(c.custom_company, '') AS company
		FROM `tabPortal User` pu
		INNER JOIN `tabCustomer` c ON c.name = pu.parent
		WHERE pu.user = %s
		  AND pu.parenttype = 'Customer'
		  AND c.disabled = 0
		ORDER BY c.customer_name
		""",
		frappe.session.user,
		as_dict=True,
	)

	seen = {}
	for row in rows:
		seen[row.customer_name] = seen.get(row.customer_name, 0) + 1

	for row in rows:
		abbr = frappe.db.get_value("Company", row.company, "abbr") if row.company else ""
		row.label = (
			f"{row.customer_name} · {abbr or row.company}"
			if seen[row.customer_name] > 1 and (abbr or row.company)
			else row.customer_name
		)
	return rows


def get_context(context):
	context.no_cache = 1

	if frappe.session.user == "Guest":
		frappe.throw(_("You need to be logged in to access this page"), frappe.PermissionError)

	context.current_user = frappe.get_doc("User", frappe.session.user)
	context.show_sidebar = True

	customers = _portal_customers()
	context.customers = customers

	# Snapshots are keyed by customer id and handed to the page as JSON: one
	# renderer draws the card, in the browser, for both the accounts fetched
	# here and the ones fetched on tap. Rendering it twice -- once in Jinja and
	# once in JS -- is how the two drift.
	snapshots = {}
	for row in customers[:MAX_EAGER_SNAPSHOTS]:
		snapshots[row.name] = get_credit_snapshot(row.name) or {}

	context.credit_snapshots = snapshots
	context.active_customer = customers[0].name if customers else ""
	# The strip names the account it is describing even when there is only one
	# and no switcher is drawn, so the renderer needs the labels too.
	context.customer_labels = {row.name: row.label for row in customers}

	# The strip formats its own figures client-side (same helper Place Order
	# uses), so it needs the site's number format -- Nepal reads 12,34,567.89.
	context.number_format = frappe.db.get_default("number_format") or "#,###.##"

	context.show_account_deletion_link = frappe.db.get_single_value(
		"Website Settings", "show_account_deletion_link"
	)

	context.quick_links = _quick_links()
