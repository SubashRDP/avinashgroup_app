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
- Pending qty is ordered qty less the qty on submitted Sales Invoices made from
  the order row (so_detail), and it is priced at TODAY's rate — the rate the
  Sales Invoice itself picks up for the item: the Item Price of the order's
  selling price list for the row's exact UOM, newest valid_from first (the
  lookup in public/js/sales_invoice.js fetch_uom_price and
  item_price_lookup.get_rate). A customer-specific Item Price wins over the
  general one, and a price not yet valid today is skipped. A row whose item has
  no Item Price keeps the order rate, and the Why column says so. The order's
  own discount % and its tax ratio (grand total / net total, i.e. VAT) are
  applied on top, so the figure is what the invoice's grand total would be —
  the amount the credit check tests.
- The customer's position comes from credit_control.get_credit_position, the
  same figures the Sales Invoice banner and the save-time check use, so this
  report can never disagree with the popup about where a customer stands.
- A customer's orders are then billed oldest-first, on paper, in whole units
  (cylinders cannot be half invoiced): each order takes as many units as the
  credit left allows, so a second order sees what the first one left, and every
  invoice not fully paid from left-over advance counts as one more unpaid bill
  against the bill-count limit. Limits are tested days, then bill count, then
  amount. The save tests count before days, but an order over either is blocked
  either way; days goes first here so the Why column names the block that
  billing more can never clear.

Pending orders outside the date filter are still billed first on paper — they
are still waiting, so they still use up credit — they are only hidden.

Read-only: nothing here writes a document.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from avinashgroup_app.custom_code.CBMS.utils import bs_date_str
from avinashgroup_app.custom_code.SalesInvoice.credit_control import get_credit_position
from avinashgroup_app.custom_code.SalesInvoice.pending_orders import _pending_filters

# A Customer amount limit at or under 1 is this group's marker for an
# advance-only account, not a rupee of headroom (see place_order.get_credit_snapshot).
ADVANCE_ONLY_LIMIT = 1

# Under a paisa is rounding, not money left to bill.
PAISA = 0.01

# Qty left on an order row below this is a rounding residue, not a unit to bill.
QTY_EPSILON = 0.0001

READY, PARTLY, BLOCKED, QTY_BILLED = "Ready", "Partly", "Blocked", "Qty Billed"


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

	customers = []
	for c in _plan_billing(orders):
		c["orders"] = [r for r in c["orders"] if _shown(r, filters)]
		if c["orders"]:
			customers.append(c)
	# Most money held back first: the customers someone has to chase are on top.
	customers.sort(key=lambda c: (-sum(r["short_by"] for r in c["orders"]),
		-sum(r["can_bill"] for r in c["orders"])))

	rows = []
	for c in customers:
		rows.append(_customer_row(c))
		rows.extend(c["orders"])

	order_rows = [r for c in customers for r in c["orders"]]
	return get_columns(), rows, None, None, _summary(order_rows)


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
			"grand_total", "net_total", "selling_price_list", "currency"],
		order_by="transaction_date asc, creation asc",
		page_length=0,
	)


def _order_items(order_names):
	"""{order: [item rows]} with each row's qty already invoiced.

	billed_qty sums submitted Sales Invoice Items made from the row (so_detail);
	a credit note against such an invoice carries a negative qty and gives the
	qty back, as it does in ERPNext's own billed figures.
	"""
	items = {}
	for row in frappe.db.sql("""
		SELECT soi.name, soi.parent, soi.item_code, soi.item_name, soi.uom, soi.qty,
			soi.rate, soi.discount_percentage,
			IFNULL(SUM(sii.qty), 0) AS billed_qty
		FROM `tabSales Order Item` soi
		LEFT JOIN `tabSales Invoice Item` sii
			ON sii.so_detail = soi.name AND sii.docstatus = 1
		WHERE soi.parent IN %(orders)s
		GROUP BY soi.name
		ORDER BY soi.parent, soi.idx
	""", {"orders": tuple(order_names)}, as_dict=True):
		items.setdefault(row.parent, []).append(row)
	return items


