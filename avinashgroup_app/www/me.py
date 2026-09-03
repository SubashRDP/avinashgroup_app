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

  * The account's recent bills and orders, with the number the customer was
    actually handed and what is still due on each. This is the page's content;
    the stock /me had none, and a customer opening it learned nothing.

  * The portal menu, laid out by weight instead of alphabetically: the two
    routes worth a tap get the width, the rest get a line each. The sidebar is
    turned OFF here because it lists the very same routes -- with both on, the
    page printed every link twice, side by side.

Only a customer sees it. /me belongs to every website login, so a session with
no Portal User row -- staff, a supplier, anyone else -- is handed frappe's own
page untouched.

Nothing here widens what anyone can see: get_credit_snapshot refuses a customer
the session user is not linked to, and every figure on the page is that user's
own account.
"""

import frappe
from frappe import _
from frappe.utils import fmt_money
from frappe.website.utils import get_portal_sidebar_items

from avinashgroup_app.templates.pages.place_order import get_credit_snapshot
from avinashgroup_app.utils.voucher_numbers import resolve as resolve_voucher_numbers

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


# The two the page leads with, in order of preference, matched the same way as
# the icons. Everything else falls back into the quiet list under "More".
_PRIMARY_TOKENS = ("place-order", "statement", "invoice", "order")

# How many documents the activity list shows. Long enough to be worth reading,
# short enough that nobody scrolls past it to reach the settings.
RECENT_LIMIT = 6


def _split_links(links):
	"""Two headline actions, and the rest.

	Eleven identical tiles is a control panel, not a page. The customer came to
	order gas or to look at what they owe; those two get the width, the other
	nine get a line of text each.
	"""
	primary, rest = [], list(links)
	for token in _PRIMARY_TOKENS:
		if len(primary) == 2:
			break
		for link in list(rest):
			if token in f"{link['route']} {link['title']}".lower():
				primary.append(link)
				rest.remove(link)
				break
	return primary, rest


def _miti(date):
	"""posting_date as a BS string. The books, the bills and the customer all
	run on Bikram Sambat, so that is the date this list prints; the AD date is
	the fallback for a date the converter cannot take."""
	if not date:
		return ""
	try:
		from avinashgroup_app.custom_code.CBMS.utils import bs_date_str

		return bs_date_str(date) or ""
	except Exception:
		return ""


def _recent_activity(customer_names, labels, exposure):
	"""The customer's last few submitted bills and orders, newest first.

	Deliberately across ALL of this login's accounts rather than following the
	stat row's account switch: the credit position is a property of one account,
	but "what have I done lately" is not. Rows carry the account name only when
	there is more than one to tell apart.

	Scoped by an explicit `customer IN (...)` over the links resolved for
	frappe.session.user, which is the same guard get_credit_snapshot applies --
	this reads past the doctype's own permissions and must never be handed a
	customer that did not come from _portal_customers.

	`exposure` is {customer: what the credit engine says the account owes}, and
	it is what decides whether a bill may be called "Due". A Sales Invoice's own
	outstanding_amount ignores the unallocated advance pool, so a prepaid dealer
	carrying 161,392 in advance had every bill on this list flagged Due directly
	beneath a header reading "Nothing outstanding" -- both from real data, and
	the page contradicting itself. The engine has the only account-level answer,
	so the engine decides; a customer whose position was not computed (past
	MAX_EAGER_SNAPSHOTS) gets no flag rather than a guessed one.
	"""
	if not customer_names:
		return []

	# The LIMIT sits INSIDE each branch, not only on the union. There is no
	# composite (customer, posting_date) index -- only one on each column -- so
	# a union that sorts afterwards has to read and filesort every bill the
	# customer has ever had: 1.11s on NGI-CUS-00592, which holds 10,121 of them.
	# Limited per branch the optimizer walks the posting_date index backwards
	# and stops at six. Same six rows, 0.00s.
	rows = frappe.db.sql(
		"""
		SELECT * FROM (
			SELECT 'Sales Invoice' AS doctype, name, customer, posting_date AS date,
			       grand_total, outstanding_amount, status, currency
			FROM `tabSales Invoice`
			WHERE docstatus = 1 AND customer IN %(customers)s
			ORDER BY posting_date DESC, name DESC
			LIMIT %(limit)s
		) AS bills
		UNION ALL
		SELECT * FROM (
			SELECT 'Sales Order' AS doctype, name, customer, transaction_date AS date,
			       grand_total, NULL AS outstanding_amount, status, currency
			FROM `tabSales Order`
			WHERE docstatus = 1 AND customer IN %(customers)s
			ORDER BY transaction_date DESC, name DESC
			LIMIT %(limit)s
		) AS orders
		ORDER BY date DESC, name DESC
		LIMIT %(limit)s
		""",
		{"customers": customer_names, "limit": RECENT_LIMIT},
		as_dict=True,
	)
	if not rows:
		return []

	# The number on the paper the customer was handed, never the Frappe name --
	# custom_branch_name on a Sales Invoice, custom_name elsewhere, and the
	# Numbering Configuration rule is what says which.
	numbers = resolve_voucher_numbers((r.doctype, r.name) for r in rows)

	out = []
	for r in rows:
		is_invoice = r.doctype == "Sales Invoice"
		due = float(r.outstanding_amount or 0) if is_invoice else 0.0

		if not is_invoice:
			state, tone = _(r.status or ""), "plain"
		elif due <= 0:
			state, tone = _("Paid"), "ok"
		elif exposure.get(r.customer) is None:
			state, tone = "", "plain"
		elif exposure[r.customer] <= 0:
			# The bill is open, but the account is square: the customer's
			# advance covers it. Saying so is both true and the answer to the
			# question the row would otherwise raise.
			state, tone = _("Covered by advance"), "ok"
		else:
			# On an untouched bill the outstanding IS the grand total, and
			# printing it under the amount stacked the same figure twice. Only
			# a part-paid bill has a second number worth stating.
			part_paid = abs(due - float(r.grand_total or 0)) > 0.01
			state = _("{0} due").format(fmt_money(due, 2)) if part_paid else _("Due")
			tone = "due"

		out.append({
			"number": numbers.get((r.doctype, r.name)) or r.name,
			"route": ("/invoices/" if is_invoice else "/orders/") + r.name,
			"kind": _("Bill") if is_invoice else _("Order"),
			"icon": "invoice" if is_invoice else "cart",
			"miti": _miti(r.date) or frappe.utils.formatdate(r.date, "d MMM yyyy"),
			"amount": fmt_money(r.grand_total or 0, 2),
			"state": state,
			"tone": tone,
			# only worth printing when the customer holds more than one account
			"account": labels.get(r.customer, "") if len(customer_names) > 1 else "",
		})
	return out


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

	customers = _portal_customers()

	# /me is frappe's account page for EVERY website login -- a supplier, an
	# employee, a member of staff who happens to open it, anyone at all with a
	# User record. This page is built for the gas customer portal and reads as
	# one: stats, bills, an account position. Anyone who is not a customer gets
	# frappe's own page instead, unchanged.
	#
	# context.template is read by get_raw_template AFTER get_context returns
	# (set_page_properties seeds it, we overwrite it), and the "frappe/" prefix
	# resolves through the jinja PrefixLoader to frappe/www/me.html
	# specifically -- not to whichever installed app's www/me.html happens to
	# come first, which is how this file wins the route in the first place.
	if not customers:
		from frappe.www.me import get_context as stock_me_context

		stock_me_context(context)
		context.template = "frappe/www/me.html"
		return

	context.current_user = frappe.get_doc("User", frappe.session.user)
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

	context.primary_links, context.more_links = _split_links(_quick_links())
	context.recent = _recent_activity(
		[row.name for row in customers],
		context.customer_labels,
		{name: snap.get("outstanding") for name, snap in snapshots.items() if snap},
	)

	# The sidebar IS the portal's navigation and it stays. What was wrong was
	# printing it twice: the tile grid this page used to carry listed the very
	# same routes beside it. Now the two never coexist -- the sidebar is the nav
	# from 768px up, and the "More" list below only appears where the sidebar is
	# hidden, on a phone, where a column of links stacked above the profile
	# would push the account itself under the fold.
	context.show_sidebar = True
