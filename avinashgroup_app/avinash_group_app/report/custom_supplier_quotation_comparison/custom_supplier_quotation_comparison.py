# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
import os
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money


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
	elif purchase_order:
		# PO chosen but untraceable to any MR -> no quotation is aligned to it;
		# offer nothing rather than everything (mirrors get_data).
		conditions.append("1 = 0")

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
	(
		data,
		quotations,
		quotation_display_name,
		column_key,
		quotations_with_orders,
		quotations_with_narration,
	) = prepare_pivoted_data(supplier_quotation_data, filters)

	# Generate columns dynamically, one block per quotation found
	columns = get_columns(
		filters,
		quotations,
		quotation_display_name,
		column_key,
		quotations_with_orders,
		quotations_with_narration,
	)

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
			sq_item.custom_narration,
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
			sq.custom_specification,
			sq.custom_warrenty,
			sq.custom_payment_terms,
			sq.custom_delivery_period,
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
	elif filters.get("purchase_order"):
		# A Purchase Order was chosen but its item lines carry no material_request
		# link (created directly, not from an MR). Nothing is "aligned to this PO",
		# so show nothing - falling through would list every quotation in the window.
		return []

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
	- One column block per Supplier Quotation. A supplier that quoted more than
	  once for the same request gets one block per quotation, numbered
	  "Supplier 1", "Supplier 2", ... so each quotation is compared on its own
	  terms instead of being collapsed into a single column
	- Subtotal, discount, tax, and invoice total rows
	"""

	# ============================================
	# CONFIGURABLE: Change this to use different price field
	# Options: 'base_rate', 'base_amount', 'rate', 'amount'
	# ============================================
	if not supplier_quotation_data:
		return [], [], {}, {}, set(), set()

	price_field = filters.get("price_field", "base_amount")
	rate_field = "base_rate" if price_field.startswith("base_") else "rate"

	float_precision = cint(frappe.db.get_default("float_precision")) or 2

	# Data structures for pivot. Each is keyed by Supplier Quotation name - one
	# quotation is one column block in the report.
	item_quotation_map = defaultdict(lambda: defaultdict(dict))
	quotation_map = {}  # Store quotation-level data per quotation
	quotation_supplier = {}  # quotation -> (supplier id, supplier display name)
	all_items = []  # Maintain order
	item_meta = {}  # Store item metadata
	seen_items = set()

	# Process each quotation line
	for row in supplier_quotation_data:
		item_code = row.get("item_code")
		quotation_name = row.get("parent")
		if not quotation_name:
			continue
		quotation_supplier[quotation_name] = (
			row.get("supplier_id"),
			row.get("supplier_name") or row.get("supplier_id"),
		)

		# Get price value based on configured field
		price_value = flt(row.get(price_field), float_precision)
		rate_value = flt(row.get(rate_field), float_precision)

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

		# Narration (custom_narration, Small Text) is the quotation's own
		# free-text note on its line for this item, so it is stored per
		# (item, quotation) alongside the price.
		narration_value = (row.get("custom_narration") or "").strip()

		# Store this quotation's price for the item. A quotation can list the
		# same item on more than one line - keep the cheapest of those lines.
		existing = item_quotation_map[item_code].get(quotation_name)
		if not existing or price_value < existing["price"]:
			item_quotation_map[item_code][quotation_name] = {
				"price": price_value,
				"rate": rate_value,
				"qty": row.get("qty"),
				"narration": narration_value,
			}

		# Store quotation-level data (discount, taxes) per quotation
		if quotation_name not in quotation_map:
			quotation_map[quotation_name] = {
				"discount_amount": flt(row.get("discount_amount"), float_precision),
				"additional_discount_percentage": flt(row.get("additional_discount_percentage"), float_precision),
				"total": flt(row.get("base_total"), float_precision),
				"total_taxes": flt(row.get("base_total_taxes_and_charges"), float_precision),
				"grand_total": flt(row.get("base_grand_total"), float_precision),
				"apply_discount_on": row.get("apply_discount_on"),
				# Quotation-level commercial terms, rendered as free-text rows below
				# the invoice total (one row per attribute, value per quotation).
				"specification": row.get("custom_specification"),
				"warranty": row.get("custom_warrenty"),
				"payment_terms": row.get("custom_payment_terms"),
				"delivery_period": row.get("custom_delivery_period"),
			}

	# Column order: suppliers alphabetically, with a supplier's own quotations
	# adjacent and in name order - which is the order they are numbered in below.
	quotations = sorted(quotation_supplier, key=lambda q: (quotation_supplier[q][1] or "", q))

	# A supplier holding more than one quotation here gets its blocks numbered
	# ("Acme 1", "Acme 2"). The display name is also what the merged supplier
	# header groups consecutive columns on, so it has to differ between the
	# blocks - otherwise two quotations would be drawn as one supplier.
	quotations_per_supplier = defaultdict(list)
	for quotation in quotations:
		quotations_per_supplier[quotation_supplier[quotation][0]].append(quotation)

	quotation_display_name = {}
	for supplier_quotations in quotations_per_supplier.values():
		numbered = len(supplier_quotations) > 1
		for position, quotation in enumerate(supplier_quotations, start=1):
			display = quotation_supplier[quotation][1]
			quotation_display_name[quotation] = f"{display} {position}" if numbered else display

	# Fieldname stem per block. frappe.scrub leaves "/" in place and the naming
	# series carries the fiscal year (NGI-SQ-83/84-00010), which has no business
	# in a fieldname; the guard keeps two names from collapsing onto one stem.
	column_key = {}
	used_keys = set()
	for position, quotation in enumerate(quotations, start=1):
		key = frappe.scrub(quotation).replace("/", "_")
		if key in used_keys:
			key = f"{key}_{position}"
		used_keys.add(key)
		column_key[quotation] = key

	# Quotations with at least one non-blank narration anywhere in the comparison -
	# like Ordered, the Narration column is dropped entirely for a quotation with
	# none, rather than showing an always-blank column.
	quotations_with_narration = {
		quotation
		for item_quotations in item_quotation_map.values()
		for quotation, line in item_quotations.items()
		if (line.get("narration") or "").strip()
	}

	# ------------------------------------------------------------------
	# Per-(item, quotation) breakdown of what a Purchase Order has already
	# ordered against these quotations. Purchase Order Item.supplier_quotation
	# records which quotation each PO line came from, so the "Ordered" column
	# shows, per item, how much was taken from that exact quotation - two
	# quotations from the same supplier each report their own.
	# Independent of the Purchase Order filter; scoped to it when one is set.
	# ------------------------------------------------------------------
	ordered_item_quotation = {}  # (item_code, quotation) -> {"qty": total, "pos": [po_name, ...]}
	if quotations:
		conditions = ["poi.parent = po.name", "po.docstatus < 2", "poi.supplier_quotation IN %(sqs)s"]
		values = {"sqs": tuple(quotations)}
		if filters.get("purchase_order"):
			conditions.append("po.name = %(po)s")
			values["po"] = filters.get("purchase_order")
		for pr in frappe.db.sql(
			f"""
			SELECT poi.item_code AS item_code, poi.supplier_quotation AS sq, po.name AS po,
			       SUM(poi.qty) AS qty
			FROM `tabPurchase Order Item` poi, `tabPurchase Order` po
			WHERE {" AND ".join(conditions)}
			GROUP BY poi.item_code, poi.supplier_quotation, po.name
			""",
			values,
			as_dict=True,
		):
			key = (pr.item_code, pr.sq)
			entry = ordered_item_quotation.setdefault(key, {"qty": 0.0, "pos": []})
			entry["qty"] += flt(pr.qty)
			if pr.po not in entry["pos"]:
				entry["pos"].append(pr.po)

	# Quotations with at least one ordered item anywhere in the comparison - the
	# Ordered column is dropped entirely for a quotation that has none, rather
	# than showing an always-blank column.
	quotations_with_orders = {q for (_, q), o in ordered_item_quotation.items() if o.get("qty")}

	# Build output rows
	data = []
	sn = 1
	quotation_totals = {quotation: 0 for quotation in quotations}

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

		# Add each quotation's rate + amount + narration as columns
		for quotation in quotations:
			col_fieldname = column_key[quotation]

			if quotation in item_quotation_map[item_code]:
				line = item_quotation_map[item_code][quotation]
				price = line["price"]
				row[col_fieldname + "_rate"] = line["rate"]
				row[col_fieldname] = price
				row[col_fieldname + "_narration"] = line.get("narration") or ""
				quotation_totals[quotation] += price
			else:
				row[col_fieldname + "_rate"] = None
				row[col_fieldname] = None
				row[col_fieldname + "_narration"] = None

			# Qty of this item already ordered against this quotation, and the
			# Purchase Order it was ordered on - the tick links to that PO when
			# there's exactly one; ambiguous (split across POs) shows the qty only.
			ordered = ordered_item_quotation.get((item_code, quotation))
			if ordered and ordered["qty"]:
				row[col_fieldname + "_ordered"] = flt(ordered["qty"], float_precision)
				row[col_fieldname + "_ordered_po"] = ordered["pos"][0] if len(ordered["pos"]) == 1 else None
			else:
				row[col_fieldname + "_ordered"] = None
				row[col_fieldname + "_ordered_po"] = None

		data.append(row)
	
	# ============================================
	# SUMMARY ROWS
	# ============================================
	
	def summary_row(label, **flags):
		return {"sn": None, "item_code": None, "item_name": None, "qty": label, **flags}

	def has_value(row):
		"""True if any quotation column in the row is non-zero."""
		return any(flt(row[column_key[q]]) for q in quotations)

	# Total row (Net Total)
	total_row = summary_row("Total", is_total_row=1)
	for quotation in quotations:
		total_row[column_key[quotation]] = quotation_totals[quotation]
	data.append(total_row)

	# Discount on Net Total row
	discount_net_row = summary_row("Less: Discount (on Net Total)", is_summary_row=1)
	for quotation in quotations:
		col_fieldname = column_key[quotation]
		discount_amount = 0

		if quotation in quotation_map:
			sq_data = quotation_map[quotation]
			apply_on = sq_data.get("apply_discount_on")

			# Only show discount here if it's applied on Net Total
			if apply_on == "Net Total":
				discount_amount = flt(sq_data.get("discount_amount", 0), float_precision)

		discount_net_row[col_fieldname] = discount_amount
	if has_value(discount_net_row):
		data.append(discount_net_row)

	# Taxable Amount row (after net discount) - always shown
	taxable_row = summary_row("Taxable Amount", is_summary_row=1)
	for quotation in quotations:
		col_fieldname = column_key[quotation]
		total = total_row[col_fieldname]
		discount = discount_net_row[col_fieldname]
		taxable_row[col_fieldname] = total - discount
	data.append(taxable_row)

	# VAT/Tax row
	vat_row = summary_row("Add: VAT", is_summary_row=1)
	for quotation in quotations:
		col_fieldname = column_key[quotation]
		if quotation in quotation_map:
			vat_row[col_fieldname] = flt(quotation_map[quotation].get("total_taxes", 0), float_precision)
		else:
			vat_row[col_fieldname] = 0
	if has_value(vat_row):
		data.append(vat_row)

	# Discount on Grand Total row
	discount_grand_row = summary_row("Less: Discount (on Grand Total)", is_summary_row=1)
	for quotation in quotations:
		col_fieldname = column_key[quotation]
		discount_amount = 0

		if quotation in quotation_map:
			sq_data = quotation_map[quotation]
			apply_on = sq_data.get("apply_discount_on")

			# Only show discount here if it's applied on Grand Total
			if apply_on == "Grand Total":
				discount_amount = flt(sq_data.get("discount_amount", 0), float_precision)

		discount_grand_row[col_fieldname] = discount_amount
	if has_value(discount_grand_row):
		data.append(discount_grand_row)

	# Invoice Amount row (Grand Total) - use DB value directly, always shown
	invoice_row = summary_row("Invoice Amount", is_invoice_row=1)
	for quotation in quotations:
		col_fieldname = column_key[quotation]
		if quotation in quotation_map:
			# Use grand_total directly from database
			invoice_row[col_fieldname] = flt(quotation_map[quotation].get("grand_total", 0), float_precision)
		else:
			# Fallback calculation if no quotation data
			taxable = taxable_row[col_fieldname]
			vat = vat_row[col_fieldname]
			discount_grand = discount_grand_row[col_fieldname]
			invoice_row[col_fieldname] = taxable + vat - discount_grand
	data.append(invoice_row)

	# ============================================
	# COMMERCIAL-TERMS ROWS
	# One free-text row per quotation-level attribute (Specification, Warranty,
	# Payment Terms, Delivery Period), the value shown under each quotation. A row
	# is dropped entirely when no quotation in the comparison carries that field.
	# Marked is_term_row so the client formatter / PDF / email skip currency
	# formatting and the per-unit Rate column for these lines.
	# ============================================
	term_rows = [
		(_("Specification"), "specification"),
		(_("Warranty"), "warranty"),
		(_("Payment Terms"), "payment_terms"),
		(_("Delivery Period"), "delivery_period"),
	]
	for label, key in term_rows:
		term_row = summary_row(label, is_term_row=1)
		for quotation in quotations:
			value = ""
			if quotation in quotation_map:
				value = (quotation_map[quotation].get(key) or "").strip()
			term_row[column_key[quotation]] = value
		if any(term_row[column_key[q]] for q in quotations):
			data.append(term_row)

	return data, quotations, quotation_display_name, column_key, quotations_with_orders, quotations_with_narration


def get_columns(
	filters,
	quotations,
	quotation_display_name=None,
	column_key=None,
	quotations_with_orders=None,
	quotations_with_narration=None,
):
	"""
	Generate columns dynamically:
	- Fixed columns for SN, item info, qty
	- One block of columns per Supplier Quotation
	- Every column in a block carries `sq_link` - that block's own Supplier
	  Quotation - so the client script opens the right document when its header
	  is clicked, including when one supplier holds several quotations
	"""
	# Fixed columns
	columns = [
		{
			"fieldname": "sn",
			"label": _("SN"),
			"fieldtype": "Int",
			"width": 40,
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"fieldname": "qty",
			"label": _("Qty"),
			"fieldtype": "Data",  # Data type to allow "Total" text
			"width": 60,
		},
	]

	column_key = column_key or {}
	quotations_with_orders = quotations_with_orders or set()
	quotations_with_narration = quotations_with_narration or set()

	# Dynamic per-quotation columns, in order: Ordered, Rate, Amount, Narration.
	# Ordered and Narration are each dropped entirely for a quotation that has
	# none anywhere in the comparison, rather than showing an always-blank
	# column. `supplier_group` carries the block's display name - the supplier,
	# numbered when that supplier quoted more than once - so the client script
	# (and the approval-email renderer) can draw it as one spanning header cell
	# above its columns. `Ordered` shows, per item, the qty already placed on a
	# Purchase Order against that quotation (tick + link to the PO).
	# `Narration` is that quotation's own note for the item.
	for quotation in quotations:
		col_fieldname = column_key.get(quotation) or frappe.scrub(quotation).replace("/", "_")
		display = (quotation_display_name or {}).get(quotation, quotation)
		sq_link = quotation
		if quotation in quotations_with_orders:
			columns.append({
				"fieldname": col_fieldname + "_ordered",
				"label": _("Ordered"),
				"fieldtype": "Float",
				"width": 70,
				"sq_link": sq_link,
				"supplier_group": display,
			})
		columns.append({
			"fieldname": col_fieldname + "_rate",
			"label": _("Rate"),
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"width": 85,
			"sq_link": sq_link,
			"supplier_group": display,
		})
		columns.append({
			"fieldname": col_fieldname,
			"label": _("Amount"),
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"width": 100,
			"sq_link": sq_link,
			"supplier_group": display,
		})
		if quotation in quotations_with_narration:
			columns.append({
				"fieldname": col_fieldname + "_narration",
				"label": _("Narration"),
				"fieldtype": "Data",
				"width": 90,
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
		</span>
		<br>
		<span class="indicator orange">
		{_("A supplier that quoted more than once gets one numbered column set per quotation")}
		</span>"""


