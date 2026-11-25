# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt
"""Inventory Report: stock position, value, performance and reorder need in one row.

Why it exists: the Material In Out Report reads purchase and sales documents and
splits rows by transaction UOM and price list. Purchases carry no price list and
are bought in Kg / MT while sales go out as 14.2 KG cylinders, so those rows never
meet and "stock on hand" cannot be read from it. This report reads the Stock
Ledger Entry instead, where every movement is already in the item's stock UOM,
and lays out the four standard inventory report sections side by side:

    In / Out      Opening, In (purchased), Out (sold), Transfer / Adjust, Closing
    Value         Rate (last purchase rate), Closing Value
    Performance   Turnover, Days of Cover, Sell-Through %, Last In / Last Out, Movement
    Forecast      Next-Period Need, Suggested Purchase, Status

The formulas and the reasoning behind each column are in
docs/inventory-report-standard.md. Keep the two in step.

Deliberately narrow:
- It does not revalue stock. ERPNext's own valuation_rate is 0 on the "(Sales)"
  warehouses here because they run negative (no transfers are posted from the
  purchase warehouse), so Rate is the last purchase incoming_rate for the
  company+item, not the SLE moving average. Stock Balance owns book valuation.
- It does not split by branch or price list. Those are sales dimensions and live
  in the Material In Out / sales reports; stock is held per warehouse.
- Negative closing stock is shown as it is and flagged, never clamped to zero:
  it means purchases, opening stock or transfers are missing from the books.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate

from avinashgroup_app.avinash_group_app.report.material_in_out_report.material_in_out_report import _as_list

# Voucher types whose movements are "In" (bought) and "Out" (sold). Returns are
# posted on the same voucher types with the opposite sign, so they net out here.
# Everything else (Stock Entry, Stock Reconciliation, ...) lands in Transfer / Adjust,
# which nets to zero across warehouses for a pure transfer.
IN_VOUCHERS = ("Purchase Receipt", "Purchase Invoice")
OUT_VOUCHERS = ("Delivery Note", "Sales Invoice")

# Filter defaults, mirrored in inventory_report.js.
DEFAULT_FORECAST_DAYS = 30  # one month of cover is the usual reorder horizon
DEFAULT_SLOW_DAYS = 90  # a quarter without a sale is the common "non-moving" cut-off

QTY_PRECISION = 3


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns(filters)

	companies = _as_list(filters.get("company"))
	if not companies:
		return columns, [], _("Please select a Company.")
	if not filters.get("from_date") or not filters.get("to_date"):
		return columns, [], _("Please select From Date and To Date.")
	if getdate(filters.from_date) > getdate(filters.to_date):
		return columns, [], _("From Date must be on or before To Date.")

	data = get_data(filters, companies)
	if data:
		data.append(total_row(data))
	return columns, data


def get_columns(filters):
	by_warehouse = filters.get("group_by") == "Warehouse"
	cols = [
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 160},
	]
	if by_warehouse:
		cols.append({"fieldname": "warehouse", "label": _("Warehouse"), "fieldtype": "Link", "options": "Warehouse", "width": 200})
	cols += [
		{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 130},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 200},
		{"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group", "width": 130},
		{"fieldname": "stock_uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 70},
		# In / Out
		{"fieldname": "opening_qty", "label": _("Opening"), "fieldtype": "Float", "width": 110, "precision": QTY_PRECISION},
		{"fieldname": "in_qty", "label": _("In (Purchased)"), "fieldtype": "Float", "width": 120, "precision": QTY_PRECISION},
		{"fieldname": "out_qty", "label": _("Out (Sold)"), "fieldtype": "Float", "width": 120, "precision": QTY_PRECISION},
		{"fieldname": "adjust_qty", "label": _("Transfer / Adjust"), "fieldtype": "Float", "width": 120, "precision": QTY_PRECISION},
		{"fieldname": "closing_qty", "label": _("Closing"), "fieldtype": "Float", "width": 120, "precision": QTY_PRECISION},
		# Value
		{"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "closing_value", "label": _("Closing Value"), "fieldtype": "Currency", "width": 140},
		# Performance
		{"fieldname": "avg_daily_out", "label": _("Avg Daily Out"), "fieldtype": "Float", "width": 110, "precision": 2},
		{"fieldname": "days_of_cover", "label": _("Days of Cover"), "fieldtype": "Float", "width": 100, "precision": 1},
		{"fieldname": "turnover", "label": _("Turnover"), "fieldtype": "Float", "width": 90, "precision": 2},
		{"fieldname": "sell_through", "label": _("Sell-Through %"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "last_in_date", "label": _("Last In"), "fieldtype": "Date", "width": 100},
		{"fieldname": "last_out_date", "label": _("Last Out"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_since_out", "label": _("Days Since Out"), "fieldtype": "Int", "width": 100},
		{"fieldname": "movement", "label": _("Movement"), "fieldtype": "Data", "width": 100},
		# Forecast / reorder
		{"fieldname": "next_need", "label": _("Next-Period Need"), "fieldtype": "Float", "width": 130, "precision": QTY_PRECISION},
		{"fieldname": "suggested_purchase", "label": _("Suggested Purchase"), "fieldtype": "Float", "width": 140, "precision": QTY_PRECISION},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
	]
	return cols


def _ledger(filters, companies):
	"""One row per company+warehouse+item with every quantity the report needs,
	read from Stock Ledger Entry up to To Date in a single pass."""
	conditions = ["sle.is_cancelled = 0", "sle.company IN %(companies)s", "sle.posting_date <= %(to_date)s"]
	values = {
		"companies": tuple(companies),
		"from_date": filters.from_date,
		"to_date": filters.to_date,
		"in_vouchers": IN_VOUCHERS,
		"out_vouchers": OUT_VOUCHERS,
	}
	items = _as_list(filters.get("item"))
	if items:
		conditions.append("sle.item_code IN %(items)s")
		values["items"] = tuple(items)
	warehouses = _as_list(filters.get("warehouse"))
	if warehouses:
		conditions.append("sle.warehouse IN %(warehouses)s")
		values["warehouses"] = tuple(warehouses)
	if filters.get("item_group"):
		lft, rgt = frappe.db.get_value("Item Group", filters.item_group, ["lft", "rgt"])
		conditions.append(
			"sle.item_code IN (SELECT it.name FROM `tabItem` it JOIN `tabItem Group` ig ON ig.name = it.item_group"
			" WHERE ig.lft >= %(ig_lft)s AND ig.rgt <= %(ig_rgt)s)"
		)
		values.update(ig_lft=lft, ig_rgt=rgt)

	return frappe.db.sql(
		f"""
		SELECT
			sle.company, sle.warehouse, sle.item_code,
			SUM(IF(sle.posting_date < %(from_date)s, sle.actual_qty, 0)) AS opening_qty,
			SUM(IF(sle.posting_date >= %(from_date)s AND sle.voucher_type IN %(in_vouchers)s, sle.actual_qty, 0)) AS in_qty,
			-SUM(IF(sle.posting_date >= %(from_date)s AND sle.voucher_type IN %(out_vouchers)s, sle.actual_qty, 0)) AS out_qty,
			SUM(IF(sle.posting_date >= %(from_date)s AND sle.voucher_type NOT IN %(in_vouchers)s
			       AND sle.voucher_type NOT IN %(out_vouchers)s, sle.actual_qty, 0)) AS adjust_qty,
			MAX(IF(sle.voucher_type IN %(in_vouchers)s AND sle.actual_qty > 0, sle.posting_date, NULL)) AS last_in_date,
			MAX(IF(sle.voucher_type IN %(out_vouchers)s AND sle.actual_qty < 0, sle.posting_date, NULL)) AS last_out_date
		FROM `tabStock Ledger Entry` sle
		WHERE {" AND ".join(conditions)}
		GROUP BY sle.company, sle.warehouse, sle.item_code
		""",
		values,
		as_dict=True,
	)


def _last_purchase_rates(companies, item_codes, to_date):
	"""{(company, item_code): incoming_rate} from the latest purchase SLE on or
	before To Date. incoming_rate is per stock UOM, so it multiplies Closing directly."""
	if not item_codes:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT company, item_code, incoming_rate FROM (
			SELECT company, item_code, incoming_rate,
				ROW_NUMBER() OVER (PARTITION BY company, item_code
				                   ORDER BY posting_datetime DESC, creation DESC) AS rn
			FROM `tabStock Ledger Entry`
			WHERE is_cancelled = 0 AND actual_qty > 0 AND incoming_rate > 0
			  AND voucher_type IN %(in_vouchers)s
			  AND company IN %(companies)s AND item_code IN %(items)s
			  AND posting_date <= %(to_date)s
		) t WHERE rn = 1
		""",
		{"in_vouchers": IN_VOUCHERS, "companies": tuple(companies), "items": tuple(item_codes), "to_date": to_date},
		as_dict=True,
	)
	return {(r.company, r.item_code): flt(r.incoming_rate) for r in rows}


