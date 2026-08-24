# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _

# Nepal Gas Udhyog trades a single Item per company, literally named "LP Gas"
# (see avinashgroup_app.templates.pages.place_order.LP_GAS_ITEM_NAME) — the
# different cylinder sizes shown as separate product codes in the legacy FACT
# WebNG report are UOMs on that one item, priced per UOM via the Price List.
LP_GAS_ITEM_NAME = "LP Gas"


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
def get_company_price_lists(company=None, txt=None):
	"""One filter option per Price List doc scoped to the selected company(ies) —
	kept one-per-company rather than deduped by category (Bulk, Dealer, ...),
	since two different companies' Price Lists can share the same category name."""
	companies = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = ["price_list_name LIKE %(txt)s"]
	values = {"txt": like}
	if companies:
		conditions.append("custom_company IN %(companies)s")
		values["companies"] = tuple(companies)
	where = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT name, price_list_name, custom_company
		FROM `tabPrice List`
		WHERE {where}
		ORDER BY price_list_name
		""",
		values,
		as_dict=True,
	)
	if not rows:
		return []

	company_abbrs = dict(
		frappe.get_all(
			"Company",
			filters=[["name", "in", [r.custom_company for r in rows if r.custom_company]]],
			fields=["name", "abbr"],
			as_list=True,
		)
	)

	return [
		{
			"value": row.name,
			"label": "{0} - {1}".format(row.price_list_name, company_abbrs.get(row.custom_company, row.custom_company)),
			"description": row.name,
		}
		for row in rows
	]


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()

	companies = _as_list(filters.get("company"))
	if not companies:
		return columns, [], _("Please select a Company.")
	if not filters.get("from_date") or not filters.get("to_date"):
		return columns, [], _("Please select From Date and To Date.")

	data = get_data(filters, companies)
	if data:
		total = {
			"company": None,
			"item_code": None,
			"item_name": _("Total"),
			"uom": None,
			"price_list": None,
			"bold": 1,
		}
		for col in columns:
			if col.get("fieldtype") in ("Currency", "Float"):
				total[col["fieldname"]] = sum(row.get(col["fieldname"]) or 0 for row in data)
		data.append(total)
	return columns, data


def get_columns():
	return [
		{"fieldname": "company",    "label": _("Company"),            "fieldtype": "Link",  "options": "Company",    "width": 160},
		{"fieldname": "item_code",  "label": _("Product Code"),       "fieldtype": "Data",                           "width": 120},
		{"fieldname": "item_name",  "label": _("Product Description"),"fieldtype": "Data",                           "width": 200},
		{"fieldname": "uom",        "label": _("UOM"),                "fieldtype": "Link",  "options": "UOM",        "width": 90},
		{"fieldname": "price_list", "label": _("Price List"),         "fieldtype": "Data",                           "width": 140},
		{"fieldname": "received",   "label": _("Received"),           "fieldtype": "Float", "width": 110, "precision": 3},
		{"fieldname": "delivered",  "label": _("Delivered"),          "fieldtype": "Float", "width": 110, "precision": 3},
		{"fieldname": "balance",    "label": _("Balance"),            "fieldtype": "Float", "width": 110, "precision": 3},
	]


def _lp_gas_items(companies):
	"""The LP Gas item for each selected company, as {item_code: {company, item_name}}."""
	rows = frappe.get_all(
		"Item",
		filters={"item_name": LP_GAS_ITEM_NAME, "custom_company": ["in", companies]},
		fields=["name", "custom_company", "item_name"],
	)
	return {r.name: {"company": r.custom_company, "item_name": r.item_name} for r in rows}


def _price_list_filter(column, price_lists):
	"""SQL condition for the Price List filter, or "" when nothing is selected.

	Documents that carry no price list at all are always kept: purchases never
	set buying_price_list here (the Bulk/Dealer/Inter-Company lists are all
	selling-only), so filtering them out would drop every Received figure.
	"""
	if not price_lists:
		return ""
	return "AND ({0} IN %(price_lists)s OR {0} IS NULL OR {0} = '')".format(column)


def _received(item_codes, from_date, to_date, price_lists):
	"""Purchase Receipt (always stock-effecting) + Purchase Invoice with update_stock=1
	(a PI billed against a PR, update_stock=0, is skipped — that PR already counted it).
	Return rows carry negative qty already, so a Purchase Return nets straight out."""
	if not item_codes:
		return []
	price_list_condition = _price_list_filter("pr.buying_price_list", price_lists)
	price_list_condition_pi = _price_list_filter("pi.buying_price_list", price_lists)
	return frappe.db.sql(
		"""
		SELECT item_code, uom, price_list, SUM(qty) AS qty FROM (
			SELECT pri.item_code AS item_code, pri.uom AS uom, NULLIF(pr.buying_price_list, '') AS price_list, pri.qty AS qty
			FROM `tabPurchase Receipt Item` pri
			JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pr.docstatus = 1 AND pri.item_code IN %(items)s
			  AND pr.posting_date BETWEEN %(from_date)s AND %(to_date)s
			  {price_list_condition}

			UNION ALL

			SELECT pii.item_code AS item_code, pii.uom AS uom, NULLIF(pi.buying_price_list, '') AS price_list, pii.qty AS qty
			FROM `tabPurchase Invoice Item` pii
			JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			WHERE pi.docstatus = 1 AND pi.update_stock = 1 AND pii.item_code IN %(items)s
			  AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
			  {price_list_condition_pi}
		) t
		GROUP BY item_code, uom, price_list
		""".format(price_list_condition=price_list_condition, price_list_condition_pi=price_list_condition_pi),
		{"items": tuple(item_codes), "from_date": from_date, "to_date": to_date, "price_lists": price_lists},
		as_dict=True,
	)


def _delivered(item_codes, from_date, to_date, price_lists):
	"""Delivery Note (always stock-effecting) + Sales Invoice with update_stock=1
	(an SI billed against a DN, update_stock=0, is skipped — that DN already counted it).
	Sales Return rows carry negative qty already, so they net straight out."""
	if not item_codes:
		return []
	price_list_condition = _price_list_filter("dn.selling_price_list", price_lists)
	price_list_condition_si = _price_list_filter("si.selling_price_list", price_lists)
	return frappe.db.sql(
		"""
		SELECT item_code, uom, price_list, SUM(qty) AS qty FROM (
			SELECT dni.item_code AS item_code, dni.uom AS uom, NULLIF(dn.selling_price_list, '') AS price_list, dni.qty AS qty
			FROM `tabDelivery Note Item` dni
			JOIN `tabDelivery Note` dn ON dn.name = dni.parent
			WHERE dn.docstatus = 1 AND dni.item_code IN %(items)s
			  AND dn.posting_date BETWEEN %(from_date)s AND %(to_date)s
			  {price_list_condition}

			UNION ALL

			SELECT sii.item_code AS item_code, sii.uom AS uom, NULLIF(si.selling_price_list, '') AS price_list, sii.qty AS qty
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.docstatus = 1 AND si.update_stock = 1 AND sii.item_code IN %(items)s
			  AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			  {price_list_condition_si}
		) t
		GROUP BY item_code, uom, price_list
		""".format(price_list_condition=price_list_condition, price_list_condition_si=price_list_condition_si),
		{"items": tuple(item_codes), "from_date": from_date, "to_date": to_date, "price_lists": price_lists},
		as_dict=True,
	)


def get_data(filters, companies):
	items = _lp_gas_items(companies)
	if not items:
		return []
	item_codes = list(items.keys())
	price_lists = tuple(_as_list(filters.get("price_list"))) or None

	received = {
		(r.item_code, r.uom, r.price_list): r.qty or 0
		for r in _received(item_codes, filters["from_date"], filters["to_date"], price_lists)
	}
	delivered = {
		(r.item_code, r.uom, r.price_list): r.qty or 0
		for r in _delivered(item_codes, filters["from_date"], filters["to_date"], price_lists)
	}

	price_list_names = {}
	all_price_lists = {k[2] for k in set(received) | set(delivered) if k[2]}
	if all_price_lists:
		price_list_docs = frappe.get_all(
			"Price List",
			filters=[["name", "in", list(all_price_lists)]],
			fields=["name", "price_list_name", "custom_company"],
		)
		# Two different companies' Price Lists can share the same category name
		# (both called "Bulk") — suffix the owning company's abbreviation so
		# those stay visibly distinct instead of looking like one merged row.
		company_abbrs = dict(
			frappe.get_all(
				"Company",
				filters=[["name", "in", [d.custom_company for d in price_list_docs if d.custom_company]]],
				fields=["name", "abbr"],
				as_list=True,
			)
		)
		price_list_names = {
			d.name: "{0} - {1}".format(d.price_list_name, company_abbrs.get(d.custom_company, d.custom_company))
			if d.custom_company
			else d.price_list_name
			for d in price_list_docs
		}

	rows = []
	for key in sorted(set(received) | set(delivered), key=lambda k: (k[0], k[1], k[2] or "")):
		item_code, uom, row_price_list = key
		item = items[item_code]
		r = received.get(key, 0)
		d = delivered.get(key, 0)
		rows.append({
			"company": item["company"],
			"item_code": item_code,
			"item_name": item["item_name"],
			"uom": uom,
			"price_list": price_list_names.get(row_price_list, row_price_list),
			"received": r,
			"delivered": d,
			"balance": r - d,
		})
	return rows
