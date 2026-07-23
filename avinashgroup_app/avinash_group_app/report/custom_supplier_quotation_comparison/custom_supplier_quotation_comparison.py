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


def _sq_filter_scope(company=None, purchase_order=None, material_request=None,
					 supplier_quotation=None, supplier=None, item_code=None):
	"""Shared WHERE fragments (aliases sq / sqi) limiting quotation rows to the
	report's current filter context. The filter-option endpoints below all build
	on this so every dropdown only offers values that can actually appear in the
	report for the chosen Purchase Order / Material Request / company."""
	conditions = ["sqi.parent = sq.name", "sqi.docstatus < 2"]
	values = {}

	if company:
		conditions.append("sq.company = %(company)s")
		values["company"] = company

	material_requests = _as_list(material_request)
	if purchase_order:
		material_requests += get_material_requests_from_purchase_order(purchase_order)
	material_requests = [mr for mr in dict.fromkeys(material_requests) if mr]
	if material_requests:
		conditions.append("sqi.material_request IN %(material_requests)s")
		values["material_requests"] = tuple(material_requests)

	quotations = _as_list(supplier_quotation)
	if quotations:
		conditions.append("sq.name IN %(quotations)s")
		values["quotations"] = tuple(quotations)

	suppliers = _as_list(supplier)
	if suppliers:
		conditions.append("sq.supplier IN %(suppliers)s")
		values["suppliers"] = tuple(suppliers)

	if item_code:
		conditions.append("sqi.item_code = %(item_code)s")
		values["item_code"] = item_code

	return conditions, values


