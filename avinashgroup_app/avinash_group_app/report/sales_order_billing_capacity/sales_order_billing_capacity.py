# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

"""Sales Order Billing Capacity — how much of the pending orders can be invoiced today.

Orders are taken freely (the portal shows the customer their credit position
but never refuses an order), while the credit limits are enforced only when the
Sales Invoice is saved (credit_control.validate_sales_invoice). Billing staff
found out an order could not be billed only by trying it and getting the
"Credit Limit Exceeded" popup, one order at a time. This report runs the same
check over every pending order up front:

- One row per pending Sales Order — "pending" exactly as the billing nudges
  mean it (pending_orders._pending_filters): submitted, not Closed / On Hold /
  Completed, billed under 99.99 %.
- The customer's position comes from credit_control.get_credit_position, the
  same figures the Sales Invoice banner and the save-time check use, so this
  report can never disagree with the popup about where a customer stands.
- A customer's orders are then billed oldest-first, on paper: each order uses
  up the credit it is given, so a second order sees what the first one left,
  and every invoice that is not fully paid from left-over advance counts as one
  more unpaid bill against the bill-count limit. Limits are tested days, then
  bill count, then amount. The save tests count before days, but an order over
  either is blocked either way; days goes first here so the Why column names
  the block that billing more can never clear.

Deliberately read-only and approximate in one known way: "To Bill" is the
order's own grand total less the part already billed. When an invoice is made
from the order it is repriced at today's Item Price (so_latest_rate), so the
real invoice can come out higher or lower than this figure after a price change.

Pending orders outside the date filter are still billed first on paper — they
are still waiting, so they still use up credit — they are only hidden.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate

from avinashgroup_app.custom_code.CBMS.utils import bs_date_str
from avinashgroup_app.custom_code.SalesInvoice.credit_control import get_credit_position
from avinashgroup_app.custom_code.SalesInvoice.pending_orders import _pending_filters

# A Customer amount limit at or under 1 is this group's marker for an
# advance-only account, not a rupee of headroom (see place_order.get_credit_snapshot).
ADVANCE_ONLY_LIMIT = 1

# Under a paisa is rounding, not money left to bill.
PAISA = 0.01

READY, PARTLY, BLOCKED = "Ready", "Partly", "Blocked"


def _as_list(value):
	"""A MultiSelectList filter value (list, JSON string or single value) as a list."""
	if not value:
		return []
	if isinstance(value, str):
		value = value.strip()
		if value.startswith("["):
			return [v for v in json.loads(value) if v]
		return [value]
	return [v for v in value if v]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if filters.from_date and filters.to_date and getdate(filters.to_date) < getdate(filters.from_date):
		frappe.throw(_("To Date cannot be before From Date."))

	orders = _pending_orders(_as_list(filters.company), _as_list(filters.customer))
	rows = _plan_billing(orders)

	rows = [r for r in rows if _shown(r, filters)]
	return get_columns(), rows, None, None, _summary(rows)


def _pending_orders(companies, customers):
	"""Every pending order of the selected companies / customers, oldest first.

	get_list, not raw SQL, so the user's Sales Order permissions (User
	Permission on Company included) decide which orders appear.
	"""
	filters = _pending_filters()
	if companies:
		filters["company"] = ["in", companies]
	if customers:
		filters["customer"] = ["in", customers]

	return frappe.get_list(
		"Sales Order",
		filters=filters,
		fields=["name", "company", "customer", "customer_name", "transaction_date",
			"grand_total", "per_billed", "currency"],
		order_by="transaction_date asc, creation asc",
		page_length=0,
	)


def _plan_billing(orders):
	"""One row per order with how much of it the customer's limits let through today."""
	abbr = dict(frappe.get_all("Company", fields=["name", "abbr"], as_list=True))

	by_customer = {}
	for o in orders:
		by_customer.setdefault(o.customer, []).append(o)

	rows = []
	for customer, customer_orders in by_customer.items():
		state = get_credit_position(customer) or {}
		rows.extend(_plan_customer(state, customer_orders, abbr))
	return rows


