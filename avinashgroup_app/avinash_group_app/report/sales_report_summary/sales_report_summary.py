# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _

from avinashgroup_app.custom_code.CBMS.utils import get_fiscal_year_dates


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
def get_all_companies():
	"""Every company name, used to preselect the Company filter on first open."""
	return frappe.get_all("Company", pluck="name", order_by="name")


@frappe.whitelist()
def get_company_items(company=None, txt=None):
	"""Item options scoped to the selected company via the item's custom_company."""
	company = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = ["(it.name LIKE %(txt)s OR it.item_name LIKE %(txt)s)"]
	values = {"txt": like}
	if company:
		conditions.append("(it.custom_company IN %(company)s OR COALESCE(it.custom_company, '') = '')")
		values["company"] = tuple(company)
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


@frappe.whitelist()
def get_company_branches(company=None, txt=None):
	"""Branch options scoped to the selected company via the branch's custom_company.
	The same branch name exists under several companies (four companies have a "Balaju"),
	so the label carries the company abbreviation — "Balaju - NGG" — the way the price
	list names already do."""
	company = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = ["(br.name LIKE %(txt)s OR br.branch LIKE %(txt)s)"]
	values = {"txt": like}
	if company:
		conditions.append("(br.custom_company IN %(company)s OR COALESCE(br.custom_company, '') = '')")
		values["company"] = tuple(company)
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
		LIMIT 50
		""",
		values,
		as_dict=True,
	)


@frappe.whitelist()
def get_company_price_lists(company=None, txt=None):
	"""Price List options scoped to the selected company via the price list's custom_company.
	Every company has its own "Bulk"/"Dealer"/"Inter-Company", and the stored price_list_name
	is the bare word, so the label carries the company abbreviation — "Bulk - NGG"."""
	company = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = ["(pl.name LIKE %(txt)s OR pl.price_list_name LIKE %(txt)s)"]
	values = {"txt": like}
	if company:
		conditions.append("(pl.custom_company IN %(company)s OR COALESCE(pl.custom_company, '') = '')")
		values["company"] = tuple(company)
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			pl.name AS value,
			CASE WHEN co.abbr IS NULL OR co.abbr = '' THEN pl.price_list_name
			     ELSE CONCAT(pl.price_list_name, ' - ', co.abbr) END AS label,
			pl.name AS description
		FROM `tabPrice List` pl
		LEFT JOIN `tabCompany` co ON co.name = pl.custom_company
		WHERE {where}
		ORDER BY co.abbr, pl.price_list_name
		LIMIT 50
		""",
		values,
		as_dict=True,
	)


def _period(filters):
	"""(from_date, to_date) for the report, honouring the "Filter By" dropdown.
	On Fiscal Year the window is the Fiscal Year record's own start/end dates, read on
	the server; the From/To Date boxes are hidden in that mode and ignored here."""
	if filters.get("date_filter_type") == "Fiscal Year":
		if not filters.get("fiscal_year"):
			return None, None
		dates = get_fiscal_year_dates(filters.get("fiscal_year"))
		return dates.get("from_date"), dates.get("to_date")

	return filters.get("from_date"), filters.get("to_date")


BRANCH_WISE = "Sales Report Summary Branch Wise"
COMPARISON = "Sales Report Summary Company-wise Comparison"

# What the per-company columns can hold in comparison mode, keyed by the filter's own
# label: (row field, short column label, fieldtype, precision). More than one may be
# picked, and they are always laid out in this order regardless of selection order.
MEASURES = {
	"Qty Wise":       ("qty",            "Quantity",       "Float",    3),
	"Taxable Amount": ("taxable_amount", "Taxable Amount", "Currency", 2),
	"Total Amount":   ("total_amount",   "Total Amount",   "Currency", 2),
}
MEASURE_ORDER = ["Qty Wise", "Taxable Amount", "Total Amount"]


@frappe.whitelist()
def get_comparison_measures(txt=None):
	"""Options for the Compare By filter, in their fixed display order."""
	txt = (txt or "").strip().lower()
	return [{"value": m, "description": ""} for m in MEASURE_ORDER if txt in m.lower()]


def _measure_field(company, measure):
	"""Column fieldname for one company/measure pair. Keyed off the company name, not its
	abbreviation, so two companies can never collide on one column."""
	return "co_{0}_{1}".format(frappe.scrub(company), frappe.scrub(measure))


