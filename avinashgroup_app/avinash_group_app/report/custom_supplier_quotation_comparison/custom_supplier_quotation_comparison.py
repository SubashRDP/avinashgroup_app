# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt


def _as_list(value):
	"""Normalize a MultiSelectList/Link filter value (list, JSON string, or single) to a list."""
	if not value:
		return []
	if isinstance(value, str):
		value = value.strip()
		if value.startswith("["):
			try:
				value = json.loads(value)
			except Exception:
				return [value]
		else:
			return [value]
	if isinstance(value, (list, tuple, set)):
		return [v for v in value if v]
	return [value]


@frappe.whitelist()
def get_company_suppliers(company=None, txt=None):
	"""Supplier options scoped to the selected company via the supplier's custom_company."""
	company = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = ["(sup.name LIKE %(txt)s OR sup.supplier_name LIKE %(txt)s)"]
	values = {"txt": like}
	if company:
		conditions.append("(sup.custom_company IN %(company)s OR COALESCE(sup.custom_company, '') = '')")
		values["company"] = tuple(company)
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT sup.name AS value, sup.supplier_name AS description
		FROM `tabSupplier` sup
		WHERE {where}
		ORDER BY sup.supplier_name
		LIMIT 50
		""",
		values,
		as_dict=True,
	)


def execute(filters=None):
	if not filters:
		return [], []

	validate_filters(filters)

	# Get raw data
	supplier_quotation_data = get_data(filters)

	# Prepare pivoted data and get list of suppliers
	data, suppliers, supplier_display_name = prepare_pivoted_data(supplier_quotation_data, filters)

	# Generate columns dynamically based on suppliers found
	columns = get_columns(filters, suppliers, supplier_display_name)

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
			sq.supplier.as_("supplier_id"),
			sq.supplier_name,
			sq.valid_till,
			sq.transaction_date,
			sq.taxes_and_charges,
			sq.discount_amount,
			sq.apply_discount_on,
			sq.additional_discount_percentage,
			sq.grand_total,
			sq.base_grand_total,
			sq.total,
			sq.base_total,
			sq.total_taxes_and_charges,
			sq.base_total_taxes_and_charges,
		)
		.where(
			(sq_item.parent == sq.name)
			& (sq_item.docstatus < 2)
			& (sq.company == filters.get("company"))
			& (sq.transaction_date.between(filters.get("from_date"), filters.get("to_date")))
		)
		.orderby(sq_item.item_code, sq.supplier)
	)

	# Source-document filter. A Supplier Quotation Item links directly to the
	# Material Request it was raised from. A Purchase Order carries the Material
	# Request on its item lines rather than on the quotation, so we resolve the PO
	# to its Material Request(s) and match on the same column. When both filters are
	# set we take the union — "show quotations for any of these source documents".
	material_requests = _as_list(filters.get("material_request"))
	if filters.get("purchase_order"):
		material_requests += get_material_requests_from_purchase_order(filters.get("purchase_order"))
	material_requests = [mr for mr in dict.fromkeys(material_requests) if mr]
	if material_requests:
		query = query.where(sq_item.material_request.isin(material_requests))

	if filters.get("item_code"):
		query = query.where(sq_item.item_code == filters.get("item_code"))

	if filters.get("supplier_quotation"):
		query = query.where(sq_item.parent.isin(filters.get("supplier_quotation")))

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
	Transform row-based data into pivoted format with totals:
	- Items as rows
	- Suppliers as columns
	- Subtotal, discount, tax, and invoice total rows
	"""
	
	# ============================================
	# CONFIGURABLE: Change this to use different price field
	# Options: 'base_rate', 'base_amount', 'rate', 'amount'
	# ============================================
	price_field = filters.get("price_field", "base_amount")
	
	float_precision = cint(frappe.db.get_default("float_precision")) or 2
	
	# Data structures for pivot
	item_supplier_map = defaultdict(lambda: defaultdict(dict))
	supplier_quotation_map = {}  # Store quotation-level data per supplier
	all_suppliers = set()
	supplier_display_name = {}  # Map supplier_id -> display name
	all_items = []  # Maintain order
	item_meta = {}  # Store item metadata
	seen_items = set()

	# Process each quotation line
	for row in supplier_quotation_data:
		item_code = row.get("item_code")
		supplier = row.get("supplier_id")
		supplier_display_name[supplier] = row.get("supplier_name") or supplier
		quotation_name = row.get("parent")
		
		# Get price value based on configured field
		price_value = flt(row.get(price_field), float_precision)
		
		all_suppliers.add(supplier)
		
		if item_code not in seen_items:
			all_items.append(item_code)
			seen_items.add(item_code)
		
		# Store item metadata (use first occurrence)
		if item_code not in item_meta:
			item_meta[item_code] = {
				"item_name": row.get("item_name"),
				"qty": row.get("qty"),
				"uom": row.get("uom"),
			}
		
		# Store item-supplier price
		if supplier not in item_supplier_map[item_code]:
			item_supplier_map[item_code][supplier] = {
				"price": price_value,
				"qty": row.get("qty"),
				"quotation": quotation_name,
			}
		else:
			# If multiple quotations, keep the one with lowest price
			if price_value < item_supplier_map[item_code][supplier]["price"]:
				item_supplier_map[item_code][supplier] = {
					"price": price_value,
					"qty": row.get("qty"),
					"quotation": quotation_name,
				}
		
		# Store quotation-level data (discount, taxes) per supplier
		if supplier not in supplier_quotation_map:
			supplier_quotation_map[supplier] = {
				"quotation": quotation_name,
				"discount_amount": flt(row.get("discount_amount"), float_precision),
				"additional_discount_percentage": flt(row.get("additional_discount_percentage"), float_precision),
				"total": flt(row.get("base_total"), float_precision),
				"total_taxes": flt(row.get("base_total_taxes_and_charges"), float_precision),
				"grand_total": flt(row.get("base_grand_total"), float_precision),
				"apply_discount_on": row.get("apply_discount_on"),
			}

	# Sort suppliers alphabetically for consistent column order
	suppliers = sorted(list(all_suppliers))
	
	# Build output rows
	data = []
	sn = 1
	supplier_totals = {supplier: 0 for supplier in suppliers}
	
	# Item rows
	for item_code in all_items:
		row = {
			"sn": sn,
			"item_code": item_code,
			"item_name": item_meta[item_code]["item_name"],
			"qty": item_meta[item_code]["qty"],
			"is_data_row": 1,  # Mark as data row for styling
		}
		
		sn += 1
		
		# Add supplier prices as columns
		for supplier in suppliers:
			col_fieldname = frappe.scrub(supplier)
			
			if supplier in item_supplier_map[item_code]:
				supplier_data = item_supplier_map[item_code][supplier]
				price = supplier_data["price"]
				row[col_fieldname] = price
				supplier_totals[supplier] += price
			else:
				row[col_fieldname] = None
		
		data.append(row)
	
	# ============================================
	# SUMMARY ROWS
	# ============================================
	
	# Total row (Net Total)
	total_row = {
		"sn": None,
		"item_code": None,
		"item_name": None,
		"qty": "Total",
		"is_total_row": 1,
	}
	for supplier in suppliers:
		col_fieldname = frappe.scrub(supplier)
		total_row[col_fieldname] = supplier_totals[supplier]
	data.append(total_row)
	
	# Discount on Net Total row
	discount_net_row = {
		"sn": None,
		"item_code": None,
		"item_name": None,
		"qty": "Less: Discount (on Net Total)",
		"is_summary_row": 1,
	}
	for supplier in suppliers:
		col_fieldname = frappe.scrub(supplier)
		discount_amount = 0
		
		if supplier in supplier_quotation_map:
			sq_data = supplier_quotation_map[supplier]
			apply_on = sq_data.get("apply_discount_on")
			
			# Only show discount here if it's applied on Net Total
			if apply_on == "Net Total":
				discount_amount = flt(sq_data.get("discount_amount", 0), float_precision)
		
		discount_net_row[col_fieldname] = discount_amount
	data.append(discount_net_row)
	
	# Taxable Amount row (after net discount)
	taxable_row = {
		"sn": None,
		"item_code": None,
		"item_name": None,
		"qty": "Taxable Amount",
		"is_summary_row": 1,
	}
	for supplier in suppliers:
		col_fieldname = frappe.scrub(supplier)
		total = total_row[col_fieldname]
		discount = discount_net_row[col_fieldname]
		taxable_row[col_fieldname] = total - discount
	data.append(taxable_row)
	
	# VAT/Tax row
	vat_row = {
		"sn": None,
		"item_code": None,
		"item_name": None,
		"qty": "Add: VAT",
		"is_summary_row": 1,
	}
	for supplier in suppliers:
		col_fieldname = frappe.scrub(supplier)
		if supplier in supplier_quotation_map:
			vat_row[col_fieldname] = flt(supplier_quotation_map[supplier].get("total_taxes", 0), float_precision)
		else:
			vat_row[col_fieldname] = 0
	data.append(vat_row)
	
	# Discount on Grand Total row (NEW)
	discount_grand_row = {
		"sn": None,
		"item_code": None,
		"item_name": None,
		"qty": "Less: Discount (on Grand Total)",
		"is_summary_row": 1,
	}
	for supplier in suppliers:
		col_fieldname = frappe.scrub(supplier)
		discount_amount = 0
		
		if supplier in supplier_quotation_map:
			sq_data = supplier_quotation_map[supplier]
			apply_on = sq_data.get("apply_discount_on")
			
			# Only show discount here if it's applied on Grand Total
			if apply_on == "Grand Total":
				discount_amount = flt(sq_data.get("discount_amount", 0), float_precision)
		
		discount_grand_row[col_fieldname] = discount_amount
	data.append(discount_grand_row)
	
	# Invoice Amount row (Grand Total) - use DB value directly
	invoice_row = {
		"sn": None,
		"item_code": None,
		"item_name": None,
		"qty": "Invoice Amount",
		"is_invoice_row": 1,
	}
	for supplier in suppliers:
		col_fieldname = frappe.scrub(supplier)
		if supplier in supplier_quotation_map:
			# Use grand_total directly from database
			invoice_row[col_fieldname] = flt(supplier_quotation_map[supplier].get("grand_total", 0), float_precision)
		else:
			# Fallback calculation if no quotation data
			taxable = taxable_row[col_fieldname]
			vat = vat_row[col_fieldname]
			discount_grand = discount_grand_row[col_fieldname]
			invoice_row[col_fieldname] = taxable + vat - discount_grand
	data.append(invoice_row)

	return data, suppliers, supplier_display_name