def _merge(rows, by_warehouse):
	"""Fold warehouse rows into company+item rows unless grouping by warehouse.
	Transfers between the company's warehouses cancel out in Transfer / Adjust."""
	if by_warehouse:
		return {(r.company, r.warehouse, r.item_code): dict(r) for r in rows}
	merged = {}
	for r in rows:
		key = (r.company, None, r.item_code)
		m = merged.setdefault(key, {"company": r.company, "warehouse": None, "item_code": r.item_code,
		                            "opening_qty": 0, "in_qty": 0, "out_qty": 0, "adjust_qty": 0,
		                            "last_in_date": None, "last_out_date": None})
		for f in ("opening_qty", "in_qty", "out_qty", "adjust_qty"):
			m[f] += flt(r[f])
		for f in ("last_in_date", "last_out_date"):
			if r[f] and (not m[f] or r[f] > m[f]):
				m[f] = r[f]
	return merged


def get_data(filters, companies):
	by_warehouse = filters.get("group_by") == "Warehouse"
	forecast_days = int(filters.get("forecast_days") or DEFAULT_FORECAST_DAYS)
	slow_days = int(filters.get("slow_days") or DEFAULT_SLOW_DAYS)
	to_date = getdate(filters.to_date)
	period_days = date_diff(to_date, filters.from_date) + 1

	merged = _merge(_ledger(filters, companies), by_warehouse)
	item_codes = {k[2] for k in merged}
	rates = _last_purchase_rates(companies, item_codes, filters.to_date)
	item_info = {
		d.name: d
		for d in frappe.get_all("Item", filters=[["name", "in", list(item_codes) or [""]]],
		                        fields=["name", "item_name", "item_group", "stock_uom"])
	}

	rows = []
	for key in sorted(merged, key=lambda k: (k[0], k[1] or "", item_info.get(k[2], {}).get("item_name") or k[2])):
		r = merged[key]
		opening, inq, out, adj = (round(flt(r[f]), QTY_PRECISION) for f in ("opening_qty", "in_qty", "out_qty", "adjust_qty"))
		closing = round(opening + inq - out + adj, QTY_PRECISION)
		if not any((opening, inq, out, adj, closing)) and not filters.get("show_zero"):
			continue

		info = item_info.get(r["item_code"]) or frappe._dict()
		rate = rates.get((r["company"], r["item_code"]), 0)
		row = {
			"company": r["company"],
			"warehouse": r["warehouse"],
			"item_code": r["item_code"],
			"item_name": info.get("item_name"),
			"item_group": info.get("item_group"),
			"stock_uom": info.get("stock_uom"),
			"opening_qty": opening,
			"in_qty": inq,
			"out_qty": out,
			"adjust_qty": adj,
			"closing_qty": closing,
			"rate": rate,
			# Negative stock has no value: it is missing purchases, not a liability.
			"closing_value": closing * rate if closing > 0 else 0,
			"last_in_date": r["last_in_date"],
			"last_out_date": r["last_out_date"],
		}
		row.update(performance(row, period_days, forecast_days, slow_days, to_date))
		rows.append(row)
	return rows