def _todays_prices(orders, items):
	"""{(item_code, price_list, uom, customer): rate} — the Sales Invoice's rate for today.

	One query for every item / price list on the report. Within a key the
	newest valid_from wins (then the newest edit), as in the invoice's own
	lookup; rows valid only from a later date, or expired, are left out.
	`customer` is "" for the general price.
	"""
	item_codes = {i.item_code for rows in items.values() for i in rows}
	price_lists = {o.selling_price_list for o in orders if o.selling_price_list}
	if not (item_codes and price_lists):
		return {}

	today = nowdate()
	prices = {}
	for p in frappe.db.sql("""
		SELECT item_code, price_list, uom, IFNULL(customer, '') AS customer, price_list_rate
		FROM `tabItem Price`
		WHERE selling = 1
		  AND item_code IN %(items)s
		  AND price_list IN %(lists)s
		  AND (valid_from IS NULL OR valid_from <= %(today)s)
		  AND (valid_upto IS NULL OR valid_upto >= %(today)s)
		ORDER BY valid_from DESC, modified DESC
	""", {"items": tuple(item_codes), "lists": tuple(price_lists), "today": today}, as_dict=True):
		prices.setdefault((p.item_code, p.price_list, p.uom, p.customer), flt(p.price_list_rate))
	return prices


def _last_invoices(customers):
	"""{customer: {invoice, posting_date, miti, qty}} — the customer's newest
	submitted Sales Invoice, whether or not it was made from an order, and its
	total qty. Tells billing staff when the customer was last sold to.

	Credit notes are left out: "last invoice" means the last sale, not the
	last return.
	"""
	miti = "custom_invoice_miti" if frappe.db.has_column("Sales Invoice", "custom_invoice_miti") else "NULL"
	rows = frappe.db.sql(f"""
		SELECT customer, invoice, posting_date, miti, qty FROM (
			SELECT customer, name AS invoice, posting_date, {miti} AS miti, total_qty AS qty,
				ROW_NUMBER() OVER (PARTITION BY customer
					ORDER BY posting_date DESC, posting_time DESC, creation DESC) AS n
			FROM `tabSales Invoice`
			WHERE docstatus = 1
			  AND is_return = 0
			  AND customer IN %(customers)s
		) latest
		WHERE n = 1
	""", {"customers": tuple(customers)}, as_dict=True)
	return {r.customer: r for r in rows}


def _plan_billing(orders):
	"""Per customer, their credit position and one row per order with how much of it
	the limits let through today: [{customer, customer_name, company, state, orders}]."""
	if not orders:
		return []

	names = [o.name for o in orders]
	items = _order_items(names)
	prices = _todays_prices(orders, items)
	last = _last_invoices({o.customer for o in orders})
	abbr = dict(frappe.get_all("Company", fields=["name", "abbr"], as_list=True))

	by_customer = {}
	for o in orders:
		o.lines = _priced_lines(o, items.get(o.name, []), prices)
		by_customer.setdefault(o.customer, []).append(o)

	customers = []
	for customer, customer_orders in by_customer.items():
		state = get_credit_position(customer) or {}
		first = customer_orders[0]
		customers.append({
			"customer": customer,
			"customer_name": first.customer_name or customer,
			"company": abbr.get(first.company) or first.company,
			"state": state,
			"last_invoice": last.get(customer),
			"orders": _plan_customer(state, customer_orders),
		})
	return customers


