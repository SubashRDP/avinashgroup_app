# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import json
import os

import frappe
from frappe import _
from frappe.utils import flt


THRESHOLD = 100000


def _as_list(value):
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


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("PAN"), "fieldname": "pan", "fieldtype": "Data", "width": 140},
		{"label": _("Name of Tax Payer"), "fieldname": "name_of_tax_payer", "fieldtype": "Data", "width": 220},
		{"label": _("Trade Name Type"), "fieldname": "trade_name_type", "fieldtype": "Data", "width": 120},
		{"label": _("Purchase / Sale"), "fieldname": "purchase_sale", "fieldtype": "Data", "width": 120},
		{"label": _("Taxable Amount"), "fieldname": "taxable_amount", "fieldtype": "Currency", "width": 150},
		{"label": _("Exempted Amount"), "fieldname": "exempted_amount", "fieldtype": "Currency", "width": 150},
	]


def get_data(filters):
	rows = []
	rows.extend(_fetch_sales_rows(filters))
	rows.extend(_fetch_purchase_rows(filters))

	data = []
	for row in rows:
		row.taxable_amount = row.taxable_amount or 0
		row.exempted_amount = row.exempted_amount or 0
		if row.taxable_amount >= THRESHOLD or row.exempted_amount >= THRESHOLD:
			data.append(row)

	data.sort(key=lambda row: ((row.name_of_tax_payer or "").lower(), row.purchase_sale or ""))
	return data


def _company_conditions(alias, values, filters):
	conditions = [f"{alias}.docstatus = 1"]
	companies = _as_list(filters.get("company"))
	if companies:
		conditions.append(f"{alias}.company IN %(company)s")
		values["company"] = tuple(companies)

	if filters.get("from_date"):
		conditions.append(f"{alias}.posting_date >= %(from_date)s")
		values["from_date"] = filters.get("from_date")
	if filters.get("to_date"):
		conditions.append(f"{alias}.posting_date <= %(to_date)s")
		values["to_date"] = filters.get("to_date")

	return conditions


def _fetch_sales_rows(filters):
	values = {}
	conditions = _company_conditions("si", values, filters)
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			cust.tax_id AS pan,
			cust.customer_name AS name_of_tax_payer,
			'E' AS trade_name_type,
			'S' AS purchase_sale,
			COALESCE(SUM(
				CASE
					WHEN COALESCE(sii.custom_vat_amount, 0) != 0 THEN
						CASE WHEN si.is_return = 1 THEN -ABS(sii.amount) ELSE ABS(sii.amount) END
					ELSE 0
				END
			), 0) AS taxable_amount,
			COALESCE(SUM(
				CASE
					WHEN COALESCE(sii.custom_vat_amount, 0) = 0 THEN
						CASE WHEN si.is_return = 1 THEN -ABS(sii.amount) ELSE ABS(sii.amount) END
					ELSE 0
				END
			), 0) AS exempted_amount
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
		WHERE {where}
		GROUP BY si.customer, cust.tax_id, cust.customer_name
		HAVING taxable_amount >= {THRESHOLD} OR exempted_amount >= {THRESHOLD}
		""",
		values,
		as_dict=True,
	)


# ── Print / PDF ──────────────────────────────────────────────────────────────
# Standalone HTML render so browser Print (Ctrl+P) and Download PDF give the same
# full-content, cleanly-paginated output (the datatable itself can't print).

GROUP_NAME = "Nepal Gas Group"
_PAGE_CAP = {"Portrait": 59.0, "Landscape": 37.0}
_NAME_CHARS_PER_LINE = 40


def _fmt_amt(value):
	value = flt(value)
	if abs(value) < 0.005:
		return "-"
	return "{:,.2f}".format(value)


def _company_label(filters):
	selected = _as_list(filters.get("company"))
	if len(selected) == 1:
		return selected[0]
	if len(selected) > 1:
		return ", ".join(selected)
	return GROUP_NAME


def _row_units(row):
	import math

	name = row.get("name_of_tax_payer") or ""
	return float(max(1, math.ceil(len(name) / _NAME_CHARS_PER_LINE)))


def _paginate(rows, orientation):
	cap = _PAGE_CAP.get(orientation, 20.0)
	pages, cur, used = [], [], 0.0
	for row in rows:
		h = _row_units(row)
		if cur and used + h > cap:
			pages.append(cur)
			cur, used = [], 0.0
		cur.append(row)
		used += h
	if cur:
		pages.append(cur)
	return pages or [[]]


def _render(filters, orientation):
	columns, data = execute(filters)
	pages = _paginate(data, orientation)
	template_path = os.path.join(os.path.dirname(__file__), "one_lakh_above_transactions_pdf.html")
	with open(template_path) as f:
		template = f.read()
	return frappe.render_template(
		template,
		{
			"columns": columns,
			"pages": pages,
			"total_pages": len(pages) or 1,
			"company": _company_label(filters),
			"filters": filters,
			"fmt": _fmt_amt,
			"fmtdate": frappe.utils.formatdate,
		},
	)


@frappe.whitelist()
def download_pdf(filters, orientation=None, view=None):
	from frappe.utils.pdf import get_pdf

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	orientation = orientation if orientation in ("Portrait", "Landscape") else "Portrait"

	html = _render(filters, orientation)

	options = {
		"page-size": "A4",
		"orientation": orientation,
		"margin-top": "10mm",
		"margin-right": "8mm",
		"margin-bottom": "12mm",
		"margin-left": "8mm",
		"encoding": "UTF-8",
		"enable-local-file-access": None,
	}
	pdf_data = get_pdf(html, options)

	frappe.response.filename = "one_lakh_above_transactions.pdf"
	frappe.response.filecontent = pdf_data
	frappe.response.type = "pdf" if frappe.utils.cint(view) else "download"


def _fetch_purchase_rows(filters):
	values = {}
	conditions = _company_conditions("pi", values, filters)
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			sup.tax_id AS pan,
			sup.supplier_name AS name_of_tax_payer,
			'E' AS trade_name_type,
			'P' AS purchase_sale,
			COALESCE(SUM(
				CASE
					WHEN COALESCE(pii.custom_vat_amount, 0) != 0 THEN
						CASE WHEN pi.is_return = 1 THEN -ABS(pii.amount) ELSE ABS(pii.amount) END
					ELSE 0
				END
			), 0) AS taxable_amount,
			COALESCE(SUM(
				CASE
					WHEN COALESCE(pii.custom_vat_amount, 0) = 0 THEN
						CASE WHEN pi.is_return = 1 THEN -ABS(pii.amount) ELSE ABS(pii.amount) END
					ELSE 0
				END
			), 0) AS exempted_amount
		FROM `tabPurchase Invoice` pi
		JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		LEFT JOIN `tabSupplier` sup ON sup.name = pi.supplier
		WHERE {where}
		GROUP BY pi.supplier, sup.tax_id, sup.supplier_name
		HAVING taxable_amount >= {THRESHOLD} OR exempted_amount >= {THRESHOLD}
		""",
		values,
		as_dict=True,
	)

