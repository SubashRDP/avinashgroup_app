# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import json
import os

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# NOTE: Frappe's query report drops falsy filter values before sending them, so an
	# UNCHECKED "Include Return" (value 0) never reaches the server. Treat absent as OFF
	# (cint(None) == 0); the JS filter's default:1 keeps it ON on first load.
	include_return = frappe.utils.cint(filters.get("include_return"))

	columns = get_columns(include_return)
	data = build_rows(filters, include_return)
	return columns, data


def _as_list(value):
	"""Normalize a MultiSelectList filter value (list, JSON string, or single value) to a list."""
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
def get_company_items(company=None, txt=None):
	"""Product options scoped to the selected company(ies) via the item's custom_company.

	Items are global in ERPNext, so the plain Item link lists every item regardless of
	company. Here we scope the Product filter to items assigned to the chosen company
	(custom_company) — or with none set — keeping the dropdown relevant per company.
	"""
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
def get_company_customers(company=None, txt=None):
	"""Customer options scoped to the selected company via the customer's custom_company."""
	company = _as_list(company)
	like = f"%{(txt or '').strip()}%"
	conditions = ["(cust.name LIKE %(txt)s OR cust.customer_name LIKE %(txt)s)"]
	values = {"txt": like}
	if company:
		conditions.append("(cust.custom_company IN %(company)s OR COALESCE(cust.custom_company, '') = '')")
		values["company"] = tuple(company)
	where = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT cust.name AS value, cust.customer_name AS label, cust.name AS description
		FROM `tabCustomer` cust
		WHERE {where}
		ORDER BY cust.customer_name
		LIMIT 50
		""",
		values,
		as_dict=True,
	)


def get_columns(include_return):
	# All columns always show, regardless of "Include Return". Code + Name double up:
	# customer id/name on customer rows, item id/name on product rows. The toggle only
	# controls whether the return-related ROWS appear (handled in build_rows).
	return [
		{"label": _("Customer/Item Code"), "fieldname": "cust_item_code", "fieldtype": "Data",     "width": 130},
		{"label": _("Customer/Item Name"), "fieldname": "cust_item_name", "fieldtype": "Data",     "width": 280},
		{"label": _("Quantity"),           "fieldname": "qty",            "fieldtype": "Float",    "width": 120},
		{"label": _("Value"),              "fieldname": "value",          "fieldtype": "Currency", "width": 150},
		{"label": _("VAT Amount"),         "fieldname": "vat",            "fieldtype": "Currency", "width": 130},
		{"label": _("Total Including VAT"), "fieldname": "total_incl_vat", "fieldtype": "Currency", "width": 160},
	]


# ── accumulator helpers ───────────────────────────────────────────────────────
def _zero():
	return {"qty": 0.0, "value": 0.0, "vat": 0.0, "total_incl_vat": 0.0}


def _add(acc, src):
	for k in ("qty", "value", "vat", "total_incl_vat"):
		acc[k] += src.get(k) or 0


def _diff(a, b):
	return {k: (a.get(k) or 0) - (b.get(k) or 0) for k in ("qty", "value", "vat", "total_incl_vat")}


def _summary_row(label, vals, kind="", **flags):
	# kind: 'product' (per-product sub-totals), 'cust' (customer Total/Net block),
	#       'grand' (report-wide totals). All carry the label in the Name column.
	row = {"cust_item_name": label, "summary_kind": kind, "is_summary": 1}
	row.update(vals)
	row.update(flags)
	return row


# ── data ──────────────────────────────────────────────────────────────────────
def _fetch(filters, include_return):
	conditions = ["si.docstatus = 1", "si.posting_date BETWEEN %(from_date)s AND %(to_date)s"]
	values = {"from_date": filters.get("from_date"), "to_date": filters.get("to_date")}

	if not include_return:
		conditions.append("si.is_return = 0")
	if filters.get("company"):
		conditions.append("si.company IN %(company)s")
		values["company"] = tuple(filters.get("company"))
	if filters.get("customer"):
		conditions.append("si.customer IN %(customer)s")
		values["customer"] = tuple(filters.get("customer"))
	if filters.get("item_code"):
		conditions.append("sii.item_code IN %(item_code)s")
		values["item_code"] = tuple(filters.get("item_code"))

	where = " AND ".join(conditions)

	# One row per (customer, item, uom, sales/return) — a product sold in two UOMs splits
	# into two product blocks. Value = item amount + excise (item `amount` excludes excise
	# on this install); VAT = custom_vat_amount. Returns are stored negative in the DB.
	return frappe.db.sql(
		f"""
		SELECT
			si.customer                               AS customer_code,
			cust.customer_name                        AS customer_name,
			cust.tax_id                               AS tax_id,
			sii.item_code                             AS item_code,
			it.item_name                              AS item_name,
			sii.uom                                   AS uom,
			si.is_return                              AS is_return,
			SUM(sii.qty)                              AS qty,
			SUM(sii.amount + sii.custom_excise_value) AS value,
			SUM(sii.custom_vat_amount)                AS vat
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		JOIN `tabItem` it ON it.name = sii.item_code
		LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
		WHERE {where}
		GROUP BY si.customer, sii.item_code, sii.uom, si.is_return
		ORDER BY cust.customer_name, si.customer, it.item_name, sii.item_code, sii.uom
		""",
		values,
		as_dict=True,
	)


def build_rows(filters, include_return):
	rows = _fetch(filters, include_return)
	if not rows:
		return []

	# Returns are negative in the DB → flip to positive for display, then add the line total.
	for r in rows:
		sign = -1 if r.is_return else 1
		r.qty = (r.qty or 0) * sign
		r.value = (r.value or 0) * sign
		r.vat = (r.vat or 0) * sign
		r.total_incl_vat = r.value + r.vat

	# How many UOMs each product appears in (decides whether to show "(UOM)" on the header).
	uoms_per_item = {}
	for r in rows:
		uoms_per_item.setdefault(r.item_code, set()).add(r.uom)

	# Group: customer → (item, uom) → {sales row, return row}
	from collections import OrderedDict
	customers = OrderedDict()
	for r in rows:
		items = customers.setdefault(r.customer_code, OrderedDict())
		slot = items.setdefault((r.item_code, r.uom), {"sample": r, "sales": None, "returns": None})
		slot["returns" if r.is_return else "sales"] = r

	data = []
	grand_sales, grand_returns = _zero(), _zero()

	for customer_code, items in customers.items():
		c0 = next(iter(items.values()))["sample"]
		pan = f" (Pan no. {c0.tax_id})" if c0.tax_id else ""
		data.append({
			"cust_item_code": customer_code,
			"cust_item_name": f"{c0.customer_name or ''}{pan}",
			"is_customer_header": 1,
		})

		cust_sales, cust_returns = _zero(), _zero()

		for (item_code, uom), slot in items.items():
			s = slot["sample"]
			product_label = s.item_name or item_code
			# Disambiguate only when this item was sold in more than one UOM.
			if len(uoms_per_item.get(item_code, set())) > 1 and uom:
				product_label = f"{product_label} ({uom})"
			data.append({
				"cust_item_code": item_code,
				"cust_item_name": product_label,
				"is_product_header": 1,
			})

			prod_sales = _zero()
			if slot["sales"]:
				_add(prod_sales, slot["sales"])
			data.append(_summary_row(_("Product Totals"), prod_sales, kind="product", product_start=1))

			if include_return:
				prod_returns = _zero()
				if slot["returns"]:
					_add(prod_returns, slot["returns"])
				data.append(_summary_row(_("Return Product Total"), prod_returns, kind="product"))
				data.append(_summary_row(_("Product Totals"), _diff(prod_sales, prod_returns), kind="product", product_end=1))
				_add(cust_returns, prod_returns)
			else:
				# No return working — close the single-row product block.
				data[-1]["product_end"] = 1

			_add(cust_sales, prod_sales)

		# Customer-level totals.
		data.append(_summary_row(_("Total Sales"), cust_sales, kind="cust", cust_start=1,
			cust_end=0 if include_return else 1))
		if include_return:
			data.append(_summary_row(_("Total Return"), cust_returns, kind="cust"))
			data.append(_summary_row(_("Net Sales"), _diff(cust_sales, cust_returns), kind="cust", cust_end=1))

		_add(grand_sales, cust_sales)
		_add(grand_returns, cust_returns)

	# Grand-total block — one bold rule above sets it apart from the customers.
	data.append(_summary_row(_("Total of Reported Sales"), grand_sales, kind="grand", grand_start=1))
	if include_return:
		data.append(_summary_row(_("Total of Reported Returns"), grand_returns, kind="grand"))
		data.append(_summary_row(_("Net Sales"), _diff(grand_sales, grand_returns), kind="grand"))

	return data


# ──────────────────────────────────────────────────────────────────────────────
# PDF / Print  (Download PDF button + Print → same wkhtmltopdf PDF, in-body pages)
# ──────────────────────────────────────────────────────────────────────────────

def _fmt_inr(v):
	# Lakh/crore grouping (e.g. 1,48,85,884.40). 0 shows as 0.00; only None renders empty.
	if v is None:
		return ''
	import locale
	try:
		locale.setlocale(locale.LC_ALL, 'en_IN.UTF-8')
		return locale.format_string('%.2f', v, grouping=True)
	except Exception:
		return '{:,.2f}'.format(v)


def _fmt_qty(v):
	if v is None:
		return ''
	import locale
	try:
		locale.setlocale(locale.LC_ALL, 'en_IN.UTF-8')
		return locale.format_string('%.3f', v, grouping=True)
	except Exception:
		return '{:,.3f}'.format(v)


def _company_label(filters):
	companies = filters.get('company')
	if isinstance(companies, str):
		companies = [companies]
	return ', '.join(companies) if companies else ''


def _render(filters, orientation, is_html_view):
	# NOTE: Frappe's query report drops falsy filter values before sending them, so an
	# UNCHECKED "Include Return" (value 0) never reaches the server. Treat absent as OFF
	# (cint(None) == 0); the JS filter's default:1 keeps it ON on first load.
	include_return = frappe.utils.cint(filters.get("include_return"))
	data = build_rows(filters, include_return)

	template_path = os.path.join(os.path.dirname(__file__), 'sales_analysis_customer_wise_details_pdf.html')
	with open(template_path) as f:
		template_content = f.read()

	return frappe.render_template(template_content, {
		'filters': filters,
		'data': data,
		'fmt': _fmt_inr,
		'fmtq': _fmt_qty,
		'include_return': include_return,
		'orientation': orientation,
		'is_html_view': is_html_view,
		'company_label': _company_label(filters),
	})


@frappe.whitelist()
def get_print_html(filters, orientation=None):
	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	return _render(filters, orientation or 'Portrait', is_html_view=True)


@frappe.whitelist()
def download_pdf(filters, orientation=None, view=None):
	from frappe.utils.pdf import get_pdf

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	orientation = orientation if orientation in ('Portrait', 'Landscape') else 'Portrait'

	html = _render(filters, orientation, is_html_view=False)

	options = {
		'page-size': 'A4',
		'orientation': orientation,
		'margin-top': '10mm',
		'margin-right': '10mm',
		'margin-bottom': '15mm',
		'margin-left': '10mm',
		'encoding': 'UTF-8',
		'enable-local-file-access': None,
	}
	pdf_data = get_pdf(html, options)

	frappe.response.filename = 'sales_analysis_customer_wise_details.pdf'
	frappe.response.filecontent = pdf_data
	frappe.response.type = 'pdf' if frappe.utils.cint(view) else 'download'
