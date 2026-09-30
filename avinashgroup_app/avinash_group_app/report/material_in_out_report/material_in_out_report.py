# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import add_days

# Start of the Opening Stock window — earlier than any document in the books.
EARLIEST_DATE = "1900-01-01"

# Every item that moved in the period is reported, not just gas. Rows are scoped by the
# company on the stock document itself rather than by the item's custom_company, so an
# item used by more than one company is reported under whichever company moved it.


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
			"branch": None,
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
		{"fieldname": "branch",     "label": _("Branch"),             "fieldtype": "Data",                           "width": 140},
		{"fieldname": "item_code",  "label": _("Product Code"),       "fieldtype": "Data",                           "width": 120},
		{"fieldname": "item_name",  "label": _("Product Description"),"fieldtype": "Data",                           "width": 200},
		{"fieldname": "uom",        "label": _("UOM"),                "fieldtype": "Link",  "options": "UOM",        "width": 90},
		{"fieldname": "price_list", "label": _("Price List"),         "fieldtype": "Data",                           "width": 140},
		# Received minus Delivered before From Date — see _opening().
		{"fieldname": "opening_stock", "label": _("Opening Stock"),   "fieldtype": "Float", "width": 110, "precision": 3},
		{"fieldname": "received",   "label": _("Received"),           "fieldtype": "Float", "width": 110, "precision": 3},
		{"fieldname": "delivered",  "label": _("Delivered"),          "fieldtype": "Float", "width": 110, "precision": 3},
		{"fieldname": "balance",    "label": _("Balance"),            "fieldtype": "Float", "width": 110, "precision": 3},
	]


@frappe.whitelist()
def get_company_items(company=None, txt=None):
	"""Item options scoped to the selected company via the item's custom_company.
	Every company has its own "LP Gas", so the label carries the company abbreviation."""
	companies = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = ["(it.name LIKE %(txt)s OR it.item_name LIKE %(txt)s)"]
	values = {"txt": like}
	if companies:
		conditions.append("(it.custom_company IN %(companies)s OR COALESCE(it.custom_company, '') = '')")
		values["companies"] = tuple(companies)
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			it.name AS value,
			CASE WHEN co.abbr IS NULL OR co.abbr = '' THEN it.item_name
			     ELSE CONCAT(it.item_name, ' - ', co.abbr) END AS label,
			it.name AS description
		FROM `tabItem` it
		LEFT JOIN `tabCompany` co ON co.name = it.custom_company
		WHERE {where}
		ORDER BY co.abbr, it.item_name
		LIMIT 50
		""",
		values,
		as_dict=True,
	)


@frappe.whitelist()
def get_company_branches(company=None, txt=None):
	"""Branch options scoped to the selected company(ies). Several companies have a
	branch of the same name (Balaju, Chitwan), so the label carries the company
	abbreviation."""
	companies = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = ["(br.name LIKE %(txt)s OR br.branch LIKE %(txt)s)"]
	values = {"txt": like}
	if companies:
		conditions.append("br.custom_company IN %(companies)s")
		values["companies"] = tuple(companies)
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			br.name AS value,
			CASE WHEN co.abbr IS NULL OR co.abbr = '' THEN br.branch
			     ELSE CONCAT(br.branch, ' - ', co.abbr) END AS label,
			br.name AS description
		FROM `tabBranch` br
		LEFT JOIN `tabCompany` co ON co.name = br.custom_company
		WHERE {where}
		ORDER BY co.abbr, br.branch
		""",
		values,
		as_dict=True,
	)


def _branch_filter(column, branches):
	"""SQL condition for the Branch filter, or "" when nothing is selected. Documents
	with no branch are left out once a branch is picked."""
	if not branches:
		return ""
	return "AND {0} IN %(branches)s".format(column)


def _item_filter(column, items):
	"""SQL condition for the Item filter, or "" when nothing is selected."""
	if not items:
		return ""
	return "AND {0} IN %(items)s".format(column)


def _item_names(item_codes):
	"""{item_code: item_name} for the items that actually appear in the report."""
	if not item_codes:
		return {}
	return dict(
		frappe.get_all(
			"Item",
			filters=[["name", "in", list(item_codes)]],
			fields=["name", "item_name"],
			as_list=True,
		)
	)