# The alternating supplier tints the on-screen report paints (kept in step with
# BAND_COLORS in the report's client script) so print and Excel read the same way.
SUPPLIER_BAND_COLORS = ["#eef3ff", "#fff8ec", "#eefaf1", "#fdeef4"]

# Suffix -> kind, for classifying a supplier's columns. Anything else in the
# block is the Amount column, which carries the bare scrubbed supplier name.
_SUPPLIER_FIELD_KINDS = (
	("_ordered", "ordered"),
	("_narration", "narration"),
	("_rate", "rate"),
)


def _supplier_groups(columns):
	"""The per-supplier column blocks, rebuilt from the columns exactly as the
	on-screen report renders them: consecutive columns sharing a `supplier_group`
	form one block, kept in their real order (Ordered, Rate, Amount, Narration),
	with Ordered / Narration simply absent when the report dropped them for
	having nothing to show. Print and Excel walk `fields` so they stay in step
	with the report instead of restating its column rules."""
	groups = []
	current = None
	for col in columns:
		group_name = col.get("supplier_group")
		if not group_name:
			current = None
			continue

		kind = "amount"
		for suffix, name in _SUPPLIER_FIELD_KINDS:
			if col["fieldname"].endswith(suffix):
				kind = name
				break

		# A new block starts on a different supplier name, and also when the same
		# name repeats a column kind - two suppliers can share a display name.
		if current is None or current["display"] != group_name or current[kind + "_field"]:
			current = {
				"display": group_name,
				"sq": col.get("sq_link"),
				"fields": [],
				"ordered_field": None,
				"rate_field": None,
				"amount_field": None,
				"narration_field": None,
			}
			groups.append(current)

		current["fields"].append({
			"kind": kind,
			"field": col["fieldname"],
			"label": col.get("label") or "",
		})
		current[kind + "_field"] = col["fieldname"]

	for index, group in enumerate(groups):
		group["span"] = len(group["fields"])
		group["band"] = SUPPLIER_BAND_COLORS[index % len(SUPPLIER_BAND_COLORS)]
	return groups