@frappe.whitelist()
def get_filter_suppliers(company=None, purchase_order=None, material_request=None,
						 supplier_quotation=None, item_code=None, txt=None):
	"""Supplier options: only suppliers with a quotation in the current scope."""
	conditions, values = _sq_filter_scope(
		company=company, purchase_order=purchase_order, material_request=material_request,
		supplier_quotation=supplier_quotation, item_code=item_code,
	)
	conditions.append("(sq.supplier LIKE %(txt)s OR sq.supplier_name LIKE %(txt)s)")
	values["txt"] = f"%{(txt or '').strip()}%"

	return frappe.db.sql(
		f"""
		SELECT DISTINCT sq.supplier AS value, sq.supplier_name AS description
		FROM `tabSupplier Quotation` sq, `tabSupplier Quotation Item` sqi
		WHERE {" AND ".join(conditions)}
		ORDER BY sq.supplier_name
		LIMIT 50
		""",
		values,
		as_dict=True,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_filter_items(doctype, txt, searchfield, start, page_len, filters):
	"""Item link-query: only items quoted in the current scope."""
	filters = filters or {}
	conditions, values = _sq_filter_scope(
		company=filters.get("company"),
		purchase_order=filters.get("purchase_order"),
		material_request=filters.get("material_request"),
		supplier_quotation=filters.get("supplier_quotation"),
		supplier=filters.get("supplier"),
	)
	conditions.append("(sqi.item_code LIKE %(txt)s OR sqi.item_name LIKE %(txt)s)")
	values.update({"txt": f"%{(txt or '').strip()}%", "start": cint(start), "page_len": cint(page_len) or 20})

	return frappe.db.sql(
		f"""
		SELECT DISTINCT sqi.item_code, sqi.item_name
		FROM `tabSupplier Quotation` sq, `tabSupplier Quotation Item` sqi
		WHERE {" AND ".join(conditions)}
		ORDER BY sqi.item_name
		LIMIT %(start)s, %(page_len)s
		""",
		values,
	)


@frappe.whitelist()
def get_supplier_quotations(company=None, purchase_order=None, material_request=None,
							supplier=None, item_code=None, txt=None):
	"""Supplier Quotation options: only quotations in the current scope."""
	conditions, values = _sq_filter_scope(
		company=company, purchase_order=purchase_order, material_request=material_request,
		supplier=supplier, item_code=item_code,
	)
	conditions.append("(sq.name LIKE %(txt)s OR sq.supplier_name LIKE %(txt)s)")
	values["txt"] = f"%{(txt or '').strip()}%"

	return frappe.db.sql(
		f"""
		SELECT DISTINCT sq.name AS value, sq.supplier_name AS description
		FROM `tabSupplier Quotation` sq, `tabSupplier Quotation Item` sqi
		WHERE {" AND ".join(conditions)}
		ORDER BY sq.transaction_date DESC
		LIMIT 50
		""",
		values,
		as_dict=True,
	)


def execute(filters=None):
	if not filters:
		return [], []

	# Get raw data
	supplier_quotation_data = get_data(filters)

	# Prepare pivoted data and get list of suppliers
	data, suppliers, supplier_display_name, supplier_sq_map = prepare_pivoted_data(
		supplier_quotation_data, filters
	)

	# Generate columns dynamically based on suppliers found
	columns = get_columns(filters, suppliers, supplier_display_name, supplier_sq_map)

	message = get_message()

	return columns, data, message, None


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
		.orderby(sq_item.item_code, sq.supplier)
	)

	query = (
		query
		.where(
			(sq_item.parent == sq.name)
			& (sq_item.docstatus < 2)
			& (sq.company == filters.get("company"))
			& (sq.transaction_date.between(filters.get("from_date"), filters.get("to_date")))
		)
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
	rate_field = "base_rate" if price_field.startswith("base_") else "rate"

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
		rate_value = flt(row.get(rate_field), float_precision)

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
				"rate": rate_value,
				"qty": row.get("qty"),
				"quotation": quotation_name,
			}
		else:
			# If multiple quotations, keep the one with lowest price
			if price_value < item_supplier_map[item_code][supplier]["price"]:
				item_supplier_map[item_code][supplier] = {
					"price": price_value,
					"rate": rate_value,
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

		# Add supplier rate + amount as columns
		for supplier in suppliers:
			col_fieldname = frappe.scrub(supplier)

			if supplier in item_supplier_map[item_code]:
				supplier_data = item_supplier_map[item_code][supplier]
				price = supplier_data["price"]
				row[col_fieldname + "_rate"] = supplier_data["rate"]
				row[col_fieldname] = price
				supplier_totals[supplier] += price
			else:
				row[col_fieldname + "_rate"] = None
				row[col_fieldname] = None

		data.append(row)
	
	# ============================================
	# SUMMARY ROWS
	# ============================================
	
	def summary_row(label, **flags):
		return {"sn": None, "item_code": None, "item_name": None, "qty": label, **flags}

	def has_value(row):
		"""True if any supplier column in the row is non-zero."""
		return any(flt(row[frappe.scrub(s)]) for s in suppliers)

	# Total row (Net Total)
	total_row = summary_row("Total", is_total_row=1)
	for supplier in suppliers:
		col_fieldname = frappe.scrub(supplier)
		total_row[col_fieldname] = supplier_totals[supplier]
	data.append(total_row)

	# Discount on Net Total row
	discount_net_row = summary_row("Less: Discount (on Net Total)", is_summary_row=1)
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
	if has_value(discount_net_row):
		data.append(discount_net_row)

	# Taxable Amount row (after net discount) - always shown
	taxable_row = summary_row("Taxable Amount", is_summary_row=1)
	for supplier in suppliers:
		col_fieldname = frappe.scrub(supplier)
		total = total_row[col_fieldname]
		discount = discount_net_row[col_fieldname]
		taxable_row[col_fieldname] = total - discount
	data.append(taxable_row)

	# VAT/Tax row
	vat_row = summary_row("Add: VAT", is_summary_row=1)
	for supplier in suppliers:
		col_fieldname = frappe.scrub(supplier)
		if supplier in supplier_quotation_map:
			vat_row[col_fieldname] = flt(supplier_quotation_map[supplier].get("total_taxes", 0), float_precision)
		else:
			vat_row[col_fieldname] = 0
	if has_value(vat_row):
		data.append(vat_row)

	# Discount on Grand Total row
	discount_grand_row = summary_row("Less: Discount (on Grand Total)", is_summary_row=1)
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
	if has_value(discount_grand_row):
		data.append(discount_grand_row)

	# Invoice Amount row (Grand Total) - use DB value directly, always shown
	invoice_row = summary_row("Invoice Amount", is_invoice_row=1)
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

	# supplier -> quotation name, used to link the column header to the document
	supplier_sq_map = {s: supplier_quotation_map[s]["quotation"] for s in supplier_quotation_map}

	return data, suppliers, supplier_display_name, supplier_sq_map


def get_columns(filters, suppliers, supplier_display_name=None, supplier_sq_map=None):
	"""
	Generate columns dynamically:
	- Fixed columns for SN, item info, qty
	- Dynamic Rate + Amount columns for each supplier
	- Each supplier column carries `sq_link` (its Supplier Quotation name) so the
	  client script can open the quotation when the header is clicked
	"""
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

	# Dynamic supplier columns. Each supplier contributes a Rate + Amount pair;
	# `supplier_group` carries the supplier's display name so the client script
	# (and the approval-email renderer) can draw it as one spanning header cell
	# above the two columns.
	for supplier in sorted(suppliers):
		col_fieldname = frappe.scrub(supplier)
		display = (supplier_display_name or {}).get(supplier, supplier)
		sq_link = (supplier_sq_map or {}).get(supplier)
		columns.append({
			"fieldname": col_fieldname + "_rate",
			"label": _("Rate"),
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"width": 110,
			"sq_link": sq_link,
			"supplier_group": display,
		})
		columns.append({
			"fieldname": col_fieldname,
			"label": _("Amount"),
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"width": 130,
			"sq_link": sq_link,
			"supplier_group": display,
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
		</span>
		<br>
		<span class="indicator green">
		{_("Click a supplier column header to open its Supplier Quotation")}
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