def _comparison(filters, companies):
	"""One row per Item Name + UOM + Price List, with a column per company per selected
	measure, so the same product line can be read across companies."""
	measures = [m for m in MEASURE_ORDER if m in _as_list(filters.get("comparison_measure"))]
	if not measures:
		measures = ["Qty Wise"]

	companies = sorted(companies)
	abbrs = dict(
		frappe.get_all(
			"Company", filters=[["name", "in", companies]], fields=["name", "abbr"], as_list=True
		)
	)

	columns = [
		{"fieldname": "item_name",  "label": _("Item Name"),  "fieldtype": "Data", "width": 220},
		{"fieldname": "uom",        "label": _("UOM"),        "fieldtype": "Data", "width": 90},
		{"fieldname": "price_list", "label": _("Price List"), "fieldtype": "Data", "width": 130},
	]
	# Companies first, each carrying every selected measure, then the totals across
	# companies — one total column per measure.
	for company in companies:
		for measure in measures:
			short, fieldtype, precision = MEASURES[measure][1:]
			columns.append({
				"fieldname": _measure_field(company, measure),
				# The company abbreviation is carried in the label itself, so the column
				# says which company it belongs to on screen and in every export.
				"label": "{0} {1}".format(abbrs.get(company) or company, short),
				"fieldtype": fieldtype,
				"width": 170,
				"precision": precision,
			})
	for measure in measures:
		short, fieldtype, precision = MEASURES[measure][1:]
		columns.append({
			"fieldname": "total_{0}".format(frappe.scrub(measure)),
			# "All Companies" rather than "Total", which would read "Total Total Amount".
			"label": _("All Companies {0}").format(short),
			"fieldtype": fieldtype,
			"width": 190,
			"precision": precision,
		})

	rows = {}
	for company in companies:
		for r in get_data(filters, company):
			key = (r["item_name"] or "", r["uom"] or "", r["price_list"] or "")
			row = rows.setdefault(key, {"item_name": key[0], "uom": key[1], "price_list": key[2]})
			for measure in measures:
				field = MEASURES[measure][0]
				value = r.get(field) or 0
				column = _measure_field(company, measure)
				total_column = "total_{0}".format(frappe.scrub(measure))
				row[column] = (row.get(column) or 0) + value
				row[total_column] = (row.get(total_column) or 0) + value

	data = [rows[key] for key in sorted(rows)]
	if data:
		data.append(_total_row(_("Total"), data, columns))
	return columns, data


def _blocks(company, rows, branch_wise):
	"""[(heading, rows)] for one company: a single block normally, or one block per
	branch in branch-wise mode.

	A company whose invoices name no branch at all keeps the plain company heading, so it
	reads exactly as the normal report. Where a company DOES use branches, only its branch
	blocks are shown — the company-level view is what the normal report is for — and any
	invoice left without a branch is therefore not represented in this mode.
	"""
	if not branch_wise:
		for row in rows:
			row.pop("branch", None)
		return [(company, rows)]

	by_branch = {}
	for row in rows:
		by_branch.setdefault(row.pop("branch", ""), []).append(row)

	if len(by_branch) > 1:
		by_branch.pop("", None)

	return [
		("{0} - {1}".format(company, branch) if branch else company, by_branch[branch])
		for branch in sorted(by_branch)
	]


def _total_row(label, rows, columns):
	"""A bold row summing every numeric column of `rows`."""
	total = {"item_name": label, "uom": None, "price_list": None, "bold": 1}
	for col in columns:
		if col.get("fieldtype") in ("Currency", "Float"):
			total[col["fieldname"]] = sum(row.get(col["fieldname"]) or 0 for row in rows)
	return total


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()

	# Company is a required filter (see the report JS), so the UI blocks the report before
	# execute runs. This guard still protects a direct/API call with no Company set.
	companies = _as_list(filters.get("company"))
	if not companies:
		return columns, []

	# Company-wise comparison pivots companies into columns instead of stacking blocks.
	if filters.get("report_type") == COMPARISON:
		return _comparison(filters, companies)

	branch_wise = filters.get("report_type") == BRANCH_WISE

	# One block per company — a heading row carrying the company name, its item rows, then
	# that company's own total. Branch Wise splits each company further, one block per
	# branch headed "Company - Branch"; invoices with no branch keep the plain company
	# heading, so a company that has no branches at all looks exactly as it does normally.
	data = []
	everything = []
	for company in sorted(companies):
		rows = get_data(filters, company, branch_wise)
		if not rows:
			continue

		for title, block in _blocks(company, rows, branch_wise):
			data.append({"item_name": title, "_section": 1, "bold": 1})
			data.extend(block)
			data.append(_total_row(_("Total"), block, columns))
			data.append({})  # spacer between blocks
			everything.extend(block)

	# A closing grand total only earns its place when more than one company is shown.
	if everything and len(data) and sum(1 for row in data if row.get("_section")) > 1:
		data.append(_total_row(_("Grand Total"), everything, columns))

	return columns, data