def _plan_customer(state, orders, abbr):
	"""Bill one customer's orders oldest-first against their credit position.

	`state` is get_credit_position's payload. Running figures:
	  exposure  what the customer owes net of left-over advance — the amount
	            check is `exposure + invoice > amount_limit`, so room = limit - exposure
	  count     unpaid bills — the count check blocks once count >= bill_limit
	  leftover  advance not yet used; an invoice it fully covers is paid at
	            once and does not add to the unpaid count
	"""
	has_limits = bool(state.get("has_limits"))
	bill_limit = int(state.get("bill_limit") or 0)
	days_limit = int(state.get("days_limit") or 0)
	amount_limit = flt(state.get("amount_limit"))
	days_used = int(state.get("days_used") or 0)
	advance_only = 0 < amount_limit <= ADVANCE_ONLY_LIMIT

	exposure = flt(state.get("exposure"))
	count = int(state.get("unpaid_count") or 0)
	leftover = flt(state.get("leftover_advance"))
	days_blocked = has_limits and days_limit and days_used >= days_limit

	rows = []
	for o in orders:
		to_bill = flt(flt(o.grand_total) * (100 - flt(o.per_billed)) / 100, 2)
		room = flt(amount_limit - exposure, 2) if (has_limits and amount_limit) else None

		if not has_limits:
			can_bill, reason = to_bill, _("No credit limit set on the customer")
		elif days_blocked:
			can_bill = 0
			reason = _("Oldest unpaid bill {0} is {1} days old (limit {2}) — collect payment first").format(
				state.get("oldest_invoice") or "", days_used, days_limit)
		elif bill_limit and count >= bill_limit:
			can_bill = 0
			reason = _("{0} unpaid bills (limit {1})").format(count, bill_limit)
			if count > int(state.get("unpaid_count") or 0):
				reason += _(" — counting the invoices for the older orders above")
		elif room is not None and room < PAISA:
			can_bill = 0
			reason = (_("Advance-only account and no advance left") if advance_only
				else _("Credit limit used up"))
		elif room is not None and room < to_bill - PAISA:
			can_bill = room
			reason = (_("Advance left covers only part of this order") if advance_only
				else _("Credit left covers only part of this order"))
		else:
			can_bill = to_bill
			reason = _("Within all limits")

		if can_bill > 0:
			exposure += can_bill
			if can_bill > leftover + PAISA:
				count += 1
			leftover = max(0.0, leftover - can_bill)

		if can_bill >= to_bill - PAISA:
			verdict = READY
		elif can_bill > 0:
			verdict = PARTLY
		else:
			verdict = BLOCKED

		rows.append({
			"customer": o.customer,
			"customer_name": o.customer_name or o.customer,
			"company": abbr.get(o.company) or o.company,
			"sales_order": o.name,
			"miti": bs_date_str(o.transaction_date) if o.transaction_date else "",
			"date": o.transaction_date,
			"order_amount": flt(o.grand_total),
			"to_bill": to_bill,
			"can_bill": can_bill,
			"short_by": flt(to_bill - can_bill, 2),
			"verdict": verdict,
			"reason": reason,
			"bills": _of(state.get("unpaid_count"), bill_limit) if has_limits else "",
			"days": _of(days_used, days_limit) if has_limits else "",
			"amount_limit": amount_limit if has_limits else None,
			"credit_left": room,
		})
	return rows


def _of(used, limit):
	"""'3 / 5', or just '3' when that limit is not set."""
	used = int(used or 0)
	return f"{used} / {limit}" if limit else str(used)


def _shown(row, filters):
	"""Date and verdict filters only hide rows; the billing plan ran over all of them."""
	if filters.from_date and getdate(row["date"]) < getdate(filters.from_date):
		return False
	if filters.to_date and getdate(row["date"]) > getdate(filters.to_date):
		return False
	if filters.verdict and row["verdict"] != filters.verdict:
		return False
	return True


def _summary(rows):
	to_bill = sum(r["to_bill"] for r in rows)
	can_bill = sum(r["can_bill"] for r in rows)
	billable_customers = {r["customer"] for r in rows if r["can_bill"] > 0}
	blocked_customers = {r["customer"] for r in rows} - billable_customers
	return [
		{"label": _("Pending Orders"), "value": len(rows), "datatype": "Int", "indicator": "Blue"},
		{"label": _("To Bill"), "value": to_bill, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Can Bill Now"), "value": can_bill, "datatype": "Currency", "indicator": "Green"},
		{"label": _("Held by Credit Limits"), "value": to_bill - can_bill, "datatype": "Currency",
			"indicator": "Red"},
		{"label": _("Customers Fully Blocked"), "value": len(blocked_customers), "datatype": "Int",
			"indicator": "Red"},
	]


def get_columns():
	return [
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer",
			"width": 130},
		{"fieldname": "customer_name", "label": _("Customer Name"), "fieldtype": "Data", "width": 190},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Data", "width": 75},
		{"fieldname": "sales_order", "label": _("Sales Order"), "fieldtype": "Link",
			"options": "Sales Order", "width": 160},
		{"fieldname": "miti", "label": _("Miti"), "fieldtype": "Data", "width": 100},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "order_amount", "label": _("Order Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "to_bill", "label": _("To Bill"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "can_bill", "label": _("Can Bill Now"), "fieldtype": "Currency", "width": 125},
		{"fieldname": "short_by", "label": _("Held Back"), "fieldtype": "Currency", "width": 115},
		{"fieldname": "verdict", "label": _("Verdict"), "fieldtype": "Data", "width": 90},
		{"fieldname": "reason", "label": _("Why"), "fieldtype": "Data", "width": 300},
		{"fieldname": "bills", "label": _("Unpaid Bills / Limit"), "fieldtype": "Data", "width": 135},
		{"fieldname": "days", "label": _("Days / Limit"), "fieldtype": "Data", "width": 105},
		{"fieldname": "amount_limit", "label": _("Amount Limit"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "credit_left", "label": _("Credit Left Before Order"), "fieldtype": "Currency",
			"width": 160},
	]