def _customer_row(c):
	"""The bold parent row of a customer's block: their orders added up, and their
	credit position, which the order rows below it no longer repeat."""
	state, orders = c["state"], c["orders"]
	has_limits = bool(state.get("has_limits"))
	amount_limit = flt(state.get("amount_limit"))
	bill_limit = int(state.get("bill_limit") or 0)
	days_limit = int(state.get("days_limit") or 0)

	verdicts = {r["verdict"] for r in orders} - {QTY_BILLED}
	if not verdicts:
		verdict = QTY_BILLED
	elif verdicts == {READY}:
		verdict = READY
	elif verdicts == {BLOCKED}:
		verdict = BLOCKED
	else:
		verdict = PARTLY
	# The first order that did not go through names what is holding the customer.
	held = next((r for r in orders if r["verdict"] in (PARTLY, BLOCKED)), None)

	meter = _credit_meter(state, sum(r["can_bill"] for r in orders))
	row = {
		"label": c["customer_name"],
		"customer": c["customer"],
		"indent": 0,
		"bold": 1,
		"company": c["company"],
		"item": _("{0} orders").format(len(orders)) if len(orders) > 1 else _("1 order"),
		"verdict": verdict,
		"reason": held["reason"] if held else _("Every order fits the limits"),
		"bills": _of(state.get("unpaid_count"), bill_limit) if has_limits else "",
		"days": _of(state.get("days_used"), days_limit) if has_limits else "",
		"amount_limit": amount_limit if has_limits else None,
		"credit_left": flt(amount_limit - flt(state.get("exposure")), 2) if (has_limits and amount_limit) else None,
		# Plain text for the Excel export; the JS draws the bar from _meter.
		"_meter": meter,
		"credit_meter": meter["text"],
	}
	last = c["last_invoice"]
	if last:
		row["last_invoice"] = last.invoice
		row["last_invoice_miti"] = last.miti or bs_date_str(last.posting_date)
		row["last_invoice_qty"] = flt(last.qty)
	for field in ("order_qty", "billed_qty", "pending_qty", "to_bill_order", "to_bill",
			"qty_can_bill", "can_bill", "short_by"):
		row[field] = flt(sum(r[field] or 0 for r in orders), 2)
	return row


def _credit_meter(state, can_bill=0):
	"""What the Credit Used cell shows: {kind, text, used_pct, after_pct | leftover}.

	Measured against the customer's whole room to bill — the amount limit PLUS
	any advance left over once their bills are covered — because that is what
	the credit check lets through (exposure = outstanding - leftover advance).
	Against the limit alone a prepaid customer reads 0 % used while their orders
	are being blocked: Counter Sales has a 1,455 limit and 1.4 lakh of advance.

	used_pct is that room used today; after_pct is once the orders that fit
	(`can_bill`) are invoiced. JS draws both on one bar.
	"""
	amount_limit = flt(state.get("amount_limit"))
	if not state.get("has_limits") or not amount_limit:
		return {"kind": "none", "text": _("No amount limit")}
	leftover = flt(state.get("leftover_advance"))
	if amount_limit <= ADVANCE_ONLY_LIMIT:
		return {"kind": "advance", "leftover": leftover,
			"text": _("Advance only · {0} left").format(frappe.format_value(leftover, "Currency"))}

	room = amount_limit + leftover
	outstanding = max(0.0, flt(state.get("outstanding")))
	used_pct = round(outstanding / room * 100, 1)
	after_pct = round((outstanding + flt(can_bill)) / room * 100, 1)
	text = _("{0}% used").format(round(used_pct))
	if after_pct > used_pct:
		text += _(" → {0}% after billing").format(round(after_pct))
	return {"kind": "amount", "used_pct": used_pct, "after_pct": after_pct, "text": text,
		"limit": amount_limit, "leftover": leftover}


def _priced_lines(order, order_items, prices):
	"""The order's rows still to bill, each with its per-unit invoice amount at
	the order's rate and at today's rate (discount and the order's VAT included)."""
	# VAT on these orders is an Actual tax row built by this app, so it is
	# carried over as the order's own grand/net ratio rather than recomputed.
	tax_ratio = flt(order.grand_total) / flt(order.net_total) if flt(order.net_total) else 1.0

	lines = []
	for i in order_items:
		pending = flt(i.qty) - flt(i.billed_qty)
		if pending < QTY_EPSILON:
			continue
		key = (i.item_code, order.selling_price_list, i.uom)
		price = prices.get(key + (order.customer,)) or prices.get(key + ("",))
		today_rate = flt(price) * (1 - flt(i.discount_percentage) / 100) if price else flt(i.rate)
		lines.append(frappe._dict(
			item_code=i.item_code,
			item_name=i.item_name or i.item_code,
			uom=i.uom,
			qty=flt(i.qty),
			billed_qty=flt(i.billed_qty),
			pending=pending,
			order_rate=flt(i.rate),
			today_rate=today_rate,
			has_price=bool(price),
			order_unit=flt(i.rate) * tax_ratio,
			today_unit=today_rate * tax_ratio,
		))
	return lines