def _branch_names(branch_ids):
	"""{Branch id: readable branch name} — Branch ids are series like NGK-Branch-00001."""
	if not branch_ids:
		return {}
	return dict(
		frappe.get_all(
			"Branch",
			filters=[["name", "in", list(branch_ids)]],
			fields=["name", "branch"],
			as_list=True,
		)
	)


def _price_list_filter(column, price_lists):
	"""SQL condition for the Price List filter, or "" when nothing is selected.

	Documents that carry no price list at all are always kept: purchases never
	set buying_price_list here (the Bulk/Dealer/Inter-Company lists are all
	selling-only), so filtering them out would drop every Received figure.
	"""
	if not price_lists:
		return ""
	return "AND ({0} IN %(price_lists)s OR {0} IS NULL OR {0} = '')".format(column)


def _received(companies, from_date, to_date, price_lists, items, branches):
	"""Purchase Receipt (always stock-effecting) + Purchase Invoice with update_stock=1
	(a PI billed against a PR, update_stock=0, is skipped — that PR already counted it).
	Return rows carry negative qty already, so a Purchase Return nets straight out."""
	price_list_condition = _price_list_filter("pr.buying_price_list", price_lists)
	price_list_condition_pi = _price_list_filter("pi.buying_price_list", price_lists)
	item_condition = _item_filter("pri.item_code", items)
	item_condition_pi = _item_filter("pii.item_code", items)
	branch_condition = _branch_filter("pr.custom_branch", branches)
	branch_condition_pi = _branch_filter("pi.custom_branch", branches)
	return frappe.db.sql(
		"""
		SELECT company, branch, item_code, uom, price_list, SUM(qty) AS qty FROM (
			SELECT pr.company AS company, NULLIF(pr.custom_branch, '') AS branch, pri.item_code AS item_code, pri.uom AS uom, NULLIF(pr.buying_price_list, '') AS price_list, pri.qty AS qty
			FROM `tabPurchase Receipt Item` pri
			JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pr.docstatus = 1 AND pr.company IN %(companies)s
			  AND pr.posting_date BETWEEN %(from_date)s AND %(to_date)s
			  {price_list_condition}
			  {item_condition}
			  {branch_condition}

			UNION ALL

			SELECT pi.company AS company, NULLIF(pi.custom_branch, '') AS branch, pii.item_code AS item_code, pii.uom AS uom, NULLIF(pi.buying_price_list, '') AS price_list, pii.qty AS qty
			FROM `tabPurchase Invoice Item` pii
			JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			WHERE pi.docstatus = 1 AND pi.update_stock = 1 AND pi.company IN %(companies)s
			  AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
			  {price_list_condition_pi}
			  {item_condition_pi}
			  {branch_condition_pi}
		) t
		GROUP BY company, branch, item_code, uom, price_list
		""".format(price_list_condition=price_list_condition, price_list_condition_pi=price_list_condition_pi,
			item_condition=item_condition, item_condition_pi=item_condition_pi,
			branch_condition=branch_condition, branch_condition_pi=branch_condition_pi),
		{"companies": tuple(companies), "from_date": from_date, "to_date": to_date,
		 "price_lists": price_lists, "items": items, "branches": branches},
		as_dict=True,
	)