def performance(row, period_days, forecast_days, slow_days, to_date):
	"""Performance, forecast and status columns for one row. Every ratio is left
	blank (None) rather than shown as 0 when its denominator is not positive, so a
	blank means "cannot be worked out", not "zero"."""
	opening, inq, out, closing = row["opening_qty"], row["in_qty"], row["out_qty"], row["closing_qty"]
	avg_daily_out = out / period_days if out > 0 else 0
	avg_stock = (opening + closing) / 2
	available = opening + inq

	days_of_cover = closing / avg_daily_out if avg_daily_out and closing > 0 else None
	days_since_out = date_diff(to_date, row["last_out_date"]) if row["last_out_date"] else None
	days_since_in = date_diff(to_date, row["last_in_date"]) if row["last_in_date"] else None
	next_need = avg_daily_out * forecast_days

	sold_recently = days_since_out is not None and days_since_out <= slow_days
	bought_recently = days_since_in is not None and days_since_in <= slow_days
	if not sold_recently and bought_recently:
		# Just bought and not sold yet: too early to call it dead.
		movement = "New"
	elif not sold_recently:
		movement = "Non-moving"
	elif days_of_cover is not None and days_of_cover > slow_days:
		movement = "Slow"
	else:
		movement = "Fast"

	if closing < 0:
		status = "Negative Stock"
	elif movement == "Non-moving" and closing > 0:
		status = "Dead Stock"
	elif closing == 0 and next_need > 0:
		status = "Out of Stock"
	elif closing < next_need:
		status = "Reorder"
	elif days_of_cover is not None and days_of_cover > slow_days:
		status = "Overstock"
	else:
		status = "OK"

	return {
		"avg_daily_out": avg_daily_out,
		"days_of_cover": days_of_cover,
		"turnover": out / avg_stock if avg_stock > 0 and out > 0 else None,
		"sell_through": out / available * 100 if available > 0 else None,
		"days_since_out": days_since_out,
		"movement": movement,
		"next_need": next_need,
		"suggested_purchase": max(0, next_need - max(closing, 0)),
		"status": status,
	}


def total_row(data):
	"""Value totals always; quantity totals only when every row shares one stock
	UOM, since adding Kg to Nos means nothing."""
	total = {"item_name": _("Total"), "bold": 1,
	         "closing_value": sum(flt(r["closing_value"]) for r in data)}
	if len({r["stock_uom"] for r in data}) == 1:
		for f in ("opening_qty", "in_qty", "out_qty", "adjust_qty", "closing_qty", "next_need", "suggested_purchase"):
			total[f] = sum(flt(r[f]) for r in data)
	return total