def get_columns():
	return [
		{"fieldname": "item_name",      "label": _("Item Name"),      "fieldtype": "Data",     "width": 240},
		{"fieldname": "uom",            "label": _("UOM"),            "fieldtype": "Data",     "width": 90},
		{"fieldname": "price_list",     "label": _("Price List"),     "fieldtype": "Data",     "width": 140},
		{"fieldname": "qty",            "label": _("Quantity"),       "fieldtype": "Float",    "width": 110, "precision": 3},
		{"fieldname": "stock_qty",      "label": _("Gas Qty in KG"),  "fieldtype": "Float",    "width": 120, "precision": 3},
		{"fieldname": "rate",           "label": _("Taxable Rate"),   "fieldtype": "Currency", "width": 130, "precision": 5},
		{"fieldname": "taxable_amount", "label": _("Taxable Amount"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "vat_amount",     "label": _("VAT Amount"),     "fieldtype": "Currency", "width": 130},
		{"fieldname": "total_amount",   "label": _("Total Amount"),   "fieldtype": "Currency", "width": 150},
	]


def get_data(filters, company, branch_wise=False):
	"""One row per Item Name + UOM + Price List for a single company, summed over every
	submitted Sales Invoice line in the period. All items are included, gas and non-gas.

	branch_wise adds the invoice's branch to the grouping, so each row also carries the
	branch it belongs to and the caller can split the company into per-branch blocks."""
	conditions = ["si.docstatus = 1", "si.company = %(company)s"]
	values = {"company": company}

	# Frappe's query report drops falsy filter values before sending them, so an UNCHECKED
	# "Include Return" (value 0) never reaches the server. Treat absent as OFF.
	if not frappe.utils.cint(filters.get("include_return")):
		conditions.append("si.is_return = 0")

	from_date, to_date = _period(filters)
	if from_date:
		conditions.append("si.posting_date >= %(from_date)s")
		values["from_date"] = from_date
	if to_date:
		conditions.append("si.posting_date <= %(to_date)s")
		values["to_date"] = to_date
	item = _as_list(filters.get("item"))
	if item:
		conditions.append("sii.item_code IN %(item)s")
		values["item"] = tuple(item)
	price_list = _as_list(filters.get("price_list"))
	if price_list:
		conditions.append("si.selling_price_list IN %(price_list)s")
		values["price_list"] = tuple(price_list)
	branch = _as_list(filters.get("branch"))
	if branch:
		conditions.append("si.custom_branch IN %(branch)s")
		values["branch"] = tuple(branch)

	# In branch-wise mode the branch joins the grouping key; otherwise it is not selected
	# at all and every branch's lines merge into one set of company rows.
	branch_select = "COALESCE(br.branch, '') AS branch," if branch_wise else ""
	branch_group = "COALESCE(br.branch, '')," if branch_wise else ""

	rows = frappe.db.sql(
		f"""
		SELECT
			{branch_select}
			sii.item_name                                        AS item_name,
			sii.uom                                              AS uom,
			COALESCE(pl.price_list_name, si.selling_price_list)  AS price_list,
			MAX(sii.stock_uom)                                   AS stock_uom,
			SUM(sii.qty)                                         AS qty,
			SUM(sii.stock_qty)                                   AS stock_qty,
			SUM(sii.custom_total)                                AS taxable_amount,
			SUM(sii.custom_vat_amount)                           AS vat_amount
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabPrice List` pl ON pl.name = si.selling_price_list
		LEFT JOIN `tabBranch` br ON br.name = si.custom_branch
		WHERE {" AND ".join(conditions)}
		GROUP BY {branch_group} sii.item_name, sii.uom, COALESCE(pl.price_list_name, si.selling_price_list)
		ORDER BY {branch_group} sii.item_name, sii.uom, price_list
		""",
		values,
		as_dict=True,
	)

	kg_uoms = _kg_uoms()

	data = []
	for r in rows:
		qty = r.qty or 0
		taxable_amount = r.taxable_amount or 0
		vat_amount = r.vat_amount or 0
		# Gas Qty in KG is the stock quantity, which only reads as KG for items stocked in a
		# kilogram UOM; an item stocked in Nos (freight, cylinders) contributes 0.
		stock_qty = (r.stock_qty or 0) if (r.stock_uom or "") in kg_uoms else 0
		data.append({
			# Not a report column — execute() groups on it and drops it.
			"branch": r.get("branch") or "",
			"item_name": r.item_name,
			"uom": r.uom,
			"price_list": r.price_list,
			"qty": qty,
			"stock_qty": stock_qty,
			# The group can span several invoices, so the rate is the effective one for the
			# whole group: taxable amount over quantity.
			"rate": (taxable_amount / qty) if qty else 0,
			"taxable_amount": taxable_amount,
			"vat_amount": vat_amount,
			"total_amount": taxable_amount + vat_amount,
		})

	return data


def _kg_uoms():
	"""Names of the UOMs that measure kilograms, taken from the UOM master."""
	names = frappe.get_all("UOM", pluck="name")
	return {n for n in names if n.strip().lower() in ("kg", "kgs", "kilogram", "kilograms")}