@frappe.whitelist()
def export_xlsx(filters):
	"""Excel export laid out like the on-screen comparison: each supplier's name
	merged and centered above that supplier's own columns, in the report's order
	(Ordered, Rate, Amount, Narration) and with the same columns dropped when the
	report drops them. Supplier blocks carry the report's alternating tint and a
	divider on the left edge, and an Ordered qty links to its Purchase Order."""
	from io import BytesIO

	from frappe.utils.xlsxutils import make_xlsx
	from openpyxl import load_workbook
	from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))

	columns, data = execute(filters)[:2]
	groups = _supplier_groups(columns)

	fixed_labels = ["SN", "Item Name", "Qty"]
	supplier_row = [""] * len(fixed_labels)
	label_row = list(fixed_labels)
	for g in groups:
		supplier_row += [g["display"]] + [""] * (g["span"] - 1)
		label_row += [f["label"] for f in g["fields"]]

	rows = [supplier_row, label_row]
	ordered_links = []  # (row, column, purchase order) for the Ordered cells
	for d in data:
		if not isinstance(d, dict) or not d:
			continue
		row = [d.get("sn"), d.get("item_name") or d.get("item_code"), d.get("qty")]
		for g in groups:
			for f in g["fields"]:
				value = d.get(f["field"])
				if f["kind"] == "ordered" and value:
					po = d.get(f["field"] + "_po")
					if po:
						# 1-based sheet coordinates of the cell this value lands in
						ordered_links.append((len(rows) + 1, len(row) + 1, po))
				row.append(value)
		rows.append(row)

	xlsx = make_xlsx(rows, "Supplier Quotation Comparison")

	# make_xlsx works on a write-only workbook, so restyle by reopening the file.
	wb = load_workbook(xlsx)
	ws = wb.active
	last_row = ws.max_row
	divider = Border(left=Side(style="medium"))

	col = len(fixed_labels) + 1
	for g in groups:
		ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + g["span"] - 1)
		cell = ws.cell(row=1, column=col)
		cell.alignment = Alignment(horizontal="center")
		cell.font = Font(bold=True)

		fill = PatternFill("solid", fgColor=g["band"].lstrip("#").upper())
		for offset in range(g["span"]):
			for row_index in range(1, last_row + 1):
				sheet_cell = ws.cell(row=row_index, column=col + offset)
				sheet_cell.fill = fill
				if offset == 0:
					sheet_cell.border = divider
		col += g["span"]

	for row_index, col_index, po in ordered_links:
		cell = ws.cell(row=row_index, column=col_index)
		cell.hyperlink = frappe.utils.get_url("/app/purchase-order/{0}".format(po))
		cell.style = "Hyperlink"

	out = BytesIO()
	wb.save(out)

	frappe.response.filename = "supplier_quotation_comparison.xlsx"
	frappe.response.filecontent = out.getvalue()
	frappe.response.type = "binary"