def _delivered(companies, from_date, to_date, price_lists, items, branches):
	"""Delivery Note (always stock-effecting) + Sales Invoice with update_stock=1
	(an SI billed against a DN, update_stock=0, is skipped — that DN already counted it).
	Sales Return rows carry negative qty already, so they net straight out."""
	price_list_condition = _price_list_filter("dn.selling_price_list", price_lists)
	price_list_condition_si = _price_list_filter("si.selling_price_list", price_lists)
	item_condition = _item_filter("dni.item_code", items)
	item_condition_si = _item_filter("sii.item_code", items)
	branch_condition = _branch_filter("dn.custom_branch", branches)
	branch_condition_si = _branch_filter("si.custom_branch", branches)
	return frappe.db.sql(
		"""
		SELECT company, branch, item_code, uom, price_list, SUM(qty) AS qty FROM (
			SELECT dn.company AS company, NULLIF(dn.custom_branch, '') AS branch, dni.item_code AS item_code, dni.uom AS uom, NULLIF(dn.selling_price_list, '') AS price_list, dni.qty AS qty
			FROM `tabDelivery Note Item` dni
			JOIN `tabDelivery Note` dn ON dn.name = dni.parent
			WHERE dn.docstatus = 1 AND dn.company IN %(companies)s
			  AND dn.posting_date BETWEEN %(from_date)s AND %(to_date)s
			  {price_list_condition}
			  {item_condition}
			  {branch_condition}

			UNION ALL

			SELECT si.company AS company, NULLIF(si.custom_branch, '') AS branch, sii.item_code AS item_code, sii.uom AS uom, NULLIF(si.selling_price_list, '') AS price_list, sii.qty AS qty
			FROM `tabSales Invoice Item` sii
			JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.docstatus = 1 AND si.update_stock = 1 AND si.company IN %(companies)s
			  AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			  {price_list_condition_si}
			  {item_condition_si}
			  {branch_condition_si}
		) t
		GROUP BY company, branch, item_code, uom, price_list
		""".format(price_list_condition=price_list_condition, price_list_condition_si=price_list_condition_si,
			item_condition=item_condition, item_condition_si=item_condition_si,
			branch_condition=branch_condition, branch_condition_si=branch_condition_si),
		{"companies": tuple(companies), "from_date": from_date, "to_date": to_date,
		 "price_lists": price_lists, "items": items, "branches": branches},
		as_dict=True,
	)


def _opening(companies, from_date, price_lists, items, branches):
	"""What was left of each row before From Date: everything it received minus
	everything it delivered, from the same documents as the Received and Delivered
	columns. Bought 80 and sold 75 up to yesterday → today opens at 5.

	Returns {(company, branch, item_code, uom, price_list): qty}, keyed like the
	Received and Delivered rows so the opening lands on the row it belongs to.
	"""
	day_before = add_days(from_date, -1)
	opening = {}
	for r in _received(companies, EARLIEST_DATE, day_before, price_lists, items, branches):
		key = (r.company, r.branch, r.item_code, r.uom, r.price_list)
		opening[key] = opening.get(key, 0) + (r.qty or 0)
	for r in _delivered(companies, EARLIEST_DATE, day_before, price_lists, items, branches):
		key = (r.company, r.branch, r.item_code, r.uom, r.price_list)
		opening[key] = opening.get(key, 0) - (r.qty or 0)
	return {key: qty for key, qty in opening.items() if round(qty, 3) != 0}


def get_data(filters, companies):
	price_lists = tuple(_as_list(filters.get("price_list"))) or None
	items = tuple(_as_list(filters.get("item"))) or None
	branches = tuple(_as_list(filters.get("branch"))) or None

	received = {
		(r.company, r.branch, r.item_code, r.uom, r.price_list): r.qty or 0
		for r in _received(companies, filters["from_date"], filters["to_date"], price_lists, items, branches)
	}
	delivered = {
		(r.company, r.branch, r.item_code, r.uom, r.price_list): r.qty or 0
		for r in _delivered(companies, filters["from_date"], filters["to_date"], price_lists, items, branches)
	}

	opening = _opening(companies, filters["from_date"], price_lists, items, branches)

	price_list_names = {}
	all_price_lists = {k[4] for k in set(received) | set(delivered) | set(opening) if k[4]}
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

	keys = set(received) | set(delivered) | set(opening)
	item_names = _item_names({k[2] for k in keys})
	branch_names = _branch_names({k[1] for k in keys if k[1]})

	rows = []
	for key in sorted(keys, key=lambda k: (k[0] or "", branch_names.get(k[1], k[1] or ""), k[2], k[3], k[4] or "")):
		company, branch, item_code, uom, row_price_list = key
		r = received.get(key, 0)
		d = delivered.get(key, 0)
		rows.append({
			"company": company,
			"branch": branch_names.get(branch, branch),
			"item_code": item_code,
			"item_name": item_names.get(item_code, item_code),
			"uom": uom,
			"price_list": price_list_names.get(row_price_list, row_price_list),
			"opening_stock": opening.get(key, 0),
			"received": r,
			"delivered": d,
			"balance": r - d,
		})
	return rows