def get_columns(filters, suppliers, supplier_display_name=None):
	"""
	Generate columns dynamically:
	- Fixed columns for SN, item info, qty
	- Dynamic columns for each supplier
	"""
	company_currency = frappe.get_cached_value("Company", filters.get("company"), "default_currency")
	
	# Fixed columns
	columns = [
		{
			"fieldname": "sn",
			"label": _("SN"),
			"fieldtype": "Int",
			"width": 50,
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"fieldname": "qty",
			"label": _("Qty"),
			"fieldtype": "Data",  # Data type to allow "Total" text
			"width": 100,
		},
	]
	
	# Dynamic supplier columns
	for i, supplier in enumerate(sorted(suppliers), 1):
		col_fieldname = frappe.scrub(supplier)
		display = (supplier_display_name or {}).get(supplier, supplier)
		columns.append({
			"fieldname": col_fieldname,
			"label": display,
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"width": 120,
		})
	
	return columns


def get_message():
	"""Return report message/legend"""
	return f"""<span class="indicator blue">
		{_("Comparison sheet showing item-wise quotations from all suppliers")}
		</span>
		<br>
		<span class="indicator">
		{_("Total includes all item amounts before discount")}
		</span>"""


# ============================================
# Utility Functions
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
def get_material_requests_from_purchase_order(purchase_order):
	"""Material Request(s) a Purchase Order was raised from, read off its item lines.

	The approval workflow runs on the Purchase Order; approvers open the comparison
	from there. A PO may draw on more than one Material Request, so this returns a
	list and get_data() matches Supplier Quotation Items against all of them.
	"""
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT poi.material_request
		FROM `tabPurchase Order Item` poi
		WHERE poi.parent = %s AND poi.material_request IS NOT NULL
		""",
		purchase_order,
	)
	return [r[0] for r in rows]