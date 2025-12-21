# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt


def execute(filters=None):
	if not filters:
		return [], []

	validate_filters(filters)

	# Get raw data
	supplier_quotation_data = get_data(filters)

	# Prepare pivoted data and get list of suppliers
	data, suppliers = prepare_pivoted_data(supplier_quotation_data, filters)

	# Generate columns dynamically based on suppliers found
	columns = get_columns(filters, suppliers)

	message = get_message()

	return columns, data, message, None


def validate_filters(filters):
	"""Validate and normalize filters"""
	if not filters.get("categorize_by") and filters.get("group_by"):
		filters["categorize_by"] = filters["group_by"]
		filters["categorize_by"] = filters["categorize_by"].replace("Group by", "Categorize by")


def get_data(filters):
	"""Fetch supplier quotation data from database"""
	sq = frappe.qb.DocType("Supplier Quotation")
	sq_item = frappe.qb.DocType("Supplier Quotation Item")

	query = (
		frappe.qb.from_(sq_item)
		.from_(sq)
		.select(
			sq_item.parent,
			sq_item.item_code,
			sq_item.item_name,
			sq_item.qty,
			sq.currency,
			sq_item.stock_qty,
			sq_item.amount,
			sq_item.rate,
			sq_item.base_rate,
			sq_item.base_amount,
			sq.price_list_currency,
			sq_item.uom,
			sq_item.stock_uom,
			sq_item.request_for_quotation,
			sq_item.lead_time_days,
			sq.supplier.as_("supplier_name"),
			sq.valid_till,
			sq.transaction_date,
		)
		.where(
			(sq_item.parent == sq.name)
			& (sq_item.docstatus < 2)
			& (sq.company == filters.get("company"))
			& (sq.transaction_date.between(filters.get("from_date"), filters.get("to_date")))
		)
		.orderby(sq_item.item_code, sq.supplier)
	)

	if filters.get("item_code"):
		query = query.where(sq_item.item_code == filters.get("item_code"))

	if filters.get("supplier_quotation"):
		query = query.where(sq_item.parent.isin(filters.get("supplier_quotation")))

	if filters.get("request_for_quotation"):
		query = query.where(sq_item.request_for_quotation == filters.get("request_for_quotation"))

	if filters.get("supplier"):
		query = query.where(sq.supplier.isin(filters.get("supplier")))

	if filters.get("preferred_quotation"):
		query = query.where(sq.custom_preferred_quotation == 1)

	if not filters.get("include_expired"):
		query = query.where(sq.status != "Expired")

	supplier_quotation_data = query.run(as_dict=True)

	return supplier_quotation_data