def _fill_units(lines, room):
	"""Whole units of each line, in row order, that fit in `room` (None = no limit).

	Returns (qty, amount) — qty of all lines together and their invoice amount.
	A part-unit left on a row (qty 2.5) is billed only when it fits whole.
	"""
	qty = amount = 0.0
	for line in lines:
		take = line.pending
		if room is not None:
			if line.today_unit > 0:
				take = min(take, int((room - amount) / line.today_unit + QTY_EPSILON))
			take = max(take, 0)
		qty += take
		amount += take * line.today_unit
	return qty, flt(amount, 2)


def _plan_customer(state, orders):
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
		lines = o.lines
		pending_qty = sum(l.pending for l in lines)
		to_bill_order = flt(sum(l.pending * l.order_unit for l in lines), 2)
		to_bill = flt(sum(l.pending * l.today_unit for l in lines), 2)
		room = flt(amount_limit - exposure, 2) if (has_limits and amount_limit) else None
		can_qty, can_bill = 0.0, 0.0

		if not lines:
			reason = _("Every unit is invoiced; only the amount differs from the order")
		elif not has_limits:
			can_qty, can_bill = pending_qty, to_bill
			reason = _("No credit limit set on the customer")
		elif days_blocked:
			reason = _("Oldest unpaid bill {0} is {1} days old (limit {2}) — collect payment first").format(
				state.get("oldest_invoice") or "", days_used, days_limit)
		elif bill_limit and count >= bill_limit:
			reason = _("{0} unpaid bills (limit {1})").format(count, bill_limit)
			if count > int(state.get("unpaid_count") or 0):
				reason += _(" — counting the invoices for the older orders above")
		elif room is not None and room < PAISA:
			reason = (_("Advance-only account and no advance left") if advance_only
				else _("Credit limit used up"))
		else:
			can_qty, can_bill = _fill_units(lines, room)
			if can_qty >= pending_qty - QTY_EPSILON:
				reason = _("Within all limits")
			elif can_qty > 0:
				reason = (_("Advance left covers {0} of {1} qty") if advance_only
					else _("Credit left covers {0} of {1} qty")).format(_qty(can_qty), _qty(pending_qty))
			else:
				reason = (_("Advance left is less than one unit") if advance_only
					else _("Credit left is less than one unit"))

		if any(not l.has_price for l in lines):
			reason += _(" · no Item Price for today, order rate used")

		if can_bill > 0:
			exposure += can_bill
			if can_bill > leftover + PAISA:
				count += 1
			leftover = max(0.0, leftover - can_bill)

		if not lines:
			verdict = QTY_BILLED
		elif can_qty >= pending_qty - QTY_EPSILON:
			verdict = READY
		elif can_qty > 0:
			verdict = PARTLY
		else:
			verdict = BLOCKED

		single = lines[0] if len(lines) == 1 else None
		rows.append({
			# Tree child of the customer row; `label` is the first column.
			"label": o.name,
			"indent": 1,
			"customer": o.customer,
			"sales_order": o.name,
			"miti": bs_date_str(o.transaction_date) if o.transaction_date else "",
			"date": o.transaction_date,
			"item": (f"{single.item_name} · {single.uom}" if single
				else _("{0} items").format(len(lines)) if lines else ""),
			"order_qty": sum(l.qty for l in lines),
			"billed_qty": sum(l.billed_qty for l in lines),
			"pending_qty": pending_qty,
			# A rate means something only for a one-item order; with several
			# items the amounts carry it.
			"order_rate": single.order_rate if single else None,
			"today_rate": single.today_rate if single else None,
			"to_bill_order": to_bill_order,
			"to_bill": to_bill,
			"qty_can_bill": can_qty,
			"can_bill": can_bill,
			"short_by": flt(to_bill - can_bill, 2),
			"verdict": verdict,
			"reason": reason,
			"credit_left": room,
		})
	return rows