@frappe.whitelist()
def download_pdf(filters, view=None):
	"""Print / PDF of the comparison in document form: company + title header,
	one column block per supplier (quotation number under the supplier's name)
	holding the same columns in the same order as the on-screen report, and the
	same summary rows below.
	Both menu entries call this — Print opens it inline (view=1), PDF downloads."""
	from frappe.utils.pdf import get_pdf

	from avinashgroup_app.custom_code.printing.chrome_pdf import render as chrome_render

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))

	columns, data = execute(filters)[:2]
	groups = _supplier_groups(columns)

	report_title = "Supplier Quotation Comparison"
	if filters.get("purchase_order"):
		report_title += " — {0}".format(filters.purchase_order)

	subline_parts = []
	material_requests = _as_list(filters.get("material_request"))
	if filters.get("purchase_order"):
		material_requests += get_material_requests_from_purchase_order(filters.purchase_order)
	material_requests = list(dict.fromkeys(mr for mr in material_requests if mr))
	if material_requests:
		subline_parts.append("Material Request: {0}".format(", ".join(material_requests)))
	if cint(filters.get("preferred_quotation")):
		subline_parts.append("Preferred quotations only")

	currency = frappe.get_cached_value("Company", filters.get("company"), "default_currency")

	def fmt(value):
		return fmt_money(flt(value), 2, currency) if value is not None else ""

	template_path = os.path.join(os.path.dirname(__file__), "supplier_quotation_comparison_pdf.html")
	with open(template_path) as f:
		template_content = f.read()

	html = frappe.render_template(
		template_content,
		{
			"company": filters.get("company"),
			"report_title": report_title,
			"subline_parts": subline_parts,
			"groups": groups,
			"data": data,
			"fmt": fmt,
			# Wide enough for a formatted NPR amount at the table's font size -
			# "Rs 1,98,750.00" plus cell padding. Too narrow and the money cells,
			# which must not wrap, spill over the column border into their neighbour.
			"field_widths": {
				"ordered": "42px",
				"rate": "72px",
				"amount": "88px",
				"narration": "95px",
			},
		},
	)

	# The three fixed columns plus about six supplier columns sit on portrait A4;
	# beyond that they get too narrow, so use landscape. Counting the real columns
	# (rather than the suppliers) keeps this right whatever each block holds.
	total_columns = 3 + sum(g["span"] for g in groups)
	orientation = "Portrait" if total_columns <= 9 else "Landscape"

	# Page geometry has to be stated twice because the two renderers read it from
	# different places: wkhtmltopdf takes the options dict below, Chrome honours
	# only an @page rule in the document itself.
	html = (
		"<style>@page { size: A4 %s; margin: 10mm 10mm 12mm 10mm; }</style>"
		% orientation.lower()
	) + html

	# This app renders print formats with headless Chrome (hooks.py: pdf_generator),
	# and a bench that has Chrome generally has no wkhtmltopdf at all - calling
	# get_pdf first would raise "No wkhtmltopdf executable found" before anything
	# else got a chance. So try Chrome, and fall back only when it isn't there.
	pdf_data = chrome_render(html=html, pdf_generator="chrome")
	if pdf_data is None:
		pdf_data = get_pdf(html, {
			"page-size": "A4",
			"orientation": orientation,
			"margin-top": "10mm",
			"margin-right": "10mm",
			"margin-bottom": "12mm",
			"margin-left": "10mm",
			"encoding": "UTF-8",
		})

	frappe.response.filename = "supplier_quotation_comparison.pdf"
	frappe.response.filecontent = pdf_data
	# view=1 (Print) -> open inline in the browser tab; otherwise download the file.
	frappe.response.type = "pdf" if cint(view) else "download"


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