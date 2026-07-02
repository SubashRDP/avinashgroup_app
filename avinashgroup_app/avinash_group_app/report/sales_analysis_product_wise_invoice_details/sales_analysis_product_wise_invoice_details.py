# Copyright (c) 2026, Raindrop and contributors
# For license information, please see license.txt

import json
import os

import frappe
from frappe import _


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


@frappe.whitelist()
def get_company_items(company=None, txt=None):
	"""Product options scoped to the selected company via the item's custom_company."""
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


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Frappe's query report drops falsy filter values before sending them, so an UNCHECKED
	# "Include Return" (value 0) never reaches the server. Treat absent as OFF (cint(None) == 0);
	# the JS filter's default:1 keeps it ON on first load.
	include_return = frappe.utils.cint(filters.get("include_return"))

	columns = get_columns()
	data = build_rows(filters, include_return, include_agent=True)
	return columns, data


def get_columns():
	return [
		{"label": _("Product Code"),                        "fieldname": "product_code", "fieldtype": "Data",     "width": 110},
		{"label": _("Product Name / Customer-Agent Code"),  "fieldname": "label",        "fieldtype": "Data",     "width": 230},
		{"label": _("Invoice Miti"),                        "fieldname": "miti",         "fieldtype": "Data",     "width": 210},
		{"label": _("Invoice Number"),                      "fieldname": "invoice_no",   "fieldtype": "Data",     "width": 170},
		{"label": _("Qty"),                                 "fieldname": "qty",          "fieldtype": "Float",    "width": 100},
		{"label": _("Value"),                               "fieldname": "value",        "fieldtype": "Currency", "width": 130},
		{"label": _("VAT 13%"),                             "fieldname": "vat",          "fieldtype": "Currency", "width": 120},
		{"label": _("Total Incl. VAT"),                     "fieldname": "total_incl_vat", "fieldtype": "Currency", "width": 140},
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
	# kind: 'cust' / 'agent' (plain), 'product' / 'grand' (bold + rule lines).
	row = {"invoice_no": label, "summary_kind": kind}
	if kind in ("product", "grand"):
		row["bold"] = 1
	row.update(vals)
	row.update(flags)
	return row


# ── data ──────────────────────────────────────────────────────────────────────
def _fetch(filters, include_return):
	conditions = ["si.docstatus = 1"]
	values = {"from_date": filters.get("from_date"), "to_date": filters.get("to_date")}
	conditions.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")

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

	# One row per (product, uom, customer, invoice, sales/return).
	# Value = item amount + excise; VAT = custom_vat_amount. Returns are stored negative.
	#
	# The Item/Customer names are NOT joined here: on a large result set (tens of
	# thousands of rows) those joins repeat the same strings on every row and force a
	# filesort. Instead we fetch item_name / customer_name / tax_id in two small lookups
	# below and sort in Python — this keeps the heavy query lean and well-indexed.
	rows = frappe.db.sql(
		f"""
		SELECT
			sii.item_code                                    AS item_code,
			sii.uom                                          AS uom,
			si.customer                                      AS customer_code,
			si.name                                          AS invoice_no,
			si.posting_date                                  AS posting_date,
			SUBSTRING_INDEX(si.custom_invoice_miti, ' ', 1)  AS miti,
			si.is_return                                     AS is_return,
			SUM(sii.qty)                                     AS qty,
			SUM(sii.amount + sii.custom_excise_value)        AS value,
			SUM(sii.custom_vat_amount)                       AS vat
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE {where}
		GROUP BY sii.item_code, sii.uom, si.customer, si.name, si.is_return
		""",
		values,
		as_dict=True,
	)
	if not rows:
		return rows

	# Attach display names from small IN-lookups (one row per distinct item / customer).
	item_codes = {r.item_code for r in rows if r.item_code}
	customer_codes = {r.customer_code for r in rows if r.customer_code}

	item_names = dict(
		frappe.db.sql(
			"SELECT name, item_name FROM `tabItem` WHERE name IN %(items)s",
			{"items": tuple(item_codes)},
		)
	) if item_codes else {}

	cust_info = {}
	if customer_codes:
		for name, cname, pan in frappe.db.sql(
			"SELECT name, customer_name, tax_id FROM `tabCustomer` WHERE name IN %(c)s",
			{"c": tuple(customer_codes)},
		):
			cust_info[name] = (cname, pan)

	for r in rows:
		r.item_name = item_names.get(r.item_code)
		cname, pan = cust_info.get(r.customer_code, (None, None))
		r.customer_name = cname
		r.tax_id = pan

	# Same ordering the SQL used to do (product → uom → customer → date → invoice).
	rows.sort(
		key=lambda r: (
			(r.item_name or "").lower(),
			r.uom or "",
			(r.customer_name or "").lower(),
			r.posting_date or "",
			r.invoice_no or "",
		)
	)
	return rows


def build_rows(filters, include_return, include_agent=True):
	rows = _fetch(filters, include_return)
	if not rows:
		return []

	# Returns are negative in the DB → flip to positive for display, and compute line total.
	for r in rows:
		sign = -1 if r.is_return else 1
		r.qty = (r.qty or 0) * sign
		r.value = (r.value or 0) * sign
		r.vat = (r.vat or 0) * sign
		r.total_incl_vat = r.value + r.vat

	# How many UOMs each product appears in (decides whether to show "(UOM)").
	uoms_per_item = {}
	for r in rows:
		uoms_per_item.setdefault(r.item_code, set()).add(r.uom)

	# Group: product (item_code, uom) → customer → rows
	from collections import OrderedDict
	products = OrderedDict()
	for r in rows:
		products.setdefault((r.item_code, r.uom), OrderedDict()).setdefault(r.customer_code, []).append(r)

	data = []
	grand_sales, grand_returns = _zero(), _zero()

	for (item_code, uom), customers in products.items():
		sample = next(iter(next(iter(customers.values()))))
		product_label = sample.item_name or item_code
		if len(uoms_per_item.get(item_code, set())) > 1 and uom:
			product_label = f"{product_label} ({uom})"

		# Product header row
		data.append({"product_code": item_code, "label": product_label, "bold": 1, "is_product_header": 1})

		# Agent grouping label (no real agent source → always "No Agent").
		if include_agent:
			data.append({"miti": _("No Agent"), "is_agent_group": 1})

		prod_sales, prod_returns = _zero(), _zero()

		for customer_code, crows in customers.items():
			c0 = crows[0]
			pan = f" (Pan no. {c0.tax_id})" if c0.tax_id else ""
			data.append({"label": customer_code, "miti": f"{c0.customer_name or ''}{pan}", "is_customer_header": 1})

			sales = [r for r in crows if not r.is_return]
			returns = [r for r in crows if r.is_return]

			# Invoice sub-section — the sale rows (header shown only when there are sales).
			cust_sales = _zero()
			if sales:
				data.append({"miti": _("Invoice"), "is_section": 1})
				for r in sales:
					data.append(_invoice_row(r))
					_add(cust_sales, r)

			# Return sub-section — the return rows (only when Include Return is on and there
			# are returns). Comes after the Invoice rows.
			cust_ret = _zero()
			if include_return and returns:
				data.append({"miti": _("Return"), "is_section": 1})
				for r in returns:
					data.append(_invoice_row(r))
					_add(cust_ret, r)

			# Summary block — Customer Sales directly above Customer Returns (after both the
			# Invoice and Return rows). Customer Returns shows (0.00 when none) only when
			# Include Return is on.
			data.append(_summary_row(_("Customer Sales"), cust_sales, kind="cust"))
			_add(prod_sales, cust_sales)
			if include_return:
				data.append(_summary_row(_("Customer Returns"), cust_ret, kind="cust"))
				_add(prod_returns, cust_ret)

		# Agent rows mirror the product-level totals (no separate agent source).
		if include_agent:
			data.append(_summary_row(_("Agent Sales"), prod_sales, kind="agent"))
			if include_return:
				data.append(_summary_row(_("Agent Returns"), prod_returns, kind="agent"))
				data.append(_summary_row(_("Agent Net Sales"), _diff(prod_sales, prod_returns), kind="agent"))

		# Product totals block — boxed by a rule above (first row) and below (last row).
		# With returns off there's no Return/Net working (Net would just equal Sales), so the
		# block collapses to the single Product Total Sales row.
		if include_return:
			data.append(_summary_row(_("Product Total Sales"), prod_sales, kind="product", product_start=1))
			data.append(_summary_row(_("Return Totals"), prod_returns, kind="product"))
			data.append(_summary_row(_("Product Net Sales"), _diff(prod_sales, prod_returns), kind="product", product_end=1))
		else:
			data.append(_summary_row(_("Product Total Sales"), prod_sales, kind="product", product_start=1, product_end=1))

		_add(grand_sales, prod_sales)
		_add(grand_returns, prod_returns)

	# Grand totals — a single bold line above this block sets it apart from the products.
	# Returns off → only the Total of Reported Sales row (no Returns/Net).
	data.append(_summary_row(_("Total of Reported Sales"), grand_sales, kind="grand", grand_start=1))
	if include_return:
		data.append(_summary_row(_("Total of Reported Returns"), grand_returns, kind="grand"))
		data.append(_summary_row(_("Net Sales"), _diff(grand_sales, grand_returns), kind="grand"))

	return data


def _invoice_row(r):
	return {
		"miti": r.miti or (frappe.utils.formatdate(r.posting_date) if r.posting_date else ""),
		"invoice_no": r.invoice_no,
		"qty": r.qty,
		"value": r.value,
		"vat": r.vat,
		"total_incl_vat": r.total_incl_vat,
		"is_invoice": 1,
	}


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
	# Frappe's query report drops falsy filter values before sending them, so an UNCHECKED
	# "Include Return" (value 0) never reaches the server. Treat absent as OFF (cint(None) == 0);
	# the JS filter's default:1 keeps it ON on first load.
	include_return = frappe.utils.cint(filters.get("include_return"))
	data = build_rows(filters, include_return, include_agent=True)

	template_path = os.path.join(os.path.dirname(__file__), 'sales_analysis_product_wise_invoice_details_pdf.html')
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
	return _render(filters, orientation or 'Landscape', is_html_view=True)


@frappe.whitelist()
def download_pdf(filters, orientation=None, view=None):
	from frappe.utils.pdf import get_pdf

	if isinstance(filters, str):
		filters = frappe._dict(json.loads(filters))
	orientation = orientation if orientation in ('Portrait', 'Landscape') else 'Landscape'

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

	frappe.response.filename = 'sales_analysis_product_wise_invoice_details.pdf'
	frappe.response.filecontent = pdf_data
	frappe.response.type = 'pdf' if frappe.utils.cint(view) else 'download'
