# Copyright (c) 2026, Avinash Group and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.nestedset import get_descendants_of

from erpnext.stock.report.stock_balance.stock_balance import StockBalanceReport


def execute(filters=None):
	if filters.get("show_zero_values"):
		# Also keep items that stocked out during the period, so they show
		# their real warehouse rows instead of a bare zero row.
		filters["include_zero_stock_items"] = 1

	columns, data = StockBalanceReport(filters).run()

	if filters.get("show_zero_values"):
		data += get_never_transacted_item_rows(filters, data)

	return columns, data


def get_never_transacted_item_rows(filters, data):
	"""One all-zero row per stock item that has no Stock Ledger Entry rows in the report.

	Items are scoped to the selected company via Item.custom_company; items with a
	blank custom_company are treated as shared and always included.
	"""
	items_in_report = {row.get("item_code") for row in data}

	item_filters = {"is_stock_item": 1, "disabled": 0, "has_variants": 0}

	if (company := filters.get("company")) and frappe.db.has_column("Item", "custom_company"):
		item_filters["custom_company"] = ["in", [company, ""]]

	if item_group := filters.get("item_group"):
		children = get_descendants_of("Item Group", item_group, ignore_permissions=True)
		item_filters["item_group"] = ["in", [*children, item_group]]

	if item_codes := filters.get("item_code"):
		item_filters["name"] = ["in", item_codes]

	if brand := filters.get("brand"):
		item_filters["brand"] = brand

	items = frappe.get_all(
		"Item",
		filters=item_filters,
		fields=["name", "item_name", "item_group", "stock_uom"],
		order_by="name",
	)

	zero_rows = []
	for item in items:
		if item.name in items_in_report:
			continue

		zero_rows.append(
			frappe._dict(
				{
					"item_code": item.name,
					"item_name": item.item_name,
					"item_group": item.item_group,
					"warehouse": None,
					"company": filters.get("company"),
					"stock_uom": item.stock_uom,
					"opening_qty": 0.0,
					"opening_val": 0.0,
					"in_qty": 0.0,
					"in_val": 0.0,
					"out_qty": 0.0,
					"out_val": 0.0,
					"bal_qty": 0.0,
					"bal_val": 0.0,
					"val_rate": 0.0,
					"reserved_stock": 0.0,
				}
			)
		)

	return zero_rows


@frappe.whitelist()
def get_company_items(company=None, item_group=None, txt=None):
	"""Item options for the Items filter, scoped to the selected company via
	Item.custom_company. Items with a blank custom_company are shared and always shown."""
	like = f"%{(txt or '').strip()}%"
	conditions = [
		"(it.name LIKE %(txt)s OR it.item_name LIKE %(txt)s)",
		"it.is_stock_item = 1",
		"it.disabled = 0",
		"it.has_variants = 0",
	]
	values = {"txt": like}

	if company and frappe.db.has_column("Item", "custom_company"):
		conditions.append("(it.custom_company = %(company)s OR COALESCE(it.custom_company, '') = '')")
		values["company"] = company

	if item_group:
		conditions.append("it.item_group = %(item_group)s")
		values["item_group"] = item_group

	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT it.name AS value, it.item_name AS label, it.name AS description
		FROM `tabItem` it
		WHERE {where}
		ORDER BY it.item_name
		LIMIT 50
		""",
		values,
		as_dict=True,
	)