def prepare_pivoted_data(supplier_quotation_data, filters):
	"""
	Transform row-based data into pivoted format:
	- Items as rows
	- Suppliers as columns
	- Price values in cells
	"""
	
	# ============================================
	# CONFIGURABLE: Change this to use different price field
	# Options: 'base_rate', 'base_amount', 'rate', 'amount', 'price_per_unit'
	# ============================================
	price_field = filters.get("price_field", "base_rate")
	
	float_precision = cint(frappe.db.get_default("float_precision")) or 2
	
	# Data structures for pivot
	item_supplier_map = defaultdict(lambda: defaultdict(dict))
	all_suppliers = set()
	all_items = set()
	item_meta = {}  # Store item metadata (name, uom, etc.)

	# Process each quotation line
	for row in supplier_quotation_data:
		item_code = row.get("item_code")
		supplier = row.get("supplier_name")
		qty = row.get("qty")
		
		# Calculate price per unit if needed
		if price_field == "price_per_unit":
			price_value = flt(row.get("amount"), float_precision) / (flt(row.get("stock_qty")) or 1)
		else:
			price_value = flt(row.get(price_field), float_precision)
		
		all_suppliers.add(supplier)
		all_items.add(item_code)
		
		# Store item metadata (use first occurrence)
		if item_code not in item_meta:
			item_meta[item_code] = {
				"item_name": row.get("item_name"),
				"uom": row.get("uom"),
				"stock_uom": row.get("stock_uom"),
			}
		
		# For same item-supplier combination, keep the best price (lowest)
		# Or you can keep latest by transaction_date
		key = f"{qty}"  # Use qty as sub-key if you want to track different quantities
		
		if supplier not in item_supplier_map[item_code]:
			item_supplier_map[item_code][supplier] = {
				"price": price_value,
				"qty": qty,
				"quotation": row.get("parent"),
				"lead_time_days": row.get("lead_time_days"),
				"valid_till": row.get("valid_till"),
			}
		else:
			# Keep lower price
			existing_price = item_supplier_map[item_code][supplier].get("price", float('inf'))
			if price_value < existing_price:
				item_supplier_map[item_code][supplier] = {
					"price": price_value,
					"qty": qty,
					"quotation": row.get("parent"),
					"lead_time_days": row.get("lead_time_days"),
					"valid_till": row.get("valid_till"),
				}

	# Sort suppliers alphabetically for consistent column order
	suppliers = sorted(list(all_suppliers))
	
	# Build output rows
	data = []
	for item_code in sorted(all_items):
		row = {
			"item_code": item_code,
			"item_name": item_meta[item_code]["item_name"],
			"uom": item_meta[item_code]["uom"],
		}
		
		# Add supplier prices as columns
		for supplier in suppliers:
			col_fieldname = frappe.scrub(supplier)
			
			if supplier in item_supplier_map[item_code]:
				supplier_data = item_supplier_map[item_code][supplier]
				row[col_fieldname] = supplier_data["price"]
				
				# Optional: Store additional data for tooltips/details
				# You can add more fields like quotation number, lead time etc.
				row[f"{col_fieldname}_qty"] = supplier_data.get("qty")
				row[f"{col_fieldname}_quotation"] = supplier_data.get("quotation")
				row[f"{col_fieldname}_lead_time"] = supplier_data.get("lead_time_days")
			else:
				# No quotation from this supplier for this item
				row[col_fieldname] = None
		
		# Calculate min price across suppliers for highlighting
		prices = [
			item_supplier_map[item_code][s]["price"] 
			for s in suppliers 
			if s in item_supplier_map[item_code]
		]
		if prices:
			min_price = min(prices)
			row["min_price"] = min_price
			
			# Mark which supplier has minimum price
			for supplier in suppliers:
				col_fieldname = frappe.scrub(supplier)
				if row.get(col_fieldname) == min_price:
					row[f"{col_fieldname}_is_min"] = 1
		
		data.append(row)

	return data, suppliers


def get_columns(filters, suppliers):
	"""
	Generate columns dynamically:
	- Fixed columns for item info
	- Dynamic columns for each supplier
	"""
	company_currency = frappe.get_cached_value("Company", filters.get("company"), "default_currency")
	
	# Fixed columns
	columns = [
		{
			"fieldname": "item_code",
			"label": _("Item Code"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"fieldname": "uom",
			"label": _("UOM"),
			"fieldtype": "Link",
			"options": "UOM",
			"width": 80,
		},
	]
	
	# Dynamic supplier columns
	for supplier in sorted(suppliers):
		col_fieldname = frappe.scrub(supplier)
		columns.append({
			"fieldname": col_fieldname,
			"label": _(supplier),
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"width": 120,
		})
	
	return columns


def get_message():
	"""Return report message/legend"""
	return f"""<span class="indicator">
		{_("Prices shown are Base Rate (company currency)")}
		</span>
		<br>
		<span class="indicator green">
		{_("Lowest price is highlighted")}
		</span>"""


# ============================================
# Utility Functions (Keep existing)
# ============================================

@frappe.whitelist()
def set_default_supplier(item_code, supplier, company):
	"""Set default supplier for an item"""
	frappe.db.set_value(
		"Item Default",
		{"parent": item_code, "company": company},
		"default_supplier",
		supplier,
	)


@frappe.whitelist()
def get_rfq_from_purchase_order(purchase_order):
	"""Get RFQ linked to a Purchase Order"""
	rfq = frappe.db.sql("""
		SELECT DISTINCT sqi.request_for_quotation
		FROM `tabPurchase Order Item` poi
		JOIN `tabSupplier Quotation Item` sqi
			ON poi.supplier_quotation = sqi.parent
		WHERE poi.parent = %s and sqi.request_for_quotation IS NOT NULL
	""", purchase_order)

	return rfq[0][0] if rfq else None