def _qty(value):
	"""Qty for a sentence: 6, not 6.0."""
	return int(value) if float(value).is_integer() else round(value, 3)


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
	blocked_customers = {r["customer"] for r in rows if r["verdict"] == BLOCKED} - billable_customers
	pending_qty = sum(r["pending_qty"] for r in rows)
	can_qty = sum(r["qty_can_bill"] for r in rows)
	return [
		{"label": _("Pending Orders"), "value": len(rows), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Qty Can Bill / Pending"), "value": f"{_qty(can_qty)} / {_qty(pending_qty)}",
			"datatype": "Data", "indicator": "Green" if can_qty >= pending_qty else "Orange"},
		{"label": _("To Bill at Today's Rate"), "value": to_bill, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Can Bill Now"), "value": can_bill, "datatype": "Currency", "indicator": "Green"},
		{"label": _("Held by Credit Limits"), "value": to_bill - can_bill, "datatype": "Currency",
			"indicator": "Red" if to_bill - can_bill > PAISA else "Green"},
		{"label": _("Customers Fully Blocked"), "value": len(blocked_customers), "datatype": "Int",
			"indicator": "Red" if blocked_customers else "Green"},
	]


def get_columns():
	return [
		# Customer name on a customer row, Sales Order number on an order row;
		# the JS formatter makes each a link to its own document.
		{"fieldname": "label", "label": _("Customer / Sales Order"), "fieldtype": "Data", "width": 240},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Data", "width": 75},
		{"fieldname": "verdict", "label": _("Verdict"), "fieldtype": "Data", "width": 100},
		{"fieldname": "credit_meter", "label": _("Credit Used"), "fieldtype": "Data", "width": 170},
		# The customer's newest invoice, from an order or not; on customer rows only.
		{"fieldname": "last_invoice", "label": _("Last Invoice"), "fieldtype": "Link",
			"options": "Sales Invoice", "width": 160},
		{"fieldname": "last_invoice_miti", "label": _("Last Invoice Miti"), "fieldtype": "Data",
			"width": 125},
		{"fieldname": "last_invoice_qty", "label": _("Last Invoice Qty"), "fieldtype": "Float",
			"width": 120},
		{"fieldname": "miti", "label": _("Miti"), "fieldtype": "Data", "width": 95},
		{"fieldname": "item", "label": _("Item"), "fieldtype": "Data", "width": 150},
		{"fieldname": "pending_qty", "label": _("Pending Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "qty_can_bill", "label": _("Qty Can Bill Now"), "fieldtype": "Float", "width": 125},
		{"fieldname": "today_rate", "label": _("Today's Rate"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "order_rate", "label": _("Order Rate"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "to_bill", "label": _("To Bill at Today's Rate"), "fieldtype": "Currency",
			"width": 155},
		{"fieldname": "can_bill", "label": _("Can Bill Now"), "fieldtype": "Currency", "width": 125},
		{"fieldname": "short_by", "label": _("Held Back"), "fieldtype": "Currency", "width": 115},
		{"fieldname": "reason", "label": _("Why"), "fieldtype": "Data", "width": 300},
		{"fieldname": "order_qty", "label": _("Order Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "billed_qty", "label": _("Billed Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "to_bill_order", "label": _("To Bill at Order Rate"), "fieldtype": "Currency",
			"width": 145},
		{"fieldname": "bills", "label": _("Unpaid Bills / Limit"), "fieldtype": "Data", "width": 135},
		{"fieldname": "days", "label": _("Days / Limit"), "fieldtype": "Data", "width": 100},
		{"fieldname": "amount_limit", "label": _("Amount Limit"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "credit_left", "label": _("Credit Left"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 95},
	]
